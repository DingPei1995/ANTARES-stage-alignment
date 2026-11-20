"""Build the new Cav + zone-plate configuration (2026-11-20) and check it against all the 2026-11-15 data."""
import io
import contextlib
import json
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.optimize import fsolve

HERE = Path(__file__).parent
ROOT = Path(r"D:\Codes\ANTARES-stage-alignment-main")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))
from quickalignment.core.calibration import CalibrationRecord, CalibrationStore  # noqa: E402
from quickalignment.core.geometry import PLATES  # noqa: E402
from quickalignment.core.stage import (B, MotorPositions as M, OpticsCalibration, StageConfig,  # noqa: E402
                                       StageModel)

sys.argv = [sys.argv[0], "53.717"]
with contextlib.redirect_stdout(io.StringIO()):
    import cav_compare as cc  # noqa: E402

plate = PLATES["gating"]
SAVE = "--save" in sys.argv[1:] or (len(sys.argv) > 2)
ZPS_REF_OLD = 53.7502   # ZPS putting the ZP focus on the lab origin (working distance kept from 11-15)
ZPS_POINT = 53.717      # ZPS in focus on the tracked point at the anchor (from the 4 SRz 0 slides)
P = tuple(cc.fitA["point"])  # D1: 2.862 / 4.548 / 6.0
M1 = M(st=-3.4982, sz=36.538, sn=-0.05173, srn=120.0, srz=0.0, pix=138, piy=142)
y_pt = ZPS_POINT - ZPS_REF_OLD

base = replace(cc.CSER)  # SRn axis (fit A, SRn 140 map), SRz axis (SN-kept), anchor for y = 0


def anchor(cfg, target):
    def f(x):
        return StageModel(replace(cfg, st0=x[0], sz0=x[1], sn_f=x[2]), plate).plate_to_lab(M1, *P) - target
    x = fsolve(f, [cfg.st0, cfg.sz0, cfg.sn_f], xtol=1e-13)
    return replace(cfg, st0=float(x[0]), sz0=float(x[1]), sn_f=float(x[2]))


NEW = anchor(base, np.array([0.0, y_pt, 0.0]))
NEW = replace(NEW, st0=round(NEW.st0, 4), sz0=round(NEW.sz0, 4), sn_f=round(NEW.sn_f, 4),
              srn_axis_u=round(NEW.srn_axis_u, 4), srn_axis_v=round(NEW.srn_axis_v, 4),
              srz_offset_t=round(NEW.srz_offset_t, 4), srz_offset_n=round(NEW.srz_offset_n, 4))
optics = OpticsCalibration(enabled=True, motors=M1, surface_w=P[2], optic_position=ZPS_POINT, optic_sign=1,
                           optic_type="zone plate + OSA")
model = StageModel(NEW, plate)
print("new stage_config:", NEW)
print(f"ZPS for the lab origin (working distance check): {optics.position_for_focus(model, 0.0):.4f} "
      f"(11-15: {ZPS_REF_OLD})")

# ---- check against every set: focus ZPS of the surface on the beam, and the point / edge PIX
rows = []
print(f"\n{'set':13s} {'SRn':>4s} {'SRz':>4s} {'SN':>7s} | {'ZPS meas':>8s} {'notes':>6s} {'ZPS cfg':>7s} {'d':>6s} | edge u (um vs ref)")
for g, s in cc.sets.items():
    m = cc.motors(s, s["pix"])
    zp = optics.position_for_focus(model, model.beam_hit(m, P[2])[1])
    q = fsolve(lambda t: [model.plate_to_lab(m, t[0], t[1], P[2])[i] for i in (0, 2)], [0.0, 0.0], xtol=1e-12)
    rows.append(dict(set=g, srn=s["srn"], srz=s["srz"], sn=s["sn"], st=s["st"], sz=s["sz"], piy=s["piy"],
                     edge=s["label"], edge_pix=round(s["pix"], 1), zps_meas=round(s["zps"], 3),
                     zps_notes=s["zps_notes"], zps_bound=s["at_end"], zps_config=round(float(zp), 3),
                     edge_u=round(float(q[0]), 4), edge_v=round(float(q[1]), 4)))
    nt = "" if s["zps_notes"] is None else f"{s['zps_notes']:.2f}"
    print(f"{g:13s} {s['srn']:4.0f} {s['srz']:4.0f} {s['sn']:7.3f} | {s['zps']:8.3f}{'*' if s['at_end'] else ' '}"
          f"{nt:>6s} {zp:7.3f} {s['zps'] - zp:+6.3f} | u {q[0]:.4f}")

pts = {}
print("\ntracked point (D1) with the config:")
for name, (st, sz, sn, srn, srz, px, py, z) in {
        "SRn 140 map": (-1.6931, 35.841, -0.05163, 140.0003, 0.0004, 132, 84, 53.7502),
        "SRz -25 first": (-4.3935, 36.548, -1.8562, 120, -25, 110, 150, 53.17),
        "SRz -25 final": (-4.7226, 36.546, -1.5809, 120, -25, 161, 158, 53.61),
        "SRn 140 / SRz -15": (-2.9839, 35.886, -0.0519, 140, -15, 138, 142, 54.33)}.items():
    m = M(st=st, sz=sz, sn=sn, srn=srn, srz=srz, pix=px, piy=py)
    q = fsolve(lambda t: [model.plate_to_lab(replace(m, pix=t[0], piy=t[1]), *P)[i] for i in (0, 2)], [px, py],
               xtol=1e-12)
    zp = optics.position_for_focus(model, model.beam_hit(m, P[2])[1])
    pts[name] = dict(pix=px, piy=py, zps_notes=z, pix_config=round(float(q[0]), 1), piy_config=round(float(q[1]), 1),
                     zps_config=round(float(zp), 3))
    print(f"  {name:18s} PIX/PIY {px}/{py} -> config {q[0]:.1f}/{q[1]:.1f}; ZPS notes {z} config {zp:.3f}")

# ---- frame-free comparison with the earlier configurations
recs = {r.path.name: r for r in CalibrationStore(ROOT / "configs").records()}
OLDS = {"11-15": ("calibration_2026-11-15_151356_zone_plate.json", (2.6975802057399307, 4.659871540778488, 5.746505506549614)),
        "11-17": ("calibration_2026-11-17_153957_zone_plate.json", (2.833, 4.597, 5.746505506549614))}


def geometry(cfg, opt, point):
    mod = StageModel(cfg, plate)
    pp = mod.plate_to_lab(M1, *point)
    ax = mod._translation(M1) + B @ mod._srz_axis_local()
    return dict(st0=cfg.st0, sz0=cfg.sz0, sn_f=cfg.sn_f, srn_u=cfg.srn_axis_u, srn_v=cfg.srn_axis_v,
                srz_t=cfg.srz_offset_t, srz_n=cfg.srz_offset_n,
                srn_rel_u=cfg.srn_axis_u - point[0], srn_rel_v=cfg.srn_axis_v - point[1],
                srz_rel_x=float(ax[0] - pp[0]), srz_rel_y=float(ax[1] - pp[1]),
                zps_origin=float(opt.position_for_focus(mod, 0.0)),
                zps_point=float(opt.position_for_focus(mod, pp[1])), point_y=float(pp[1]), point_h=point[2] - 5.0)


G = {k: geometry(recs[f].config, recs[f].optics, pt) for k, (f, pt) in OLDS.items()}
G["11-20"] = geometry(NEW, optics, P)
keys = ["st0", "sz0", "sn_f", "srn_u", "srn_v", "srz_t", "srz_n", "srn_rel_u", "srn_rel_v", "srz_rel_x", "srz_rel_y",
        "zps_origin", "zps_point", "point_y", "point_h"]
print(f"\n{'':11s} {'11-15':>9s} {'11-17':>9s} {'11-20':>9s} {'20-15':>8s} {'20-17':>8s}")
for k in keys:
    a, b, c = G["11-15"][k], G["11-17"][k], G["11-20"][k]
    print(f"{k:11s} {a:9.4f} {b:9.4f} {c:9.4f} {c - a:+8.4f} {c - b:+8.4f}")

if "--save" in sys.argv:
    pass
out = dict(new=NEW.__dict__, optics=dict(optic_position=ZPS_POINT, surface_w=P[2]), rows=rows, points=pts,
           geometry=G)
(HERE / "cav_make_config.json").write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")
