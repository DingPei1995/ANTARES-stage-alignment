"""Figures and numbers of the "How the calibration is computed" section of RealSampleCalibration/README.md.

Run from anywhere: python RealSampleCalibration/docs/calculation/make_figures.py
Writes RealSampleCalibration/docs/images/calculation/*.png and prints every number quoted in the README.
Data: the capillary calibration of 2026-11-14 (configs/calibration_2026-11-14_173743_capillary.json, 5 sets) and the
zone-plate SRz series of 2026-11-15 (configs/calibration_2026-11-15_151356_zone_plate.json)."""
import sys
from dataclasses import replace
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from quickalignment.core.calibration import CalibrationStore  # noqa: E402
from quickalignment.core.geometry import PLATES  # noqa: E402
from quickalignment.core.stage import B, MotorPositions as M, StageModel  # noqa: E402
from quickalignment.realsample.fit import (  # noqa: E402
    PARAM_LABELS, MeasurementSet, _residual_vector, fit_real_sample_calibration, measurement_sigmas, on_beam)

OUT = ROOT / "RealSampleCalibration" / "docs" / "images" / "calculation"
OUT.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({"font.size": 8, "axes.titlesize": 9, "axes.formatter.use_locale": False})
C = {"st": "#1f77b4", "sz": "#ff7f0e", "sn": "#9467bd", "opt": "#2ca02c", "red": "#d62728", "grey": "#7f7f7f"}

recs = {r.path.name: r for r in CalibrationStore(ROOT / "configs").records()}
CAP = recs["calibration_2026-11-14_173743_capillary.json"]
OLD_CAP = recs["calibration_2026-10-24_235500_capillary.json"]
ZP = recs["calibration_2026-11-15_151356_zone_plate.json"]
plate = PLATES["gating"]
UVW = tuple(CAP.check["reference_uvw"])  # (1.284, 0.775, 5.5): feature x, y and w = 5.0 + H
sets = [MeasurementSet(**s) for s in CAP.check["sets"]]
s1, s2, s3 = sets[:3]
T2 = np.array([1.0, -1.0]) / np.sqrt(2)
N2 = np.array([1.0, 1.0]) / np.sqrt(2)


def rot(deg):
    a = np.radians(deg)
    return np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])


def save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / name, dpi=150)
    plt.close(fig)
    print("wrote", name)


# ============================================================ step by step, closed form (2026-11-14 capillary)
u, v, w = UVW
st0 = s1.st + u
sz0 = s1.sz + v
sn_f = s1.sn - w + 5.0
F = s1.optic
print(f"step 1: ST0 = {st0:.4f}  SZ0 = {sz0:.4f}  SN_f = {sn_f:.4f}  F = {F:.4f}")

theta = s2.srn - 120.0
q = np.array([u, v])
q2 = q - np.array([s2.st - s1.st, s2.sz - s1.sz])
R = rot(theta)
c_srn = np.linalg.solve(np.eye(2) - R, q2 - R @ q)
amp = 1 / (2 * np.sin(np.radians(theta) / 2))
print(f"step 2: theta {theta}  q' = {q2}  SRn axis = {c_srn}  error amplification 1/(2 sin(theta/2)) = {amp:.2f}")

phi = -s3.srz
d_st, d_opt = s3.st - s1.st, s3.optic - s1.optic
dx = -d_st / np.sqrt(2)
dy = d_opt - dx
Rz = rot(phi)
r = np.linalg.solve(Rz - np.eye(2), np.array([dx, dy]))  # feature - axis (lab x across, y along the beam)
A = -r  # axis position, feature at the origin
off_t = A @ T2 - (s1.st - st0)
off_n = A @ N2 - (s1.sn - sn_f)
# sensitivity of r to the readings
Minv = np.linalg.inv(Rz - np.eye(2))
J_meas = Minv @ np.array([[-1 / np.sqrt(2), 0.0], [1 / np.sqrt(2), 1.0]])  # d r / d(dST, dOpt)
print(f"step 3: phi {phi}  d = ({dx:.4f}, {dy:.4f})  feature-axis r = {r}  axis A = {A}")
print(f"        SRz offset ST = {off_t:.4f}  SRz offset SN = {off_n:.4f}")
print(f"        dr/d(dST, dOpt) =\n{J_meas}")
for so in (0.10, 0.02):
    cov = J_meas @ np.diag([0.02**2 * 2, so**2 * 2]) @ J_meas.T
    print(f"        sigma r (pos 0.02, optic {so}) = {np.sqrt(np.diag(cov))}")

# ============================================================ least-squares fits
fit_u = fit_real_sample_calibration(sets, plate, UVW, base=OLD_CAP.config, mode="full")
fit_w = fit_real_sample_calibration(sets, plate, UVW, base=OLD_CAP.config, mode="full",
                                     sigmas=measurement_sigmas("capillary"))
fit3 = fit_real_sample_calibration(sets[:3], plate, UVW, base=OLD_CAP.config, mode="full")
for name, f in (("unweighted 5 sets", fit_u), ("weighted 5 sets", fit_w), ("unweighted 3 sets", fit3)):
    print(f"\n{name}: dof {f.dof}  rms {f.rms * 1000:.1f} um  chi2/dof {f.chi2_dof}")
    for p in f.params:
        val = f.optic_focus if p == "optic_focus" else getattr(f.config, p)
        sg = f.sigma[p] if f.sigma else float("nan")
        print(f"   {PARAM_LABELS[p]:24s} {val:9.4f}  +- {sg:.4f}")
    print("   weakest", f.weakest)
m3 = StageModel(fit3.config, plate)
pred45 = []
for s in sets[3:]:
    p = on_beam(m3, UVW, s.srn, s.srz, s.sn, s.pix, s.piy, fit3.optic_focus)
    dev = (s.st - p[0], s.sz - p[1], None if s.optic is None else s.optic - p[2])
    pred45.append((s, p, dev))
    print(f"prediction from sets 1-3 for {s.name}: {p}  measured - predicted {dev}")

# ============================================================ figure 1: frames
fig, axs = plt.subplots(1, 2, figsize=(9.5, 4.3))
ax = axs[0]
ax.set_title("Top view (lab frame, at SRn 120 / SRz 0)")
ax.annotate("", (0, 4.2), (0, -4.2), arrowprops=dict(arrowstyle="->", color=C["red"], lw=2))
ax.text(0.15, 3.7, "beam +y", color=C["red"])
ax.plot(0, 0, "o", color="k")
ax.text(0.2, -0.45, "analyzer focus\n(origin)", fontsize=7)
ax.plot([-3.5 * T2[0], 3.5 * T2[0]], [-3.5 * T2[1], 3.5 * T2[1]], color="#bfa100", lw=4, solid_capstyle="butt")
ax.text(-2.6, 2.05, "plate surface", color="#8a7300", rotation=-45)
body = np.array([[-3.5, 3.5], [3.5, 3.5]]) * 0
poly = np.array([-3.5 * T2, 3.5 * T2, 3.5 * T2 + 1.6 * N2, -3.5 * T2 + 1.6 * N2])
ax.fill(poly[:, 0], poly[:, 1], color="#d9d9d9", zorder=0)
for vec, lab, col in ((T2, "+ST  t = (1,-1)/√2", C["st"]), (N2, "+SN  n = (1,1)/√2", C["sn"])):
    ax.annotate("", 2.4 * vec + np.array([2.2, -0.6]), np.array([2.2, -0.6]),
                arrowprops=dict(arrowstyle="->", color=col, lw=1.6))
    ax.text(*(2.5 * vec + np.array([2.25, -0.6])), lab, color=col, fontsize=7)
an = -3.1 * N2
ax.add_patch(Rectangle(an - [0.5, 0.5], 1.0, 1.0, angle=0, color=C["grey"], alpha=0.5))
ax.text(an[0] - 0.9, an[1] - 1.0, "analyzer (at −n)", fontsize=7)
ax.annotate("", (-0.9 * N2[0], -0.9 * N2[1]), (0, 0), arrowprops=dict(arrowstyle="->", color="k"))
ax.text(-1.55, -0.35, "+w", fontsize=7)
ax.plot(*(2.0 * N2 + 0.3 * T2), "kx", ms=8)
ax.text(*(2.0 * N2 + 0.3 * T2 + [0.15, 0.1]), "SRz axis (vertical)", fontsize=7)
ax.set_xlim(-4.3, 5.4)
ax.set_ylim(-4.3, 4.3)
ax.set_aspect("equal")
ax.set_xlabel("x (mm, across the beam)")
ax.set_ylabel("y (mm, along the beam)")
ax = axs[1]
ax.set_title("Front view (plate frame, gating plate, tab up)")
ax.add_patch(Rectangle((-9, -7.75), 18, 15.5, fc="#eeeeee", ec="k"))
ax.add_patch(Rectangle((-5.5, -2.75), 11, 10.5, fc="#f6e7a8", ec="#8a7300"))
ax.add_patch(Rectangle((-5.5, -8.75 + 1.0), 11, 6.0, fc="#cfd8e3", ec=C["grey"]))
ax.text(-5.2, 7.0, "sample area (riser)", fontsize=7, color="#8a7300")
ax.text(-5.2, -7.2, "contact block", fontsize=7, color="#555555")
ax.plot(u, v, "*", color=C["red"], ms=12)
ax.text(u + 0.4, v + 0.3, f"feature ({u}, {v}), H {w - 5.0:.1f}", color=C["red"], fontsize=7)
ax.plot(*c_srn, "x", color="k", ms=9, mew=2)
ax.text(c_srn[0] - 4.5, c_srn[1] - 1.2, "SRn axis (srn_axis_u, _v)", fontsize=7)
ang = np.linspace(0, np.radians(50), 30)
ax.plot(c_srn[0] + 3.2 * np.cos(ang + 0.6), c_srn[1] + 3.2 * np.sin(ang + 0.6), color="k", lw=0.8)
ax.annotate("", (c_srn[0] + 3.2 * np.cos(ang[-1] + 0.6), c_srn[1] + 3.2 * np.sin(ang[-1] + 0.6)),
            (c_srn[0] + 3.2 * np.cos(ang[-3] + 0.6), c_srn[1] + 3.2 * np.sin(ang[-3] + 0.6)),
            arrowprops=dict(arrowstyle="->"))
ax.text(1.0, 3.6, "SRn − 120 (CCW)", fontsize=7)
ax.annotate("", (3, -9.8), (0, -9.8), arrowprops=dict(arrowstyle="->", color=C["st"]), annotation_clip=False)
ax.text(3.2, -10.0, "+u  (= −ST)", fontsize=7, color=C["st"])
ax.annotate("", (-10.5, 3), (-10.5, 0), arrowprops=dict(arrowstyle="->", color=C["sz"]), annotation_clip=False)
ax.text(-11.6, 3.3, "+v (= −SZ)", fontsize=7, color=C["sz"])
ax.set_xlim(-12, 10)
ax.set_ylim(-10.5, 9)
ax.set_aspect("equal")
ax.set_xlabel("u = plate x (mm)")
ax.set_ylabel("v = plate y (mm)")
save(fig, "frames.png")

# ============================================================ figure 2: SRn step
fig, ax = plt.subplots(figsize=(6.2, 4.6))
ax.set_title(f"Step 2 – SRn axis from set 2 (SRn {s2.srn:.0f}, θ = {theta:+.0f}°), 2026-11-14")
rad = np.linalg.norm(q - c_srn)
a0 = np.arctan2(*(q - c_srn)[::-1])
arc = np.linspace(a0, a0 + np.radians(theta), 40)
ax.plot(c_srn[0] + rad * np.cos(arc), c_srn[1] + rad * np.sin(arc), color="k", lw=1)
ax.plot(*q, "o", color=C["st"], ms=8, label=f"feature, set 1: q = ({q[0]:.3f}, {q[1]:.3f})")
ax.plot(*q2, "s", color=C["red"], ms=8, label=f"set 2: q' = q − (ΔST, ΔSZ) = ({q2[0]:.3f}, {q2[1]:.3f})")
ax.plot(*c_srn, "x", color="k", ms=10, mew=2, label=f"SRn axis c = ({c_srn[0]:.3f}, {c_srn[1]:.3f})")
ax.plot([c_srn[0], q[0]], [c_srn[1], q[1]], ":", color=C["grey"])
ax.plot([c_srn[0], q2[0]], [c_srn[1], q2[1]], ":", color=C["grey"])
mid, ch = (q + q2) / 2, q2 - q
perp = np.array([-ch[1], ch[0]]) / np.linalg.norm(ch)
ax.plot(*np.array([mid - 0.4 * perp, mid + 1.9 * perp]).T, "--", color=C["opt"], lw=1,
        label="perpendicular bisector of q q' (c lies on it)")
ax.annotate("", q2, q, arrowprops=dict(arrowstyle="->", color=C["red"], lw=1.2))
ax.text(*(c_srn + [0.05, 0.25]), f"θ = {theta:+.0f}°", fontsize=8)
ax.set_aspect("equal")
ax.set_xlabel("u (mm)")
ax.set_ylabel("v (mm)")
ax.legend(fontsize=7, loc="lower right")
ax.set_xlim(-0.6, 1.6)
ax.set_ylim(-0.6, 1.5)
save(fig, "step_srn.png")

# ============================================================ figure 3: SRz step
fig, axs = plt.subplots(1, 2, figsize=(10, 4.4), gridspec_kw={"width_ratios": [1.15, 1]})
ax = axs[0]
ax.set_title(f"Step 3 – SRz axis from set 3 (SRz {s3.srz:.0f}°, SN kept), top view")
p1 = A + Rz @ (np.zeros(2) - A)
ax.annotate("", (0, 1.2), (0, -3.2), arrowprops=dict(arrowstyle="->", color=C["red"], lw=1.5))
ax.text(0.05, 1.0, "beam", color=C["red"])
ax.plot(*A, "kx", ms=10, mew=2)
ax.text(A[0] + 0.1, A[1] + 0.1, f"SRz axis A = ({A[0]:.2f}, {A[1]:.2f})", fontsize=7)
rad = np.linalg.norm(A)
a0 = np.arctan2(-A[1], -A[0])
arc = np.linspace(a0, a0 + np.radians(phi), 30)
ax.plot(A[0] + rad * np.cos(arc), A[1] + rad * np.sin(arc), color="k", lw=0.8)
ax.plot(0, 0, "o", color=C["st"], ms=8, label="feature, set 1 (analyzer focus)")
ax.plot(*p1, "o", mfc="none", color=C["st"], ms=8, label="after SRz, before ST: p = A + R(φ)(0 − A)")
end = np.array([0.0, p1[1] + p1[0]])
ax.annotate("", end, p1, arrowprops=dict(arrowstyle="->", color=C["st"], lw=1.4))
ax.text(*(p1 + [0.12, -0.25]), f"ΔST = {d_st:+.2f}\n(along t)", color=C["st"], fontsize=7)
ax.plot(*end, "s", color=C["opt"], ms=8, label=f"back on the beam: optic refocused by {d_opt:+.2f}")
ax.plot([A[0], 0], [A[1], 0], ":", color=C["grey"])
ax.plot([A[0], p1[0]], [A[1], p1[1]], ":", color=C["grey"])
ax.set_aspect("equal")
ax.set_xlabel("x (mm, across the beam)")
ax.set_ylabel("y (mm, along the beam)")
ax.legend(fontsize=7, loc="lower left")
ax.set_xlim(min(A[0], 0) - 0.8, max(A[0], 0) + 1.6)
ax.set_ylim(min(A[1], -3.2) - 0.3, max(A[1], 1.3) + 0.3)
ax = axs[1]
srz = np.linspace(-25, 0, 60)
ph = np.radians(-srz)
ax.plot(srz, np.sqrt(2) * (1 - np.cos(ph)), color=C["st"], ls="--", label="∂ΔST/∂r_x  (across: 2nd order)")
ax.plot(srz, np.sqrt(2) * np.sin(ph), color=C["st"], label="∂ΔST/∂r_y  (along)")
ax.plot(srz, np.cos(ph) - 1 + np.sin(ph), color=C["opt"], label="∂Δoptic/∂r_x  (across)")
ax.plot(srz, np.cos(ph) - 1 - np.sin(ph), color=C["opt"], ls="--", label="∂Δoptic/∂r_y  (along)")
ax.axhline(0, color="k", lw=0.5)
ax.set_xlabel("SRz (deg)")
ax.set_ylabel("mm of reading per mm of feature–axis distance")
ax.set_title("What each reading sees of r = feature − axis")
ax.legend(fontsize=7)
save(fig, "step_srz.png")

# ============================================================ figure 4: sensitivity (weighted Jacobian)
ps, osg = measurement_sigmas("capillary")
params = fit_w.params
x0 = np.array([getattr(fit_w.config, p) for p in params[:-1]] + [fit_w.optic_focus])


def resid(xv):
    cfg = replace(fit_w.config, **{p: float(val) for p, val in zip(params[:-1], xv)})
    return _residual_vector(cfg, float(xv[-1]), plate, UVW, sets, [], False, ps, osg)


r0 = resid(x0)
J = np.empty((len(r0), len(x0)))
for i in range(len(x0)):
    dxv = np.zeros_like(x0)
    dxv[i] = 1e-6
    J[:, i] = (resid(x0 + dxv) - r0) / 1e-6
rows = []
short = {"1 reference": "1 SRn120/SRz0", "2 SRn rotated": "2 SRn140", "3 SRz rotated": "3 SRz−10",
         "4 SRn rotated (check)": "4 SRn100", "6 SRn 100 SRz -5": "5 SRn100/SRz−5"}
for s in sets:
    rows += [f"{short[s.name]}: ST", f"{short[s.name]}: SZ"] + ([] if s.sn_kept else [f"{short[s.name]}: SN"])
rows += [f"{short[s.name]}: optic" for s in sets if s.optic is not None]
fig, ax = plt.subplots(figsize=(8.2, 5.4))
im = ax.imshow(np.abs(J), cmap="Blues", aspect="auto")
for i in range(J.shape[0]):
    for j in range(J.shape[1]):
        if abs(J[i, j]) > 0.05:
            ax.text(j, i, f"{abs(J[i, j]):.1f}", ha="center", va="center", fontsize=6,
                    color="white" if abs(J[i, j]) > 0.6 * np.abs(J).max() else "black")
ax.set_xticks(range(len(params)), [PARAM_LABELS[p].replace("Optic at analyzer focus", "F (optic)") for p in params],
              rotation=30, ha="right")
ax.set_yticks(range(len(rows)), rows)
ax.set_title("|∂r_i/∂p_j| of the weighted residuals (σ: positions 0.02, capillary focus 0.10 mm)")
fig.colorbar(im, ax=ax, shrink=0.8, label="1/mm × mm (per σ)")
save(fig, "sensitivity.png")

# ============================================================ figure 5: residuals + prediction of the redundant sets
fig, axs = plt.subplots(1, 2, figsize=(10, 3.6), gridspec_kw={"width_ratios": [1.3, 1]})
ax = axs[0]
names = [short[s.name] for s in sets]
rmap = {n: (a, b, c) for n, a, b, c in fit_u.residuals}
omap = dict(fit_u.optic_residuals)
xs = np.arange(len(sets))
wdt = 0.2
ax.bar(xs - 1.5 * wdt, [1000 * rmap[s.name][0] for s in sets], wdt, color=C["st"], label="ST")
ax.bar(xs - 0.5 * wdt, [1000 * rmap[s.name][1] for s in sets], wdt, color=C["sz"], label="SZ")
ax.bar(xs + 0.5 * wdt, [1000 * (rmap[s.name][2] or 0) for s in sets], wdt, color=C["sn"], label="SN (set 1)")
ax.bar(xs + 1.5 * wdt, [1000 * (omap.get(s.name) or 0) for s in sets], wdt, color=C["opt"], label="optic (CPS)")
ax.axhspan(-20, 20, color="grey", alpha=0.12, label="reading ±0.02 mm")
ax.axhline(0, color="k", lw=0.5)
ax.set_xticks(xs, names, fontsize=7)
ax.set_ylabel("model − measured (µm)")
ax.set_ylim(-30, 30)
ax.legend(fontsize=6.5, ncol=3, loc="upper center")
ax.set_title(f"All 5 sets fitted: 15 equations, 8 unknowns, rms {fit_u.rms * 1000:.1f} µm")
ax = axs[1]
lab = [short[s.name] for s, _, _ in pred45]
xs = np.arange(len(pred45))
ax.bar(xs - wdt, [1000 * d[0] for _, _, d in pred45], wdt, color=C["st"], label="ST")
ax.bar(xs, [1000 * d[1] for _, _, d in pred45], wdt, color=C["sz"], label="SZ")
ax.bar(xs + wdt, [1000 * (d[2] or 0) for _, _, d in pred45], wdt, color=C["opt"], label="optic")
ax.axhspan(-50, 50, color="grey", alpha=0.12, label="'found' tolerance ±0.05 mm")
ax.axhline(0, color="k", lw=0.5)
ax.set_xticks(xs, lab)
ax.set_ylabel("measured − predicted (µm)")
ax.set_ylim(-60, 60)
ax.legend(fontsize=6.5, loc="upper right")
ax.set_title("Sets 4, 5 predicted from sets 1–3 only")
save(fig, "residuals.png")

# ============================================================ figure 6: SRz series of 2026-11-15 (zone plate)
ZPF = 53.7502
M1 = M(st=-3.4982, sz=36.538, sn=-0.05173, srn=120.0, srz=0.0, pix=138, piy=142)
OLD = replace(CAP.config, st0=-0.8127, sz0=41.2059)  # capillary mechanics, zone-plate spot
NEW = ZP.config
series = [(m["srz"], m["st"], m["sz"], m["sn"], m["zps"]) for m in ZP.check["measurements"]
          if m["name"].startswith("SRz -") and "moved" not in m["name"]]
chk = [m for m in ZP.check["measurements"] if "test" in m["name"]][0]


def along(model, m):
    pt = model.lab_to_plate(M1, np.zeros(3))
    return float(model.plate_to_lab(m, *pt)[1])


fig, ax = plt.subplots(figsize=(6.4, 3.9))
srz_v = [0] + [s[0] for s in series]
ax.plot(srz_v, [ZPF] + [s[4] for s in series], "o", color="k", label="measured ZPS (SN kept)")
for name, cfg, sty, col in (("capillary-fitted SRz axis (11-14)", OLD, "s--", C["red"]),
                            ("refitted with the series (11-15)", NEW, "^-", C["opt"])):
    mod = StageModel(cfg, plate)
    ax.plot(srz_v, [ZPF] + [ZPF + along(mod, M(st=s[1], sz=s[2], sn=s[3], srn=120, srz=s[0], pix=138, piy=142))
                            for s in series], sty, mfc="none", color=col, label=name)
    mc = M(st=chk["st"], sz=chk["sz"], sn=chk["sn"], srn=chk["srn"], srz=chk["srz"], pix=138, piy=142)
    pc = ZPF + along(mod, mc)
    ax.plot(chk["srz"] - 0.6, pc, "x", color=col, ms=8, mew=2, label=f"check predicted: {pc:.2f}")
    print(f"check SRn 140 / SRz -15 predicted by {name}: ZPS {pc:.3f}")
ax.plot(chk["srz"] - 0.6, chk["zps"], "*", color="#9467bd", ms=12, label=f"check SRn 140 / SRz −15: {chk['zps']}")
ax.invert_xaxis()
ax.set_xlabel("SRz (deg), SRn 120")
ax.set_ylabel("ZPS in focus (mm)")
ax.set_title("Redundant SRz series with the zone plate (2026-11-15)")
ax.legend(fontsize=7)
save(fig, "srz_series.png")

# model-free inversion of the series (same as step 3, least squares over the 4 angles)
Am, bm = [], []
for a_, st, sz, sn, zps in series:
    dxs = -(st - M1.st) / np.sqrt(2)
    Am.append(rot(-a_) - np.eye(2))
    bm.append(np.array([dxs, (zps - ZPF) - dxs]))
rr, *_ = np.linalg.lstsq(np.vstack(Am), np.concatenate(bm), rcond=None)
res = np.vstack(Am) @ rr - np.concatenate(bm)
print(f"11-15 series: feature - axis r = {rr}, max residual {np.abs(res).max() * 1000:.0f} um")

# ============================================================ figure 7: the loop
fig, ax = plt.subplots(figsize=(9.5, 4.6))
ax.axis("off")
boxes = {
    "sets": (0.02, 0.62, "Measurement sets\n(feature on the beam:\nST, SZ, SN or SN kept,\noptic position)"),
    "fit": (0.27, 0.62, "Weighted Gauss–Newton fit\nmin Σ (r_i/σ_i)²\nrank check (SVD) →\n'add a set at …'"),
    "qual": (0.52, 0.62, "Quality\nrms, χ²/dof, σ(p),\nleast-determined\ncombination"),
    "tests": (0.77, 0.62, "Test points\n(other SRn / SRz):\npredicted ST, SZ, SN,\noptic"),
    "beam": (0.77, 0.12, "At the beamline\nfound (≤ 0.05 mm)\nor real ST, SZ, optic"),
    "save": (0.27, 0.12, "Save\nconfigs/calibration_\n<date>_<optic>.json\n(constants + check record)"),
}
for k, (x, y, t) in boxes.items():
    ax.add_patch(FancyBboxPatch((x, y), 0.2, 0.3, boxstyle="round,pad=0.01", fc="#eef3f8", ec="#1a3a5c"))
    ax.text(x + 0.1, y + 0.15, t, ha="center", va="center", fontsize=7.5)


def arrow(a, b, text="", rad=0.0, dy=0.0):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=12, color="#1a3a5c",
                                 connectionstyle=f"arc3,rad={rad}"))
    if text:
        ax.text((a[0] + b[0]) / 2, (a[1] + b[1]) / 2 + dy, text, ha="center", fontsize=7, color=C["red"])


arrow((0.22, 0.77), (0.27, 0.77))
arrow((0.47, 0.77), (0.52, 0.77))
arrow((0.72, 0.77), (0.77, 0.77))
arrow((0.87, 0.62), (0.87, 0.42))
arrow((0.77, 0.36), (0.40, 0.62), "", rad=-0.15)
ax.text(0.52, 0.36, "measured points: +2–3 equations each → refit", ha="center", fontsize=7, color=C["red"])
arrow((0.77, 0.22), (0.47, 0.22), "a round all found", dy=-0.06)
ax.text(0.5, 0.01, "Found points only confirm (not fitted). An outlier set: untick it and fit again.",
        ha="center", fontsize=7.5, color=C["grey"])
save(fig, "loop.png")
