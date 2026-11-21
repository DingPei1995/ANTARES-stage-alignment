"""The agent API and its MCP server: the three tools driven as an agent would, without Qt."""

import json
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from quickalignment.agent import AgentAPI, APIError
from quickalignment.agent.mcp_server import TOOLS, Server
from quickalignment.core.calibration import CalibrationStore
from quickalignment.core.geometry import GATING_PLATE
from quickalignment.core.stage import MotorPositions, StageModel
from quickalignment.realsample.fit import on_beam, protocol_sets

ROOT = Path(__file__).resolve().parent.parent
PHOTO = ROOT / "tests" / "data" / "gating_plate_photo.jpg"
CORNERS = [(207.5, 212.0), (543.5, 298.0), (466.5, 624.0), (128.0, 542.0)]


@pytest.fixture
def configs(tmp_path):
    folder = tmp_path / "configs"
    shutil.copytree(ROOT / "configs", folder)
    return folder


@pytest.fixture
def api(configs):
    return AgentAPI(configs)


def started(api, plate="gating"):
    api.alignment.start(plate, "capillary")
    api.alignment.register_photo(CORNERS, path=str(PHOTO))
    return api.alignment


# -- alignment ------------------------------------------------------------------------------------------------
def test_start_asks_for_what_is_missing(api):
    with pytest.raises(APIError, match="optic"):
        api.alignment.start("standard", None)
    with pytest.raises(APIError, match="start"):
        api.alignment.sample_positions()
    with pytest.raises(APIError, match="custom_plate_mm"):
        api.alignment.start("custom", "capillary")
    with pytest.raises(APIError, match="at least 4.5"):  # the holder would touch the OSA
        api.alignment.start("custom", "zone plate", {"length": 8, "width": 6, "height": 4.2})
    out = api.alignment.start("custom", "zone plate", {"length": 8, "width": 6, "height": 6.2})
    assert out["optic"] == "zone plate + OSA" and "Custom plate" in out["plate"]
    assert [c["number"] for c in out["photo_corners"]] == [1, 2, 3, 4]
    assert out["photo_corners"][0]["plate_mm"] == [-4.0, 3.0]


def test_photo_registration_and_images(api):
    a = api.alignment
    a.start("gating", "capillary")
    grid = a.photo_grid(str(PHOTO))
    assert grid["image_png"][:4] == b"\x89PNG" and grid["photo_size"] == [800, 850]
    zoom = a.photo_grid(str(PHOTO), region=[150, 180, 260, 250], marks=[{"x": 207.5, "y": 212, "label": "1"}])
    assert zoom["region"] == [150, 180, 260, 250] and zoom["grid_step_px"] < grid["grid_step_px"]
    with pytest.raises(APIError, match="order"):  # clicked the wrong way round
        a.register_photo(CORNERS[::-1], path=str(PHOTO))
    reg = a.register_photo(CORNERS, path=str(PHOTO))
    assert 25 < reg["pixels_per_mm"] < 40 and not reg["warnings"]
    corners = a.photo_to_plate(CORNERS)["plate_mm"]
    assert [v for c in corners for v in (c["x"], c["y"])] == pytest.approx([-5.5, 7.75, 5.5, 7.75, 5.5, -2.75, -5.5, -2.75])
    back = a.plate_to_photo([[-5.5, 7.75]])["photo_px"][0]
    assert back == pytest.approx(CORNERS[0], abs=0.1)
    assert a.photo_overlay()["image_png"][:4] == b"\x89PNG"
    assert a.plate_view()["image_png"][:4] == b"\x89PNG"
    # without the file: corners read on the image seen in the chat
    reg = a.register_photo(CORNERS, image_size=[800, 850], photo_id="chat")
    with pytest.raises(APIError, match="without its file"):
        a.photo_overlay("chat")


def test_detection_with_a_picked_sample_colour(api):
    a = started(api)
    on_substrate = a.plate_to_photo([[3.65, 6.15]])["photo_px"][0]
    found = a.detect_samples(sample_colors_px=[on_substrate])["detections"]
    big = max(found, key=lambda d: d["area_mm2"])
    assert big["length"] > 6 and big["width"] > 6  # the black substrate, not the silver paint
    assert a.samples()["samples"] == []  # detection adds nothing


def test_samples_positions_and_found_here(api):
    a = started(api)
    out = a.add_sample_from_photo([[290, 330], [520, 370], [480, 590], [250, 545]], height=0.525, name="flake")
    s = out["added"]
    assert s["name"] == "flake" and len(out["edge_angles_deg"]) == 4
    dev = a.add_device("flake", "D1", x=s["x"] + 0.5, y=s["y"] - 0.3)
    assert dev["added"] == "flake/D1" and not dev["warnings"]
    rows = {r["target"]: r for r in a.sample_positions()["positions"]}
    c = a.record.config
    assert rows["flake/D1"]["ST"] == pytest.approx(c.st0 - (s["x"] + 0.5), abs=1e-3)
    assert rows["flake/D1"]["SN"] == pytest.approx(c.sn_f + 0.525, abs=1e-3)
    assert "flake" not in rows  # a substrate is listed by its devices
    # the device is really 0.2 mm further right and 0.1 mm lower: found there, its sample follows
    model = a.model
    true = model.motors_for_target(s["x"] + 0.7, s["y"] - 0.4, 5.525, srn=140, srz=-10)
    fh = a.found_here("flake/D1", {k: getattr(true, k) for k in ("st", "sn", "sz", "srn", "srz")})
    assert fh["shift_mm"]["dx"] == pytest.approx(0.2, abs=1e-6) and fh["shift_mm"]["dy"] == pytest.approx(-0.1, abs=1e-6)
    rows = {r["target"]: r for r in fh["positions"]}
    assert rows["flake/D1"]["ST"] == pytest.approx(c.st0 - (s["x"] + 0.7), abs=1e-3)
    big = a.found_here("flake/D1", {"st": true.st + 0.5, "sn": true.sn, "sz": true.sz, "srn": 140, "srz": -10},
                       apply=False)
    assert "calibration" in big["warning"]


def test_bring_to_beam_rotate_and_edge(api):
    a = started(api)
    a.add_sample(2.0, 3.0, 3.0, 2.0, 0.525, name="S1")
    sn_focus = round(a.record.config.sn_f + 0.525, 3)  # S1's surface at the analyzer focus (newest config)
    a.set_position({"st": 0.0, "sn": sn_focus, "sz": 40.0, "srn": 120.0, "srz": 0.0})
    on = a.bring_to_beam("S1")
    m = MotorPositions(**on["stage"])
    hit = a.beam_on({k: on["stage"][k] for k in ("st", "sn", "sz", "srn", "srz")})
    assert hit["beam_lands_on"] == "S1" and hit["plate_mm"] == pytest.approx([2.0, 3.0], abs=1e-3)
    assert m.sn == sn_focus and on["focus_ok"]
    far = a.bring_to_beam("S1", {"sn": 1.0})
    assert not far["focus_ok"] and "correct_sn" in far["advice"]
    focus = a.bring_to_beam("S1", {"sn": 1.0}, correct_sn=True)
    assert focus["distance_from_analyzer_focus_um"] == 0
    rot = a.rotate(140.0, -10.0, motors=on["stage"])
    assert rot["point"]["on"] == "S1" and rot["sn_kept"]["stage"]["sn"] == pytest.approx(sn_focus)
    assert rot["sn_corrected"]["distance_from_analyzer_focus_um"] == 0
    assert rot["recommended"] in ("sn_kept", "sn_corrected")
    new = MotorPositions(**rot["sn_corrected"]["stage"])
    assert np.linalg.norm(a.model.plate_to_lab(new, 2.0, 3.0, 5.525)) < 2e-4  # positions rounded to 0.1 µm
    # an edge at +30 deg on the plate is along the slit after turning SRn by -30
    edge = a.align_edge([0, 0], [np.cos(np.radians(30)), np.sin(np.radians(30))], plate_mm=True, current_srn=120)
    assert edge["edge_angle_on_plate_deg"] == pytest.approx(30)
    assert edge["srn_options"][0]["SRn"] == pytest.approx(90.0)
    vertical = a.align_edge([0, 0], [1, 1], along="vertical", plate_mm=True, current_srn=120)
    assert vertical["srn_options"][0]["SRn"] == pytest.approx(165.0)
    none = a.align_edge([0, 0], [1, 0], along="vertical", plate_mm=True, current_srn=120)
    assert none["srn_options"] == [] and "remount" in none["note"]
    assert a.collision_check(on["stage"])["collision"] == []


def test_bz_angles(api):
    a = started(api)
    out = a.bz_angles(3.282, 95.0, [0.0, 0.0], [0.0, 22.0], "K", "K", 0, 95.0, map_srn=120, map_srz=0)
    assert out["best"] is not None and "SRn" in out["best"]
    assert out["check"]["from_lattice"] == pytest.approx(4 * np.pi / (3 * 3.282), abs=1e-3)


def test_bz_point_to_keep_srn(api):
    """2026-11-14, graphene with the slit along Γ–K: K read at θ 1, φ -0.86 at 115 eV (SRn 120 / SRz -24), wanted at
    φ -1 at 95 eV with the in-plane orientation kept: only SRz turns."""
    a = api.alignment
    a.start("gating", "capillary", configuration="calibration_2026-11-14_173743_capillary.json")
    a.add_sample(2.687, 4.666, 0.2, 0.2, 0.748, name="Cav")
    out = a.bz_point_to(2.46, 115.0, [1.0, -0.86], 120, -24, hv=95.0, target_angles=[0, -1], keep_srn=True,
                        sample="Cav")
    best = out["solutions"][0]
    assert best["SRn"] == 120 and best["SRz"] == pytest.approx(-25.88, abs=0.05)
    assert best["phi"] == pytest.approx(-1.0, abs=1e-3) and best["theta"] == pytest.approx(1.08, abs=0.05)
    assert not out["frame"]["gamma_given"] and out["frame"]["surface_tilt_from_plate_deg"] == pytest.approx(6.45, abs=0.05)
    assert out["positions_at_focus"]["stage"]["srz"] == pytest.approx(best["SRz"], abs=0.01)
    # same hv, same angles: the map position itself
    same = a.bz_point_to(2.46, 115.0, [1.0, -0.86], 120, -24, target_angles=[1.0, -0.86])["solutions"][0]
    assert same["SRn"] == pytest.approx(120, abs=0.01) and same["SRz"] == pytest.approx(-24, abs=0.01)
    # free SRn reaches θ = 0 as well
    free = a.bz_point_to(2.46, 115.0, [1.0, -0.86], 120, -24, hv=95.0, target_angles=[0, -1])["solutions"][0]
    assert free["theta"] == pytest.approx(0, abs=1e-3) and free["SRn"] != pytest.approx(120, abs=0.5)


def test_found_here_not_in_focus_and_old_configuration(api):
    """2026-11-14: a position noted with the 2026-10-24 configuration, SN not at the analyzer focus: x, y follow from
    that configuration, H is kept (found_here used to turn the SN offset into a 1.9 mm height)."""
    a = api.alignment
    a.start("gating", "capillary", configuration="calibration_2026-11-14_173743_capillary.json")
    a.add_sample(-2.0, 2.0, 11.0, 10.0, 0.748, name="Cav")
    old = {"srn": 120, "srz": -24, "st": -6, "sz": 35.2, "sn": 0}
    out = a.found_here("Cav", old, configuration="calibration_2026-10-24_235500_capillary.json")
    s = out["sample"]
    assert s["height"] == pytest.approx(0.748) and out["shift_mm"]["dH"] == 0
    # H 0.748 kept: x 2.693 (found at the beamline: x 2.687); with the old frame's 0.525 it was 2.607
    assert s["x"] == pytest.approx(2.693, abs=0.01) and s["y"] == pytest.approx(5.429, abs=0.01)
    assert a.motors is None  # an old position is not the stage now
    # at_focus=false with the configuration in use: H kept, the sample put where the beam crosses it
    m = {"srn": 120, "srz": -10, "st": -4.0, "sz": 36.0, "sn": 0.5}
    out = a.found_here("Cav", m, at_focus=False)
    assert out["sample"]["height"] == pytest.approx(0.748)
    hit = a.beam_on(m)["plate_mm"]
    assert hit == pytest.approx([out["sample"]["x"], out["sample"]["y"]], abs=2e-3)
    # height_exact: H known precisely, kept; x / y from where the beam crosses the surface (plate offset moves y)
    m = {"srn": 120, "srz": 0, "st": -3.0, "sz": 36.0, "sn": 0.8}
    hit = a.beam_on(m)["plate_mm"]
    out = a.found_here("Cav", m, height_exact=True)
    assert out["sample"]["height"] == pytest.approx(0.748) and out["shift_mm"]["dH"] == 0
    assert "marked exact" in out["height_kept"] and out["sample"]["x"] == pytest.approx(hit[0], abs=2e-3)
    # an H from the SN set by eye is not exact unless the known height is given; given, it replaces it (check kept)
    rows = {r["target"]: r for r in a.sample_positions()["positions"]}
    assert rows["Cav"]["SN_source"].startswith("from H")
    a.check_height("Cav", 0.9)
    rows = {r["target"]: r for r in a.sample_positions()["positions"]}
    assert rows["Cav"]["SN_source"] == "set by eye" and rows["Cav"]["SN"] == pytest.approx(0.9, abs=1e-4)
    with pytest.raises(APIError, match="SN set by eye"):
        a.found_here("Cav", m, height_exact=True)
    out = a.found_here("Cav", m, height_exact=True, height=0.525)
    assert out["sample"]["height"] == pytest.approx(0.525) and "height_checked_at_sn" not in out["sample"]
    assert "SN set by eye 0.900" in out["sn_by_eye_check"] and out["shift_mm"]["dH"] == 0
    assert out["sample"]["x"] == pytest.approx(a.beam_on(m)["plate_mm"][0], abs=2e-3)


def test_device_photo_from_point_pairs(api):
    a = started(api)
    a.add_sample(0.0, 2.0, 4.0, 4.0, 0.5, name="sub")
    # microscope photo: 100 px per mm, not turned, origin at the substrate's lower left corner (-2, 0), y down
    pairs = [{"photo": [0, 400], "plate_mm": [-2, 0]}, {"photo": [400, 0], "plate_mm": [2, 4]},
             {"photo": [400, 400], "plate_mm": [2, 0]}]
    reg = a.register_device_photo(pairs, photo_id="micro")
    assert reg["pair_rms_mm"] == pytest.approx(0, abs=1e-9) and reg["mm_per_px"] == pytest.approx(0.01)
    dev = a.add_device("sub", "FET", photo_px=[150, 250], photo_id="micro")
    assert [dev["x"], dev["y"]] == pytest.approx([-0.5, 1.5])
    # the same photo turned by 90° on the plate: the direction (bottom edge of the substrate) gives the orientation, the
    # pairs scale and shift only (least squares)
    direction = {"photo": [[0, 0], [0, 300]], "plate_mm": [[-1.5, 0], [2, 0]]}  # not the same places, same direction
    pairs = [{"photo": [400, 0], "plate_mm": [-2, 4]}, {"photo": [0, 400], "plate_mm": [2, 0]},
             {"photo": [400, 400], "plate_mm": [2, 4]}]
    reg = a.register_device_photo(pairs, photo_id="turned", direction=direction)
    assert reg["rotation_deg"] == pytest.approx(90) and reg["pair_rms_mm"] == pytest.approx(0, abs=1e-9)
    assert "no distortion" in reg["transform"] and reg["warnings"] == []
    dev = a.add_device("sub", "FET2", photo_px=[100, 300], photo_id="turned")
    assert [dev["x"], dev["y"]] == pytest.approx([1.0, 1.0])
    with pytest.raises(APIError):
        a.register_device_photo(pairs, direction={"photo": [[0, 0]], "plate_mm": [[0, 0], [1, 0]]})


def test_session_round_trip(api, tmp_path):
    a = started(api)
    a.add_sample(1.0, 2.0, 2.0, 2.0, 0.3, name="A")
    a.add_device("A", "d", x=1.2, y=2.1)
    path = a.save_session(str(tmp_path / "plate"))["saved"]
    b = AgentAPI(api.configs).alignment
    status = b.load_session(path, "capillary")
    assert status["samples"][0]["devices"][0]["name"] == "d"
    assert b.layout.plate.key == "gating"


# -- real-sample calibration ---------------------------------------------------------------------------------
def test_real_sample_calibration_full_mode(api, configs):
    r = api.real_sample
    assert r.guide()["step"] == "start"
    out = r.start("full", "capillary", "standard", 0.5, 1.0, 0.3)
    assert out["step"] == "measure sets" and len(out["sets"]) == 5
    newest = CalibrationStore(configs).latest("capillary")
    true = replace(newest.config, st0=newest.config.st0 + 0.12, srn_axis_u=0.3, srz_offset_n=2.9)
    model = StageModel(true)
    for s in protocol_sets(120.0, "full"):
        m = model.motors_for_target(0.5, 1.0, 5.3, srn=s.srn, srz=s.srz)
        r.measure_set(s.name.split(" ")[0], m.st, m.sz, m.sn, optic=60.0)
    fit = r.fit()
    assert fit["rms_mm"] < 1e-6
    values = {c["name"]: c["value"] for c in fit["constants"]}
    assert values["ST0"] == pytest.approx(true.st0, abs=1e-4) and values["SRn axis x"] == pytest.approx(0.3, abs=1e-4)
    assert fit["step"] == "test points" and len(fit["test_points"]) == 6
    for t in fit["test_points"]:
        r.answer_test(t["name"].split(" ")[0], found=True)
    assert r.guide()["step"] == "save"
    saved = r.save("agent test")
    assert Path(saved["saved"]).exists() and CalibrationStore(configs).latest("capillary").config.st0 == \
        pytest.approx(true.st0, abs=1e-4)


def test_real_sample_optics_mode_needs_a_configuration(api, configs, tmp_path):
    empty = AgentAPI(tmp_path / "none").real_sample
    with pytest.raises(APIError, match="full"):
        empty.start("optics", "capillary", "standard", 0, 0, 0)
    out = api.real_sample.start("optics", "capillary", "gating", 1.5, 2.8, 0.525)
    assert out["kept_from_previous"] and out["sets"][0]["sn"].startswith("kept")
    assert out["sets"][0]["expected_from"] == "newest configuration"
    with pytest.raises(APIError, match="Not enough data|set"):
        api.real_sample.fit()


def test_real_sample_full_mode_sn_kept(api, configs):
    """As at the beamline: set 1 at the analyzer focus, rotated sets with SN kept and the optic refocused; the
    expected positions follow set 1 once it is measured; test points keep SN."""
    r = api.real_sample
    r.start("full", "capillary", "gating", 1.284, 0.775, 0.525)
    newest = CalibrationStore(configs).latest("capillary")
    true = replace(newest.config, st0=newest.config.st0 - 0.6, sz0=newest.config.sz0 + 0.4, sn_f=-0.825,
                   srn_axis_u=-0.1, srz_offset_n=2.3)
    plate = GATING_PLATE
    model, uvw, focus = StageModel(true, plate), (1.284, 0.775, plate.total_thickness + 0.525), 61.45
    ref = model.motors_for_target(*uvw, srn=120.0, srz=0.0)
    r.measure_set("1", ref.st, ref.sz, ref.sn, optic=focus)
    table = r.status()["sets"]
    assert table[1]["expected_from"].startswith("set 1") and table[1]["expected"]["SN"] == pytest.approx(ref.sn)
    with pytest.raises(APIError, match="optic"):
        r.measure_set("3", -3.0, 40.0, ref.sn)
    r.add_set("6 SRn and SRz", 100.0, -5.0)
    for s in r.sets[1:]:
        if s.srz > 0:
            continue  # leave the positive SRz set unmeasured
        st, sz, optic = on_beam(model, uvw, s.srn, s.srz, ref.sn, 150.0, 150.0, focus)
        r.measure_set(s.name.split(" ")[0], st, sz, ref.sn, optic=optic)
    fit = r.fit()
    assert fit["rms_mm"] < 1e-6
    values = {c["name"]: c["value"] for c in fit["constants"]}
    assert values["SN_f"] == pytest.approx(-0.825, abs=1e-4) and values["SRz offset SN"] == pytest.approx(2.3, abs=1e-4)
    assert all(t["go_to"]["SN"] == pytest.approx(ref.sn) for t in fit["test_points"])


def test_optics_mode_keeps_the_mechanics_of_a_chosen_configuration(api, configs):
    """Zone plate mounted after a capillary calibration: keep the capillary's mechanics; test points keep SN and
    SRz <= 0, as the stage is run."""
    r = api.real_sample
    cap = next(x for x in CalibrationStore(configs).records() if x.optic_name == "capillary")
    out = r.start("optics", "zone plate", "gating", 2.687, 4.666, 0.748, configuration=cap.path.name)
    assert out["previous_configuration"] == cap.label
    with pytest.raises(APIError, match="No configuration"):
        r.start("optics", "zone plate", "gating", 0, 0, 0, configuration="nope.json")
    r.start("optics", "zone plate", "gating", 2.687, 4.666, 0.748, configuration=cap.label)
    true = replace(cap.config, st0=cap.config.st0 + 0.8, sz0=cap.config.sz0 + 0.19)
    model, uvw = StageModel(true, GATING_PLATE), (2.687, 4.666, GATING_PLATE.total_thickness + 0.748)
    st, sz, optic = on_beam(model, uvw, 120.0, 0.0, -0.05, 150.0, 150.0, 53.75)
    r.measure_set("1", st, sz, -0.05, optic=optic)
    fit = r.fit()
    values = {c["name"]: c["value"] for c in fit["constants"]}
    assert values["ST0"] == pytest.approx(true.st0, abs=1e-4) and values["Optic at analyzer focus"] == \
        pytest.approx(53.75, abs=1e-4)
    assert fit["reading_errors_mm"]["optic"] == pytest.approx(0.02)
    assert all(t["go_to"]["SN"] == pytest.approx(-0.05) and t["go_to"]["SRz"] <= 0 for t in fit["test_points"])


def test_read_spem_positions(api, tmp_path):
    h5py = pytest.importorskip("h5py")
    path = tmp_path / "map.nxs"
    with h5py.File(path, "w") as f:
        e = f.create_group("img1_0001")
        e.create_group("scan_data").create_dataset("data_01", data=np.zeros((2, 2)))
        a = e.create_group("ANTARES")
        for m, v in (("st", -3.4982), ("sz", 36.538), ("sn", -0.0517), ("srn", 120.0006), ("srz", 0.0005)):
            a.create_dataset(f"i12-m-cx1-ex-sample-mt_{m}/position", data=[v])
        a.create_dataset("PI/PI_X", data=[176.0])
        a.create_dataset("PI/PI_Y", data=[40.0])
        a.create_dataset("i12-m-cx1-op-zp-mt_zs/position", data=[53.7502])
        a.create_dataset("i12-m-c04-op-mono1/energy", data=[95.0])
        t = e.create_group("scan_config/trajectory/actuator_1_1")
        for k, v in (("name", b"i12-m-cx1/ex/pi/x"), ("from", b"130.0"), ("to", b"180.0"), ("delta", b"2.0")):
            t.create_dataset(k, data=v)
    api.real_sample.start("optics", "zone plate", "gating", 0, 0, 0,
                          configuration=next(x for x in CalibrationStore(api.configs).records()
                                             if x.optic_name == "capillary").path.name)
    out = api.real_sample.read_spem(str(path))
    assert out["st"] == pytest.approx(-3.4982) and out["zps"] == pytest.approx(53.7502)
    assert out["optic_for_this_calibration"] == pytest.approx(53.7502) and out["hv"] == pytest.approx(95.0)
    assert out["scanned"] == [{"motor": "pix", "from": 130.0, "to": 180.0, "step": 2.0}]
    with pytest.raises(APIError):
        api.real_sample.read_spem(str(tmp_path / "missing.nxs"))


# -- MCP server ----------------------------------------------------------------------------------------------
def rpc(server, method, params=None, mid=1):
    return server.handle({"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}})


def test_mcp_protocol_in_process(configs):
    server = Server(configs)
    init = rpc(server, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                      "clientInfo": {"name": "test", "version": "0"}})["result"]
    assert init["protocolVersion"] == "2025-06-18" and "tools" in init["capabilities"]
    assert "find samples" in init["instructions"]
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    tools = rpc(server, "tools/list")["result"]["tools"]
    assert len(tools) == len(TOOLS) and all(t["inputSchema"]["type"] == "object" for t in tools)
    res = rpc(server, "tools/call", {"name": "align_start", "arguments": {"plate": "gating", "optic": "capillary"}})
    assert not res["result"]["isError"] and json.loads(res["result"]["content"][0]["text"])["optic"] == "capillary"
    res = rpc(server, "tools/call", {"name": "align_photo_grid", "arguments": {"path": str(PHOTO)}})["result"]
    assert [c["type"] for c in res["content"]] == ["text", "image"] and res["content"][1]["mimeType"] == "image/png"
    bad = rpc(server, "tools/call", {"name": "align_add_sample", "arguments": {"x": 1}})["result"]
    assert bad["isError"] and "Missing" in bad["content"][0]["text"]
    bad = rpc(server, "tools/call", {"name": "align_start", "arguments": {"plate": "x", "optic": "capillary"}})["result"]
    assert bad["isError"] and "Unknown plate" in bad["content"][0]["text"]
    assert rpc(server, "tools/call", {"name": "nope"})["error"]["code"] == -32602
    assert rpc(server, "foo/bar")["error"]["code"] == -32601
    prompt = rpc(server, "prompts/get", {"name": "calibrate"})["result"]
    assert "real sample" in prompt["messages"][0]["content"]["text"]


def test_mcp_server_over_stdio(configs):
    lines = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "align_plates", "arguments": {}}},
    ]
    proc = subprocess.run([sys.executable, str(ROOT / "Agent" / "quickalignment_mcp.py"), "--configs", str(configs)],
                          input="\n".join(json.dumps(x) for x in lines) + "\n", capture_output=True, text=True,
                          timeout=120, encoding="utf-8")
    replies = [json.loads(x) for x in proc.stdout.splitlines()]
    assert [r["id"] for r in replies] == [1, 2]
    assert replies[0]["result"]["protocolVersion"] == "2024-11-05"
    plates = json.loads(replies[1]["result"]["content"][0]["text"])["plates"]
    assert [p["key"] for p in plates] == ["standard", "gating", "custom"]


# -- oblique photos (optional 3D correction) ------------------------------------------------------------------
@pytest.fixture(scope="module")
def qapp():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from quickalignment.ui._qt import QtWidgets
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def oblique_camera(tilt_deg=25.0):
    k = np.array([[1500, 0, 400], [0, 1500, 450], [0, 0, 1.0]])
    a = np.radians(tilt_deg)
    r = np.array([[1, 0, 0], [0, np.cos(a), -np.sin(a)], [0, np.sin(a), np.cos(a)]]) @ np.diag([1, -1, -1])
    return k @ np.c_[r, [0, 0, 60.0]]


def test_3d_correction_of_an_oblique_photo(api):
    from quickalignment.alignment.photo import project, reference_points_3d
    a = api.alignment
    a.start("gating", "capillary")
    cam = oblique_camera()
    pts = a.photo_points_3d()["points"]
    assert len(pts) >= 8 and {p["plate_mm"][2] for p in pts[:8]} == {5.0, 1.1}
    with pytest.raises(APIError, match="different heights"):
        a.register_photo_3d([{"number": i + 1, "px": project(cam, [p["plate_mm"]])[0].tolist()} for i, p in
                             enumerate(pts[:4])] * 2, image_size=[800, 900])
    given = [{"name": p["name"], "px": project(cam, [p["plate_mm"]])[0].tolist()} for p in pts[:8]]
    reg = a.register_photo_3d(given, image_size=[800, 900], photo_id="oblique")
    assert reg["rms_px"] < 0.01 and not reg["warnings"]
    # a 1 mm thick sample, its top corners as seen on the photo
    top = [(1.0, 2.0, 6.0), (3.0, 2.0, 6.0), (3.0, 4.0, 6.0), (1.0, 4.0, 6.0)]
    out = a.add_sample_from_photo(project(cam, top).tolist(), height=1.0, name="thick", photo_id="oblique")["added"]
    assert [out["x"], out["y"], out["length"], out["width"]] == pytest.approx([2.0, 3.0, 2.0, 2.0], abs=1e-3)
    # the four-corner registration alone puts it off by a few tenths of a mm
    corners = [project(cam, [xyz])[0].tolist() for _, xyz in reference_points_3d(a.layout.plate)[:4]]
    a.register_photo(corners, image_size=[800, 900], photo_id="flat")
    flat = a.add_sample_from_photo(project(cam, top).tolist(), height=1.0, name="thick2", photo_id="flat")["added"]
    assert abs(flat["y"] - 3.0) > 0.2


def test_photo_window_3d_mode(qapp):
    from quickalignment.ui.photo_dialog import PhotoImportDialog
    from quickalignment.core.geometry import GATING_PLATE
    dlg = PhotoImportDialog(GATING_PLATE, 0.525)
    assert not dlg.use_3d.isChecked() and len(dlg.reg.ref_points) == 4  # off by default
    assert dlg.load_photo(str(PHOTO))
    dlg.use_3d.setChecked(True)
    assert len(dlg.reg.ref_points) == 8
    dlg.set_corners(CORNERS + [(92, 203), (617, 333), (330, 68), (455, 80)])
    assert dlg.reg.camera is not None and dlg.reg.camera_rms < 15 and dlg.reg.h is not None
    dlg.use_3d.setChecked(False)
    assert dlg.reg.camera is None and len(dlg.reg.ref_points) == 4


def test_manual_annotation_round_trip(api, tmp_path, monkeypatch, qapp):
    from quickalignment.core.fileio import write_json
    from quickalignment.ui import annotate
    from quickalignment.ui.photo_dialog import PhotoImportDialog
    a = started(api)
    a.add_sample(1.0, 1.0, 1.0, 1.0, name="wrong")
    # the window: the user draws one box and presses OK
    def accept(self):
        self.add_box(0.5, 2.5, 4.5, 6.5)
        return 1
    monkeypatch.setattr(PhotoImportDialog, "exec", accept, raising=False)
    monkeypatch.setattr(PhotoImportDialog, "exec_", accept, raising=False)
    layout_file, out = tmp_path / "layout.json", tmp_path / "result.json"
    a.layout.save(layout_file)
    assert annotate.main(["--photo", str(PHOTO), "--layout", str(layout_file), "--out", str(out),
                          "--corners", ";".join(f"{x},{y}" for x, y in CORNERS)]) == 0
    res = a.load_annotation(str(out))
    names = [s["name"] for s in res["samples"]]
    assert res["accepted"] and "wrong" in names and len(names) == 2
    write_json(out, {"accepted": True, "replace": True, "samples": [{"name": "only", "u": 2.5, "v": 4.5,
                                                                     "length": 4, "width": 4, "height": 0.5}]})
    assert [s["name"] for s in a.load_annotation(str(out))["samples"]] == ["only"]


def test_manual_annotation_keeps_user_corners(api, tmp_path, monkeypatch, qapp):
    """Corners the user moves in the window replace the assistant's registration of that photo."""
    from quickalignment.ui import annotate
    from quickalignment.ui.photo_dialog import PhotoImportDialog
    a = started(api)
    pid = next(iter(a.photos))
    moved = [(x + 6.0, y - 4.0) for x, y in CORNERS]

    def accept(self):
        self.set_corners(moved)
        self.add_box(0.5, 2.5, 4.5, 6.5)
        return 1
    monkeypatch.setattr(PhotoImportDialog, "exec", accept, raising=False)
    monkeypatch.setattr(PhotoImportDialog, "exec_", accept, raising=False)
    layout_file, out = tmp_path / "layout.json", tmp_path / "result.json"
    a.layout.save(layout_file)
    assert annotate.main(["--photo", str(PHOTO), "--layout", str(layout_file), "--out", str(out),
                          "--corners", ";".join(f"{x},{y}" for x, y in CORNERS)]) == 0
    a._annotation_photo = pid  # as manual_annotation sets it
    res = a.load_annotation(str(out))
    assert res["registration"]["changed"]
    assert np.allclose(a.photos[pid].corners, moved, atol=1e-6)
    # unchanged corners: nothing re-registered
    assert not a.load_annotation(str(out))["registration"]["changed"]


def test_bring_to_beam_centres_the_piezo(api):
    a = started(api)
    a.add_sample(1.0, 2.0, 2.0, 2.0, 0.5, name="S1")
    out = a.bring_to_beam("S1", {"st": 0, "sz": 40, "sn": 0.5, "srn": 120, "srz": -10, "pix": 138, "piy": 162})
    assert out["stage"]["pix"] == 150 and out["stage"]["piy"] == 150


def test_centre_piezo(api):
    a = started(api)
    a.add_sample(1.0, 2.0, 2.0, 2.0, 0.5, name="S1")
    on = a.bring_to_beam("S1", {"st": 0, "sz": 40, "sn": 0.5, "srn": 120, "srz": -10})["stage"]
    seen = dict(on, pix=140.0, piy=155.0)
    out = a.centre_piezo(seen, optic_position=60.0)
    assert out["stage"]["pix"] == 150 and out["stage"]["piy"] == 150
    assert out["stage"]["sn"] == pytest.approx(seen["sn"]) and out["stage"]["srz"] == pytest.approx(-10)
    hit_seen, hit_new = a.beam_on(seen)["plate_mm"], a.beam_on(out["stage"])["plate_mm"]
    assert hit_new == pytest.approx(hit_seen, abs=1e-3)  # the same plate point on the beam
    with pytest.raises(APIError):
        a.centre_piezo(on)  # already centred
