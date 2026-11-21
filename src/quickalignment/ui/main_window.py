"""Main window: "Samples" tab (plate editor) and "Stage & Optics" tab."""

from __future__ import annotations

import sys

from ..core.calibration import CalibrationRecord, CalibrationStore
from ..core.geometry import SampleLayout
from ..core.session import Session
from ._qt import QtWidgets, exec_app, install_excepthook
from .calibration_dialog import CalibrationDialog
from ..core.stage import OPTIC_TYPES
from .plate_choice import ask_plate, ask_setup
from .plate_editor import PlateEditor
from .quick_rotation_panel import QuickRotationPanel
from .rotation_panel import RotationPanel
from .stage_panel import StagePanel, set_motor_limits


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, session: Session | None = None, store: CalibrationStore | None = None, optic: str | None = None):
        super().__init__()
        self.setWindowTitle("ANTARES QuickAlignment")
        self.resize(1450, 860)
        self._path: str | None = None

        self.store = store or CalibrationStore()
        set_motor_limits(self.store.motor_limits())  # before the input fields are made
        self.editor = PlateEditor()
        self.stage = StagePanel(lambda: self.editor.layout_model)
        self.editor.config_getter = self.stage.config  # SN_f of the configuration in use, for the height check
        self.stage.default_height_getter = self.editor.default_height  # to tell an H never entered
        self.editor.height_exact_getter = self.stage.is_exact  # the SN hint of Set SN by eye
        self.stage.heightConfirmed.connect(self.editor._refresh_sn_hint)
        self.editor.layoutChanged.connect(self.stage.refresh_targets)
        self.editor.samplesPlaced.connect(self.go_to_stage)
        self.stage.layoutCorrected.connect(self._on_layout_corrected)
        self.rotation = RotationPanel(self.stage, lambda: self.editor.layout_model, self.editor.default_height)
        # on its own: reads only the configuration in use and the plate mounted
        self.quick_rotation = QuickRotationPanel(self.stage, lambda: self.editor.layout_model.plate)
        self.cal_dialog = CalibrationDialog(self.store, self.stage, self)
        self.cal_dialog.recordChanged.connect(self._on_record)
        self.cal_dialog.limitsChanged.connect(self._on_limits)
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.addTab(self.editor, "Samples")
        self.tabs.addTab(self.stage, "Stage && Optics")
        self.tabs.addTab(self.rotation, "Rotate sample")
        self.tabs.addTab(self.quick_rotation, "Quick sample rotation (without pre-setup)")
        self.setCentralWidget(self.tabs)

        bar = self.addToolBar("File")
        for text, slot in (
            ("New", self.new_session),
            ("Open…", self.open_session),
            ("Save", self.save_session),
            (None, None),
            ("Configuration…", self.open_calibration),
            ("Change plate…", self.change_plate),
        ):
            if text is None:
                bar.addSeparator()
                continue
            btn = QtWidgets.QToolButton()
            btn.setText(text)
            btn.clicked.connect(slot)
            bar.addWidget(btn)
        bar.addSeparator()
        self.plate_label = QtWidgets.QLabel()
        self.plate_label.setStyleSheet("padding-left: 8px; font-weight: bold;")
        bar.addWidget(self.plate_label)
        self.cal_label = QtWidgets.QLabel()
        self.cal_label.setStyleSheet("padding-left: 12px;")
        bar.addWidget(self.cal_label)
        self.statusBar().showMessage("Draw samples on the plate, then go to “Stage & Optics”.")
        self.set_session(session or Session())
        # the newest calibration configuration (for the chosen optic) is used by default
        self._on_record(self.store.latest(optic))

    def open_calibration(self) -> None:
        self.cal_dialog.show()
        self.cal_dialog.raise_()
        self.cal_dialog.activateWindow()

    def _on_record(self, record: CalibrationRecord) -> None:
        self.stage.set_record(record)
        self.rotation.update_optic()
        self.quick_rotation.update_optic()
        self._show_cal_label()
        self.stage.update_view()

    def _show_cal_label(self) -> None:
        record = self.stage.record
        d = record.plate_shift(self.editor.layout_model.plate.key)
        self.cal_label.setText(f"Configuration: {record.label}"
                               + (f" (made with the {record.plate or 'standard'} plate: SZ0 {d:+g} mm)" if d else ""))
        self.cal_label.setToolTip(record.plate_note(self.editor.layout_model.plate.key))

    def _on_limits(self) -> None:
        self.stage.motors.apply_limits()
        self.rotation.apply_limits()
        self.quick_rotation.apply_limits()
        self.stage.update_view()  # out-of-range and anti-collision readouts with the new limits
        self.statusBar().showMessage("New motor limits in use.")

    def session(self) -> Session:
        return Session(self.editor.layout_model, self.stage.motors.value())

    def set_session(self, session: Session) -> None:
        self.editor.set_layout(session.layout)
        self.plate_label.setText(f"Plate: {session.layout.plate.name}")
        self.stage.plate_changed()
        self._show_cal_label()
        self.stage.motors.set_value(session.motors)
        self.stage.refresh_targets()
        self.stage.update_view()

    def new_session(self) -> None:
        optic = self.stage.optic_type.currentText()
        setup = ask_setup(self.editor.layout_model.plate, optic if optic in OPTIC_TYPES else OPTIC_TYPES[0], self)
        if setup is None:
            return
        plate, new_optic = setup
        self._path = None
        self.set_session(Session(layout=SampleLayout(plate=plate)))
        if new_optic != optic:
            self._on_record(self.store.latest(new_optic))

    def _on_layout_corrected(self, name: str) -> None:
        self.editor.set_layout(self.editor.layout_model)
        self.statusBar().showMessage(f"Position of {name} corrected.")

    def go_to_stage(self) -> None:
        """Samples are placed: show where they are at the reference orientation in the Stage tab."""
        self.stage.show_start_positions()
        self.tabs.setCurrentWidget(self.stage)
        self.statusBar().showMessage(
            f"Positions of the samples at SRn = {self.stage.config().srn_ref:g}°, SRz = 0° are shown in “Stage & Optics”.")

    def change_plate(self) -> None:
        plate = ask_plate(self.editor.layout_model.plate, self)
        if plate is None:
            return
        session = self.session()
        session.layout.plate = plate  # samples are kept; misplaced ones are flagged
        session.layout.plate_offset_v = 0.0  # another plate goes in: the offset found for the old one is gone
        self.set_session(session)

    def open_session(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open session", "", "Session (*.json)")
        if not path:
            return
        try:
            self.set_session(Session.load(path))
        except (OSError, ValueError, TypeError, KeyError) as exc:
            QtWidgets.QMessageBox.critical(self, "Open failed", str(exc))
            return
        self._path = path
        self.statusBar().showMessage(f"Loaded {path}")

    def save_session(self) -> None:
        """Save to the session's file; the first save asks for the file name."""
        path = self._path
        if path is None:
            path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save session", "session.json", "Session (*.json)")
            if not path:
                return
        try:
            self.session().save(path)
        except OSError as exc:
            QtWidgets.QMessageBox.critical(self, "Save failed", f"The session could not be saved to\n{path}:\n\n{exc}")
            return
        self._path = path
        self.statusBar().showMessage(f"Saved {self._path}")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(argv)
    install_excepthook("QuickAlignment")
    from .photo_cache import photo_cache
    app.aboutToQuit.connect(photo_cache().clear)  # photos kept for this run (also deleted at exit)
    session, path = Session(), None
    if len(argv) > 1:
        try:
            session, path = Session.load(argv[1]), argv[1]
        except (OSError, ValueError, TypeError, KeyError) as exc:
            QtWidgets.QMessageBox.critical(None, "Open failed",
                                           f"The session {argv[1]} could not be read:\n\n{exc}\n\nStarting empty.")
    # plate and focusing optic are confirmed at every start
    setup = ask_setup(session.layout.plate)
    if setup is None:
        return 0
    session.layout.plate, optic = setup
    win = MainWindow(session, optic=optic)
    win._path = path
    win.show()
    return exec_app(app)
