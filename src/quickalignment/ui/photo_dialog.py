"""Samples from a photo: the plate photographed from above (sample side).

1. open the photo
2. click on it the four corners of the sample area in the order of the
   numbers shown in the right view (the next one in red); drag them to refine
3. the photo is mapped onto the plate model (right view); the user draws a box
   on each sample there (on by default), deletes wrong ones, merges pieces
4. enter the sample height H (not visible on a photo from above)
5. optionally (step 2) locate devices on a second photo, matched to the plate
   photo by points the user marks on both (device_match.py)
6. add the samples (with their devices) to the plate

Finding the samples by their colour (alignment.photo.detect_samples) is left to
the assistant (align_detect_samples); this window only has the drawn boxes.
The boxes are a starting point: they can be moved / resized in the Samples
tab like drawn ones, and "Fine tunings by ZPS/CPS" corrects the positions later.
"""

from __future__ import annotations

import math

import numpy as np

from ._qt import QtCore, QtGui, QtWidgets
from .device_match import DeviceMatchPanel, container
from .photo_cache import PLATE, photo_cache
from .photo_widgets import STEP_COLORS, PhotoRegistration, color_tabs, step_style
from .plate_editor import COLOR_SAMPLE, cosmetic_pen
from ..core.geometry import Device, PlateGeometry, Sample
from ..alignment.photo import PX_PER_MM, Detection, overlap, plate_view_bounds

Qt = QtCore.Qt

COLOR_FOUND = QtGui.QColor("#18c418")
RESULT_COLUMNS = ["Name", "x (mm)", "y (mm)", "L (mm)", "W (mm)", "H (mm)", "Devices"]
NAME, H_COL, DEV_COL = 0, 5, 6
SAME_BOX = 0.5  # boxes overlapping more than this (intersection over union) are the same sample
DRAW_STEP = 0.05  # mm, drawn boxes are rounded to this


class PhotoImportDialog(QtWidgets.QDialog):
    def __init__(self, plate: PlateGeometry, default_height: float, existing: list[str] | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Samples from a photo")
        self.resize(1400, 920)
        self.plate = plate
        self.existing = list(existing or [])
        self.source: str | None = None  # file of the plate photo (to remember it with its points)
        self.manual: list[Detection] = []  # drawn or merged by the user
        self.detections: list[Detection] = []  # shown (the drawn boxes, once the photo is registered)
        self._plate_overlay: list[QtWidgets.QGraphicsItem] = []
        self._filling = False

        self.reg = PhotoRegistration(plate, plate.riser_bounds(), "the sample area", plate_view_bounds(plate),
                                     PX_PER_MM)
        self.reg.photo_title.setText("<b>Photo</b> from above (sample side)")
        self.reg.changed.connect(self._on_registration)
        self.reg.plateClicked.connect(self._on_plate_click)
        self.reg.plateDragged.connect(self._on_plate_drag)
        self.reg.cursor_text = self._cursor_text

        open_btn = QtWidgets.QPushButton("Open photo…")
        open_btn.clicked.connect(self.open_photo)
        self.recent = QtWidgets.QComboBox()
        self.recent.setToolTip("Plate photos already used while the program runs (kept until it exits), with the "
                               "points clicked on them")
        self.recent.activated.connect(self._on_recent)
        self._fill_recent()
        undo_btn = QtWidgets.QPushButton("Undo last point")
        undo_btn.setToolTip("Remove the last point clicked on the photo (Ctrl+Z); the others stay")
        undo_btn.clicked.connect(lambda: self.reg.undo_corner())
        QtWidgets.QShortcut(QtGui.QKeySequence.Undo, self.reg, self.reg.undo_corner)
        reset_btn = QtWidgets.QPushButton("Clear all points")
        reset_btn.setToolTip("Remove all the points clicked on the photo and start again")
        reset_btn.clicked.connect(lambda: self.reg.clear_corners())
        self.use_3d = QtWidgets.QCheckBox("3D correction")
        self.use_3d.setChecked(False)
        self.use_3d.setToolTip("For a photo not taken from straight above: click 8 points at two heights (the 4 "
                               "sample-area corners on the riser, 2 top corners of the back plate, 2 top corners of "
                               "the tab).\nA camera model then corrects the perspective at every height. Off: the 4 "
                               "sample-area corners only (enough for a photo from about straight above).")
        self.use_3d.toggled.connect(self._on_3d)
        self.file_label = QtWidgets.QLabel("no photo")
        self.file_label.setStyleSheet("color: #555;")
        self.instruction = QtWidgets.QLabel()
        self.instruction.setWordWrap(True)

        # a drag in the right view draws a sample box (on by default); off: the plate model is only looked at
        self.draw_btn = QtWidgets.QPushButton("Draw box on plate model (right side)")
        self.draw_btn.setToolTip("Drag in the right view (plate model) to draw a box on a sample / substrate.\n"
                                 "A click selects a box (Ctrl + click: several).")
        self.draw_btn.setCheckable(True)
        self.draw_btn.setChecked(True)
        self.draw_btn.toggled.connect(self._on_tool_toggled)

        self.height_box = QtWidgets.QDoubleSpinBox()
        self.height_box.setRange(0.0, 20.0)
        self.height_box.setDecimals(3)
        self.height_box.setSingleStep(0.1)
        self.height_box.setSuffix(" mm")
        self.height_box.setValue(default_height)
        self.height_box.setToolTip("Sample height H above the plate surface: it cannot be seen on a photo from "
                                   "above.\nIt can be changed per sample in the table.")
        height_all = QtWidgets.QPushButton("Set H of all")
        height_all.clicked.connect(self.set_height_of_all)

        self.table = QtWidgets.QTableWidget(0, len(RESULT_COLUMNS))
        self.table.setHorizontalHeaderLabels(RESULT_COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeaderItem(DEV_COL).setToolTip("Devices located on it in step 2")
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setMinimumHeight(130)
        self.table.itemChanged.connect(self._on_table_changed)
        self.table.itemSelectionChanged.connect(self._on_selection)
        merge_btn = QtWidgets.QPushButton("Merge selected")
        merge_btn.setToolTip("One sample from the selected boxes (pieces of a sample broken up by paint or wires).\n"
                             "Select boxes by clicking them (Ctrl + click: several) or their rows.")
        merge_btn.clicked.connect(self.merge_selected)
        delete_btn = QtWidgets.QPushButton("Delete selected")
        delete_btn.setToolTip("Remove the selected boxes (also with the Delete key)")
        delete_btn.clicked.connect(self.delete_selected)
        undo_btn = QtWidgets.QPushButton("Remove all boxes")
        undo_btn.setToolTip("Remove all the boxes drawn on this photo and start again")
        undo_btn.clicked.connect(self.undo_edits)
        QtWidgets.QShortcut(QtGui.QKeySequence(Qt.Key_Delete), self.table, self.delete_selected)

        self.replace = QtWidgets.QCheckBox("Remove the samples already on the plate")
        self.replace.setVisible(bool(self.existing))
        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)
        self.add_btn = QtWidgets.QPushButton("Add to plate")
        self.add_btn.setStyleSheet("font-weight: bold;")
        self.add_btn.setEnabled(False)
        self.add_btn.setAutoDefault(False)
        self.add_btn.clicked.connect(self.accept)
        cancel = QtWidgets.QPushButton("Cancel")
        cancel.setAutoDefault(False)
        cancel.clicked.connect(self.reject)

        self.devices_panel = DeviceMatchPanel()
        self.devices_panel.changed.connect(self._on_devices_changed)

        top = QtWidgets.QHBoxLayout()
        top.addWidget(open_btn)
        top.addWidget(self.recent)
        top.addWidget(undo_btn)
        top.addWidget(reset_btn)
        top.addWidget(self.use_3d)
        top.addWidget(self.file_label, 1)
        params = QtWidgets.QHBoxLayout()
        params.addWidget(self.draw_btn)
        params.addStretch(1)

        height_row = QtWidgets.QHBoxLayout()
        height_row.addWidget(QtWidgets.QLabel("<b>Samples</b> (all are added)   height H"))
        height_row.addWidget(self.height_box)
        height_row.addWidget(height_all)
        note = QtWidgets.QLabel("(not visible from above; Si wafer substrate 0.525 mm)")
        note.setStyleSheet("color: #555;")
        height_row.addWidget(note)
        height_row.addStretch(1)
        for b in (merge_btn, delete_btn, undo_btn):
            height_row.addWidget(b)
        bottom = QtWidgets.QHBoxLayout()
        bottom.addWidget(self.replace)
        bottom.addStretch(1)
        bottom.addWidget(self.add_btn)
        bottom.addWidget(cancel)

        lower = QtWidgets.QVBoxLayout()
        lower.setContentsMargins(0, 0, 0, 0)
        lower.addLayout(height_row)
        lower.addWidget(self.table, 1)
        lower.addWidget(self.status)
        lower_w = QtWidgets.QWidget()
        lower_w.setLayout(lower)
        split = QtWidgets.QSplitter(Qt.Vertical)
        split.addWidget(self.reg)
        split.addWidget(lower_w)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)

        tab1 = QtWidgets.QWidget()
        t1 = QtWidgets.QVBoxLayout(tab1)
        t1.addLayout(top)
        t1.addLayout(params)
        t1.addWidget(split, 1)
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.addTab(tab1, "Step 1  Plate photo → samples")
        self.tabs.addTab(self.devices_panel, "Step 2  Devices (second photo)")
        color_tabs(self.tabs)
        self.tabs.currentChanged.connect(lambda _: self._update_instruction())

        box = QtWidgets.QVBoxLayout(self)
        box.addWidget(self.instruction)
        box.addWidget(self.tabs, 1)
        box.addLayout(bottom)
        self._on_tool_toggled(True)
        self._rebuild([], [])

    # -- photo ---------------------------------------------------------------------
    @property
    def rectified(self):
        return self.reg.rectified

    def open_photo(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open plate photo", "",
                                                        "Images (*.jpg *.jpeg *.png *.bmp *.tif *.tiff)")
        if path:
            self.load_photo(path)

    def load_photo(self, path: str, remember: bool = True) -> bool:
        if not self.reg.load_photo(path):
            return False
        self.file_label.setText(path)
        self.source = path
        if remember:
            photo_cache().add(PLATE, path)
            self._fill_recent()
        return True

    def _fill_recent(self) -> None:
        photos = photo_cache().of_kind(PLATE, self.plate.key)
        self.recent.blockSignals(True)
        self.recent.clear()
        self.recent.addItem("recent photos…" if photos else "no recent photo")
        for c in photos:
            self.recent.addItem(c.label, c)
        self.recent.setEnabled(bool(photos))
        self.recent.blockSignals(False)

    def load_recent(self, c) -> bool:
        """A photo used earlier in this run, with the points clicked on it then (when they were kept)."""
        if not self.reg.load_photo(str(c.path)):
            return False
        self.source = c.source
        self.file_label.setText(f"{c.source} (kept copy)")
        if c.corners and c.plate == self.plate.key:
            if self.use_3d.isChecked() != c.use_3d:
                self.use_3d.setChecked(c.use_3d)
            self.reg.set_corners(c.corners)
        return True

    def _on_recent(self, index: int) -> None:
        c = self.recent.itemData(index)
        if c is not None:
            self.load_recent(c)
        self.recent.setCurrentIndex(0)

    def remember(self) -> None:
        """Keep the photo with its points for this run (Device from photo, From photo again)."""
        if self.source and self.reg.photo is not None:
            photo_cache().remember_registration(self.source, self.plate.key, self.reg.corner_positions(),
                                                self.reg.use_3d, self.reg.h)

    def done(self, result: int) -> None:
        self.remember()  # also on Cancel: the points clicked are not lost
        super().done(result)

    def set_photo(self, rgb: np.ndarray) -> None:
        self.reg.set_photo(rgb)

    def set_corners(self, points) -> None:
        self.reg.set_corners(points)

    def _on_3d(self, on: bool) -> None:
        self.reg.set_3d(on)
        self._update_instruction()

    def _on_registration(self) -> None:
        self.devices_panel.set_source(self.reg.photo, self.reg.h)
        self._rebuild(self.detections, self._row_states())
        self._update_instruction()

    def _update_instruction(self, error: str = "") -> None:
        if self.tabs.currentIndex() == 1:
            self.instruction.setStyleSheet(step_style(self.devices_panel.step()))
            self.instruction.setText(self.devices_panel.instruction())
            return
        error = error or self.reg.error
        text = self.reg.corner_instruction()
        if self.reg.photo is None:
            text = "Open a photo of the plate taken from straight above (sample side, whole sample area visible)."
        elif text is None and error:
            text = error
        elif text is None:
            text = ("Check that the plate model (blue) lies on the plate; drag the points to refine. "
                    + ("Drag in the right view (plate model) to draw a box on each sample / substrate; "
                       if self.draw_btn.isChecked() else "Press “Draw box on plate model” to draw sample boxes; ")
                    + "click a box to select it, then Merge or Delete.")
            if self.reg.camera is not None:
                text += f" 3D correction: the points fit the camera model within {self.reg.camera_rms:.1f} px (rms)."
        if not (error and text == error):
            text = "Step 1: " + text
        color = "#c00000" if error and text == error else STEP_COLORS[0]
        self.instruction.setStyleSheet(f"font-weight: bold; color: {color};")
        self.instruction.setText(text)

    # -- tools (what a click does) --------------------------------------------------
    def _on_tool_toggled(self, _on: bool = True) -> None:
        draw = self.draw_btn.isChecked()
        self.reg.plate_view.drag_enabled = draw
        self.reg.plate_view.viewport().setCursor(Qt.CrossCursor if draw else Qt.ArrowCursor)
        self._update_instruction()

    def _on_plate_click(self, u: float, v: float) -> None:
        if self.rectified is not None:
            self.select_at(u, v)

    def _on_plate_drag(self, u0: float, v0: float, u1: float, v1: float) -> None:
        if self.draw_btn.isChecked():
            self.add_box(u0, v0, u1, v1)

    def _cursor_text(self, u: float, v: float) -> str:
        for row, d in enumerate(self.detections):
            if d.u0 <= u <= d.u1 and d.v0 <= v <= d.v1:
                return f"in {self._name(row)}"
        return ""

    # -- boxes ---------------------------------------------------------------------
    def _rebuild(self, old_detections: list[Detection], old_states: list) -> None:
        """Shown boxes = the drawn / merged ones (once the photo is registered); rows keep their name / H by box
        overlap."""
        self.detections = [] if self.rectified is None else list(self.manual)
        states, taken = [], set()
        for d in self.detections:
            free = [i for i in range(len(old_detections)) if i not in taken]
            best = max(free, key=lambda i: overlap(d.rect, old_detections[i].rect), default=None)
            ok = best is not None and overlap(d.rect, old_detections[best].rect) > SAME_BOX
            states.append(old_states[best] if ok else None)
            if ok:
                taken.add(best)
        self._fill_table(states)
        self._update_substrates()
        self._draw_detections()

    def _draw_detections(self) -> None:
        for it in self._plate_overlay:
            self.reg.plate_scene.removeItem(it)
        self._plate_overlay = []
        selected = self._selected_rows()
        shapes = []
        for row, d in enumerate(self.detections):
            pen = cosmetic_pen(COLOR_FOUND, 3 if row in selected else 1.8)
            item = self.reg.plate_scene.addRect(QtCore.QRectF(d.u0, -d.v1, d.u1 - d.u0, d.v1 - d.v0), pen,
                                                QtGui.QBrush(COLOR_SAMPLE if row in selected else Qt.NoBrush))
            item.setZValue(9)
            item.setAcceptedMouseButtons(Qt.NoButton)
            label = self.reg.plate_scene.addSimpleText(self._name(row))
            label.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
            label.setBrush(QtGui.QBrush(QtGui.QColor("#0a6a0a")))
            label.setPos(d.u0, -d.v1)
            label.setZValue(9)
            label.setAcceptedMouseButtons(Qt.NoButton)
            self._plate_overlay += [item, label]
            shapes.append(([(d.u0, d.v0), (d.u1, d.v0), (d.u1, d.v1), (d.u0, d.v1)], COLOR_FOUND,
                           3 if row in selected else 2))
        for dev in self.devices_panel.devices:
            dot = self.reg.plate_scene.addEllipse(-4, -4, 8, 8, cosmetic_pen("#e00000", 2))
            dot.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
            dot.setPos(dev.u, -dev.v)
            dot.setZValue(10)
            dot.setToolTip(dev.name)
            dot.setAcceptedMouseButtons(Qt.NoButton)
            self._plate_overlay.append(dot)
        self.reg.set_photo_overlay(shapes)
        n = len(self.detections)
        self.add_btn.setEnabled(n > 0)
        if self.rectified is None:
            self.status.setText("")
        else:
            self.status.setText(f"{n} sample(s) to add, {len(self.devices_panel.devices)} device(s). Click a box to "
                                "select it (Ctrl + click: several), then Merge or Delete. Positions can be refined "
                                "afterwards in the Samples tab.")

    # -- hand edits ----------------------------------------------------------------
    def add_box(self, u0: float, v0: float, u1: float, v1: float) -> Detection | None:
        """A sample drawn by hand (plate rectangle)."""
        u0, v0, u1, v1 = (round(x / DRAW_STEP) * DRAW_STEP for x in (u0, v0, u1, v1))
        if u1 - u0 < DRAW_STEP or v1 - v0 < DRAW_STEP:
            return None
        d = Detection(u0, v0, u1, v1, (u1 - u0) * (v1 - v0), math.nan, manual=True)
        old = (self.detections, self._row_states())
        self.manual.append(d)
        self._rebuild(*old)
        self._select_row(self.detections.index(d))
        return d

    def _remove(self, parts: list[Detection]) -> None:
        for d in parts:
            self.manual.remove(d)

    def merge_selected(self) -> None:
        rows = self._selected_rows()
        if len(rows) < 2:
            QtWidgets.QMessageBox.information(self, "Merge", "Select the rows (or boxes) of the pieces to merge "
                                              "(Ctrl + click).")
            return
        old = (self.detections, self._row_states())
        parts = [self.detections[r] for r in rows]
        merged = Detection.merged(parts)
        self._remove(parts)
        self.manual.append(merged)
        # the merged box keeps the name of its first piece
        states = list(old[1])
        self._rebuild(old[0] + [merged], states + [states[rows[0]]])
        self._select_row(self.detections.index(merged))

    def delete_selected(self) -> None:
        rows = self._selected_rows()
        if not rows:
            return
        old = (self.detections, self._row_states())
        self._remove([self.detections[r] for r in rows])
        self._rebuild(*old)

    def undo_edits(self) -> None:
        """Remove all the boxes."""
        old = (self.detections, self._row_states())
        self.manual = []
        self._rebuild(*old)

    def select_at(self, u: float, v: float) -> None:
        """Select the (smallest) box under a click."""
        hits = [r for r, d in enumerate(self.detections) if d.u0 <= u <= d.u1 and d.v0 <= v <= d.v1]
        if not hits:
            self.table.clearSelection()
            return
        row = min(hits, key=lambda r: self.detections[r].size[0] * self.detections[r].size[1])
        if QtWidgets.QApplication.keyboardModifiers() & Qt.ControlModifier:
            self.table.selectionModel().select(self.table.model().index(row, 0),
                                               QtCore.QItemSelectionModel.Toggle | QtCore.QItemSelectionModel.Rows)
        else:
            self._select_row(row)

    def _select_row(self, row: int) -> None:
        self.table.clearSelection()
        self.table.selectRow(row)

    def _on_selection(self) -> None:
        rows = self._selected_rows()
        if len(rows) == 1:  # step 2 shows the selected substrate
            self.devices_panel.select_substrate(self._name(rows[0]))
        self._draw_detections()

    def _selected_rows(self) -> list[int]:
        return sorted({i.row() for i in self.table.selectedIndexes()})

    # -- results table ------------------------------------------------------------
    def _default_names(self, n: int, taken: set) -> list[str]:
        taken = taken | set(self.existing)
        names, i = [], 1
        while len(names) < n:
            if f"S{i}" not in taken:
                names.append(f"S{i}")
            i += 1
        return names

    def _row_states(self) -> list[tuple]:
        """(name, H) of the table rows."""
        return [(self.table.item(row, NAME).text(), self.table.item(row, H_COL).text())
                for row in range(self.table.rowCount())]

    def _fill_table(self, states: list) -> None:
        """Rows for the detections; states[row] (name, H) are kept where given (not None)."""
        self._filling = True
        self.table.setRowCount(len(self.detections))
        names = iter(self._default_names(sum(s is None for s in states), {s[0] for s in states if s}))
        for row, d in enumerate(self.detections):
            (u, v), (length, width) = d.center, d.size
            name, height = states[row] or (next(names), f"{self.height_box.value():.3f}")
            values = [name, f"{u:.2f}", f"{v:.2f}", f"{length:.2f}", f"{width:.2f}", height, ""]
            for col, text in enumerate(values):
                item = QtWidgets.QTableWidgetItem(text)
                if col not in (NAME, H_COL):
                    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.table.setItem(row, col, item)
        self._filling = False
        self._update_device_counts()

    def _on_table_changed(self, item) -> None:
        if self._filling:
            return
        if item.column() == NAME:
            self._update_substrates()
        if item.column() == H_COL:
            try:
                value = float(item.text())
                ok = 0 <= value <= 20
            except ValueError:
                ok = False
            self._filling = True
            item.setText(f"{value:.3f}" if ok else f"{self.height_box.value():.3f}")
            self._filling = False
        self._draw_detections()

    def _name(self, row: int) -> str:
        item = self.table.item(row, NAME)
        return item.text().strip() if item is not None else ""

    def set_height_of_all(self) -> None:
        self._filling = True
        for row in range(self.table.rowCount()):
            self.table.item(row, H_COL).setText(f"{self.height_box.value():.3f}")
        self._filling = False

    # -- result ------------------------------------------------------------------
    # -- devices (step 2) ---------------------------------------------------------
    def _substrates(self) -> list[tuple[str, tuple]]:
        return [(self._name(row), d.rect) for row, d in enumerate(self.detections)]

    def _update_substrates(self) -> None:
        self.devices_panel.set_substrates(self._substrates())

    def _devices_of(self, row: int) -> list:
        subs = self._substrates()
        return [d for d in self.devices_panel.devices if (c := container(subs, d.u, d.v)) and c[0] == subs[row][0]]

    def _update_device_counts(self) -> None:
        self._filling = True
        for row in range(self.table.rowCount()):
            n = len(self._devices_of(row))
            self.table.item(row, DEV_COL).setText(str(n) if n else "")
        self._filling = False

    def _on_devices_changed(self) -> None:
        self._update_device_counts()
        self._draw_detections()
        self._update_instruction()

    # -- result ------------------------------------------------------------------
    def samples(self) -> list[Sample]:
        """The samples with their devices (names may still clash with existing ones: the editor makes them
        unique). Devices not on a sample are left out."""
        out = []
        for row, d in enumerate(self.detections):
            (u, v), (length, width) = d.center, d.size
            s = Sample(self._name(row), u=round(u, 3), v=round(v, 3), length=round(length, 3),
                       width=round(width, 3), height=float(self.table.item(row, H_COL).text()))
            for p in self._devices_of(row):
                dev = Device(p.name)
                dev.set_position(s, round(p.u, 3), round(p.v, 3))
                s.devices.append(dev)
            out.append(s)
        return out

    def replace_existing(self) -> bool:
        return self.replace.isVisible() and self.replace.isChecked()
