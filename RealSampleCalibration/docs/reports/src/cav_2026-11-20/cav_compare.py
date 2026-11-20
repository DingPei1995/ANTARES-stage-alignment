"""Edges of the fine PIX x ZPS scans against the stage model.

1. per set (scans with the same motors pooled): focus ZPS = local parabola of the edge sharpness around its maximum,
   edge PIX at focus;
2. absolute edge position on the plate (u, v) from ST/SZ/SN/PIX/PIY with the model (beam line x = z = 0 crossing the
   surface w = 6.0);
3. model ZPS of the surface where the beam hits it (independent of PIX) against the measured focus;
4. SRz axis from SN-kept data only (SRz series: edge PIX + focus) and the SN-moved SRz -25 sets against it."""
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.optimize import fsolve, least_squares

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, r"D:\Codes\ANTARES-stage-alignment-main\src")
from cav_edges import SCANS, analyse  # noqa: E402
from quickalignment.core.geometry import PLATES  # noqa: E402
from quickalignment.core.stage import MotorPositions as M, StageConfig, StageModel  # noqa: E402

plate = PLATES["gating"]
ZPF, W = float(sys.argv[1]) if len(sys.argv) > 1 else 53.7502, 6.0
print(f"ZPS of the anchor focus used: {ZPF}")
NOTES = {"A": 53.7502, "13-23-52": 51.16, "14-13-13": 54.46, "14-23-15": 54.90, "14-41-25": 55.40, "13-37-04": 54.10,
         "SRz-10": 54.53, "13-43-52": 54.96, "13-54-20": 55.46, "SRz-25 first": 53.17, "SRz-25 final": 53.61,
         "15-06-02": 54.33, "10-38-38": None}
GROUPS = {"A": ["11-00-33", "11-03-42"], "10-38-38": ["10-38-38"], "13-23-52": ["13-23-52"], "14-13-13": ["14-13-13"],
          "14-23-15": ["14-23-15"], "14-41-25": ["14-41-25"], "13-37-04": ["13-37-04"],
          "SRz-10": ["13-01-51", "13-15-14"], "13-43-52": ["13-43-52"], "13-54-20": ["13-54-20"],
          "SRz-25 first": ["12-03-50", "12-08-46"], "SRz-25 final": ["15-26-49", "15-33-36"], "15-06-02": ["15-06-02"]}

# ---------------------------------------------------------------- 1. focus and edge per set
sets = {}
for g, tags in GROUPS.items():
    z, pos, sh = [], [], []
    for t in tags:
        r, _ = analyse(t)
        z += r["z"]
        pos += r["pos"]
        sh += r["sharp"]
        m = {k: r[k] for k in ("st", "sn", "sz", "srn", "srz", "piy")}
        label = r["label"]
    z, pos, sh = map(np.asarray, (z, pos, sh))
    o = np.argsort(z)
    z, pos, sh = z[o], pos[o], sh[o]
    shs = uniform_filter1d(sh, 3, mode="nearest")
    k = int(np.argmax(shs))
    lo, hi = max(k - 3, 0), min(k + 4, len(z))
    c = np.polyfit(z[lo:hi], sh[lo:hi], 2)
    zf = -c[1] / (2 * c[0]) if c[0] < 0 else z[k]
    end = k <= 1 or k >= len(z) - 2
    if not (z[lo] <= zf <= z[hi - 1]):
        zf = z[k]
    near = np.abs(z - zf) <= 0.04
    cx = np.polyfit(z[near], pos[near], 1)
    sets[g] = dict(m, label=label, zps=float(zf), zps_notes=NOTES[g], at_end=bool(end), zrange=(z[0], z[-1]),
                   pix=float(np.polyval(cx, zf)), slope=float(cx[0]),
                   pix_err=float(abs(cx[0]) * 0.02 + 0.5))  # +-0.02 ZPS on the focus, 0.5 um edge

# ---------------------------------------------------------------- configurations
old = json.loads(Path(r"D:\Codes\ANTARES-stage-alignment-main\configs\calibration_2026-11-17_153957_zone_plate.json")
                 .read_text(encoding="utf-8"))
C1117 = StageConfig(**old["stage_config"])
fitA = json.loads((HERE / "cav_refit.json").read_text(encoding="utf-8"))
CNEW = replace(C1117, **fitA["anchor"], **fitA["fit"])


def motors(s, pix):
    return M(st=s["st"], sz=s["sz"], sn=s["sn"], srn=s["srn"], srz=s["srz"], pix=pix, piy=s["piy"])


def on_beam_plate(cfg, s, pix):
    """Plate (u, v) under the beam (lab x = z = 0) on the surface w = 6.0."""
    mod = StageModel(cfg, plate)
    m = motors(s, pix)
    q = fsolve(lambda t: [mod.plate_to_lab(m, t[0], t[1], W)[i] for i in (0, 2)], [0.0, 0.0], xtol=1e-12)
    return q


def plane_zps(cfg, s):
    return ZPF + StageModel(cfg, plate).beam_hit(motors(s, 150), W)[1]


def pix_for(cfg, s, u, v):
    """PIX (and PIY) putting plate point (u, v, 6.0) on the beam at the set's ST/SZ/SN/rotations."""
    mod = StageModel(cfg, plate)
    q = fsolve(lambda t: [mod.plate_to_lab(motors(s, t[0]) if True else None, u, v, W)[0] if False else
                          [mod.plate_to_lab(replace(motors(s, t[0]), piy=t[1]), u, v, W)[i] for i in (0, 2)][j]
                          for j in (0, 1)], [150.0, s["piy"]], xtol=1e-12)
    return q


print("=== 1-3. sets: focus, edge, absolute position, model ZPS ===")
print(f"{'set':13s} {'edge':22s} {'SRn':>4s} {'SRz':>4s} {'SN':>7s} {'PIY':>4s} | {'ZPS fit':>7s} {'notes':>6s} "
      f"{'PIX':>6s} | {'u new':>7s} {'v new':>6s} {'ZPS new':>7s} {'d':>6s} | {'u 1117':>7s} {'ZPS 1117':>8s} {'d':>6s}")
for g, s in sets.items():
    un, vn = on_beam_plate(CNEW, s, s["pix"])
    uo, vo = on_beam_plate(C1117, s, s["pix"])
    zn, zo = plane_zps(CNEW, s), plane_zps(C1117, s)
    s.update(u_new=float(un), v_new=float(vn), u_1117=float(uo), zps_new=float(zn), zps_1117=float(zo))
    nt = "" if s["zps_notes"] is None else f"{s['zps_notes']:.2f}"
    print(f"{g:13s} {s['label'][:22]:22s} {s['srn']:4.0f} {s['srz']:4.0f} {s['sn']:7.3f} {s['piy']:4.0f} | "
          f"{s['zps']:7.3f}{'*' if s['at_end'] else ' '}{nt:>6s} {s['pix']:6.1f} | {un:7.4f} {vn:6.3f} {zn:7.3f} "
          f"{s['zps'] - zn:+6.3f} | {uo:7.4f} {zo:8.3f} {s['zps'] - zo:+6.3f}")
print("* sharpest row at the end of the scanned ZPS range: focus is a bound")

# ---------------------------------------------------------------- slides at SRz 0: edge B absolute u (axes-free)
slides = ["13-23-52", "14-13-13", "14-23-15", "14-41-25"]
uB = np.array([sets[g]["u_new"] for g in slides])
print(f"\nedge B (stripe left edge, PIY 40) from the SRz 0 slides: u = {uB.round(4)} -> mean {uB.mean():.4f} "
      f"+- {uB.std():.4f}")
slide_d = [(sets[g]["sn"] - (-0.0517)) * np.sqrt(2) for g in slides]
print("  slide along the beam (mm):", np.round(slide_d, 3), " edge PIX:", [round(sets[g]["pix"], 1) for g in slides])
zf_sl = np.array([sets[g]["zps"] - d for g, d in zip(slides, slide_d)])
print(f"  anchor focus implied by each slide (ZPS - slide, 1:1): {zf_sl.round(3)} -> {zf_sl.mean():.3f} "
      f"+- {zf_sl.std():.3f}")
uA = sets["A"]["u_new"]
print(f"edge A (stripe right edge, PIY 40) at the anchor: u = {uA:.4f}; stripe width A-B = {(uA - uB.mean()) * 1e3:.1f} um "
      "(sign: +u = smaller ST / larger PIX)")

# ---------------------------------------------------------------- 4. SRz axis from SN-kept data only
series = ["13-37-04", "SRz-10", "13-43-52", "13-54-20"]
UB = float(uB.mean())


def resid_axis(x, cfg0=CNEW, use=series, sig_pix=2.0, sig_z=0.02):
    cfg = replace(cfg0, srz_offset_t=x[0], srz_offset_n=x[1])
    r = []
    for g in use:
        s = sets[g]
        mod = StageModel(cfg, plate)
        # lateral: plate point under the beam at the measured edge PIX must be edge B (u), v free
        u, v = on_beam_plate(cfg, s, s["pix"])
        r.append((u - UB) * 1000 / sig_pix)
        r.append((ZPF + mod.beam_hit(motors(s, 150), W)[1] - s["zps"]) / sig_z)
    return np.array(r)


sol = least_squares(resid_axis, [CNEW.srz_offset_t, CNEW.srz_offset_n])
cov = np.linalg.inv(sol.jac.T @ sol.jac)
e = np.sqrt(np.diag(cov))
print(f"\nSRz axis from the SN-kept SRz series (edge B PIX + focus): offset_t {sol.x[0]:+.4f} +- {e[0]:.4f}, "
      f"offset_n {sol.x[1]:+.4f} +- {e[1]:.4f}  (fit A: {CNEW.srz_offset_t:+.4f} / {CNEW.srz_offset_n:+.4f}; "
      f"11-17 in its own frame: {C1117.srz_offset_t:+.4f} / {C1117.srz_offset_n:+.4f})")
print("  residuals (sigma: edge 2 um, ZPS 0.02):", np.round(sol.fun, 2), " chi2", round(float(sol.fun @ sol.fun), 2))
CSER = replace(CNEW, srz_offset_t=float(sol.x[0]), srz_offset_n=float(sol.x[1]))
# tracked point (D1) predictions with this axis for the SN-moved and SRn 140 sets (notes' PIX/PIY of the point)
P = tuple(fitA["point"])
NOTES_PT = {"SRz-25 first": (110, 150, 53.17), "SRz-25 final": (161, 158, 53.61), "15-06-02": (138, 142, 54.33)}
print("\n  set            | measured point PIX/PIY, focus | SN-kept axis: PIX PIY ZPS | fit A: PIX PIY ZPS")
for g, (px, py, zn) in NOTES_PT.items():
    s = sets[g]
    out = []
    for cfg in (CSER, CNEW):
        mod = StageModel(cfg, plate)
        q = fsolve(lambda t: [mod.plate_to_lab(replace(motors(s, t[0]), piy=t[1]), *P)[i] for i in (0, 2)],
                   [px, py], xtol=1e-12)
        out.append((q[0], q[1], plane_zps(cfg, s)))
    print(f"  {g:14s} | {px:4.0f} {py:4.0f} {s['zps']:.3f} (notes {zn}) | {out[0][0]:6.1f} {out[0][1]:6.1f} "
          f"{out[0][2]:.3f} | {out[1][0]:6.1f} {out[1][1]:6.1f} {out[1][2]:.3f}")

# sensitivity: ZPS / edge PIX change per 0.1 mm of SRz axis across / along the beam
print("\nsensitivity at SRz -20 (13-54-20) and -25 (final):")
for g in ("13-54-20", "SRz-25 final"):
    s = sets[g]
    for k, name in ((0, "offset_t"), (1, "offset_n")):
        x = np.array(sol.x)
        dz = []
        for d in (0.0, 0.1):
            xx = x.copy()
            xx[k] += d
            cfg = replace(CNEW, srz_offset_t=xx[0], srz_offset_n=xx[1])
            dz.append((plane_zps(cfg, s), on_beam_plate(cfg, s, s["pix"])[0]))
        print(f"  {g:13s} {name}: +0.1 mm -> ZPS {dz[1][0] - dz[0][0]:+.3f}, edge u {1000 * (dz[1][1] - dz[0][1]):+.1f} um")
json.dump({g: {k: (v if not isinstance(v, tuple) else list(v)) for k, v in s.items()} for g, s in sets.items()},
          open(HERE / "cav_compare.json", "w"), indent=1)
json.dump({"srz_offset_t": float(sol.x[0]), "srz_offset_n": float(sol.x[1]), "err": e.tolist(), "uB": UB,
           "uA": uA}, open(HERE / "cav_axis_snkept.json", "w"), indent=1)
