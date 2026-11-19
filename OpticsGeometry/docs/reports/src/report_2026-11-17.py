"""English PDF report: ZP / capillary 3-D geometry, the capillary spot discrepancy, test plan and the outline of a
beamline optics alignment procedure. Run figures_2026-11-17.py first."""
import json
from pathlib import Path

from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image as RLImage, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

HERE = Path(__file__).parent
PDF = HERE.parent / "2026-11-17_zp_capillary_geometry.pdf"
FIGS = HERE / "report_figs"
N = json.loads((HERE / "numbers.json").read_text(encoding="utf-8"))

ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=ss["Heading1"], fontSize=15, spaceAfter=6, textColor=colors.HexColor("#1a3a5c"))
H2 = ParagraphStyle("H2", parent=ss["Heading2"], fontSize=12, spaceBefore=10, spaceAfter=4,
                    textColor=colors.HexColor("#1a3a5c"), keepWithNext=1)
H3 = ParagraphStyle("H3", parent=ss["Heading3"], fontSize=10, spaceBefore=6, spaceAfter=2,
                    textColor=colors.HexColor("#1a3a5c"), keepWithNext=1)
B = ParagraphStyle("B", parent=ss["BodyText"], fontSize=9.2, leading=12.5, spaceAfter=4)
SM = ParagraphStyle("SM", parent=B, fontSize=8, leading=10.5, textColor=colors.HexColor("#444444"))
TC = ParagraphStyle("TC", parent=B, fontSize=7.8, leading=9.6, spaceAfter=0)
story = []


def P(t, s=B):
    story.append(Paragraph(t, s))


def table(data, widths, header=1):
    data = [[Paragraph(f"<b>{c}</b>" if i < header else str(c), TC) for c in row] for i, row in enumerate(data)]
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=header)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, header - 1), colors.HexColor("#dce6f0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9aa9b8")),
        ("ROWBACKGROUNDS", (0, header), (-1, -1), [colors.white, colors.HexColor("#f4f7fa")]),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(t)
    story.append(Spacer(1, 4))


def fig(name, width_mm, caption):
    path = FIGS / name
    im = Image.open(path)
    w = width_mm * mm
    story.append(KeepTogether([RLImage(str(path), width=w, height=w * im.height / im.width), Paragraph(caption, SM)]))


def bullets(items, style=B):
    for t in items:
        story.append(Paragraph("• " + t, style))


def steps(items):
    for i, t in enumerate(items, 1):
        story.append(Paragraph(f"{i}. {t}", B))


cav, tod = N["cav"], N["today"]
gx, gz = N["gap_x"], N["gap_z"]

# ------------------------------------------------------------------------------------------------------------
P("ANTARES - zone plate and capillary geometry: 3-D model, capillary spot discrepancy, test plan", H1)
P("2026-11-17 &nbsp;|&nbsp; model: <b>OpticsGeometry/</b> (package <b>quickalignment.optics</b>, separate from the "
  "alignment programs) &nbsp;|&nbsp; data: Cav/*.nxs (2026-11-14, 2026-11-15), configs/calibration_2026-11-15_151356_*.json, "
  "and a ZP / capillary test set given on 2026-11-17", SM)
story.append(Spacer(1, 6))

P("1. Summary", H2)
P("The stage programs assume one straight beam through the analyzer focus. This report starts a separate 3-D model of "
  "the two focusing optics of the main chamber: the zone plate (ZPS, ZPX, ZPZ) and the capillary (CPS, CPX, Cap Rz, "
  "Cap Rx), both carried by the ZPZ stage. The zone-plate beam is the reference line. The capillary reference spot is "
  "taken from the calibration configurations: 0.80 mm in ST and 0.19 mm in SZ from the zone-plate spot.")
P("A test set of 2026-11-17 (same sample found with both optics) disagrees with that reference: the stage moved "
  f"<b>{tod['dst']:+.2f} mm in ST and {tod['dsz']:+.2f} mm in SZ</b> between the two optics, where the model expects "
  f"<b>{N['model_dst']:+.2f} / {N['model_dsz']:+.2f}</b>. Across the beam this is {gx:.2f} mm horizontally and "
  f"{gz:.2f} mm vertically. With parallel beams and SN kept, the ST / SZ move between the optics does not depend on the "
  "sample thickness, so a wrong thickness cannot explain it. The thickness does explain the <i>focus</i> readings: the "
  f"ZPS and CPS values agree with a sample of about {N['h_from_zp_096']:.2f}-{N['h_from_zp']:.2f} mm (not 0.1 mm) on "
  "the 5 mm plate.")
P("The most likely cause of the horizontal gap is that the capillary position across the beam (CPX, possibly Cap Rz) "
  "did not come back to the same place although its readings did (section 6). Cap Rx cannot explain the vertical gap "
  "(its change has the wrong sign, and would need a pivot ~550 mm behind the focus). The configurations were <b>not</b> changed. Section 7 gives "
  "short tests that settle this, and also measure the unknown Cap Rz sign and pivot. Section 8 lists the steps of a "
  "beamline optics alignment procedure built from the sample upstream.")

# ------------------------------------------------------------------------------------------------------------
P("2. Frame, motors and units", H2)
P("Lab frame of the stage model (src/quickalignment/core/stage.py): origin = analyzer focus, <b>+x right, +y along "
  "the beam (downstream), +z up</b>. The analyzer sits at -n = (-1, -1, 0)/sqrt2, so 'towards the analyzer' across the "
  "beam is <b>-x</b>. At SRn 120 / SRz 0 the sample surface is the plane through the focus with normal n: a "
  "horizontal beam shift dx moves the illuminated point by dx*sqrt2 along ST; a vertical shift dz moves it by dz in "
  "SZ.")
table([["motor", "Tango device", "+ direction (lab)", "unit", "status"],
       ["ZPS", "i12-m-cx1/op/zp-mt_zs", "downstream (+y)", "mm", "direction given; 1 mm ZPS ~ 0.95-1.015 mm of focus (measured 11-15)"],
       ["ZPX", "i12-m-cx1/op/zp-mt_zx", "towards the analyzer (-x)", "mm", "direction given"],
       ["ZPZ", "i12-m-cx1/op/zp-mt_zz", "up (+z)", "mm", "shared by ZP and capillary"],
       ["CPS (Cap Ts)", "i12-m-cx1/op/cap-mt-ts", "downstream (+y)", "mm", "direction given; parked at 0"],
       ["CPX (Cap Tx)", "i12-m-cx1/op/cap-mt-tx", "towards the analyzer (-x)", "mm", "direction given; parked at 0"],
       ["Cap Rz", "i12-m-cx1/op/cap-mt-rz", "tip towards the analyzer = negative", "deg", "<b>sign provisional</b>; pivot unknown; cap_rz (other device) not used"],
       ["Cap Rx", "i12-m-cx1/op/cap_rx", "tip up = positive", "deg", "pivot unknown"]],
      [22, 42, 40, 10, 60])

# ------------------------------------------------------------------------------------------------------------
P("3. The 3-D model", H2)
P("Model, first version (OpticsGeometry/optics_geometry.json, src/quickalignment/optics/geometry.py):")
bullets([
    "The incoming beam is parallel to +y. The zone plate images a distant source, so its focus follows the lens 1:1 "
    "(ZPS along the beam, ZPX and ZPZ across it). Reference: ZPS 53.7502, ZPX 0.4683, ZPZ 23.511 put the focus on the "
    "analyzer focus (configuration 2026-11-15, Cav map 11:13:55). Parked: ZPS -20.",
    "The capillary focus is fixed to the capillary body (working distance past the tip): it follows CPS, CPX and ZPZ "
    "1:1 and turns with Cap Rz / Cap Rx about a pivot at an unknown distance L behind the focus. Reference: CPS 61.5075 "
    "(capillary configuration, CPS at the analyzer focus), CPX 57.14, ZPZ 3.2395, Cap Rz -0.408, Cap Rx 3.9056 (Cav "
    "2026-11-14 19:48). Parked: CPS 0 / CPX 0.",
    "Capillary reference spot = (dST0) t + (dSN_f) n + (dSZ0) z between the two configurations = "
    f"({N['model_cap_spot'][0]:+.3f}, {N['model_cap_spot'][1]:+.3f}, {N['model_cap_spot'][2]:+.3f}) mm, i.e. on the sample "
    "surface 0.80 mm towards -ST and 0.19 mm lower. The capillary beam is taken parallel to the ZP beam.",
    "ZPZ carriage: the capillary is in the beam at ZPZ 3.2395 and the zone plate at 23.511, so the capillary sits "
    "20.27 mm above the zone plate on the carriage.",
    "Program: python OpticsGeometry/OpticsGeometry.py [--nxs files] [--focus capillary x y z]: optic in use (from the "
    "parking positions), focus, beam direction, ST0 / SZ0 shift against the ZP spot, motors for a given focus.",
])
fig("persp_zp.png", 150, "Figure 1. Zone plate in the beam (ZP mode; the parked capillary is not drawn), perspective, to "
    "scale: zone plate (focal length 0.256 E = 24.32 mm at 95 eV) and OSA shield (3.5 mm before the focus at the working "
    "position S 80 / Z 26.63) as in the QuickAlignment anti-collision model, analyzer front 35 mm from the focus. Red arrows: + direction of each motor.")
fig("ortho_zp.png", 175, "Figure 2. ZP mode, orthographic views: top (from +z), side (from +x), along the beam (from downstream).")
fig("persp_cap.png", 150, "Figure 3. Capillary in the beam (ZPZ carriage 20.27 mm lower; the parked zone plate is not drawn). "
    "Capillary to scale as in the anti-collision model: working distance 7.2 mm, nose, chamfered head, body and ring "
    "(20.9 mm from the focus to the rear). Dashed green: capillary beam (0.6 mm from the ZP beam, true scale).")
fig("ortho_cap.png", 175, "Figure 4. Capillary mode, orthographic views.")

# ------------------------------------------------------------------------------------------------------------
P("4. Parameters missing from the model", H2)
table([["parameter", "now in the model", "why it matters", "how to get it"],
       ["Cap Rz sign", "tip towards the analyzer = negative (provisional)", "direction of the spot for an Rz move", "test T3"],
       ["Cap Rz / Rx pivot (distance L to the focus)", "0 (rotations turn the beam about the focus)",
        "spot shift per degree = L * 0.01745 mm", "tests T3, T4"],
       ["order of the Rz / Rx stages", "Rx on top of Rz", "second order only", "drawing / mechanics"],
       ["capillary beam direction vs ZP beam", "parallel", "spot moves with SN / sample height if tilted", "test T6"],
       ["capillary motor reproducibility (open loop?)", "assumed exact", "main suspect of the 0.42 mm gap", "tests T1, T2; controller settings"],
       ["CPS / CPX / ZPX / ZPZ scale (focus mm per motor mm)", "1", "ZPS measured 0.95-1.015", "test T2, T7"],
       ["capillary working distance and spot size", "not used", "focus tolerance on CPS", "specification (Sigray) / test T6"],
       ["OSA geometry (OS, OX, OZ)", "not modelled", "must stay on the ZP axis", "section 8, step 2"],
       ["incoming beam position / angle at the optics", "parallel to +y, fixed", "upstream changes (M1, Wolter, pinhole)",
        "section 8"],
       ["sample thickness of the test set", "0.1 mm (to be confirmed)", "focus readings fit ~0.30 mm", "measure H"]],
      [42, 40, 50, 42])

# ------------------------------------------------------------------------------------------------------------
P("5. Spot positions: data and comparison", H2)
mt = N["motors"]
table([["set", "optic motors", "ST", "SZ", "SN", "source"],
       ["A: capillary, Cav", f"CPS {mt['cav_cap']['cps']:.2f}, CPX {mt['cav_cap']['cpx']:.2f}, ZPZ {mt['cav_cap']['zpz']:.4f}, "
        f"Rz {mt['cav_cap']['cap_rz']:.3f}, Rx {mt['cav_cap']['cap_rx']:.4f}", "-4.2981", "36.361", "-0.0493",
        "Cav_2026-11-14_19-48-34.nxs"],
       ["B: zone plate, Cav", f"ZPS {mt['cav_zp']['zps']:.4f}, ZPX {mt['cav_zp']['zpx']:.4f}, ZPZ {mt['cav_zp']['zpz']:.3f}",
        "-3.4982", "36.538", "-0.0517", "Cav_2026-11-15_11-13-55.nxs (point at PIX 138 / PIY 142)"],
       ["C: zone plate, test set", "ZPS 54.22, ZPX 0.47, ZPZ 23.51", "-1.55", "41.25", "-0.15", "given 2026-11-17"],
       ["D: capillary, test set", "CPS 61.34, CPX 57.14, ZPZ 3.24, Rz -0.408, Rx 3.886", "-1.75", "41.25", "-0.15",
        "given 2026-11-17"]],
      [30, 62, 14, 14, 14, 40])
P("Assumed for C, D: SRn 120, SRz 0, piezo 150 / 150, the same feature in both. Sample: '0.1 mm on the 5 mm plate', "
  "thickness to be confirmed.", SM)

P("5.1 Across the beam: capillary spot minus ZP spot", H3)
table([["", "dST", "dSZ", "x (mm)", "z (mm)"],
       ["model (configurations)", f"{N['model_dst']:+.3f}", f"{N['model_dsz']:+.3f}",
        f"{N['model_cap_spot'][0]:+.3f}", f"{N['model_cap_spot'][2]:+.3f}"],
       ["Cav raw readings (A - B)", f"{cav['dst']:+.3f}", f"{cav['dsz']:+.3f}", f"{cav['x']:+.3f}", f"{cav['z']:+.3f}"],
       ["test set (D - C)", f"{tod['dst']:+.3f}", f"{tod['dsz']:+.3f}", f"{tod['x']:+.3f}", f"{tod['z']:+.3f}"],
       ["test set - model", f"{tod['dst'] - N['model_dst']:+.3f}", f"{tod['dsz'] - N['model_dsz']:+.3f}",
        f"{gx:+.3f}", f"{gz:+.3f}"]],
      [50, 25, 25, 25, 25])
P("The configuration values come from the Cav pair (A, B; SZ -0.177 from the raw readings, -0.190 in the configuration, "
  "which used the session SZ 36.35 and the plate coordinates of Cav). Cav is listed as 0.2 x 0.2 mm in the session "
  "(possibly the default size), so A and B may differ by up to ~0.1 mm on the sample. A and B are a day apart, with the "
  "capillary parked (CPS / CPX 0) and brought back in between. C and D are one pair of the test set.")
fig("spots.png", 135, "Figure 5. Capillary spot relative to the ZP spot, seen along the beam (x: + away from the analyzer). "
    "Error bars: ±0.1 mm on the sample for the Cav pair, ±0.02 mm (stage readings) for the test set. Blue: the direction "
    "each motor moves the capillary focus (Cap Rz, Rx: times the pivot distance L).")

P("5.2 Along the beam: the focus readings and the thickness", H3)
P("With the surface at SN = SN_f + H in focus, the test set at SN -0.15 puts the surface (SN - SN_f - H)*sqrt2 "
  "downstream of the analyzer focus along the ZP beam. ZPS 54.22 puts the ZP focus "
  f"{N['zp_focus_today'][1]:.2f} mm downstream (1 mm of ZPS per mm). For the capillary (spot at its measured place, "
  "test set), CPS 61.34 puts the focus:")
rows = [["H (mm)", "surface along the beam (mm)", "ZP focus - surface (mm)", "capillary focus - spot (mm)"]]
for r in N["thickness_rows"]:
    rows.append([f"{r['H']:.1f}", f"{r['surface_y']:+.3f}", f"{r['zp_focus_minus_surface']:+.3f}",
                 f"{r['cap_focus_minus_spot']:+.3f}"])
table(rows, [25, 45, 45, 50])
P(f"Both focus readings agree with H ~ {N['h_from_zp_096']:.2f}-{N['h_from_zp']:.2f} mm (ZP exactly; the capillary then "
  "0.2 mm short, within the CPS judgement of earlier days, 0.1-0.2 mm). With H = 0.1 mm the ZP would be 0.31 mm and the "
  "capillary 0.52 mm out of focus. Other readings of the same fact: the plate surface is not at w = 5.0, or SN_f / the "
  "ZPS reference changed. <b>Conclusion: the thickness explains the focus, not the ST / SZ gap.</b>")

# ------------------------------------------------------------------------------------------------------------
P("6. What can move the capillary spot: most likely relations", H2)
P("Both optics put their focus at a point fixed to their own body; the incoming beam only changes the flux and, through "
  "the demagnification, the spot position very little. A 0.42 mm horizontal and 0.19 mm vertical move of the capillary "
  "spot relative to the ZP spot therefore needs one of the optics to have moved, a reading to be wrong, or the two sets "
  "not to be on the same feature. In order of likelihood:")
P("6.1 CPX (and CPS) not reproducing their readings - most likely for x", H3)
bullets([
    "The capillary motors are recorded as <i>value</i> with 2-3 decimals (57.14, 61.38, -0.408), the ZP and stage motors "
    "as <i>position</i> with 4 decimals. The homing note (Manual_Homing_Capillary_Sigray) references Cap Tx and Cap Ts "
    "on their limit switch ('Initialize Reference Position => -1', then go to 0). This suggests counted positions "
    "without an absolute encoder (to be confirmed on the controller).",
    "Then a re-homing between A and D (limit-switch repeatability) or lost steps during the park / return (57.14 -> 0 -> "
    "57.14, 61.x -> 0 -> 61.x) shift the capillary with unchanged readings. A CPX error of +0.42 mm (capillary further "
    "from the analyzer than the reading says) explains the whole x gap.",
    "CPS moves along the beam: its change (61.38 -> 61.34) cannot move the spot across the beam unless the CPS axis is "
    "tilted by ~0.42/0.04 rad - excluded. A CPS error shows up in the focus only (section 5.2).",
])
P("6.2 Cap Rz with a pivot behind the focus - possible for x", H3)
P("A rotation dθ about a pivot L behind the focus moves the focus sideways by L*dθ: 0.42 mm needs 0.48° at L = 50 mm, "
  "0.24° at 100 mm, 0.12° at 200 mm (Figure 6). The Cap Rz reading is the same in A and D (-0.408), so this needs Cap Rz "
  "to be open loop as well, or cap_rz and cap-mt-rz to disagree. If the pivot is at the focus (L ~ 0) this cannot move "
  "the spot at all.")
P("6.3 Cap Rx - excluded as the cause of z", H3)
P("Cap Rx went from 3.9056 (A) to 3.886 (D), -0.0196°: tip down, which moves the focus <i>down</i> for a pivot behind "
  "it, while the capillary spot is found 0.19 mm <i>higher</i> than the model. Even with the right sign it needs "
  "L ~ 550 mm. For z the candidates are the sample (user: sample large enough) and an Rx / ZPZ reproducibility "
  "problem; ZPZ reads the same in both pairs (3.2395 / 3.24 with the capillary, 23.511 / 23.51 with the ZP).")
P("6.4 Excluded or second order", H3)
bullets([
    "A tilt between the two beams: the illuminated surface moved by ~0.5-0.8 mm along the beam between the sets; a "
    "0.42 mm sideways change needs ~30°.",
    "Upstream optics (M1, Wolter, pinhole): the spot moves by the source shift times the demagnification; 0.4 mm needs "
    "tens of mm of source motion. Note M1A (Rz2) read -567 on 11-14 and -582 on 11-15 (controller units); its effect on "
    "the spot has not been measured (section 8).",
    "Stage: ST, SZ, SN are encoded (4 decimals), SN equal within each pair, SRn / SRz assumed equal.",
])
fig("pivot.png", 135, "Figure 6. Rotation needed to move the capillary focus by the observed gap, against the pivot "
    "distance L. Dotted: the Cap Rx change actually read between A and D (and with the wrong sign).")
P("Which pair to trust: the configuration value comes from two days and one park / return cycle, the test set from one "
  "pair (please confirm it was measured the same day, and how the sample was identified - map feature or 'sample "
  "found'). If both are right, the capillary moved by ~0.42 mm horizontally relative to the zone plate between "
  "2026-11-14 and the test set without any change of its readings.")

# ------------------------------------------------------------------------------------------------------------
P("7. Test plan: capillary and zone plate", H2)
P("All tests on one small, sharp feature (SPEM map), SRn 120 / SRz 0, SN kept, piezo centred, same photon energy. "
  "Record every time: the full motor snapshot (.nxs), the map file, the feature position in the map (PIX / PIY) and "
  "whether it is in focus. A horizontal spot shift dx appears as an ST (or PIX) shift of dx*sqrt2, a vertical one as "
  "dz in SZ (or PIY).")
table([["test", "what to do", "what it gives", "expected size"],
       ["T1 park / return", "capillary on the feature, map; CPS / CPX to 0 / 0; back to the same readings; map again "
        "(repeat 2-3 times; once with ZPZ to the ZP position and back)", "reproducibility of CPS, CPX, ZPZ", "decides 6.1: "
        "x shifts of 0.1-0.4 mm = open-loop problem"],
       ["T2 CPX / CPS scale", "CPX +0.10 and -0.10 mm, map each; CPS ±0.3 mm, judge focus", "focus mm per motor mm, "
        "sign of CPX", "CPX: feature moves 0.14 mm in ST per 0.1 mm"],
       ["T3 Cap Rz", "Cap Rz -0.10° and +0.10° from the reference, map each (keep the flux in view)",
        "<b>sign of Cap Rz</b> and the pivot distance L = shift / 0.001745", "L = 100 mm: 0.17 mm per 0.1°"],
       ["T4 Cap Rx", "Cap Rx ±0.10°, map each", "sign check and L for Rx", "as T3, vertical"],
       ["T5 ZPZ", "with the capillary: ZPZ ±0.10 mm; with the ZP: same", "1:1 for both optics on the shared stage",
        "0.10 mm in SZ"],
       ["T6 SN slide", "capillary: SN -0.5 and +0.5 mm from focus, refocus with CPS, map (and the same with the ZP)",
        "tilt of each beam vs +y; CPS / ZPS per mm; depth of focus", "tilt 10 mrad: 20 µm in ST per mm of SN"],
       ["T7 ZP across", "ZPX ±0.05, ZPZ ±0.05, map each", "ZP 1:1 assumption, ZPX sign", "0.07 mm in ST per 0.05"],
       ["T8 cross pair", "same session: ZP on the feature, map; capillary in, find the same feature, map; ZP back, map",
        "the capillary spot relative to the ZP spot (replaces the Cav value)", "the result to put in the model"],
       ["T9 thickness", "measure H of the test sample (or ZP focus at two SN)", "H; check of SN_f and ZPS reference",
        "0.1 vs ~0.3 mm"]],
      [22, 66, 46, 40])
P("Order: T8 first (one session, gives the number), then T1 (is it reproducible), T3 / T4 (signs and pivots), T2 / T5 / T7 "
  "(scales), T6 (beam directions). If T1 shows the capillary does not come back, the model needs a re-measured reference "
  "after every park / return, or the capillary needs a reference mark.")

# ------------------------------------------------------------------------------------------------------------
story.append(PageBreak())
P("8. Toward a beamline optics alignment procedure (from the sample upstream)", H2)
P("Plan: build the model from the sample upstream, element by element, so that each step uses the parts already "
  "calibrated downstream as its detector (the sample stage and SPEM maps first, then the focusing optics, and so on). "
  "The final alignment procedure can then be written in the usual upstream-to-downstream order. Units below are "
  "written only where a document gives them; otherwise 'not confirmed' (the readings are in the controller unit).")
P("8.1 Elements, readings and units", H3)
table([["step", "element", "motors (Tango, label)", "readings 11-14 / 11-15", "unit / meaning", "source of the unit"],
       ["0", "sample stage", "ST, SZ, SN, SRn, SRz, piezo PIX / PIY", "-", "mm, deg, µm", "stage model, calibrations"],
       ["1", "zone plate", "zp-mt_zs / zx / zz (ZPS, ZPX, ZPZ)", "-20.00 / 53.75; 0.468; 3.24 / 23.51", "mm", "this report"],
       ["1", "capillary", "cap-mt-ts / tx (CPS, CPX), cap-mt-rz, cap_rx", "61.38 / 0; 57.14 / 0; -0.408; 3.906 / 3.914",
        "mm; Rz, Rx deg", "beamline (2026-11-17)"],
       ["2", "OSA", "osa-mt_os / ox / oz", "20.00 / 72.00; -0.504; -6.337 / -5.002", "not confirmed", "-"],
       ["3", "pinhole", "pin-mt_ps / px / pz", "-0.0035; -7.0006; -4.998", "not confirmed", "-"],
       ["4", "Wolter M3 / M4 (C08)", "wolt-mt_tz.1 (M3Z), wolt-mt_tz.2 (M4Z), wolt-mt_rz.1", "34398; 35491; 22486",
        "not confirmed (controller units)", "-"],
       ["5", "vertical slit (C04)", "fent_v.1-mt_ec (gap), fent_v.1-mt_tx.1 (position)", "80000; 84000",
        "gap: 80000 = 340 µm; position: not confirmed", "homing note (mono); Tx 'theoretical 62000'"],
       ["5", "horizontal slit (C05)", "fent_h.1-mt_ec (gap)", "not recorded", "not confirmed", "-"],
       ["6", "monochromator (C04)", "mono1-mt_rx.1 (grating rotation), mono1-mt_rx.2 (mirror rotation), "
        "mono1-mt_tx.1 (grating translation)", "11.539; 8.068; 35.448 (95 eV, 1300 l/mm)",
        "rx: deg; tx: mm", "homing note (AxisPositionRatio, deg accuracy, mm/s)"],
       ["7", "mirror M1 (C02)", "mir1-mt_rz.1 = Rz1 'M1 (A+B+C)', mir1-mt_rz.2 = Rz2 'M1A': <b>two rotations</b>",
        "-46949 / -46948; -567 / -582", "controller units, conversion to angle not known",
        "homing note: configurations at 2.5° and 5° (Rz1 -46820 / Rz2 +2303 at 2.5°)"],
       ["8", "source", "HU60 / HU256 (control room)", "-", "-", "-"]],
      [9, 24, 46, 34, 30, 31])
P("Note for M1: the homing note (procedure 2) gives Rz2 (M1A) +2303 for the 2.5° configuration, the files read -567 / "
  "-582 (after a 'Salsa' optimisation?). To be checked with the beamline before using these numbers.", SM)

P("8.2 Steps", H3)
P("<b>Step 0 - sample stage (done).</b> Calibrations of 2026-11-14 / 15 (ST0, SZ0, SN_f, SRn / SRz axes). Keep one "
  "reference sample with a sharp feature for all following steps.")
P("<b>Step 1 - focusing optics (now).</b> Tests T1-T9. Result: ZP and capillary focus as functions of their motors, "
  "the capillary spot relative to the ZP spot, Cap Rz sign and pivots, reproducibility after parking.")
P("<b>Step 2 - OSA.</b> With the ZP in focus: scan OSX and OSZ across the ZP axis (flux and map), move OSS along the "
  "beam. Gives the OSA centre relative to the ZP axis and the OSS range that blocks the zero order without cutting the "
  "first order. Record OSA readings with every ZP set. Units to be confirmed.")
P("<b>Step 3 - pinhole.</b> With each optic in focus: scan PX and PZ (flux on the sample / diode CX0 and spot position in "
  "the map), PS if relevant. Gives whether the pinhole defines the illuminated part of the optic and whether it moves "
  "the spot (expected: flux only). Units to be confirmed.")
P("<b>Step 4 - Wolter M3 / M4.</b> Small steps of M3Z, M4Z and Wolter Rz around the working values, one at a time: flux "
  "(diodes) and spot position / size with the ZP and with the capillary. Gives the sensitivity of the spot to the beam "
  "height and angle at the optics (the 'incoming beam' parameter of the model). Units and steps to be agreed with the "
  "beamline before any move.")
P("<b>Step 5 - slits.</b> Vertical slit gap (80000 = 340 µm) and position, horizontal slit gap: effect on flux, spot size "
  "and spot position (secondary source). Expected: spot size and flux, little position.")
P("<b>Step 6 - monochromator.</b> Record the spot position and focus (ZPS / CPS) against photon energy over the working "
  "range: chromatic focus of the ZP (focal length proportional to energy) and any beam motion with the grating / mirror "
  "rotations. Do not move the monochromator motors directly; change the energy.")
P("<b>Step 7 - M1.</b> The existing 'Beamline Alignment' scan (PythonVersion, M1A scan on the diodes C05 and CX0) gives "
  "the flux optimum. Add: spot position and focus at the optimum and at ± a few hundred units of M1A, with ZP and "
  "capillary. Gives how much an M1A re-optimisation (as between 11-14 and 11-15, -567 -> -582) moves the spot.")
P("<b>Step 8 - source.</b> Note the undulator in use (HU60 / HU256), gap / phase, and the machine filling; repeat a "
  "short check (step 1, T8) after a change.")
P("<b>For every step:</b> one motor at a time; return to the starting reading and re-check (reproducibility); keep the "
  "full .nxs snapshot; write the result into the model file (OpticsGeometry/optics_geometry.json) only after it has "
  "been checked; staff decides on any move of upstream optics.")

# ------------------------------------------------------------------------------------------------------------
P("9. Files", H2)
bullets([
    "Model and program: src/quickalignment/optics/ (geometry.py, nxs.py, schematic3d.py, cli.py), "
    "OpticsGeometry/OpticsGeometry.py, OpticsGeometry/optics_geometry.json; tests: tests/test_optics_geometry.py.",
    "Element list, motor directions, decisions, test data: OpticsGeometry/optics_elements.md.",
    "This report: OpticsGeometry/docs/reports/src/figures_2026-11-17.py (figures, numbers.json), report_2026-11-17.py.",
], SM)

doc = SimpleDocTemplate(str(PDF), pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm,
                        bottomMargin=14 * mm, title="ZP and capillary geometry", author="ANTARES")
doc.build(story)
print(PDF)
