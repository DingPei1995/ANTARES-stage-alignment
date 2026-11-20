"""Edge analysis of the fine PIX x ZPS scans (ZPS step 0.01 / 0.02, clear edge).

Per ZPS row (only points really measured: finite timestamps): position of the steepest edge of the expected sign
(max of the gradient, parabola-refined) and its sharpness = max gradient / step height (1/um). Focus = vertex of a
parabola through sharpness(ZPS) around its maximum; edge PIX at focus from a local linear fit of position(ZPS)."""
import json
from pathlib import Path

import h5py
import matplotlib
import numpy as np
from scipy.ndimage import gaussian_filter1d

matplotlib.use("Agg")
import matplotlib.pyplot as plt

D = Path(r"D:\Codes\ANTARES-stage-alignment-main\CavData")
OUT = Path(__file__).parent
# tag: (PIX window, edge sign along +PIX, edge label)
SCANS = {
    "11-00-33": ((150, 170), -1, "A stripe right edge"),
    "11-03-42": ((155, 180), -1, "A stripe right edge"),
    "10-38-38": ((95, 130), -1, "other area (ST -3.40, SZ 36.19)"),
    "13-23-52": ((115, 150), +1, "B stripe left edge"),
    "14-13-13": ((110, 160), +1, "B stripe left edge"),
    "14-23-15": ((110, 160), +1, "B stripe left edge"),
    "14-41-25": ((110, 160), +1, "B stripe left edge"),
    "13-37-04": ((125, 160), +1, "B stripe left edge"),
    "13-01-51": ((115, 150), +1, "B stripe left edge"),
    "13-15-14": ((115, 150), +1, "B stripe left edge"),
    "13-43-52": ((120, 160), +1, "B stripe left edge"),
    "13-54-20": ((110, 160), +1, "B stripe left edge"),
    "12-03-50": ((95, 126), +1, "C head left edge"),
    "12-08-46": ((90, 126), +1, "C head left edge"),
    "15-26-49": ((150, 185), +1, "C head left edge"),
    "15-33-36": ((150, 170), +1, "C head left edge"),
    "15-06-02": ((60, 86), +1, "D SRn 140 stripe left edge"),
}


def motors(f, e):
    g = lambda p: float(np.asarray(f[f"{e}/ANTARES/{p}"][()]).reshape(-1)[0])  # noqa: E731
    out = {m: g(f"i12-m-cx1-ex-sample-mt_{m}/position") for m in ("st", "sn", "sz", "srn", "srz")}
    out["piy"] = g("PI/PI_Y")
    return out


def read(tag):
    with h5py.File(D / f"Cav_2026-11-15_{tag}.nxs", "r") as f:
        e = [k for k in f if "scan_data" in f[k]][0]
        sd = f[e]["scan_data"]
        img = np.asarray(sd["data_12"][()], float).sum(axis=(2, 3))
        ts = np.asarray(sd["sensors_rel_timestamps"][()], float)
        zps = np.asarray(sd["actuator_2_1"][()], float)
        tx = np.asarray(sd["trajectory_1_1"][()], float)
        m = motors(f, e)
    ok = np.isfinite(ts).all(axis=1) & np.isfinite(zps)
    return img[ok], zps[ok], tx, m


def edge_of_row(x, prof, sign):
    p = gaussian_filter1d(prof, 0.7) * sign
    g = np.gradient(p, x)
    k = int(np.argmax(g))
    k = min(max(k, 1), len(x) - 2)
    a, b, c = g[k - 1], g[k], g[k + 1]
    den = a - 2 * b + c
    dx = 0.5 * (a - c) / den if den != 0 else 0.0
    dx = float(np.clip(dx, -1, 1))
    pos = x[k] + dx * (x[1] - x[0])
    height = np.percentile(p, 90) - np.percentile(p, 10)
    return pos, b / height if height > 0 else 0.0


def analyse(tag):
    (lo, hi), sign, label = SCANS[tag]
    img, zps, x, m = read(tag)
    sel = (x >= lo) & (x <= hi)
    xs = x[sel]
    rows = np.array([(z, *edge_of_row(xs, prof, sign)) for z, prof in zip(zps, img[:, sel])])
    z, pos, sh = rows.T
    order = np.argsort(z)
    z, pos, sh = z[order], pos[order], sh[order]
    kmax = int(np.argmax(sh))
    top = sh > 0.6 * sh.max()
    flag = ""
    if top.sum() >= 3:
        c = np.polyfit(z[top], sh[top], 2)
        zf = -c[1] / (2 * c[0]) if c[0] < 0 else z[kmax]
        if not (z[top].min() <= zf <= z[top].max()):
            zf = z[kmax]
    else:
        c, zf = None, z[kmax]
    if kmax <= 1 or kmax >= len(z) - 2:
        flag = "sharpest row at the end of the ZPS range"
    near = np.abs(z - zf) <= 0.045
    if near.sum() >= 3:
        cx = np.polyfit(z[near], pos[near], 1)
    else:
        cx = np.array([0.0, pos[kmax]])
    pf = float(np.polyval(cx, zf))
    scat = float(np.std(pos[near] - np.polyval(cx, z[near]))) if near.sum() >= 3 else float("nan")
    return dict(tag=tag, label=label, **m, zps_focus=float(zf), pix_edge=pf, slope_um_per_mm=float(cx[0]),
                sharp_max=float(sh.max()), edge_scatter_um=scat, flag=flag, z=z.tolist(), pos=pos.tolist(),
                sharp=sh.tolist(), zrange=[float(z.min()), float(z.max())]), (img, zps, x, c)


if __name__ == "__main__":
    res = []
    fig, axs = plt.subplots(len(SCANS), 3, figsize=(12, 2.4 * len(SCANS)))
    for row, tag in zip(axs, SCANS):
        r, (img, zps, x, c) = analyse(tag)
        res.append(r)
        a0, a1, a2 = row
        a0.pcolormesh(x, zps, img, shading="nearest", cmap="gray")
        a0.plot(r["pos"], r["z"], "r.", ms=3)
        a0.axhline(r["zps_focus"], color="c", lw=1)
        a0.set_title(f"{tag} {r['label']} SRz {r['srz']:.0f} SN {r['sn']:.3f} PIY {r['piy']:.0f}", fontsize=8)
        a1.plot(r["z"], r["sharp"], "o", ms=3)
        if c is not None:
            zz = np.linspace(min(r["z"]), max(r["z"]), 60)
            a1.plot(zz, np.polyval(c, zz), "-")
        a1.axvline(r["zps_focus"], color="c")
        a1.set_title(f"focus ZPS {r['zps_focus']:.3f} {r['flag']}", fontsize=8)
        a2.plot(r["z"], r["pos"], "o", ms=3)
        a2.axvline(r["zps_focus"], color="c")
        a2.set_title(f"edge PIX at focus {r['pix_edge']:.1f}, {r['slope_um_per_mm']:.0f} um/mm", fontsize=8)
        print(f"{tag} {r['label'][:22]:22s} SRn {r['srn']:.0f} SRz {r['srz']:6.1f} SN {r['sn']:7.4f} ST {r['st']:8.4f} "
              f"SZ {r['sz']:.3f} PIY {r['piy']:4.0f} | ZPS {r['zrange'][0]:.2f}-{r['zrange'][1]:.2f} focus "
              f"{r['zps_focus']:.3f} edge PIX {r['pix_edge']:6.1f} (+-{r['edge_scatter_um']:.1f}) "
              f"{r['slope_um_per_mm']:5.0f} um/mm {r['flag']}")
    fig.tight_layout()
    fig.savefig(OUT / "cav_edges.png", dpi=60)
    (OUT / "cav_edges.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
