"""2026-11-20 (v2, user's choice): the tracked point is in focus at ZPS 53.7502 at the anchor (as noted at the
beamline), Cav H 1.0 from the riser top. Gating-plate Cav config, then the standard-plate config the same way as
2026-11-19 (ZP working distance kept, device S1/D1 found on the standard plate, axes kept in the lab).
Run with --save to write both configurations."""
import contextlib
import io
import json
import sys
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from scipy.optimize import fsolve

HERE = Path(__file__).parent
ROOT = Path(r"D:\Codes\ANTARES-stage-alignment-main")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))
from quickalignment.core.calibration import CalibrationRecord, CalibrationStore  # noqa: E402
from quickalignment.core.geometry import PLATES  # noqa: E402
from quickalignment.core.stage import B, MotorPositions as M, OpticsCalibration, StageModel  # noqa: E402

ZPS0 = 53.717  # user 2026-11-20: ZP working distance = the one of ZPS 53.717 (point in focus at the anchor)
argv = sys.argv[:]
sys.argv = [sys.argv[0], str(ZPS0)]
with contextlib.redirect_stdout(io.StringIO()):
    import cav_compare as cc  # noqa: E402
sys.argv = argv

GAT, STD = PLATES["gating"], PLATES["standard"]
P = tuple(cc.fitA["point"])  # Cav D1 (2.862, 4.548, 6.0)
M1 = M(st=-3.4982, sz=36.538, sn=-0.05173, srn=120.0, srz=0.0, pix=138, piy=142)


def r4(cfg):
    return replace(cfg, **{k: round(getattr(cfg, k), 4) for k in
                           ("st0", "sz0", "sn_f", "srn_axis_u", "srn_axis_v", "srz_offset_t", "srz_offset_n")})


# ------------------------------------------------------------------ gating (Cav)
G = r4(cc.CSER)  # anchor: point at the lab origin at M1 (ZPS 53.7502); SRn axis fit A; SRz axis SN-kept, ZPF 53.7502
G_opt = OpticsCalibration(enabled=True, motors=M1, surface_w=P[2], optic_position=ZPS0, optic_sign=1,
                          optic_type="zone plate + OSA")
mg = StageModel(G, GAT)
print("gating config:", G)
print("  point lab at anchor:", np.round(mg.plate_to_lab(M1, *P), 5), " SRz axis fit +-", np.round(cc.e, 4),
      " chi2", round(float(cc.sol.fun @ cc.sol.fun), 2))


def zps_cfg(model, opt, s, w):
    return opt.position_for_focus(model, model.beam_hit(cc.motors(s, s["pix"]), w)[1])


print(f"\n{'set':13s} {'ZPS meas':>9s} {'notes':>6s} {'ZPS cfg':>8s} {'meas-cfg':>8s}   H-1.0+-0.033: ZPS cfg change")
rows = []
for g, s in cc.sets.items():
    z = zps_cfg(mg, G_opt, s, P[2])
    dz = []
    for dh in (-0.033, 0.033):  # H off: anchor re-solved (SN_f absorbs), ZPS reference on the same point
        Pd = (P[0], P[1], P[2] + dh)
        f = lambda x: StageModel(replace(G, st0=x[0], sz0=x[1], sn_f=x[2]), GAT).plate_to_lab(M1, *Pd)  # noqa: E731
        x = fsolve(f, [G.st0, G.sz0, G.sn_f], xtol=1e-13)
        Gd = replace(G, st0=x[0], sz0=x[1], sn_f=x[2])
        od = replace(G_opt, surface_w=Pd[2])
        dz.append(zps_cfg(StageModel(Gd, GAT), od, s, Pd[2]) - z)
    nt = "" if s["zps_notes"] is None else f"{s['zps_notes']:.2f}"
    rows.append(dict(set=g, srn=s["srn"], srz=s["srz"], sn=s["sn"], edge=s["label"], edge_pix=round(s["pix"], 1),
                     zps_meas=round(s["zps"], 3), zps_notes=s["zps_notes"], zps_bound=s["at_end"],
                     zps_config=round(float(z), 3)))
    print(f"{g:13s} {s['zps']:8.3f}{'*' if s['at_end'] else ' '} {nt:>6s} {z:8.3f} {s['zps'] - z:+8.3f}   "
          f"{dz[0]:+.4f} / {dz[1]:+.4f}")

pts = {}
for name, (st, sz, sn, srn, srz, px, py, z) in {
        "SRn 140 map": (-1.6931, 35.841, -0.05163, 140.0003, 0.0004, 132, 84, 53.7502),
        "SRz -25 first": (-4.3935, 36.548, -1.8562, 120, -25, 110, 150, 53.17),
        "SRz -25 final": (-4.7226, 36.546, -1.5809, 120, -25, 161, 158, 53.61),
        "SRn 140 / SRz -15": (-2.9839, 35.886, -0.0519, 140, -15, 138, 142, 54.33)}.items():
    m = M(st=st, sz=sz, sn=sn, srn=srn, srz=srz, pix=px, piy=py)
    q = fsolve(lambda t: [mg.plate_to_lab(replace(m, pix=t[0], piy=t[1]), *P)[i] for i in (0, 2)], [px, py],
               xtol=1e-12)
    zz = G_opt.position_for_focus(mg, mg.beam_hit(m, P[2])[1])
    pts[name] = dict(pix=px, piy=py, zps_notes=z, pix_config=round(float(q[0]), 1),
                     piy_config=round(float(q[1]), 1), zps_config=round(float(zz), 3))
    print(f"  {name:18s} PIX/PIY {px}/{py} -> {q[0]:.1f}/{q[1]:.1f}; ZPS notes {z} config {zz:.3f}")

# ------------------------------------------------------------------ standard plate (method of 2026-11-19)
old19 = json.loads((ROOT / "configs/calibration_2026-11-19_123901_zone_plate.json").read_text(encoding="utf-8"))
f19 = old19["check"]["found"]
MS = M(st=f19["st"], sz=f19["sz"], sn=f19["sn"], srn=120.0, srz=0.0, pix=f19["pix"], piy=f19["piy"])
US, VS = old19["check"]["point_plate_uvw"][:2]
y_dev = f19["zps"] - ZPS0  # ZP working distance kept: ZPS 53.82 -> focus +0.0698 along the beam


def solve_std(x):
    st0, sz0, w = x
    cfg = replace(G, st0=st0, sz0=sz0)
    return StageModel(cfg, STD).plate_to_lab(MS, US, VS, w) - np.array([0.0, y_dev, 0.0])


st0s, sz0s, ws = fsolve(solve_std, [G.st0, G.sz0, 5.7], xtol=1e-13)
du, dv = st0s - G.st0, sz0s - G.sz0  # plate frame shift (axes kept in the lab)
S = r4(replace(G, st0=st0s, sz0=sz0s, srn_axis_u=G.srn_axis_u + du, srn_axis_v=G.srn_axis_v + dv,
               srz_offset_t=G.srz_offset_t + du))
S_opt = OpticsCalibration(enabled=True, motors=MS, surface_w=float(ws), optic_position=f19["zps"], optic_sign=1,
                          optic_type="zone plate + OSA")
ms = StageModel(S, STD)
print("\nstandard config:", S)
print(f"  device H {ws - 5.0:.4f} (11-19: {old19['optics']['surface_w'] - 5:.4f}); plate shift standard vs gating "
      f"du {du:+.4f} dv {dv:+.4f}; device lab {np.round(ms.plate_to_lab(MS, US, VS, ws), 5)}; "
      f"ZPS for lab origin {S_opt.position_for_focus(ms, 0.0):.4f}")
# lab axes identical?
for name, cfg, pl in (("gating", G, GAT), ("standard", S, STD)):
    mod = StageModel(cfg, pl)
    ax = mod._translation(M1) + B @ mod._srz_axis_local()
    srn = mod.plate_to_lab(replace(M1, pix=150, piy=150), cfg.srn_axis_u, cfg.srn_axis_v, 5.0)
    print(f"  {name:8s} SRz axis lab at M1 {np.round(ax[:2], 4)}  SRn axis lab at M1 {np.round(srn, 4)}")

# ------------------------------------------------------------------ comparison tables
recs = {r.path.name: r for r in CalibrationStore(ROOT / "configs").records()}


def frame_free(cfg, opt, plate, m_ref, point):
    mod = StageModel(cfg, plate)
    pp = mod.plate_to_lab(m_ref, *point)
    ax = mod._translation(m_ref) + B @ mod._srz_axis_local()
    return [cfg.st0, cfg.sz0, cfg.sn_f, cfg.srn_axis_u, cfg.srn_axis_v, cfg.srz_offset_t, cfg.srz_offset_n,
            cfg.srn_axis_u - point[0], cfg.srn_axis_v - point[1], ax[0] - pp[0], ax[1] - pp[1],
            opt.position_for_focus(mod, 0.0), point[2] - 5.0]


names = ["ST0", "SZ0", "SN_f", "SRn axis u", "SRn axis v", "SRz offset_t", "SRz offset_n", "SRn axis - point u",
         "SRn axis - point v", "SRz axis - point x", "SRz axis - point y", "ZPS for lab origin", "H of point"]
c15 = recs["calibration_2026-11-15_151356_zone_plate.json"]
c17 = recs["calibration_2026-11-17_153957_zone_plate.json"]
c19 = recs["calibration_2026-11-19_123901_zone_plate.json"]
T = {"11-15": frame_free(c15.config, c15.optics, GAT, M1, (2.6975802057399307, 4.659871540778488, 5.746505506549614)),
     "11-17": frame_free(c17.config, c17.optics, GAT, M1, (2.833, 4.597, 5.746505506549614)),
     "11-20 G": frame_free(G, G_opt, GAT, M1, P)}
print(f"\n{'gating':20s} {'11-15':>9s} {'11-17':>9s} {'11-20':>9s} {'-11-15':>8s} {'-11-17':>8s}")
for i, n in enumerate(names):
    a, b, c = T["11-15"][i], T["11-17"][i], T["11-20 G"][i]
    print(f"{n:20s} {a:9.4f} {b:9.4f} {c:9.4f} {c - a:+8.4f} {c - b:+8.4f}")
T19 = frame_free(c19.config, c19.optics, STD, MS, (US, VS, c19.optics.surface_w))
T20 = frame_free(S, S_opt, STD, MS, (US, VS, ws))
print(f"\n{'standard':20s} {'11-19':>9s} {'11-20':>9s} {'diff':>8s}")
for i, n in enumerate(names):
    print(f"{n:20s} {T19[i]:9.4f} {T20[i]:9.4f} {T20[i] - T19[i]:+8.4f}")
print(f"gating - standard SZ0: {G.sz0 - S.sz0:+.4f}, ST0: {G.st0 - S.st0:+.4f}")

# ------------------------------------------------------------------ save
if "--save" in argv:
    resid_sl = [r["zps_meas"] - r["zps_config"] for r in rows if r["set"] in ("13-23-52", "14-13-13", "14-23-15",
                                                                               "14-41-25")]
    common = ("SRz axis from SN-kept data only (SRz -5 / -10 / -15 / -20 line scans: left edge of the device stripe at "
              "PIY ~40, edge PIX measured, its plate position from the 4 SRz 0 slides; and their foci): offset_t "
              f"{G.srz_offset_t} +- 0.031, offset_n {G.srz_offset_n} +- 0.023. SRn axis from the SRn 140 map "
              "(PIX 132 / PIY 84), relative to the point unchanged since 11-15. ")
    gcom = (
        "Gating plate + zone plate, sample Cav (graphene), data of 2026-11-15 (CavData/*.nxs) re-analysed 2026-11-20. "
        "Supersedes calibration_2026-11-20_141536, 2026-11-17 15:39:57 and 2026-11-15 15:13:56. "
        "Cav layout Cav.json: H 1.0 mm from the riser top (measured), tracked point = device D1 (PIX 138 / PIY 142 at "
        "SRn 120 / SRz 0) at plate x 2.862 / y 4.548. Anchor: ST -3.4982, SZ 36.538, SN -0.05173, PIX 138, PIY 142, "
        "point in focus at ZPS 53.717 and on the lab origin (user 2026-11-20: ZP working distance = that of ZPS "
        "53.717). 53.717 comes from the steepest edge of the fine PIX x ZPS scans: the 4 SRz 0 SN slides with ST "
        "compensating (-2.556 / +0.752 / +1.202 / +1.701 mm along the beam) give 53.728 / 53.709 / 53.719 / 53.711 "
        "(ZPS 1:1); the beamline note was 53.75. "
        f"ST0 {G.st0}, SZ0 {G.sz0}, SN_f {G.sn_f} (was -0.7983, from H 0.748). " + common +
        "Residuals: SRz 0 slides " + " / ".join(f"{v:+.3f}" for v in resid_sl) +
        " mm; SRz -5..-20 within 0.016 mm; check SRn 140 / SRz -15 PIX "
        f"{pts['SRn 140 / SRz -15']['pix_config']} (found 138), ZPS {pts['SRn 140 / SRz -15']['zps_config']} (found "
        "54.33). Open: the two SRz -25 sets with SN moved focus ~0.2 mm lower in ZPS than predicted, PIX within "
        "~10 um (pure along-beam error, not an SN reading error). Capillary configuration of 2026-11-14 not used.")
    gcheck = {"type": "zone-plate SPEM edge analysis (fine PIX x ZPS scans) + point tracking", "plate": "gating",
              "point_plate_uvw": list(P), "layout": "Cav.json", "zps_point_in_focus_at_anchor": ZPS0,
              "slides_imply_anchor_focus": 53.717, "edge_sets": rows, "tracked_point": pts,
              "srz_axis_fit": {"data": f"SN-kept SRz -5..-20 (edge PIX + focus), ZPS ref {ZPS0}",
                               "err": [round(float(e), 4) for e in cc.e],
                               "chi2": round(float(cc.sol.fun @ cc.sol.fun), 2), "dof": 6},
              "analysis": "RealSampleCalibration/docs/reports/2026-11-20_cav_zp_memo.md",
              "previous": ["2026-11-20 14:15:36 zone plate (working distance of ZPS 53.7502, point 0.033 upstream)",
                           "2026-11-17 15:39:57 zone plate",
                           "2026-11-15 15:13:56 zone plate"]}
    scom = (
        "Standard plate + zone plate, 2026-11-20, from the gating-plate Cav configuration of the same time (2026-11-20 "
        "v2) the way 2026-11-19 was made from 2026-11-17: zone-plate working distance kept (ZPS 53.717 = lab origin), "
        "SN_f kept, SRn / SRz axes kept in the lab and re-expressed in the standard plate frame. Device S1/D1 "
        f"(20261119/Sample.json, plate x {US} / y {VS}) found at SRn 120 / SRz 0: ST {MS.st}, SZ {MS.sz}, SN {MS.sn}, "
        f"PIX {MS.pix:.0f}, PIY {MS.piy:.0f}, ZPS {f19['zps']} in focus (+{y_dev * 1000:.0f} um along the beam from the "
        f"lab origin): device H {ws - 5:.4f} (11-19: 0.6989), ST0 {S.st0}, SZ0 {S.sz0} (plate {du:+.4f} / {dv:+.4f} mm "
        "in u / v against the gating plate of the Cav configuration). Supersedes calibration_2026-11-19_123901. "
        "Only one device, one rotation: rotation axes not checked with this plate.")
    scheck = {"type": "one device found with the zone plate, working distance kept", "plate": "standard",
              "point_plate_uvw": [US, VS, float(ws)], "device": "S1/D1, 20261119/Sample.json",
              "found": f19, "from": "gating Cav configuration 2026-11-20 v2",
              "gating_minus_standard": {"st0": round(G.st0 - S.st0, 4), "sz0": round(G.sz0 - S.sz0, 4)},
              "previous": ["2026-11-19 12:39:01 zone plate"]}
    store = CalibrationStore(ROOT / "configs")
    now = datetime.now()
    a = store.save(CalibrationRecord(comment=gcom, config=G, optics=G_opt, check=gcheck), now=now)
    b = store.save(CalibrationRecord(comment=scom, config=S, optics=S_opt, check=scheck), now=now + timedelta(seconds=1))
    print("\nsaved:", a.path.name, b.path.name)
    print("latest zone plate:", store.latest("zone plate + OSA").path.name)
