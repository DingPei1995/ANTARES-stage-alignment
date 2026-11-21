"""Stage & optics panel: motor inputs, results and the schematic.

The schematic and the results are only recomputed when "Update" is pressed.
Calibration constants come from the current CalibrationRecord (see the
calibration window).
"""

from __future__ import annotations

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from dataclasses import replace

from ._qt import QtCore, QtWidgets, Signal
from ..core.calibration import CalibrationRecord
from ..core.motors import (  # noqa: F401  (re-exported for the other windows)
    CONFIG_SPECS, DEFAULT_LIMITS, FOCUS_WARNING, LARGE_FOUND_OFFSET, LIMIT_MOTORS, MOTOR_SPECS, PLATE_OFFSET_WARNING,
    TOLERANCE, TRAVEL, current_limits, out_of_range, set_motor_limits,
)
from ..core.collision import ACCEPTANCE_HALF_ANGLE, collisions, in_acceptance, motor_limits
from ..core.schematic import draw_schematic
from ..core.stage import (
    HEIGHT_CHECK_OPTIC, HEIGHT_CHECK_SRZ, HEIGHT_EXPLAIN_TOL, OPTIC_TYPES, MotorPositions, OpticsCalibration,
    Y_HAT, StageConfig, StageModel, apply_found_offset, beam_at_height, checked_sn, fit_height, focus_correction,
    found_offset, slide_to_sn, sn_from_height, sn_to_focus,
)
from ..realsample.fit import measurement_sigmas

Qt = QtCore.Qt
FINE_TUNE_BUTTON = "Fine tunings by ZPS/CPS"
EYE_SN_WARN = 0.1  # mm: SN set by eye this far from the SN of the exact H: check SN_f or the mounting
HEIGHT_FOCUS_MIN = 0.002  # mm: a height change from the focus below this is not offered (H confirmed)
FOUND_POSITION_MIN = 0.001  # mm: x / y changes from the focus below this (with H below HEIGHT_FOCUS_MIN) are not offered

def unsigned_zero(x: float, decimals: int) -> float:
    """x rounded to `decimals`, a value that rounds to zero without its sign (shown 0.000, not -0.000)."""
    return round(x, decimals) + 0.0


def set_range(box: QtWidgets.QDoubleSpinBox, name: str) -> None:
    box.setRange(*MOTOR_SPECS[name][1:3])


def spin(value: float, lo: float = -1000, hi: float = 1000, decimals: int = 3, step: float = 0.1, suffix: str = " mm"):
    box = QtWidgets.QDoubleSpinBox()
    box.setRange(lo, hi)
    box.setDecimals(decimals)
    box.setSingleStep(step)
    box.setSuffix(suffix)
    box.setValue(value)
    box.setKeyboardTracking(False)
    return box


def equal_row(*widgets) -> QtWidgets.QHBoxLayout:
    """A row of widgets (buttons, panels) that all get the same width."""
    row = QtWidgets.QHBoxLayout()
    width = max(w.sizeHint().width() for w in widgets)
    for w in widgets:
        w.setMinimumWidth(width)
        row.addWidget(w, 1)
    return row


def form_labels(form: QtWidgets.QFormLayout) -> list:
    out = []
    for i in range(form.rowCount()):
        item = form.itemAt(i, QtWidgets.QFormLayout.LabelRole)
        if item is not None and item.widget() is not None:
            out.append(item.widget())
    return out


def align_labels(*parts) -> None:
    """Give the label column of several forms (QFormLayout or MotorForm) the same
    width, so that their input fields start at the same x."""
    labels = [w for p in parts for w in (p.labels if isinstance(p, MotorForm) else form_labels(p))]
    width = max(w.sizeHint().width() for w in labels)
    for w in labels:
        w.setMinimumWidth(width)


class MotorForm(QtWidgets.QWidget):
    def __init__(self, motors: MotorPositions | None = None, parent=None):
        super().__init__(parent)
        motors = motors or MotorPositions()
        self.boxes = {}
        self.labels = []  # first column, see align_labels
        grid = QtWidgets.QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        for i, (name, (label, lo, hi, dec, step, suffix)) in enumerate(MOTOR_SPECS.items()):
            self.boxes[name] = spin(getattr(motors, name), lo, hi, dec, step, suffix)
            text = QtWidgets.QLabel(label)
            if i % 2 == 0:
                self.labels.append(text)
            grid.addWidget(text, i // 2, 2 * (i % 2))
            grid.addWidget(self.boxes[name], i // 2, 2 * (i % 2) + 1)
        # both columns of fields equally wide, labels only as wide as needed
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

    def apply_limits(self) -> None:
        """Input ranges from MOTOR_SPECS (after set_motor_limits)."""
        for name, box in self.boxes.items():
            set_range(box, name)

    def value(self) -> MotorPositions:
        return MotorPositions(**{k: b.value() for k, b in self.boxes.items()})

    def set_value(self, m: MotorPositions) -> None:
        for k, b in self.boxes.items():
            b.setValue(getattr(m, k))


class StagePanel(QtWidgets.QWidget):
    layoutCorrected = Signal(str)  # a sample was moved to where its target was found
    heightConfirmed = Signal()  # the H of a sample was confirmed as exact (SN hint of the Samples tab)

    def __init__(self, layout_getter, parent=None):
        super().__init__(parent)
        self._layout_getter = layout_getter
        self.record = CalibrationRecord()

        self.motors = MotorForm()
        self.target_combo = QtWidgets.QComboBox()
        goto_btn = QtWidgets.QPushButton("Bring target onto the beam")
        goto_btn.setToolTip("Compute ST / SZ that put the target on the beam with SN kept as entered (how the stage\n"
                            "is run), keeping SRn, SRz, with the piezo centred (PIX = PIY = 150 µm); tells how far the\n"
                            "target then is from the analyzer focus. The optic refocuses on it.")
        goto_btn.clicked.connect(self.bring_target_on_beam)
        centre_btn = QtWidgets.QPushButton("Centre the piezo")
        centre_btn.setToolTip(
            "The sample was seen in a PIX / PIY scan away from the piezo centre: enter that PIX, PIY (and the optic\n"
            "position in focus there) in the fields. Computes the ST / SZ that show it with the piezo centred\n"
            "(PIX = PIY = 150 µm) at the same SRn, SRz, SN kept, and the optic refocused (as the last step of\n"
            "Rotate sample).")
        centre_btn.clicked.connect(self.centre_piezo)
        self.correct_sn_btn = QtWidgets.QPushButton("Correct SN")
        self.correct_sn_btn.setToolTip("Only if the target is too far from the analyzer focus: compute SN, ST, SZ that put it\n"
                                       "on the analyzer focus (absolute: relies on the configuration's SN_f).")
        self.correct_sn_btn.clicked.connect(self.bring_target_to_focus)
        self.goto_label = QtWidgets.QLabel()
        self.goto_label.setWordWrap(True)
        self.goto_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.goto_label.hide()
        for box in self.motors.boxes.values():  # the readout only holds for the positions it was computed for
            box.valueChanged.connect(self.goto_label.hide)
        motor_box = QtWidgets.QGroupBox("Sample stage (current / planned positions)")
        mb = QtWidgets.QVBoxLayout(motor_box)
        mb.addWidget(self.motors)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Target"))
        self.target_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToContents)
        self.target_combo.setMinimumContentsLength(12)  # names are short (S1, Sample1/Device2)
        row.addWidget(self.target_combo)
        row.addStretch(1)
        mb.addLayout(row)
        self.target_combo.currentTextChanged.connect(lambda _: self._show_target_height())
        mb.addLayout(equal_row(goto_btn, centre_btn))
        mb.addWidget(self.goto_label)
        # Correct SN: a step of its own, only when the target is too far from the analyzer focus
        sn_box = QtWidgets.QGroupBox("Analyzer focus (SN)")
        sb_ = QtWidgets.QVBoxLayout(sn_box)
        sn_note = QtWidgets.QLabel("Only if the target is too far from the analyzer focus with SN kept (the line above "
                                   "says so): SN, ST, SZ that put it on the analyzer focus.")
        sn_note.setWordWrap(True)
        sn_note.setStyleSheet("color: #555;")
        sb_.addWidget(sn_note)
        sb_.addLayout(equal_row(self.correct_sn_btn))

        # focusing optic: absolute position along the beam
        self.optic_type = QtWidgets.QComboBox()
        self.optic_type.addItems(OPTIC_TYPES)
        self.optic_type.currentTextChanged.connect(self._on_optic_type)
        self.optic_pos = spin(0.0, -10000, 10000, 4, 0.01)
        self.optic_pos.setToolTip("Absolute optic motor position along the beam (from the configuration, or typed in).")
        focus_btn = QtWidgets.QPushButton(FINE_TUNE_BUTTON)
        focus_btn.setToolTip(
            "The Target was found on the beam and in focus at the entered stage positions with the optic\n"
            "(ZPS / CPS) at the entered position. The optic's focal distance is fixed, so that position tells\n"
            "where along the beam the sample surface is (configuration's optics reference). Then:\n"
            "1. at SRz 0 the focus gives where the Target really is (asked first): Δx moves its sample, Δy is the\n"
            "   plate sitting at another height in the holder (all samples' SZ), ΔH corrects its height.\n"
            "   After an SRz turn only H, if a change of H explains the optic and the ST / SZ errors together\n"
            "   (optic > 0.05 mm off).\n"
            "2. SN (ST compensating, the sample stays on the beam; SZ stays) brings the surface onto the\n"
            "   analyzer focal plane, and the optic goes back to the configuration's position for the analyzer\n"
            "   focus.")
        focus_btn.clicked.connect(self.bring_found_to_focal_plane)
        self.undo_fine_btn = QtWidgets.QPushButton("Undo fine tuning")
        self.undo_fine_btn.setToolTip(
            "Take back the last “Fine tunings by ZPS/CPS”: the sample position and height, the plate offset, the\n"
            "SN set by eye and the stage / optic fields return to what they were before it. Pressed again, it takes\n"
            "back the one before, down to the state before the first fine tuning (e.g. the SN set by eye).")
        self.undo_fine_btn.clicked.connect(self.undo_fine_tuning)
        self.undo_fine_btn.setEnabled(False)
        self._fine_history: list[dict] = []  # states before each fine tuning (undo_fine_tuning)
        # height of the Target's sample, and whether it is exact (then the fine tuning corrects x / y only)
        self.height_box = spin(0.0, 0.0, 100.0, 3, 0.005)
        self.height_box.setToolTip("Height H of the Target's sample (its top surface above the plate surface), the\n"
                                   "same as H in the Samples tab. Type the known height here (e.g. a wafer of known\n"
                                   "thickness) before the fine tuning.")
        self.height_box.valueChanged.connect(self._on_height_typed)
        self.height_source = QtWidgets.QLabel()  # where H comes from: SN by eye, default, exact ...
        self.height_source.setWordWrap(True)
        self.height_exact = QtWidgets.QCheckBox("H is exact: do not correct it")
        self.height_exact.setToolTip(
            "Tick when the sample height is known precisely (e.g. a Si wafer of known thickness, mounted to within\n"
            "0.02 mm). The fine tuning then keeps H: the Target is where the beam meets its surface at that height,\n"
            "only its position on the plate (photo error, plate offset) is corrected, and SN brings that surface onto\n"
            "the analyzer focus. The optic focus reading is only reported (it would otherwise correct H).\n"
            "Off (default): the optic focus corrects H as well.\n"
            "Trust: a known exact H > the ZPS / CPS focus > the SN set by eye. An H from the SN set by eye (or left at\n"
            "the default) is asked for once before it is taken as exact.")
        self.height_exact.setChecked(False)
        self.height_exact.toggled.connect(self._on_exact_toggled)
        self._exact: dict[int, float] = {}  # id(sample) -> H confirmed as exact (known thickness)
        self._eye_sn: dict[int, float] = {}  # id(sample) -> SN set by eye, replaced by an exact H (kept as a check)
        self.default_height_getter = None  # height of new samples (Samples tab), to tell an H never entered
        fine_note = QtWidgets.QLabel(
            "Works because the focal distance of the optic is fixed: the ZPS / CPS of the found focus corrects "
            "the sample position and height and brings the sample back onto the analyzer focus.")
        fine_note.setWordWrap(True)
        fine_note.setStyleSheet("color: #555;")
        self.optic_ref_label = QtWidgets.QLabel()
        self.optic_ref_label.setWordWrap(True)
        self.optic_ref_label.setStyleSheet("color: #555;")
        optic_box = QtWidgets.QGroupBox("Focusing optic (along the beam)")
        of = QtWidgets.QFormLayout(optic_box)
        of.addRow("Type", self.optic_type)
        of.addRow("Optic position", self.optic_pos)
        of.addRow("Target's sample H", self.height_box)
        of.addRow(self.height_source)
        of.addRow(self.height_exact)
        of.addRow(equal_row(focus_btn, self.undo_fine_btn))
        of.addRow(fine_note)
        of.addRow(self.optic_ref_label)
        # the working distances of the optic solids (anti-collision) come from the configuration only (beamline staff,
        # RealSampleCalibration): no fields here
        align_labels(self.motors, of)

        update_btn = QtWidgets.QPushButton("Update schematic && optics")
        update_btn.setMinimumHeight(36)
        update_btn.setStyleSheet("font-weight: bold;")
        update_btn.clicked.connect(self.update_view)

        self.result_label = QtWidgets.QLabel("Press “Update schematic & optics”.")
        self.result_label.setWordWrap(True)
        self.result_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.result_label.setStyleSheet("font-size: 13px; padding: 6px; background: #f6f6f6; border: 1px solid #ddd;")
        self.cal_status = QtWidgets.QLabel()
        self.cal_status.setWordWrap(True)
        self.cal_status.setStyleSheet("color: #555;")

        # filled when the user confirms in the Samples tab that the samples are placed
        self.start_label = QtWidgets.QLabel()
        self.start_label.setWordWrap(True)
        self.start_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.start_box = QtWidgets.QGroupBox("Where the samples are at the initial rotation")
        self.start_box.setStyleSheet("QGroupBox { background: #eef6ee; }")
        sb = QtWidgets.QVBoxLayout(self.start_box)
        sb.addWidget(self.start_label)
        self.start_box.hide()

        left = QtWidgets.QWidget()
        lv = QtWidgets.QVBoxLayout(left)
        # result_label / cal_status are kept up to date but not shown (too long for the panel)
        for w in (self.start_box, motor_box, sn_box, optic_box, update_btn):
            lv.addWidget(w)
        lv.addStretch(1)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidget(left)
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(430)

        self.figure = Figure(figsize=(11, 5.5))
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.mpl_connect("motion_notify_event", self._on_canvas_motion)
        self.canvas.mpl_connect("figure_leave_event", lambda _event: self._show_cursor(None))
        self.cursor_label = QtWidgets.QLabel()
        self.cursor_label.setToolTip("Mouse position in the sample plane view (as of the last update): the ST, SZ\n"
                                     "that bring this point onto the beam, and where it is on the plate.")
        self._plane = None  # (axes, model, motors, layout) of the last drawn sample plane view
        self._show_cursor(None)
        right = QtWidgets.QWidget()
        rv = QtWidgets.QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.addWidget(self.canvas, 1)
        rv.addWidget(self.cursor_label)

        splitter = QtWidgets.QSplitter()
        splitter.addWidget(scroll)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        box = QtWidgets.QVBoxLayout(self)
        box.setContentsMargins(4, 4, 4, 4)
        box.addWidget(splitter)

        self.last_result = None
        self._target_labels = None
        self.set_record(self.record)
        self.refresh_targets()
        self._show_target_height()

    # -- state ----------------------------------------------------------------
    def set_record(self, record: CalibrationRecord) -> None:
        """Use a configuration; the optic fields are loaded from it."""
        self.record = record
        self.optic_type.blockSignals(True)
        if self.optic_type.findText(record.optics.optic_type) < 0:
            self.optic_type.addItem(record.optics.optic_type)
        self.optic_type.setCurrentText(record.optics.optic_type)
        self.optic_type.blockSignals(False)
        self.optic_pos.setValue(record.optics.current_position)
        self._show_record()
        if not self.start_box.isHidden():
            self.show_start_positions()

    def plate_changed(self) -> None:
        """Another plate is mounted: the configuration's plate correction (SZ shift) may change."""
        self._show_record()
        if not self.start_box.isHidden():
            self.show_start_positions()

    def _show_record(self) -> None:
        record, optics = self.record, self.record.optics
        if optics.enabled:
            m = optics.motors
            ref = (f"in focus at optic {optics.optic_position:.4f} with ST {m.st:.4f}, SZ {m.sz:.4f}, SN {m.sn:.4f}, "
                   f"SRn {m.srn:.3f}, SRz {m.srz:.3f}")
        else:
            ref = f"in focus on the analyzer focus at optic {optics.optic_position:.4f}"
        self.optic_ref_label.setText(f"Optics reference: {ref}")
        note = record.plate_note(self._layout_getter().plate.key)
        self.cal_status.setText(f"Configuration in use: <b>{record.label}</b>"
                                + (f" — <span style='color:#b05000'>{note}</span>" if note else "")
                                + f" — {record.comment}")

    def config(self) -> StageConfig:
        """Stage constants of the configuration for the plate mounted now (SZ shift if it was made with a plate
        seated at another height, e.g. gating vs standard; and the plate offset found with "Fine tunings by ZPS/CPS")."""
        layout = self._layout_getter()
        return self.record.config_for(layout.plate.key, layout.plate_offset_v)

    def calibration(self) -> OpticsCalibration:
        return self.record.optics

    def _on_optic_type(self, text: str) -> None:
        # the collision solids of the configuration belong to its optic: another optic takes its defaults
        self.record = replace(self.record, optics=replace(self.record.optics, optic_type=text), collision=None)

    def bring_found_to_focal_plane(self) -> tuple[MotorPositions, float] | None:
        """"Fine tunings by ZPS/CPS". A sample was found on the beam and in focus at the entered stage positions with
        the optic (ZPS / CPS) at the entered position. The optic's focal distance is fixed, so the configuration's
        optics reference turns that optic position into where the focus, i.e. the sample surface, is along the beam.
        First the height H of the Target's sample is checked against it (check_found_height); then SN (ST
        compensating, the point slides along the beam, SZ stays) brings the surface onto the analyzer focal plane and
        the optic goes back to the configuration's position for the analyzer focus. Returns (motors, optic).

        With "H is exact" ticked the height is kept: the Target is where the beam meets its surface at that height
        (core.stage.beam_at_height), only its plate position is corrected, and SN brings that surface onto the analyzer
        focus; the optic reading is only compared. The state before is kept for undo_fine_tuning."""
        m, optic_now = self.motors.value(), self.optic_pos.value()
        state = self._fine_state()
        target_sample = self._target_sample()
        if (self.height_exact.isChecked() and target_sample is not None
                and not self._confirm_exact(target_sample, record=False)):
            return None  # H not confirmed as exact: nothing done
        height_text = self.check_found_height(m, optic_now)  # may correct H (or only x / y) of the target's sample
        model, cal = self.model(), self.calibration()
        y_optic = cal.focus_for_position(model, optic_now)
        y = y_optic
        sample = self._target_sample()
        if self.height_exact.isChecked() and sample is not None:
            t = self.target_point(self.target_combo.currentText())
            y = beam_at_height(model, m, t[2])
        u, v, w = (float(x) for x in model.lab_to_plate(m, y * Y_HAT))
        new = slide_to_sn(m, m.sn - y / 2 ** 0.5)
        optic_new = cal.position_for_focus(model, 0.0)
        if not self._go_to(new, "The found sample cannot be brought onto the analyzer focal plane", optic=optic_new):
            self._restore_fine_state(state)  # nothing done: take back a correction already applied
            return None
        self._fine_history.append(state)
        self.undo_fine_btn.setEnabled(True)
        self._show_target_height()
        height = w - model.plate.total_thickness
        side = "downstream" if y > 0 else "upstream"
        where = ("It was already on the analyzer focus." if abs(y) < TOLERANCE else
                 f"It was {abs(y) * 1000:.0f} µm {side} of the analyzer focus (optic {optic_now:.4f}).")
        self.goto_label.setStyleSheet("color: #207020;")
        self.goto_label.setText(
            f"Found sample (plate x = {u:.3f}, y = {v:.3f} mm, surface H = {height:.3f} mm above the plate top) "
            f"on the analyzer focal plane: ST = {new.st:.4f}, SZ = {new.sz:.4f}, <b>SN = {new.sn:.4f}</b> "
            f"(ΔSN = {unsigned_zero(new.sn - m.sn, 4):+.4f} mm, ΔST = {unsigned_zero(new.st - m.st, 4):+.4f} mm, "
            f"SZ kept), optic back to <b>{optic_new:.4f}</b> (configuration's position for the analyzer focus). "
            f"{where}"
            + (f"<br>{height_text}" if height_text else ""))
        self.goto_label.show()
        return new, optic_new

    # -- fine tuning: height of the target, undo --------------------------------------
    def _target_sample(self):
        label = self.target_combo.currentText()
        return self._layout_getter().sample_of(label) if label else None

    def _show_target_height(self) -> None:
        """The H field follows the Target's sample (disabled for the plate centre), with where H comes from."""
        sample = self._target_sample()
        self.height_box.blockSignals(True)
        self.height_box.setValue(sample.height if sample is not None else 0.0)
        self.height_box.blockSignals(False)
        self.height_box.setEnabled(sample is not None)
        kind, text = self.height_origin(sample)
        color = {"exact": "#207020", "eye": "#b05000", "default": "#c00000"}.get(kind, "#555")
        self.height_source.setStyleSheet(f"color: {color};")
        self.height_source.setText(text)
        self.height_source.setVisible(bool(text))

    def is_exact(self, sample) -> bool:
        """H of `sample` was confirmed as its known, exact height (and not changed since)."""
        h = self._exact.get(id(sample))
        return h is not None and abs(h - sample.height) < 5e-7 and sample.sn_checked is None

    def height_origin(self, sample) -> tuple[str, str]:
        """Where H of the sample comes from: ("exact" | "eye" | "default" | "entered" | "", text)."""
        if sample is None:
            return "", ""
        if self.is_exact(sample):
            return "exact", "H exact (known thickness): kept by the fine tuning."
        if sample.sn_checked is not None:
            return "eye", f"H from the SN set by eye (SN {sample.sn_checked:.3f} mm, about ±0.05 mm)."
        default = self.default_height_getter() if self.default_height_getter else None
        if default is not None and abs(sample.height - default) < 5e-7:
            return "default", (f"H is the default height of new samples ({default:.3f} mm): enter the known height "
                               "if it was never entered.")
        return "entered", ""

    def _known_height(self, sample) -> float | None:
        """Ask whether H of `sample` is its known, exact height (or for that height). None: cancelled."""
        kind, _ = self.height_origin(sample)
        h = sample.height
        why = {
            "eye": (f"H = {h:.3f} mm of {sample.name} comes from the SN set by eye (SN = {sample.sn_checked:.3f} mm, "
                    "about ±0.05 mm), not from a known thickness."),
            "default": (f"H = {h:.3f} mm of {sample.name} is the default height of new samples: it may never have "
                        "been entered."),
        }.get(kind, f"H of {sample.name} is {h:.3f} mm.")
        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Question)
        box.setWindowTitle("Is the sample height exact?")
        box.setText(
            f"{why}\n\nTrust: a known exact H (e.g. a wafer of known thickness) > the ZPS / CPS focus > the SN set by "
            "eye. If you do not know the thickness, leave “H is exact” off: the fine tuning then corrects H from the "
            "focus.\n\nIs it the known, exact height?")
        yes = box.addButton(f"Yes, H = {h:.3f} mm is exact", QtWidgets.QMessageBox.AcceptRole)
        enter = box.addButton("Enter the known H…", QtWidgets.QMessageBox.ActionRole)
        box.addButton(QtWidgets.QMessageBox.Cancel)
        box.exec()
        if box.clickedButton() is yes:
            return h
        if box.clickedButton() is enter:
            value, ok = QtWidgets.QInputDialog.getDouble(
                self, "Known sample height", f"Exact height H of {sample.name} (mm, above the plate surface):",
                h, 0.0, 100.0, 3)
            return float(value) if ok else None
        return None

    def _confirm_exact(self, sample, record: bool = True) -> bool:
        """Make sure H of `sample` is a known exact height before it is kept: asks when it comes from the SN set by
        eye, is the default or was not confirmed yet. The exact H replaces the SN set by eye (kept as a check).
        record: the state before can be taken back with Undo fine tuning (back to the SN set by eye)."""
        if self.is_exact(sample):
            return True
        h = self._known_height(sample)
        if h is None:
            return False
        if record and (sample.sn_checked is not None or abs(sample.height - h) > 5e-7):
            self._fine_history.append(self._fine_state())
            self.undo_fine_btn.setEnabled(True)
        self._set_exact(sample, h)
        return True

    def _set_exact(self, sample, h: float) -> None:
        if sample.sn_checked is not None:
            self._eye_sn[id(sample)] = sample.sn_checked
        changed = abs(sample.height - h) > 5e-7 or sample.sn_checked is not None
        sample.height, sample.sn_checked = h, None
        self._exact[id(sample)] = h
        self.heightConfirmed.emit()
        if not self.start_box.isHidden():
            self.show_start_positions()
        if changed:
            self.layoutCorrected.emit(sample.name)
            self.refresh_targets()
        self._show_target_height()

    def eye_check(self, sample) -> str:
        """The SN set by eye compared with the SN of the exact H (a check of SN_f / the mounting); "" if none."""
        eye = self._eye_sn.get(id(sample))
        if eye is None or not self.is_exact(sample):
            return ""
        sn = sn_from_height(self.config(), sample.height, self._layout_getter().plate)
        text = (f"SN set by eye {eye:.3f} mm, SN for the exact H on the analyzer focus {sn:.3f} mm "
                f"(Δ {unsigned_zero(eye - sn, 3):+.3f} mm")
        return text + (f", more than {EYE_SN_WARN:g} mm: check SN_f of the configuration or the mounting)"
                       if abs(eye - sn) > EYE_SN_WARN else ")")

    def _on_exact_toggled(self, on: bool) -> None:
        sample = self._target_sample()
        if on and sample is not None and not self._confirm_exact(sample):
            self.height_exact.blockSignals(True)
            self.height_exact.setChecked(False)
            self.height_exact.blockSignals(False)
        self._show_target_height()

    def _on_height_typed(self, value: float) -> None:
        sample = self._target_sample()
        if sample is None or abs(value - sample.height) < 5e-7:
            return
        if self.height_exact.isChecked():  # a height typed with "H is exact" ticked is the known one
            self._set_exact(sample, value)
        else:
            if sample.sn_checked is not None:
                self._eye_sn[id(sample)] = sample.sn_checked
            sample.height = value
            sample.sn_checked = None  # typed by hand: no longer from the SN set by eye (as in the Samples tab)
            self.layoutCorrected.emit(sample.name)
            self.refresh_targets()
        self.goto_label.hide()

    def _fine_state(self) -> dict:
        layout = self._layout_getter()
        return {"layout": layout, "plate_offset_v": layout.plate_offset_v,
                "samples": [(s, s.u, s.v, s.height, s.sn_checked) for s in layout.samples],
                "motors": self.motors.value(), "optic": self.optic_pos.value()}

    def _restore_fine_state(self, state: dict) -> list[str]:
        """Put the plate, the samples and the stage / optic fields back as in `state`; returns the samples changed."""
        layout = state["layout"]
        layout.plate_offset_v = state["plate_offset_v"]
        changed = []
        for s, u, v, h, sn in state["samples"]:
            if s in layout.samples and (s.u, s.v, s.height, s.sn_checked) != (u, v, h, sn):
                s.u, s.v, s.height, s.sn_checked = u, v, h, sn
                changed.append(s.name)
        self.motors.set_value(state["motors"])
        self.optic_pos.setValue(state["optic"])
        return changed

    def undo_fine_tuning(self) -> bool:
        """Take back the last "Fine tunings by ZPS/CPS" (sample position and height, plate offset, SN set by eye,
        stage and optic fields). False if there is nothing to take back (or the plate was changed since)."""
        while self._fine_history:
            state = self._fine_history.pop()
            if state["layout"] is self._layout_getter():
                break
        else:
            self.undo_fine_btn.setEnabled(False)
            return False
        changed = self._restore_fine_state(state)
        self.undo_fine_btn.setEnabled(bool(self._fine_history))
        for name in changed or [""]:
            self.layoutCorrected.emit(name or "the plate")
        self.refresh_targets()
        self._show_target_height()
        left = len(self._fine_history)
        self.goto_label.setStyleSheet("color: #555;")
        self.goto_label.setText(
            "Fine tuning taken back: samples, plate offset and stage / optic fields as before it"
            + (f" ({left} more fine tuning(s) can be taken back)." if left else
               " (the state before the first fine tuning, e.g. the SN set by eye)."))
        self.goto_label.show()
        return True

    def check_found_height(self, m: MotorPositions, optic: float) -> str:
        """Correction part of "Fine tunings by ZPS/CPS": the Target was found on the beam and in focus at m with the
        optic at `optic`. At SRz 0 (|SRz| below HEIGHT_CHECK_SRZ) the focus gives where the Target really is: x, plate
        offset and H (correct_found_at_srz0). After an SRz turn, if the optic is more than HEIGHT_CHECK_OPTIC off its
        prediction,
        fit one change of the sample height to the ST, SZ and optic errors together; if it explains them
        (fit_height), ask to correct H of the target's sample. Returns a line for the result text ("" when there is
        nothing to say)."""
        label = self.target_combo.currentText()
        layout = self._layout_getter()
        sample = layout.sample_of(label) if label else None
        t = self.target_point(label) if label else None
        if t is None or sample is None:
            return ""
        optic_type = self.optic_type.currentText()
        capillary = "capillary" in optic_type
        name = "CPS" if capillary else "ZPS"
        if abs(m.srz) < HEIGHT_CHECK_SRZ:
            return self.correct_found_at_srz0(m, optic, label, sample, t, name, optic_type)
        if self.height_exact.isChecked():
            eye = self.eye_check(sample)
            return (f"<span style='color:#555'>H of {sample.name} marked exact ({sample.height:.3f} mm): no height "
                    "check after the SRz turn." + (f" {eye}." if eye else "") + "</span>")
        fit = fit_height(self.model(), m, self.calibration(), optic, *t, sigmas=measurement_sigmas(optic_type))
        st, sz, op = fit.before
        if abs(op) <= HEIGHT_CHECK_OPTIC:
            return (f"<span style='color:#555'>Height check of {label}: {name} {op:+.3f} mm from the prediction "
                    f"(within {HEIGHT_CHECK_OPTIC:g} mm): H kept.</span>")
        a_st, a_sz, a_op = fit.after
        errors = f"ST {st:+.3f}, SZ {sz:+.3f}, {name} {op:+.3f} mm"
        if not fit.explained:
            return ("<span style='color:#b00'>Height check of " + label + f": found off the prediction by {errors}. "
                    f"No change of H explains it (best ΔH = {fit.dh:+.3f} mm leaves ST {a_st:+.3f}, SZ {a_sz:+.3f}, "
                    f"{name} {a_op:+.3f} mm): H kept. More likely the plate position of the sample (Fine tunings at "
                    "SRz 0), the SRz axis or SN_f of the configuration.</span>")
        note = ("\n\nCapillary: the CPS focus is read to about ±0.10 mm, so this ΔH is known to about ±0.07 mm "
                "only. Prefer a zone-plate focus when possible." if capillary else "")
        answer = QtWidgets.QMessageBox.question(
            self, "Correct the sample height?",
            f"{label} was found on the beam and in focus at SRz = {m.srz:g}° off the prediction by {errors}.\n\n"
            f"A height change ΔH = {fit.dh:+.3f} mm of {sample.name} explains these errors together: "
            f"with it they become ST {a_st:+.3f}, SZ {a_sz:+.3f}, {name} {a_op:+.3f} mm "
            f"(all within {HEIGHT_EXPLAIN_TOL:g} mm).\n\n"
            f"Correct H of {sample.name}: {sample.height:.3f} → {max(sample.height + fit.dh, 0.0):.3f} mm "
            "(kept for the next positions and rotations)?" + note,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.Yes,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return (f"<span style='color:#555'>Height check of {label}: ΔH = {fit.dh:+.3f} mm would explain the "
                    f"errors ({errors}); H not changed.</span>")
        before = sample.height
        apply_found_offset(self.config(), layout, sample, 0.0, 0.0, fit.dh)
        self.layoutCorrected.emit(sample.name)
        self.refresh_targets()
        return (f"<span style='color:#207020'>Height of {sample.name} corrected: H {before:.3f} → "
                f"{sample.height:.3f} mm (it explains the errors {errors}).</span>")

    def correct_found_at_srz0(self, m: MotorPositions, optic: float, label: str, sample, t, name: str,
                              optic_type: str) -> str:
        """SRz 0 part of "Fine tunings by ZPS/CPS" (replaces "Found here"): the surface on the beam is parallel to the
        analyzer focal plane, so the plate point at the optic focus (fixed focal distance) gives where the Target
        really is, independent of the rotation axes: Δx (this sample, with its devices), Δy (the plate sits at another
        height in the holder: plate offset, every sample's SZ) and ΔH (this sample's height). Asks, then applies them.
        Returns a line for the result text."""
        model, cal = self.model(), self.calibration()
        layout = self._layout_getter()
        y = cal.focus_for_position(model, optic)
        sigma = measurement_sigmas(optic_type)[1] / 2 ** 0.5  # optic reading along the beam -> along the normal
        if self.height_exact.isChecked():
            return self._correct_found_exact_height(m, optic, label, sample, t, name, y, sigma)
        du, dv, dw = found_offset(model, m, *t, y=y)
        su, sv, sw = (unsigned_zero(x, 3) for x in (du, dv, dw))
        if abs(du) < FOUND_POSITION_MIN and abs(dv) < FOUND_POSITION_MIN and abs(dw) < HEIGHT_FOCUS_MIN:
            return (f"<span style='color:#555'>{label} found where expected (Δx {su:+.3f}, Δy {sv:+.3f}, "
                    f"ΔH {sw:+.3f} mm): nothing corrected.</span>")
        large = ""
        if abs(du) > LARGE_FOUND_OFFSET:
            large = (f"\n\nΔx (ST) is more than {LARGE_FOUND_OFFSET:g} mm: more likely the beam spot has moved (optic "
                     "realigned?) than the sample, or the Target is not the one on the beam. If other samples show the "
                     "same ST shift, ask beamline staff for an optics recalibration (RealSampleCalibration, mode "
                     "optics) instead of correcting the sample.")
        if abs(dw) > LARGE_FOUND_OFFSET:
            large += (f"\n\nΔH is more than {LARGE_FOUND_OFFSET:g} mm: check the Target, the optic position typed and "
                      "SN_f of the configuration.")
        if abs(layout.plate_offset_v + dv) > PLATE_OFFSET_WARNING:
            large += (f"\n\nThe plate would then sit {layout.plate_offset_v + dv:+.2f} mm off its usual height in the "
                      f"holder (more than {PLATE_OFFSET_WARNING:g} mm): check that the right sample was found.")
        answer = QtWidgets.QMessageBox.question(
            self, "Correct the plate / sample position and height?",
            f"{label} was found on the beam and in focus at SRz = 0° with {name} = {optic:.4f} "
            f"(ST = {m.st:.4f}, SZ = {m.sz:.4f}, SN = {m.sn:.4f}).\n\n"
            "The focal distance of the optic is fixed, so the focus tells where the surface is: "
            f"Δx = {su:+.3f}, Δy = {sv:+.3f} mm on the plate and ΔH = {sw:+.3f} ± {sigma:.3f} mm from where it was "
            "drawn.\n\n"
            f"• Δy is taken as the plate sitting at another height in the sample holder (it does not always go in at "
            f"the same height; not the beam): the whole plate moves by {sv:+.3f} mm (plate offset "
            f"{layout.plate_offset_v:+.3f} → {layout.plate_offset_v + dv:+.3f} mm), so every sample's SZ changes by "
            f"{unsigned_zero(-dv, 3):+.3f} mm.\n"
            f"• Δx and ΔH: {sample.name} (with its devices) is moved by Δx and its height corrected "
            f"(H {sample.height:.3f} → {max(sample.height + dw, 0.0):.3f} mm); the other samples stay." + large
            + self._height_hint(sample),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.Yes,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return (f"<span style='color:#555'>{label}: the {name} focus gives Δx {su:+.3f}, Δy {sv:+.3f}, "
                    f"ΔH {sw:+.3f} mm; nothing corrected.</span>")
        before = sample.height
        apply_found_offset(self.config(), layout, sample, du, dv, dw)
        self.layoutCorrected.emit(sample.name)
        self.refresh_targets()
        return (f"<span style='color:#207020'>Corrected by the {name} focus: {sample.name} moved by Δx {su:+.3f} mm, "
                f"H {before:.3f} → {sample.height:.3f} mm (± {sigma:.3f}); plate offset "
                f"{layout.plate_offset_v:+.3f} mm.</span>")

    def _height_hint(self, sample) -> str:
        """Reminder in the fine-tuning window when H was never entered (default) or set by eye: a known thickness
        would be better (Target's sample H, H is exact)."""
        kind, _ = self.height_origin(sample)
        if kind == "default":
            return (f"\n\nH of {sample.name} is still the default height of new samples ({sample.height:.3f} mm). "
                    "If you know its thickness, answer No, enter it in “Target's sample H”, tick “H is exact” and "
                    "press Fine tunings again.")
        if kind == "eye":
            return (f"\n\nH of {sample.name} comes from the SN set by eye; the focus is more precise and corrects it. "
                    "If you know its exact thickness, answer No, enter it in “Target's sample H” and tick “H is "
                    "exact”.")
        return ""

    def _correct_found_exact_height(self, m: MotorPositions, optic: float, label: str, sample, t, name: str,
                                    y_optic: float, sigma: float) -> str:
        """SRz 0 fine tuning with "H is exact": the Target is where the beam meets its surface at the known height,
        so only Δx (this sample) and Δy (plate offset) are corrected, from the photo error; the optic focus reading is
        compared with that surface (its difference is not taken as a height error)."""
        model = self.model()
        layout = self._layout_getter()
        y = beam_at_height(model, m, t[2])
        du, dv, _ = found_offset(model, m, *t, y=y)
        _, _, dw_optic = found_offset(model, m, *t, y=y_optic)
        su, sv, so = (unsigned_zero(x, 3) for x in (du, dv, dw_optic))
        optic_note = (f"the {name} focus puts the surface {so:+.3f} ± {sigma:.3f} mm from H = {sample.height:.3f} mm"
                      + (" (more than 3 σ: check the optic position typed, H or SN_f of the configuration)"
                         if abs(dw_optic) > 3 * sigma else ""))
        eye = self.eye_check(sample)
        if eye:
            optic_note += f"; {eye}"
        if abs(du) < FOUND_POSITION_MIN and abs(dv) < FOUND_POSITION_MIN:
            return (f"<span style='color:#555'>{label} found where expected (Δx {su:+.3f}, Δy {sv:+.3f} mm; H exact, "
                    f"kept); {optic_note}: nothing corrected.</span>")
        large = ""
        if abs(du) > LARGE_FOUND_OFFSET:
            large = (f"\n\nΔx (ST) is more than {LARGE_FOUND_OFFSET:g} mm: more likely the beam spot has moved (optic "
                     "realigned?) than the sample, or the Target is not the one on the beam.")
        if abs(layout.plate_offset_v + dv) > PLATE_OFFSET_WARNING:
            large += (f"\n\nThe plate would then sit {layout.plate_offset_v + dv:+.2f} mm off its usual height in the "
                      f"holder (more than {PLATE_OFFSET_WARNING:g} mm): check that the right sample was found.")
        answer = QtWidgets.QMessageBox.question(
            self, "Correct the plate / sample position?",
            f"{label} was found on the beam at SRz = 0° (ST = {m.st:.4f}, SZ = {m.sz:.4f}, SN = {m.sn:.4f}). The height "
            f"of {sample.name} is marked exact (H = {sample.height:.3f} mm, kept), so the Target is where the beam "
            f"meets its surface: Δx = {su:+.3f}, Δy = {sv:+.3f} mm on the plate from where it was drawn (photo "
            f"error).\n\n"
            f"• Δy: the whole plate moves by {sv:+.3f} mm in the holder (plate offset {layout.plate_offset_v:+.3f} → "
            f"{layout.plate_offset_v + dv:+.3f} mm), every sample's SZ changes by {unsigned_zero(-dv, 3):+.3f} mm.\n"
            f"• Δx: {sample.name} (with its devices) is moved by Δx; the other samples stay.\n\n"
            f"For information: {optic_note}." + large,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.Yes,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return (f"<span style='color:#555'>{label}: Δx {su:+.3f}, Δy {sv:+.3f} mm (H exact); nothing "
                    "corrected.</span>")
        apply_found_offset(self.config(), layout, sample, du, dv, 0.0)
        self.layoutCorrected.emit(sample.name)
        self.refresh_targets()
        return (f"<span style='color:#207020'>Corrected (H exact, {sample.height:.3f} mm kept): {sample.name} moved by "
                f"Δx {su:+.3f} mm; plate offset {layout.plate_offset_v:+.3f} mm. {optic_note[0].upper()}"
                f"{optic_note[1:]}.</span>")

    def model(self) -> StageModel:
        return StageModel(self.config(), self._layout_getter().plate)

    # -- targets ----------------------------------------------------------------
    def refresh_targets(self) -> None:
        # called on every mouse move while a sample is dragged: the lists only change with the names
        labels = self.target_labels()
        if labels != self._target_labels:
            self._target_labels = labels
            current = self.target_combo.currentText()
            self.target_combo.blockSignals(True)
            self.target_combo.clear()
            self.target_combo.addItems(["plate centre", *labels])
            self.target_combo.setCurrentIndex(max(self.target_combo.findText(current), 0))
            self.target_combo.blockSignals(False)
        if not self.start_box.isHidden():
            self.show_start_positions()
        if hasattr(self, "height_box"):
            self._show_target_height()

    def show_start_positions(self) -> None:
        """List the ST / SZ / SN putting each sample / device on the analyzer focus at SRn = ref, SRz = 0."""
        model = self.model()
        layout = self._layout_getter()
        c = model.config
        rows = []
        for label in ["plate centre", *self.target_labels()]:
            st, sz, sn = (unsigned_zero(x, 3) for x in model.reference_motors(*self.target_point(label)))
            sample = layout.sample_of(label)
            mark = ("" if sample is None else " (by eye)" if sample.sn_checked is not None
                    else " (exact H)" if self.is_exact(sample) else " (from H)")
            rows.append(f"<tr><td>{label}</td><td align=right>{st:.3f}</td><td align=right>{sz:.3f}</td>"
                        f"<td align=right>{sn:.3f}{mark}</td></tr>")
        if layout.plate_offset_v:
            rows.append(f"<tr><td colspan=4><i>plate {layout.plate_offset_v:+.3f} mm off its usual height in the "
                        "holder (Fine tunings by ZPS/CPS): SZ0 shifted for all samples</i></td></tr>")
        self.start_label.setText(
            f"At SRn = {c.srn_ref:g}° (plate vertical, tab up), SRz = 0°, PIX = PIY = {c.pi_center:g} µm, "
            "each sample centre is on the beam at the analyzer focus at:"
            "<table cellspacing=0 cellpadding=3><tr><th align=left>sample</th><th>ST (mm)</th><th>SZ (mm)</th>"
            f"<th>SN (mm)</th></tr>{''.join(rows)}</table>"
            f"(ST = ST0 − x, SZ = SZ0 − y with ST0 = {c.st0:g}, SZ0 = {c.sz0:g}; SN puts the sample surface "
            "in the analyzer focal plane: <i>by eye</i> the SN set by eye, <i>from H</i> / <i>exact H</i> from the "
            "sample height H, right only if H is exact: otherwise set the SN by eye in the Samples tab.) <i>Bring target onto the beam</i> gives ST, SZ for the entered SN, rotations "
            "and piezo, and how far the target then is from the analyzer focus; <i>Correct SN</i> only if that is too far."
        )
        self.start_box.show()

    def target_labels(self) -> list[str]:
        return [label for label, *_ in self._layout_getter().targets()]

    def target_point(self, label: str):
        """(u, v, w) of a target: sample / device surface centre, or the plate centre."""
        plate = self._layout_getter().plate
        if label == "plate centre":
            return 0.0, 0.0, plate.total_thickness
        for name, u, v, h in self._layout_getter().targets():
            if name == label:
                return u, v, plate.total_thickness + h
        return None

    # -- actions ----------------------------------------------------------------
    def bring_target_on_beam(self) -> MotorPositions | None:
        """ST / SZ putting the target on the beam with SN as entered; reports its distance from the analyzer focus.
        A target whose sample height was checked keeps the SN of that check (exact at SRn ref, SRz 0: its height
        was corrected with it), whatever the SN field says."""
        label = self.target_combo.currentText()
        t = self.target_point(label)
        if t is None:
            return None
        m = self.motors.value()
        checked = checked_sn(self._layout_getter(), label)
        sn = m.sn if checked is None else checked
        pi = self.config().pi_center  # another target: the piezo back to its centre (it may still hold a scan position)
        new = self.model().motors_on_beam(*t, srn=m.srn, srz=m.srz, sn=sn, pix=pi, piy=pi)
        if not self._go_to(new, "The target cannot be brought onto the beam with SN kept",
                           "\n\nCorrect SN may reach it (it also moves SN)."):
            return None
        self._show_goto(label, t, new, checked=checked is not None)
        return new

    def bring_target_to_focus(self) -> MotorPositions | None:
        """Second step, when the target is too far from the analyzer focus with SN kept: SN, ST, SZ putting it there."""
        label = self.target_combo.currentText()
        t = self.target_point(label)
        if t is None:
            return None
        m = self.motors.value()
        pi = self.config().pi_center
        new = self.model().motors_for_target(*t, srn=m.srn, srz=m.srz, pix=pi, piy=pi)
        if not self._go_to(new, "The target cannot be brought to the analyzer focus"):
            return None
        self._show_goto(label, t, new, m.sn)
        return new

    def centre_piezo(self):
        """The sample was seen at the entered PIX / PIY (a piezo scan), away from the centre, with the optic in focus at
        the entered position: ST / SZ that show it with the piezo centred at the same SRn / SRz, SN kept, and the optic
        refocused (rotation.recentre_piezo, as the last step of Rotate sample). Returns the PiezoRecentre or None."""
        from ..alignment.rotation import recentre_piezo
        m, optic = self.motors.value(), self.optic_pos.value()
        pi = self.config().pi_center
        if abs(m.pix - pi) < 1e-9 and abs(m.piy - pi) < 1e-9:
            QtWidgets.QMessageBox.information(
                self, "Centre the piezo", f"PIX and PIY are already at the centre ({pi:g} µm): enter the PIX, PIY "
                "where the sample is seen in the scan first.")
            return None
        p = recentre_piezo(self.model(), m, optic, self.calibration())
        if not self._go_to(p.new, "The piezo-centred position cannot be reached", optic=p.optic_new):
            return None
        self.goto_label.setStyleSheet("color: #207020;")
        self.goto_label.setText(
            f"Seen at PIX = {m.pix:.2f}, PIY = {m.piy:.2f} µm → with the piezo centred ({pi:g} / {pi:g} µm), SRn, SRz "
            f"and SN kept: ST = <b>{p.new.st:.4f}</b> (Δ {unsigned_zero(p.new.st - m.st, 4):+.4f}), SZ = "
            f"<b>{p.new.sz:.4f}</b> (Δ {unsigned_zero(p.new.sz - m.sz, 4):+.4f}) mm, optic <b>{p.optic_new:.4f}</b> "
            f"(Δ {unsigned_zero(p.optic_new - optic, 4):+.4f}; the point moves {p.beam_shift * 1000:.1f} µm along the "
            "beam).")
        self.goto_label.show()
        return p

    def _go_to(self, new: MotorPositions, what: str, hint: str = "", optic: float | None = None) -> bool:
        """Move to `new` (and the optic to `optic`, if given) unless out of range or colliding."""
        bad = out_of_range(new)
        if bad:
            QtWidgets.QMessageBox.warning(self, "Out of range", f"{what}:\n" + "\n".join(bad)
                                          + "\n\nThe positions are not changed." + hint)
            return False
        hits = self.move_collisions(new, optic_new=optic)
        if hits:
            QtWidgets.QMessageBox.warning(self, "Collision", f"{what}: the plate would touch {hits}."
                                          "\n\nThe positions are not changed." + hint)
            return False
        if optic is not None:
            self.optic_pos.setValue(optic)
        self.motors.set_value(new)
        self.update_view()
        return True

    def _show_goto(self, label: str, t, m: MotorPositions, sn_before: float | None = None,
                   checked: bool = False) -> None:
        """Where the target is along the beam after a move, and the SN correction that would remove it."""
        model = self.model()
        y = model.beam_position(m, *t)
        res = self.last_result
        optic = (f" Optic for focus on it: <b>{res.required_optic_position:.4f}</b>."
                 if res is not None and res.required_optic_position is not None else "")
        if sn_before is not None:
            text = (f"<b>{label}</b> on the analyzer focus: ST = {m.st:.4f}, SZ = {m.sz:.4f}, "
                    f"<b>SN = {m.sn:.4f}</b> (ΔSN = {unsigned_zero(m.sn - sn_before, 4):+.4f} mm).{optic}")
            self.goto_label.setStyleSheet("color: #207020;")
        else:
            kept = "SN of its height check" if checked else "SN"
            text = (f"<b>{label}</b> on the beam with {kept} = {m.sn:.4f} kept: ST = {m.st:.4f}, SZ = {m.sz:.4f}."
                    f"{optic}<br>")
            if abs(y) < TOLERANCE:
                text += "It is on the analyzer focus."
            elif checked:
                text += (f"It is {abs(y) * 1000:.0f} µm {'downstream' if y > 0 else 'upstream'} of the analyzer focus "
                         "(model, this rotation): SN is kept from the height check (right at SRn "
                         f"{self.config().srn_ref:g}°, SRz 0°); the optic refocuses on it.")
                self.goto_label.setStyleSheet("color: #207020;")
                self.goto_label.setText(text)
                self.goto_label.show()
                return
            else:
                text += (f"It is <b>{abs(y) * 1000:.0f} µm {'downstream' if y > 0 else 'upstream'}</b> of the analyzer "
                         f"focus (model); ΔSN = {sn_to_focus(model, m, *t):+.4f} mm (ST compensating) would remove it.")
                text += (" <b>Too far: the spectra would be distorted — Correct SN?</b>" if abs(y) > FOCUS_WARNING
                         else " Close enough: no SN correction needed.")
            self.goto_label.setStyleSheet("color: #b00;" if abs(y) > FOCUS_WARNING else "color: #207020;")
        self.goto_label.setText(text)
        self.goto_label.show()

    # -- anti-collision ------------------------------------------------------
    def collision_hits(self, m: MotorPositions, optic_positions) -> list[str]:
        """Solids (analyzer, OSA, ...) the plate touches at m with the optic at any of these absolute positions."""
        model = self.model()
        ys = [self.calibration().focus_for_position(model, p) for p in optic_positions]
        return collisions(model, m, self._layout_getter(), self.record.collision_geometry(), ys,
                          self.calibration().reference_y(model))

    def move_collisions(self, new: MotorPositions, optic_new: float | None = None, optic_now: float | None = None) -> str:
        """What the plate touches at `new`, with the optic where it is now (`optic_now`, default: the entered
        position) or refocused (`optic_new`, default: the position focusing on the illuminated surface at
        `new`); empty if nothing."""
        optic_now = self.optic_pos.value() if optic_now is None else optic_now
        if optic_new is None:
            res = focus_correction(self.model(), new, self._layout_getter(), self.calibration(), self.optic_pos.value())
            optic_new = res.required_optic_position
        out = []
        for name, positions in (("with the optic where it is now", [optic_now]),
                                ("with the optic refocused", [] if optic_new is None else [optic_new])):
            hits = self.collision_hits(new, positions)
            if hits:
                out.append(f"{', '.join(hits)} ({name})")
        return "; ".join(out)

    def describe_limits(self, m: MotorPositions) -> tuple[str, list[str]]:
        """Collision-free ST / SN / SZ ranges at m (optic as entered) as text, and the solids touched now."""
        model, layout, geo = self.model(), self._layout_getter(), self.record.collision_geometry()
        y = self.calibration().focus_for_position(model, self.optic_pos.value())
        fixed_y = self.calibration().reference_y(model)  # where the OSA stays
        hits = collisions(model, m, layout, geo, [y], fixed_y)
        head = (f"Anti-collision ({self.optic_type.currentText()} at {self.optic_pos.value():.4f}, "
                f"margin {geo.margin:g} mm)")
        if hits:
            return f"<b>{head}: COLLISION now with {', '.join(hits)}.</b>", hits
        limits = motor_limits(model, m, layout, geo, [y], TRAVEL, fixed_y)
        parts = []
        for name, lim in limits.items():
            label, *_ = MOTOR_SPECS[name]
            lo = f"{lim.lo:.3f}" + (f" ({lim.lo_by})" if lim.lo_by != "travel" else "")
            hi = f"{lim.hi:.3f}" + (f" ({lim.hi_by})" if lim.hi_by != "travel" else "")
            parts.append(f"{label} {lo} … {hi}")
        text = f"{head}, one motor moved at a time: " + " · ".join(parts)
        shadow = in_acceptance(geo, [y], fixed_y)
        if shadow:
            text += (f"<br><b>{', '.join(shadow)} in the analyzer acceptance cone (±{ACCEPTANCE_HALF_ANGLE:g}°): "
                     "it would shadow the electrons.</b>")
        return text, []

    def update_view(self) -> None:
        layout = self._layout_getter()
        model = self.model()
        m = self.motors.value()
        res = focus_correction(model, m, layout, self.calibration(), self.optic_pos.value())
        _, hits = self.describe_limits(m)  # drawn in red in the schematic; moves into a collision are refused
        _, ax_plane = draw_schematic(self.figure, model, m, layout, res, self.optic_type.currentText(),
                                     self.record.collision_geometry(), tuple(hits),
                                     self.calibration().reference_y(model))
        self._plane = (ax_plane, model, m, layout)
        self._show_cursor(None)
        self.canvas.draw_idle()
        self.result_label.setText(self.describe(res))
        self.last_result = res

    # -- cursor readout ------------------------------------------------------
    def _on_canvas_motion(self, event) -> None:
        if self._plane is None or event.inaxes is not self._plane[0] or event.xdata is None:
            self._show_cursor(None)
        else:
            self._show_cursor((event.xdata, event.ydata))

    def cursor_text(self, st: float, sz: float) -> str:
        """Readout for the sample plane point (ST, SZ): plate position and what lies there."""
        _, model, m, layout = self._plane
        c = model.config
        u, v = model.plate_from_stage_frame(m, (c.st0 - st, c.sz0 - sz))
        text = f"cursor: ST = {st:.3f} mm, SZ = {sz:.3f} mm   (plate x = {u:.2f}, y = {v:.2f} mm)"
        hits = []
        for s in layout.samples:
            u0, v0, u1, v1 = s.bounds()
            if u0 <= u <= u1 and v0 <= v <= v1:
                hits.append(s.name)
        if hits:
            text += "   on " + ", ".join(hits)
        return text

    def _show_cursor(self, point) -> None:
        self.cursor_label.setText("cursor: ST = –, SZ = –" if point is None else self.cursor_text(*point))

    def describe_focal_plane(self) -> str:
        """Which surface height is on the analyzer focal plane (the camera "SN = 0" line) now.

        SN_f refers to the standard plate, so a surface put on that line shows its height
        above the plate top whatever SN reads (e.g. SN_f = -0.1 after maintenance)."""
        model, m = self.model(), self.motors.value()
        plate = model.plate
        w = model.focal_plane_height(m)
        _, _, sn_top = model.reference_motors(0.0, 0.0, plate.total_thickness)
        return (f"Analyzer focal plane (camera “SN = 0” line) at these positions: surface "
                f"H = {w - plate.total_thickness:.3f} mm above the plate top "
                f"(plate top in focus at SN = {sn_top:.3f}, SN_f = {self.config().sn_f:.3f}).")

    def describe(self, res) -> str:
        if res.hit is None:
            return "<b>The beam misses the plate</b> (or runs parallel to it).<br>" + self.describe_focal_plane()
        st, sz, sn = self.model().reference_motors(*res.plate_uv, res.surface_w)
        lines = [
            f"Beam lands on <b>{res.target}</b>: the point that comes onto the beam at ST = {st:.3f}, "
            f"SZ = {sz:.3f}, SN = {sn:.3f} with SRn = {self.config().srn_ref:g}, SRz = 0.",
            f"Beam spot is {abs(res.hit[1]):.3f} mm {'downstream' if res.hit[1] > 0 else 'upstream'} of the analyzer focus."
            if abs(res.hit[1]) >= TOLERANCE else "Beam spot is on the analyzer focus.",
            self.describe_focal_plane(),
        ]
        if abs(res.required_optic_position - res.optic_position) < TOLERANCE:
            lines.append(f"<b>Optic position {res.optic_position:.4f}: in focus on {res.target}.</b>")
        else:
            lines.append(
                f"<b>Optic position for focus on {res.target}: {res.required_optic_position:.4f}</b> "
                f"(entered: {res.optic_position:.4f})."
            )
        return "<br>".join(lines)
