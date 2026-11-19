"""Figures and numbers of 2026-11-17_zp_capillary_geometry.pdf (run from anywhere; writes report_figs/ and numbers.json)."""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "src"))

from quickalignment.core.stage import N_HAT, T_HAT, Z_HAT  # noqa: E402
from quickalignment.optics import OpticsGeometry, OpticsGeometryConfig, OpticsMotors  # noqa: E402
from quickalignment.optics.nxs import read_motors  # noqa: E402
from quickalignment.optics.schematic3d import VIEWS, draw  # noqa: E402

FIGS = HERE / "report_figs"
FIGS.mkdir(exist_ok=True)
g = OpticsGeometry(OpticsGeometryConfig.load(ROOT / "OpticsGeometry" / "optics_geometry.json"))
zp, cap = g.config.zone_plate, g.config.capillary
SN_F = -0.798260207455943

# ---- 3-D views -------------------------------------------------------------------------------------------
zp_mode = OpticsMotors(zps=zp.zps, zpx=zp.zpx, zpz=zp.zpz, cps=0, cpx=0, cap_rz=cap.cap_rz, cap_rx=cap.cap_rx)
cap_mode = OpticsMotors(zps=zp.zps_parked, zpx=zp.zpx, zpz=cap.zpz, cps=cap.cps, cpx=cap.cpx,
                        cap_rz=cap.cap_rz, cap_rx=cap.cap_rx)
from matplotlib.lines import Line2D  # noqa: E402

LEGEND = [Line2D([], [], color=c, lw=2, ls=ls, label=t) for c, ls, t in (
    ("#EF9F27", "-", "ZP beam (reference line, +y)"), ("#7F77DD", "-", "zone plate"),
    ("#1D9E75", "-", "capillary"), ("#1D9E75", "--", "capillary beam"),
    ("#888780", "-", "sample (45 deg) / analyzer"), ("#D85A30", "-", "motor + directions"),
    ("#378ADD", "-", "lab axes"))]
for tag, m in (("zp", zp_mode), ("cap", cap_mode)):
    fig = plt.figure(figsize=(10, 7.5))
    ax = fig.add_subplot(projection="3d")
    draw(ax, g, m, view="perspective", labels="all")
    fig.subplots_adjust(0, 0, 1, 1)
    fig.savefig(FIGS / f"persp_{tag}.png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    fig = plt.figure(figsize=(15, 5.6))
    for i, view in enumerate(list(VIEWS)[1:]):
        ax = fig.add_subplot(1, 3, i + 1, projection="3d")
        draw(ax, g, m, view=view, labels="none")
        ax.set_title(view, fontsize=12)
    fig.legend(handles=LEGEND, loc="lower center", ncol=4, fontsize=10, frameon=False)
    fig.subplots_adjust(0, 0.1, 1, 0.95, wspace=0.05)
    fig.savefig(FIGS / f"ortho_{tag}.png", dpi=120, bbox_inches="tight")
    plt.close(fig)

# ---- data --------------------------------------------------------------------------------------------------
cav_cap, _ = read_motors(ROOT / "Cav" / "Cav_2026-11-14_19-48-34.nxs")
cav_zp, _ = read_motors(ROOT / "Cav" / "Cav_2026-11-15_11-13-55.nxs")
today_zp = OpticsMotors(zps=54.22, zpx=0.47, zpz=23.51, cps=0, cpx=0, cap_rz=-0.408, cap_rx=3.886)
today_cap = OpticsMotors(zps=-20, zpx=0.47, zpz=3.24, cps=61.34, cpx=57.14, cap_rz=-0.408, cap_rx=3.886)
stage = {"cav_cap": {"st": -4.2981, "sz": 36.361, "sn": -0.0493}, "cav_zp": {"st": -3.4982, "sz": 36.538, "sn": -0.0517},
         "today_zp": {"st": -1.55, "sz": 41.25, "sn": -0.15}, "today_cap": {"st": -1.75, "sz": 41.25, "sn": -0.15}}


def cross(dst, dsz):
    """Capillary spot minus ZP spot across the beam (x, z), from the stage moves between the two optics."""
    d = dst * T_HAT + dsz * Z_HAT
    return float(d[0]), float(d[2])


model_x, model_z = cross(*(np.array([cap.focus[0] * np.sqrt(2), cap.focus[2]])))
cav_x, cav_z = cross(stage["cav_cap"]["st"] - stage["cav_zp"]["st"], stage["cav_cap"]["sz"] - stage["cav_zp"]["sz"])
tod_x, tod_z = cross(stage["today_cap"]["st"] - stage["today_zp"]["st"], 0.0)

zp_f = g.zone_plate_focus(today_zp)
cap_b = g.capillary_beam(today_cap)
rows_h = []
for h in (0.1, 0.2, 0.3):
    s = -0.15 - (SN_F + h)
    hit_zp = np.array([0.0, s * np.sqrt(2), 0.0])
    hit_cap_meas = hit_zp - 0.2 * T_HAT
    rows_h.append({"H": h, "surface_y": float(hit_zp[1]), "zp_focus_minus_surface": float(zp_f[1] - hit_zp[1]),
                   "cap_focus_minus_spot": float((cap_b.focus - hit_cap_meas) @ cap_b.direction)})
h_zp = -0.15 - SN_F - zp_f[1] / np.sqrt(2)
h_zp96 = -0.15 - SN_F - (zp_f[1] / 0.96) / np.sqrt(2)

numbers = {
    "model_cap_spot": cap.focus, "model_dst": float(cap.focus[0] * np.sqrt(2)), "model_dsz": cap.focus[2],
    "cav": {"dst": stage["cav_cap"]["st"] - stage["cav_zp"]["st"], "dsz": stage["cav_cap"]["sz"] - stage["cav_zp"]["sz"],
            "x": cav_x, "z": cav_z},
    "today": {"dst": -0.20, "dsz": 0.0, "x": tod_x, "z": tod_z},
    "gap_x": tod_x - model_x, "gap_z": tod_z - model_z,
    "zp_focus_today": zp_f.tolist(), "cap_focus_today": cap_b.focus.tolist(), "cap_dir_today": cap_b.direction.tolist(),
    "thickness_rows": rows_h, "h_from_zp": float(h_zp), "h_from_zp_096": float(h_zp96),
    "motors": {"cav_cap": vars(cav_cap), "cav_zp": vars(cav_zp), "today_zp": vars(today_zp), "today_cap": vars(today_cap)},
}
(HERE / "numbers.json").write_text(json.dumps(numbers, indent=2), encoding="utf-8")

# ---- spots across the beam -----------------------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(7.2, 5.4))
ax.axhline(0, color="#ccc", lw=0.6)
ax.axvline(0, color="#ccc", lw=0.6)
ax.plot(0, 0, "o", color="#7F77DD", ms=9, label="ZP spot (reference line)")
ax.errorbar(model_x, model_z, xerr=0.1 / np.sqrt(2), yerr=0.1, fmt="s", color="#1D9E75", ms=8, capsize=3,
            label="capillary, config (Cav 11-14 vs 11-15)")
ax.errorbar(tod_x, tod_z, xerr=0.02, yerr=0.02, fmt="D", color="#D85A30", ms=8, capsize=3,
            label="capillary, test set 2026-11-17")
ax.annotate("", xy=(tod_x, tod_z), xytext=(model_x, model_z),
            arrowprops=dict(arrowstyle="->", color="#444", lw=1.2, ls="--"))
ax.text((model_x + tod_x) / 2 + 0.02, (model_z + tod_z) / 2 - 0.05,
        f"+{tod_x - model_x:.2f} mm x\n+{tod_z - model_z:.2f} mm z", fontsize=9, color="#444")
o = np.array([0.25, -0.33])
for d, lab in (((-0.1, 0), "+CPX / +ZPX"), ((0, 0.1), "+ZPZ"), ((0.1, 0), "+Cap Rz x L (provisional)"),
               ((0, -0.1), "-Cap Rx x L")):
    ax.annotate("", xy=o + d, xytext=o, arrowprops=dict(arrowstyle="->", color="#378ADD", lw=1.2))
    ax.text(*(o + 1.25 * np.array(d) + (0, 0.012)), lab, fontsize=8, color="#378ADD",
            ha="center" if d[0] == 0 else ("right" if d[0] < 0 else "left"))
ax.set_xlabel("x across the beam (mm, + = away from the analyzer)")
ax.set_ylabel("z (mm, up)")
ax.set_xlim(-0.8, 0.6)
ax.set_ylim(-0.5, 0.25)
ax.set_aspect("equal")
ax.legend(loc="upper left", fontsize=8)
ax.set_title("Capillary spot relative to the ZP spot, seen along the beam", fontsize=10)
fig.tight_layout()
fig.savefig(FIGS / "spots.png", dpi=140)
plt.close(fig)

# ---- rotation needed vs pivot distance ------------------------------------------------------------------
L = np.linspace(20, 600, 300)
fig, ax = plt.subplots(figsize=(7.2, 4.2))
for d, lab, c in ((tod_x - model_x, f"Cap Rz for {tod_x - model_x:.2f} mm in x", "#D85A30"),
                  (tod_z - model_z, f"Cap Rx for {tod_z - model_z:.2f} mm in z", "#1D9E75")):
    ax.plot(L, np.degrees(np.arctan(d / L)), color=c, label=lab)
ax.axhline(abs(today_cap.cap_rx - cav_cap.cap_rx), color="#1D9E75", ls=":", lw=1,
           label=f"|Cap Rx change| read: {abs(today_cap.cap_rx - cav_cap.cap_rx):.4f} deg (wrong sign)")
ax.set_xlabel("pivot -> focus distance L (mm)")
ax.set_ylabel("rotation needed (deg)")
ax.set_yscale("log")
ax.set_ylim(0.005, 2)
ax.grid(True, which="both", alpha=0.3)
ax.legend(fontsize=8)
ax.set_title("Rotation that would move the capillary focus by the observed gap", fontsize=10)
fig.tight_layout()
fig.savefig(FIGS / "pivot.png", dpi=140)
plt.close(fig)
print(json.dumps({k: numbers[k] for k in ("model_dst", "model_dsz", "cav", "today", "gap_x", "gap_z", "h_from_zp",
                                          "h_from_zp_096", "thickness_rows")}, indent=1))
_ = N_HAT
