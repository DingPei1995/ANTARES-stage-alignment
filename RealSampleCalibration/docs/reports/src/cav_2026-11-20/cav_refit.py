"""Cav + ZP 2026-11-15 refit with the new Cav layout (Cav.json: H 1.0, device D1 = tracked point PIX 138 / PIY 142)."""
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
from scipy.optimize import fsolve, least_squares

ROOT = Path(r"D:\Codes\ANTARES-stage-alignment-main")
sys.path.insert(0, str(ROOT / "src"))
from quickalignment.core.geometry import PLATES  # noqa: E402
from quickalignment.core.stage import MotorPositions as M, StageConfig, StageModel  # noqa: E402

plate = PLATES["gating"]
lay = json.loads((ROOT / "Cav.json").read_text(encoding="utf-8"))["layout"]
s = lay["samples"][0]
d = s["devices"][0]
u = s["u"] - s["length"] / 2 + d["dx"]
v = s["v"] - s["width"] / 2 + d["dy"]
w = plate.total_thickness + s["height"]
P = (u, v, w)
print(f"D1 plate point u {u:.4f} v {v:.4f} w {w:.4f}")

old = json.loads((ROOT / "configs/calibration_2026-11-17_153957_zone_plate.json").read_text(encoding="utf-8"))
OLD = StageConfig(**old["stage_config"])
ZPF = 53.7502

# ---- step 1: anchor at SRn 120 / SRz 0 (ZPS 53.7502 focus = lab origin, working distance kept)
M1 = M(st=-3.4982, sz=36.538, sn=-0.05173, srn=120.0, srz=0.0, pix=138, piy=142)
base = StageModel(replace(OLD), plate)
# solve st0, sz0, sn_f so that the point is at the lab origin at M1 (independent of the axes at the ref rotation)
def anchor(cfg):
    def f(x):
        c = replace(cfg, st0=x[0], sz0=x[1], sn_f=x[2])
        return StageModel(c, plate).plate_to_lab(M1, *P)
    x = fsolve(f, [cfg.st0, cfg.sz0, cfg.sn_f], xtol=1e-12)
    return replace(cfg, st0=float(x[0]), sz0=float(x[1]), sn_f=float(x[2]))

A = anchor(OLD)
print(f"anchor: st0 {A.st0:.4f} (old {OLD.st0}), sz0 {A.sz0:.4f} (old {OLD.sz0}), sn_f {A.sn_f:.4f} (old {OLD.sn_f:.4f})")

# ---- step 2: data sets with PIX, PIY and ZPS all read on the tracked point
# (name, motors, zps, sigma_pix_um)
SETS = [
    ("SRn 140 / SRz 0 map", M(st=-1.6931, sz=35.841, sn=-0.05163, srn=140.0003, srz=0.0004, pix=132, piy=84), 53.7502, 4),
    ("SRz -25 SN moved (first)", M(st=-4.3935, sz=36.548, sn=-1.856, srn=120, srz=-25, pix=110, piy=150), 53.17, 10),
    ("SRz -25 SN moved (final)", M(st=-4.7228, sz=36.54, sn=-1.578, srn=120, srz=-25, pix=161, piy=158), 53.61, 4),
]
CHECK = ("SRn 140 / SRz -15", M(st=-2.9839, sz=35.886, sn=-0.052, srn=140, srz=-15, pix=138, piy=142), 54.33)
SRZ_SERIES = [  # PIX/PIY not really located on these (user)
    ("SRz -5", M(st=-4.066, sz=36.54, sn=-0.05, srn=120, srz=-5, pix=138, piy=142), 54.10),
    ("SRz -10", M(st=-4.6255, sz=36.539, sn=-0.048, srn=120, srz=-10, pix=138, piy=142), 54.53),
    ("SRz -15", M(st=-5.1703, sz=36.54, sn=-0.05, srn=120, srz=-15, pix=138, piy=142), 54.96),
    ("SRz -20", M(st=-5.6966, sz=36.54, sn=-0.05, srn=120, srz=-20, pix=138, piy=142), 55.46),
]
SIG_ZPS = 0.02


def cfg_of(x, base_cfg=A):
    return replace(base_cfg, srn_axis_u=x[0], srn_axis_v=x[1], srz_offset_t=x[2], srz_offset_n=x[3])


def resid(x, sets=SETS):
    mod = StageModel(cfg_of(x), plate)
    r = []
    for _, m, zps, sp in sets:
        p = mod.plate_to_lab(m, *P)
        r += [p[0] / (sp / 1000), p[2] / (sp / 1000), (p[1] - (zps - ZPF)) / SIG_ZPS]
    return np.array(r)


x0 = [A.srn_axis_u, A.srn_axis_v, A.srz_offset_t, A.srz_offset_n]
sol = least_squares(resid, x0, xtol=1e-14, ftol=1e-14)
J = sol.jac
cov = np.linalg.inv(J.T @ J)
dof = len(sol.fun) - len(sol.x)
chi2 = float(sol.fun @ sol.fun)
err = np.sqrt(np.diag(cov))
NEW = cfg_of(sol.x)
names = ["srn_axis_u", "srn_axis_v", "srz_offset_t", "srz_offset_n"]
print(f"\nfit: chi2 {chi2:.2f}, dof {dof}")
for n, a, b, e in zip(names, x0, sol.x, err):
    print(f"  {n:13s} {a:+.4f} -> {b:+.4f}  +- {e:.4f}")
corr = cov / np.outer(err, err)
print("  corr\n", np.round(corr, 2))
ev, evec = np.linalg.eigh(cov)
print(f"  least determined combination: {np.round(evec[:, -1], 3)} +- {np.sqrt(ev[-1]):.4f}")


def predict(cfg, m):
    """PIX / PIY at which the point is on the beam at these ST/SZ/SN/rotations, and the ZPS of its focus."""
    mod = StageModel(cfg, plate)
    q = fsolve(lambda t: [mod.plate_to_lab(replace(m, pix=t[0], piy=t[1]), *P)[i] for i in (0, 2)], [m.pix, m.piy],
               xtol=1e-12)
    y = mod.plate_to_lab(replace(m, pix=q[0], piy=q[1]), *P)[1]
    return q[0], q[1], ZPF + y


OLD_A = replace(OLD)  # 11-17 config as it was (point taken as H 0.748 there, but its own point)
P_OLD = tuple(old["check"]["point_plate_uvw"])


def predict_old(m):
    mod = StageModel(OLD, plate)
    q = fsolve(lambda t: [mod.plate_to_lab(replace(m, pix=t[0], piy=t[1]), *P_OLD)[i] for i in (0, 2)],
               [m.pix, m.piy], xtol=1e-12)
    return q[0], q[1], ZPF + mod.plate_to_lab(replace(m, pix=q[0], piy=q[1]), *P_OLD)[1]


print("\n=== fitted sets + check + SRz series: measured vs new axes vs 11-17 config ===")
hdr = f"{'set':28s} {'PIX':>5s} {'PIY':>5s} {'ZPS':>6s} | {'PIX new':>7s} {'PIY new':>7s} {'ZPS new':>7s} | {'PIX 1117':>8s} {'PIY 1117':>8s} {'ZPS 1117':>8s}"
print(hdr)
rows = []
for name, m, zps, *_ in [("SRn 120 / SRz 0 anchor", M1, ZPF)] + SETS + [CHECK] + SRZ_SERIES:
    a, b, c = predict(NEW, m)
    a0, b0, c0 = predict_old(m)
    print(f"{name:28s} {m.pix:5.0f} {m.piy:5.0f} {zps:6.2f} | {a:7.1f} {b:7.1f} {c:7.3f} | {a0:8.1f} {b0:8.1f} {c0:8.3f}")
    rows.append(dict(name=name, st=m.st, sz=m.sz, sn=m.sn, srn=m.srn, srz=m.srz, pix=m.pix, piy=m.piy, zps=zps,
                     pix_new=a, piy_new=b, zps_new=c, pix_1117=a0, piy_1117=b0, zps_1117=c0))

# SRz axis relative to the point (top view, lab x across / y along the beam), at SRn 120 / SRz 0 / M1
for lab, cfg, pt in (("new", NEW, P), ("11-17", OLD, P_OLD)):
    mod = StageModel(cfg, plate)
    ax = mod._translation(M1) + __import__("quickalignment.core.stage", fromlist=["B"]).B @ mod._srz_axis_local()
    pp = mod.plate_to_lab(M1, *pt)
    print(f"SRz axis - point ({lab}): x {ax[0] - pp[0]:+.4f}, y {ax[1] - pp[1]:+.4f} mm")

out = dict(point=P, anchor=dict(st0=A.st0, sz0=A.sz0, sn_f=A.sn_f), fit=dict(zip(names, sol.x.tolist())),
           err=dict(zip(names, err.tolist())), chi2=chi2, dof=dof, rows=rows,
           resid=sol.fun.tolist())
Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print("\nresiduals (sigma units, x z y per set):", np.round(sol.fun, 2))

# convergence check of predict()
for name, m, zps, *_ in SETS + [CHECK] + SRZ_SERIES:
    a, b, c = predict(NEW, m)
    p = StageModel(NEW, plate).plate_to_lab(replace(m, pix=a, piy=b), *P)
    hit = StageModel(NEW, plate).beam_hit(m, w)[1] + ZPF
    print(f"  {name:26s} |x|,|z| um {abs(p[0])*1e3:.3f} {abs(p[2])*1e3:.3f}  plane-hit ZPS {hit:.3f} vs {c:.3f}")

# ---- variant B (information only): also the ZPS of the SRz series + check as surface-plane foci (PIX-independent)
PLANE = [(n, m, z) for n, m, z in SRZ_SERIES] + [CHECK]


def resid_b(x):
    mod = StageModel(cfg_of(x), plate)
    r = list(resid(x))
    for _, m, zps in PLANE:
        r.append((mod.beam_hit(m, w)[1] - (zps - ZPF)) / SIG_ZPS)
    return np.array(r)


sb = least_squares(resid_b, sol.x, xtol=1e-14, ftol=1e-14)
eb = np.sqrt(np.diag(np.linalg.inv(sb.jac.T @ sb.jac)))
print(f"\nvariant B (+ plane ZPS of SRz series and check): chi2 {sb.fun @ sb.fun:.1f}, dof {len(sb.fun) - 4}")
for n, a, e in zip(names, sb.x, eb):
    print(f"  {n:13s} {a:+.4f} +- {e:.4f}")
print("  residuals (sigma):", np.round(sb.fun, 1))
NB = cfg_of(sb.x)
for name, m, zps, *_ in SETS + [CHECK] + SRZ_SERIES:
    a, b, c = predict(NB, m)
    print(f"  {name:26s} PIX {a:6.1f} PIY {b:6.1f} ZPS {c:7.3f} (meas {m.pix:.0f}/{m.piy:.0f}/{zps})")

# ---- variant C: SN-kept data only for the SRz axis (SRn140 map + SRz-series/check plane foci), no SN-moved sets
def resid_c(x):
    mod = StageModel(cfg_of(x), plate)
    r = list(resid(x, SETS[:1]))
    for _, m, zps in PLANE:
        r.append((mod.beam_hit(m, w)[1] - (zps - ZPF)) / SIG_ZPS)
    return np.array(r)


sc = least_squares(resid_c, sol.x, xtol=1e-14, ftol=1e-14)
ec = np.sqrt(np.diag(np.linalg.inv(sc.jac.T @ sc.jac)))
print(f"\nvariant C (SN kept only): chi2 {sc.fun @ sc.fun:.1f}, dof {len(sc.fun) - 4}")
for n, a, e in zip(names, sc.x, ec):
    print(f"  {n:13s} {a:+.4f} +- {e:.4f}")
print("  residuals (sigma):", np.round(sc.fun, 1))
NC = cfg_of(sc.x)
for name, m, zps, *_ in SETS + [CHECK] + SRZ_SERIES:
    a, b, c = predict(NC, m)
    print(f"  {name:26s} PIX {a:6.1f} PIY {b:6.1f} ZPS {c:7.3f} (meas {m.pix:.0f}/{m.piy:.0f}/{zps})")
