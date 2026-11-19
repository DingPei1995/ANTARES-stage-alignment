import numpy as np
import pytest

from quickalignment.core.geometry import PLATE_SEAT_V, plate_seat_v
from quickalignment.core.stage import MotorPositions, StageConfig, StageModel, config_for_plate


@pytest.fixture
def seat_1mm(monkeypatch):
    """The mechanism with a gating plate seated 1 mm higher (the default is 0 since 2026-11-19)."""
    monkeypatch.setitem(PLATE_SEAT_V, "gating", 1.0)


def test_gating_plate_sits_like_the_standard_plate():
    # measured 2026-11-19: +0.014 / +0.077 mm (pin springs back), not the 1.0 mm of the drawing
    assert plate_seat_v("gating") == 0.0 and plate_seat_v("standard") == 0.0 and plate_seat_v(None) == 0.0


def test_config_for_plate_moves_the_plate_frame_with_the_seat(seat_1mm):
    gating = StageConfig(st0=-0.68, sz0=41.143, sn_f=-0.8, srn_axis_u=0.10, srn_axis_v=-0.12, srz_offset_t=-0.01,
                         srz_offset_n=2.775)
    seat = plate_seat_v("gating")
    assert seat == 1.0
    standard = config_for_plate(gating, seat, 0.0)
    assert standard.sz0 == pytest.approx(gating.sz0 + seat) and standard.srn_axis_v == pytest.approx(-0.12 + seat)
    assert (standard.st0, standard.sn_f, standard.srz_offset_n) == (gating.st0, gating.sn_f, gating.srz_offset_n)
    # a holder point is at v_std in the standard frame and v_std - seat in the gating frame: same lab point at any
    # motor positions (rotations included)
    for m in (MotorPositions(st=-3.5, sn=-0.05, sz=36.5), MotorPositions(st=-2.0, sn=0.3, sz=37.0, srn=140.0,
                                                                         srz=-15.0, pix=120.0, piy=180.0)):
        for u, v, w in ((0.0, 0.0, 5.0), (2.8, 4.6, 5.75), (-4.0, -7.0, 0.0)):
            a = StageModel(standard).plate_to_lab(m, u, v, w)
            b = StageModel(gating).plate_to_lab(m, u, v - seat, w)
            assert np.allclose(a, b, atol=1e-12)
    assert config_for_plate(standard, 0.0, seat) == gating


def _record(plate):
    from quickalignment.core.calibration import CalibrationRecord
    return CalibrationRecord(config=StageConfig(sz0=41.2, srn_axis_v=-0.05),
                             check=None if plate is None else {"plate": plate})


@pytest.mark.parametrize("made, mounted, d", [("gating", "gating", 0.0), ("standard", "standard", 0.0),
                                             (None, "standard", 0.0), ("gating", "standard", 1.0),
                                             ("standard", "gating", -1.0), (None, "gating", -1.0),
                                             ("gating", "custom", 1.0)])
def test_record_config_for_the_plate_mounted(made, mounted, d, seat_1mm):
    r = _record(made)
    c = r.config_for(mounted)
    assert c.sz0 == pytest.approx(41.2 + d) and c.srn_axis_v == pytest.approx(-0.05 + d)
    assert r.plate_shift(mounted) == d
    assert (r.plate_note(mounted) == "") == (d == 0.0)
    converted = r.for_plate(mounted)
    assert converted.config == c and (converted is r) == (d == 0.0)
    assert converted.config_for(mounted) == c  # not shifted twice
    assert r.config.sz0 == 41.2  # the record itself is unchanged


def test_real_configs_record_their_plate():
    from quickalignment.core.calibration import CalibrationStore
    recs = {r.path.name: r for r in CalibrationStore().records()}
    if "calibration_2026-11-15_151356_zone_plate.json" not in recs:
        pytest.skip("configs folder not present")
    for name in ("calibration_2026-11-14_173743_capillary.json", "calibration_2026-11-15_151356_capillary.json",
                 "calibration_2026-11-15_151356_zone_plate.json"):
        assert recs[name].plate == "gating"
        assert recs[name].config_for("gating") == recs[name].config
        assert recs[name].config_for("standard") == recs[name].config  # same seat (2026-11-19)
    new = recs.get("calibration_2026-11-19_123901_zone_plate.json")
    if new is not None:
        assert new.plate == "standard" and new.config_for("gating") == new.config


def test_alignment_agent_uses_the_plate_correction(tmp_path, seat_1mm):
    import json
    from quickalignment.agent.alignment import AlignmentSession
    rec = {"created": "2026-11-15 15:13:56", "stage_config": {"st0": -0.8, "sz0": 41.2},
           "optics": {"optic_type": "capillary"}, "check": {"plate": "gating"}}
    (tmp_path / "calibration_2026-11-15_151356_capillary.json").write_text(json.dumps(rec), encoding="utf-8")
    for plate, sz0 in (("gating", 41.2), ("standard", 42.2)):
        s = AlignmentSession(tmp_path)
        info = s.start(plate=plate, optic="capillary")["configuration"]
        assert info["made_with_plate"] == "gating"
        assert info["constants"]["sz0"] == pytest.approx(sz0)
        assert ("plate_correction" in info) == (plate == "standard")
        centre = s.sample_positions()["positions"][0]
        assert centre["SZ"] == pytest.approx(sz0)
