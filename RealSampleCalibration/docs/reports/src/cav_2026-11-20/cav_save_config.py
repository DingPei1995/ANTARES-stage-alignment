"""Save the 2026-11-20 Cav + zone-plate configuration (values from cav_make_config.py)."""
import json
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
ROOT = Path(r"D:\Codes\ANTARES-stage-alignment-main")
sys.path.insert(0, str(ROOT / "src"))
from quickalignment.core.calibration import CalibrationRecord, CalibrationStore  # noqa: E402
from quickalignment.core.stage import MotorPositions as M, OpticsCalibration, StageConfig  # noqa: E402

R = json.loads((HERE / "cav_make_config.json").read_text(encoding="utf-8"))
cfg = StageConfig(**R["new"])
M1 = M(st=-3.4982, sz=36.538, sn=-0.05173, srn=120.0, srz=0.0, pix=138, piy=142)
optics = OpticsCalibration(enabled=True, motors=M1, surface_w=6.0, optic_position=53.717, optic_sign=1,
                           optic_type="zone plate + OSA")
comment = (
    "Gating plate + zone plate, sample Cav (graphene), data of 2026-11-15 (CavData/*.nxs) re-analysed 2026-11-20. "
    "Replaces calibration_2026-11-17_153957_zone_plate.json (and 2026-11-15 15:13:56). "
    "Cav layout Cav.json: substrate H 1.0 mm (measured, was 0.748 from the by-eye SN), tracked point = device D1 "
    "(PIX 138 / PIY 142 at SRn 120 / SRz 0) at plate x 2.862 / y 4.548. "
    "Anchor: ST -3.4982, SZ 36.538, SN -0.05173, PIX 138, PIY 142; ZP working distance kept from 11-15 (ZPS 53.7502 "
    "focuses on the lab origin). Focus judged from the steepest edge of the fine PIX x ZPS scans: the point is in "
    "focus at ZPS 53.717, not 53.75 (the 4 SRz 0 SN slides with ST compensating, -2.556 / +0.752 / +1.202 / +1.701 mm "
    "along the beam, give 53.728 / 53.709 / 53.719 / 53.711, i.e. ZPS 1:1 within 0.011 mm), so the point sits "
    "0.033 mm upstream of the lab origin: ST0 -0.6717, SZ0 41.094, SN_f -1.0283 (was -0.7983: with H 1.0 the "
    "standard riser top is 0.23 mm further; contradicts the 0.5 mm Si substrate of 2026-11-14, open). "
    "SRn axis from the SRn 140 map (PIX 132 / PIY 84): u 0.1325 / v -0.1682 (relative to the point unchanged since "
    "11-15). SRz axis from SN-kept data only: SRz -5 / -10 / -15 / -20 line scans (left edge of the device stripe at "
    "PIY ~40, edge PIX measured; plate position of that edge from the SRz 0 slides, +-5 um) and their foci: "
    "offset_t -0.1878 +- 0.031, offset_n 2.361 +- 0.023, chi2 9 / 6 dof; the SRz axis is 0.26 mm closer to the point "
    "across the beam than in the 11-15 / 11-17 configurations (along the beam unchanged). All SN-kept sets (anchor, 4 "
    "slides, SRz -5..-20) reproduced within 0.016 mm in ZPS and 5 um in edge position; independent check SRn 140 / "
    "SRz -15: PIX 139 (found 138), ZPS 54.34 (found 54.33). Open: the two SRz -25 sets with SN moved (-1.856 / "
    "-1.581) focus 0.20 / 0.27 mm lower in ZPS than predicted while their PIX is within 2 / 9 um: a pure along-beam "
    "error, not an SN reading error (that would also move the point across the beam), not a marking error, not the "
    "SRz angle (both would show in PIX). To separate: SRz -25 with SN kept, and SRz -10 with SN moved.")
check = {
    "type": "zone-plate SPEM edge analysis (fine PIX x ZPS scans) + point tracking",
    "plate": "gating",
    "point_plate_uvw": [2.862, 4.548, 6.0],
    "layout": "Cav.json (S1 u 2.775 / v 4.6, 5.35 x 5.8, H 1.0; D1 left 2.762 / bottom 2.848)",
    "zps_point_in_focus_at_anchor": 53.717,
    "zps_lab_origin": 53.7502,
    "edge_sets": R["rows"],
    "tracked_point": R["points"],
    "srz_axis_fit": {"data": "SN-kept SRz -5..-20 (edge PIX + focus)", "srz_offset_t": [-0.1878, 0.0308],
                     "srz_offset_n": [2.361, 0.0234], "chi2": 8.95, "dof": 6},
    "rejected": "SRz axis fitted to the two SN-moved SRz -25 sets (offset_t +0.330, offset_n 2.668): misses the "
                "SRz -5..-20 foci by +0.06..+0.20 mm and the edge positions by 16-24 um",
    "open": ["SRz -25 with SN moved: focus 0.20 / 0.27 mm below the prediction (along the beam only)",
             "SN_f -1.028 (Cav, H 1.0) against -0.798 (2026-11-14, Si 0.5 mm): 0.23 mm"],
    "analysis": "RealSampleCalibration/docs/reports/2026-11-20_cav_zp_memo.md",
    "previous": ["2026-11-17 15:39:57 zone plate", "2026-11-15 15:13:56 zone plate", "2026-11-14 17:37:43 capillary"],
}
rec = CalibrationRecord(comment=comment, config=cfg, optics=optics, check=check)
saved = CalibrationStore(ROOT / "configs").save(rec, now=datetime.now())
print(saved.path)
latest = CalibrationStore(ROOT / "configs").latest("zone plate + OSA")
print("latest zone plate:", latest.path.name, latest.config)
