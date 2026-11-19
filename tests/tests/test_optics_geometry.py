"""Separate ZP / capillary geometry model (quickalignment.optics)."""

from pathlib import Path

import numpy as np
import pytest

from quickalignment.core.stage import T_HAT, Z_HAT
from quickalignment.optics import OpticsGeometry, OpticsGeometryConfig, OpticsMotors, default_config
from quickalignment.optics.geometry import capillary_focus_from_configs

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def g():
    return OpticsGeometry(default_config(ROOT / "configs"))


def zp_mode(g):
    zp, cap = g.config.zone_plate, g.config.capillary
    return OpticsMotors(zps=zp.zps, zpx=zp.zpx, zpz=zp.zpz, cps=0.0, cpx=0.0, cap_rz=cap.cap_rz, cap_rx=cap.cap_rx)


def cap_mode(g):
    cap = g.config.capillary
    return OpticsMotors(zps=-20.0, zpx=0.4681, zpz=cap.zpz, cps=cap.cps, cpx=cap.cpx,
                        cap_rz=cap.cap_rz, cap_rx=cap.cap_rx)


def test_capillary_spot_from_the_two_configs(g):
    f = np.array(g.config.capillary.focus)
    assert np.allclose(f, [-0.80004 / np.sqrt(2), 0.80004 / np.sqrt(2), -0.19001], atol=1e-4)
    # the capillary spot gives back the capillary config's ST0 / SZ0 from the zone-plate ones
    o = g.stage_offsets(cap_mode(g))
    assert o["optic"] == "capillary"
    assert -0.8127 + o["dst0"] == pytest.approx(-1.6127389262697402, abs=1e-6)
    assert 41.2059 + o["dsz0"] == pytest.approx(41.015885840956955, abs=1e-6)
    assert o["focus_along_beam"] == pytest.approx(0.0, abs=1e-9)


def test_configs_offset_formula():
    d = capillary_focus_from_configs({"st0": 0, "sz0": 0, "sn_f": 0}, {"st0": 1, "sz0": 2, "sn_f": 0})
    assert np.allclose(d, T_HAT + 2 * Z_HAT)


def test_active_optic(g):
    assert g.active_optic(zp_mode(g)) == "zone plate"
    assert g.active_optic(cap_mode(g)) == "capillary"
    parked = zp_mode(g)
    parked.zps = -20.0
    assert g.active_optic(parked) == "none"


def test_zone_plate_motor_directions(g):
    m = zp_mode(g)
    assert np.allclose(g.beam(m).focus, 0.0)
    m.zps += 1.0
    assert np.allclose(g.zone_plate_focus(m), [0, 1, 0])  # + downstream
    m = zp_mode(g)
    m.zpx += 1.0
    assert np.allclose(g.zone_plate_focus(m), [-1, 0, 0])  # + towards the analyzer (-x)
    m = zp_mode(g)
    m.zpz += 1.0
    assert np.allclose(g.zone_plate_focus(m), [0, 0, 1])  # + up


def test_zone_plate_energy_and_lens(g):
    zp = g.config.zone_plate
    assert zp.focal_length() == pytest.approx(0.256 * 95)  # 24.32 mm at 95 eV
    m = zp_mode(g)
    assert np.allclose(g.zone_plate_lens(m), [0, -24.32, 0])
    # 1 eV more: the focus moves 0.256 mm downstream; ZPS -0.256 brings it back
    assert np.allclose(g.zone_plate_focus(m, energy=96.0), [0, 0.256, 0])
    back = g.zone_plate_motors_for([0, 0, 0], m, energy=96.0)
    assert back.zps == pytest.approx(zp.zps - 0.256)
    assert np.allclose(g.zone_plate_focus(back, energy=96.0), 0.0)


def test_osa_position(g):
    m = zp_mode(g)
    assert np.allclose(g.osa_position(m), [0, -3.5, 0])  # working position S 80 / Z 26.63 (readings missing)
    m.osa_s, m.osa_z = 81.0, 27.63
    assert np.allclose(g.osa_position(m), [0, -2.5, 1.0])  # + S downstream, + Z up


def test_capillary_motor_directions(g):
    f0 = np.array(g.config.capillary.focus)
    for name, step in (("cps", [0, 1, 0]), ("cpx", [-1, 0, 0]), ("zpz", [0, 0, 1])):
        m = cap_mode(g)
        setattr(m, name, getattr(m, name) + 1.0)
        assert np.allclose(g.capillary_beam(m).focus - f0, step), name


def test_capillary_rotations(g):
    m = cap_mode(g)
    m.cap_rz -= 1.0  # negative: the tip turns towards the analyzer (-x)  [provisional sign]
    assert g.capillary_beam(m).direction[0] < 0
    m = cap_mode(g)
    m.cap_rx += 1.0  # positive: the tip turns up
    assert g.capillary_beam(m).direction[2] > 0
    # with the pivot behind the focus, a turn moves the focus sideways the same way as the beam
    g.config.capillary.pivot_to_focus = 50.0
    m = cap_mode(g)
    m.cap_rz -= 1.0
    f = g.capillary_beam(m).focus - np.array(g.config.capillary.focus)
    assert f[0] == pytest.approx(-50 * np.sin(np.radians(1.0)), abs=1e-9)


def test_motors_for_focus_round_trip(g):
    target = np.array([0.1, -0.2, 0.3])
    m = g.capillary_motors_for(target)
    assert np.allclose(g.capillary_beam(m).focus, target)
    m = g.zone_plate_motors_for(target, zp_mode(g))
    assert np.allclose(g.zone_plate_focus(m), target)


def test_config_save_load(g, tmp_path):
    p = tmp_path / "optics.json"
    g.config.save(p)
    assert '"zps": 53.7502' in p.read_text(encoding="utf-8")  # "." decimals, whatever the system locale
    back = OpticsGeometryConfig.load(p)
    assert back.to_dict() == g.config.to_dict()


@pytest.mark.parametrize("name,optic", [("Cav_2026-11-14_19-48-34.nxs", "capillary"),
                                        ("Cav_2026-11-15_11-13-55.nxs", "zone plate")])
def test_cav_files(g, name, optic):
    pytest.importorskip("h5py")
    path = ROOT / "Cav" / name
    if not path.exists():
        pytest.skip("Cav data not present")
    from quickalignment.optics.nxs import read_motors

    m, found = read_motors(path)
    assert g.active_optic(m) == optic
    assert {"st", "sz", "sn", "srn", "srz"} <= set(found)
