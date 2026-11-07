"""Motor travel ranges and the tolerances used when positions are proposed (no Qt: shared by the windows and
the agent API).

The limits can be changed for a session (Configuration window, ``configs/motor_limits.json``):
`set_motor_limits` updates MOTOR_SPECS and TRAVEL in place, so every user sees the new values.
"""

from __future__ import annotations

from .stage import MotorPositions

MOTOR_SPECS = {  # name: (label, min, max, decimals, step, suffix); min / max: default limits (Configuration window)
    "st": ("ST", -9, 9, 4, 0.1, " mm"),
    # SN: below the focal plane (SN_f ≈ 0) the real limit is a collision (OSA / capillary, analyzer 30 mm away),
    # computed for the current positions by the anti-collision check
    "sn": ("SN", -30, 65, 4, 0.1, " mm"),
    "sz": ("SZ", 35, 45, 4, 0.1, " mm"),
    "srn": ("SRn", -720, 720, 3, 1.0, " °"),
    "srz": ("SRz", -720, 720, 3, 1.0, " °"),
    "pix": ("PIX", 0, 300, 2, 1.0, " µm"),
    "piy": ("PIY", 0, 300, 2, 1.0, " µm"),
}
CONFIG_SPECS = {
    "st0": ("ST0 (plate centre)", " mm"),
    "sz0": ("SZ0 (plate centre)", " mm"),
    "sn_f": ("SN_f (plate surface in focus)", " mm"),
    "srn_ref": ("SRn ref (vertical, tab up)", " °"),
    "pi_center": ("Piezo centre", " µm"),
    "srn_axis_u": ("SRn axis u on plate", " mm"),
    "srn_axis_v": ("SRn axis v on plate", " mm"),
    "srz_offset_t": ("SRz axis offset along +ST", " mm"),
    "srz_offset_n": ("SRz axis offset along +SN", " mm"),
}
TOLERANCE = 1e-3  # mm; below this a move is reported as not needed
LARGE_FOUND_OFFSET = 0.3  # mm; a larger "Found here" correction hints at an outdated configuration
FOCUS_WARNING = 0.05  # mm from the analyzer focus; farther, the spectra would be distorted
TRAVEL = {name: MOTOR_SPECS[name][1:3] for name in ("st", "sn", "sz")}  # kept up to date by set_motor_limits
LIMIT_MOTORS = ("st", "sz", "sn", "srn", "srz")  # limits that can be changed by hand in the Configuration window
DEFAULT_LIMITS = {name: MOTOR_SPECS[name][1:3] for name in LIMIT_MOTORS}


def current_limits() -> dict[str, tuple[float, float]]:
    """Limits in use, {name: (min, max)} for LIMIT_MOTORS."""
    return {name: tuple(MOTOR_SPECS[name][1:3]) for name in LIMIT_MOTORS}


def set_motor_limits(limits: dict[str, tuple[float, float]]) -> None:
    """Use these limits (missing motors: the defaults) everywhere: input ranges, out-of-range and anti-collision
    checks. Input fields already made take them with MotorForm.apply_limits."""
    new = {name: limits.get(name, DEFAULT_LIMITS[name]) for name in LIMIT_MOTORS}
    for name, (lo, hi) in new.items():  # all checked before any is changed
        if not lo < hi:
            raise ValueError(f"{MOTOR_SPECS[name][0]}: min {lo:g} must be below max {hi:g}")
    for name, (lo, hi) in new.items():
        label, _, _, *rest = MOTOR_SPECS[name]
        MOTOR_SPECS[name] = (label, float(lo), float(hi), *rest)
    for name in TRAVEL:
        TRAVEL[name] = MOTOR_SPECS[name][1:3]


def out_of_range(m: MotorPositions) -> list[str]:
    """Motors of m outside their range, e.g. ["ST = 9.2000 (range −9 … 9)"]."""
    out = []
    for name, (label, lo, hi, dec, *_) in MOTOR_SPECS.items():
        value = getattr(m, name)
        if not lo <= value <= hi:
            out.append(f"{label} = {value:.{dec}f} (range {lo:g} … {hi:g})")
    return out
