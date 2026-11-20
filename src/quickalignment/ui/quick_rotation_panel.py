"""Quick sample rotation (without pre-setup): a sample found on the beam and in focus, nothing else known.

For a user who skipped the earlier steps (no photo, samples not placed on the plate): only the stage positions and
the optic position (ZPS / CPS) at which the sample is in focus are entered. The working distance of the optic is
fixed, so with the optics reference of the configuration in use the optic position tells where along the beam the
focus is; that point, brought back to the plate frame with the stage model of the configuration, is where the
sample is: its plate position x, y and height H (stage.focus_point). The new position after a rotation is computed
about it (rotation.relocate with `point`).

The tab stands on its own: it reads the configuration in use and the plate mounted, and nothing else (no samples of
the Samples tab, no "Fine tunings by ZPS/CPS" plate offset); it changes nothing in the other tabs.

Step 4, as in the Rotate sample tab: the sample found at the new position with the piezo off centre gives the
ST / SZ / SN and the optic that show it with the piezo centred (piezo_box.PiezoBox, without "Send to Stage").
"""

from __future__ import annotations

from ._qt import QtCore, QtWidgets
from .piezo_box import PiezoBox
from .stage_panel import FOCUS_WARNING, MOTOR_SPECS, TRAVEL, MotorForm, align_labels, out_of_range, set_range, spin
from ..alignment.rotation import relocate
from ..core.geometry import SampleLayout
from ..core.stage import StageModel, focus_point

Qt = QtCore.Qt

BOX_STYLE = "font-size: 13px; padding: 6px; background: #f6f6f6; border: 1px solid #ddd;"
COLLISION_STYLE = "<br><span style='color:#b00'><b>Collision: the plate would touch {}.</b></span>"
MAX_HEIGHT = 20.0  # mm: a point at the optic focus higher than this above the plate surface is not a sample


class QuickRotationPanel(QtWidgets.QWidget):
    def __init__(self, stage_panel, plate_getter, parent=None):
        """`stage_panel`: only read (configuration in use, anti-collision check); `plate_getter`: the plate mounted."""
        super().__init__(parent)
        self.stage = stage_panel
        self._plate_getter = plate_getter
        self.located = None  # plate point (u, v, w) at the optic focus
        self.result = None  # SN kept
        self.corrected = None  # SN corrected

        self.about = about = QtWidgets.QLabel(
            "<b>For a sample found on the beam without any preparation</b> (no photo, samples not placed in the "
            "Samples tab). Enter the stage positions and the optic position at which the sample is in focus, and "
            "the wanted angles.<br><br>"
            "<b>How it is computed (an estimate):</b> the working distance of the zone plate / capillary does not "
            "change, so the optic position in focus tells where along the beam the sample is. With the optics "
            "reference and the stage model of the <b>configuration in use</b> (the configuration file made earlier) "
            "this gives where the sample is on the plate (x, y) and its height H above the plate surface, and the "
            "rotation is computed about that point.<br>"
            "It is only as good as the configuration: its optics reference (optic position ↔ focus) and its stage "
            "constants (ST0, SZ0, SN_f, rotation axes). An error δ of the optics reference moves the point by δ "
            "along the beam (H and the plate position both change). Check the sample on the camera / spectrum at "
            "the new position.<br>"
            "This tab uses nothing from the other tabs (no samples, no “Fine tunings by ZPS/CPS” corrections) and changes "
            "nothing there.")
        about.setWordWrap(True)
        about.setTextFormat(Qt.RichText)
        about.setStyleSheet("padding: 6px; background: #eef4fb; border: 1px solid #c8d8ea;")
        self.config_label = QtWidgets.QLabel()
        self.config_label.setWordWrap(True)

        # -- 1. current position -------------------------------------------------------
        self.measured = MotorForm()
        self.optic_label = QtWidgets.QLabel()
        self.measured_optic = spin(0.0, -10000, 10000, 4, 0.01)
        self.measured_optic.setToolTip("Optic position (ZPS / CPS) at which the beam is in focus on the sample now.")
        self.stage.optic_type.currentTextChanged.connect(self.update_optic)
        now_box = QtWidgets.QGroupBox("1. Current position (sample on the beam, in focus)")
        nb = QtWidgets.QVBoxLayout(now_box)
        nb.addWidget(self.measured)
        of = QtWidgets.QFormLayout()
        of.addRow(self.optic_label, self.measured_optic)
        nb.addLayout(of)

        # -- 2. wanted angles ------------------------------------------------------------
        self.new_srn = spin(120.0, *MOTOR_SPECS["srn"][1:])
        self.new_srz = spin(0.0, *MOTOR_SPECS["srz"][1:])
        compute_btn = QtWidgets.QPushButton("Locate the sample and compute the new position")
        compute_btn.setMinimumHeight(34)
        compute_btn.setStyleSheet("font-weight: bold;")
        compute_btn.clicked.connect(self.compute)
        goal_box = QtWidgets.QGroupBox("2. Wanted angles")
        gf = QtWidgets.QFormLayout(goal_box)
        gf.addRow("SRn", self.new_srn)
        gf.addRow("SRz", self.new_srz)
        gf.addRow(compute_btn)

        # -- 3. result ---------------------------------------------------------------------
        self.locate_label = QtWidgets.QLabel()
        self.locate_label.setWordWrap(True)
        self.locate_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.locate_label.setStyleSheet(BOX_STYLE)
        self.result_label = QtWidgets.QLabel()
        self.result_label.setWordWrap(True)
        self.result_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.result_label.setStyleSheet(BOX_STYLE)
        self.focus_label = QtWidgets.QLabel()
        self.focus_label.setWordWrap(True)
        self.correct_sn = QtWidgets.QCheckBox("Correct SN (put the sample on the analyzer focus)")
        self.correct_sn.setToolTip("Off (default): SN stays, ST / SZ keep the sample on the beam, the optic refocuses.\n"
                                   "On: SN, ST, SZ and the optic move so the sample is on the analyzer focus.")
        self.correct_sn.toggled.connect(self._show)
        self.corrected_label = QtWidgets.QLabel()
        self.corrected_label.setWordWrap(True)
        self.corrected_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.corrected_label.setStyleSheet(BOX_STYLE)
        res_box = QtWidgets.QGroupBox("3. Where the sample is, and the new position")
        rb = QtWidgets.QVBoxLayout(res_box)
        for w in (self.locate_label, self.result_label, self.focus_label, self.correct_sn, self.corrected_label):
            rb.addWidget(w)
        # -- 4. found off the piezo centre (nothing is sent to the Stage tab: this tab stays on its own) ----
        self.piezo = PiezoBox("4. Sample seen off the piezo centre at the new position?", self.chosen, self.model,
                              self.stage.calibration, self.optic_name, self._move_collisions)
        self.correct_sn.toggled.connect(lambda *_: self.piezo.reset())

        align_labels(self.measured, of, gf)
        left = QtWidgets.QWidget()
        lv = QtWidgets.QVBoxLayout(left)
        for w in (now_box, goal_box):
            lv.addWidget(w)
        lv.addStretch(1)
        right = QtWidgets.QWidget()
        rv = QtWidgets.QVBoxLayout(right)
        rv.addWidget(res_box)
        rv.addWidget(self.piezo)
        rv.addStretch(1)
        splitter = QtWidgets.QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([560, 700])
        box = QtWidgets.QVBoxLayout(self)
        box.setContentsMargins(4, 4, 4, 4)
        box.addWidget(about)
        box.addWidget(self.config_label)
        box.addWidget(splitter, 1)
        self.update_optic()
        self._show()

    # -- configuration in use -----------------------------------------------------------------
    def optic_name(self) -> str:
        return self.stage.record.optic_name

    def model(self) -> StageModel:
        """Stage model of the configuration in use for the plate mounted (no "Fine tunings by ZPS/CPS" plate offset)."""
        plate = self._plate_getter()
        return StageModel(self.stage.record.config_for(plate.key), plate)

    def update_optic(self, *_) -> None:
        """Name the optic field after the optic of the configuration in use; say which configuration is used."""
        name = self.optic_name()
        self.optic_label.setText(f"{name[0].upper()}{name[1:]} position")
        self.piezo.update_optic()
        record, plate = self.stage.record, self._plate_getter()
        optics = record.optics
        if optics.enabled:
            m = optics.motors
            ref = (f"in focus at {name} position {optics.optic_position:.4f} on a surface at plate height "
                   f"{optics.surface_w:.3f} mm with ST {m.st:.4f}, SZ {m.sz:.4f}, SN {m.sn:.4f}, SRn {m.srn:.3f}, "
                   f"SRz {m.srz:.3f}")
        else:
            ref = f"in focus on the analyzer focus at {name} position {optics.optic_position:.4f}"
        self.config_label.setText(f"Configuration in use: <b>{record.label}</b>, plate mounted: <b>{plate.name}</b>. "
                                  f"Optics reference: {ref}.")

    def showEvent(self, event) -> None:  # the configuration or the plate may have changed
        self.update_optic()
        super().showEvent(event)

    def apply_limits(self) -> None:
        self.measured.apply_limits()
        self.piezo.apply_limits()
        set_range(self.new_srn, "srn")
        set_range(self.new_srz, "srz")

    # -- computation -----------------------------------------------------------------------
    def locate(self) -> tuple[float, float, float]:
        """Plate point (u, v, w) at the optic focus; ValueError if it cannot be a sample on the plate."""
        model, m = self.model(), self.measured.value()
        u, v, w = (float(x) for x in focus_point(model, m, self.stage.calibration(), self.measured_optic.value()))
        plate = model.plate
        h = w - plate.total_thickness
        if abs(u) > plate.width / 2 or abs(v) > plate.height / 2:
            where = f"outside the plate (x = {u:.2f}, y = {v:.2f} mm)"
        elif not -0.05 <= h <= MAX_HEIGHT:
            where = f"{h:.2f} mm above the plate surface"
        else:
            return u, v, w
        raise ValueError(f"The optic focus is {where}: check the positions and the {self.optic_name()} position, "
                         "and that the configuration in use (optics reference) is the right one.")

    def compute(self) -> None:
        self.located = self.result = self.corrected = None
        try:
            self.located = self.locate()
            model, m = self.model(), self.measured.value()
            args = (model, SampleLayout(plate=model.plate), m, self.new_srn.value(), self.new_srz.value(),
                    self.stage.calibration(), self.measured_optic.value())
            common = dict(recentre_piezo=True, point=self.located)
            self.result = relocate(*args, keep_sn=True, **common)
            self.corrected = relocate(*args, to_analyzer_focus=True, limits=TRAVEL, **common)
        except ValueError as exc:
            self.result = self.corrected = None
            self.locate_label.setText(f"<span style='color:#b00'><b>{exc}</b></span>")
            self._show()
            self.piezo.reset()
            return
        self.correct_sn.blockSignals(True)
        self.correct_sn.setChecked(False)
        self.correct_sn.blockSignals(False)
        self._show()
        self.piezo.reset()

    def _table(self, r, names) -> str:
        rows = []
        for name in names:
            label, *_, suffix = MOTOR_SPECS[name]
            fmt = ".3f" if name in ("srn", "srz") else ".4f"
            a, b = getattr(r.measured, name), getattr(r.new, name)
            rows.append((label, f"{a:{fmt}}", f"<b>{b:{fmt}}</b>", f"{b - a:+{fmt}}", suffix.strip()))
        if r.optic_new is not None:
            a = self.measured_optic.value()
            rows.append((self.optic_name(), f"{a:.4f}", f"<b>{r.optic_new:.4f}</b>", f"{r.optic_new - a:+.4f}", ""))
        body = "".join(f"<tr><td>{a}</td><td align=right>{b}</td><td align=right>{c}</td><td align=right>{d}</td>"
                       f"<td>{u}</td></tr>" for a, b, c, d, u in rows)
        return (f"<table cellspacing=0 cellpadding=3><tr><th></th><th>now</th><th>new</th><th>Δ</th><th></th></tr>"
                f"{body}</table>")

    def _show(self, *_) -> None:
        r = self.result
        self.corrected_label.setVisible(r is not None and self.correct_sn.isChecked())
        self.result_label.setVisible(r is not None)
        self.focus_label.setVisible(r is not None)
        self.correct_sn.setVisible(r is not None)
        if r is None:
            if self.located is None and not self.locate_label.text():
                self.locate_label.setText("Enter the current position, the optic position and the wanted angles, "
                                          "then press “Locate the sample and compute the new position”.")
            return
        u, v, w = self.located
        h = w - self._plate_getter().total_thickness
        self.locate_label.setText(
            f"Estimated from the optic focus: the sample is at plate <b>x = {u:.3f} mm, y = {v:.3f} mm</b>, "
            f"height <b>H = {h:.3f} mm</b> above the plate surface (plate frame: origin at the centre of the back "
            "plate, x along the plate width, y towards the tab).")
        pi = self.model().config.pi_center
        bad = out_of_range(r.new)
        self.result_label.setText(
            f"At SRn = {r.new.srn:.3f}°, SRz = {r.new.srz:.3f}°, PIX = PIY = {pi:g} µm, SN kept:"
            + self._table(r, ("st", "sz", "sn"))
            + (f"<span style='color:#b00'><b>Out of range: {', '.join(bad)}</b> — not reachable with SN kept, "
               "use the corrected solution.</span>" if bad else "")
            + self._collision_text(r))
        y = r.beam_offset
        side = "" if abs(y) < 1e-6 else f" {'downstream' if y > 0 else 'upstream'}"
        text = (f"With SN kept the sample is {r.focus_distance * 1000:.0f} µm{side} from the analyzer focus "
                f"(now: {r.measured_focus_distance * 1000:.0f} µm); the optic refocuses on it.")
        if abs(y) >= 1e-6:
            text += f" Removing it would take ΔSN ≈ {-y / 2 ** 0.5:+.4f} mm (ST compensating)."
        if r.focus_distance > FOCUS_WARNING:
            text = (f"<span style='color:#b00'><b>{text}</b> Too far from the analyzer focus, the data would be "
                    "distorted: correct SN?</span>")
        else:
            text = f"<span style='color:#207020'>{text} Close enough: no SN correction needed.</span>"
        self.focus_label.setText(text)
        c = self.corrected
        if c.focus_distance < 1e-4:
            where = "on the analyzer focus"
        else:
            where = (f"<span style='color:#b00'><b>closest reachable position: {c.focus_distance * 1000:.0f} µm "
                     "from the analyzer focus</b> (motor range)</span>")
        self.corrected_label.setText(f"With SN corrected, the sample is {where}:"
                                     + self._table(c, ("st", "sz", "sn")) + self._collision_text(c))

    def _move_collisions(self, new, optic_new, optic_now) -> str:
        """Anti-collision check of the configuration in use (plate and optic; read only)."""
        return self.stage.move_collisions(new, optic_new, optic_now)

    def _collision_text(self, r) -> str:
        hits = self._move_collisions(r.new, r.optic_new, self.measured_optic.value())
        return COLLISION_STYLE.format(hits) if hits else ""

    def chosen(self):
        return self.corrected if self.correct_sn.isChecked() else self.result
