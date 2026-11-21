"""Corrections of "Fine tunings by ZPS/CPS" (StagePanel.check_found_height): at SRz 0 the optic focus (fixed focal
distance) gives where the Target really is, x / plate offset / H (replaces "Found here"); after an SRz turn, an optic
(ZPS / CPS) error above 0.05 mm is checked against one change of the sample height H, which must explain the ST, SZ and
optic errors together (core.stage.fit_height)."""

import os
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from quickalignment.core.calibration import CalibrationStore
from quickalignment.core.geometry import PLATES, Sample
from quickalignment.core.stage import MotorPositions as M, StageModel, fit_height

ROOT = Path(__file__).resolve().parent.parent
PLATE = PLATES["gating"]


def records():
    return {r.path.name: r for r in CalibrationStore(ROOT / "configs").records()}


def cav():
    """Zone-plate configuration of 2026-11-15 and the tracked point of Cav (on the analyzer focus at SRz 0)."""
    zp = records()["calibration_2026-11-15_151356_zone_plate.json"]
    model = StageModel(zp.config, PLATE)
    m1 = M(st=-3.4982, sz=36.538, sn=-0.05173, srn=120.0006, srz=0.0005, pix=138, piy=142)
    return zp, model, tuple(float(x) for x in model.lab_to_plate(m1, np.zeros(3)))


def found(model, cal, u, v, w, srz=-20.0):
    """Motors and optic position where (u, v, w) really is on the beam and in focus (SN kept at -0.05)."""
    m = model.motors_on_beam(u, v, w, srn=120, srz=srz, sn=-0.05, pix=138, piy=142)
    return m, cal.position_for_focus(model, model.beam_position(m, u, v, w))


def test_height_error_is_found_and_explains_both_errors():
    zp, model, (u, v, w) = cav()
    m, optic = found(model, zp.optics, u, v, w - 0.1)  # the surface is 0.1 mm lower than believed
    fit = fit_height(model, m, zp.optics, optic, u, v, w)
    assert abs(fit.optic_error) > 0.05 and abs(fit.before[0]) > 0.03  # optic and ST both off
    assert fit.dh == pytest.approx(-0.1, abs=1e-6)
    assert fit.explained and max(abs(x) for x in fit.after) < 1e-6


def test_plate_position_error_is_not_a_height_error():
    zp, model, (u, v, w) = cav()
    m, optic = found(model, zp.optics, u + 0.1, v, w)  # the sample is 0.1 mm off in x on the plate
    assert not fit_height(model, m, zp.optics, optic, u, v, w).explained


@pytest.mark.parametrize("srz, st, zps", [(-10, -4.6255, 54.53), (-15, -5.1703, 54.96), (-20, -5.6966, 55.46)])
def test_srz_axis_error_of_2026_11_15_is_not_a_height_error(srz, st, zps):
    """With the capillary axes the ZPS of the SRz series was 0.17-0.29 mm off while ST was right: an SRz-axis error
    across the beam, which no height change explains."""
    recs = records()
    zp = recs["calibration_2026-11-15_151356_zone_plate.json"]
    old = replace(recs["calibration_2026-11-14_173743_capillary.json"].config, st0=-0.8127, sz0=41.2059)
    model = StageModel(old, PLATE)
    m1 = M(st=-3.4982, sz=36.538, sn=-0.05173, srn=120.0006, srz=0.0005, pix=138, piy=142)
    u, v, w = (float(x) for x in model.lab_to_plate(m1, np.zeros(3)))
    cal = replace(zp.optics, enabled=False, optic_position=53.7502)  # ZPS at the analyzer focus, as on 2026-11-15
    fit = fit_height(model, M(st=st, sz=36.54, sn=-0.05, srn=120, srz=srz, pix=138, piy=142), cal, zps, u, v, w)
    assert abs(fit.optic_error) > 0.15 and abs(fit.before[0]) < 0.005
    assert not fit.explained


# -- the button -------------------------------------------------------------------------------------------------------
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
qt = pytest.importorskip("quickalignment.ui._qt")
QtWidgets = qt.QtWidgets


@pytest.fixture
def stage(monkeypatch, tmp_path):
    from quickalignment.core.session import Session
    from quickalignment.core.geometry import SampleLayout
    from quickalignment.ui.main_window import MainWindow

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    win = MainWindow(Session(SampleLayout(plate=PLATE, samples=[])), store=CalibrationStore(tmp_path / "configs"),
                     optic="zone plate + OSA")
    win.editor.add_sample(Sample("Cav", u=2.0, v=4.0, length=2.0, width=2.0, height=0.75))
    win.stage.refresh_targets()
    win.stage.target_combo.setCurrentText("Cav")
    app.processEvents()
    yield win.stage, win.editor.layout_model.samples[0]
    win.close()


def set_found(st, true_height, srz):
    """Enter the motors and optic where Cav (centre, height `true_height`) is on the beam and in focus."""
    model, cal = st.model(), st.calibration()
    w = PLATE.total_thickness + true_height
    m = model.motors_on_beam(2.0, 4.0, w, srn=120, srz=srz, sn=0.3, pix=150, piy=150)
    st.motors.set_value(M(st=round(m.st, 4), sz=round(m.sz, 4), sn=m.sn, srn=120, srz=srz, pix=150, piy=150))
    st.optic_pos.setValue(cal.position_for_focus(model, model.beam_position(m, 2.0, 4.0, w)))


def answer(monkeypatch, reply):
    asked = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "question", lambda *a, **k: asked.append(a[2]) or reply)
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", lambda *a, **k: pytest.fail(a[2]))
    return asked


def test_move_found_corrects_the_height_after_an_srz_turn(stage, monkeypatch):
    st, sample = stage
    set_found(st, 0.65, -20.0)  # 0.1 mm lower than drawn
    asked = answer(monkeypatch, QtWidgets.QMessageBox.Yes)
    assert st.bring_found_to_focal_plane() is not None
    assert len(asked) == 1 and "ΔH = -0.100 mm" in asked[0]
    assert sample.height == pytest.approx(0.65, abs=2e-4)
    assert "Height of Cav corrected" in st.goto_label.text()


def test_move_found_keeps_the_height_when_refused(stage, monkeypatch):
    st, sample = stage
    set_found(st, 0.65, -20.0)
    answer(monkeypatch, QtWidgets.QMessageBox.No)
    st.bring_found_to_focal_plane()
    assert sample.height == 0.75 and "H not changed" in st.goto_label.text()


def test_no_height_check_for_a_small_optic_error_after_an_srz_turn(stage, monkeypatch):
    st, sample = stage
    asked = answer(monkeypatch, QtWidgets.QMessageBox.Yes)
    set_found(st, 0.74, -20.0)  # 0.01 mm: the optic is within 0.05 mm of the prediction
    st.bring_found_to_focal_plane()
    assert not asked and sample.height == 0.75
    assert "H kept" in st.goto_label.text()


def test_fine_tuning_at_srz_0_corrects_the_height_from_the_focus(stage, monkeypatch):
    st, sample = stage
    set_found(st, 0.65, 0.0)  # 0.1 mm lower than drawn, found on the beam (centre) and in focus
    asked = answer(monkeypatch, QtWidgets.QMessageBox.Yes)
    new, optic = st.bring_found_to_focal_plane()
    assert len(asked) == 1 and "ΔH = -0.100" in asked[0] and "Δx = +0.000" in asked[0]
    assert sample.height == pytest.approx(0.65, abs=2e-4)
    assert (sample.u, sample.v) == pytest.approx((2.0, 4.0), abs=2e-4)
    assert st._layout_getter().plate_offset_v == pytest.approx(0.0, abs=2e-4)
    assert "Corrected by the ZPS focus" in st.goto_label.text()
    # then back on the analyzer focus: the optic at the configuration's position for it, the sample surface there
    model, cal = st.model(), st.calibration()
    assert optic == pytest.approx(cal.position_for_focus(model, 0.0))
    assert model.beam_position(st.motors.value(), 2.0, 4.0, PLATE.total_thickness + 0.65) == pytest.approx(0, abs=2e-4)
    # found again where it now is expected: nothing more to correct
    asked.clear()
    st.bring_found_to_focal_plane()
    assert not asked and "nothing corrected" in st.goto_label.text()


def test_fine_tuning_at_srz_0_moves_sample_and_plate(stage, monkeypatch):
    """Found elsewhere on the plate (what "Found here" did, now with the focus where the optic says it is)."""
    st, sample = stage
    model, cal = st.model(), st.calibration()
    w = PLATE.total_thickness + 0.80
    m = model.motors_on_beam(2.1, 3.95, w, srn=120, srz=0.0, sn=0.3, pix=150, piy=150)
    st.motors.set_value(M(st=m.st, sz=m.sz, sn=m.sn, srn=120, srz=0.0, pix=150, piy=150))
    st.optic_pos.setValue(cal.position_for_focus(model, model.beam_position(m, 2.1, 3.95, w)))
    answer(monkeypatch, QtWidgets.QMessageBox.Yes)
    st.bring_found_to_focal_plane()
    assert (sample.u, sample.height) == pytest.approx((2.1, 0.80), abs=2e-4)
    assert sample.v == 4.0 and st._layout_getter().plate_offset_v == pytest.approx(-0.05, abs=2e-4)


def test_fine_tuning_at_srz_0_refused_changes_nothing(stage, monkeypatch):
    st, sample = stage
    set_found(st, 0.65, 0.0)
    answer(monkeypatch, QtWidgets.QMessageBox.No)
    st.bring_found_to_focal_plane()
    assert sample.height == 0.75 and "nothing corrected" in st.goto_label.text()


# -- H exact, the H field and Undo fine tuning ------------------------------------------------------------------------
def test_height_field_follows_the_target_and_sets_h(stage):
    st, sample = stage
    assert st.height_box.isEnabled() and st.height_box.value() == pytest.approx(0.75)
    assert not st.height_exact.isChecked()  # off by default
    sample.sn_checked = 1.234
    st.height_box.setValue(0.525)
    assert sample.height == pytest.approx(0.525) and sample.sn_checked is None  # typed: no longer the SN set by eye
    st.target_combo.setCurrentText("plate centre")
    assert not st.height_box.isEnabled()


def test_exact_height_corrects_only_the_photo_error(stage, monkeypatch):
    """H exact (0.75 mm): found 0.1 mm off in x and 0.05 mm low in y on the plate, the optic read 0.04 mm off along the
    beam: x and the plate offset are corrected, H is kept, and the surface at H ends on the analyzer focus."""
    st, sample = stage
    st.height_exact.setChecked(True)
    model, cal = st.model(), st.calibration()
    w = PLATE.total_thickness + 0.75
    m = model.motors_on_beam(2.1, 3.95, w, srn=120, srz=0.0, sn=0.3, pix=150, piy=150)
    st.motors.set_value(M(st=m.st, sz=m.sz, sn=m.sn, srn=120, srz=0.0, pix=150, piy=150))
    st.optic_pos.setValue(cal.position_for_focus(model, model.beam_position(m, 2.1, 3.95, w) + 0.04))
    asked = answer(monkeypatch, QtWidgets.QMessageBox.Yes)
    st.bring_found_to_focal_plane()
    assert len(asked) == 1 and "marked exact" in asked[0] and "Δx = +0.100" in asked[0]
    assert sample.height == 0.75 and sample.u == pytest.approx(2.1, abs=2e-4)
    assert st._layout_getter().plate_offset_v == pytest.approx(-0.05, abs=2e-4)
    assert "H exact" in st.goto_label.text()
    model = st.model()
    assert model.beam_position(st.motors.value(), 2.1, 4.0, w) == pytest.approx(0, abs=2e-4)


def test_exact_height_no_height_check_after_an_srz_turn(stage, monkeypatch):
    st, sample = stage
    st.height_exact.setChecked(True)
    set_found(st, 0.65, -20.0)  # the optic says 0.1 mm lower: not taken as a height error
    asked = answer(monkeypatch, QtWidgets.QMessageBox.Yes)
    st.bring_found_to_focal_plane()
    assert not asked and sample.height == 0.75 and "marked exact" in st.goto_label.text()


def test_undo_fine_tuning_back_to_the_sn_set_by_eye(stage, monkeypatch):
    st, sample = stage
    assert not st.undo_fine_btn.isEnabled() and not st.undo_fine_tuning()
    sample.sn_checked = 0.4  # SN set by eye
    layout = st._layout_getter()
    answer(monkeypatch, QtWidgets.QMessageBox.Yes)
    set_found(st, 0.65, 0.0)
    m0, optic0 = st.motors.value(), st.optic_pos.value()
    st.bring_found_to_focal_plane()  # H corrected, SN set by eye follows
    assert sample.height == pytest.approx(0.65, abs=2e-4) and sample.sn_checked != 0.4
    model, cal = st.model(), st.calibration()  # a second fine tuning, found 0.1 mm off in x
    w = PLATE.total_thickness + 0.65
    m = model.motors_on_beam(2.1, 4.0, w, srn=120, srz=0.0, sn=0.3, pix=150, piy=150)
    st.motors.set_value(m)
    st.optic_pos.setValue(cal.position_for_focus(model, model.beam_position(m, 2.1, 4.0, w)))
    m1, optic1 = st.motors.value(), st.optic_pos.value()
    st.bring_found_to_focal_plane()
    assert sample.u == pytest.approx(2.1, abs=2e-4) and st.undo_fine_btn.isEnabled()
    assert st.undo_fine_tuning()  # the second one
    assert sample.u == pytest.approx(2.0, abs=2e-4) and sample.height == pytest.approx(0.65, abs=2e-4)
    assert st.motors.value() == m1 and st.optic_pos.value() == pytest.approx(optic1)
    assert st.undo_fine_tuning()  # the first one: back to the SN set by eye
    assert (sample.u, sample.v, sample.height, sample.sn_checked) == (2.0, 4.0, 0.75, 0.4)
    assert layout.plate_offset_v == 0.0 and st.height_box.value() == pytest.approx(0.75)
    assert st.motors.value() == m0 and st.optic_pos.value() == pytest.approx(optic0)
    assert not st.undo_fine_btn.isEnabled() and "before the first fine tuning" in st.goto_label.text()
