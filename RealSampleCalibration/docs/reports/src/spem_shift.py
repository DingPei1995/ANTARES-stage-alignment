"""Shift of the device between the two SPEM maps (plate frame) vs what the stage model expects from the motors."""
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))
from quickalignment.core.calibration import CalibrationStore
from quickalignment.core.geometry import PLATES
from quickalignment.core.stage import MotorPositions, StageModel

D = Path(__file__).parent / "spem"
a, b = np.load(D / "before.npz"), np.load(D / "after.npz")
step = float(a["x"][1] - a["x"][0])


def norm(img):
    img = ndimage.gaussian_filter(img.astype(float), 0.7)
    lo, hi = np.percentile(img, [5, 99])
    return np.clip((img - lo) / (hi - lo), 0, 1.2)


A, Bm = norm(a["total"]), norm(b["total"])
best = None
for dy in np.arange(-10, 10.01, 0.1):        # pixel shift applied to map B (rows = PIY, cols = PIX)
    for dx in np.arange(-10, 10.01, 0.1):
        s = ndimage.shift(Bm, (dy, dx), order=1, mode="constant", cval=np.nan)
        ok = np.isfinite(s)
        if ok.sum() < 300:
            continue
        r = np.corrcoef(A[ok], s[ok])[0, 1]
        if best is None or r > best[0]:
            best = (r, dy, dx)
r, dy, dx = best
# feature in B sits at (A position - shift): B moved by (-dx, -dy) px relative to A
d_pix, d_piy = -dx * step, -dy * step
print(f"best corr {r:.3f}; device in map 2 relative to map 1: dPIX {d_pix:+.1f} um, dPIY {d_piy:+.1f} um, "
      f"|d| {np.hypot(d_pix, d_piy):.1f} um")

# model: plate point on the beam (piezo centred) at the two recorded stage positions
rec = next(r for r in CalibrationStore(ROOT / "configs").records() if r.path.name == "calibration_2026-11-14_173743_capillary.json")
model = StageModel(rec.config, PLATES["gating"])
W = 5.5
m1 = MotorPositions(st=-1.9207, sz=40.04, sn=-0.30013125, srn=119.999942073, srz=-0.000249648)
m2 = MotorPositions(st=-1.7658, sz=39.932, sn=-0.45163125, srn=150.000582453, srz=-9.999931626)
p = []
for m in (m1, m2):
    hit = model.beam_hit(m, W)
    uvw = model.lab_to_plate(m, hit)
    focus = model.lab_to_plate(m, np.zeros(3))
    p.append(uvw)
    print(f"  beam on plate x {uvw[0]:.4f}, y {uvw[1]:.4f}; distance of that point from the analyzer focus "
          f"{np.linalg.norm(hit) * 1000:.1f} um")
du, dv = (p[1][0] - p[0][0]) * 1000, (p[1][1] - p[0][1]) * 1000
print(f"model: plate point on the beam moves by dx {du:+.1f} um, dy {dv:+.1f} um between the files")
np.savez(D / "shift.npz", d_pix=d_pix, d_piy=d_piy, corr=r, du=du, dv=dv, p1=p[0], p2=p[1])
