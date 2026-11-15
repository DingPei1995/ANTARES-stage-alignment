"""Integrated SPEM maps of the two files (ARPES viewer loader), saved as npz + quick-look png."""
import sys
from pathlib import Path

import numpy as np

import os

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, os.environ.get("ARPES_VIEWER", r"D:\Codes\ARPES-viewer-main"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from arpes_viewer.loader.registry import load

OUT = Path(__file__).parent / "spem"
OUT.mkdir(exist_ok=True)
files = {"before": "Real_2026-11-14_18-08-53.nxs", "after": "Real_2026-11-14_18-16-15.nxs"}
fig, axs = plt.subplots(2, 4, figsize=(16, 8))
for row, (tag, name) in enumerate(files.items()):
    s = load(str(ROOT / "Photos" / name))
    print(tag, s.info.get("_group"), s.info.get("_other_entries"))
    cube = np.asarray(s.value4d[:, :, :, :], float)  # (y, x, k, E)
    x, y, k, e = (np.asarray(v) for v in (s.x, s.y, s.k, s.z))
    total = cube.sum(axis=(2, 3))
    spec = cube.sum(axis=(0, 1, 2))
    # energy windows: deep (low KE) vs near E_F (high KE)
    lo, hi = e < e.min() + 3, e > e.max() - 3
    near_ef = cube[..., hi].sum(axis=(2, 3))
    deep = cube[..., lo].sum(axis=(2, 3))
    np.savez(OUT / f"{tag}.npz", x=x, y=y, k=k, e=e, total=total, near_ef=near_ef, deep=deep, spec=spec,
             ek=cube.sum(axis=(0, 1)))
    s.close()
    for col, (t, img) in enumerate([("total", total), ("near E_F (last 3 eV KE)", near_ef), ("deep (first 3 eV KE)", deep),
                                    ("ratio near/deep", near_ef / np.maximum(deep, 1))]):
        ax = axs[row, col]
        ax.imshow(img, origin="lower", extent=(x[0], x[-1], y[0], y[-1]), cmap="viridis")
        ax.set_title(f"{tag}: {t}", fontsize=9)
        ax.set_xlabel("PIX (um)")
        ax.set_ylabel("PIY (um)")
fig.tight_layout()
fig.savefig(OUT / "quicklook.png", dpi=90)
fig2, ax = plt.subplots(figsize=(6, 3))
for tag in files:
    d = np.load(OUT / f"{tag}.npz")
    ax.plot(d["e"], d["spec"] / d["spec"].max(), label=tag)
ax.legend()
ax.set_xlabel("KE (eV)")
fig2.tight_layout()
fig2.savefig(OUT / "spectra.png", dpi=90)
print("x axis", x[:3], "y axis", y[:3])
