"""The focusing optic at other photon energies (core/photon_energy.py): model, measured points, the session and
the Stage & Optics tab."""
import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from quickalignment.agent import AlignmentSession
from quickalignment.core.calibration import CalibrationRecord, CalibrationStore
from quickalignment.core.photon_energy import (
    REFERENCE_HV, OpticsEnergyTable, optics_at_energy, zone_plate_focal_length,
)
from quickalignment.core.stage import OpticsCalibration, StageModel

CONFIGS = Path(__file__).resolve().parent.parent / "configs"


def table(f=None, zp_points=(), cap_points=()):
    t = OpticsEnergyTable()
    t.optics["zone plate"].focal_length_mm = f
    for hv, shift in zp_points:
        t.add_point("zone plate + OSA", hv, shift)
    for hv, shift in cap_points:
        t.add_point("capillary", hv, shift)
    return t


def test_no_shift_at_the_reference_energy():
    t = table(f=2.0)
    assert t.shift("zone plate + OSA", REFERENCE_HV).shift == 0.0
    assert t.shift("capillary", 300.0).shift == 0.0           # achromatic


def test_zone_plate_model_moves_the_optic_away_from_the_sample():
    t = table(f=2.0)
    s = t.shift("zone plate + OSA", 2 * REFERENCE_HV, optic_sign=1)
    assert s.shift == pytest.approx(-2.0)                      # f doubles: 2 mm more working distance, upstream
    assert t.shift("zone plate + OSA", 2 * REFERENCE_HV, optic_sign=-1).shift == pytest.approx(2.0)
    assert "model" in s.source


def test_zone_plate_without_focal_length_is_reported_unknown():
    s = table().shift("zone plate + OSA", 120.0)
    assert s.shift == 0.0 and "NOT KNOWN" in s.source


def test_measured_points_are_interpolated_and_extrapolated_with_the_model_slope():
    t = table(f=1.9, zp_points=[(135.0, -0.75)])
    mid = t.shift("zone plate + OSA", 115.0)
    assert mid.shift == pytest.approx(-0.375) and "interpolated" in mid.source
    far = t.shift("zone plate + OSA", 145.0)
    assert far.shift == pytest.approx(-0.75 - 1.9 / REFERENCE_HV * 10.0)


def test_capillary_measured_points_are_used():
    t = table(cap_points=[(150.0, 0.02)])
    assert t.shift("capillary", 150.0).shift == pytest.approx(0.02)
    assert t.shift("capillary", 200.0).shift == pytest.approx(0.02)      # flat beyond the last point


def test_focal_length_formula():
    # D = 200 µm, dr = 50 nm at 95 eV: lambda = 13.05 nm, f = 0.766 mm
    assert zone_plate_focal_length(200.0, 50.0, 95.0) == pytest.approx(200e-3 * 50.0 / (1239.84193 / 95.0))


def test_optics_at_energy_shifts_every_prediction_consistently():
    t = table(f=2.0)
    cal = OpticsCalibration(optic_position=54.3, optic_type="zone plate + OSA", last_position=54.4)
    moved, shift = optics_at_energy(cal, t, 142.5)
    model = StageModel()
    assert shift.shift == pytest.approx(-1.0)
    assert moved.position_for_focus(model, 0.1) == pytest.approx(cal.position_for_focus(model, 0.1) - 1.0)
    assert moved.focus_for_position(model, moved.position_for_focus(model, 0.1)) == pytest.approx(0.1)
    assert moved.current_position == pytest.approx(53.4) and moved.photon_energy == 142.5
    assert optics_at_energy(cal, t, None)[0] is cal


def test_old_configuration_files_are_at_95_ev_and_new_ones_keep_the_energy():
    rec = CalibrationStore(CONFIGS).latest("capillary")
    assert rec.optics.photon_energy == REFERENCE_HV
    again = CalibrationRecord.from_dict(replace(rec, optics=replace(rec.optics, photon_energy=120.0)).to_dict())
    assert again.optics.photon_energy == 120.0


@pytest.fixture
def zp_session(tmp_path):
    folder = tmp_path / "configs"
    shutil.copytree(CONFIGS, folder)
    data = json.loads((folder / "optics_vs_hv.json").read_text(encoding="utf-8"))
    data["optics"]["zone plate"]["focal_length_mm"] = 1.5
    (folder / "optics_vs_hv.json").write_text(json.dumps(data), encoding="utf-8")
    s = AlignmentSession(folder)
    s.start("standard", "zone plate")
    s.add_sample(1.0, 2.0, 2.0, 2.0, 0.5, "A")
    return s, folder


def test_session_optic_positions_follow_the_photon_energy(zp_session):
    s, _ = zp_session
    at95 = s.bring_to_beam("A")["optic_position_for_focus"]
    out = s.set_photon_energy(190.0)
    assert out["optic_shift_mm"] == pytest.approx(-1.5)
    assert s.bring_to_beam("A")["optic_position_for_focus"] == pytest.approx(at95 - 1.5, abs=1e-4)
    assert s.status()["photon_energy"]["photon_energy_eV"] == 190.0
    s.set_photon_energy(None)
    assert s.bring_to_beam("A")["optic_position_for_focus"] == pytest.approx(at95, abs=1e-4)


def test_unknown_shift_is_said(tmp_path):
    folder = tmp_path / "configs"
    shutil.copytree(CONFIGS, folder)
    s = AlignmentSession(folder)
    s.start("standard", "zone plate")
    assert "warning" in s.set_photon_energy(130.0)


def test_a_measured_point_is_saved_only_when_asked(zp_session):
    s, folder = zp_session
    pos = s.bring_to_beam("A")
    predicted = pos["optic_position_for_focus"]
    out = s.add_optic_energy_point("A", 120.0, pos["stage"], predicted - 0.33)
    assert out["shift_mm"] == pytest.approx(-0.33, abs=1e-4) and "saved" not in out
    assert OpticsEnergyTable.load(folder).optics["zone plate"].points == []
    out = s.add_optic_energy_point("A", 120.0, pos["stage"], predicted - 0.33, comment="test", save=True)
    t = OpticsEnergyTable.load(folder)
    assert [p.hv for p in t.optics["zone plate"].points] == [120.0]
    s.set_photon_energy(120.0)
    assert s.bring_to_beam("A")["optic_position_for_focus"] == pytest.approx(predicted - 0.33, abs=1e-4)


def test_the_configuration_folder_is_not_mistaken_for_a_calibration():
    assert all("optics_vs_hv" not in str(r.path) for r in CalibrationStore(CONFIGS).records())


qt = pytest.importorskip("quickalignment.ui._qt")


def test_stage_tab_photon_energy_field(tmp_path):
    from quickalignment.core.geometry import STANDARD_PLATE, SampleLayout
    from quickalignment.core.session import Session
    from quickalignment.ui.main_window import MainWindow
    folder = tmp_path / "configs"
    shutil.copytree(CONFIGS, folder)
    data = json.loads((folder / "optics_vs_hv.json").read_text(encoding="utf-8"))
    data["optics"]["zone plate"]["focal_length_mm"] = 1.5
    (folder / "optics_vs_hv.json").write_text(json.dumps(data), encoding="utf-8")
    app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
    win = MainWindow(Session(SampleLayout(plate=STANDARD_PLATE)), store=CalibrationStore(folder),
                     optic="zone plate + OSA")
    try:
        st = win.stage
        before = st.calibration().optic_position
        st.hv_box.setValue(190.0)
        app.processEvents()
        assert st.calibration().optic_position == pytest.approx(before - 1.5)
        assert "190 eV" in st.optic_ref_label.text()
    finally:
        win.close()
