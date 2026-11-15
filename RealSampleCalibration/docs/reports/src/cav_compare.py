"""Figure: the two Cav SPEM maps (as ARPES viewer draws ANTARES maps, PIX large -> small) and their spectra."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import ndimage

D = Path(__file__).parent / "spem"
a, b = np.load(D / "cav_before.npz"), np.load(D / "cav_after.npz")
sh = np.load(D / "cav_shift.npz")

fig, axs = plt.subplots(1, 3, figsize=(13.5, 4.0), gridspec_kw={"width_ratios": [1, 1, 1.25]})
titles = (f"SPEM 19-48-34: SRn 120 / SRz 0, SN {float(a['m_sn']):.2f}",
          f"SPEM 20-06-03: SRn 120 / SRz {float(b['m_srz']):.1f}, SN {float(b['m_sn']):.2f}")
lo = min(np.percentile(d["total"], 1) for d in (a, b))
hi = max(np.percentile(d["total"], 99.5) for d in (a, b))
for ax, d, t in zip(axs[:2], (a, b), titles):
    x, y = d["x"], d["y"]
    st = (x[1] - x[0]) / 2
    ax.imshow(d["total"], origin="lower", extent=(x[0] - st, x[-1] + st, y[0] - st, y[-1] + st), cmap="magma",
              vmin=lo, vmax=hi)
    ax.invert_xaxis()  # as ARPES viewer draws ANTARES maps (Spatial.invert_x): PIX runs large -> small
    ax.plot(150, 150, "+", color="cyan", ms=14, mew=1.5)
    ax.set_title(t, fontsize=9)
    ax.set_xlabel("PIX (µm)", fontsize=8)
    ax.set_ylabel("PIY (µm)", fontsize=8)
ax = axs[2]
ratio = float(b["total"].sum() / a["total"].sum())
for d, lab, col in ((a, "19-48-34 (SRz 0)", "#1f77b4"), (b, f"20-06-03 (SRz {float(b['m_srz']):.1f})", "#d62728")):
    sp = ndimage.uniform_filter1d(d["spec"].astype(float), 9)
    ax.plot(d["e"], sp / sp.max(), color=col, lw=1.2, label=lab)
ax.set_title(f"Spectrum of the whole map (normalised; total intensity ratio {ratio:.2f})", fontsize=9)
ax.set_xlabel("KE (eV)", fontsize=8)
ax.set_ylabel("intensity (norm.)", fontsize=8)
ax.legend(fontsize=8)
for ax in axs:
    ax.tick_params(labelsize=7)
fig.tight_layout()
fig.savefig(D / "cav_compare.png", dpi=110)
print(D / "cav_compare.png", "corr", float(sh["corr"]))
