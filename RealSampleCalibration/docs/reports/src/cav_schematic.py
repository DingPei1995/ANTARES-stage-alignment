"""Three top-view schematics: why SN has to be corrected after an SRz rotation (Cav test, 2026-11-14).

(a) SRn 120 / SRz 0 as in SPEM 19-48-34: the surface lies in the analyzer focal plane, the beam spot is at the focus.
(b) SRz turned, SN kept and the sample brought back onto the beam with ST only: the spot leaves the focal plane.
(c) SRz turned with SN corrected (positions of SPEM 20-06-03): the spot is back at the analyzer focus.
All positions from the stage model (calibration_2026-11-14_173743_capillary.json). Lab frame, top view: x right,
y along the beam; the analyzer looks along -n, its focal plane is the line along ST through the focus.
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams.update({"font.size": 10})
import numpy as np

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))
from quickalignment.core.calibration import CalibrationStore  # noqa: E402
from quickalignment.core.geometry import PLATES  # noqa: E402
from quickalignment.core.stage import N_HAT, T_HAT, MotorPositions, StageModel  # noqa: E402

D = Path(__file__).parent / "spem"
a, b = np.load(D / "cav_before.npz"), np.load(D / "cav_after.npz")
rec = next(x for x in CalibrationStore(ROOT / "configs").records()
           if x.path.name == "calibration_2026-11-14_173743_capillary.json")
plate = PLATES["gating"]
model = StageModel(rec.config, plate)
U, V, H = 2.687, 4.666, 0.748  # Cav on the plate (mm)
W = 5.0 + H


def mot(d):
    return MotorPositions(st=float(d["m_st"]), sz=float(d["m_sz"]), sn=float(d["m_sn"]), srn=float(d["m_srn"]),
                          srz=float(d["m_srz"]))


m_a, m_c = mot(a), mot(b)
m_b = model.motors_on_beam(U, V, W, srn=m_c.srn, srz=m_c.srz, sn=m_a.sn)  # SN kept, ST / SZ to the beam
CASES = [("(a) SRn 120 / SRz 0 - SPEM 19-48-34", m_a, "#1f77b4"),
         (f"(b) SRz {m_c.srz:.1f}, SN kept at {m_a.sn:.2f}", m_b, "#d62728"),
         (f"(c) SRz {m_c.srz:.1f}, SN corrected to {m_c.sn:.2f} - SPEM 20-06-03", m_c, "#2ca02c")]


def xy(p):
    return np.asarray(p)[..., :2]


def draw(ax, title, m, col):
    lim = 4.2
    # beam (along +y) and analyzer focal plane (line along ST through the focus)
    ax.annotate("", xy=(0, lim * 0.95), xytext=(0, -lim), arrowprops=dict(arrowstyle="-|>", color="#e6a700", lw=2))
    ax.text(0.12, -lim + 0.6, "X-ray beam", color="#b38200", fontsize=10.4, rotation=90, va="bottom")
    s = np.linspace(-lim * 1.4, lim * 1.4, 2)
    ax.plot(s * T_HAT[0], s * T_HAT[1], "--", color="grey", lw=1)
    lp = -2.9 * T_HAT
    ax.text(lp[0] - 0.25, lp[1] - 0.25, "analyzer focal plane", color="grey", fontsize=9.8, rotation=-45,
            ha="center", va="center")
    # analyzer: lens axis along -n towards the lower left
    tip = -2.9 * N_HAT
    ax.annotate("", xy=xy(-0.45 * N_HAT), xytext=xy(tip), arrowprops=dict(arrowstyle="-|>", color="black", lw=1.4))
    ax.text(tip[0] - 0.2, tip[1] - 0.45, "analyzer", fontsize=10.4, ha="center")
    # motor directions
    o = np.array([2.6, -1.3])
    for vec, lab in ((T_HAT, "+ST"), (N_HAT, "+SN")):
        ax.annotate("", xy=o + 0.9 * vec[:2], xytext=o, arrowprops=dict(arrowstyle="-|>", color="#555", lw=1))
        ax.text(*(o + 1.15 * vec[:2]), lab, fontsize=9.1, color="#555", ha="center", va="center")
    # plate riser (top at w = 5) and Cav substrate (top at w = 5 + H), cut at the height of the sample point
    u0, u1 = plate.riser_bounds()[0], plate.riser_bounds()[2]
    riser = np.array([model.plate_to_lab(m, u, V, w) for u, w in ((u0, 0), (u1, 0), (u1, 5.0), (u0, 5.0), (u0, 0))])
    ax.fill(riser[:, 0], riser[:, 1], color="#c9ccd1", zorder=1)
    ax.plot(riser[:, 0], riser[:, 1], color="#8a8f98", lw=0.8, zorder=1)
    sub = np.array([model.plate_to_lab(m, u, V, w) for u, w in
                    ((U - 2, 5.0), (U + 2, 5.0), (U + 2, W), (U - 2, W), (U - 2, 5.0))])
    ax.fill(sub[:, 0], sub[:, 1], color=col, alpha=0.35, zorder=2)
    ax.plot(sub[:, 0], sub[:, 1], color=col, lw=1, zorder=2)
    top = np.array([model.plate_to_lab(m, u, V, W) for u in (U - 2, U + 2)])
    ax.plot(top[:, 0], top[:, 1], color=col, lw=2.6, zorder=3, label="Cav surface")
    # beam spot on the surface, analyzer focus
    hit = model.beam_hit(m, W)
    dist = float(np.linalg.norm(hit))
    ax.plot(0, 0, "o", mfc="none", mec="black", ms=11, mew=1.5, zorder=5)
    ax.plot(hit[0], hit[1], "*", color="red", ms=13, zorder=6)
    if dist > 0.05:
        ax.annotate("", xy=(0.45, hit[1]), xytext=(0.45, 0), arrowprops=dict(arrowstyle="<->", color="red", lw=1.2))
        dsn = (hit @ N_HAT)
        ax.text(0.6, hit[1] / 2 - 0.1, f"{dist:.2f} mm along the beam\n(= {abs(dsn):.2f} mm along SN)\nfrom the analyzer focus",
                color="red", fontsize=10.4, va="center", zorder=7,
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.85))
        ax.text(-0.35, hit[1] - 0.35, "beam spot", color="red", fontsize=9.8, ha="right", va="center")
    else:
        ax.text(-3.95, -3.2, f"spot at the analyzer\nfocus (within {max(1000 * dist, 1):.0f} µm)",
                color="#1a7f1a", fontsize=10.4, ha="left", va="top")
    ax.text(0.25, -0.45, "analyzer focus", fontsize=9.8)
    ax.set_title(title, fontsize=11.7, color=col)
    ax.text(0.02, 0.98, f"ST {m.st:.3f}  SZ {m.sz:.3f}\nSN {m.sn:.3f}  SRz {m.srz:.1f}", transform=ax.transAxes,
            fontsize=9.8, va="top", family="monospace")
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.set_aspect("equal")
    ax.set_xlabel("x (mm), lab, top view", fontsize=9.8)
    ax.set_ylabel("y (mm), along the beam", fontsize=9.8)
    ax.tick_params(labelsize=7)
    return dist


dists = []
for i, (title, m, col) in enumerate(CASES):
    fig, ax = plt.subplots(figsize=(5.4, 5.4))
    dists.append(draw(ax, title, m, col))
    fig.tight_layout()
    fig.savefig(D / f"cav_sn_{'abc'[i]}.png", dpi=150)
    plt.close(fig)
np.savez(D / "cav_schematic.npz", dist=np.array(dists), st_b=m_b.st, sz_b=m_b.sz, sn_b=m_b.sn,
         dsn=float(model.beam_hit(m_b, W) @ N_HAT))
print("spot from the analyzer focus (mm):", np.round(dists, 3), "case b motors", round(m_b.st, 3), round(m_b.sz, 3),
      round(m_b.sn, 3))
