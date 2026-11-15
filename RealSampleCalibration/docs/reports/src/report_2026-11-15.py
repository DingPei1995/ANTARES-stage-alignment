"""English PDF report of the 2026-11-15 zone-plate calibration and SRz-axis correction (run zp_maps.py, zp_figs.py
first)."""
import json
from pathlib import Path

from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image as RLImage, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

HERE = Path(__file__).parent
ROOT = HERE.parents[3]
PDF = HERE.parent / "2026-11-15_zone_plate_calibration_srz_axis.pdf"
FIGS = HERE / "report_figs"
N = json.loads((HERE / "spem" / "zp_numbers.json").read_text(encoding="utf-8"))
CFG = {p.name: json.loads(p.read_text(encoding="utf-8"))["stage_config"]
       for p in (ROOT / "configs").glob("calibration_2026-11-1[45]_*.json")}
OLD = CFG["calibration_2026-11-14_173743_capillary.json"]
NEW = CFG["calibration_2026-11-15_151356_zone_plate.json"]

ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=ss["Heading1"], fontSize=15, spaceAfter=6, textColor=colors.HexColor("#1a3a5c"))
H2 = ParagraphStyle("H2", parent=ss["Heading2"], fontSize=12, spaceBefore=10, spaceAfter=4,
                    textColor=colors.HexColor("#1a3a5c"), keepWithNext=1)
B = ParagraphStyle("B", parent=ss["BodyText"], fontSize=9.2, leading=12.5, spaceAfter=4)
SM = ParagraphStyle("SM", parent=B, fontSize=8, leading=10.5, textColor=colors.HexColor("#444444"))
TC = ParagraphStyle("TC", parent=B, fontSize=8, leading=10, spaceAfter=0)


def table(data, widths, header=1, align="RIGHT"):
    data = [[Paragraph(f"<b>{c}</b>" if i < header else str(c), TC) if isinstance(c, str) and (len(c) > 22 or i < header)
             else c for c in row] for i, row in enumerate(data)]
    t = Table(data, colWidths=widths, repeatRows=header)
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8),
        ("BACKGROUND", (0, 0), (-1, header - 1), colors.HexColor("#dce6f0")),
        ("ALIGN", (1, 0), (-1, -1), align),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9aa9b8")),
        ("ROWBACKGROUNDS", (0, header), (-1, -1), [colors.white, colors.HexColor("#f4f7fa")]),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return t


def fig(name, width_mm):
    path = FIGS / name
    im = Image.open(path)
    w = width_mm * mm
    return RLImage(str(path), width=w, height=w * im.height / im.width)


def bullets(items):
    for txt in items:
        story.append(Paragraph("• " + txt, B))


sm = {(r["label"], r["axes"]): r for r in N["sn_moved"]}
fin, first = sm[("final (new axes)", "new")], sm[("first (capillary axes)", "old")]
cap = {(r["srn"], r["srz"]): r for r in N["cap_rows"]}

story = []
story.append(Paragraph("ANTARES sample stage - zone-plate calibration and SRz-axis correction", H1))
story.append(Paragraph(
    "2026-11-15 &nbsp;|&nbsp; gating plate, zone plate + OSA, hv 95 eV &nbsp;|&nbsp; sample Cav (graphene), not "
    "touched since 2026-11-14 &nbsp;|&nbsp; new configurations <b>calibration_2026-11-15_151356_zone_plate.json</b> and "
    "<b>calibration_2026-11-15_151356_capillary.json</b>", SM))
story.append(Spacer(1, 6))

story.append(Paragraph("1. Summary", H2))
story.append(Paragraph(
    "The capillary was replaced by the zone plate. Starting from the mechanics of the capillary calibration of "
    "2026-11-14 (rotation axes, SN_f), the zone-plate spot was located on the sample Cav and one point of Cav was "
    "tracked with SPEM maps through SRn and SRz rotations. Three results: "
    "(1) the zone-plate spot sits +0.80 mm in ST0 and +0.19 mm in SZ0 from the capillary spot, ZPS 53.75 focuses on "
    "the analyzer focal plane; "
    "(2) the SRn axis, from one SRn 140 map, is at plate x -0.032 / y -0.057 mm (±0.012; capillary fit -0.166 / "
    "-0.107); "
    "(3) the SRz axis was 0.97 mm off <i>across</i> the beam in the capillary configuration. That direction is seen "
    "almost only in the focus, which the capillary (CPS) did not resolve; the zone plate does. With the corrected "
    "axis, a pure SRz series (-5 to -20) is reproduced within 0.05 mm in ZPS, and a check at SRn 140 / SRz -15 was "
    "predicted at ZPS 54.30 and found at 54.33 (old axis: 54.57). "
    "<b>Open:</b> after moving SN by ~1.5 mm at SRz -25 the focus stays ~0.14 mm short of the prediction and the "
    "point is ~25 µm off in the map (section 7).", B))
kt = [["constant (mm)", "capillary 2026-11-14", "2026-11-15", "how"],
      ["ST0 (zone-plate spot)", "-1.613 (capillary)", f"{NEW['st0']:.4f}", "SPEM point, SRn 120 / SRz 0"],
      ["SZ0 (zone-plate spot)", "41.016 (capillary)", f"{NEW['sz0']:.4f}", "same"],
      ["ZPS at analyzer focus", "53.22 (2026-10-24)", "53.75", "same, SN -0.05 at analyzer focus"],
      ["SN_f", f"{OLD['sn_f']:.4f}", f"{NEW['sn_f']:.4f}", "kept"],
      ["SRn axis x / y", f"{OLD['srn_axis_u']:.3f} / {OLD['srn_axis_v']:.3f}",
       f"{NEW['srn_axis_u']:.3f} / {NEW['srn_axis_v']:.3f}", "SPEM tracking SRn 120 -> 140"],
      ["SRz offset ST / SN", f"{OLD['srz_offset_t']:.3f} / {OLD['srz_offset_n']:.3f}",
       f"{NEW['srz_offset_t']:.3f} / {NEW['srz_offset_n']:.3f}", "ZPS focus, SRz -5 ... -20, SN kept"]]
story.append(table(kt, [44 * mm, 38 * mm, 30 * mm, 62 * mm]))

story.append(Paragraph("2. Starting point", H2))
story.append(Paragraph(
    "The rotation axes were assumed unchanged since the capillary calibration (same plate, same sample, only the "
    "optic exchanged). The real-sample calibration was therefore run in mode <i>optics</i> (fit ST0, SZ0 and the optic "
    "reference, keep SN_f and the axes). The program would have kept the axes of the newest <i>zone-plate</i> "
    "configuration (2026-10-24, standard plate, a rough SRn axis); it was changed so that the mechanics can be taken "
    "from any configuration (rsc_start(configuration=...), section 9). "
    "Cav was found at SRn 120 / SRz 0, ST -3.50, SZ 36.54, SN -0.05 (the SN of Cav at the analyzer focus, from "
    "2026-11-14), ZPS 53.75. On the SPEM map 11:13:55 the tracked point (the corner of the bright structure) is at "
    "PIX 138 / PIY 142. Taking it as the Cav position of 2026-11-14 (plate x 2.687 / y 4.666, H 0.748) gives ST0 "
    "-0.8127 and SZ0 41.2059 for the zone-plate spot.", B))
story.append(fig("zp_maps.png", 170))
story.append(Paragraph("Figure 1. Integrated SPEM maps of Cav (ARPES viewer loader) with the tracked point.", SM))

story.append(Paragraph("3. SRn axis (SRn 120 -> 140) and the piezo directions", H2))
story.append(Paragraph(
    "Predicted for SRn 140 with the capillary axes: ST -1.693, SZ 35.851 with the point at PIX 138 / PIY 142. At ST "
    "-1.6931, SZ 35.841 the point was seen at <b>PIX 132 / PIY 84</b> (±4 µm), ZPS unchanged and in focus: the "
    "capillary axes put it 18 µm across and 43 µm vertically off the beam. Since the sample did not move, this was "
    "read as an SRn-axis error: two equations, two unknowns, SRn axis at x -0.032 ± 0.012, y -0.057 ± 0.012 mm "
    "(capillary fit -0.166 / -0.107, itself from ST / SZ readings of ±0.02 mm, i.e. about ±0.04 mm). The model assumes "
    "the piezo turns with SRn. "
    "PIX direction checked at the beamline: to see a feature at a larger PIX, ST must be decreased - as in the model "
    "(PIY was checked on 2026-11-14). No code change needed.", B))

story.append(Paragraph("4. The SRz -25 defocus and how it was traced", H2))
story.append(Paragraph(
    f"At SRn 120 / SRz -25 with SN moved to the predicted analyzer focus (ST -4.3935, SZ 36.548, SN -1.856, ZPS kept "
    f"53.75) the point was on the beam (PIX 110 / PIY 150, ±10 µm; model {first['pix_model']:.0f} / "
    f"{first['piy_model']:.0f}) but strongly out of focus; refocused at <b>ZPS 53.17</b> (0.58 mm). The causes were "
    "tested one by one, each against all the data, without fitting them in:", B))
tests = [["test / hypothesis", "result", "verdict"],
         ["A: SRz 0, ZPS scan 53.0-54.0 (diffraction order, OSA)", "single focus at 53.75", "excluded"],
         ["B: SRz 0, SN -1.856 with ST compensating (pure slide, -2.552 mm)", "ZPS 51.16 (ratio 1.015)",
          "SN travel and ZPS fine"],
         ["SN slide +0.75 / +1.20 / +1.70 mm (ZPS above 53.75)", "ZPS 54.46 / 54.90 / 55.40 (0.95-0.97)",
          "ZPS motor fine"],
         ["spot not in the analyzer focal plane", "needs ~6 mm; breaks SRn 140 by 100s of µm", "excluded"],
         ["beam / zone plate tilted (±20 mrad)", "focus changes < 5 µm", "excluded"],
         ["SRz angle scale, SRz axis tilted (50 mrad)", "breaks the map positions by 100s of µm", "excluded"],
         ["SRz axis moved along ST or along SN only", "breaks the map positions", "excluded"],
         ["SRz series -5 ... -20, SN kept (pure rotation)", "focus 0.75-0.84 x the model", "see section 5"]]
story.append(table(tests, [74 * mm, 58 * mm, 42 * mm], align="LEFT"))
story.append(Spacer(1, 4))
story.append(fig("zp_zps_linearity.png", 110))
story.append(Paragraph("Figure 2. ZPS change against a pure stage slide along the beam at SRz 0: ZPS follows the "
                       "focus 1:1 within 5 %.", SM))

story.append(Paragraph("5. New SRz axis", H2))
rf, ro = N["r_fit"], N["r_old"]
res_max = max(abs(v) for row in N["r_res_um"] for v in row)
story.append(Paragraph(
    "For a pure SRz rotation with SN kept, ST brings the point back on the beam and ZPS measures where it is along "
    "the beam. Both together give the displacement of the point in the horizontal plane, from which the point's "
    "position relative to a vertical SRz axis follows directly, without the stage model: "
    f"<b>({rf[0]:+.2f}, {rf[1]:+.2f}) mm</b> (x across, y along the beam) for all four angles (residuals &lt;= "
    f"{res_max:.0f} µm), against ({ro[0]:+.2f}, {ro[1]:+.2f}) mm in the capillary configuration: the axis is "
    f"{abs(rf[0] - ro[0]):.2f} mm off across the beam. This direction changes ST only to second order (cos SRz - 1), "
    "so the ST readings could not show it; it shows in the focus, linearly in sin SRz. The capillary CPS readings of "
    "2026-11-14 at SRz -10 / -5 were not precise enough. In configuration terms: SRz offset ST -0.924 -> -0.145, "
    "SRz offset SN 2.188 -> 2.775 (ZPS scale 1.015 from test B; with 1:1 the offsets differ by < 0.07 mm). "
    f"<b>Check</b> at SRn 140 / SRz -15 (SN kept): ZPS predicted {N['check_new']:.2f} (old axis "
    f"{N['check_old']:.2f}), found <b>54.33</b> at ST -2.9839, SZ 35.886.", B))
story.append(fig("zp_srz_focus.png", 130))
story.append(Paragraph("Figure 3. ZPS in focus after pure SRz rotations: measured, capillary axes, new axis; the "
                       "check point at SRn 140 / SRz -15.", SM))

story.append(Paragraph("6. Configurations saved", H2))
bullets([
    "<b>calibration_2026-11-15_151356_zone_plate.json</b>: zone-plate spot (ST0 -0.8127, SZ0 41.2059), ZPS 53.7502 at "
    "the analyzer focus, SN_f -0.7983, new SRn and SRz axes. Supersedes 2026-10-24 17:00 zone plate.",
    "<b>calibration_2026-11-15_151356_capillary.json</b>: the capillary configuration of 2026-11-14 with the same new "
    "axes; ST0, SZ0, SN_f and CPS 61.51 kept (set 1 at SRn 120 / SRz 0 does not depend on the axes). Supersedes "
    "2026-11-14 17:37:43.",
    "Both files carry all of today's measurements in their check block. QuickAlignment loads them at the next start."])

story.append(Paragraph("7. Open points", H2))
c10, c5, c100 = cap[(120, -10)], cap[(100, -5)], cap[(100, 0)]
bullets([
    f"<b>SRz -25 with SN moved.</b> Final measurement with the new axes: ST -4.7228, SZ 36.54, SN -1.578 -> point at "
    f"PIX {fin['pix']} / PIY {fin['piy']} (±4 µm; model {fin['pix_model']:.0f} / {fin['piy_model']:.0f}), focus at "
    f"ZPS {fin['zps']:.2f} (model {fin['zps_model']:.2f}). The first SRz -25 measurement gives the same with the new "
    f"axes: ZPS 53.17 against {sm[('first (capillary axes)', 'new')]['zps_model']:.2f}. So moving SN by ~1.5-1.8 mm "
    "at SRz -25 leaves ~0.14 mm along the beam and ~20-25 µm across unexplained, while the same SN slide at SRz 0 "
    "(test B) is exact. Candidates to check: the SN direction / straightness with SRz turned, the analyzer focal "
    "plane (SN_f is judged by eye on a camera reference line), the sample height H of Cav (0.748, derived from SN).",
    f"<b>Capillary data of 2026-11-14 against the new axes.</b> CPS change at SRz -10: model {c10['new']['along']:+.2f}, "
    f"read {c10['cps']:+.2f}; at SRn 100 / SRz -5: {c5['new']['along']:+.2f} vs {c5['cps']:+.2f}; SRn 100 vertical "
    f"{c100['new']['z'] * 1000:+.0f} µm (readings ±20 µm). Possible reasons (user): the CPS focus was not judged "
    "carefully; the substrate of that first sample is thinner than Cav's, and its H enters the capillary data; SN_f "
    "is judged on the camera line. To be checked with the capillary on a later occasion.",
    "The SRn axis rests on one SRn rotation (exact solution, no redundancy); an SRn 100 map would check it and the "
    "piezo-turns-with-SRn assumption.",
    "ARPES note (user): on graphene at 115 eV, SRn 120 / SRz -24, with Gamma-K along the slit, the Dirac cone below the "
    "first BZ appeared at slit angle -0.8°, deflector +1°: a ~1° tilt of the surface normal (substrate tilt or "
    "SRn / SRz zero offsets). It does not affect point tracking (a point's path depends only on its position "
    "relative to the axes) and changes the focus by ~17 µm per mm across the surface."])

story.append(Paragraph("8. Lessons for the procedure", H2))
bullets([
    "The SRz axis across the beam is only measured by the focus. Use the zone plate (focus to ~0.02 mm) and SRz down "
    "to -20 / -25 for it; a capillary focus (±0.1-0.2 mm) does not fix it.",
    "Track one point with SPEM maps and note the PIX / PIY where it is seen; this is 5-10 x more precise than "
    "ST / SZ readings and separates the lateral from the focus information.",
    "Test the optic and SN separately at SRz 0 (ZPS scan for other orders; SN slide with ST compensating) before "
    "blaming the rotation axes.",
    "When a reading contradicts the model, list the mismatches per hypothesis and decide which is real; do not let a "
    "joint fit absorb it (an early free fit had 'explained' the SRz -25 defocus by moving the axis ~1 mm in a "
    "direction that also contradicted the capillary data)."])

story.append(Paragraph("9. Code changes (QuickAlignment)", H2))
bullets([
    "<b>rsc_start(configuration=...)</b>: optics mode keeps the mechanics of a chosen configuration, also of the other "
    "optic; the optic reference is compared with the newest configuration of the chosen optic.",
    "<b>Weighted fit</b> (realsample/fit.py): positions ±0.02 mm, optic ±0.10 mm (capillary) / ±0.02 mm (zone plate); "
    "rsc_fit reports the reading errors, chi2/dof and the <b>least determined combination</b> of constants, with a "
    "warning when it is worse than 0.05 mm (typically the SRz axis across the beam).",
    "Test points and full-mode protocol keep <b>SRz &lt;= 0</b> (SRz -25 added); in mode optics the test points keep SN, "
    "as the sets were measured.",
    "<b>rsc_read_spem(path)</b>: motor and optic positions (ST, SZ, SN, SRn, SRz, ZPS, CPS, hv, scanned axes) read "
    "from a SPEM .nxs file.",
    "StageModel: PIX direction documented as checked; agent workflow text updated; API.md regenerated; tests added."])


S = json.loads((HERE / "spem" / "zp_schem.json").read_text(encoding="utf-8"))
(uc, vc), (uz, vz) = S["spot"]["capillary"], S["spot"]["zone plate"]
(ao, bo), (an, bn) = S["srn_axis"]["2026-11-14"], S["srn_axis"]["2026-11-15"]
(to, no), (tn, nn) = S["srz_offsets"]["2026-11-14"], S["srz_offsets"]["2026-11-15"]
dx, dy = S["srz_shift_lab"]
(sc, zc), (sz_, zz) = S["st0_sz0"]["capillary"], S["st0_sz0"]["zone plate"]
story.append(Paragraph("10. Schematics: beam spots and rotation axes", H2))
story.append(Paragraph(
    "Figure 4 shows, in the plate frame (front view, tab up), where the capillary and the zone-plate beams meet the "
    f"plate at the same motor positions (ST {-3.4982}, SZ 36.538, SRn 120 / SRz 0, piezo centred), and the SRn axis "
    "of both days. Figure 5 is a top view at SRn 120 / SRz 0 with the tracked point of Cav on the beam at the "
    "analyzer focus: the SRz axis of 2026-11-14 and 2026-11-15 relative to that point (same plate point for both).", B))
story.append(fig("zp_schem_front.png", 172))
story.append(Paragraph("Figure 4. Beam spots of the two optics and the SRn axis, gating plate front view.", SM))
story.append(fig("zp_schem_top.png", 120))
story.append(Paragraph("Figure 5. SRz axis relative to the tracked point, top view (beam along +y; the analyzer looks "
                       "at the surface from the lower left; +SN moves the plate away from the analyzer).", SM))
diff = [["", "2026-11-14 (capillary)", "2026-11-15 (zone plate)", "difference"],
        ["Beam spot: ST0", f"{sc:.4f}", f"{sz_:.4f}", f"{sz_ - sc:+.3f}"],
        ["Beam spot: SZ0", f"{zc:.4f}", f"{zz:.4f}", f"{zz - zc:+.3f}"],
        ["Spot on the plate at the same motors (x / y)", f"{uc:.3f} / {vc:.3f}", f"{uz:.3f} / {vz:.3f}",
         f"{uz - uc:+.3f} / {vz - vc:+.3f} ({((uz - uc) ** 2 + (vz - vc) ** 2) ** 0.5:.3f})"],
        ["Optic at the analyzer focus", "CPS 61.51", "ZPS 53.75", "different motors"],
        ["SRn axis on the plate (x / y)", f"{ao:.3f} / {bo:.3f}", f"{an:.3f} / {bn:.3f}",
         f"{an - ao:+.3f} / {bn - bo:+.3f} ({((an - ao) ** 2 + (bn - bo) ** 2) ** 0.5:.3f})"],
        ["SRz axis offset along ST / SN", f"{to:.3f} / {no:.3f}", f"{tn:.3f} / {nn:.3f}",
         f"{tn - to:+.3f} / {nn - no:+.3f}"],
        ["SRz axis vs tracked point (across / along the beam)", "", "", f"{dx:+.3f} / {dy:+.3f} "
         f"({(dx ** 2 + dy ** 2) ** 0.5:.3f})"]]
story.append(KeepTogether([table(diff, [62 * mm, 36 * mm, 36 * mm, 40 * mm]), Spacer(1, 3), Paragraph(
    "Mm throughout. The beam spot difference is an optics change (the two optics put their focus at different "
    "places on the plate). The SRn and SRz axis differences are not a mechanical change (same plate and sample, the "
    "stage was not touched): they are the error of the 2026-11-14 capillary values, which were fixed by ST / SZ "
    "readings of ±0.02 mm (SRn axis, about ±0.04 mm) and by capillary CPS foci (SRz axis across the beam, which "
    "the CPS did not resolve). The 2026-11-15 values come from SPEM maps (±4 µm) and zone-plate foci (~0.02 mm).",
    SM)]))


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#666666"))
    canvas.drawString(18 * mm, 10 * mm, "ANTARES stage alignment - zone-plate calibration 2026-11-15")
    canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"page {doc.page}")
    canvas.restoreState()


doc = SimpleDocTemplate(str(PDF), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                        bottomMargin=16 * mm, title="Zone-plate calibration and SRz-axis correction 2026-11-15",
                        author="ANTARES stage alignment")
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print(PDF)
