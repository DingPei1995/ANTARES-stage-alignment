"""Helpers shared by the agent API: errors, motor positions from plain dicts, JSON-friendly numbers.

Everything the agent API returns is made of dicts, lists, strings, bools and numbers, so it can be sent as
JSON (MCP) as it is. Numbers are plain Python floats: JSON writes them with a "." whatever the system locale.
"""

from __future__ import annotations

import math
from dataclasses import fields

from ..core.stage import OPTIC_TYPES, MotorPositions

MOTOR_NAMES = tuple(f.name for f in fields(MotorPositions))  # st, sn, sz, srn, srz, pix, piy


class APIError(ValueError):
    """A request the API cannot carry out; the message says why and what to do (shown to the user)."""


def number(value, what: str) -> float:
    """A finite float from a number or a numeric string with a "." (never the system locale)."""
    if isinstance(value, bool) or value is None:
        raise APIError(f"{what}: a number is needed, got {value!r}.")
    try:
        out = float(value)
    except (TypeError, ValueError):
        raise APIError(f"{what}: {value!r} is not a number (use a '.' as decimal separator).") from None
    if not math.isfinite(out):
        raise APIError(f"{what}: {value!r} is not a finite number.")
    return out


def motors_from(data: dict | None, base: MotorPositions | None = None) -> MotorPositions:
    """MotorPositions from a dict such as {"st": -1.2, "sz": 40.1}; missing motors are taken from `base`."""
    base = base or MotorPositions()
    if data is None:
        return MotorPositions(**{k: getattr(base, k) for k in MOTOR_NAMES})
    if not isinstance(data, dict):
        raise APIError("Motor positions must be an object like {\"st\": -1.2, \"sz\": 40.1, \"sn\": 0.5}.")
    unknown = [k for k in data if k.lower() not in MOTOR_NAMES]
    if unknown:
        raise APIError(f"Unknown motor(s) {unknown}: use {', '.join(MOTOR_NAMES)}.")
    values = {k: getattr(base, k) for k in MOTOR_NAMES}
    for k, v in data.items():
        if v is not None:
            values[k.lower()] = number(v, k.upper())
    return MotorPositions(**values)


def rounded(value, digits: int = 4):
    """Floats rounded (also inside lists / tuples / dicts), -0.0 shown as 0.0; other values unchanged."""
    if isinstance(value, bool) or value is None or isinstance(value, (int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        r = round(float(value), digits)
        return 0.0 if r == 0 else r
    if isinstance(value, dict):
        return {k: rounded(v, digits) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [rounded(v, digits) for v in value]
    try:  # numpy scalars
        return rounded(float(value), digits)
    except (TypeError, ValueError):
        return value


def motors_dict(m: MotorPositions, digits: int = 4) -> dict:
    return {k: rounded(float(getattr(m, k)), 3 if k in ("srn", "srz") else digits) for k in MOTOR_NAMES}


def optic_type(name: str | None) -> str:
    """One of OPTIC_TYPES from a loose name ("capillary", "zone plate", "zone_plate", "zp", "zone plate + OSA")."""
    if name is None:
        raise APIError("Which focusing optic is mounted: 'capillary' or 'zone plate' (+ OSA)?")
    text = str(name).strip().lower().replace("_", " ")
    if "cap" in text:
        return OPTIC_TYPES[1]
    if "zone" in text or text in ("zp", "fzp", "osa"):
        return OPTIC_TYPES[0]
    raise APIError(f"Unknown optic {name!r}: use 'capillary' or 'zone plate'.")


def optic_short(optic: str) -> str:
    return "capillary" if "capillary" in optic else "zone plate"


__all__ = ["APIError", "MOTOR_NAMES", "motors_dict", "motors_from", "number", "optic_short", "optic_type", "rounded"]
