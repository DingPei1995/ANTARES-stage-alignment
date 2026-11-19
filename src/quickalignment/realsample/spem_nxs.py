"""Read the motor positions recorded in an ANTARES SPEM scan (.nxs): the stage, the piezo, the optic motors and the
photon energy when the map was taken. Used by RealSampleCalibration to fill a measured set from a SPEM map.

Layout: ``/<entry>/ANTARES/i12-m-cx1-ex-sample-mt_<st|sn|sz|srn|srz>/position`` (motors), ``/<entry>/ANTARES/PI/PI_X``
and ``PI_Y`` (piezo), ``/<entry>/scan_config/trajectory/*`` (scanned axes). Needs h5py.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

SAMPLE_GROUP = "i12-m-cx1-ex-sample-mt_{}"


def _h5py():
    try:
        import h5py
    except ImportError:
        raise ImportError("reading .nxs files needs h5py (pip install h5py)") from None
    return h5py


def _text(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if isinstance(value, np.ndarray):
        return _text(value.reshape(-1)[0]) if value.size else ""
    return str(value)


def stage_of(name: str) -> str | None:
    """Sample stage of a Tango name: ``i12-m-cx1/ex/sample-mt_srn/position`` -> ``srn``, ``.../pi/x`` -> ``pix``."""
    tokens = [t for t in re.split(r"[/_\-. ]+", str(name or "").strip().lower()) if t]
    while tokens and tokens[-1] in ("position", "value", "pos"):
        tokens.pop()
    if not tokens:
        return None
    if tokens[-1] in ("st", "sn", "sz", "srn", "srz", "pix", "piy"):
        return tokens[-1]
    if tokens[-1] in ("x", "y") and len(tokens) > 1 and tokens[-2] == "pi":
        return "pi" + tokens[-1]
    return None


def _fixed_motors(f, entry) -> dict:
    out = {}
    for m in ("st", "sn", "sz", "srn", "srz"):
        path = f"{entry}/ANTARES/{SAMPLE_GROUP.format(m)}/position"
        if path in f:
            out[m] = float(np.asarray(f[path][()]).reshape(-1)[0])
    for m, name in (("pix", "PI_X"), ("piy", "PI_Y")):
        path = f"{entry}/ANTARES/PI/{name}"
        if path in f:
            out[m] = float(np.asarray(f[path][()]).reshape(-1)[0])
    return out


OPTIC_POSITIONS = {"zps": ("i12-m-cx1-op-zp-mt_zs/position",), "cps": ("i12-m-cx1-op-cap-mt-ts/value",
                                                                         "i12-m-cx1-op-cap-mt-ts/position")}


def read_positions(path, entry: str | None = None) -> dict:
    """Motor values recorded in a SPEM file (the stage when the map was taken): ST, SN, SZ, SRn, SRz, the piezo
    (PIX, PIY at the end of the scan, not the map centre), the optic motors (ZPS, CPS), the photon energy and the
    scanned axes (Tango name, from, to, step). OSA positions are not read (not reliable at ANTARES)."""
    h5py = _h5py()
    with h5py.File(path, "r") as f:
        entry = entry or next((k for k in f.keys() if isinstance(f[k], h5py.Group) and "scan_data" in f[k]), None)
        if entry is None:
            raise KeyError(f"{Path(path).name}: no scan entry")
        out = {"file": Path(path).name, "entry": entry, **_fixed_motors(f, entry)}
        for key, names in OPTIC_POSITIONS.items():
            for name in names:
                if f"{entry}/ANTARES/{name}" in f:
                    out[key] = float(np.asarray(f[f"{entry}/ANTARES/{name}"][()]).reshape(-1)[0])
                    break
        if f"{entry}/ANTARES/i12-m-c04-op-mono1/energy" in f:
            out["hv"] = float(np.asarray(f[f"{entry}/ANTARES/i12-m-c04-op-mono1/energy"][()]).reshape(-1)[0])
        if f"{entry}/start_time" in f:
            out["start_time"] = _text(f[f"{entry}/start_time"][()])
        axes = []
        traj = f.get(f"{entry}/scan_config/trajectory")
        if traj is not None:
            for name in sorted(traj.keys()):
                g = traj[name]
                try:
                    axes.append({"motor": stage_of(_text(g["name"][()])) or _text(g["name"][()]),
                                 "from": float(_text(g["from"][()])), "to": float(_text(g["to"][()])),
                                 "step": float(_text(g["delta"][()]))})
                except (KeyError, ValueError):
                    continue
        out["scanned"] = axes
    return out


__all__ = ["read_positions", "stage_of"]
