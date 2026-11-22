"""The focusing optic at other photon energies.

The configurations (calibration_*.json) were all measured at 95 eV: the optic position that puts the focus on
the reference point, and "the working distance of the optic is fixed", hold at that photon energy. At another
photon energy the optic has to move along the beam by an energy shift:

* zone plate (+ OSA): the focal length f = D x dr / lambda grows in proportion to the photon energy
  (f(hv) = f_ref x hv / hv_ref); the zone plate has to move away from the sample by f(hv) - f_ref. The model needs
  f_ref, the focal length at the reference energy (from the zone plate's diameter D and outermost zone width dr:
  f = D x dr / lambda, lambda [nm] = 1239.84 / hv [eV]); until it is set, only measured points are used. The OSA has to
  follow the zone plate; it is not computed here.
* capillary: a mirror, achromatic: no shift (measured points correct it if needed).

Measured points (optic position in focus at a photon energy minus the position predicted at the reference
energy, for the same point of the sample) are kept in ``configs/optics_vs_hv.json`` and take precedence: between
them the shift is interpolated linearly; outside them it follows the model's slope from the nearest point (zone
plate with f_ref) or stays at the nearest point's value (capillary, or zone plate without f_ref).

The shift is applied by moving the optic reference of a configuration (`optics_at_energy`): every optic position
then predicted (bring_to_beam, rotate, centre_piezo, beam_on, anti-collision) is for that photon energy, and every
optic position read at that photon energy is understood as such.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from pathlib import Path

from .fileio import read_json, write_json
from .stage import OpticsCalibration

REFERENCE_HV = 95.0  # eV: the photon energy of every configuration made before photon_energy was recorded
FILE = "optics_vs_hv.json"
HC_EV_NM = 1239.84193
OPTIC_KEYS = ("zone plate", "capillary")


def optic_key(optic_type: str) -> str:
    return "capillary" if "capillary" in str(optic_type).lower() else "zone plate"


@dataclass
class EnergyPoint:
    hv: float  # eV
    shift: float  # mm of optic motor: position in focus at hv - position predicted at the reference energy
    created: str = ""
    comment: str = ""


@dataclass
class OpticEnergy:
    model: str = "achromatic"  # "zone_plate": f proportional to hv; "achromatic": no shift
    focal_length_mm: float | None = None  # zone plate: focal length at the reference energy (None: not known)
    points: list[EnergyPoint] = field(default_factory=list)

    def model_slope(self, optic_sign: int) -> float | None:
        """d(shift)/d(hv) in mm/eV from the model; None when the model is not known (zone plate without f)."""
        if self.model == "zone_plate":
            if self.focal_length_mm is None:
                return None
            # a longer focal length: the zone plate moves upstream, away from the sample (against +optic_sign)
            return -optic_sign * self.focal_length_mm / REFERENCE_HV
        return 0.0


@dataclass
class EnergyShift:
    shift: float  # mm of optic motor, relative to the reference energy
    source: str  # how it was found


class OpticsEnergyTable:
    """configs/optics_vs_hv.json: per optic, the model and the measured points."""

    def __init__(self, reference_hv: float = REFERENCE_HV, optics: dict | None = None, path: Path | None = None):
        self.reference_hv = float(reference_hv)
        self.optics = optics or {"zone plate": OpticEnergy("zone_plate"), "capillary": OpticEnergy("achromatic")}
        self.path = path

    # -------------------------------------------------------------------------------------------------- files
    @classmethod
    def load(cls, folder: str | Path) -> OpticsEnergyTable:
        path = Path(folder) / FILE
        try:
            data = read_json(path)
        except (OSError, ValueError):
            return cls(path=path)
        optics = {}
        for key in OPTIC_KEYS:
            raw = data.get("optics", {}).get(key) or {}
            f = raw.get("focal_length_mm")
            points = []
            for p in raw.get("points", []):
                try:
                    hv, shift = float(p["hv"]), float(p["shift"])
                except (KeyError, TypeError, ValueError):
                    continue
                if math.isfinite(hv) and math.isfinite(shift):
                    points.append(EnergyPoint(hv, shift, str(p.get("created", "")), str(p.get("comment", ""))))
            optics[key] = OpticEnergy(str(raw.get("model", "zone_plate" if key == "zone plate" else "achromatic")),
                                      None if f is None else float(f), points)
        return cls(float(data.get("reference_hv", REFERENCE_HV)), optics, path)

    def to_dict(self) -> dict:
        return {"_comment": "Focusing optic against photon energy (quickalignment/core/photon_energy.py). shift: "
                            "optic position in focus at hv minus the position predicted at reference_hv, in mm "
                            "of optic motor. focal_length_mm: zone plate focal length at reference_hv.",
                "reference_hv": self.reference_hv,
                "optics": {k: {"model": o.model, "focal_length_mm": o.focal_length_mm,
                               "points": [asdict(p) for p in sorted(o.points, key=lambda p: p.hv)]}
                           for k, o in self.optics.items()}}

    def save(self, folder: str | Path | None = None) -> Path:
        path = Path(folder) / FILE if folder else self.path
        if path is None:
            raise ValueError("No folder to save optics_vs_hv.json in.")
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json(path, self.to_dict())
        self.path = path
        return path

    # -------------------------------------------------------------------------------------------- the shift
    def shift(self, optic_type: str, hv: float | None, optic_sign: int = 1) -> EnergyShift:
        """Optic shift (mm) at photon energy hv relative to the reference energy."""
        if hv is None or abs(float(hv) - self.reference_hv) < 1e-9:
            return EnergyShift(0.0, f"reference energy {self.reference_hv:g} eV")
        hv = float(hv)
        o = self.optics.get(optic_key(optic_type), OpticEnergy())
        pts = sorted([EnergyPoint(self.reference_hv, 0.0)] + [p for p in o.points
                                                              if abs(p.hv - self.reference_hv) > 1e-9],
                     key=lambda p: p.hv)
        slope = o.model_slope(optic_sign)
        if len(pts) > 1 and pts[0].hv <= hv <= pts[-1].hv:
            for a, b in zip(pts, pts[1:]):
                if a.hv <= hv <= b.hv:
                    t = (hv - a.hv) / (b.hv - a.hv) if b.hv > a.hv else 0.0
                    return EnergyShift(a.shift + t * (b.shift - a.shift),
                                       f"interpolated between measured {a.hv:g} and {b.hv:g} eV")
        end = pts[0] if hv < pts[0].hv else pts[-1]
        if slope is not None:
            what = "zone plate focal length proportional to hv" if o.model == "zone_plate" else "achromatic"
            return EnergyShift(end.shift + slope * (hv - end.hv),
                               f"model ({what}) from {'the reference' if end.hv == self.reference_hv else 'measured'} "
                               f"{end.hv:g} eV")
        return EnergyShift(end.shift, f"NOT KNOWN beyond {end.hv:g} eV: zone plate focal length at "
                                      f"{self.reference_hv:g} eV not set in {FILE} and no measured point; shift kept "
                                      f"at {end.shift:+.4f} mm")

    def add_point(self, optic_type: str, hv: float, shift: float, comment: str = "") -> EnergyPoint:
        o = self.optics.setdefault(optic_key(optic_type), OpticEnergy())
        p = EnergyPoint(float(hv), float(shift), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), str(comment))
        o.points = [q for q in o.points if abs(q.hv - p.hv) > 1e-6] + [p]
        return p

    def describe(self) -> dict:
        out = {"reference_hv": self.reference_hv, "file": str(self.path) if self.path else None}
        for k, o in self.optics.items():
            out[k] = {"model": o.model, "focal_length_mm": o.focal_length_mm,
                      "measured": [{"hv": p.hv, "shift_mm": round(p.shift, 4), "created": p.created,
                                    "comment": p.comment} for p in sorted(o.points, key=lambda p: p.hv)]}
        return out


def zone_plate_focal_length(diameter_um: float, outer_zone_nm: float, hv: float = REFERENCE_HV) -> float:
    """f = D dr / lambda in mm, for a zone plate of diameter D (µm) and outermost zone width dr (nm) at hv (eV)."""
    lam_nm = HC_EV_NM / float(hv)
    return float(diameter_um) * 1e-3 * float(outer_zone_nm) / lam_nm


def optics_at_energy(cal: OpticsCalibration, table: OpticsEnergyTable, hv: float | None) -> tuple[OpticsCalibration,
                                                                                                    EnergyShift]:
    """The optic reference moved to photon energy hv (None: as measured). The configuration's own photon energy
    (cal.photon_energy) is taken into account: the shift is shift(hv) - shift(photon_energy of the reference)."""
    if hv is None or abs(float(hv) - cal.photon_energy) < 1e-9:
        return cal, EnergyShift(0.0, f"photon energy of the configuration ({cal.photon_energy:g} eV)")
    to = table.shift(cal.optic_type, hv, cal.optic_sign)
    frm = table.shift(cal.optic_type, cal.photon_energy, cal.optic_sign)
    d = to.shift - frm.shift
    moved = replace(cal, optic_position=cal.optic_position + d,
                    last_position=None if cal.last_position is None else cal.last_position + d,
                    photon_energy=float(hv))
    return moved, EnergyShift(d, to.source)


__all__ = ["REFERENCE_HV", "EnergyPoint", "EnergyShift", "OpticEnergy", "OpticsEnergyTable", "optic_key",
           "optics_at_energy", "zone_plate_focal_length"]
