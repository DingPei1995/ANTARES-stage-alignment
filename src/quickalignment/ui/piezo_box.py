"""Step "sample seen off the piezo centre" of the rotation tabs (Rotate sample, Quick sample rotation).

At the new position the sample is found with the piezo moved away from its centre: the PIX / PIY where it is seen
(and the optic position in focus there) give the ST / SZ (SN kept) and the optic that show it with the piezo centred
(rotation.recentre_piezo; the rotations do not change).
"""

from __future__ import annotations

from dataclasses import replace

from ._qt import QtCore, QtWidgets
from .stage_panel import MOTOR_SPECS, out_of_range, set_range, spin
from ..alignment.rotation import recentre_piezo

Qt = QtCore.Qt

COLLISION_STYLE = "<br><span style='color:#b00'><b>Collision: the plate would touch {}.</b></span>"


class PiezoBox(QtWidgets.QGroupBox):
    def __init__(self, title: str, chosen, model, optics, optic_name, collisions, send=None, parent=None):
        """`chosen()`: the relocation shown in the tab (or None); `model()`, `optics()`: stage model and optics
        calibration in use; `optic_name()`; `collisions(new, optic_new, optic_now)`: what the plate would touch
        (empty: nothing); `send(new, optic)`: puts the corrected position in the Stage tab (None: no button)."""
        super().__init__(title, parent)
        self._chosen, self._model, self._optics = chosen, model, optics
        self._optic_name, self._collisions, self._send = optic_name, collisions, send
        self.result = None
        self.pix = spin(150.0, *MOTOR_SPECS["pix"][1:])
        self.piy = spin(150.0, *MOTOR_SPECS["piy"][1:])
        self.optic = spin(0.0, -10000, 10000, 4, 0.01)
        self.optic.setToolTip("Optic position at which the sample is in focus there.")
        self.optic_label = QtWidgets.QLabel()
        button = QtWidgets.QPushButton("Centre the piezo: correct ST / SZ / SN and the optic")
        button.clicked.connect(self.compute)
        self.label = QtWidgets.QLabel()
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.label.setStyleSheet("font-size: 13px; padding: 6px; background: #f6f6f6; border: 1px solid #ddd;")
        self.label.hide()
        self.send_button = QtWidgets.QPushButton("Send corrected position to Stage && Optics tab")
        self.send_button.clicked.connect(self.send)
        self.send_button.hide()

        box = QtWidgets.QVBoxLayout(self)
        intro = QtWidgets.QLabel(
            "If, at the new position above (the solution shown), the sample was found with the piezo moved away from "
            "PIX = PIY = 150 µm, enter where it is seen. ST / SZ / SN and the optic are corrected so that it is "
            "seen with the piezo centred (rotations unchanged).")
        intro.setWordWrap(True)
        box.addWidget(intro)
        form = QtWidgets.QFormLayout()
        form.addRow("PIX where the sample is seen", self.pix)
        form.addRow("PIY where the sample is seen", self.piy)
        form.addRow(self.optic_label, self.optic)
        box.addLayout(form)
        box.addWidget(button)
        box.addWidget(self.label)
        if send is not None:
            box.addWidget(self.send_button)
        self.update_optic()

    def update_optic(self) -> None:
        name = self._optic_name()
        self.optic_label.setText(f"{name[0].upper()}{name[1:]} position (in focus there)")

    def apply_limits(self) -> None:
        set_range(self.pix, "pix")
        set_range(self.piy, "piy")

    def reset(self) -> None:
        """A new position to start from: the piezo centred and the optic as computed, until the user enters more."""
        self.result = None
        self.label.hide()
        self.send_button.hide()
        r = self._chosen()
        if r is None:
            return
        pi = self._model().config.pi_center
        self.pix.setValue(pi)
        self.piy.setValue(pi)
        if r.optic_new is not None:
            self.optic.setValue(r.optic_new)

    def compute(self) -> None:
        r = self._chosen()
        if r is None:
            self.label.setText("<b>Compute the new position first.</b>")
            self.label.show()
            return
        found = replace(r.new, pix=self.pix.value(), piy=self.piy.value())
        p = self.result = recentre_piezo(self._model(), found, self.optic.value(), self._optics())
        rows = []
        for name in ("st", "sz", "sn", "pix", "piy"):
            label, *_, suffix = MOTOR_SPECS[name]
            fmt = ".2f" if name in ("pix", "piy") else ".4f"
            a, b = getattr(p.found, name), getattr(p.new, name)
            rows.append((label, f"{a:{fmt}}", f"<b>{b:{fmt}}</b>", f"{b - a:+{fmt}}", suffix.strip()))
        rows.append((self._optic_name(), f"{p.optic_found:.4f}", f"<b>{p.optic_new:.4f}</b>",
                     f"{p.optic_new - p.optic_found:+.4f}", ""))
        body = "".join(f"<tr><td>{a}</td><td align=right>{b}</td><td align=right>{c}</td><td align=right>{d}</td>"
                       f"<td>{u}</td></tr>" for a, b, c, d, u in rows)
        text = (f"At SRn = {p.new.srn:.3f}°, SRz = {p.new.srz:.3f}°, the sample is seen at PIX = PIY = "
                f"{p.new.pix:g} µm with SN kept:"
                f"<table cellspacing=0 cellpadding=3><tr><th></th><th>found</th><th>new</th><th>Δ</th><th></th></tr>"
                f"{body}</table>")
        s = p.same_point
        if abs(s.sn - p.new.sn) >= 5e-5:
            text += (f"The sample moves {p.beam_shift * 1000:.1f} µm along the beam, the optic refocuses. "
                     f"Or, to keep it exactly where it was found (optic unchanged): ST = {s.st:.4f}, "
                     f"SZ = {s.sz:.4f}, SN = {s.sn:.4f} mm.")
        else:
            text += "The sample stays where it was found: the optic does not move."
        bad = out_of_range(p.new)
        if bad:
            text += f"<br><span style='color:#b00'><b>Out of range: {', '.join(bad)}</b></span>"
        hits = self._collisions(p.new, p.optic_new, p.optic_found)
        if hits:
            text += COLLISION_STYLE.format(hits)
        self.label.setText(text)
        self.label.show()
        self.send_button.setVisible(self._send is not None)

    def send(self) -> None:
        p = self.result
        if p is None or self._send is None:
            return
        bad = out_of_range(p.new)
        if bad:
            QtWidgets.QMessageBox.warning(self, "Out of range", "Not reachable:\n" + "\n".join(bad))
            return
        hits = self._collisions(p.new, p.optic_new, p.optic_found)
        if hits:
            QtWidgets.QMessageBox.warning(self, "Collision", f"Not reachable: the plate would touch {hits}.")
            return
        self._send(p.new, p.optic_new)
