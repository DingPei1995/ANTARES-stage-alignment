import json

import pytest

from quickalignment.core.geometry import GATING_PLATE, STANDARD_PLATE, Sample, SampleLayout
from quickalignment.core.stage import (
    MotorPositions, StageConfig, StageModel, apply_found_offset, check_height, checked_sn, config_for_plate,
    found_offset, height_from_sn, sn_from_height,
)

CFG = StageConfig(st0=-0.8, sz0=41.2, sn_f=-0.3, srn_axis_u=0.1, srn_axis_v=-0.1, srz_offset_t=-0.01,
                  srz_offset_n=2.775)


@pytest.mark.parametrize("plate", [STANDARD_PLATE, GATING_PLATE])
def test_height_from_sn_puts_the_top_surface_on_the_focal_plane(plate):
    layout = SampleLayout(plate=plate, samples=[Sample("S1", 1.0, 2.0, height=0.525)])
    s = layout.samples[0]
    dh = check_height(CFG, layout, s, 0.45)
    assert s.height == pytest.approx(0.75) and dh == pytest.approx(0.225) and s.sn_checked == 0.45
    model = StageModel(CFG, plate)
    st, sz, sn = model.reference_motors(s.u, s.v, s.surface_height(plate))
    assert sn == pytest.approx(0.45)  # the start table gives back the SN of the check
    m = MotorPositions(st=st, sn=0.45, sz=sz, srn=CFG.srn_ref, srz=0.0)
    assert model.focal_plane_height(m) == pytest.approx(s.surface_height(plate))
    assert sn_from_height(CFG, s.height, plate) == pytest.approx(0.45)
    assert height_from_sn(CFG, CFG.sn_f, plate) == 0.0
    assert checked_sn(layout, "S1") == 0.45 and checked_sn(layout, "nothing") is None


def test_found_here_moves_the_plate_in_the_holder():
    """A plate sitting 1.3 mm higher than usual and a sample drawn 0.05 mm off in x: after found here on one sample,
    the other sample (not found) is predicted where it really is."""
    true_layout = SampleLayout(samples=[Sample("A", 2.0, 3.0, height=0.5), Sample("B", -3.0, -1.0, height=0.6)])
    drawn = SampleLayout(samples=[Sample("A", 2.05, 3.0, height=0.5), Sample("B", -3.0, -1.0, height=0.6)])
    truth = StageModel(config_for_plate(CFG, 0.0, 1.3))
    a = true_layout.samples[0]
    for srn, srz in ((120.0, 0.0), (135.0, -10.0)):  # found at the start rotation or turned
        layout = SampleLayout(samples=[Sample(**{**s.__dict__, "devices": []}) for s in drawn.samples])
        m = truth.motors_for_target(a.u, a.v, 5.0 + a.height, srn, srz)
        model = StageModel(config_for_plate(CFG, 0.0, layout.plate_offset_v))
        du, dv, dw = found_offset(model, m, layout.samples[0].u, layout.samples[0].v, 5.5)
        apply_found_offset(model.config, layout, layout.samples[0], du, dv, dw)
        assert layout.plate_offset_v == pytest.approx(1.3, abs=1e-9)
        assert layout.samples[0].u == pytest.approx(2.0) and layout.samples[0].v == 3.0  # y of the sample kept
        assert layout.samples[0].height == pytest.approx(0.5)
        new = StageModel(config_for_plate(CFG, 0.0, layout.plate_offset_v))
        b = layout.samples[1]
        for srn2, srz2 in ((120.0, 0.0), (140.0, -15.0)):
            want = truth.motors_for_target(b.u, b.v, 5.6, srn2, srz2)
            got = new.motors_for_target(b.u, b.v, 5.6, srn2, srz2)
            assert (got.st, got.sz, got.sn) == pytest.approx((want.st, want.sz, want.sn), abs=1e-9)


def test_found_here_height_keeps_the_checked_sn_consistent():
    layout = SampleLayout(samples=[Sample("A", 0.0, 0.0, height=0.5)])
    s = layout.samples[0]
    check_height(CFG, layout, s, 0.2)
    apply_found_offset(CFG, layout, s, 0.0, 0.0, 0.03)
    assert s.sn_checked == pytest.approx(sn_from_height(CFG, s.height, layout.plate))


def test_layout_file_keeps_offset_and_check():
    layout = SampleLayout(plate=GATING_PLATE, samples=[Sample("A", 1.0, 1.0, height=0.7, sn_checked=0.4),
                                                       Sample("B", -2.0, 1.0)], plate_offset_v=1.25)
    back = SampleLayout.from_dict(json.loads(json.dumps(layout.to_dict())))
    assert back.plate_offset_v == 1.25 and back.samples[0].sn_checked == 0.4 and back.samples[1].sn_checked is None
    old = layout.to_dict()
    del old["plate_offset_v"]
    for s in old["samples"]:
        del s["sn_checked"]
    back = SampleLayout.from_dict(old)  # files written before
    assert back.plate_offset_v == 0.0 and back.samples[0].sn_checked is None


def _session(tmp_path, plate="gating"):
    from quickalignment.agent.alignment import AlignmentSession
    rec = {"created": "2026-11-15 15:13:56", "stage_config": {"st0": -0.8, "sz0": 41.2, "sn_f": -0.3},
           "optics": {"optic_type": "capillary"}, "check": {"plate": "gating"}}
    (tmp_path / "calibration_2026-11-15_151356_capillary.json").write_text(json.dumps(rec), encoding="utf-8")
    s = AlignmentSession(tmp_path)
    s.start(plate=plate, optic="capillary")
    return s


def test_agent_height_check_and_bring_to_beam(tmp_path):
    s = _session(tmp_path)
    s.add_sample(x=1.0, y=2.0, length=2.0, width=2.0, height=0.525, name="S1")
    s.add_sample(x=-3.0, y=2.0, length=2.0, width=2.0, height=0.525, name="S2")
    out = s.check_height("S1", 0.45)
    assert out["sample"]["height"] == pytest.approx(0.75) and out["sample"]["height_checked_at_sn"] == 0.45
    row = next(r for r in out["positions"] if r["target"] == "S1")
    assert row["SN"] == pytest.approx(0.45) and row["height_checked"]
    # at another rotation, with the stage at another SN: the SN of the check is kept
    r = s.bring_to_beam("S1", {"srn": 140.0, "srz": -10.0, "sn": None})
    assert r["stage"]["sn"] == pytest.approx(0.45) and r["sn_from_height_check"] == pytest.approx(0.45)
    assert "correct_sn" not in r.get("advice", "")
    # an explicit SN wins; a sample not checked keeps the stage SN
    assert s.bring_to_beam("S1", {"sn": 0.1})["stage"]["sn"] == pytest.approx(0.1)
    assert "sn_from_height_check" not in s.bring_to_beam("S2", {"sn": 0.1})
    s.update_sample("S1", height=0.6)  # typed by hand: no longer checked
    assert "height_checked_at_sn" not in s.samples()["samples"][0]
    with pytest.raises(Exception):
        s.check_height("S1", -2.0)  # below the plate top


def test_agent_found_here_moves_the_plate(tmp_path):
    s = _session(tmp_path)
    s.add_sample(x=1.0, y=2.0, length=2.0, width=2.0, height=0.5, name="S1")
    s.add_sample(x=-3.0, y=-1.0, length=2.0, width=2.0, height=0.5, name="S2")
    before = {r["target"]: r for r in s.sample_positions()["positions"]}
    p = before["S1"]
    out = s.found_here("S1", {"st": p["ST"] - 0.02, "sz": p["SZ"] - 1.5, "sn": p["SN"]})
    assert out["plate_offset_mm"]["after"] == pytest.approx(1.5, abs=1e-6)
    assert "warning" not in out  # 1.5 mm in SZ is the plate, not a calibration problem
    after = {r["target"]: r for r in out["positions"]}
    assert after["S1"]["SZ"] == pytest.approx(p["SZ"] - 1.5, abs=1e-6)
    assert after["S1"]["ST"] == pytest.approx(p["ST"] - 0.02, abs=1e-6)
    assert after["S2"]["SZ"] == pytest.approx(before["S2"]["SZ"] - 1.5, abs=1e-6)  # the whole plate moved
    assert after["S2"]["ST"] == pytest.approx(before["S2"]["ST"], abs=1e-6)  # x only for the found sample
    assert s.samples()["samples"][0]["y"] == pytest.approx(2.0)  # the drawing stays
