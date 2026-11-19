"""Optics and stage motor readings recorded in an ANTARES .nxs file (needs h5py)."""

from __future__ import annotations

from pathlib import Path

from .geometry import TANGO, OpticsMotors

STAGE_TANGO = {
    "st": "i12-m-cx1/ex/sample-mt_st",
    "sn": "i12-m-cx1/ex/sample-mt_sn",
    "sz": "i12-m-cx1/ex/sample-mt_sz",
    "srn": "i12-m-cx1/ex/sample-mt_srn",
    "srz": "i12-m-cx1/ex/sample-mt_srz",
}


def _value(group, name: str):
    """Reading of one Tango device in <entry>/ANTARES (device "/" written as "-"): position, else value."""
    key = name.replace("/", "-")
    if key not in group:
        return None
    dev = group[key]
    for attr in ("position", "value"):
        if attr in dev:
            v = dev[attr][()]
            try:
                return float(v.reshape(-1)[0]) if hasattr(v, "reshape") else float(v)
            except (TypeError, ValueError, IndexError):
                return None
    return None


def read_motors(path, entry: str | None = None) -> tuple[OpticsMotors, dict]:
    """(optics motors, every reading found: optics + stage motors) of the file's first entry."""
    try:
        import h5py
    except ImportError:
        raise ImportError("reading .nxs files needs h5py (pip install h5py)") from None
    with h5py.File(path, "r") as f:
        entry = entry or next((k for k in f.keys() if isinstance(f[k], h5py.Group) and "ANTARES" in f[k]), None)
        if entry is None:
            raise KeyError(f"{Path(path).name}: no entry with an ANTARES group")
        g = f[entry]["ANTARES"]
        found = {k: _value(g, name) for k, name in {**TANGO, **STAGE_TANGO}.items()}
        mono = "i12-m-c04-op-mono1"
        if mono in g and "energy" in g[mono]:
            found["energy"] = float(g[mono]["energy"][()].reshape(-1)[0])
    found = {k: v for k, v in found.items() if v is not None}
    return OpticsMotors.from_dict(found), found


__all__ = ["STAGE_TANGO", "read_motors"]
