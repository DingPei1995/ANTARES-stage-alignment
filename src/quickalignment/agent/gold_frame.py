"""GoldFrameCalibration for an agent: plan the SZ lines over the gold frame, load the measured files, fit, save.

The same steps as the GoldFrameCalibration window (`quickalignment.goldframe`):

1. `start`: optic, gold height, where the frame is taken to be on the plate (default: the riser centre).
2. `plan`: the 33 SZ lines (groups A, B, C) placed with the newest configuration, each checked against the
   motor ranges and the anti-collision model; CSV for the beamline; the optional SN points.
3. `add_files`: the measured ANTARES .nxs files (or .npz from the simulator); `set_sn_points` (optional).
4. `fit`: every edge of every line at once; constants with uncertainties, change from the newest
   configuration, and a quality check; `plot` shows the data with the fitted edges.
5. `save`: a new configuration in configs/ (only after the user agreed).

`simulate_example` writes a simulated measurement with known faults, to try the steps without beam time.
"""

from __future__ import annotations

import io
import tempfile
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np

from ..core.calibration import CalibrationStore
from ..goldframe.cli import (
    CONFIG_ARGS, calibration_record, load_map, plan_issues, read_sn_points, save_scan, write_plan_csv,
)
from ..goldframe.model import (
    GROUP_TEXT, PARAM_TEXT, GoldFrame, Instrument, Setup, SNPoint, fit_global, simulated_measurement, sn_point_plan,
    survey_plan,
)
from .common import APIError, number, optic_short, optic_type, rounded

STEPS = [
    ("1 overview + SN scan", "SRn 120, SRz 0, PIX = PIY = 150. Find the gold frame with an ST x SZ overview map "
     "(±2 mm, ST steps 0.1 mm, SZ fast). Then an SN scan with ST following (ΔST = −ΔSN) on a gold bar: the peak is "
     "SN_gold; the same scan on the riser gives the gold height h (difference of the peaks). Focus the optic on the gold "
     "and note its position."),
    ("2 plan", "plan(): check that every line is 'ok', save the CSV for the beamline."),
    ("3 SZ lines", "Measure the lines of groups A, B, C. Per setting: set SRn, SRz and SN, then for each line set ST "
     "and fly-scan SZ (step 0.02 mm), e.g. one 2-D scan per setting with ST stepped."),
    ("4 SN points (optional)", "At each SN point of the plan run an SN scan (ST following) on the right bar and note "
     "the ST and SN at the peak: set_sn_points."),
    ("5 fit", "add_files(all files, overview included), fit(sn_gold). Check: edge rms a few µm, few lines left out, "
     "tilt ≲ 2°, scales within 0.5 % of 1, plot() edges on the data, the change from the newest configuration."),
    ("6 save", "save(comment) after the user agreed; then try it on a sample of known position (QuickAlignment, "
     "found_here)."),
]


class GoldFrameSession:
    def __init__(self, configs: str | Path | None = None):
        self.store = CalibrationStore(configs)
        self.optic = optic_type("capillary")
        self.frame = GoldFrame()
        self.files: list[tuple[str, object]] = []
        self.sn_points: list[SNPoint] = []
        self.sn_gold: float | None = None
        self.result = None
        self.fit_options = {}
        self.saved = None
        self.started = False

    def newest(self):
        return self.store.latest(self.optic)

    def guide_setup(self) -> Setup:
        return Setup(self.newest().config, self.frame)

    # ---------------------------------------------------------------------------------------------- setup
    def start(self, optic: str | None = "capillary", gold_height: float = 0.05, frame_x: float = 0.0,
              frame_y: float = 0.0, outer: float = 2.0, inner: float = 1.0) -> dict:
        """Begin: optic, gold height above the riser top (mm, measured with SN scans), where the frame centre is
        taken to be on the plate (mm), its outer size and hole (mm)."""
        self.optic = optic_type(optic)
        self.frame = GoldFrame(outer=number(outer, "outer"), inner=number(inner, "inner"),
                               height=number(gold_height, "gold height"), u=number(frame_x, "x"), v=number(frame_y, "y"))
        self.files, self.sn_points, self.sn_gold, self.result, self.saved = [], [], None, None, None
        self.started = True
        newest = self.newest()
        return {"optic": self.optic, "frame": rounded(asdict(self.frame)), "newest_configuration": newest.label,
                "protocol": [{"step": s, "do": d} for s, d in STEPS], **self.guide()}

    def _need_start(self) -> None:
        if not self.started:
            raise APIError("Call start(optic, gold_height, frame_x, frame_y) first.")

    def guide(self) -> dict:
        if not self.started:
            return {"step": "start", "do": "Ask which optic is mounted, the gold height (if measured) and whether the "
                    "frame sits at the riser centre; then start()."}
        if self.saved:
            return {"step": "done", "do": f"Saved {self.saved}; check it on a sample of known position."}
        if not self.files:
            return {"step": "measure", "do": "Steps 1-3 at the beamline (see protocol; plan() gives the lines). "
                    "Then add_files with the paths of the .nxs files."}
        if self.result is None:
            return {"step": "fit", "do": f"{len(self.files)} file(s) loaded. Set SN gold if the default is wrong, then "
                    "fit()."}
        return {"step": "check and save", "do": "Show the fit (constants, quality, plot) to the user; save(comment) "
                "only when they agree."}

    # ------------------------------------------------------------------------------------------------- plan
    def plan(self, csv_path: str | None = None) -> dict:
        """The SZ lines to measure, placed with the newest configuration, each checked (motor range, collision)."""
        self._need_start()
        guide = self.guide_setup()
        lines = survey_plan(guide)
        points = sn_point_plan(guide)
        issues = plan_issues(lines, guide, self.newest())
        rows = [{"group": p.group, "SRn": p.srn, "SRz": p.srz, "ST": p.st, "SN": p.sn, "SZ_from": p.sz_from,
                 "SZ_to": p.sz_to, "check": "; ".join(i) or "ok"} for p, i in zip(lines, issues)]
        out = {"placed_with": self.newest().label, "groups": GROUP_TEXT, "lines": rounded(rows),
               "settings": len({(p.srn, p.srz) for p in lines}),
               "problems": sum(bool(i) for i in issues),
               "sn_points_optional": [rounded({"SRn": p.srn, "SRz": p.srz, "ST": p.st, "SZ": p.sz, "expected_SN": p.sn})
                                      for p in points],
               "scan": "every line: SZ fly scan, step 0.02 mm; SN set once per SRn / SRz setting; ST between lines"}
        if csv_path:
            path = Path(csv_path).expanduser()
            write_plan_csv(path, lines, points)
            out["csv"] = str(path)
        return out

    # ------------------------------------------------------------------------------------------------- data
    def add_files(self, paths, normalize: bool = False) -> dict:
        """Measured files (.nxs; .npz from the simulator): survey lines, overview map, SRn sweep, single lines."""
        self._need_start()
        added, errors = [], []
        for path in paths if isinstance(paths, (list, tuple)) else [paths]:
            path = str(Path(path).expanduser())
            if any(p == path for p, _ in self.files):
                continue
            try:
                self.files.append((path, load_map([path], normalize=bool(normalize))))
                added.append(Path(path).name)
            except (OSError, KeyError, ValueError, ImportError) as exc:
                errors.append(f"{Path(path).name}: {exc}")
        self.result = None
        return {"added": added, "errors": errors, "files": self.file_list()["files"], **self.guide()}

    def file_list(self) -> dict:
        rows = []
        ref = self.newest().config.srn_ref
        for path, scan in self.files:
            def rng(m):
                v = scan.motor_grid(m)
                lo, hi = float(np.nanmin(v)), float(np.nanmax(v))
                return rounded(lo, 3) if hi - lo < 1e-3 else rounded([lo, hi], 3)
            flat = np.allclose(scan.base["srn"], ref) and np.allclose(scan.base["srz"], 0)
            rows.append({"file": Path(path).name, "lines": len(scan.x), "SRn": rng("srn"), "SRz": rng("srz"),
                         "ST": rng("st"), "SN": rng("sn"), "kind": scan.kind, "flat": bool(flat)})
        return {"files": rows, "sn_gold_default": rounded(self._flat_sn())}

    def remove_file(self, name: str) -> dict:
        before = len(self.files)
        self.files = [(p, s) for p, s in self.files if Path(p).name != name and p != name]
        if len(self.files) == before:
            raise APIError(f"No file {name!r} loaded.")
        self.result = None
        return self.file_list()

    def _flat_sn(self):
        ref = self.newest().config.srn_ref
        for _, scan in self.files:
            if np.allclose(scan.base["srn"], ref) and np.allclose(scan.base["srz"], 0):
                return float(scan.base["sn"][0])
        return None

    def set_sn_points(self, points=None, csv_path: str | None = None) -> dict:
        """Optional SN points: [{srn, srz, st, sz, sn}] (sn: SN at the intensity peak), or a CSV with those columns."""
        self._need_start()
        out = []
        if csv_path:
            out += read_sn_points(Path(csv_path).expanduser())
        for p in points or []:
            out.append(SNPoint(*(number(p[k], k) for k in ("srn", "srz", "st", "sz", "sn"))))
        self.sn_points = out
        self.result = None
        return {"sn_points": len(out)}

    # -------------------------------------------------------------------------------------------------- fit
    def fit(self, sn_gold: float | None = None, fit_tilt: bool = True, fit_scales: bool = True) -> dict:
        """Fit every edge of every line; the constants, their change and a quality check."""
        self._need_start()
        if not self.files:
            raise APIError("No file loaded: add_files first.")
        sn = self._flat_sn() if sn_gold is None else number(sn_gold, "SN gold")
        if sn is None:
            raise APIError("No file at SRn 120 / SRz 0 to take SN gold from: give sn_gold (SN with the gold top at the "
                           "analyzer focus, from the SN scan).")
        self.sn_gold = sn
        newest = self.newest()
        try:
            res = fit_global([s for _, s in self.files], sn, self.frame, newest.config, free_tilt=bool(fit_tilt),
                             free_scales=bool(fit_scales), sn_points=self.sn_points)
        except (ValueError, np.linalg.LinAlgError) as exc:
            raise APIError(f"The fit failed: {exc}") from None
        self.result = res
        c, old = res.setup.config, newest.config
        constants = [rounded({"name": k, "value": getattr(c, k), "sigma": res.sigma.get(k),
                              "newest": getattr(old, k), "change": getattr(c, k) - getattr(old, k),
                              "kept": k in res.kept}) for k in CONFIG_ARGS]
        extra = {PARAM_TEXT[k]: rounded({"value": res.values[k], "sigma": res.sigma.get(k)}) for k in
                 ("frame.rotation", "frame.tilt_u", "instrument.st_scale", "instrument.sz_scale") if k in res.values}
        checks = []
        checks.append(("edge rms a few µm", res.rms * 1000 <= 10, f"{res.rms * 1000:.1f} µm"))
        checks.append(("few lines left out", res.lines_used >= 0.85 * res.lines_total,
                       f"{res.lines_used}/{res.lines_total} lines used"))
        if "frame.tilt_u" in res.values:
            checks.append(("tilt ≲ 2°", abs(res.values["frame.tilt_u"]) <= 2.0, f"{res.values['frame.tilt_u']:.2f}°"))
        for k in ("instrument.st_scale", "instrument.sz_scale"):
            if k in res.values:
                checks.append((f"{PARAM_TEXT[k]} within 0.5 % of 1", abs(res.values[k] - 1) <= 0.005,
                               f"{res.values[k]:.4f}"))
        out = {"lines_used": res.lines_used, "lines_total": res.lines_total, "edges": res.edges,
               "edge_rms_um": rounded(res.rms * 1000, 1), "sn_gold": rounded(sn), "constants": constants,
               "frame_and_scales": extra,
               "per_file": [{"file": Path(p).name, "lines_used": f"{u}/{t}", "rms_um": rounded(r * 1000, 1)}
                            for (p, _), (u, t, r) in zip(self.files, res.per_scan)],
               "kept": {PARAM_TEXT.get(k, k): why for k, why in res.kept.items()},
               "notes": list(res.notes),
               "quality": [{"check": a, "ok": bool(b), "value": v} for a, b, v in checks],
               "sn_point_residuals_um": [rounded(r * 1000, 1) for r in res.sn_residuals if r is not None],
               "limit": "The frame is the plate reference: an error in where it is glued goes into ST0 / SZ0 and the axes."}
        out.update(self.guide())
        return out

    def plot(self) -> dict:
        """The loaded data with the fitted edges (after fit) as a PNG."""
        self._need_start()
        if not self.files:
            raise APIError("No file loaded.")
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from matplotlib.figure import Figure

        from ..goldframe.plot import draw_survey
        fig = Figure(figsize=(16, 5.2), dpi=90, layout="constrained")
        FigureCanvasAgg(fig)
        overlay = {"fit": self.result.setup} if self.result is not None else None
        draw_survey(fig, [s for _, s in self.files], overlay, self.newest().config.srn_ref)
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        return {"image_png": buf.getvalue(), "legend": "measured intensity per SZ line; orange: fitted gold edges"}

    def save(self, comment: str = "", optic_position: float | None = None) -> dict:
        """Save the fit as a new configuration in configs/ (only after the user agreed)."""
        self._need_start()
        if self.result is None:
            raise APIError("Nothing to save: fit() first.")
        newest = self.newest()
        opt = None if optic_position is None else number(optic_position, "optic position")
        record = calibration_record(self.result, [s for _, s in self.files], self.sn_gold, newest,
                                    optic_short(self.optic).replace(" ", "_"), opt, comment,
                                    {"files": [p for p, _ in self.files]}, self.sn_points)
        try:
            saved = self.store.save(record)
        except OSError as exc:
            raise APIError(f"Could not write to {self.store.folder}: {exc}") from None
        self.saved = saved.path.name
        return {"saved": str(saved.path), "comment": saved.comment, **self.guide()}

    # ------------------------------------------------------------------------------------------------- try
    def simulate_example(self, folder: str | None = None) -> dict:
        """A simulated measurement of the planned lines over a frame with known faults, written as files (to try
        the steps). Returns the files and the true values."""
        self._need_start()
        config = self.newest().config
        guide = Setup(config, replace(self.frame, u=0.0, v=0.0))
        m = guide.frame_motors()
        truth = Setup(replace(config, srn_axis_u=config.srn_axis_u + 0.1, srz_offset_n=config.srz_offset_n + 0.2),
                      replace(self.frame, u=0.15, v=-0.1, rotation=1.5, tilt_u=1.0),
                      Instrument(counts=3000, scale_st_ref=m.st, scale_sz_ref=m.sz))
        out_dir = Path(folder).expanduser() if folder else Path(tempfile.mkdtemp(prefix="gold_frame_example_"))
        out_dir.mkdir(parents=True, exist_ok=True)
        scans = simulated_measurement(guide, truth, overview=True, rng=np.random.default_rng(0))
        paths = [str(save_scan(scan, out_dir / key, optic=60.0)) for key, scan in scans.items()]
        c = truth.config
        return {"folder": str(out_dir), "files": paths, "sn_gold": rounded(truth.frame_motors().sn),
                "truth_with_frame_at_centre": rounded({"st0": c.st0 - 0.15, "sz0": c.sz0 + 0.1,
                                                       "srn_axis_u": c.srn_axis_u - 0.15, "srn_axis_v": c.srn_axis_v + 0.1,
                                                       "srz_offset_t": c.srz_offset_t - 0.15, "srz_offset_n": c.srz_offset_n}),
                "next": "add_files(files), fit(sn_gold=...)"}

    def status(self) -> dict:
        if not self.started:
            return self.guide()
        return {"optic": self.optic, "frame": rounded(asdict(self.frame)), "files": self.file_list()["files"],
                "sn_points": len(self.sn_points), "fitted": self.result is not None, **self.guide()}


__all__ = ["GoldFrameSession", "STEPS"]
