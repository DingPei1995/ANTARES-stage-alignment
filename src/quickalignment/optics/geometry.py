"""3-D geometry of the focusing optics: zone plate (ZP) and capillary on the shared ZPZ carriage.

Separate from the stage model: nothing here is used by QuickAlignment or RealSampleCalibration.
It runs through its own program (OpticsGeometry/OpticsGeometry.py).

Lab frame of `quickalignment.core.stage`, mm: origin = analyzer focus, +x right, +y along the beam
(downstream), +z up. The analyzer sits at -n = (-1, -1, 0)/sqrt2, so "towards the analyzer" across the
beam is -x.

Reference line: the zone-plate beam, along +y through the origin. With the ZP motors at their reference
(ZP in focus at the analyzer focus), the ZP focus is the origin.

Motors (directions given by the beamline, 2026-11-17):

* ZPS  + downstream (+y)            ZPZ  + up (+z), shared by ZP and capillary
* ZPX  + towards the analyzer (-x)
* CPS  + downstream (+y)            CPX  + towards the analyzer (-x)
* Cap Rz (``cap-mt-rz``): the tip turning towards the analyzer is negative  (PROVISIONAL, to confirm)
* Cap Rx (``cap_rx``):    the tip turning up is positive

Model (first version):

* The incoming beam is taken parallel to +y. A zone plate images a far source, so its focus follows
  the lens 1:1 across the beam (ZPX, ZPZ) and along it (ZPS).
* The capillary focus is fixed to the capillary body (at its working distance past the tip): it follows
  CPS, CPX and ZPZ 1:1, and turns with Cap Rz / Cap Rx about a pivot `pivot_to_focus` mm behind the
  focus on the capillary axis (unknown yet: 0 = the rotations turn the beam about the focus).
* The capillary beam is parallel to the ZP beam at its reference angles (to be corrected later).
* The capillary reference focus comes from the calibration configs: the same plate point is on the ZP
  spot at (ST0, SZ0, SN_f) of the zone-plate config and on the capillary spot at those of the capillary
  config, so the capillary spot is (dST0) t + (dSN_f) n + (dSZ0) z from the ZP spot.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

import numpy as np

from ..core.stage import N_HAT, T_HAT, Z_HAT

X_HAT = np.array([1.0, 0.0, 0.0])
Y_HAT = np.array([0.0, 1.0, 0.0])

# Lab direction of +1 mm of each translation motor.
ZPS_DIR = Y_HAT
ZPX_DIR = -X_HAT  # towards the analyzer
ZPZ_DIR = Z_HAT
CPS_DIR = Y_HAT
CPX_DIR = -X_HAT  # towards the analyzer

# Cap Rz: a positive right-handed turn about +z swings the tip (+y) towards -x, the analyzer side.
# The beamline says that direction is NEGATIVE Cap Rz, so +Cap Rz is a turn about -z. PROVISIONAL.
CAP_RZ_SIGN = -1.0
# Cap Rx: a positive right-handed turn about +x swings the tip (+y) up (+z): as the beamline says.
CAP_RX_SIGN = 1.0

ANGLE_UNITS = {"deg": np.pi / 180.0, "mrad": 1e-3, "rad": 1.0}

# Tango devices of the optics motors (as recorded in the ANTARES .nxs files: "/" -> "-").
TANGO = {
    "zps": "i12-m-cx1/op/zp-mt_zs",
    "zpx": "i12-m-cx1/op/zp-mt_zx",
    "zpz": "i12-m-cx1/op/zp-mt_zz",
    "cps": "i12-m-cx1/op/cap-mt-ts",
    "cpx": "i12-m-cx1/op/cap-mt-tx",
    "cap_rz": "i12-m-cx1/op/cap-mt-rz",
    "cap_rx": "i12-m-cx1/op/cap_rx",
    "osa_s": "i12-m-cx1/op/osa-mt_os",
    "osa_x": "i12-m-cx1/op/osa-mt_ox",
    "osa_z": "i12-m-cx1/op/osa-mt_oz",
}


def rot_x(a: float) -> np.ndarray:
    c, s = np.cos(a), np.sin(a)
    return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]])


def rot_z(a: float) -> np.ndarray:
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


@dataclass
class OpticsMotors:
    """Readings of the optics motors (mm; Cap Rz / Rx in deg) and the photon energy (eV, None: the ZP reference
    energy)."""

    zps: float = 0.0
    zpx: float = 0.0
    zpz: float = 0.0
    cps: float = 0.0
    cpx: float = 0.0
    cap_rz: float = 0.0
    cap_rx: float = 0.0
    osa_s: float | None = None
    osa_x: float | None = None
    osa_z: float | None = None
    energy: float | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "OpticsMotors":
        names = {f.name for f in fields(cls)}
        return cls(**{k: float(v) for k, v in d.items() if k in names and v is not None})


@dataclass
class ZonePlateReference:
    """ZP motors putting the ZP focus on the analyzer focus (lab origin) at the photon energy `energy`.

    The focal length is proportional to the photon energy, f = focal_per_ev * E (the beamline's ZPS energy
    coefficient, -0.256 mm/eV, with ZPS taken 1:1 with the lens): 24.32 mm at 95 eV. The ZP itself (the lens) is f
    upstream of its focus."""

    zps: float = 53.7502
    zpx: float = 0.4683
    zpz: float = 23.511
    energy: float = 95.0  # eV of the reference (the zone plate is used at 95 eV)
    focal_per_ev: float = 0.256  # mm/eV: f = focal_per_ev * E; ZPS refocuses by -focal_per_ev per eV
    zps_per_mm: float = 1.0  # ZPS change per mm of focus along the beam (SN-slide checks 0.95 - 1.015; 1:1 chosen)
    zps_parked: float = -20.0
    source: str = ("ZPS: configs/calibration_2026-11-15_151356_zone_plate.json (optic_position, 95 eV); "
                   "ZPX, ZPZ: Cav/Cav_2026-11-15_11-13-55.nxs; energy coefficient -0.256 mm/eV: beamline 2026-11-17")

    def focal_length(self, energy: float | None = None) -> float:
        return self.focal_per_ev * (self.energy if energy is None else energy)


@dataclass
class OsaReference:
    """OSA working position (beamline, 2026-11-17): centred on the ZP beam, the OSA shield crossing the beam
    `distance` mm upstream of the reference ZP focus (estimate of the anti-collision model). OSA S: + downstream
    (as ZPS); OSA Z: + up (as ZPZ); OSA X: direction not known, hardly ever moved (not used for the position)."""

    s: float = 80.0
    x: float = 0.5
    z: float = 26.63
    distance: float = 3.5
    parked_s: float = 20.0  # OSA out of the beam (beamline, 2026-11-18): S 20, Z -5, X unchanged
    parked_z: float = -5.0
    source: str = ("S 80, X 0.5, Z 26.63: OSA working position (beamline 2026-11-17); 3.5 mm: collision model "
                   "estimate; parked S 20, Z -5 (beamline 2026-11-18)")


@dataclass
class CapillaryReference:
    """Capillary motors of the reference capillary focus `focus` (lab, mm)."""

    cps: float = 61.50753956178848
    cpx: float = 57.14
    zpz: float = 3.2395
    cap_rz: float = -0.408
    cap_rx: float = 3.9056
    focus: tuple = (0.0, 0.0, 0.0)  # filled by `capillary_focus_from_configs`
    direction: tuple = (0.0, 1.0, 0.0)  # beam direction at the reference angles (parallel to the ZP beam)
    cps_per_mm: float = 1.0
    angle_unit: str = "deg"  # unit of Cap Rz / Rx (confirmed 2026-11-17)
    pivot_to_focus: float = 0.0  # mm from the Rz / Rx pivot to the focus along the axis: NOT KNOWN YET
    parked: tuple = (0.0, 0.0)  # CPS, CPX when the capillary is out
    source: str = ("CPS: configs/calibration_2026-11-15_151356_capillary.json (optic_position); "
                   "CPX, ZPZ, Cap Rz, Cap Rx: Cav/Cav_2026-11-14_19-48-34.nxs")


@dataclass
class OpticsGeometryConfig:
    zone_plate: ZonePlateReference = field(default_factory=ZonePlateReference)
    capillary: CapillaryReference = field(default_factory=CapillaryReference)
    comment: str = ""
    osa: OsaReference = field(default_factory=OsaReference)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["capillary"]["focus"] = [float(v) for v in self.capillary.focus]
        d["capillary"]["direction"] = [float(v) for v in self.capillary.direction]
        d["capillary"]["parked"] = [float(v) for v in self.capillary.parked]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "OpticsGeometryConfig":
        zp = ZonePlateReference(**d.get("zone_plate", {}))
        cap = dict(d.get("capillary", {}))
        for k in ("focus", "direction", "parked"):
            if k in cap:
                cap[k] = tuple(float(v) for v in cap[k])
        return cls(zp, CapillaryReference(**cap), d.get("comment", ""), OsaReference(**d.get("osa", {})))

    def save(self, path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path) -> "OpticsGeometryConfig":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def capillary_focus_from_configs(zp_stage: dict, cap_stage: dict) -> np.ndarray:
    """Lab position of the capillary spot from the `stage_config` blocks of a zone-plate and a capillary
    calibration config taken on the same plate (ZP spot = origin)."""
    d_st = float(cap_stage["st0"]) - float(zp_stage["st0"])
    d_sz = float(cap_stage["sz0"]) - float(zp_stage["sz0"])
    d_sn = float(cap_stage["sn_f"]) - float(zp_stage["sn_f"])
    return d_st * T_HAT + d_sn * N_HAT + d_sz * Z_HAT


def default_config(configs_dir=None) -> OpticsGeometryConfig:
    """Reference geometry of 2026-11-14 / 15 (gating plate, sample Cav)."""
    cfg = OpticsGeometryConfig(comment="ZP beam = reference line (+y through the analyzer focus); "
                                       "capillary beam taken parallel to it. Cap Rz sign provisional.")
    configs_dir = Path(configs_dir) if configs_dir else Path(__file__).resolve().parents[3] / "configs"
    zp_file = configs_dir / "calibration_2026-11-15_151356_zone_plate.json"
    cap_file = configs_dir / "calibration_2026-11-15_151356_capillary.json"
    if zp_file.exists() and cap_file.exists():
        zp = json.loads(zp_file.read_text(encoding="utf-8"))
        cap = json.loads(cap_file.read_text(encoding="utf-8"))
        focus = capillary_focus_from_configs(zp["stage_config"], cap["stage_config"])
        cfg.zone_plate.zps = float(zp["optics"]["optic_position"])
        cfg.capillary.cps = float(cap["optics"]["optic_position"])
    else:  # the numbers of those files
        focus = capillary_focus_from_configs(
            {"st0": -0.8127, "sz0": 41.2059, "sn_f": -0.798260207455943},
            {"st0": -1.6127389262697402, "sz0": 41.015885840956955, "sn_f": -0.798260207455943})
    cfg.capillary.focus = tuple(float(v) for v in focus)
    return cfg


@dataclass
class Beam:
    optic: str  # "zone plate", "capillary" or "none"
    focus: np.ndarray  # lab, mm
    direction: np.ndarray  # unit vector, downstream

    def point_at(self, s: float) -> np.ndarray:
        return self.focus + s * self.direction

    def hit_plane(self, point=(0.0, 0.0, 0.0), normal=N_HAT) -> np.ndarray:
        """Where the beam line crosses a plane (default: the sample surface at SN_f, SRz 0)."""
        normal = np.asarray(normal, float)
        den = float(self.direction @ normal)
        if abs(den) < 1e-12:
            raise ValueError("The beam runs parallel to the plane.")
        s = float((np.asarray(point, float) - self.focus) @ normal) / den
        return self.point_at(s)


class OpticsGeometry:
    def __init__(self, config: OpticsGeometryConfig | None = None):
        self.config = config or default_config()

    # --- which optic is in the beam -------------------------------------------------------------------
    def active_optic(self, m: OpticsMotors, tol: float = 0.5) -> str:
        zp, cap = self.config.zone_plate, self.config.capillary
        cap_parked = abs(m.cps - cap.parked[0]) < 1e-3 and abs(m.cpx - cap.parked[1]) < 1e-3
        zp_parked = abs(m.zps - zp.zps_parked) < tol
        if not cap_parked and abs(m.zpz - cap.zpz) < abs(m.zpz - zp.zpz):
            return "capillary"
        if not zp_parked:
            return "zone plate"
        return "none"

    # --- zone plate -------------------------------------------------------------------------------------
    def zone_plate_lens(self, m: OpticsMotors) -> np.ndarray:
        """Lab position of the zone plate itself (centre of the lens): f(E_ref) upstream of the reference focus."""
        r = self.config.zone_plate
        return ((m.zps - r.zps) / r.zps_per_mm * ZPS_DIR + (m.zpx - r.zpx) * ZPX_DIR
                + (m.zpz - r.zpz) * ZPZ_DIR - r.focal_length() * Y_HAT)

    def zone_plate_focus(self, m: OpticsMotors, energy: float | None = None) -> np.ndarray:
        """Lab position of the ZP focus: the lens plus f(E) along the beam (E: `energy`, else m.energy, else the
        reference energy)."""
        r = self.config.zone_plate
        e = energy if energy is not None else m.energy
        return self.zone_plate_lens(m) + r.focal_length(e) * Y_HAT

    def zone_plate_motors_for(self, focus, m: OpticsMotors | None = None, energy: float | None = None) -> OpticsMotors:
        """ZP motors putting the ZP focus at `focus` (lab) at the photon energy (default: m.energy, else the
        reference); the other motors kept from `m`."""
        r = self.config.zone_plate
        f = np.asarray(focus, float)
        out = OpticsMotors(**asdict(m)) if m else OpticsMotors()
        e = energy if energy is not None else out.energy
        df = r.focal_length(e) - r.focal_length()
        out.zps = r.zps + r.zps_per_mm * (float(f @ ZPS_DIR) - df)
        out.zpx = r.zpx + float(f @ ZPX_DIR)
        out.zpz = r.zpz + float(f @ ZPZ_DIR)
        return out

    def osa_position(self, m: OpticsMotors) -> np.ndarray:
        """Lab position where the OSA shield crosses the ZP beam axis (OSA X not used; missing readings: the
        working position)."""
        o = self.config.osa
        s = o.s if m.osa_s is None else m.osa_s
        z = o.z if m.osa_z is None else m.osa_z
        return (s - o.s) * Y_HAT + (z - o.z) * Z_HAT - o.distance * Y_HAT

    # --- capillary --------------------------------------------------------------------------------------
    def capillary_rotation(self, m: OpticsMotors) -> np.ndarray:
        r = self.config.capillary
        k = ANGLE_UNITS[r.angle_unit]
        a_z = CAP_RZ_SIGN * (m.cap_rz - r.cap_rz) * k
        a_x = CAP_RX_SIGN * (m.cap_rx - r.cap_rx) * k
        return rot_z(a_z) @ rot_x(a_x)  # Rx stage taken on top of the Rz stage (order unknown; small angles)

    def capillary_beam(self, m: OpticsMotors) -> Beam:
        r = self.config.capillary
        d0 = np.asarray(r.direction, float)
        d0 = d0 / np.linalg.norm(d0)
        f0 = np.asarray(r.focus, float)
        shift = ((m.cps - r.cps) / r.cps_per_mm * CPS_DIR + (m.cpx - r.cpx) * CPX_DIR
                 + (m.zpz - r.zpz) * ZPZ_DIR)
        rot = self.capillary_rotation(m)
        pivot = f0 - r.pivot_to_focus * d0
        focus = pivot + rot @ (f0 - pivot) + shift
        return Beam("capillary", focus, rot @ d0)

    def capillary_motors_for(self, focus, m: OpticsMotors | None = None) -> OpticsMotors:
        """CPS, CPX, ZPZ putting the capillary focus at `focus` (lab), angles kept from `m`."""
        r = self.config.capillary
        base = OpticsMotors(**asdict(m)) if m else OpticsMotors(cps=r.cps, cpx=r.cpx, zpz=r.zpz,
                                                                cap_rz=r.cap_rz, cap_rx=r.cap_rx)
        now = self.capillary_beam(base).focus
        d = np.asarray(focus, float) - now
        base.cps += r.cps_per_mm * float(d @ CPS_DIR)
        base.cpx += float(d @ CPX_DIR)
        base.zpz += float(d @ ZPZ_DIR)
        return base

    # --- the beam in use --------------------------------------------------------------------------------
    def beam(self, m: OpticsMotors, optic: str | None = None) -> Beam:
        optic = optic or self.active_optic(m)
        if optic == "capillary":
            return self.capillary_beam(m)
        if optic == "zone plate":
            return Beam("zone plate", self.zone_plate_focus(m), Y_HAT.copy())  # at m.energy
        raise ValueError("No optic in the beam (ZP and capillary parked).")

    def stage_offsets(self, m: OpticsMotors, optic: str | None = None) -> dict:
        """What the beam of `optic` changes for the stage model, against the ZP reference spot:

        dst0, dsz0: add to the zone-plate ST0 / SZ0 (the spot on the sample surface at SN_f, SRz 0);
        focus_along_beam: focus minus that spot along the beam (mm, + = focus downstream of the surface).
        """
        b = self.beam(m, optic)
        hit = b.hit_plane()
        return {"optic": b.optic, "spot": hit, "focus": b.focus, "direction": b.direction,
                "dst0": float(hit @ T_HAT), "dsz0": float(hit @ Z_HAT),
                "focus_along_beam": float((b.focus - hit) @ b.direction)}


__all__ = [
    "ANGLE_UNITS", "Beam", "CAP_RX_SIGN", "CAP_RZ_SIGN", "CapillaryReference", "OpticsGeometry",
    "OpticsGeometryConfig", "OpticsMotors", "OsaReference", "TANGO", "ZonePlateReference", "capillary_focus_from_configs",
    "default_config",
]
