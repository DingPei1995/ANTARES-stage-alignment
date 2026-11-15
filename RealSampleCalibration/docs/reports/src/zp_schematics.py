"""Two schematics for the 2026-11-15 report: (a) front view of the gating plate with the capillary and zone-plate
spots and the SRn axes of 2026-11-14 / 2026-11-15; (b) top view at SRn 120 / SRz 0 with the SRz axes. Writes
report_figs/zp_schem_front.png, report_figs/zp_schem_top.png and spem/zp_schem.json (the differences)."""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from dataclasses import replace

import numpy as np
from matplotlib.patches import Polygon, Rectangle

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))
from quickalignment.core.calibration import CalibrationStore  # noqa: E402
from quickalignment.core.geometry import PLATES  # noqa: E402
from quickalignment.core.stage import B, N_HAT, T_HAT, MotorPositions as M, StageModel  # noqa: E402

HERE = Path(__file__).parent
FIGS, SPEM = HERE / "report_figs", HERE / "spem"
plate = PLATES["gating"]
recs = {r.path.name: r for r in CalibrationStore(ROOT / "configs").records()}
CAP = recs["calibration_2026-11-14_173743_capillary.json"].config
ZP = recs["calibration_2026-11-15_151356_zone_plate.json"].config
REF = M(st=-3.4982, sz=36.538, sn=-0.05173, srn=120.0, srz=0.0)  # map 1 motors, piezo centred
CAV = (2.687, 4.666)
FEATURE_CAP = (1.284, 0.775)  # reference feature of the capillary calibration
CAP_C, ZP_C, OLD_C, NEW_C = "#d62728", "#1f77b4", "#ff7f0e", "#2ca02c"

# spots on the plate (where the beam hits at the same motors), plate frame
spot = {name: (cfg.st0 - REF.st, cfg.sz0 - REF.sz) for name, cfg in (("capillary", CAP), ("zone plate", ZP))}
srn_axis = {"2026-11-14": (CAP.srn_axis_u, CAP.srn_axis_v), "2026-11-15": (ZP.srn_axis_u, ZP.srn_axis_v)}

# ------------------------------------------------------------------ (a) front view
fig, axs = plt.subplots(1, 2, figsize=(10, 5.2), gridspec_kw={"width_ratios": [1, 1.25]})
for k, ax in enumerate(axs):
    ax.add_patch(Polygon(plate.outline(), closed=True, fc="#e8e8e8", ec="grey", lw=1))
    r0, s0, r1, s1 = plate.riser_bounds()
    ax.add_patch(Rectangle((r0, s0), r1 - r0, s1 - s0, fc="#d0d6dd", ec="#7a8794", lw=1,
                           label="sample area (riser)" if k == 0 else None))
    c0, d0, c1, d1 = plate.contact_block
    ax.add_patch(Rectangle((c0, d0), c1 - c0, d1 - d0, fc="#c9b28f", ec="#8a7350", lw=1, alpha=0.7,
                           label="contact block" if k == 0 else None))
    ax.add_patch(Rectangle((CAV[0] - 0.1, CAV[1] - 0.1), 0.2, 0.2, fc="#9467bd", ec="none", alpha=0.6,
                           label="Cav (0.2 x 0.2 mm)"))
    ax.plot(*FEATURE_CAP, "D", color="grey", ms=5, label="2026-11-14 reference feature")
    for (name, (u, v)), c in zip(spot.items(), (CAP_C, ZP_C)):
        ax.plot(u, v, "o", ms=9 if k else 6, mfc="none", mec=c, mew=2, label=f"{name} spot")
    for (day, (u, v)), c, mk in zip(srn_axis.items(), (OLD_C, NEW_C), ("+", "x")):
        ax.plot(u, v, mk, ms=11 if k else 8, mew=2, color=c, label=f"SRn axis {day}")
    ax.plot(0, 0, ".", color="black", ms=4)
    ax.set_aspect("equal")
    ax.tick_params(labelsize=7)
    ax.set_xlabel("plate x (mm)", fontsize=8)
    ax.set_ylabel("plate y (mm)", fontsize=8)
axs[0].set_xlim(-10, 10)
axs[0].set_ylim(-10.5, 13)
axs[0].set_title("Gating plate, front view (tab up)", fontsize=9)
axs[0].add_patch(Rectangle((-0.6, -0.6), 3.9, 5.8, fill=False, ec="black", ls=":", lw=1))
axs[0].legend(fontsize=6.5, loc="lower left", framealpha=0.9)
axs[1].set_xlim(-0.6, 3.3)
axs[1].set_ylim(-0.6, 5.2)
axs[1].set_title("Zoom (dotted box)", fontsize=9)
(uc, vc), (uz, vz) = spot["capillary"], spot["zone plate"]
axs[1].annotate("", (uz, vz), (uc, vc), arrowprops=dict(arrowstyle="->", color="black", lw=1))
axs[1].text((uc + uz) / 2, (vc + vz) / 2 - 0.28, f"+{uz - uc:.2f} / +{vz - vc:.2f} mm", ha="center", fontsize=7.5)
(ao, bo), (an, bn) = srn_axis.values()
axs[1].annotate("", (an, bn), (ao, bo), arrowprops=dict(arrowstyle="->", color="black", lw=1))
axs[1].text(an + 0.12, bn + 0.15, f"+{an - ao:.3f} / +{bn - bo:.3f} mm", fontsize=7.5)
fig.suptitle(f"Where the beam meets the plate at the same motors (ST {REF.st}, SZ {REF.sz}, SRn 120 / SRz 0, piezo "
             "centred) and the SRn axis", fontsize=9)
fig.tight_layout()
fig.savefig(FIGS / "zp_schem_front.png", dpi=170)
plt.close(fig)

# ------------------------------------------------------------------ (b) top view (horizontal plane, SRz 0)
lab = {}
# same zone-plate spot for both: the axes are compared relative to the same plate point (the tracked point)
for name, cfg in (("2026-11-14", replace(CAP, st0=ZP.st0, sz0=ZP.sz0)), ("2026-11-15", ZP)):
    m = StageModel(cfg, plate)
    p = m.lab_to_plate(REF, np.zeros(3))  # point at the analyzer focus at REF (nearly the tracked point)
    axis = m._translation(REF) + B @ m._srz_axis_local()
    lab[name] = axis[:2]  # x across the beam, y along the beam; the point on the beam is at (0, 0)
d = lab["2026-11-15"] - lab["2026-11-14"]

fig, ax = plt.subplots(figsize=(7.4, 5.6))
t, n = T_HAT[:2], N_HAT[:2]
s = np.linspace(-3.2, 3.2, 2)
surf = np.outer(s, t)
ax.plot(surf[:, 0], surf[:, 1], color="#7a8794", lw=4, solid_capstyle="butt", label="sample surface (Cav)")
back = surf + 5.75 * n  # plate back face, w = 0 (H 0.748 + 5.0 behind the surface; +SN = towards -w)
ax.plot(back[:, 0], back[:, 1], color="#bbbbbb", lw=2, ls="--", label="plate back face")
ax.annotate("", (0, 2.6), (0, -2.6), arrowprops=dict(arrowstyle="->", color="#9467bd", lw=2))
ax.text(0.12, -1.6, "beam (zone plate)", color="#9467bd", fontsize=8)
ax.plot(0, 0, "*", ms=12, color="black", label="tracked point at the analyzer focus")
for (name, xy), c, mk in zip(lab.items(), (OLD_C, NEW_C), ("+", "x")):
    ax.plot(*xy, mk, ms=13, mew=2.5, color=c, label=f"SRz axis {name}")
ax.annotate("", lab["2026-11-15"], lab["2026-11-14"], arrowprops=dict(arrowstyle="->", color="black", lw=1.2))
ax.text(lab["2026-11-15"][0] + 0.35, lab["2026-11-15"][1] - 0.1,
        f"{d[0]:+.2f} mm across\n{d[1]:+.2f} mm along the beam", ha="left", va="center", fontsize=8)
o = np.array([-3.4, 1.0])
for vec, label in ((t, "+ST"), (n, "+SN")):
    ax.annotate("", o + 0.9 * vec, o, arrowprops=dict(arrowstyle="->", color="grey", lw=1.2))
    ax.text(*(o + 1.05 * vec), label, fontsize=8, color="grey", ha="center", va="center")
ax.annotate("", (-1.7, -1.7), (-0.35, -0.35), arrowprops=dict(arrowstyle="->", color="grey", lw=1.2))
ax.text(-1.8, -1.95, "towards the analyzer", fontsize=8, color="grey", ha="center", va="top")
ax.set_aspect("equal")
ax.set_xlim(-4, 4)
ax.set_ylim(-4, 6.8)
ax.set_xlabel("lab x: across the beam (mm)", fontsize=8)
ax.set_ylabel("lab y: along the beam (mm, + downstream)", fontsize=8)
ax.tick_params(labelsize=7)
ax.legend(fontsize=6.5, loc="upper left")
ax.set_title("Top view at SRn 120 / SRz 0: SRz axis relative to the tracked point", fontsize=9)
fig.tight_layout()
fig.savefig(FIGS / "zp_schem_top.png", dpi=170)
plt.close(fig)

out = {"spot": spot, "srn_axis": srn_axis, "srz_axis_lab": {k: v.tolist() for k, v in lab.items()},
       "srz_shift_lab": d.tolist(),
       "srz_offsets": {"2026-11-14": (CAP.srz_offset_t, CAP.srz_offset_n), "2026-11-15": (ZP.srz_offset_t, ZP.srz_offset_n)},
       "st0_sz0": {"capillary": (CAP.st0, CAP.sz0), "zone plate": (ZP.st0, ZP.sz0)}}
(SPEM / "zp_schem.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print(json.dumps(out, indent=1))
