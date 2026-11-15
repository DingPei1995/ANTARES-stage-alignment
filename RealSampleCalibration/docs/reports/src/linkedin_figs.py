"""Two figures for a public post: the SPEM maps before / after a predicted rotation, sample photos pixelated and
file names / sample names left out. Data: spem/*.npz written by spem_maps.py and cav_maps.py."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

HERE = Path(__file__).parent
D = HERE / "spem"
ROOT = HERE.parents[3]
OUT = ROOT / "linkedin"
OUT.mkdir(exist_ok=True)
FOOT = "ANTARES (SOLEIL) · SPEM maps 300 × 300 µm, 10 µm steps, hν = 95 eV · cyan cross: piezo centre, on the beam"


def hide_stamps(img: Image.Image) -> Image.Image:
    """Paint over the date and objective stamps of the microscope photo with the substrate colour around them."""
    from PIL import ImageDraw

    img = img.convert("RGB").copy()
    arr = np.asarray(img)
    w, h = img.size
    draw = ImageDraw.Draw(img)
    for box in ((10, 25, 215, 85), (10, h - 100, 315, h - 35)):  # date (top left), objective (bottom left)
        x0, y0, x1, y1 = box
        ring = np.concatenate([arr[y1:y1 + 15, x0:x1].reshape(-1, 3), arr[y0:y1, x1:x1 + 15].reshape(-1, 3)])
        draw.rectangle(box, fill=tuple(int(c) for c in np.median(ring, axis=0)))
    return img


def num(v: float, n: int) -> str:
    return f"{v:.{n}f}".replace("-", "−")


def draw_map(ax, d, title):
    x, y, img = d["x"], d["y"], d["total"].astype(float)
    st = (x[1] - x[0]) / 2
    lo, hi = np.percentile(img, [1, 99.5])
    ax.imshow(img, origin="lower", extent=(x[0] - st, x[-1] + st, y[0] - st, y[-1] + st), cmap="magma",
              vmin=lo, vmax=hi)
    ax.invert_xaxis()  # as ARPES viewer draws ANTARES maps
    ax.plot(150, 150, "+", color="cyan", ms=16, mew=1.8)
    ax.set_title(title, fontsize=11)
    ax.set_xlabel("PIX (µm)", fontsize=9)
    ax.set_ylabel("PIY (µm)", fontsize=9)
    ax.tick_params(labelsize=8)


# -- 1: device on Si, rotation SRn 120 / SRz 0 -> SRn 150 / SRz -10 ------------------------------------------
a, b = np.load(D / "before.npz"), np.load(D / "after.npz")
sh = np.load(D / "shift.npz")
res = float(np.hypot(float(sh["d_pix"]) - float(sh["du"]), float(sh["d_piy"]) + float(sh["dv"])))
plate = Image.open(ROOT / "Photos" / "20261111_103232.JPG").crop((4150, 2000, 5250, 2900))
micro = hide_stamps(Image.open(ROOT / "Photos" / "20261113_165443.jpg"))
fig, axs = plt.subplots(2, 2, figsize=(10, 9.4))
for ax, im, t in ((axs[0, 0], plate, "1. Photo of the sample plate (the input)"),
                  (axs[0, 1], micro, "2. Microscope photo of the device")):
    ax.imshow(im)
    ax.set_title(t, fontsize=11)
    ax.set_xticks([])
    ax.set_yticks([])
draw_map(axs[1, 0], a, "Found: SRn 120°, SRz 0°")
draw_map(axs[1, 1], b, "Predicted: SRn 150°, SRz −10°")
fig.suptitle(f"Rotate, go to the predicted ST / SZ / SN, scan once: same spot within {res:.0f} µm", fontsize=13)
fig.text(0.5, 0.01, FOOT, ha="center", fontsize=8, color="#555555")
fig.tight_layout(rect=(0, 0.025, 1, 0.97))
fig.savefig(OUT / "1_device_rotation_SRn150_SRz-10.png", dpi=180)
plt.close(fig)

# -- 2: second sample, SRz 0 -> -26.9 with SN corrected ----------------------------------------------------
a, b = np.load(D / "cav_before.npz"), np.load(D / "cav_after.npz")
sh = np.load(D / "cav_shift.npz")
res = float(np.hypot(float(sh["d_pix"]) - float(sh["exp_pix"]), float(sh["d_piy"]) - float(sh["exp_piy"])))
fig, axs = plt.subplots(1, 2, figsize=(10, 5.0))
draw_map(axs[0], a, f"Found: SRn 120°, SRz 0°, SN {num(float(a['m_sn']), 2)}")
draw_map(axs[1], b, f"Predicted: SRn 120°, SRz {num(float(b['m_srz']), 1)}°, SN {num(float(b['m_sn']), 2)}")
fig.suptitle(f"SRz −27° with SN corrected back to the analyzer focus: same spot within {res:.0f} µm", fontsize=13)
fig.text(0.5, 0.01, FOOT, ha="center", fontsize=8, color="#555555")
fig.tight_layout(rect=(0, 0.04, 1, 0.95))
fig.savefig(OUT / "2_second_sample_SRz-27_SN_corrected.png", dpi=180)
plt.close(fig)
print(OUT)
