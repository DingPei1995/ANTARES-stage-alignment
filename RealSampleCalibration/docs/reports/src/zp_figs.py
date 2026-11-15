"""Figures of the 2026-11-15 zone-plate report (report_figs/zp_*.png) and the numbers they show (spem/zp_numbers.npz).

Everything is computed from the measured values listed below (beamline notes of 2026-11-15) with the stage model of
QuickAlignment; nothing is fitted here except the model-free SRz-axis inversion of section 5."""
import json
import sys
from dataclasses import replace
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))
from quickalignment.core.calibration import CalibrationStore  # noqa: E402
from quickalignment.core.geometry import PLATES  # noqa: E402
from quickalignment.core.stage import B, MotorPositions as M, StageModel, slide_to_sn  # noqa: E402

HERE = Path(__file__).parent
FIGS, SPEM = HERE / "report_figs", HERE / "spem"
FIGS.mkdir(exist_ok=True)
plate = PLATES["gating"]
recs = {r.path.name: r for r in CalibrationStore(ROOT / "configs").records()}
CAP_OLD = recs["calibration_2026-11-14_173743_capillary.json"]
ZP_NEW = recs["calibration_2026-11-15_151356_zone_plate.json"]
ZPF = 53.7502                      # ZPS in focus at the reference (taken as the analyzer focus)
OLD = replace(CAP_OLD.config, st0=-0.8127, sz0=41.2059)  # capillary mechanics + zone-plate spot (set 1)
NEW = ZP_NEW.config
M1 = M(st=-3.4982, sz=36.538, sn=-0.05173, srn=120.0006, srz=0.0005, pix=138, piy=142)

# ------------------------------------------------------------------ measured values (beamline notes 2026-11-15)
SLIDES = [  # SRz 0, SN with ST compensating (feature slides along the beam): SN, ST, ZPS in focus
    (-1.856, -1.6939, 51.16), (0.48, -4.028, 54.46), (0.798, -4.3487, 54.90), (1.151, -4.70, 55.40)]
SRZ_SERIES = [  # SRn 120, SN kept: SRz, ST, SZ, SN, ZPS in focus
    (-5, -4.066, 36.54, -0.05, 54.10), (-10, -4.6255, 36.539, -0.048, 54.53),
    (-15, -5.1703, 36.54, -0.05, 54.96), (-20, -5.6966, 36.54, -0.05, 55.46)]
SN_MOVED = [  # SRn 120 / SRz -25 with SN moved: ST, SZ, SN, PIX, PIY, ZPS, label
    (-4.3935, 36.548, -1.856, 110, 150, 53.17, "first (capillary axes)"),
    (-4.7228, 36.54, -1.578, 161, 158, 53.61, "final (new axes)")]
CHECK = (140, -15, -2.9839, 35.886, -0.052, 54.33)  # SRn, SRz, ST, SZ, SN, ZPS


def point(model):
    return model.lab_to_plate(M1, np.zeros(3))


def along(model, m):
    return float(model.plate_to_lab(m, *point(model))[1])


num = {}
# --- ZPS against the stage slide (SRz 0)
slide_mm, slide_zps = [], []
for sn, st, zps in SLIDES:
    m = replace(M1, sn=sn, st=st)
    slide_mm.append(along(StageModel(NEW, plate), m))
    slide_zps.append(zps - ZPF)
num["slide_mm"], num["slide_zps"] = slide_mm, slide_zps

fig, ax = plt.subplots(figsize=(5.2, 3.4))
xs = np.linspace(-2.8, 2.0, 2)
ax.plot(xs, xs, color="grey", lw=1, ls="--", label="1:1")
ax.plot(slide_mm, slide_zps, "o", color="#1f77b4", label="measured (SRz 0, SN + ST slide)")
for x, y in zip(slide_mm, slide_zps):
    ax.annotate(f"{y / x:.3f}", (x, y), textcoords="offset points", xytext=(6, -10), fontsize=7)
ax.set_xlabel("feature moved along the beam by the stage (mm, model)", fontsize=8)
ax.set_ylabel("ZPS change to refocus (mm)", fontsize=8)
ax.tick_params(labelsize=7)
ax.legend(fontsize=7)
ax.set_title("ZPS against a pure stage slide: ~1:1 (ratios labelled)", fontsize=9)
fig.tight_layout()
fig.savefig(FIGS / "zp_zps_linearity.png", dpi=170)
plt.close(fig)

# --- SRz series: measured focus against the old and new axis
srz = np.array([s[0] for s in SRZ_SERIES])
meas = np.array([s[4] for s in SRZ_SERIES])
pred = {}
for name, cfg in (("old", OLD), ("new", NEW)):
    mod = StageModel(cfg, plate)
    pred[name] = np.array([ZPF + along(mod, M(st=s[1], sz=s[2], sn=s[3], srn=120, srz=s[0], pix=138, piy=142))
                           for s in SRZ_SERIES])
num["srz"], num["srz_meas"], num["srz_old"], num["srz_new"] = srz, meas, pred["old"], pred["new"]
fig, ax = plt.subplots(figsize=(5.6, 3.5))
ax.plot([0, *srz], [ZPF, *meas], "o", color="black", label="measured ZPS (SN kept)")
ax.plot([0, *srz], [ZPF, *pred["old"]], "s--", mfc="none", color="#d62728", label="capillary axes (2026-11-14)")
ax.plot([0, *srz], [ZPF, *pred["new"]], "^-", mfc="none", color="#2ca02c", label="new SRz axis (2026-11-15)")
ax.plot([CHECK[1]], [CHECK[5]], "*", ms=11, color="#9467bd", label="check SRn 140 / SRz -15 (measured)")
mo, mn = StageModel(OLD, plate), StageModel(NEW, plate)
mc = M(st=CHECK[2], sz=CHECK[3], sn=CHECK[4], srn=CHECK[0], srz=CHECK[1], pix=138, piy=142)
num["check_old"], num["check_new"] = ZPF + along(mo, mc), ZPF + along(mn, mc)
ax.plot([CHECK[1]] * 2, [num["check_old"], num["check_new"]], "x", color="#9467bd", ms=7,
        label=f"check predicted: old {num['check_old']:.2f} / new {num['check_new']:.2f}")
ax.invert_xaxis()
ax.set_xlabel("SRz (deg), SRn 120", fontsize=8)
ax.set_ylabel("ZPS in focus", fontsize=8)
ax.tick_params(labelsize=7)
ax.legend(fontsize=7)
ax.set_title("Focus after a pure SRz rotation (ST brings the point back on the beam)", fontsize=9)
fig.tight_layout()
fig.savefig(FIGS / "zp_srz_focus.png", dpi=170)
plt.close(fig)

# --- model-free inversion of the SRz series (point relative to a vertical SRz axis, lab x across / y along)
T = np.array([1, -1]) / np.sqrt(2)
A, b = [], []
for a_, st, sz, sn, zps in SRZ_SERIES:
    s, y = st - M1.st, (zps - ZPF)
    D = np.array([0.0, y]) - s * T
    phi = np.radians(-a_)
    R = np.array([[np.cos(phi), -np.sin(phi)], [np.sin(phi), np.cos(phi)]])
    A.append(R - np.eye(2))
    b.append(D)
r_fit, *_ = np.linalg.lstsq(np.vstack(A), np.concatenate(b), rcond=None)
res = (np.vstack(A) @ r_fit - np.concatenate(b)).reshape(-1, 2)
axis_old = StageModel(OLD, plate)._translation(M1) + B @ StageModel(OLD, plate)._srz_axis_local()
num["r_fit"], num["r_old"], num["r_res_um"] = r_fit, -axis_old[:2], res * 1000

# --- SRz -25 with SN moved
rows = []
for st, sz, sn, pix, piy, zps, label in SN_MOVED:
    m = M(st=st, sz=sz, sn=sn, srn=120, srz=-25, pix=pix, piy=piy)
    for name, cfg in (("old", OLD), ("new", NEW)):
        mod = StageModel(cfg, plate)
        p = point(mod)
        lab = mod.plate_to_lab(m, *p)
        # PIX / PIY where the model puts the point on the beam at these motors
        from scipy.optimize import fsolve
        q = fsolve(lambda v: [mod.plate_to_lab(replace(m, pix=v[0], piy=v[1]), *p)[i] for i in (0, 2)], [pix, piy])
        rows.append({"label": label, "axes": name, "pix_model": float(q[0]), "piy_model": float(q[1]),
                     "pix": pix, "piy": piy, "zps_model": ZPF + float(lab[1]), "zps": zps})
num["sn_moved"] = rows

# --- yesterday's capillary sets with the new mechanics
cap_rows = []
for st, sz, srn, srz_, cps in ((-2.50, 39.80, 140, 0, 61.45), (-3.76, 40.24, 120, -10, 62.05),
                               (-3.12, 40.80, 100, 0, None), (-3.54, 40.78, 100, -5, 61.76)):
    out = {"srn": srn, "srz": srz_}
    for name, cfg in (("old", CAP_OLD.config), ("new", recs["calibration_2026-11-15_151356_capillary.json"].config)):
        lab = StageModel(cfg, plate).plate_to_lab(M(st=st, sz=sz, sn=-0.30, srn=srn, srz=srz_), 1.284, 0.775, 5.5)
        out[name] = {"x": float(lab[0]), "z": float(lab[2]), "along": float(lab[1])}
    out["cps"] = None if cps is None else cps - 61.45
    cap_rows.append(out)
num["cap_rows"] = cap_rows

# --- the two SPEM maps with the tracked point
fig, axs = plt.subplots(1, 2, figsize=(9.2, 4.0), gridspec_kw={"width_ratios": [1, 1.1]})
for ax, tag, mark, title in ((axs[0], "zp_srn120", (138, 142), "SRn 120 / SRz 0 (11:13:55)"),
                             (axs[1], "zp_srn140", (132, 84), "SRn 140 / SRz 0 (11:33:22)")):
    d = np.load(SPEM / f"{tag}.npz")
    x, y, img = d["x"], d["y"], d["total"]
    step = float(x[1] - x[0])
    ax.imshow(img, origin="lower", cmap="gray", extent=(x[0] - step / 2, x[-1] + step / 2, y[0] - step / 2,
                                                        y[-1] + step / 2), aspect="equal")
    ax.plot(*mark, "o", mfc="none", mec="red", ms=12, mew=1.8)
    ax.annotate(f"PIX {mark[0]}, PIY {mark[1]}", mark, textcoords="offset points", xytext=(10, 10), color="red",
                fontsize=8)
    ax.set_title(title + f"\nST {float(d['m_st']):.4f}, SZ {float(d['m_sz']):.3f}, SN {float(d['m_sn']):.4f}, "
                 f"ZPS {float(d['m_zps']):.2f}", fontsize=8)
    ax.set_xlabel("PIX (µm)", fontsize=8)
    ax.set_ylabel("PIY (µm)", fontsize=8)
    ax.tick_params(labelsize=7)
fig.tight_layout()
fig.savefig(FIGS / "zp_maps.png", dpi=170)
plt.close(fig)


def jsonable(v):
    if isinstance(v, np.ndarray):
        return v.tolist()
    if isinstance(v, (list, tuple)):
        return [jsonable(x) for x in v]
    if isinstance(v, dict):
        return {k: jsonable(x) for k, x in v.items()}
    return float(v) if isinstance(v, (np.floating,)) else v


(SPEM / "zp_numbers.json").write_text(json.dumps(jsonable(num), indent=1), encoding="utf-8")
print(json.dumps(jsonable(num), indent=1)[:3000])
