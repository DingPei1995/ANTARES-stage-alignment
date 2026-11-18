from dataclasses import replace

import numpy as np
import pytest

pytest.importorskip("scipy")

from quickalignment.cadmodel.build import DATA, split_triangles  # noqa: E402
from quickalignment.cadmodel.frame import F_CAD, R_CAD_TO_LAB, cad_dir_to_lab, cad_to_lab  # noqa: E402
from quickalignment.cadmodel.trimesh_ops import point_triangle, segment_segment, triangle_triangle  # noqa: E402
from quickalignment.core.stage import N_HAT, T_HAT, Z_HAT  # noqa: E402

TRI = np.array([[0.0, 0, 0], [10, 0, 0], [0, 10, 0]])


def one(t):
    return np.asarray(t, float)[None]


# --- exact distances ----------------------------------------------------------------------------------------
def test_point_triangle_regions():
    a, b, c = (one(v) for v in TRI)
    assert point_triangle(one([2, 2, 3]), a, b, c)[0] == pytest.approx(3.0)  # above the face
    assert point_triangle(one([-3, -4, 0]), a, b, c)[0] == pytest.approx(5.0)  # off the vertex
    assert point_triangle(one([5, -2, 0]), a, b, c)[0] == pytest.approx(2.0)  # off an edge


def test_degenerate_triangle_is_only_its_edges():
    a, b, c = one([0, 0, 0]), one([0, 0, 0]), one([10, 0, 0])
    assert point_triangle(one([5, 0, 2]), a, b, c)[0] == pytest.approx(2.0)
    assert point_triangle(one([5, 3, 0]), a, b, c)[0] == pytest.approx(3.0)


def test_segment_segment():
    d = segment_segment(one([0, 0, 0]), one([10, 0, 0]), one([5, -5, 2]), one([5, 5, 2]))
    assert d[0] == pytest.approx(2.0)  # skew, closest inside both
    d = segment_segment(one([0, 0, 0]), one([1, 0, 0]), one([3, 0, 0]), one([4, 0, 0]))
    assert d[0] == pytest.approx(2.0)  # collinear, end to end


def test_triangle_triangle_parallel_crossing_and_edges():
    t1 = one(TRI)
    assert triangle_triangle(t1, one(TRI + [0, 0, 1.5]))[0] == pytest.approx(1.5)
    crossing = one([[2, 2, -1], [2, 2, 1], [3, 1, 0]])  # pierces the face of t1
    assert triangle_triangle(t1, crossing)[0] == 0.0
    edge = one([[5, -1, 1], [5, -1, -1], [5, -6, 0]])  # beside the edge y = 0, 1 mm away
    assert triangle_triangle(t1, edge)[0] == pytest.approx(1.0)


def test_split_keeps_the_surface():
    t = np.array([[[0, 0, 0], [30, 0, 0], [0, 9, 0]]], float)
    s = split_triangles(t, 4.0)
    e = np.linalg.norm(s[:, [1, 2, 0]] - s, axis=2)
    assert e.max() <= 4.0 + 1e-9
    area = lambda x: 0.5 * np.linalg.norm(np.cross(x[:, 1] - x[:, 0], x[:, 2] - x[:, 0]), axis=1).sum()  # noqa: E731
    assert area(s) == pytest.approx(area(t))


# --- CAD frame ---------------------------------------------------------------------------------------------
def test_cad_frame():
    assert np.linalg.det(R_CAD_TO_LAB) == pytest.approx(1.0)
    assert np.allclose(cad_to_lab(F_CAD), 0)
    # analyzer acceptance cone (CAD (1, 0, 1)/sqrt2) -> -n; SN rails -> n; ST rails -> t; CAD up -> lab up
    assert np.allclose(cad_dir_to_lab(np.array([1, 0, 1]) / np.sqrt(2)), -N_HAT)
    assert np.allclose(cad_dir_to_lab(-np.array([1, 0, 1]) / np.sqrt(2)), N_HAT)
    assert np.allclose(cad_dir_to_lab(np.array([1, 0, -1]) / np.sqrt(2)), T_HAT)
    assert np.allclose(cad_dir_to_lab([0, 1, 0]), Z_HAT)


# --- the model (needs the built data) -----------------------------------------------------------------------
needs_data = pytest.mark.skipif(not DATA.exists(), reason="run python -m quickalignment.cadmodel.build first")


@pytest.fixture(scope="module")
def model():
    from quickalignment.cadmodel.model import CadCollisionModel
    return CadCollisionModel()


@needs_data
def test_reference_pose_is_the_drawing(model):
    tf = model.transforms(model.m0, model.default_optics())
    for link in ("piezo", "srn"):
        R, t = tf[link]
        assert np.allclose(R, np.eye(3)) and np.allclose(t, 0, atol=1e-9)


@needs_data
def test_stage_motors_move_the_parts(model):
    om = model.default_optics()
    m0 = model.m0
    R, t = model.transforms(replace(m0, st=m0.st + 1.0), om)["piezo"]
    assert np.allclose(R, np.eye(3)) and np.allclose(t, T_HAT)
    R, t = model.transforms(replace(m0, sz=m0.sz + 2.0), om)["srn"]
    assert np.allclose(t, 2 * Z_HAT)
    # the piezo moves the plate side, not the PI box
    tf = model.transforms(replace(m0, pix=m0.pix + 1000.0), om)
    assert np.linalg.norm(tf["piezo"][1]) == pytest.approx(1.0)
    assert np.allclose(tf["srn"][1], 0)
    # SRz turns about the vertical
    R, _ = model.transforms(replace(m0, srz=10.0), om)["piezo"]
    assert np.allclose(R @ Z_HAT, Z_HAT) and R[0, 0] == pytest.approx(np.cos(np.radians(10)))


@needs_data
def test_optics_anchors(model):
    om = model.default_optics()
    tf = model.transforms(model.m0, om)
    R, t = tf["zp"]
    assert np.allclose(R @ model.anchors["zp"] + t, model.optics.zone_plate_lens(om))
    assert np.allclose(model.optics.zone_plate_lens(om), [0, -24.32, 0], atol=1e-6)
    R, t = tf["osa"]
    assert np.allclose(R @ model.anchors["osa"] + t, [0, -3.5, 0])
    R, t = tf["cap"]
    beam = model.optics.capillary_beam(om)
    assert np.allclose(R @ model.anchors["cap_tip"] + t, beam.focus - model.working_distance * beam.direction)
    assert np.allclose(R @ model.cap_axis, beam.direction)


def test_zone_plates_mounted_on_the_bracket():
    from quickalignment.cadmodel.build import ANCHORS_CAD, PLATE_387_FRONT, ZP_SHIFTS
    # 95 eV holder 176: back (x 113.90) on the plate, bore (y 291.81, z 0) onto the upper hole (y 311.81, z -1)
    assert 113.90 + ZP_SHIFTS["zone_plate_95eV"][0] == pytest.approx(PLATE_387_FRONT)
    assert np.allclose([291.81, 0.0] + ZP_SHIFTS["zone_plate_95eV"][1:], [311.81, -1.0])
    # second holder 642: back (x 115.43) on the plate, centre (y 290.06, z -1) onto the lower hole (y 291.81)
    assert 115.43 + ZP_SHIFTS["zone_plate_2"][0] == pytest.approx(PLATE_387_FRONT)
    assert np.allclose([290.06, -1.0] + ZP_SHIFTS["zone_plate_2"][1:], [291.81, -1.0])
    # the 95 eV zone plate (vertical hole of 176, x 98.849) is the anchor, on the upper hole axis
    assert np.allclose(ANCHORS_CAD["zp"], [98.849 + 2.0, 311.81, -1.0])


def test_analyzer_front_from_the_drawing():
    from quickalignment.cadmodel.model import ANALYZER_PROFILE
    prof = np.array(ANALYZER_PROFILE)
    assert prof[0, 0] == 35.0  # front face 35 mm from the sample centre
    assert prof[1, 1] == pytest.approx(35.0 - 9.1 * np.sqrt(2))  # front face edge, Ø44.3
    assert 2 * prof[2:4, 1] == pytest.approx([52.0, 52.0])  # Ø52 nose ...
    assert prof[3, 0] - prof[0, 0] == pytest.approx(15.0)  # ... 15 mm long
    assert 2 * prof[-1, 1] == pytest.approx(150.0)  # Ø150 body
    # every corner at least 9.1 mm from the 45° line through the sample centre (free distance to metal)
    assert ((prof[1:, 0] - prof[1:, 1]) / np.sqrt(2) >= 9.1 - 1e-9).all()


def test_thinner_ceramic_spacers():
    from quickalignment.cadmodel.build import W_CAD, body_correction
    p = np.array([[[1.0, 330.0, -2.0]] * 3])
    # plate and the holder on the spacers stay; the boss 457 and the PI box come 1 mm towards the analyzer
    assert np.allclose(body_correction(493, "sample_plate", p), p)
    assert np.allclose(body_correction(506, "sample_stage", p), p)
    assert np.allclose(body_correction(457, "sample_stage", p) - p, W_CAD)
    assert np.allclose(body_correction(473, "PI_motors", p) - p, W_CAD)
    assert np.allclose(body_correction(176, "zone_plate_95eV", p), p)  # optics untouched
    # a spacer keeps its front face (w = -7.22) and loses 1 mm at the back (w = -10.72): 3.5 -> 2.5 mm
    front = F_CAD + (-7.22) * W_CAD
    back = F_CAD + (-10.72) * W_CAD
    tri = np.array([[front, back, back]])
    out = body_correction(244, "sample_stage", tri)
    assert np.allclose(out[0, 0], front) and np.allclose(out[0, 1], back + W_CAD)
    assert np.dot(out[0, 0] - out[0, 1], W_CAD) == pytest.approx(2.5)


@needs_data
def test_working_position_presets(model):
    zp = model.optics_preset("zone plate + OSA")
    assert model.optics.active_optic(zp) == "zone plate"
    assert (zp.osa_s, zp.osa_x, zp.osa_z) == (80.0, 0.5, 26.63)
    cap = model.optics_preset("capillary")
    assert model.optics.active_optic(cap) == "capillary"
    assert (cap.osa_s, cap.osa_x, cap.osa_z) == (20.0, 0.5, -5.0)  # OSA parked, X unchanged
    assert cap.zps == model.optics.config.zone_plate.zps_parked
    assert not any(r.hit for r in model.check(model.m0, cap))
    with pytest.raises(ValueError):
        model.optics_preset("nothing")


@needs_data
def test_xray_path_follows_the_optic_in_use(model):
    zp = model.beams(model.optics_preset("zone plate + OSA"))
    assert zp["active"] == "zone plate"
    p = np.array(zp["path"])
    assert np.allclose(p[:2, [0, 2]], 0)  # incoming beam fixed on the reference line x = 0, z = 0
    assert np.allclose(p[2], zp["focus"]) and np.allclose(zp["focus"], 0, atol=1e-6)
    cap_motors = model.optics_preset("capillary")
    cap = model.beams(cap_motors)
    assert cap["active"] == "capillary"
    assert np.allclose(np.array(cap["path"])[:2, [0, 2]], 0)
    assert np.allclose(cap["focus"], model.optics.capillary_beam(cap_motors).focus)
    none = model.beams(replace(cap_motors, cps=0.0, cpx=0.0))  # capillary parked, ZP parked: straight through
    assert none["active"] == "none" and none["focus"] is None
    assert np.allclose(np.array(none["path"])[:, [0, 2]], 0)


@needs_data
def test_align_capillary_onto_the_zone_plate_spot(model):
    from quickalignment.optics.geometry import OpticsMotors
    om = replace(model.optics_preset("capillary"), cap_rz=model.optics.config.capillary.cap_rz + 0.3)  # tilted beam
    spot = model.zone_plate_spot()
    assert np.allclose(spot, 0, atol=1e-9)
    res = model.align_capillary(om)
    new = OpticsMotors(**res["optics"])
    assert new.cps == om.cps and new.cap_rz == om.cap_rz and new.cap_rx == om.cap_rx  # only CPX, ZPZ move
    beam = model.optics.capillary_beam(new)
    rel = spot - beam.focus
    assert np.linalg.norm(rel - (rel @ beam.direction) * beam.direction) < 1e-9  # the beam passes the spot
    assert res["beam_miss"] < 1e-9
    assert res["focus_along_beam"] == pytest.approx(-(rel @ beam.direction))
    both = model.align_capillary(om, along_beam=True)
    assert np.allclose(model.optics.capillary_beam(OpticsMotors(**both["optics"])).focus, spot, atol=1e-9)
    # untilted: the moves are the offset across the beam (CPX + towards the analyzer = -x; ZPZ up)
    om0 = model.optics_preset("capillary")
    r0 = model.align_capillary(om0)
    off = np.array(r0["offset_now"])
    assert r0["d_cpx"] == pytest.approx(off[0], abs=1e-6) and r0["d_zpz"] == pytest.approx(-off[2], abs=1e-6)


@needs_data
def test_check_move_finds_a_collision_on_the_way(model):
    om = model.optics_preset("zone plate + OSA")
    far = replace(om, zps=om.zps + 30.0)  # the zone plate driven 30 mm towards the sample: it hits the stage
    res = model.check_move(model.m0, om, far, steps=4)
    assert res["first_hit"] is not None and res["first_hit"] <= 1.0
    calm = model.check_move(model.m0, om, replace(om, zps=om.zps - 2.0), steps=2)
    assert calm["first_hit"] is None


def test_load_stage_config_shifts_a_gating_configuration(tmp_path):
    import json
    from quickalignment.cadmodel.model import load_stage_config
    cfg = {"st0": -0.6773, "sz0": 41.143, "srn_axis_v": -0.1195}
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"stage_config": cfg, "check": {"plate": "gating"}}), encoding="utf-8")
    hc = load_stage_config(p)
    assert hc.plate == "gating" and hc.seat == 1.0
    assert hc.config.sz0 == pytest.approx(42.143) and hc.config.srn_axis_v == pytest.approx(0.8805)
    assert hc.original.sz0 == 41.143 and hc.sz_shift == pytest.approx(1.0)
    assert "41.1430 -> 42.1430" in hc.describe()
    assert load_stage_config(p, seat=0.8).config.sz0 == pytest.approx(41.943)  # measured seat
    assert load_stage_config(p, plate="standard").config.sz0 == 41.143  # override
    p.write_text(json.dumps({"stage_config": cfg}), encoding="utf-8")  # plate not recorded: standard
    hc = load_stage_config(p)
    assert hc.plate is None and hc.sz_shift == 0.0


@needs_data
def test_gating_layout_drawn_higher_in_the_holder(model):
    from quickalignment.core.geometry import GATING_PLATE, STANDARD_PLATE, SampleLayout
    std = model.layout_part(SampleLayout(plate=STANDARD_PLATE))
    gat = model.layout_part(SampleLayout(plate=GATING_PLATE))
    # the standard plate bottom (-7.75) is where the drawn plate is; the gating block bottom (-8.75) 1 mm higher
    assert std.tri[..., 1].min() == pytest.approx(-7.75)
    assert gat.tri[..., 1].min() == pytest.approx(-8.75 + 1.0)


@needs_data
def test_reference_is_free_and_zp_too_close_collides(model):
    om = model.default_optics()
    res = model.check(model.m0, om)
    assert not any(r.hit for r in res)
    near = {(r.a, r.b): r.distance for r in res if r.distance is not None}
    assert near[("sample_plate (CAD)", "OSA")] == pytest.approx(2.41, abs=0.05)
    res = model.check(model.m0, replace(om, zps=om.zps + 20.0))
    hits = {(r.a, r.b) for r in res if r.hit}
    assert ("sample_stage", "ZP_mount") in hits
