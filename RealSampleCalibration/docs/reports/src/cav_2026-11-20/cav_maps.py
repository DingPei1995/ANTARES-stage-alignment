"""2D PIX x PIY maps with the PIY / PIX range of the line scans of the same set drawn on them."""
from pathlib import Path

import h5py
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

D = Path(r"D:\Codes\ANTARES-stage-alignment-main\CavData")
OUT = Path(__file__).parent
# map -> line scans (same motors)
SETS = {"10-50-42": ["11-00-33", "11-03-42"], "10-43-58": ["10-38-38"], "11-53-17": ["12-03-50", "12-08-46"],
        "11-50-21": [], "12-45-15": [], "12-55-08": ["13-23-52"], "12-58-46": ["13-01-51", "13-15-14"],
        "13-34-32": ["13-37-04"], "13-42-35": ["13-43-52"], "13-52-09": ["13-54-20"], "14-11-18": ["14-13-13"],
        "11-39-04": [], "14-54-41": ["15-00-22", "15-06-02"], "15-17-30": ["15-26-49", "15-33-36"],
        "15-39-24": [], "15-41-02": [], "15-59-46": [], "10-47-06": []}


def motors(f, e):
    g = lambda p: float(np.asarray(f[f"{e}/ANTARES/{p}"][()]).reshape(-1)[0])  # noqa: E731
    out = {m: g(f"i12-m-cx1-ex-sample-mt_{m}/position") for m in ("st", "sn", "sz", "srn", "srz")}
    out["pix"], out["piy"] = g("PI/PI_X"), g("PI/PI_Y")
    out["zps"] = g("i12-m-cx1-op-zp-mt_zs/position")
    return out


def read_map(tag):
    with h5py.File(D / f"Cav_2026-11-15_{tag}.nxs", "r") as f:
        e = [k for k in f if "scan_data" in f[k]][0]
        sd = f[e]["scan_data"]
        img = np.asarray(sd["data_12"][()], float).sum(axis=(2, 3))
        tx = np.asarray(sd["trajectory_1_1"][()], float)
        ty = np.asarray(sd["trajectory_2_1"][()], float)
        m = motors(f, e)
    return img, tx, ty, m


if __name__ == "__main__":
    fig, axs = plt.subplots(4, 5, figsize=(21, 17))
    for ax, (mp, lines) in zip(axs.flat, SETS.items()):
        img, tx, ty, m = read_map(mp)
        img = np.where(img > 0, img, np.nan)
        ax.pcolormesh(tx, ty, img, shading="nearest", cmap="gray")
        ax.set_aspect("equal")
        for ln in lines:
            with h5py.File(D / f"Cav_2026-11-15_{ln}.nxs", "r") as f:
                e = [k for k in f if "scan_data" in f[k]][0]
                lm = motors(f, e)
                lx = np.asarray(f[e]["scan_data"]["trajectory_1_1"][()], float)
            same = all(abs(lm[k] - m[k]) < 2e-3 for k in ("st", "sz", "sn"))
            ax.plot([lx[0], lx[-1]], [lm["piy"]] * 2, "-", color="red" if same else "orange", lw=2)
            ax.text(lx[-1], lm["piy"], ln, color="red", fontsize=7)
        ax.set_title(f"{mp} SRn {m['srn']:.0f} SRz {m['srz']:.0f} SN {m['sn']:.3f}\nST {m['st']:.4f} SZ {m['sz']:.3f} "
                     f"ZPS {m['zps']:.3f}", fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "cav_maps.png", dpi=65)
