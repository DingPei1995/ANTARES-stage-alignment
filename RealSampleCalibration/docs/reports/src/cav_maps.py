"""Cav test (2026-11-14): the two SPEM files before / after the SRz rotation, read with ARPES viewer's loader.

Saves spem/cav_before.npz, spem/cav_after.npz (integrated maps, angle-energy images, motor values from the file)
and spem/cav_shift.npz (shift of the sample between the maps and the shift the stage model expects).
"""
import os
import sys
from pathlib import Path

import h5py
import numpy as np
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, os.environ.get("ARPES_VIEWER", r"D:\Codes\ARPES-viewer-main"))
from arpes_viewer.loader.registry import load  # noqa: E402
from quickalignment.core.calibration import CalibrationStore  # noqa: E402
from quickalignment.core.geometry import PLATES  # noqa: E402
from quickalignment.core.stage import MotorPositions, StageModel  # noqa: E402

OUT = Path(__file__).parent / "spem"
OUT.mkdir(exist_ok=True)
FILES = {"cav_before": "Cav_2026-11-14_19-48-34.nxs", "cav_after": "Cav_2026-11-14_20-06-03.nxs"}
H = 0.748  # Cav height above the plate surface (SN -0.05 at the analyzer focus, SRn 120 / SRz 0)
W = 5.0 + H

MOTORS = {"st": "i12-m-cx1-ex-sample-mt_st/position", "sz": "i12-m-cx1-ex-sample-mt_sz/position",
          "sn": "i12-m-cx1-ex-sample-mt_sn/position", "srn": "i12-m-cx1-ex-sample-mt_srn/position",
          "srz": "i12-m-cx1-ex-sample-mt_srz/position", "cps": "i12-m-cx1-op-cap-mt-ts/value",
          "hv": "i12-m-c04-op-mono1/energy"}


def motors_of(path):
    with h5py.File(path, "r") as f:
        g = f["img1_0001/ANTARES"]
        return {k: float(np.ravel(g[v][()])[0]) for k, v in MOTORS.items()}


for tag, name in FILES.items():
    path = ROOT / "Cav" / name
    s = load(str(path))
    cube = np.asarray(s.value4d[:, :, :, :], float)  # (PIY, PIX, angle along slit, KE)
    x, y, k, e = (np.asarray(v) for v in (s.x, s.y, s.k, s.z))
    s.close()
    mot = motors_of(path)
    np.savez(OUT / f"{tag}.npz", x=x, y=y, k=k, e=e, total=cube.sum(axis=(2, 3)), ek=cube.sum(axis=(0, 1)),
             spec=cube.sum(axis=(0, 1, 2)), **{f"m_{a}": v for a, v in mot.items()})
    print(tag, name, {a: round(v, 4) for a, v in mot.items()}, "map", cube.shape)

# shift of the sample between the two integrated maps (same method as spem_shift.py)
a, b = np.load(OUT / "cav_before.npz"), np.load(OUT / "cav_after.npz")
step = float(a["x"][1] - a["x"][0])


def norm(img):
    img = ndimage.gaussian_filter(img.astype(float), 0.7)
    lo, hi = np.percentile(img, [5, 99])
    return np.clip((img - lo) / (hi - lo), 0, 1.2)


A, Bm = norm(a["total"]), norm(b["total"])
best = None
for dy in np.arange(-12, 12.01, 0.1):
    for dx in np.arange(-12, 12.01, 0.1):
        sh = ndimage.shift(Bm, (dy, dx), order=1, mode="constant", cval=np.nan)
        ok = np.isfinite(sh)
        if ok.sum() < 300:
            continue
        r = np.corrcoef(A[ok], sh[ok])[0, 1]
        if best is None or r > best[0]:
            best = (r, dy, dx)
r, dy, dx = best
d_pix, d_piy = -dx * step, -dy * step
print(f"best corr {r:.3f}; sample in map 2 relative to map 1: dPIX {d_pix:+.1f} um, dPIY {d_piy:+.1f} um")

rec = next(x for x in CalibrationStore(ROOT / "configs").records()
           if x.path.name == "calibration_2026-11-14_173743_capillary.json")
model = StageModel(rec.config, PLATES["gating"])
pts, dist = [], []
for d in (a, b):
    m = MotorPositions(st=float(d["m_st"]), sz=float(d["m_sz"]), sn=float(d["m_sn"]), srn=float(d["m_srn"]),
                       srz=float(d["m_srz"]))
    hit = model.beam_hit(m, W)
    pts.append(model.lab_to_plate(m, hit))
    dist.append(float(np.linalg.norm(hit)) * 1000)
du, dv = (pts[1][0] - pts[0][0]) * 1000, (pts[1][1] - pts[0][1]) * 1000
# map direction: +PIX moves the plate +x, +PIY moves the plate -y (PIY increases towards plate +y in the maps)
exp_pix, exp_piy = du, -dv
print(f"model: beam point on the plate x {pts[0][0]:.4f} -> {pts[1][0]:.4f}, y {pts[0][1]:.4f} -> {pts[1][1]:.4f}; "
      f"from the analyzer focus {dist[0]:.1f} / {dist[1]:.1f} um; expected map shift {exp_pix:+.1f} / {exp_piy:+.1f} um")
np.savez(OUT / "cav_shift.npz", d_pix=d_pix, d_piy=d_piy, corr=r, exp_pix=exp_pix, exp_piy=exp_piy,
         dist1=dist[0], dist2=dist[1], p1=pts[0], p2=pts[1])
