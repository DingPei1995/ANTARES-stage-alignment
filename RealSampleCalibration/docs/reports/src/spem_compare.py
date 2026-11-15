"""Figure: device photos vs the two SPEM maps, maps drawn as ARPES viewer draws them (PIX large -> small)."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

D = Path(__file__).parent / "spem"
ROOT = Path(__file__).resolve().parents[4]
a, b = np.load(D / "before.npz"), np.load(D / "after.npz")
sh = np.load(D / "shift.npz")

plate = Image.open(ROOT / "Photos" / "20261111_103232.JPG")
micro = Image.open(ROOT / "Photos" / "20261113_165443.jpg")
fig, axs = plt.subplots(1, 4, figsize=(15, 4.1), gridspec_kw={"width_ratios": [1, 1.33, 1, 1]})
x0, y0, x1, y1 = 4150, 2000, 5250, 2900  # plate photo crop around the device (px, 354 px/mm)
axs[0].imshow(plate.crop((x0, y0, x1, y1)), extent=(x0, x1, y1, y0))
axs[0].set_title("Plate photo (front view, 354 px/mm)", fontsize=9)
axs[1].imshow(micro)
axs[1].set_title("Microscope photo of the device", fontsize=9)
for ax, d, t in ((axs[2], a, "SPEM 18-08-53: SRn 120 / SRz 0"), (axs[3], b, "SPEM 18-16-15: SRn 150 / SRz -10")):
    x, y = d["x"], d["y"]
    ax.imshow(d["total"], origin="lower", extent=(x[0] - 5, x[-1] + 5, y[0] - 5, y[-1] + 5), cmap="magma")
    ax.invert_xaxis()  # as ARPES viewer draws ANTARES maps (Spatial.invert_x): PIX runs large -> small
    ax.plot(150, 150, "+", color="cyan", ms=14, mew=1.5)
    ax.set_title(t, fontsize=9)
    ax.set_xlabel("PIX (µm)", fontsize=8)
    ax.set_ylabel("PIY (µm)", fontsize=8)
for ax in axs:
    ax.tick_params(labelsize=7)
fig.tight_layout()
fig.savefig(D / "compare.png", dpi=110)
print(D / "compare.png")
