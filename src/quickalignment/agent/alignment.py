"""QuickAlignment for an agent: plate photo -> plate model -> stage positions, corrections, rotations.

The same computations as the QuickAlignment window, without Qt, as methods returning plain dicts:

1. `start`: plate (standard / gating / custom), optic (capillary / zone plate), configuration (newest of the
   optic by default, from configs/).
2. Photo of the plate from above (sample side): `photo_grid` shows it with a pixel grid; the four corners of
   the sample area are read on it (1 top left on the tab side, 2 top right, 3 bottom right, 4 bottom left) and
   `register_photo` maps the photo onto the plate (homography). `photo_overlay` draws the model back onto
   the photo to check it.
3. Samples: `detect_samples` (colour) and / or `add_sample_from_photo` (pixel corners read on the photo),
   `add_sample` (plate mm); devices with `add_device` (plate mm, a pixel on the plate photo, or a pixel on a
   microscope photo registered with `register_device_photo`). The height H is not visible from above.
4. `sample_positions`: ST / SZ / SN of every sample / device at the start rotation (SRn ref, SRz 0).
5. At the beamline: `bring_to_beam` (ST / SZ for the SN in use), `beam_on` (what the beam hits now),
   `found_here` (a target found elsewhere: its sample is moved there), `rotate` (new ST / SZ / SN / optic after
   turning SRn / SRz), `align_edge` (SRn that turns an edge seen on the photo along the slit), `bz_angles`
   (SRn / SRz for a Brillouin-zone point), `collision_check`.

Coordinates: plate frame (x, y) in mm, front view (sample side) with the tab up, origin at the centre of the
back plate, x right, y up; motor positions absolute (ST, SN, SZ in mm, SRn, SRz in degrees, PIX, PIY in µm).
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from ..alignment.photo import (
    apply_homography, camera_matrix, check_corners, check_mirror_3d, corner_points, detect_samples, homography,
    line_transform, pair_transform, plane_homography, plate_view_bounds, rectify, reference_points_3d, rgb_to_lab,
)
from ..alignment.rotation import recentre_piezo, relocate, wrap180
from ..core.calibration import CalibrationRecord, CalibrationStore
from ..core.collision import ACCEPTANCE_HALF_ANGLE, collisions, in_acceptance, motor_limits
from ..core.geometry import PLATES, STANDARD_PLATE, X_EDGES, Y_EDGES, Device, Sample, SampleLayout, custom_plate
from ..core.photon_energy import OpticsEnergyTable, optics_at_energy
from ..core.motors import (
    FOCUS_WARNING, LARGE_FOUND_OFFSET, PLATE_OFFSET_WARNING, TOLERANCE, TRAVEL, out_of_range, set_motor_limits,
)
from ..core.session import Session
from ..core.stage import (
    MotorPositions, StageModel, apply_found_offset, check_height, checked_sn, focus_correction, found_offset,
    height_from_sn, sn_from_height, sn_to_focus,
)
from .common import APIError, motors_dict, motors_from, number, optic_short, optic_type, rounded
from .photos import grid_png, overlay_png, plate_png, read_image

DEFAULT_HEIGHT = 0.525  # mm, Si wafer (standard 100 mm wafer) when the user gives no height
SRN_USABLE = (60.0, 180.0)  # deg, SRn range used for proposals (120 +- 60)


class _Photo:
    """A registered photo: pixels (if read from a file) and the map photo pixel <-> plate mm."""

    def __init__(self, photo_id: str, kind: str, to_plate: np.ndarray, path: str | None, size, corners=None,
                 rgb=None, rms: float = 0.0, camera: np.ndarray | None = None, points_3d=None):
        self.id, self.kind, self.path, self.size = photo_id, kind, path, size
        self.to_plate = to_plate  # 3 x 3: photo px -> plate mm, in the plane of the registration
        self.to_photo = np.linalg.inv(to_plate)
        self.corners = corners or []  # the four sample-area corners on the photo
        self.rgb = rgb
        self.rms = rms
        self.camera = camera  # 3 x 4 camera matrix with the 3D correction, else None
        self.points_3d = points_3d or []  # [(name, (u, v, w), (x, y))] used for the camera

    def homography(self, w: float | None = None) -> np.ndarray:
        """Plate (u, v) -> photo px in the plane at height w (3D correction); the registration plane otherwise."""
        if self.camera is None or w is None:
            return self.to_photo
        return plane_homography(self.camera, w)

    def plate(self, pts, w: float | None = None) -> np.ndarray:
        return apply_homography(np.linalg.inv(self.homography(w)), np.asarray(pts, float).reshape(-1, 2))

    def pixels(self, pts, w: float | None = None) -> np.ndarray:
        return apply_homography(self.homography(w), np.asarray(pts, float).reshape(-1, 2))

    def info(self) -> dict:
        out = {"photo_id": self.id, "kind": self.kind, "path": self.path, "size_px": list(self.size) if self.size else None}
        if self.kind == "plate":
            out["corners_px"] = rounded([list(c) for c in self.corners], 1)
            out["3d_correction"] = self.camera is not None
            if self.camera is not None:
                out["camera_rms_px"] = rounded(self.rms, 2)
        else:
            out["pair_rms_mm"] = rounded(self.rms, 4)
        return out


class AlignmentSession:
    """One plate on the stage: its samples, the configuration in use, registered photos, the stage position."""

    def __init__(self, configs: str | Path | None = None):
        self.store = CalibrationStore(configs)
        self.layout = SampleLayout()
        self.optic = optic_type("capillary")
        self.record = CalibrationRecord()
        self.photos: dict[str, _Photo] = {}
        self.motors: MotorPositions | None = None  # the stage as last reported by the user
        self.optic_position: float | None = None
        self.started = False
        self.photon_energy: float | None = None  # eV; None: the photon energy of the configuration (95 eV)
        self.energy_table = OpticsEnergyTable.load(self.store.folder)

    # ------------------------------------------------------------------------------------------------- setup
    def plates(self) -> dict:
        """The sample plates the program knows, with their sample area and the photo corners."""
        out = []
        for key, plate in PLATES.items():
            u0, v0, u1, v1 = plate.riser_bounds()
            out.append({"key": key, "name": plate.name, "sample_area_mm": {"x": [u0, u1], "y": [v0, v1]},
                        "riser_height_mm": plate.total_thickness})
        out.append({"key": "custom", "name": "Custom plate: the standard back plate with a block of your size",
                    "needs": {"length": "block size along x (mm)", "width": "block size along y (mm)",
                              "height": "block top above the back face of the plate (mm; standard riser 5.0)",
                              "center_y": "block centre along y (mm, default 0)"}})
        return {"plates": out, "note": "Standard and gating plates share the 18 x 15.5 mm Ta back plate. The gating "
                "plate takes samples only on the upper 10.5 mm of the riser, above its contact block."}

    def configurations(self, optic: str | None = None) -> dict:
        records = self.store.records()
        if optic is not None:
            name = optic_short(optic_type(optic))
            records = [r for r in records if r.optic_name == name]
        return {"folder": str(self.store.folder), "configurations": [
            {"label": r.label, "file": r.path.name if r.path else None, "optic": r.optic_name,
             "plate": r.plate or "standard (not recorded)", "comment": r.comment}
            for r in records], "note": "Newest first; `start` uses the newest of the chosen optic. A configuration "
                                       "made with another plate than the one mounted is corrected for the plate "
                                       "seat height (PLATE_SEAT_V; gating and standard plates now both 0: the "
                                       "pin springs back, measured 2026-11-19)."}

    def start(self, plate: str = "standard", optic: str | None = "capillary", custom_plate_mm: dict | None = None,
              configuration: str | None = None) -> dict:
        """Begin with an empty plate: plate type, optic and configuration (default: the newest for the optic)."""
        key = str(plate or "standard").strip().lower()
        if key.startswith("gat"):
            geometry = PLATES["gating"]
        elif key.startswith("stand") or key in ("std", "ta"):
            geometry = STANDARD_PLATE
        elif key.startswith("cust"):
            if not custom_plate_mm:
                raise APIError("A custom plate needs custom_plate_mm = {length, width, height, center_y} (mm).")
            p = {k: number(custom_plate_mm.get(k, 0.0 if k == "center_y" else None), k)
                 for k in ("length", "width", "height", "center_y")}
            try:
                geometry = custom_plate(p["length"], p["width"], p["height"], p["center_y"])
            except ValueError as exc:
                raise APIError(str(exc)) from None
        else:
            raise APIError(f"Unknown plate {plate!r}: 'standard', 'gating' or 'custom'.")
        self.optic = optic_type(optic)
        self.record = self._find_record(configuration)
        set_motor_limits(self.store.motor_limits())
        self.layout = SampleLayout(plate=geometry)
        self.photos = {}
        self.motors = None
        self.optic_position = None
        self.started = True
        return {"plate": geometry.name, "optic": self.optic, "configuration": self._record_info(),
                "photo_corners": self.photo_corners()["corners"],
                "next": "Send / give the path of a photo of the plate taken from above (sample side). Call "
                        "photo_grid on it, read the four corners of the sample area in the order of "
                        "photo_corners, and call register_photo."}

    def _find_record(self, configuration: str | None) -> CalibrationRecord:
        if not configuration:
            return self.store.latest(self.optic)
        text = str(configuration).strip()
        for r in self.store.records():
            if text in (r.label, r.created, r.path.name if r.path else None, r.path.stem if r.path else None):
                return r
        raise APIError(f"No configuration {configuration!r} in {self.store.folder}; see configurations().")

    def _record_info(self) -> dict:
        r = self.record
        c = self.model.config
        note = r.plate_note(self.layout.plate.key) if self.started else ""
        return {"label": r.label, "file": r.path.name if r.path else None, "comment": r.comment,
                "made_with_plate": r.plate or "standard (not recorded)",
                **({"plate_correction": note} if note else {}),
                "constants": rounded({"st0": c.st0, "sz0": c.sz0, "sn_f": c.sn_f, "srn_ref": c.srn_ref,
                                      "srn_axis": [c.srn_axis_u, c.srn_axis_v],
                                      "srz_offset_st": c.srz_offset_t, "srz_offset_sn": c.srz_offset_n}),
                "optic_reference": rounded(r.optics.optic_position) if r.optics.enabled else "not calibrated"}

    def _need_start(self) -> None:
        if not self.started:
            raise APIError("Call start(plate, optic) first: which sample plate and which focusing optic?")

    @property
    def model(self) -> StageModel:
        return StageModel(self.record.config_for(self.layout.plate.key, self.layout.plate_offset_v), self.layout.plate)

    @property
    def optics(self):
        """The configuration's optic reference at the photon energy in use (photon_energy.py)."""
        return optics_at_energy(self.record.optics, self.energy_table, self.photon_energy)[0]

    def _energy_info(self) -> dict:
        cal = self.record.optics
        moved, shift = optics_at_energy(cal, self.energy_table, self.photon_energy)
        return {"photon_energy_eV": rounded(moved.photon_energy), "configuration_photon_energy_eV": cal.photon_energy,
                "optic_shift_mm": rounded(shift.shift), "optic_shift_source": shift.source}

    def status(self) -> dict:
        self._need_start()
        return {"plate": self.layout.plate.name, "optic": self.optic, "configuration": self._record_info(),
                "samples": self.samples()["samples"], "photos": [p.info() for p in self.photos.values()],
                "stage": None if self.motors is None else motors_dict(self.motors),
                "optic_position": rounded(self.current_optic()), "photon_energy": self._energy_info()}

    # ------------------------------------------------------------------------------------------------ photos
    def photo_corners(self) -> dict:
        """The four points to read on a plate photo, in this order (plate mm)."""
        plate = self.layout.plate
        corners = [{"number": i + 1, "name": name, "plate_mm": [u, v]} for i, (name, (u, v)) in
                   enumerate(corner_points(plate))]
        what = ("the raised block (custom plate)" if plate.key == "custom" else
                "the sample area: the upper part of the riser, above the contact block (gating plate)" if
                plate.contact_block else "the riser top face (the raised 11 mm wide part)")
        return {"corners": corners, "what": f"Corners of {what}; 'top' is the tab side of the plate.",
                "order": "1 top left, 2 top right, 3 bottom right, 4 bottom left, as seen on the photo of the sample "
                         "side with the tab up (the order turns with the photo if it is rotated)."}

    def photo_info(self, path: str) -> dict:
        rgb = read_image(path)
        return {"path": str(Path(path).expanduser()), "width_px": int(rgb.shape[1]), "height_px": int(rgb.shape[0]),
                "note": "Pixel coordinates: x right, y down, origin top left, after the EXIF rotation."}

    def photo_grid(self, path: str | None = None, photo_id: str | None = None, region=None, step: float | None = None,
                   marks=None) -> dict:
        """The photo (or a zoomed region [x0, y0, x1, y1]) with a pixel grid, to read coordinates precisely."""
        rgb, path = self._rgb(path, photo_id)
        png, info = grid_png(rgb, region, step, marks or ())
        return {"image_png": png, **info, "path": path}

    def _rgb(self, path, photo_id):
        if path:
            return read_image(path), str(path)
        photo = self._photo(photo_id)
        if photo.rgb is None:
            if not photo.path:
                raise APIError(f"Photo {photo.id!r} was registered without its file: give its path.")
            photo.rgb = read_image(photo.path)
        return photo.rgb, photo.path

    def _photo(self, photo_id: str | None, kind: str | None = None) -> _Photo:
        if not self.photos:
            raise APIError("No photo registered yet: register_photo first.")
        if photo_id is None:
            candidates = [p for p in self.photos.values() if kind is None or p.kind == kind]
            if not candidates:
                raise APIError(f"No {kind} photo registered.")
            return candidates[-1]
        if photo_id not in self.photos:
            raise APIError(f"No photo {photo_id!r}; registered: {list(self.photos)}.")
        return self.photos[photo_id]

    def register_photo(self, corners_px, path: str | None = None, image_size=None, photo_id: str | None = None) -> dict:
        """Map a plate photo onto the plate from the four sample-area corners read on it (photo pixels, in the
        order of photo_corners). `path`: the image file (needed for detect_samples and the overlays); without it
        give `image_size` [width, height] of the image the corners were read on."""
        self._need_start()
        pts = np.asarray(corners_px, float)
        if pts.shape != (4, 2):
            raise APIError("corners_px: four [x, y] pixel points, in the order of photo_corners.")
        ref = [p for _, p in corner_points(self.layout.plate)]
        try:
            check_corners(ref, pts)
            h = homography(ref, pts)  # plate -> photo
        except ValueError as exc:
            raise APIError(str(exc)) from None
        rgb, size = None, None
        if path:
            rgb = read_image(path)
            size = (int(rgb.shape[1]), int(rgb.shape[0]))
        elif image_size is not None:
            size = (int(number(image_size[0], "width")), int(number(image_size[1], "height")))
        if size and not all(-0.05 * size[i % 2] <= c <= 1.05 * size[i % 2] for xy in pts for i, c in enumerate(xy)):
            raise APIError(f"A corner is outside the photo ({size[0]} x {size[1]} px).")
        pid = photo_id or (Path(path).stem if path else f"photo{len(self.photos) + 1}")
        photo = _Photo(pid, "plate", np.linalg.inv(h), str(Path(path).expanduser()) if path else None, size,
                       [tuple(p) for p in pts.tolist()], rgb)
        self.photos[pid] = photo
        u0, v0, u1, v1 = self.layout.plate.riser_bounds()
        side_px = [float(np.linalg.norm(pts[i] - pts[(i + 1) % 4])) for i in range(4)]
        side_mm = [u1 - u0, v1 - v0, u1 - u0, v1 - v0]
        ppm = [p / m for p, m in zip(side_px, side_mm)]
        warn = []
        if max(ppm) / min(ppm) > 1.5:
            warn.append("The sides of the area differ a lot in scale (strong perspective, or a corner misplaced): "
                        "check photo_overlay.")
        if min(ppm) < 15:
            warn.append(f"Only about {min(ppm):.0f} px per mm: positions from this photo are rough (±0.1 mm or worse).")
        return {"photo_id": pid, "pixels_per_mm": rounded(sum(ppm) / 4, 1), "warnings": warn,
                "next": "Check with photo_overlay (the green outline must lie on the sample-area edges), then find the "
                        "samples (detect_samples / add_sample_from_photo)."}

    def photo_points_3d(self) -> dict:
        """Points that can be used for the optional 3D correction of an oblique photo, with their plate (x, y) and
        height w above the back face (mm)."""
        self._need_start()
        pts = reference_points_3d(self.layout.plate)
        return {"points": [{"number": i + 1, "name": n, "plate_mm": [u, v, w]} for i, (n, (u, v, w)) in enumerate(pts)],
                "note": "Optional, only for photos not taken from straight above. Give at least 6 points, at two heights "
                        "or more: the 4 sample-area corners (on the riser) plus corners of the back plate or of the tab "
                        "(1.1 mm above the back face). More points = better; skip what you cannot see clearly."}

    def register_photo_3d(self, points, path: str | None = None, image_size=None, photo_id: str | None = None) -> dict:
        """OPTIONAL 3D correction for an oblique photo: a camera model from >= 6 points at several heights
        ([{"name" or "number" from photo_points_3d, "px": [x, y]}] or [{"plate_mm": [x, y, w], "px": [x, y]}]).
        Positions at any height (thick samples, devices) are then corrected for the perspective."""
        self._need_start()
        known = reference_points_3d(self.layout.plate)
        names = {n.lower(): (n, xyz) for n, xyz in known}
        used = []
        for i, p in enumerate(points or []):
            if not isinstance(p, dict) or "px" not in p:
                raise APIError(f"point {i + 1}: give 'px' [x, y] and 'name' / 'number' or 'plate_mm' [x, y, w].")
            px = (number(p["px"][0], "x"), number(p["px"][1], "y"))
            if "plate_mm" in p:
                xyz = tuple(number(c, "plate_mm") for c in p["plate_mm"])
                if len(xyz) != 3:
                    raise APIError(f"point {i + 1}: plate_mm is [x, y, w] (w: height above the back face).")
                used.append((p.get("name") or f"point {i + 1}", xyz, px))
            elif "number" in p:
                k = int(number(p["number"], "number")) - 1
                if not 0 <= k < len(known):
                    raise APIError(f"point {i + 1}: number 1 … {len(known)} (photo_points_3d).")
                used.append((known[k][0], known[k][1], px))
            elif str(p.get("name", "")).lower() in names:
                n, xyz = names[str(p["name"]).lower()]
                used.append((n, xyz, px))
            else:
                raise APIError(f"point {i + 1}: unknown name {p.get('name')!r}; see photo_points_3d.")
        try:
            cam, rms, res = camera_matrix([u for _, u, _ in used], [x for _, _, x in used])
            top = self.layout.plate.total_thickness
            check_mirror_3d(cam, top)
        except ValueError as exc:
            raise APIError(str(exc)) from None
        h = plane_homography(cam, top)
        rgb, size = None, None
        if path:
            rgb = read_image(path)
            size = (int(rgb.shape[1]), int(rgb.shape[0]))
        elif image_size is not None:
            size = (int(number(image_size[0], "width")), int(number(image_size[1], "height")))
        corners = apply_homography(h, [uv for _, uv in corner_points(self.layout.plate)])
        pid = photo_id or (Path(path).stem if path else f"photo{len(self.photos) + 1}")
        self.photos[pid] = _Photo(pid, "plate", np.linalg.inv(h), str(Path(path).expanduser()) if path else None, size,
                                  [tuple(c) for c in corners.tolist()], rgb, rms, cam, used)
        worst = sorted(zip(res, [n for n, _, _ in used]), reverse=True)
        warn = [f"'{n}' is {r:.1f} px off the camera model: check it." for r, n in worst
                if r > max(8.0, 3 * float(np.median(res)))]
        return {"photo_id": pid, "3d_correction": True, "points_used": len(used), "rms_px": rounded(rms, 2),
                "residual_px": {n: rounded(float(r), 1) for r, n in worst}, "warnings": warn,
                "next": "Check with photo_overlay (back plate outline at its own height, samples at theirs)."}

    def register_device_photo(self, pairs, path: str | None = None, photo_id: str | None = None,
                              plate_photo_id: str | None = None, direction: dict | None = None) -> dict:
        """A close-up (microscope) photo of a substrate, mapped onto the plate. Recommended: `direction`, the same
        direction on both, as two points A -> B along a substrate edge or a long pattern line on each, {"photo":
        [[x, y], [x, y]], "plate_mm": [[x, y], [x, y]] or "plate_photo_px": [...]} (only the direction counts: A and B
        need not be the same places on both): it sets the in-plane orientation, and the point `pairs` (>= 2) then set
        the scale and the shift by least squares, without distorting the photo. `pairs`: the same feature (substrate
        corner, mark) seen on this photo (`photo` px) and on the plate (`plate_mm`, or `plate_photo_px` on the
        registered plate photo). Without `direction` (former way): 2 pairs similarity, 3 affine, >= 4 perspective."""
        self._need_start()
        plate_photo = None

        def plate_point(p, what):
            nonlocal plate_photo
            if "plate_mm" in p:
                return [number(p["plate_mm"][0], "x"), number(p["plate_mm"][1], "y")]
            if "plate_photo_px" in p:
                plate_photo = plate_photo or self._photo(plate_photo_id, "plate")
                return plate_photo.plate([p["plate_photo_px"]])[0].tolist()
            raise APIError(f"{what}: give 'plate_mm' or 'plate_photo_px'.")

        src, dst = [], []
        for i, p in enumerate(pairs or []):
            if "photo" not in p:
                raise APIError(f"pair {i + 1}: give 'photo' [x, y] and 'plate_mm' or 'plate_photo_px'.")
            src.append([number(p["photo"][0], "x"), number(p["photo"][1], "y")])
            dst.append(plate_point(p, f"pair {i + 1}"))
        fit = None
        try:
            if direction is not None:
                line = direction if isinstance(direction, dict) else {}
                ends = line.get("photo")
                key = next((k for k in ("plate_mm", "plate_photo_px") if k in line), None)
                if not ends or len(ends) != 2 or key is None or len(line[key]) != 2:
                    raise APIError("direction: give 'photo' [[x, y], [x, y]] and 'plate_mm' or 'plate_photo_px' "
                                   "[[x, y], [x, y]] (two points A -> B along the same direction on both).")
                line_px = [[number(e[0], "x"), number(e[1], "y")] for e in ends]
                line_mm = [plate_point({key: e}, "direction") for e in line[key]]
                fit = line_transform(line_px, line_mm, src, dst)
                t, rms = fit.t, fit.rms
            else:
                t, rms = pair_transform(src, dst)
        except ValueError as exc:
            raise APIError(str(exc)) from None
        rgb = read_image(path) if path else None
        pid = photo_id or (Path(path).stem if path else f"device_photo{len(self.photos) + 1}")
        size = (int(rgb.shape[1]), int(rgb.shape[0])) if rgb is not None else None
        self.photos[pid] = _Photo(pid, "device", t, str(path) if path else None, size, rgb=rgb, rms=rms)
        out = {"photo_id": pid, "pair_rms_mm": rounded(rms, 4),
               "mm_per_px": rounded(float(np.sqrt(abs(np.linalg.det(t[:2, :2])))), 6),
               "next": "add_device(sample, name, photo_px=[x, y], photo_id=...) for each device on this photo."}
        if fit is not None:
            out["transform"] = "rotation from the direction + scale + shift (least squares, no distortion)"
            out["rotation_deg"] = rounded(fit.angle, 2)
            out["pair_residual_mm"] = [rounded(float(r), 4) for r in fit.residuals]
            if fit.angle_check is not None:
                out["points_angle_check_deg"] = rounded(fit.angle_check, 2)
            warn = []
            if rms > 0.02:
                warn.append(f"pair {int(np.argmax(fit.residuals)) + 1} is the farthest off: check it.")
            if len(src) >= 3 and fit.angle_check is not None and abs(fit.angle_check) > 2:
                warn.append(f"the points would turn the photo {fit.angle_check:+.1f} deg more than the direction: "
                            "check that the direction lines follow the same feature on both.")
            out["warnings"] = warn
        else:
            out["transform"] = {2: "similarity (rotation, scale, shift)", 3: "affine"}.get(len(src), "perspective")
            out["hint"] = ("Give 'direction' (along the same edge on both) to set the orientation: the pairs then fit only scale "
                           "and shift, by least squares, and more pairs do not distort the photo.")
        return out

    def _w(self, height: float | None) -> float:
        """Height above the back face of a surface `height` mm above the plate surface (sample area)."""
        return self.layout.plate.total_thickness + (0.0 if height is None else number(height, "height"))

    def photo_to_plate(self, points_px, photo_id: str | None = None, height: float | None = None) -> dict:
        """Photo pixels -> plate mm, in the plane `height` mm above the plate surface (only with the 3D correction;
        default 0: the sample-area plane)."""
        photo = self._photo(photo_id)
        uv = photo.plate(points_px, self._w(height))
        r0, s0, r1, s1 = self.layout.plate.riser_bounds()
        return {"photo_id": photo.id, "plate_mm": [
            {"x": rounded(float(u), 3), "y": rounded(float(v), 3),
             "in_sample_area": bool(r0 <= u <= r1 and s0 <= v <= s1)} for u, v in uv]}

    def plate_to_photo(self, points_mm, photo_id: str | None = None, height: float | None = None) -> dict:
        photo = self._photo(photo_id)
        return {"photo_id": photo.id, "photo_px": rounded(photo.pixels(points_mm, self._w(height)).tolist(), 1)}

    def photo_overlay(self, photo_id: str | None = None, region=None) -> dict:
        """The registered plate photo with the model drawn on it, to check the corners and the samples."""
        photo = self._photo(photo_id, "plate")
        rgb, _ = self._rgb(None, photo.id)
        png = overlay_png(rgb, photo.pixels, self.layout.plate, self.layout, photo.corners, region=region,
                          outline=photo.camera is not None)
        return {"image_png": png, "legend": "green: sample area of the model; blue: samples (names in yellow); red: "
                "devices; yellow crosses: the corners given; white (3D correction only): back plate outline. Everything should lie on the photo's "
                "edges; if not, correct the corners (register_photo again) or the samples."}

    def plate_view(self) -> dict:
        """The plate model (front view, tab up) with the samples and devices, axes in plate mm."""
        self._need_start()
        return {"image_png": plate_png(self.layout, f"{self.layout.plate.name} — {len(self.layout.samples)} sample(s)")}

    # --------------------------------------------------------------------------------- manual annotation
    def manual_annotation(self, photo_id: str | None = None) -> dict:
        """Open the "Samples from a photo" window on the user's screen with this photo and its registration, so the
        user marks / corrects the samples and devices by hand (when they are not satisfied with what was found).
        Returns at once; call load_annotation when the user has pressed OK."""
        import importlib.util
        import subprocess
        import sys
        import tempfile

        photo = self._photo(photo_id, "plate")
        if not photo.path:
            raise APIError("The window needs the photo file: register_photo with its path first.")
        if not any(importlib.util.find_spec(m) for m in ("PyQt5", "PySide6")):
            raise APIError("No Qt on this computer, the window cannot open. Alternatives: the user tells the corrections "
                           "(positions / sizes) in the chat, or gives the sample corners read on photo_grid.")
        folder = Path(tempfile.mkdtemp(prefix="quickalignment_annotation_"))
        layout_file, out = folder / "layout.json", folder / "result.json"
        self.layout.save(layout_file)
        args = [sys.executable, "-m", "quickalignment.ui.annotate", "--photo", photo.path, "--layout", str(layout_file),
                "--out", str(out), "--height", f"{DEFAULT_HEIGHT}"]
        if photo.camera is not None:
            from ..alignment.photo import GUI_POINTS_3D, project
            xyz = [p_ for _, p_ in reference_points_3d(self.layout.plate)[:GUI_POINTS_3D]]
            args += ["--points-3d", ";".join(f"{x:.2f},{y:.2f}" for x, y in project(photo.camera, xyz))]
        else:
            args += ["--corners", ";".join(f"{x:.2f},{y:.2f}" for x, y in photo.corners)]
        src = str(Path(__file__).resolve().parents[2])
        env = dict(__import__("os").environ, PYTHONPATH=src)
        log = folder / "window.log"
        # The MCP server talks over stdin / stdout: the window must not inherit them. On Windows a child sharing a
        # synchronous pipe that the server is reading hangs at start-up (no window ever shows), and anything it
        # printed would corrupt the protocol. Its errors go to window.log instead.
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        with open(log, "w", encoding="utf-8") as err:
            proc = subprocess.Popen(args, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=err,
                                    close_fds=True, creationflags=flags)
        self._annotation = (proc, out)
        self._annotation_photo = photo.id
        try:  # a window that fails to start (missing module, bad photo...) usually exits within a few seconds
            code = proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            code = None
        if code is not None:
            self._annotation = (None, None)
            raise APIError(f"The annotation window failed to start (exit code {code}): "
                           f"{log.read_text(encoding='utf-8', errors='replace').strip()[-1500:] or 'no error text'}")
        return {"opened": True, "result_file": str(out), "log_file": str(log),
                "tell_the_user": "A window 'Samples from a photo — manual annotation' is open with your photo, already "
                                 "registered. Draw boxes on the samples (Draw box on plate model, on by default: "
                                 "drag in the right view), delete or merge wrong ones, set the names and heights H, "
                                 "add devices in the Step 2 tab if needed, then press OK.",
                "next": "When the user says they are done, call load_annotation."}

    def load_annotation(self, path: str | None = None, wait: bool = False) -> dict:
        """Read the result of the manual-annotation window into the plate (replacing the samples if the user chose
        so in the window, else adding them)."""
        proc, out = getattr(self, "_annotation", (None, None))
        if path:
            out = Path(path)
        if out is None:
            raise APIError("No manual annotation was started (manual_annotation).")
        if proc is not None and proc.poll() is None:
            if not wait:
                return {"done": False, "note": "The window is still open: ask the user to press OK (or Cancel)."}
            proc.wait()
        if not Path(out).exists():
            log = Path(out).with_name("window.log")
            text = log.read_text(encoding="utf-8", errors="replace").strip()[-1500:] if log.exists() else ""
            raise APIError("The window was closed without a result (it may have failed to start)."
                           + (f" Its errors: {text}" if text else ""))
        from ..core.fileio import read_json
        data = read_json(out)
        if not data.get("accepted"):
            return {"done": True, "accepted": False, "note": "The user cancelled: nothing changed."}
        new = SampleLayout.from_dict({"plate_type": "standard", "samples": data.get("samples", [])}).samples
        if data.get("replace"):
            self.layout.samples.clear()
        for s in new:
            if not s.name or any(o.name == s.name for o in self.layout.samples):
                s.name = self.layout.unique_name()
            self.layout.samples.append(s)
        self._annotation = (None, None)
        out_dict = {"done": True, "accepted": True, "replaced": bool(data.get("replace"))}
        reg = self._adopt_annotation_registration(data)
        if reg:
            out_dict["registration"] = reg
        return {**out_dict, **self.samples()}

    def _adopt_annotation_registration(self, data: dict) -> dict | None:
        """The user's registration from the window replaces the session's (the user's points win over the
        assistant's): the samples were measured with it."""
        pid = getattr(self, "_annotation_photo", None)
        photo = self.photos.get(pid) if pid else None
        if photo is None:
            return None
        if data.get("points_3d"):
            new = [tuple(p["px"]) for p in data["points_3d"]]
            old = [tuple(px) for _, _, px in photo.points_3d] if photo.camera is not None else []
            if len(old) == len(new) and np.allclose(old, new, atol=0.5):
                return {"changed": False}
            res = self.register_photo_3d(data["points_3d"], path=photo.path, photo_id=photo.id)
        elif data.get("corners_px"):
            new = [tuple(p) for p in data["corners_px"]]
            if photo.camera is None and np.allclose(photo.corners, new, atol=0.5):
                return {"changed": False}
            res = self.register_photo(new, path=photo.path, photo_id=photo.id)
        else:
            return None
        return {"changed": True, "note": "The user moved the registration points in the window: the photo is now "
                "registered with THEIR points (they win over the assistant's).", **res}

    # ----------------------------------------------------------------------------------------------- samples
    def detect_samples(self, photo_id: str | None = None, threshold: float = 12.0, min_area_mm2: float = 0.2,
                       sample_colors_px=None, background_px=None) -> dict:
        """Samples found by colour on the registered plate photo (nothing is added): boxes in plate mm.

        Without `sample_colors_px` a sample is what differs from the bare plate by more than `threshold` (ΔE,
        CIELAB); with pixels picked on samples it is what is within `threshold` of their colours (leaves out
        silver paint, glue, wires)."""
        photo = self._photo(photo_id, "plate")
        rgb, _ = self._rgb(None, photo.id)
        rect = rectify(rgb, photo.to_photo, plate_view_bounds(self.layout.plate))

        def lab_at(px):
            x, y = int(round(number(px[0], "x"))), int(round(number(px[1], "y")))
            patch = rgb[max(0, y - 3): y + 4, max(0, x - 3): x + 4].reshape(-1, 3).astype(np.float32)
            if not len(patch):
                raise APIError(f"pixel {px} is not on the photo.")
            return rgb_to_lab(patch.mean(axis=0)[None, None, :])[0, 0]

        colors = [lab_at(p) for p in sample_colors_px] if sample_colors_px else None
        background = lab_at(background_px) if background_px else None
        try:
            res = detect_samples(rect, self.layout.plate.riser_bounds(), threshold, min_area_mm2,
                                 background=background, sample_colors=colors)
        except ValueError as exc:
            raise APIError(str(exc)) from None
        out = []
        for i, d in enumerate(res.detections):
            (u, v), (length, width) = d.center, d.size
            out.append({"index": i, "x": rounded(u, 3), "y": rounded(v, 3), "length": rounded(length, 3),
                        "width": rounded(width, 3), "area_mm2": rounded(d.area, 3), "delta_e": rounded(d.delta_e, 1),
                        "photo_px_center": rounded(photo.pixels([(u, v)])[0].tolist(), 1)})
        return {"detections": out, "note": "Boxes (axis-aligned on the plate) of the regions found. Compare with the "
                "photo: merge pieces of one sample, drop dust / paint, then add them with add_sample (H is not "
                "visible on the photo: ask the user)."}

    def _unique(self, name: str | None) -> str:
        if not name:
            return self.layout.unique_name()
        if any(s.name == name for s in self.layout.samples):
            raise APIError(f"There is already a sample called {name!r}.")
        if "/" in name:
            raise APIError("Sample names cannot contain '/'.")
        return str(name)

    def _sample(self, name: str) -> Sample:
        s = self.layout.sample_of(str(name))
        if s is None:
            raise APIError(f"No sample {name!r}; samples: {[x.name for x in self.layout.samples]}.")
        return s

    def add_sample(self, x: float, y: float, length: float, width: float, height: float | None = None,
                   name: str | None = None) -> dict:
        """A rectangular sample: centre (x, y), length along x, width along y (plate mm), height H (mm)."""
        self._need_start()
        s = Sample(self._unique(name), number(x, "x"), number(y, "y"), number(length, "length"),
                   number(width, "width"), DEFAULT_HEIGHT if height is None else number(height, "height"))
        if s.length <= 0 or s.width <= 0 or s.height < 0:
            raise APIError("length and width must be > 0 and the height >= 0.")
        self.layout.samples.append(s)
        return {"added": self._sample_info(s), "height_assumed": height is None}

    def add_sample_from_photo(self, points_px, height: float | None = None, name: str | None = None,
                              photo_id: str | None = None) -> dict:
        """A sample from points read on the plate photo: its 4 corners (any order), or 2 opposite corners of its
        box. The sample is the plate rectangle around them; its in-plane angle is reported."""
        photo = self._photo(photo_id, "plate")
        pts = np.asarray(points_px, float).reshape(-1, 2)
        if len(pts) < 2:
            raise APIError("Give at least 2 opposite corners (better all 4) of the sample in photo pixels.")
        uv = photo.plate(pts, self._w(DEFAULT_HEIGHT if height is None else height))  # the sample's top face
        u0, v0 = uv.min(axis=0)
        u1, v1 = uv.max(axis=0)
        out = self.add_sample((u0 + u1) / 2, (v0 + v1) / 2, u1 - u0, v1 - v0, height, name)
        if len(uv) >= 3:
            out["edge_angles_deg"] = self._edge_angles(uv)
            out["note"] = ("The sample is stored as the axis-aligned box around the corners; edge_angles_deg gives how "
                           "its edges are turned on the plate (0 = along x).")
        return out

    @staticmethod
    def _edge_angles(uv) -> list[float]:
        hull = uv if len(uv) != 4 else uv[np.argsort(np.arctan2(uv[:, 1] - uv[:, 1].mean(), uv[:, 0] - uv[:, 0].mean()))]
        out = []
        for a, b in zip(hull, np.roll(hull, -1, axis=0)):
            ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
            out.append(rounded((ang + 90.0) % 180.0 - 90.0, 2))
        return out

    def update_sample(self, name: str, x=None, y=None, length=None, width=None, height=None, new_name=None) -> dict:
        s = self._sample(name)
        for attr, value in (("u", x), ("v", y), ("length", length), ("width", width), ("height", height)):
            if value is not None:
                setattr(s, attr, number(value, attr))
        if height is not None:
            s.sn_checked = None  # given by hand: no longer from the height check
        if new_name and new_name != s.name:
            s.name = self._unique(new_name)
        return {"sample": self._sample_info(s)}

    def remove_sample(self, name: str) -> dict:
        s = self._sample(name)
        self.layout.samples.remove(s)
        return {"removed": s.name, "samples": [x.name for x in self.layout.samples]}

    def clear_samples(self) -> dict:
        n = len(self.layout.samples)
        self.layout.samples = []
        return {"removed": n}

    def add_device(self, sample: str, name: str | None = None, x: float | None = None, y: float | None = None,
                   photo_px=None, photo_id: str | None = None, x_edge: str = "left", y_edge: str = "bottom",
                   size_mm: float = 0.2) -> dict:
        """A device on a substrate: at plate (x, y) mm, or at a pixel of a registered photo (plate or microscope).
        It is stored relative to the substrate edges (x_edge left/right, y_edge bottom/top), so it moves with it."""
        s = self._sample(sample)
        if photo_px is not None:
            x, y = self._photo(photo_id).plate([photo_px], self._w(s.height))[0]
        if x is None or y is None:
            raise APIError("Give the device position: x, y (plate mm) or photo_px.")
        if x_edge not in X_EDGES or y_edge not in Y_EDGES:
            raise APIError(f"x_edge: {X_EDGES}, y_edge: {Y_EDGES}.")
        names = {d.name for x_ in self.layout.samples for d in x_.devices}
        name = name or self.layout.unique_device_name()
        if name in names or "/" in name:
            raise APIError(f"Device name {name!r} is taken or contains '/'.")
        d = Device(name, x_edge=x_edge, y_edge=y_edge, length=number(size_mm, "size_mm"), width=number(size_mm, "size_mm"))
        d.set_position(s, number(x, "x"), number(y, "y"))
        s.devices.append(d)
        warn = self.layout.device_warnings(s, d)
        return {"added": f"{s.name}/{d.name}", "x": rounded(float(x), 3), "y": rounded(float(y), 3),
                "edges": {x_edge: rounded(d.dx, 3), y_edge: rounded(d.dy, 3)}, "warnings": warn}

    def remove_device(self, target: str) -> dict:
        sname, _, dname = str(target).partition("/")
        s = self._sample(sname)
        dev = next((d for d in s.devices if d.name == dname), None)
        if dev is None:
            raise APIError(f"No device {target!r} (use 'sample/device').")
        s.devices.remove(dev)
        return {"removed": target}

    def _sample_info(self, s: Sample) -> dict:
        info = {"name": s.name, "x": s.u, "y": s.v, "length": s.length, "width": s.width, "height": s.height,
                "warnings": self.layout.warnings(s)}
        if s.sn_checked is not None:
            info["height_checked_at_sn"] = s.sn_checked
        if s.devices:
            info["devices"] = [{"name": d.name, "x": d.position(s)[0], "y": d.position(s)[1],
                                "warnings": self.layout.device_warnings(s, d)} for d in s.devices]
        return rounded(info, 4)

    def samples(self) -> dict:
        self._need_start()
        return {"plate": self.layout.plate.name, "plate_offset_mm": rounded(self.layout.plate_offset_v, 4),
                "samples": [self._sample_info(s) for s in self.layout.samples]}

    def check_height(self, sample: str, sn: float) -> dict:
        """Set SN by eye: the top surface of `sample` was driven onto the camera reference line (the analyzer focal
        plane) at SRn ref, SRz 0, at SN = sn (read by eye, about ±0.05 mm). Its height H follows roughly;
        bring_to_beam then keeps this SN for its targets (right at SRn ref, SRz 0, as the height was set with it).
        A zone-plate / capillary focus ('Fine tunings by ZPS/CPS' in the program) gives H more precisely."""
        self._need_start()
        s = self._sample(sample)
        sn = number(sn, "sn")
        c = self.model.config
        h = height_from_sn(c, sn, self.layout.plate)
        if h < 0:
            raise APIError(f"SN = {sn:g} puts the reference line {-h:.3f} mm below the plate top (SN_f = {c.sn_f:g}): "
                           "check the SN value and the configuration.")
        old = s.height
        dh = check_height(c, self.layout, s, sn)
        return {"sample": self._sample_info(s), "height_before": rounded(old, 4), "dH": rounded(dh, 4),
                "note": f"H = SN - SN_f + 5.0 - plate top ({self.layout.plate.total_thickness:g}); SN read by eye "
                        "(about ±0.05 mm).",
                "positions": self.sample_positions()["positions"]}

    # ----------------------------------------------------------------------------------------- stage positions
    def _target(self, label: str):
        plate = self.layout.plate
        if label in (None, "", "plate centre", "plate center", "centre", "center"):
            return "plate centre", (0.0, 0.0, plate.total_thickness)
        for name, u, v, h in self.layout.targets():
            if name == label:
                return name, (u, v, plate.total_thickness + h)
        # a substrate name: its centre
        s = self.layout.sample_of(label)
        if s is not None and "/" not in label:
            return s.name, (s.u, s.v, plate.total_thickness + s.height)
        raise APIError(f"No target {label!r}; targets: {['plate centre'] + [t[0] for t in self.layout.targets()]}.")

    def current_optic(self) -> float:
        return self.optics.current_position if self.optic_position is None else self.optic_position

    def _base_motors(self) -> MotorPositions:
        if self.motors is not None:
            return self.motors
        c = self.model.config
        return MotorPositions(st=c.st0, sn=c.sn_f, sz=c.sz0, srn=c.srn_ref, srz=0.0, pix=c.pi_center, piy=c.pi_center)

    def set_position(self, motors: dict, optic_position: float | None = None) -> dict:
        """The stage as it is now (absolute motor values read at the beamline); missing motors keep their value."""
        self._need_start()
        self.motors = motors_from(motors, self._base_motors())
        if optic_position is not None:
            self.optic_position = number(optic_position, "optic position")
        out = self.beam_on()
        out["stage"] = motors_dict(self.motors)
        return out

    def sample_positions(self) -> dict:
        """ST / SZ / SN putting each sample / device centre on the beam at the analyzer focus at the start rotation
        (SRn ref, SRz 0, piezo centred)."""
        self._need_start()
        model = self.model
        c = model.config
        rows = []
        labels = ["plate centre"] + [t[0] for t in self.layout.targets()]
        for label in labels:
            _, (u, v, w) = self._target(label)
            st, sz, sn = model.reference_motors(u, v, w)
            m = MotorPositions(st=st, sn=sn, sz=sz, srn=c.srn_ref, srz=0.0, pix=c.pi_center, piy=c.pi_center)
            row = {"target": label, "x": rounded(u, 3), "y": rounded(v, 3), "ST": rounded(st), "SZ": rounded(sz),
                   "SN": rounded(sn), "out_of_range": out_of_range(m)}
            if label != "plate centre":
                checked = checked_sn(self.layout, label) is not None
                row["SN_source"] = "set by eye" if checked else "from H (right only if H is exact)"
                if checked:
                    row["height_checked"] = True
            rows.append(row)
        return {"rotation": {"SRn": c.srn_ref, "SRz": 0.0, "PIX": c.pi_center, "PIY": c.pi_center},
                "configuration": self.record.label, "plate_offset_mm": rounded(self.layout.plate_offset_v, 4),
                "positions": rows,
                "formula": f"ST = ST0 - x = {c.st0:g} - x, SZ = SZ0 - y = {c.sz0:g} - y, SN = SN_f + H (SN_f = {c.sn_f:g})",
                "next": "Go to a position; when the target is really found elsewhere on the beam in the analyzer focus, "
                        "give its ST, SZ, SN to found_here (SZ off: the plate sits at another height in the holder)."}

    def _collision_text(self, new: MotorPositions, optic_new: float | None) -> list[str]:
        model = self.model
        cal = self.optics
        geo = self.record.collision_geometry()
        fixed_y = cal.reference_y(model)
        out = []
        for what, positions in (("optic where it is now", [self.current_optic()]),
                                ("optic refocused", [] if optic_new is None else [optic_new])):
            if not positions:
                continue
            ys = [cal.focus_for_position(model, p) for p in positions]
            hits = collisions(model, new, self.layout, geo, ys, fixed_y)
            if hits:
                out.append(f"{', '.join(hits)} ({what})")
        return out

    def _move_report(self, label: str, uvw, new: MotorPositions) -> dict:
        model = self.model
        res = focus_correction(model, new, self.layout, self.optics, self.current_optic())
        y = model.beam_position(new, *uvw)
        out = {"target": label, "stage": motors_dict(new),
               "distance_from_analyzer_focus_um": rounded(abs(y) * 1000, 0),
               "side": "on the focus" if abs(y) < TOLERANCE else ("downstream" if y > 0 else "upstream"),
               "beam_lands_on": res.target,
               "optic_position_for_focus": rounded(res.required_optic_position),
               "out_of_range": out_of_range(new),
               "collisions": self._collision_text(new, res.required_optic_position)}
        if abs(y) >= TOLERANCE:
            out["delta_sn_to_focus"] = rounded(sn_to_focus(model, new, *uvw))
        out["focus_ok"] = abs(y) <= FOCUS_WARNING
        return out

    def centre_piezo(self, motors: dict | None = None, optic_position: float | None = None) -> dict:
        """The sample was seen in a PIX / PIY scan away from the piezo centre, at these (or the current) positions with
        the optic in focus at `optic_position` (default: the current one): the ST / SZ that show it with the piezo
        centred (PIX = PIY = 150 µm) at the same SRn / SRz, SN kept, and the refocused optic (as "Centre the piezo" in
        the program and the last step of Rotate sample). Only computes: give the result to set_position once the
        user has moved there."""
        self._need_start()
        m = motors_from(motors, self._base_motors())
        optic = self.current_optic() if optic_position is None else number(optic_position, "optic position")
        pi = self.model.config.pi_center
        if abs(m.pix - pi) < 1e-9 and abs(m.piy - pi) < 1e-9:
            raise APIError(f"PIX and PIY are already at the centre ({pi:g} µm): give the PIX, PIY where the sample is "
                           "seen in the scan.")
        p = recentre_piezo(self.model, m, optic, self.optics)
        return {"seen_at": motors_dict(m), "optic_position_seen": rounded(optic),
                "stage": motors_dict(p.new), "optic_position": rounded(p.optic_new),
                "delta_mm": rounded({"ST": p.new.st - m.st, "SZ": p.new.sz - m.sz, "SN": p.new.sn - m.sn,
                                     "optic": p.optic_new - optic}),
                "moves_along_beam_um": rounded(p.beam_shift * 1000, 1),
                "same_point_optic_unchanged": motors_dict(p.same_point),
                "out_of_range": out_of_range(p.new), "collisions": self._collision_text(p.new, p.optic_new),
                "next": "Tell the user these ST, SZ (PIX = PIY = 150, SN kept) and the optic position; once there, "
                        "set_position with them."}

    def bring_to_beam(self, target: str, motors: dict | None = None, correct_sn: bool = False) -> dict:
        """ST / SZ putting a target on the beam with SN kept (how the stage is run), at the given (or current)
        SRn, SRz, with the piezo centred (PIX = PIY = 150 µm: it may still hold a scan position); with correct_sn also SN, so that it is on the analyzer focus. A target whose sample height
        was checked (check_height) keeps the SN of that check unless `motors` gives SN."""
        self._need_start()
        label, uvw = self._target(target)
        m = motors_from(motors, self._base_motors())
        checked = checked_sn(self.layout, label)
        sn_given = isinstance(motors, dict) and any(k.lower() == "sn" and v is not None for k, v in motors.items())
        use_checked = checked is not None and not correct_sn and not sn_given
        pi = self.model.config.pi_center
        if correct_sn:
            new = self.model.motors_for_target(*uvw, srn=m.srn, srz=m.srz, pix=pi, piy=pi)
        else:
            sn = checked if use_checked else m.sn
            new = self.model.motors_on_beam(*uvw, srn=m.srn, srz=m.srz, sn=sn, pix=pi, piy=pi)
        out = self._move_report(label, uvw, new)
        if use_checked:
            out["sn_from_height_check"] = rounded(checked)
            if not out["focus_ok"]:
                out["advice"] = ("SN kept from the height check (right at SRn ref, SRz 0); the optic refocuses on the "
                                 "target. Do not correct SN unless the user asks.")
            elif out["out_of_range"] or out["collisions"]:
                out["advice"] = "Not reachable as it is: see out_of_range / collisions."
            return out
        if not correct_sn and not out["focus_ok"]:
            out["advice"] = (f"{out['distance_from_analyzer_focus_um']:.0f} µm from the analyzer focus: the spectra would "
                             "be distorted. Call again with correct_sn=true to move SN as well.")
        elif out["out_of_range"] or out["collisions"]:
            out["advice"] = "Not reachable as it is: see out_of_range / collisions."
        return out

    def beam_on(self, motors: dict | None = None, optic_position: float | None = None) -> dict:
        """What the beam hits at these (or the current) positions, and the optic position focusing there."""
        self._need_start()
        m = motors_from(motors, self._base_motors())
        optic = self.current_optic() if optic_position is None else number(optic_position, "optic position")
        res = focus_correction(self.model, m, self.layout, self.optics, optic)
        out = {"beam_lands_on": res.target, "stage": motors_dict(m),
               "plate_mm": None if res.plate_uv is None else rounded(list(res.plate_uv), 3),
               "surface_in_focal_plane_H_mm": rounded(self.model.focal_plane_height(m) - self.layout.plate.total_thickness),
               "optic_position": rounded(optic), "optic_position_for_focus": rounded(res.required_optic_position)}
        if res.delta is not None:
            out["surface_from_optic_focus_mm"] = rounded(res.delta)
        return out

    def found_here(self, target: str, motors: dict, apply: bool = True, at_focus: bool = True,
                   configuration: str | None = None, height_exact: bool = False, height: float | None = None) -> dict:
        """The target was found on the beam at these stage positions. ST is usually right; SZ is off (0-2 mm) because
        the plate does not always go into the holder at the same height, not because of the beam: the y shift moves
        the whole plate in the holder (plate offset: SZ of every sample changes, the configuration and the drawing
        stay), the x shift moves its sample (with its devices) and the height shift changes its H.

        at_focus: SN was set so that the target is in the analyzer focus (then its height H follows from SN too).
        false: SN was not corrected (only on the beam): x, y follow and H is kept.
        height_exact: the sample height is known precisely (e.g. a wafer of known thickness, mounted within 0.02 mm):
        H is kept, x, y follow from where the beam crosses the surface at that height (only the photo error and the
        plate offset are corrected), as "H is exact" in the program's Fine tunings by ZPS/CPS. Trust: a known exact H >
        the ZPS / CPS focus > the SN set by eye: an H from the SN set by eye is not taken as exact (error) unless the
        known one is given in `height`.
        height: the known height H of its sample (mm), set first (users often remember it only now); it replaces an
        SN set by eye, which is then reported as a check (SN_f / mounting).
        configuration: the motor values were read with another (older) configuration, e.g. a position noted months
        ago (another mounting of the plate); x, y follow from that configuration and move the sample, H is kept
        (heights do not carry over between configurations)."""
        self._need_start()
        label, uvw = self._target(target)
        if label == "plate centre":
            raise APIError("Choose a sample or device, not the plate centre.")
        sample = self.layout.sample_of(label)
        eye_sn = None
        if height is not None:
            h = number(height, "height")
            if h < 0:
                raise APIError("height: H is >= 0 mm (top surface above the plate surface).")
            eye_sn = sample.sn_checked
            if apply:
                sample.height, sample.sn_checked = h, None
            uvw = (uvw[0], uvw[1], self.layout.plate.total_thickness + h)  # the target on its sample's top surface
        if height_exact and sample.sn_checked is not None and height is None:
            raise APIError(f"H of {sample.name} ({sample.height:.3f} mm) comes from the SN set by eye (about ±0.05 mm), "
                           "not from a known thickness. Trust: a known exact H > the ZPS / CPS focus > the SN set by "
                           "eye. Ask the user for the known thickness and give it as height=..., or call without "
                           "height_exact so that the focus corrects H.")
        m = motors_from(motors, self._base_motors())
        model = self.model if configuration is None else StageModel(
            self._find_record(configuration).config_for(self.layout.plate.key), self.layout.plate)
        if at_focus and configuration is None and not height_exact:
            du, dv, dw = found_offset(model, m, *uvw)
        else:
            hit = model.beam_hit(m, uvw[2])
            if hit is None:
                raise APIError("The beam runs along the sample surface at these angles.")
            u, v, _ = model.lab_to_plate(m, hit)
            du, dv, dw = u - uvw[0], v - uvw[1], 0.0
        out = {"target": label, "stage": motors_dict(m), "shift_mm": rounded({"dx": du, "dy": dv, "dH": dw})}
        if eye_sn is not None:
            sn = sn_from_height(self.model.config, number(height, "height"), self.layout.plate)
            out["sn_by_eye_check"] = (f"SN set by eye {eye_sn:.3f} mm, SN for the known H on the analyzer focus "
                                      f"{sn:.3f} mm (difference {eye_sn - sn:+.3f} mm"
                                      + ("; more than 0.1 mm: check SN_f of the configuration or the mounting)."
                                         if abs(eye_sn - sn) > 0.1 else ")."))
        elif height_exact and height is None and abs(sample.height - DEFAULT_HEIGHT) < 5e-7:
            out["height_warning"] = (f"H of {sample.name} is the default {DEFAULT_HEIGHT} mm: make sure it is the known "
                                     "thickness (users often forget to enter it), else give height=... .")
        plate_move = configuration is None  # an older configuration: another mounting, the sample moves as before
        if plate_move:
            out["plate_offset_mm"] = rounded({"before": self.layout.plate_offset_v,
                                              "after": self.layout.plate_offset_v + dv}, 4)
            out["how"] = ("dy: the plate sits at another height in the holder (not the beam): all samples move with it "
                          f"(their SZ by {-dv:+.4f} mm); dx and dH: {sample.name} only.")
        if configuration is not None or not at_focus or height_exact:
            out["height_kept"] = (f"H kept at {sample.height:.3f} mm"
                                  + (" (marked exact)" if height_exact else "")
                                  + "; x, y from where the beam crosses the surface"
                                  + (f" with configuration {configuration!r}." if configuration else "."))
        if abs(du) > LARGE_FOUND_OFFSET:
            out["warning"] = (f"x (ST) off by more than {LARGE_FOUND_OFFSET:g} mm: more likely the beam spot has moved "
                              "(optic realigned?) than the sample. If other samples show the same ST shift, suggest an "
                              "optics recalibration (RealSampleCalibration, mode optics) rather than moving samples.")
        elif max([abs(dw)] + ([] if plate_move else [abs(dv)])) > LARGE_FOUND_OFFSET:
            out["warning"] = (f"More than {LARGE_FOUND_OFFSET:g} mm in H (or y with an older configuration): check the "
                              "height (check_height) or run a calibration.")
        if plate_move and abs(self.layout.plate_offset_v + dv) > PLATE_OFFSET_WARNING:
            out["warning_plate"] = (f"The plate would sit {self.layout.plate_offset_v + dv:+.2f} mm off its usual "
                                    f"height (more than {PLATE_OFFSET_WARNING:g} mm): check that the right target "
                                    "was found.")
        if apply:
            if plate_move:
                apply_found_offset(self.model.config, self.layout, sample, du, dv, dw)
                self.motors = m
            else:  # positions read with another configuration are not the stage now
                sample.u += du
                sample.v += dv
                sample.height = max(sample.height + dw, 0.0)
            out["applied"] = (f"plate offset {self.layout.plate_offset_v:+.4f} mm, {sample.name} corrected; "
                              "positions recomputed." if plate_move else f"{sample.name} moved; positions recomputed.")
            out["sample"] = self._sample_info(sample)
            out["positions"] = self.sample_positions()["positions"]
        return out

    # -------------------------------------------------------------------------------------------- rotations
    def rotate(self, srn: float, srz: float | None = None, motors: dict | None = None,
               measured_optic: float | None = None, target: str | None = None) -> dict:
        """New ST / SZ (/ SN) and optic position keeping the point now on the beam there after turning to (srn, srz).

        `motors`: the stage with the point of interest on the beam and in focus (default: the current position;
        with `target` and no position: the target at the analyzer focus at the current rotation).
        Two answers: SN kept (how the stage is run; the point slides along the beam) and SN corrected (on the
        analyzer focus, within the motor ranges)."""
        self._need_start()
        base = self._base_motors()
        if motors is None and target is not None:
            _, uvw = self._target(target)
            measured = self.model.motors_for_target(*uvw, srn=base.srn, srz=base.srz, pix=base.pix, piy=base.piy)
        else:
            measured = motors_from(motors, base)
        srn = number(srn, "SRn")
        srz = measured.srz if srz is None else number(srz, "SRz")
        optic = self.current_optic() if measured_optic is None else number(measured_optic, "optic position")
        default_h = DEFAULT_HEIGHT
        try:
            kept = relocate(self.model, self.layout, measured, srn, srz, self.optics, optic,
                            recentre_piezo=True, keep_sn=True, default_height=default_h)
            focus = relocate(self.model, self.layout, measured, srn, srz, self.optics, optic,
                             recentre_piezo=True, to_analyzer_focus=True, limits=TRAVEL, default_height=default_h)
        except ValueError as exc:
            raise APIError(str(exc)) from None

        def report(r, sn_kept):
            d = {"stage": motors_dict(r.new),
                 "change": rounded({k.upper(): getattr(r.new, k) - getattr(r.measured, k) for k in ("st", "sz", "sn")}),
                 "optic_position": rounded(r.optic_new),
                 "distance_from_analyzer_focus_um": rounded(r.focus_distance * 1000, 0),
                 "out_of_range": out_of_range(r.new), "collisions": self._collision_text(r.new, r.optic_new)}
            if sn_kept and abs(r.beam_offset) > 1e-6:
                d["delta_sn_to_focus"] = rounded(-r.beam_offset / math.sqrt(2))
            return d

        u, v, w = kept.uvw
        out = {"point": {"on": kept.target, "x": rounded(u, 3), "y": rounded(v, 3)},
               "from": motors_dict(measured), "to_angles": {"SRn": srn, "SRz": srz},
               "sn_kept": report(kept, True), "sn_corrected": report(focus, False),
               "optic_reference": kept.optic_source}
        ok = kept.focus_distance <= FOCUS_WARNING and not out["sn_kept"]["out_of_range"]
        out["recommended"] = "sn_kept" if ok else "sn_corrected"
        out["why"] = ("SN kept: the point stays within {:.0f} µm of the analyzer focus.".format(FOCUS_WARNING * 1000)
                      if ok else "With SN kept the point would be too far from the analyzer focus (or out of range): "
                                 "use the SN-corrected position.")
        return out

    def align_edge(self, p1, p2, along: str = "slit", photo_id: str | None = None, plate_mm: bool = False,
                   current_srn: float | None = None) -> dict:
        """SRn turning a straight edge (two points on it: photo pixels of a registered photo, or plate mm with
        plate_mm=true) along the analyzer slit (horizontal at ANTARES) or across it ('vertical')."""
        self._need_start()
        if plate_mm:
            a, b = np.asarray(p1, float), np.asarray(p2, float)
        else:
            a, b = self._photo(photo_id).plate([p1, p2])
        phi = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))  # in the front view, CCW from +x
        ref = self.record.config.srn_ref
        target = 0.0 if str(along).lower() in ("slit", "horizontal", "st", "h") else 90.0
        now = self._base_motors().srn if current_srn is None else number(current_srn, "SRn")
        options = []
        for k in range(-4, 5):
            srn = ref + target - phi + 180.0 * k
            if SRN_USABLE[0] <= srn <= SRN_USABLE[1]:
                options.append({"SRn": rounded(srn, 2), "turn_from_now_deg": rounded(srn - now, 2)})
        options.sort(key=lambda o: abs(o["turn_from_now_deg"]))
        note = ("SRn turns the plate about its normal (CCW seen from the analyzer). Then call rotate(srn=...) for the "
                "new ST / SZ / SN and optic position.")
        if not options:
            ideal = ref + target - phi
            near = min((ideal + 180.0 * k for k in range(-4, 5)), key=lambda s: min(abs(s - SRN_USABLE[0]),
                                                                                    abs(s - SRN_USABLE[1])))
            edge = SRN_USABLE[0] if abs(near - SRN_USABLE[0]) < abs(near - SRN_USABLE[1]) else SRN_USABLE[1]
            note = (f"Not reachable within SRn {SRN_USABLE[0]:g} … {SRN_USABLE[1]:g}° (needs {near:.1f}°): remount the "
                    f"sample turned by about {near - edge:+.0f}° on the plate (CCW seen from the sample side), or use "
                    "the other direction.")
        return {"edge_angle_on_plate_deg": rounded(wrap180(phi), 2),
                "edge_angle_seen_now_deg": rounded(wrap180(phi + now - ref), 2),
                "wanted": "along the slit (horizontal, along ST)" if target == 0 else "across the slit (vertical)",
                "srn_options": options, "note": note}

    def bz_angles(self, lattice_a: float, hv_map: float, gamma: list, ref_point: list, ref_label: str = "K",
                  feature: str = "K", line: int = 0, hv: float | None = None, map_srn: float | None = None,
                  map_srz: float | None = None, binding: float = 0.0) -> dict:
        """SRn / SRz putting a 2-D hexagonal Brillouin-zone point (Γ, K, K', M) at the slit centre with the slit
        along a high-symmetry line, from a measured map (ARPES viewer angles θ = deflector, φ = along the slit)."""
        self._need_start()
        from ..alignment import bz_target as bt
        from ..alignment.rotation import AnalyzerGeometry

        feat = {"g": "Γ", "γ": "Γ", "gamma": "Γ", "k": "K (K or K′)", "k only": "K only", "k'": "K′ only",
                "k′": "K′ only", "k' only": "K′ only", "m": "M"}.get(str(feature).strip().lower(), feature)
        if feat not in bt.FEATURES:
            raise APIError(f"feature: one of {bt.FEATURES}.")
        base = self._base_motors()
        measured = MotorPositions(srn=base.srn if map_srn is None else number(map_srn, "map SRn"),
                                  srz=base.srz if map_srz is None else number(map_srz, "map SRz"))
        t = bt.HexTarget(a=number(lattice_a, "lattice constant"), hv_map=number(hv_map, "hv of the map"),
                         gamma=(number(gamma[0], "Γ θ"), number(gamma[1], "Γ φ")), ref_label=str(ref_label).upper()[:1],
                         ref=(number(ref_point[0], "θ"), number(ref_point[1], "φ")), measured=measured, feature=feat,
                         line=int(line), binding=number(binding, "binding"))
        if t.ref_label not in ("K", "M"):
            raise APIError("ref_label: 'K' or 'M' (the point whose angles you read besides Γ).")
        try:
            adv = bt.advise(self.model, AnalyzerGeometry(), t, number(hv or hv_map, "hv"), optic_short(self.optic))
        except ValueError as exc:
            raise APIError(str(exc)) from None
        lines = [label for label, _ in bt.LINES[bt.feature_kind(feat)]]
        return {"reachable": adv.ok, "lines": lines, "line_used": lines[t.line] if t.line < len(lines) else None,
                "best": None if adv.best is None else self._candidate(adv.best),
                "candidates": [self._candidate(c) for c in adv.candidates[:6]], "messages": adv.messages,
                "check": {"gamma_to_ref_measured": rounded(adv.frame.ref_k), "from_lattice": rounded(adv.frame.ref_k_expected),
                          "gamma_from_normal_deg": rounded(adv.frame.tilt, 2)},
                "next": "rotate(srn=..., srz=...) gives the stage positions for the chosen angles."}

    def bz_point_to(self, lattice_a: float, hv_map: float, ref_point: list, map_srn: float, map_srz: float,
                    ref_label: str = "K", hv: float | None = None, target_angles: list | None = None,
                    gamma: list | None = None, keep_srn: bool = False, binding: float = 0.0,
                    sample: str | None = None) -> dict:
        """SRn / SRz putting a K or M point read on a map (θ = deflector, φ = slit, ARPES viewer) at chosen analyzer
        angles at another photon energy. Γ is optional: without it the surface tilt is estimated from |Γ–point|.
        keep_srn: keep the in-plane orientation (slit already along Γ–K / Γ–M) and turn SRz only. With `sample`, also
        the ST / SZ / SN putting it at the analyzer focus there."""
        self._need_start()
        from ..alignment import bz_target as bt
        from ..alignment.rotation import AnalyzerGeometry

        label = str(ref_label).strip().upper()[:1]
        if label not in ("K", "M"):
            raise APIError("ref_label: 'K' or 'M'.")
        a = number(lattice_a, "lattice constant")
        ref_k = bt.gamma_k(a) if label == "K" else bt.gamma_m(a)
        measured = MotorPositions(srn=number(map_srn, "map SRn"), srz=number(map_srz, "map SRz"))
        ref = (number(ref_point[0], "θ"), number(ref_point[1], "φ"))
        tgt = (0.0, 0.0) if target_angles is None else (number(target_angles[0], "target θ"),
                                                         number(target_angles[1], "target φ"))
        g = None if gamma is None else (number(gamma[0], "Γ θ"), number(gamma[1], "Γ φ"))
        hv_map_v = number(hv_map, "hv of the map")
        hv_v = hv_map_v if hv is None else number(hv, "hv")
        geo = AnalyzerGeometry()
        try:
            frame = bt.point_frame(self.model, geo, measured, ref, ref_k, hv_map_v, g, number(binding, "binding"))
            moves = bt.move_point(self.model, geo, measured, frame, ref_k, hv_v, tgt, bool(keep_srn),
                                  number(binding, "binding"))
        except ValueError as exc:
            raise APIError(str(exc)) from None
        gamma_map = bt.analyzer_angles(geo, bt.plate_to_lab_dir(self.model, measured.srn, measured.srz) @ frame.n)
        out = {"point": label, "hv": hv_v, "target_angles": {"theta": tgt[0], "phi": tgt[1]},
               "frame": {"gamma_given": frame.gamma_given,
                         "gamma_on_map": {"theta": rounded(gamma_map[0], 2), "phi": rounded(gamma_map[1], 2)},
                         "surface_tilt_from_plate_deg": rounded(frame.tilt, 2),
                         "point_from_gamma_on_map_deg": rounded(frame.measured_angle, 2),
                         "expected_from_lattice_deg": rounded(frame.expected_angle, 2)},
               "solutions": [{"SRn": rounded(m.srn, 2), "SRz": rounded(m.srz, 2), "theta": rounded(m.theta, 2),
                              "phi": rounded(m.phi, 2),
                              "gamma_at": {"theta": rounded(m.gamma[0], 2), "phi": rounded(m.gamma[1], 2)}}
                             for m in moves[:4]]}
        notes = []
        if not frame.gamma_given:
            notes.append(f"Γ was not given: the surface is taken as tilted {frame.tilt:.1f}° from the plate towards the "
                         f"{label} point (the smallest tilt that puts it at its lattice angle). A tilt across that "
                         "direction is not seen with one point; give Γ when it is on a map.")
        elif abs(frame.measured_angle - frame.expected_angle) > 1.0:
            notes.append(f"The {label} point is {frame.measured_angle:.1f}° from Γ on the map but {frame.expected_angle:.1f}° "
                         "is expected from the lattice and hv: check the angles, hv_map or lattice_a.")
        if keep_srn and moves:
            notes.append(f"SRn kept: SRz sets φ; θ stays at {moves[0].theta:.2f}° (use the deflector for it).")
        if not moves:
            notes.append("No solution: the point cannot reach these angles" + (" with SRn kept." if keep_srn else "."))
        else:
            best = moves[0]
            if not (bt.SRZ_RANGE[0] <= best.srz <= bt.SRZ_RANGE[1]):
                notes.append(f"SRz {best.srz:.1f}° is outside the usual range {bt.SRZ_RANGE[0]:g} … {bt.SRZ_RANGE[1]:g}°: "
                             "check collisions (the positions below do).")
            if sample:
                out["positions_at_focus"] = self.bring_to_beam(sample, {"srn": best.srn, "srz": best.srz}, correct_sn=True)
        out["notes"] = notes
        out["next"] = "rotate(srn, srz, motors=...) from a measured position gives ST / SZ / SN for SN kept and corrected."
        return out

    @staticmethod
    def _candidate(c) -> dict:
        return {"point": c.label, "SRn": rounded(c.srn, 2), "SRz": rounded(c.srz, 2), "theta": rounded(c.theta, 2),
                "phi": rounded(c.phi, 2), "slit_off_line_deg": rounded(c.direction_error, 1),
                "beam_from_normal_deg": rounded(c.incidence, 0), "ok": c.ok, "problems": c.problems}

    def collision_check(self, motors: dict | None = None, optic_position: float | None = None) -> dict:
        """Does the plate touch the analyzer / optic at these positions, and how far can each motor go."""
        self._need_start()
        m = motors_from(motors, self._base_motors())
        model, geo, cal = self.model, self.record.collision_geometry(), self.optics
        optic = self.current_optic() if optic_position is None else number(optic_position, "optic position")
        y = cal.focus_for_position(model, optic)
        fixed = cal.reference_y(model)
        hits = collisions(model, m, self.layout, geo, [y], fixed)
        out = {"stage": motors_dict(m), "optic_position": rounded(optic), "collision": hits,
               "out_of_range": out_of_range(m)}
        if not hits:
            lim = motor_limits(model, m, self.layout, geo, [y], TRAVEL, fixed)
            out["free_range"] = {k.upper(): {"min": rounded(v.lo), "max": rounded(v.hi), "min_set_by": v.lo_by,
                                             "max_set_by": v.hi_by} for k, v in lim.items()}
        shadow = in_acceptance(geo, [y], fixed)
        if shadow:
            out["shadow"] = f"{', '.join(shadow)} inside the analyzer acceptance cone (±{ACCEPTANCE_HALF_ANGLE:g}°)"
        return out

    # ------------------------------------------------------------------------------------- photon energy
    def set_photon_energy(self, hv: float | None = None) -> dict:
        """The photon energy in use (eV; None: back to the configuration's, 95 eV). Every optic position computed
        afterwards (bring_to_beam, rotate, centre_piezo, beam_on, collisions) is for this photon energy, and every
        optic position given is read as one at this photon energy: the zone plate's focal length grows with hv
        (optics_vs_hv.json: model and measured points)."""
        self.photon_energy = None if hv is None else number(hv, "photon energy")
        if self.photon_energy is not None and not 10.0 <= self.photon_energy <= 2000.0:
            raise APIError("photon energy: eV between 10 and 2000.")
        out = self._energy_info()
        if "NOT KNOWN" in out["optic_shift_source"]:
            out["warning"] = ("The optic shift at this photon energy is not known: measure the focus here and add the "
                              "point (add_optic_energy_point), or set the zone plate focal length in optics_vs_hv.json.")
        return out

    def optics_vs_hv(self) -> dict:
        """The optic against photon energy: the model of each optic and the measured points (optics_vs_hv.json),
        and the shift at the photon energy in use."""
        return {"table": self.energy_table.describe(), "now": self._energy_info()}

    def add_optic_energy_point(self, target: str, hv: float, motors: dict, optic_position: float,
                               comment: str = "", save: bool = False) -> dict:
        """A focus measured at another photon energy: `target` on the beam and in focus at `motors` with the optic at
        `optic_position` (read at photon energy hv). The shift is that position minus the position the configuration
        predicts for the same surface at its reference energy. Measure it on a target whose height was corrected at
        the reference energy (Fine tunings by ZPS/CPS), else the height error enters the shift. `save`: write it to
        optics_vs_hv.json (only on the user's explicit request: it changes the predictions for everyone)."""
        self._need_start()
        hv = number(hv, "photon energy")
        optic = number(optic_position, "optic position")
        label, uvw = self._target(target)
        m = motors_from(motors, self._base_motors())
        ref = optics_at_energy(self.record.optics, self.energy_table, self.energy_table.reference_hv)[0]
        hit = self.model.beam_hit(m, uvw[2])
        if hit is None:
            raise APIError("The beam runs along the sample surface at these angles.")
        predicted = ref.position_for_focus(self.model, float(hit[1]))
        shift = optic - predicted
        out = {"target": label, "hv": hv, "optic_position": rounded(optic),
               "predicted_at_reference_energy": rounded(predicted), "shift_mm": rounded(shift),
               "model_shift_mm": rounded(self.energy_table.shift(ref.optic_type, hv, ref.optic_sign).shift)}
        if save:
            self.energy_table.add_point(ref.optic_type, hv, shift, comment)
            out["saved"] = str(self.energy_table.save(self.store.folder))
        else:
            out["note"] = "Not saved: call again with save=true when the user asks to add it to optics_vs_hv.json."
        return out

    # ---------------------------------------------------------------------------------------------- files
    def save_session(self, path: str) -> dict:
        self._need_start()
        session = Session(self.layout, self._base_motors())
        path = Path(path).expanduser()
        if path.suffix.lower() != ".json":
            path = path.with_suffix(".json")
        session.save(path)
        return {"saved": str(path), "note": "Open it in QuickAlignment (Open…) or load_session."}

    def load_session(self, path: str, optic: str | None = None) -> dict:
        try:
            session = Session.load(Path(path).expanduser())
        except (OSError, ValueError) as exc:
            raise APIError(f"Could not read {path}: {exc}") from None
        if optic is not None or not self.started:
            self.optic = optic_type(optic or self.optic)
            self.record = self.store.latest(self.optic)
            set_motor_limits(self.store.motor_limits())
        self.layout = session.layout
        self.motors = session.motors
        self.photos = {}
        self.started = True
        return self.status()


__all__ = ["AlignmentSession", "DEFAULT_HEIGHT"]
