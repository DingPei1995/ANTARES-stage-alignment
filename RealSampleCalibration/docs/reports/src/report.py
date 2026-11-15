"""English PDF report of the 2026-11-14 capillary real-sample calibration."""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))
from quickalignment.core.calibration import CalibrationStore
from quickalignment.core.geometry import PLATES
from quickalignment.core.stage import StageModel
from quickalignment.realsample.fit import MeasurementSet, fit_real_sample_calibration, on_beam, optic_focus_of

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image as RLImage, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT_DIR = ROOT / "RealSampleCalibration" / "docs" / "reports"
OUT_DIR.mkdir(parents=True, exist_ok=True)
PDF = OUT_DIR / "2026-11-14_capillary_real_sample_calibration.pdf"
WORK = Path(__file__).parent / "report_figs"
WORK.mkdir(exist_ok=True)

# ------------------------------------------------------------------------------------------------ data
records = {r.path.name: r for r in CalibrationStore(ROOT / "configs").records()}
NEW = records["calibration_2026-11-14_172237_capillary.json"]
OLD = records["calibration_2026-10-24_235500_capillary.json"]
plate = PLATES["gating"]
UVW = tuple(NEW.check["reference_uvw"])
m_new, m_old = StageModel(NEW.config, plate), StageModel(OLD.config, plate)
f_new, f_old = NEW.check["optic_focus"], optic_focus_of(OLD, plate)
SN = -0.3

# corrections after the calibration (0.5 mm substrate, CPS 61.51) and the SPEM test (scratchpad spem_*.py)
NEWREC = records["calibration_2026-11-14_173743_capillary.json"]
OLDSNF = NEW.config.sn_f
SPEM = Path(__file__).parent / "spem"
SH = {k: float(v) for k, v in np.load(SPEM / "shift.npz").items() if np.ndim(v) == 0}
EXP_PIX, EXP_PIY = SH["du"], -SH["dv"]  # plate shift of the on-beam point -> map shift (PIY as seen in the maps)
RES_PIX, RES_PIY = SH["d_pix"] - EXP_PIX, SH["d_piy"] - EXP_PIY
TEST_RES = float(np.hypot(RES_PIX, RES_PIY))
import shutil  # noqa: E402
shutil.copy(SPEM / "compare.png", WORK / "spem_compare.png")

# Cav test (cav_maps.py, cav_compare.py, cav_schematic.py)
CA, CB = np.load(SPEM / "cav_before.npz"), np.load(SPEM / "cav_after.npz")
CS = {k: float(v) for k, v in np.load(SPEM / "cav_shift.npz").items() if np.ndim(v) == 0}
CSCH = np.load(SPEM / "cav_schematic.npz")
CAV_RES_PIX, CAV_RES_PIY = CS["d_pix"] - CS["exp_pix"], CS["d_piy"] - CS["exp_piy"]
CAV_RES = float(np.hypot(CAV_RES_PIX, CAV_RES_PIY))
CAV_OFF = float(CSCH["dist"][1])  # spot from the analyzer focus with SN kept (mm, along the beam)
for nm in ("cav_compare.png", "cav_sn_a.png", "cav_sn_b.png", "cav_sn_c.png"):
    shutil.copy(SPEM / nm, WORK / nm)


def cm(d, a):
    return float(d[f"m_{a}"])

sets = [MeasurementSet(**s) for s in NEW.check["sets"]]
LABEL = {"1 reference": "1  SRn 120 / SRz 0 (reference)", "2 SRn rotated": "2  SRn 140 / SRz 0",
         "3 SRz rotated": "3  SRn 120 / SRz -10", "4 SRn rotated (check)": "4  SRn 100 / SRz 0 (check)",
         "6 SRn 100 SRz -5": "5  SRn 100 / SRz -5 (check)"}

# old configuration as it was (raw) and moved onto the measured set 1 (ST0, SZ0, SN_f, optic from set 1)
anch = fit_real_sample_calibration([sets[0]], plate, UVW, base=OLD.config, mode="full", params=("st0", "sz0", "sn_f"))
m_anch, f_anch = StageModel(anch.config, plate), anch.optic_focus
# fit of the first three sets only (the prediction used for sets 4 and 5)
fit3 = fit_real_sample_calibration(sets[:3], plate, UVW, base=OLD.config, mode="full")
m3, f3 = StageModel(fit3.config, plate), fit3.optic_focus


def pred(model, focus, s):
    return on_beam(model, UVW, s.srn, s.srz, SN, 150, 150, focus)


rows_pred = []
for s in sets:
    raw, an, p3, nw = pred(m_old, f_old, s), pred(m_anch, f_anch, s), pred(m3, f3, s), pred(m_new, f_new, s)
    rows_pred.append((s, raw, an, p3, nw))

# full fit residuals (new config)
res_new = fit_real_sample_calibration(sets, plate, UVW, base=OLD.config, mode="full")
sig = res_new.sigma

# old vs new over a range of rotations, both moved onto set 1 (what changed in the mechanics)
angles = [(srn, srz) for srn in (90, 100, 110, 120, 130, 140, 150) for srz in (-15, -10, -5, 0)]
diff = []
for srn, srz in angles:
    a = on_beam(m_anch, UVW, srn, srz, SN, 150, 150, f_anch)
    b = on_beam(m_new, UVW, srn, srz, SN, 150, 150, f_new)
    diff.append((srn, srz, b[0] - a[0], b[1] - a[1], b[2] - a[2]))

# coupling of ST0 with SN_f: how much the on-beam ST moves for 0.3 mm of SN at the reference rotation
st_a = on_beam(m_new, UVW, 120, 0, SN, 150, 150, f_new)[0]
st_b = on_beam(m_new, UVW, 120, 0, SN + 0.3, 150, 150, f_new)[0]
D_ST_PER_03_SN = st_b - st_a

# ------------------------------------------------------------------------------------------------ figures
img = Image.open(ROOT / "Photos" / "20261111_103232.JPG")
fig, axs = plt.subplots(1, 2, figsize=(10, 4.6), gridspec_kw={"width_ratios": [1.25, 1]})
x0, y0, x1, y1 = 2500, 0, 6600, 3950
axs[0].imshow(img.crop((x0, y0, x1, y1)).reduce(4), extent=(x0, x1, y1, y0))
corners = np.array([[2597, 110], [6482, 68], [6520, 3805], [2645, 3848], [2597, 110]])
axs[0].plot(corners[:, 0], corners[:, 1], color="#2ca02c", lw=1.2, label="sample area (registration)")
axs[0].plot(5021, 2569, "o", mfc="none", mec="red", ms=10, mew=2, label="reference feature")
axs[0].plot(5086, 2594, "x", color="orange", ms=8, mew=2, label="first (wrong) reading")
axs[0].legend(loc="upper left", fontsize=7, framealpha=0.85)
axs[0].set_title("Gating plate, photo 20261111_103232", fontsize=10)
axs[0].set_xlabel("photo x (px)", fontsize=8)
axs[0].set_ylabel("photo y (px)", fontsize=8)
axs[0].tick_params(labelsize=7)
zx0, zy0, zx1, zy1 = 4700, 2350, 5250, 2900
axs[1].imshow(img.crop((zx0, zy0, zx1, zy1)), extent=(zx0, zx1, zy1, zy0))
axs[1].plot(5021, 2569, "o", mfc="none", mec="red", ms=14, mew=2)
axs[1].plot(5086, 2594, "x", color="orange", ms=10, mew=2)
axs[1].set_title("Top-right corner of the lower-right gold pad", fontsize=10)
axs[1].tick_params(labelsize=7)
fig.tight_layout()
fig.savefig(WORK / "photo.png", dpi=170)
plt.close(fig)

fig, ax = plt.subplots(figsize=(8, 3.2))
names = [LABEL[s.name].split("  ")[1].split(" (")[0] for s in sets]
rmap = {n: (a, b, c) for n, a, b, c in res_new.residuals}
omap = dict(res_new.optic_residuals)
w = 0.25
xs = np.arange(len(sets))
ax.bar(xs - w, [1000 * rmap[s.name][0] for s in sets], w, label="ST", color="#1f77b4")
ax.bar(xs, [1000 * rmap[s.name][1] for s in sets], w, label="SZ", color="#ff7f0e")
ax.bar(xs + w, [1000 * (omap.get(s.name) or 0) for s in sets], w, label="CPS (mm)", color="#2ca02c")
ax.axhspan(-20, 20, color="grey", alpha=0.12, label="reading precision ±0.02 mm")
ax.axhline(0, color="black", lw=0.6)
ax.set_xticks(xs, names, fontsize=8)
ax.set_ylabel("model - measured (µm)", fontsize=8)
ax.tick_params(labelsize=8)
ax.set_ylim(-30, 30)
ax.legend(fontsize=7, ncol=4, loc="upper center")
ax.set_title("Residuals of the new configuration (5 sets, rms 6.7 µm)", fontsize=10)
fig.tight_layout()
fig.savefig(WORK / "residuals.png", dpi=170)
plt.close(fig)

fig, axs = plt.subplots(1, 3, figsize=(10, 3.0))
srns = sorted({a for a, _, *_ in diff})
for k, (title, idx) in enumerate([("ST", 2), ("SZ", 3), ("CPS", 4)]):
    for srz, col in zip((0, -5, -10, -15), ("#1f77b4", "#ff7f0e", "#2ca02c", "#d62728")):
        axs[k].plot(srns, [1000 * d[idx] for d in diff if d[1] == srz], "o-", ms=3, color=col, label=f"SRz {srz}")
    axs[k].axhspan(-50, 50, color="grey", alpha=0.12)
    axs[k].axhline(0, color="black", lw=0.6)
    axs[k].set_title(f"{title}: new - old (µm)", fontsize=9)
    axs[k].set_xlabel("SRn (deg)", fontsize=8)
    axs[k].tick_params(labelsize=7)
axs[0].legend(fontsize=7)
fig.suptitle("Old vs new configuration, both anchored on the measured set 1 (SN -0.3; grey: ±0.05 mm)", fontsize=9)
fig.tight_layout()
fig.savefig(WORK / "old_vs_new.png", dpi=170)
plt.close(fig)

# ------------------------------------------------------------------------------------------------ PDF
ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=ss["Heading1"], fontSize=15, spaceAfter=6, textColor=colors.HexColor("#1a3a5c"))
H2 = ParagraphStyle("H2", parent=ss["Heading2"], fontSize=12, spaceBefore=10, spaceAfter=4,
                    textColor=colors.HexColor("#1a3a5c"), keepWithNext=1)
B =ParagraphStyle("B", parent=ss["BodyText"], fontSize=9.2, leading=12.5, spaceAfter=4)
SM = ParagraphStyle("SM", parent=B, fontSize=8, leading=10.5, textColor=colors.HexColor("#444444"))
TC = ParagraphStyle("TC", parent=B, fontSize=8, leading=10, spaceAfter=0)


def table(data, widths, header=1, align="RIGHT"):
    data = [[Paragraph(f"<b>{c}</b>" if i < header else str(c), TC) if isinstance(c, str) and (len(c) > 22 or i < header)
             else c for c in row] for i, row in enumerate(data)]
    t = Table(data, colWidths=widths, repeatRows=header)
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8),
        ("FONT", (0, 0), (-1, header - 1), "Helvetica-Bold", 8),
        ("BACKGROUND", (0, 0), (-1, header - 1), colors.HexColor("#dce6f0")),
        ("ALIGN", (1, 0), (-1, -1), align),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9aa9b8")),
        ("ROWBACKGROUNDS", (0, header), (-1, -1), [colors.white, colors.HexColor("#f4f7fa")]),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return t


def f(v, n=3):
    return "-" if v is None else f"{v:.{n}f}"


def fig(path, width_mm):
    im = Image.open(path)
    w = width_mm * mm
    return RLImage(str(path), width=w, height=w * im.height / im.width)


story = []
story.append(Paragraph("ANTARES sample stage - capillary real-sample calibration", H1))
story.append(Paragraph("2026-11-14 &nbsp;|&nbsp; gating plate, capillary &nbsp;|&nbsp; fit "
                       "<b>calibration_2026-11-14_172237_capillary.json</b> (replaces 2026-10-24 23:55); configuration "
                       "in use: <b>calibration_2026-11-14_173743_capillary.json</b> (same fit with the 0.5 mm substrate, "
                       "CPS 61.51, section 8)", SM))
story.append(Spacer(1, 6))

story.append(Paragraph("1. Summary", H2))
story.append(Paragraph(
    "The stage was recalibrated on one sharp feature of a real sample (corner of a gold contact pad on a Si "
    "substrate) at five rotations. At the SN where the surface is in the analyzer focus (-0.3), the configuration "
    "of 2026-10-24 put the feature 0.97 mm off in ST and 0.39 mm off in SZ, with the capillary 2.2 CPS away from "
    "focus; it also expected that surface in focus at SN 0 instead of -0.3. The new configuration reproduces all five measured positions within 0.016 mm (rms 6.7 µm, reading "
    "precision 0.02 mm); the two check rotations were predicted from the first three sets within 0.034 mm before "
    "they were measured. The changes are mostly in the beam position (ST0, SZ0) and the capillary focus (CPS), "
    "consistent with a realignment of the capillary, and in SN_f, which was measured for the first time. The "
    "rotation axes changed little: within about 0.06 mm in ST / SZ over the measured range, and up to 0.16 mm along "
    "the beam at SRz -10 (the SRz axis along SN, the least known constant before). "
    f"<b>Test on the device (section 8): after turning from SRn 120 / SRz 0 to SRn 150 / SRz -10 to the predicted "
    f"ST / SZ / SN, two SPEM maps show the device at the same place within {TEST_RES:.0f} µm (tolerance 50 µm): "
    "the test is successful.</b> "
    f"<b>Second test on the graphene sample Cav (section 9): SRz turned by {cm(CB, 'srz'):.1f}° with SN corrected; the "
    f"sample stayed at the same place within {CAV_RES:.0f} µm and in the analyzer focus (same CPS).</b>", B))

kt = [["", "previous (2026-10-24)", "new (2026-11-14, measured)"],
      ["Feature at SRn 120 / SRz 0, SN -0.3: ST", f(pred(m_old, f_old, sets[0])[0]), "-2.900"],
      ["   SZ", f(pred(m_old, f_old, sets[0])[1]), "40.240"],
      ["   CPS in focus", f(pred(m_old, f_old, sets[0])[2], 2), "61.45"],
      ["SN with the 0.525 mm surface at the analyzer focus", "0.000", "-0.300"],
      ["rms of the fit", "22 µm (4 sets, 2 samples)", "6.7 µm (5 sets, 1 feature)"],
      ["SRz axis uncertainty (ST / SN)", "± 0.23 / ± 0.39 mm", f"± {sig['srz_offset_t']:.2f} / ± {sig['srz_offset_n']:.2f} mm"]]
story.append(table(kt, [74 * mm, 44 * mm, 44 * mm]))

story.append(Paragraph("2. Sample, reference feature and plate photo", H2))
story.append(Paragraph(
    "Gating sample plate (contact block, 4 screws) with a Si substrate (H = 0.525 mm above the plate surface) "
    "carrying a gated device. Reference feature: the top-right corner of the lower-right gold pad. The plate photo "
    "20261111_103232 (9600 x 5400 px, 354 px/mm) was registered on the four corners of the sample area; the feature "
    f"is at plate x = {UVW[0]:.3f} mm, y = {UVW[1]:.3f} mm. A first reading (orange cross) was 65 px (0.18 mm) to "
    "the right of the corner, because the zoomed photo grid was read without its margin offset; it was corrected "
    "after the user pointed it out. With a single feature, any error of the photo position goes entirely into ST0 "
    "and SZ0 (estimated ± 0.05 mm here).", B))
story.append(fig(WORK / "photo.png", 170))
story.append(Paragraph("Figure 1. Plate photo with the registered sample area and the reference feature.", SM))

story.append(Paragraph("3. Procedure", H2))
steps = [
    "Prediction from the 2026-10-24 configuration at SRn 120 / SRz 0: ST -2.234, SZ 39.855 (SN 0 for a 0.525 mm "
    "surface at the analyzer focus). The sample surface was found in the analyzer focus at <b>SN = -0.3</b>, not 0.",
    "<b>Set 1</b> (SRn 120 / SRz 0, at the analyzer focus): feature found at ST -2.90, SZ 40.24, SN -0.30, "
    "CPS 61.45, i.e. 0.67 mm / 0.39 mm from the prediction.",
    "Mode <b>full</b> (all constants fitted). The rotated sets were measured as the stage is normally run: "
    "<b>SN kept at -0.3</b>, the feature brought onto the beam with ST / SZ and the <b>capillary refocused</b> "
    "(the CPS then measures where the feature is along the beam).",
    "<b>Set 2</b> (SRn 140): ST -2.50, SZ 39.80, CPS 61.45. <b>Set 3</b> (SRz -10): ST -3.76, SZ 40.24, CPS 62.05.",
    "First fit: the program assumed every set to be at the analyzer focus. Set 3 was 0.6 mm away from it, so that "
    "fit was wrong (CPS residual 0.4, SRz axis moved by about 1.9 mm). The three sets were fitted again with the "
    "SN-kept sets entered as ST, SZ, CPS equations (exact, 2 redundant equations).",
    "From this fit, check positions were predicted. Positive SRz was avoided on request, so the second check was "
    "moved from SRn 120 / SRz +10 to SRn 100 / SRz -5.",
    "<b>Check 4</b> (SRn 100): ST -3.12, SZ 40.80 (predicted -3.125 / 40.790). <b>Check 5</b> (SRn 100 / SRz -5): "
    "ST -3.54, SZ 40.78, CPS 61.76 (predicted -3.574 / 40.790 / 61.764). Both within the 0.05 mm tolerance.",
    "Final fit of the five sets (7 redundant equations) and saved as the new capillary configuration.",
]
for i, s in enumerate(steps, 1):
    story.append(Paragraph(f"{i}. {s}", B))

story.append(Paragraph("4. Measurements and predictions", H2))
story.append(Paragraph(
    "All positions at SN = -0.3, PIX = PIY = 150 µm, positions read to ± 0.02 mm. Predictions are the ST / SZ / CPS "
    "putting the feature on the beam with SN = -0.3: (a) previous configuration as it was; (b) previous "
    "configuration moved onto the measured set 1 (its ST0, SZ0, SN_f and CPS taken from set 1, rotation axes kept); "
    "(c) fit of sets 1-3 (the prediction used for the checks); (d) new configuration.", B))
hdr = ["Set", "measured ST / SZ / CPS", "(a) previous", "(b) previous on set 1", "(c) fit of sets 1-3", "(d) new"]
data = [hdr]
for s, raw, an, p3, nw in rows_pred:
    cps = "-" if s.optic is None else f"{s.optic:.2f}"
    data.append([LABEL[s.name], f"{s.st:.2f} / {s.sz:.2f} / {cps}",
                 f"{raw[0]:.3f} / {raw[1]:.3f} / {raw[2]:.2f}", f"{an[0]:.3f} / {an[1]:.3f} / {an[2]:.2f}",
                 f"{p3[0]:.3f} / {p3[1]:.3f} / {p3[2]:.2f}", f"{nw[0]:.3f} / {nw[1]:.3f} / {nw[2]:.2f}"])
story.append(table(data, [42 * mm, 30 * mm, 27 * mm, 27 * mm, 27 * mm, 27 * mm]))
story.append(Spacer(1, 3))
story.append(Paragraph(
    "Column (b) shows what the old mechanics alone predict once the beam position is taken from set 1: deviations "
    "of up to 0.04 mm in ST, 0.04 mm in SZ and 0.16 in CPS. Column (c) was obtained before sets 4 and 5 were "
    "measured; its deviations there (at most 0.034 mm) are the real test of the calibration.", B))

story.append(KeepTogether([fig(WORK / "residuals.png", 160),
                           Paragraph("Figure 2. Residuals of the final fit per set (CPS residuals in mm of capillary "
                                     "travel; set 4 has no CPS).", SM)]))

story.append(Paragraph("5. New configuration compared with 2026-10-24 23:55", H2))
lab = {"st0": "ST0 (mm)", "sz0": "SZ0 (mm)", "sn_f": "SN_f (mm)", "srn_axis_u": "SRn axis x (mm)",
       "srn_axis_v": "SRn axis y (mm)", "srz_offset_t": "SRz axis offset along ST (mm)",
       "srz_offset_n": "SRz axis offset along SN (mm)", "optic_focus": "CPS at the analyzer focus"}
data = [["Constant", "previous", "new", "± 1 sigma", "change"]]
for p in ("st0", "sz0", "sn_f", "srn_axis_u", "srn_axis_v", "srz_offset_t", "srz_offset_n", "optic_focus"):
    o = f_old if p == "optic_focus" else getattr(OLD.config, p)
    n = f_new if p == "optic_focus" else getattr(NEW.config, p)
    data.append([lab[p], f(o, 4), f(n, 4), f(sig[p], 4), f"{n - o:+.4f}"])
story.append(table(data, [62 * mm, 25 * mm, 25 * mm, 22 * mm, 22 * mm]))
story.append(Spacer(1, 4))
story.append(Paragraph(
    "The constants are not independent: the SRz offsets are measured from the reference defined by ST0 and SN_f, "
    "so a change of the reference changes their values even if the axis does not move. Figure 3 therefore compares "
    "the two configurations by what they predict: both are moved onto the measured set 1 and the predicted "
    "positions of the feature are compared over SRn 90-150 and SRz -15 to 0. The difference stays below "
    f"{1000 * max(abs(d[2]) for d in diff):.0f} µm in ST, {1000 * max(abs(d[3]) for d in diff):.0f} µm in SZ and "
    f"{max(abs(d[4]) for d in diff):.2f} in CPS (mm along the beam). In ST and SZ the largest values are at the "
    "ends of the range (SRn 90 / 150, SRz -15), where the axes are extrapolated; inside the measured range "
    "(SRn 100-140, SRz -10 to 0) they are within about 0.06 mm, and within 0.04 mm at the measured points. Along the beam the difference grows with SRz: "
    "0.08 mm at SRz -5, 0.16 mm at SRz -10. This is the real correction of the SRz axis along SN, the least known "
    "constant in October; with SN kept it shows up as a refocus of the capillary. The large numbers in the table "
    "are otherwise mostly the new beam position and the new reference.", B))
story.append(KeepTogether([fig(WORK / "old_vs_new.png", 170),
                           Paragraph("Figure 3. New minus previous configuration (previous one moved onto set 1), "
                                     "for the feature at SN = -0.3. SZ does not depend on SRz: the four curves "
                                     "coincide.", SM)]))

story.append(Paragraph("6. Likely causes of the changes", H2))
causes = [
    ("Beam position on the stage: ST0 -0.66 mm, SZ0 +0.39 mm; capillary focus: CPS +1.76",
     "The most likely cause is a realignment of the capillary since 2026-10-24 (translation / pitch / yaw of the "
     "optic): the previous configuration already noted that SZ0 and the CPS reference depend on the capillary "
     "alignment. Smaller contributions: the seating of the plate on the holder (another mounting of the gating "
     "plate), and the photo position of the feature (± 0.05 mm, single feature, cannot be separated from ST0 / SZ0). "
     f"Part of the ST0 change is a change of reference rather than a movement: at SRn 120 a change of 0.3 mm in SN "
     f"moves the on-beam ST by {abs(D_ST_PER_03_SN):.2f} mm, and the previous ST0 was tied to an assumed SN_f "
     "(see next item)."),
    ("SN_f -0.30 mm",
     "SN_f was not measured in October: no set was at the analyzer focus, and SN_f = -0.525 was assumed so that "
     "the measured surfaces (SN about 0) were in the focal plane. Today the 0.525 mm surface was found in the "
     "analyzer focus at SN = -0.3, which fixes SN_f directly. The 0.3 mm can come from the assumed value itself, "
     "from the actual height of this sample stack (Si thickness, glue / silver paint under the substrate, height of "
     "this gating plate's riser), or from how the analyzer focus is judged. A sample of known thickness on this "
     "plate would separate these."),
    ("SRn axis: about 0.1 mm",
     "Within the uncertainty of the October fit, which used two samples, one of them without a photo (its position "
     "was fitted). No mechanical change is needed to explain it."),
    ("SRz axis: values -0.70 / -0.41 mm; effect up to 0.04 mm in ST and 0.16 mm along the beam at SRz -10",
     "The numerical change mostly follows the new ST0 / SN_f reference (Figure 3); what remains is a correction of "
     "about 0.1-0.2 mm of the axis position along SN, within the October uncertainty. The October SRz axis was known "
     "to ± 0.23 / ± 0.39 mm; it is now ± 0.06 / ± 0.08 mm. SRz was only used at 0, -5 and -10 deg; SRz > 0 and "
     "SRz < -10 are extrapolated."),
]
for t, txt in causes:
    story.append(Paragraph(f"<b>{t}.</b> {txt}", B))

story.append(Paragraph("7. Software changes made during this calibration", H2))
for txt in [
    "<b>SN-kept sets in the full calibration</b> (realsample/fit.py, agent/real_sample.py, MCP tools rsc_start, "
    "rsc_add_set, rsc_measure_set: parameter <i>sn_kept</i>). Set 1 goes to the analyzer focus (it fixes SN_f); "
    "the rotated sets keep its SN and refocus the optic, and enter the fit as ST, SZ, CPS. The CPS is now required "
    "in such a set. Before, such sets were silently fitted as if they were at the analyzer focus.",
    "<b>Expected positions follow the measurements</b>: after set 1 the other sets are predicted from set 1 and "
    "the previous rotation axes, after a fit from the fit (field <i>expected_from</i>). Extra sets at any angle "
    "(rsc_add_set) get their predicted position directly.",
    "<b>Test points keep SN</b> as in set 1 when the sets were measured that way, with the CPS to refocus.",
    "Workflow text for the agent, API.md regenerated; new tests. Full test suite: 203 passed.",
    "<b>Manual-annotation window</b> (agent/alignment.py, ui/annotate.py): the window started by the MCP server "
    "inherited the server's stdin / stdout pipes and hung at start-up on Windows, so it never appeared. It now "
    "starts detached from them (errors in window.log, reported if it fails to start) and comes to the front. Two "
    "tests that depended on the previous configuration being the newest were updated.",
]:
    story.append(Paragraph("• " + txt, B))

story.append(Paragraph("8. Corrections after the calibration and test on the device", H2))
story.append(Paragraph(
    "<b>Substrate thickness.</b> The Si substrate of the calibration sample is 0.500 mm thick, not 0.525 mm as "
    "assumed above. The five sets were fitted again with the reference feature at w = 5.500 mm: only SN_f "
    f"({OLDSNF:+.4f} -> {NEWREC.config.sn_f:+.4f}) and the SRz axis offset along SN "
    f"({NEW.config.srz_offset_n:+.4f} -> {NEWREC.config.srz_offset_n:+.4f}) move, both by +0.025 mm; all other "
    "constants and the residuals (rms 6.7 µm) are unchanged, as the data cannot tell the substrate thickness from "
    "SN_f. The thickness matters for samples of other heights. <b>CPS.</b> The CPS at the analyzer focus was set by "
    f"hand to 61.51 (fit: {NEW.check['optic_focus']:.4f}), the value used at the beamline. Both corrections are in "
    "<b>calibration_2026-11-14_173743_capillary.json</b>.", B))
story.append(Paragraph(
    "<b>Test.</b> Device D1 (junction of the three electrodes) was marked on the plate photo by hand. The photo is "
    "too blurred to see the electrodes; at SRn 120 / SRz 0 the device was found 0.10 mm (x) and 0.10 mm (y) from the "
    "marked point, at ST -1.92, SZ 40.03, SN -0.30, and the sample was corrected there (<i>found_here</i>). From "
    "this, the new configuration predicted the position at <b>SRn 150 / SRz -10</b> with SN corrected to put the "
    "device at the analyzer focus. At both positions a 300 x 300 µm SPEM map (piezo PIX / PIY, 10 µm steps, "
    "hν 95 eV, KE 84-92 eV) was measured and opened with ARPES viewer.", B))
tt = [["", "SRn 120 / SRz 0", "SRn 150 / SRz -10"],
      ["SPEM file", "Real_2026-11-14_18-08-53.nxs", "Real_2026-11-14_18-16-15.nxs"],
      ["ST / SZ / SN / CPS predicted", "(found) -1.920 / 40.030 / -0.300 / 61.51", "-1.767 / 39.940 / -0.449 / 61.51"],
      ["ST / SZ / SN / CPS in the file", "-1.921 / 40.040 / -0.300 / 61.51", "-1.766 / 39.932 / -0.452 / 61.51"],
      ["Device in map 2 relative to map 1 (PIX / PIY)", "", f"{SH['d_pix']:+.0f} / {SH['d_piy']:+.0f} µm (measured)"],
      ["   expected from the motor values in the files", "", f"{EXP_PIX:+.0f} / {EXP_PIY:+.0f} µm"],
      ["   prediction error", "", f"{RES_PIX:+.0f} / {RES_PIY:+.0f} µm, |d| = {TEST_RES:.0f} µm"]]
story.append(table(tt, [62 * mm, 54 * mm, 54 * mm]))
story.append(Spacer(1, 4))
story.append(Paragraph(
    "The piezo moves the sample in the plate frame (before SRn), so both maps are in plate coordinates and the "
    "device must appear at the same place if the prediction is right; the 30° SRn rotation does not rotate the "
    "map. Drawn as ARPES viewer draws ANTARES maps (PIX from large to small), the maps show the same three "
    "electrodes as the microscope photo: the wide electrode to the left, one up, one to the lower right (Figure 4). "
    f"The shift of the device between the two maps was measured by correlating the integrated intensity maps "
    f"(correlation {float(SH['corr']):.2f}, 0.1 px steps): {SH['d_pix']:+.0f} µm in PIX and {SH['d_piy']:+.0f} µm in PIY. "
    "Part of it comes from the motor values actually set, which differ by up to 10 µm from the predicted ones "
    f"(SZ 40.040 instead of 40.030 at SRn 120): the model gives {EXP_PIX:+.0f} / {EXP_PIY:+.0f} µm for these values. "
    f"What remains, <b>{TEST_RES:.0f} µm</b>, is the error of the prediction over a rotation that moved the stage by "
    "0.15 mm in ST, 0.09 mm in SZ and 0.15 mm in SN, within the 50 µm tolerance and the ± 20 µm reading of the "
    "found position. <b>The calibration predicts a rotation to SRn 150 / SRz -10 (outside the measured range "
    "SRn 100-140) correctly; the test is successful.</b> The device stayed at the analyzer focus: the CPS was "
    "kept at 61.51 and the spectra of both maps agree.", B))
story.append(KeepTogether([fig(WORK / "spem_compare.png", 174),
                           Paragraph("Figure 4. Plate photo and microscope photo of the device, and the integrated "
                                     "SPEM intensity (KE 84-92 eV) at SRn 120 / SRz 0 and at the predicted position "
                                     "for SRn 150 / SRz -10. Maps drawn as in ARPES viewer (PIX from large to small); "
                                     "cyan cross: piezo centre (150, 150), on the beam at the stage position.", SM)]))
story.append(Paragraph(
    "Note on the piezo directions: in this orientation the maps match the photos with PIY increasing towards plate "
    "+y, while the stage model then expected a feature at larger plate y at smaller PIY. The expected shift above uses "
    "the direction seen in the maps (with the old model sign the prediction error would be 51 µm). <b>Confirmed at the "
    "beamline afterwards</b>: to see a feature at a larger PIY, SZ has to be increased, so +PIY moves the plate down "
    "(against +SZ). The sign was fixed in the stage model (<i>StageModel._piezo</i>); it only matters when the piezo "
    "is not centred. The PIX direction has not been checked yet.", SM))

# ------------------------------------------------------------------------------------------------ section 9: Cav
story.append(Paragraph("9. Test on the Cav sample: rotation with SN correction", H2))
story.append(Paragraph(
    "Sample <b>Cav</b> (graphene, gating plate) was found at SRn 120 / SRz 0 at ST -4.30, SZ 36.35, with its surface "
    f"in the analyzer focus at SN -0.05 (sample height H = 0.748 mm in this configuration) and the capillary at CPS "
    f"{cm(CA, 'cps'):.2f}; it is at plate x 2.687, y 4.666 mm (session Cav/Cav_2026-11-14_capillary.json). A map at "
    "115 eV had shown the K point of the first Brillouin zone close to the slit centre with the slit along Γ-K. At "
    "95 eV the K point lies about 2° further from Γ, so SRz was turned, keeping SRn 120 (the in-plane alignment), to "
    f"bring K back to the slit centre: <b>SRz {cm(CB, 'srz'):.1f}</b>. The new configuration gave ST, SZ and SN for "
    "that rotation with SN corrected to put the sample back in the analyzer focus. At both positions a 300 x 300 µm "
    "SPEM map (PIX / PIY, 10 µm steps, hν 95 eV, KE 84-92 eV) was measured.", B))
ct = [["", "before rotation", "after rotation"],
      ["SPEM file", "Cav_2026-11-14_19-48-34.nxs", "Cav_2026-11-14_20-06-03.nxs"],
      ["SRn / SRz", f"{cm(CA, 'srn'):.1f} / {cm(CA, 'srz'):.1f}", f"{cm(CB, 'srn'):.1f} / {cm(CB, 'srz'):.2f}"],
      ["ST / SZ / SN predicted", "(found) -4.300 / 36.350 / -0.050", "-5.238 / 36.350 / -2.002"],
      ["ST / SZ / SN in the file", f"{cm(CA, 'st'):.3f} / {cm(CA, 'sz'):.3f} / {cm(CA, 'sn'):.3f}",
       f"{cm(CB, 'st'):.3f} / {cm(CB, 'sz'):.3f} / {cm(CB, 'sn'):.3f}"],
      ["CPS in the file", f"{cm(CA, 'cps'):.2f}", f"{cm(CB, 'cps'):.2f} (not changed)"],
      ["hν (eV)", f"{cm(CA, 'hv'):.2f}", f"{cm(CB, 'hv'):.2f}"],
      ["Sample in map 2 relative to map 1 (PIX / PIY)", "", f"{CS['d_pix']:+.0f} / {CS['d_piy']:+.0f} µm (measured)"],
      ["   expected from the motor values in the files", "", f"{CS['exp_pix']:+.0f} / {CS['exp_piy']:+.0f} µm"],
      ["   prediction error", "", f"{CAV_RES_PIX:+.0f} / {CAV_RES_PIY:+.0f} µm, |d| = {CAV_RES:.0f} µm"]]
story.append(table(ct, [62 * mm, 54 * mm, 54 * mm]))
story.append(Spacer(1, 4))
story.append(Paragraph(
    "The two maps, drawn as ARPES viewer draws ANTARES maps (PIX from large to small), show the same electrodes at "
    "the same place (Figure 5). Correlating the integrated maps (correlation "
    f"{CS['corr']:.2f}, 0.1 px steps) gives a shift of {CS['d_pix']:+.0f} µm in PIX and {CS['d_piy']:+.0f} µm in PIY; "
    f"the motor values actually set account for {CS['exp_pix']:+.0f} / {CS['exp_piy']:+.0f} µm, so the prediction "
    f"error is <b>{CAV_RES:.0f} µm</b> for a rotation of {abs(cm(CB, 'srz')):.0f}° in SRz that moved the stage by "
    f"{abs(cm(CB, 'st') - cm(CA, 'st')):.2f} mm in ST and {abs(cm(CB, 'sn') - cm(CA, 'sn')):.2f} mm in SN, within "
    "the 50 µm tolerance. The rotation is beyond the range used in the calibration (SRz -10 to 0), so the SRz axis "
    "is extrapolated here and still predicts well. The capillary was left at the same CPS and the spectra of the two "
    "maps have the same shape: the sample was in focus at both positions. The total intensity drops to about half "
    "after the rotation, as expected for the changed emission and incidence angles.", B))
story.append(KeepTogether([fig(WORK / "cav_compare.png", 174),
                           Paragraph("Figure 5. Integrated SPEM intensity of Cav (KE 84-92 eV) before and after the SRz "
                                     "rotation (same colour scale), and the spectra of both maps. Maps drawn as in "
                                     "ARPES viewer (PIX from large to small); cyan cross: piezo centre (150, 150), on "
                                     "the beam at the stage position.", SM)]))
story.append(Paragraph(
    "<b>Why SN has to be corrected after an SRz rotation.</b> The analyzer collects electrons from a fixed point, its "
    "focus; the surfaces it sees sharply lie in its focal plane, which runs along ST (Figure 6). At SRz 0 the "
    "sample surface is parallel to that plane, so ST and SZ move the sample within the plane and SN sets its "
    "distance (a). SRz turns the surface about the vertical SRz axis, which lies a few mm behind the surface. "
    "Bringing the sample back onto the beam with ST alone (SN kept, as the stage is usually run) puts the beam "
    f"spot on the turned surface <b>{CAV_OFF:.2f} mm along the beam from the analyzer focus</b> for SRz "
    f"{cm(CB, 'srz'):.1f} (b): the capillary could be refocused there (CPS about {cm(CA, 'cps') + CAV_OFF:.2f}), "
    "but the analyzer would see the spot out of its focus, and the spectra and angles would be distorted and weaker. "
    f"Moving SN by {float(CSCH['dsn']):+.2f} mm (to {cm(CB, 'sn'):.2f}) and ST accordingly brings the spot back to "
    "the analyzer focus (c), where the capillary focus is unchanged: that is why the CPS stayed at "
    f"{cm(CB, 'cps'):.2f}. The offset grows with the angle and with the distance of the surface from the SRz axis; "
    "QuickAlignment gives it for any target (<i>bring_to_beam</i>, <i>correct_sn</i>).", B))
cap6 = Paragraph(
    "<b>Figure 6.</b> Top view (stage model, calibration_2026-11-14_173743_capillary.json, file motor values), cut "
    "at the height of the sample: X-ray beam (yellow), analyzer focal plane (dashed), analyzer focus (circle), beam "
    "spot on the Cav surface (red star), plate riser (grey) and substrate.<br/><br/>(a) SRz 0, as in SPEM 19-48-34: "
    "the surface lies in the focal plane.<br/>(b) SRz turned, SN kept and the sample brought onto the beam with ST: "
    f"the spot is {CAV_OFF:.2f} mm from the analyzer focus.<br/>(c) SRz turned with SN corrected, as in SPEM "
    "20-06-03: the spot is back at the analyzer focus.", SM)
six = Table([[fig(WORK / "cav_sn_a.png", 84), fig(WORK / "cav_sn_b.png", 84)],
             [fig(WORK / "cav_sn_c.png", 84), cap6]], colWidths=[87 * mm] * 2)
six.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (1, 1), (1, 1), 8)]))
story.append(six)

story.append(Paragraph("10. Recommendations", H2))
for txt in [
    "Use the new configuration for the samples on this plate; check the first sample found with <i>found_here</i>. "
    "A deviation of more than 0.05 mm on a sample whose position on the photo is good points to the plate "
    "mounting or to the sample height.",
    "After the next capillary realignment, an <i>optics</i> recalibration (one set at SRn 120 / SRz 0, CPS noted) "
    "should be enough; SN_f and the rotation axes can be kept.",
    "Measure SN_f once more on a sample of known thickness to confirm the 0.3 mm change (the 0.5 mm substrate "
    "accounts for 0.025 mm of it).",
    "Mark devices on a microscope photo registered on the plate photo (align_register_device_photo) rather than on "
    "the plate photo alone: here the blurred plate photo put the device 0.14 mm off.",
    "PIY direction: confirmed and fixed in the stage model (section 8). Check the PIX direction the same way (a "
    "feature seen at a larger PIX: which way does ST have to move?).",
    "After an SRz rotation, correct SN (<i>correct_sn</i>): with SN kept the spot is millimetres away from the "
    "analyzer focus at large SRz (section 9). SRz down to -27° was predicted within 30 µm; calibration sets at "
    "SRz -20 to -25 would make such rotations safer.",
    "Note the CPS in every set, also in SRn-only sets, and use SRz in the range that will be used for the "
    "measurements (here -10 to 0 deg).",
    "Restart the QuickAlignment MCP server so that it uses the updated calibration code.",
]:
    story.append(Paragraph("• " + txt, B))


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#666666"))
    canvas.drawString(18 * mm, 10 * mm, "ANTARES stage alignment - capillary real-sample calibration 2026-11-14")
    canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"page {doc.page}")
    canvas.restoreState()


doc = SimpleDocTemplate(str(PDF), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                        bottomMargin=16 * mm, title="Capillary real-sample calibration 2026-11-14",
                        author="ANTARES stage alignment")
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print(PDF)
print("anchored dev:", [(LABEL[s.name][:3], round(an[0] - s.st, 4), round(an[1] - s.sz, 4),
                         None if s.optic is None else round(an[2] - s.optic, 3)) for s, raw, an, p3, nw in rows_pred])
print("max diff", max(abs(d[2]) for d in diff), max(abs(d[3]) for d in diff), max(abs(d[4]) for d in diff))
print("dST per 0.3 SN", D_ST_PER_03_SN)
