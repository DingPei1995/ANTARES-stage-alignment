"""Devices from a second photo, matched by points the user marks on both photos.

The photo of the plate shows where a substrate is, but usually not its
devices; a second, closer photo (microscope, camera) shows the devices but
often not the substrate edges. The user marks the same features (paint dots,
pattern corners, scratches …) on both: on the left a crop of the plate photo
around the substrate, already in plate coordinates, on the right the device
photo. From these point pairs (2: rotation + scale + shift, 3: affine, 4 or
more: perspective) the device photo is mapped onto the plate, and the devices
clicked on it get plate coordinates. Devices have no height: they are on the
surface of their substrate.

Devices can also be added to a substrate already on the plate (DeviceFromPhotoDialog, "Device from photo…" in the
Samples tab) without the plate photo: the left view then shows the substrate as drawn, and its corners and the devices
already placed are the reference points (clicks snap to them).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ._qt import QtCore, QtGui, QtWidgets, Signal
from .photo_cache import DEVICE, PLATE, photo_cache
from .photo_widgets import CornerItem, ZoomView, array_to_qimage, read_photo
from .plate_editor import cosmetic_pen
from ..core.geometry import Device, Rect, Sample
from ..alignment.photo import apply_homography, pair_transform, rectify

Qt = QtCore.Qt

COLOR_DEVICE = QtGui.QColor("#e00000")
COLOR_SUBSTRATE = QtGui.QColor("#ff8c00")
COLOR_FIXED = QtGui.QColor("#0060d0")  # devices already on the substrate (reference points)
COLUMNS = ["Device", "on", "x (mm)", "y (mm)", "dx from left (mm)", "dy from bottom (mm)", "Status"]
PAIRS, DEVICES = range(2)
TRANSFORM_KIND = {2: "rotation + scale + shift", 3: "affine"}
MAX_CROP_PX = 1600  # crop of the plate photo: at most this many pixels across
MAX_PX_PER_MM = 100.0
SNAP_PX = 12  # schematic view: a click this close (screen px) to a reference point snaps to it
SNAP_MAX = 0.05  # ... but at most this fraction of the substrate size


@dataclass
class DevicePoint:
    name: str
    u: float  # plate mm
    v: float
    px: tuple[float, float] | None = None  # on the current device photo (follows its matching); None: fixed


def crop_view(rect: Rect) -> tuple[Rect, float]:
    """Plate rectangle shown around a substrate, and its resolution (px / mm)."""
    u0, v0, u1, v1 = rect
    m = max(0.5, 0.3 * max(u1 - u0, v1 - v0))
    bounds = (u0 - m, v0 - m, u1 + m, v1 + m)
    return bounds, min(MAX_PX_PER_MM, MAX_CROP_PX / max(bounds[2] - bounds[0], bounds[3] - bounds[1]))


def container(substrates: list[tuple[str, Rect]], u: float, v: float) -> tuple[str, Rect] | None:
    """The (smallest) substrate holding the plate point."""
    hits = [(n, r) for n, r in substrates if r[0] <= u <= r[2] and r[1] <= v <= r[3]]
    return min(hits, key=lambda h: (h[1][2] - h[1][0]) * (h[1][3] - h[1][1]), default=None)


class DeviceMatchPanel(QtWidgets.QWidget):
    changed = Signal()  # devices or instruction changed

    def __init__(self, parent=None, schematic: bool = False):
        super().__init__(parent)
        # schematic: no plate photo, the left view shows the substrate as drawn (corners, devices already placed)
        self.schematic = schematic
        self.fixed: list[tuple[str, float, float]] = []  # devices already placed: (name, u, v), reference points
        self.taken_names: set[str] = set()  # device names already used on the plate
        self.photo1: np.ndarray | None = None
        self.h1: np.ndarray | None = None  # plate -> plate photo
        self.substrates: list[tuple[str, Rect]] = []
        self.photo2: np.ndarray | None = None
        self.left_pts: list[CornerItem] = []
        self.right_pts: list[CornerItem] = []
        self.t: np.ndarray | None = None  # device photo -> plate
        self.rms = 0.0
        self.error = ""
        self.devices: list[DevicePoint] = []
        self._left_items: list[QtWidgets.QGraphicsItem] = []
        self._right_items: list[QtWidgets.QGraphicsItem] = []
        self._crop_key = None
        self._filling = False

        self.substrate = QtWidgets.QComboBox()
        self.substrate.setMinimumContentsLength(10)
        self.substrate.setToolTip("Substrate shown on the left (found or drawn on the plate photo)")
        self.substrate.currentIndexChanged.connect(lambda _: self._refresh_crop())
        open_btn = QtWidgets.QPushButton("Open device photo…")
        open_btn.clicked.connect(self.open_photo)
        self.recent = QtWidgets.QComboBox()
        self.recent.setToolTip("Device photos already used while the program runs (kept until it exits)")
        self.recent.activated.connect(self._on_recent)
        self._fill_recent()
        undo_btn = QtWidgets.QPushButton("Undo last point")
        undo_btn.setToolTip("Remove the last point clicked (Ctrl+Z); the others stay")
        undo_btn.clicked.connect(lambda: self.undo_point())
        QtWidgets.QShortcut(QtGui.QKeySequence.Undo, self, self.undo_point)
        clear_btn = QtWidgets.QPushButton("Clear all points")
        clear_btn.setToolTip("Remove all the matched points (the devices already marked stay where they are)")
        clear_btn.clicked.connect(lambda: self.clear_pairs())
        self.pair_radio = QtWidgets.QRadioButton("mark the same point on both")
        self.device_radio = QtWidgets.QRadioButton("mark devices")
        self.pair_radio.setChecked(True)
        self.pair_radio.toggled.connect(lambda _: self.changed.emit())
        self.file_label = QtWidgets.QLabel("no device photo")
        self.file_label.setStyleSheet("color: #555;")
        self.match_label = QtWidgets.QLabel()

        self.left_scene = QtWidgets.QGraphicsScene(self)
        self.left_view = ZoomView(self.left_scene)
        self.left_view.clicked.connect(self._on_left_click)
        self.left_view.hovered.connect(lambda x, y: self._show_cursor(x, -y))
        self.crop_item = QtWidgets.QGraphicsPixmapItem()
        self.crop_item.setTransformationMode(Qt.SmoothTransformation)
        self.left_scene.addItem(self.crop_item)
        self.right_scene = QtWidgets.QGraphicsScene(self)
        self.right_view = ZoomView(self.right_scene)
        self.right_view.clicked.connect(self._on_right_click)
        self.right_view.hovered.connect(self._on_right_hover)
        self.photo_item = QtWidgets.QGraphicsPixmapItem()
        self.photo_item.setTransformationMode(Qt.SmoothTransformation)
        self.right_scene.addItem(self.photo_item)
        self.left_title = QtWidgets.QLabel()
        self.cursor_label = QtWidgets.QLabel("cursor: x = –, y = – (plate mm)")
        self.cursor_label.setStyleSheet("font-family: monospace;")

        self.table = QtWidgets.QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setMinimumHeight(100)
        self.table.itemChanged.connect(self._on_name_changed)
        self.table.itemSelectionChanged.connect(self._draw)
        delete_btn = QtWidgets.QPushButton("Delete selected devices")
        delete_btn.clicked.connect(self.delete_selected)
        QtWidgets.QShortcut(QtGui.QKeySequence(Qt.Key_Delete), self.table, self.delete_selected)

        top = QtWidgets.QHBoxLayout()
        top.addWidget(QtWidgets.QLabel("substrate"))
        top.addWidget(self.substrate)
        top.addWidget(open_btn)
        top.addWidget(self.recent)
        top.addWidget(undo_btn)
        top.addWidget(clear_btn)
        top.addSpacing(12)
        top.addWidget(self.pair_radio)
        top.addWidget(self.device_radio)
        top.addWidget(self.file_label, 1)
        left = QtWidgets.QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.addWidget(self.left_title)
        left.addWidget(self.left_view, 1)
        left_w = QtWidgets.QWidget()
        left_w.setLayout(left)
        right = QtWidgets.QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.addWidget(QtWidgets.QLabel("<b>Device photo</b>"))
        right.addWidget(self.right_view, 1)
        right_w = QtWidgets.QWidget()
        right_w.setLayout(right)
        views = QtWidgets.QSplitter()
        views.addWidget(left_w)
        views.addWidget(right_w)
        upper = QtWidgets.QVBoxLayout()
        upper.setContentsMargins(0, 0, 0, 0)
        upper.addWidget(views, 1)
        upper.addWidget(self.cursor_label)
        upper_w = QtWidgets.QWidget()
        upper_w.setLayout(upper)
        rows = QtWidgets.QHBoxLayout()
        rows.addWidget(QtWidgets.QLabel("<b>Devices</b> (no height: on the surface of their substrate)"))
        rows.addStretch(1)
        rows.addWidget(delete_btn)
        lower = QtWidgets.QVBoxLayout()
        lower.setContentsMargins(0, 0, 0, 0)
        lower.addLayout(rows)
        lower.addWidget(self.table, 1)
        lower_w = QtWidgets.QWidget()
        lower_w.setLayout(lower)
        split = QtWidgets.QSplitter(Qt.Vertical)
        split.addWidget(upper_w)
        split.addWidget(lower_w)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        box = QtWidgets.QVBoxLayout(self)
        box.addLayout(top)
        box.addWidget(self.match_label)
        box.addWidget(split, 1)
        self._update_match_label()
        self._refresh_crop()

    # -- inputs from the plate photo -------------------------------------------------
    def set_source(self, photo: np.ndarray | None, h: np.ndarray | None) -> None:
        """The plate photo and its registration (plate -> photo)."""
        self.photo1, self.h1 = photo, h
        self._crop_key = None
        self._refresh_crop()

    def set_substrates(self, substrates: list[tuple[str, Rect]]) -> None:
        """The samples found / drawn on the plate photo: (name, plate rect)."""
        current = self.current_substrate()
        self.substrates = list(substrates)
        names = [n for n, _ in self.substrates]
        self.substrate.blockSignals(True)
        self.substrate.clear()
        self.substrate.addItems(names)
        if current is not None and current[0] in names:
            self.substrate.setCurrentIndex(names.index(current[0]))
        self.substrate.blockSignals(False)
        self._refresh_crop()
        self._fill_table()

    def set_fixed(self, devices: list[tuple[str, float, float]]) -> None:
        """Devices already on the substrate (name, plate u, v): drawn in blue, reference points for the matching."""
        self.fixed = [(str(n), float(u), float(v)) for n, u, v in devices]
        self._draw()

    def _has_left(self) -> bool:
        """The left view can be used: plate photo registered, or the schematic substrate."""
        return self.current_substrate() is not None and (self.schematic or self.h1 is not None)

    def current_substrate(self) -> tuple[str, Rect] | None:
        i = self.substrate.currentIndex()
        return self.substrates[i] if 0 <= i < len(self.substrates) else None

    def select_substrate(self, name: str) -> None:
        names = [n for n, _ in self.substrates]
        if name in names:
            self.substrate.setCurrentIndex(names.index(name))

    def _refresh_crop(self) -> None:
        sub = self.current_substrate()
        if sub is not None and self.schematic:
            bounds, _ = crop_view(sub[1])
            if bounds != self._crop_key:
                self.crop_item.setPixmap(QtGui.QPixmap())
                self.left_scene.setSceneRect(QtCore.QRectF(bounds[0], -bounds[3], bounds[2] - bounds[0],
                                                           bounds[3] - bounds[1]))
                self.left_view.fit()
                self._crop_key = bounds
            self.left_title.setText(f"<b>{sub[0]}</b> as drawn on the plate: its corners and the devices already "
                                    "placed (blue) are reference points")
        elif sub is None or self.photo1 is None or self.h1 is None:
            self.crop_item.setPixmap(QtGui.QPixmap())
            self.left_title.setText("<b>Plate photo</b> around the substrate (find the samples in tab 1 first)")
            self._crop_key = None
        else:
            bounds, px = crop_view(sub[1])
            key = (bounds, px, id(self.photo1), self.h1.tobytes())
            if key != self._crop_key:
                r = rectify(self.photo1, self.h1, bounds, px)
                self.crop_item.setPixmap(QtGui.QPixmap.fromImage(array_to_qimage(r.pixels)))
                self.crop_item.setScale(1 / px)
                self.crop_item.setPos(bounds[0], -bounds[3])
                self.left_scene.setSceneRect(QtCore.QRectF(bounds[0], -bounds[3], bounds[2] - bounds[0],
                                                           bounds[3] - bounds[1]))
                self.left_view.fit()
                self._crop_key = key
            self.left_title.setText(f"<b>Plate photo</b> around {sub[0]} (plate coordinates)")
        self._draw()
        self.changed.emit()

    # -- device photo --------------------------------------------------------------
    def open_photo(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open device photo", "",
                                                        "Images (*.jpg *.jpeg *.png *.bmp *.tif *.tiff)")
        if path:
            self.load_photo(path)

    def load_photo(self, path: str, remember: bool = True) -> bool:
        rgb = read_photo(path, self)
        if rgb is None:
            return False
        self.set_photo(rgb)
        self.file_label.setText(path)
        if remember:
            photo_cache().add(DEVICE, path)
            self._fill_recent()
        return True

    def _fill_recent(self) -> None:
        photos = photo_cache().of_kind(DEVICE)
        self.recent.blockSignals(True)
        self.recent.clear()
        self.recent.addItem("recent photos…" if photos else "no recent photo")
        for c in photos:
            self.recent.addItem(c.label, c)
        self.recent.setEnabled(bool(photos))
        self.recent.blockSignals(False)

    def _on_recent(self, index: int) -> None:
        c = self.recent.itemData(index)
        if c is not None and self.load_photo(str(c.path), remember=False):
            photo_cache().add(DEVICE, c.source)  # newest first
            self.file_label.setText(f"{c.source} (kept copy)")
            self._fill_recent()
        self.recent.setCurrentIndex(0)

    def set_photo(self, rgb: np.ndarray) -> None:
        """A new device photo: the devices marked so far keep their plate positions, the points start again."""
        for d in self.devices:
            d.px = None
        self.photo2 = rgb
        self.photo_item.setPixmap(QtGui.QPixmap.fromImage(array_to_qimage(rgb)))
        h, w = rgb.shape[:2]
        m = 0.15 * max(w, h)
        self.right_scene.setSceneRect(QtCore.QRectF(-m, -m, w + 2 * m, h + 2 * m))
        self.right_view.fit()
        self.pair_radio.setChecked(True)
        self.clear_pairs()

    # -- point pairs ---------------------------------------------------------------
    def undo_point(self) -> bool:
        """Remove the last point clicked: the unmatched left point, else the right point of the last pair (its left
        point then waits for a new right click). False if there is none."""
        if len(self.left_pts) > len(self.right_pts):
            self.left_scene.removeItem(self.left_pts.pop())
        elif self.right_pts:
            self.right_scene.removeItem(self.right_pts.pop())
        else:
            return False
        self._match()
        return True

    def clear_pairs(self) -> None:
        for it in self.left_pts:
            self.left_scene.removeItem(it)
        for it in self.right_pts:
            self.right_scene.removeItem(it)
        self.left_pts, self.right_pts = [], []
        self._match()

    def set_pairs(self, plate_pts, photo_pts) -> None:
        """Place point pairs: plate mm on the left, device photo pixels on the right."""
        self.clear_pairs()
        for (u, v), (x, y) in zip(plate_pts, photo_pts):
            self._add_marker(self.left_scene, self.left_pts, u, -v)
            self._add_marker(self.right_scene, self.right_pts, x, y)
        self._match()

    def _add_marker(self, scene, markers, x, y) -> None:
        item = CornerItem(len(markers), self._match)
        markers.append(item)
        scene.addItem(item)
        item.setPos(x, y)

    def _snap(self, u: float, v: float) -> tuple[float, float]:
        """A device already placed (and, in the schematic view, a substrate corner) near a click; else the click."""
        sub = self.current_substrate()
        if sub is None:
            return u, v
        u0, v0, u1, v1 = sub[1]
        points = ([(u0, v0), (u1, v0), (u1, v1), (u0, v1)] if self.schematic else []) + \
            [(fu, fv) for _, fu, fv in self.fixed]
        if not points:
            return u, v
        scale = self.left_view.transform().m11()
        tol = min(SNAP_PX / scale if scale > 0 else 0.0, SNAP_MAX * max(u1 - u0, v1 - v0))
        best = min(points, key=lambda p: np.hypot(p[0] - u, p[1] - v))
        return best if np.hypot(best[0] - u, best[1] - v) <= tol else (u, v)

    def _on_left_click(self, x: float, y: float) -> None:
        if not self._has_left():
            return
        if self.device_radio.isChecked():
            self.add_device(x, -y)
            return
        u, v = self._snap(x, -y)
        x, y = u, -v
        if len(self.left_pts) > len(self.right_pts):
            self.left_pts[-1].setPos(x, y)  # the point is not matched yet: move it
        else:
            self._add_marker(self.left_scene, self.left_pts, x, y)
            self._match()

    def _on_right_click(self, x: float, y: float) -> None:
        if self.photo2 is None:
            return
        if self.device_radio.isChecked():
            if self.t is not None:
                u, v = apply_homography(self.t, [(x, y)])[0]
                self.add_device(float(u), float(v), (x, y))
        elif len(self.right_pts) < len(self.left_pts):
            self._add_marker(self.right_scene, self.right_pts, x, y)
            self._match()

    def _match(self) -> None:
        n = min(len(self.left_pts), len(self.right_pts))
        self.t, self.rms, self.error = None, 0.0, ""
        if n >= 2:
            plate = [(p.pos().x(), -p.pos().y()) for p in self.left_pts[:n]]
            photo = [(p.pos().x(), p.pos().y()) for p in self.right_pts[:n]]
            try:
                self.t, self.rms = pair_transform(photo, plate)
            except ValueError as exc:
                self.error = str(exc)
        if self.t is not None:
            for d in self.devices:
                if d.px is not None:
                    d.u, d.v = (float(c) for c in apply_homography(self.t, [d.px])[0])
        self._update_match_label()
        self._fill_table()
        self.changed.emit()

    def _update_match_label(self) -> None:
        n = min(len(self.left_pts), len(self.right_pts))
        if self.error:
            text, color = self.error, "#c00000"
        elif self.t is None:
            text, color = f"{n} point pair(s): at least 2 are needed to place the device photo.", "#555"
        else:
            kind = TRANSFORM_KIND.get(n, "perspective")
            warn = self.rms > 0.02
            text = (f"{n} point pairs → {kind}; mismatch of the points {self.rms * 1000:.0f} µm rms"
                    + (" – check the points (one may be wrong)" if warn else "")
                    + ("" if n > {2: 2, 3: 3}.get(n, 4) else " (more pairs show the accuracy)"))
            color = "#c00000" if warn else "#207020"
        self.match_label.setStyleSheet(f"color: {color};")
        self.match_label.setText(text)

    def instruction(self) -> str:
        sub = self.current_substrate()
        if not self._has_left():
            return "Find or draw the samples on the plate photo (tab 1) first."
        if self.photo2 is None:
            return f"Open a photo showing the devices of {sub[0]} (it need not show the substrate edges)."
        if self.device_radio.isChecked():
            if self.t is None:
                return "Mark at least 2 point pairs first (“mark the same point on both”)."
            return ("Click on each device in the device photo (or on the left). Name them in the table; switch back "
                    "to “mark the same point on both” to add or drag points.")
        n = len(self.left_pts)
        if n > len(self.right_pts):
            return f"Click the same point {n} on the device photo (right). A wrong point: Undo last point (Ctrl+Z)."
        more = "" if n < 2 else " Enough points: choose “mark devices”, or add more pairs for accuracy."
        what = ("a corner of the substrate or a device already placed (blue; clicks snap to them)" if self.schematic
                else "a feature you also see on the device photo (paint dot, pattern corner, scratch)")
        return (f"Click point {n + 1} on the left: {what}, then the same point on the right. Wheel = zoom, middle "
                f"drag = pan.{more}")

    # -- devices -------------------------------------------------------------------
    def add_device(self, u: float, v: float, px: tuple[float, float] | None = None) -> DevicePoint:
        names = {d.name for d in self.devices} | self.taken_names | {n for n, _, _ in self.fixed}
        i = 1
        while f"D{i}" in names:
            i += 1
        d = DevicePoint(f"D{i}", u, v, px)
        self.devices.append(d)
        self._fill_table()
        self.table.selectRow(len(self.devices) - 1)
        self.changed.emit()
        return d

    def delete_selected(self) -> None:
        rows = {i.row() for i in self.table.selectedIndexes()}
        if rows:
            self.devices = [d for r, d in enumerate(self.devices) if r not in rows]
            self._fill_table()
            self.changed.emit()

    def _fill_table(self) -> None:
        self._filling = True
        self.table.setRowCount(len(self.devices))
        for row, d in enumerate(self.devices):
            sub = container(self.substrates, d.u, d.v)
            if sub:
                u0, v0 = sub[1][0], sub[1][1]
                values = [d.name, sub[0], f"{d.u:.3f}", f"{d.v:.3f}", f"{d.u - u0:.3f}", f"{d.v - v0:.3f}", "ok"]
            else:
                values = [d.name, "–", f"{d.u:.3f}", f"{d.v:.3f}", "", "", "not on a sample"]
            for col, text in enumerate(values):
                item = QtWidgets.QTableWidgetItem(text)
                if col:
                    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                if col == len(values) - 1:
                    item.setForeground(QtGui.QBrush(QtGui.QColor("#207020" if sub else "#c00000")))
                self.table.setItem(row, col, item)
        self._filling = False
        self._draw()

    def _on_name_changed(self, item) -> None:
        if self._filling or item.column() != 0:
            return
        d = self.devices[item.row()]
        d.name = item.text().strip() or d.name
        self._draw()
        self.changed.emit()

    # -- drawing -------------------------------------------------------------------
    def _cross(self, scene, x, y, name, selected, items, color=COLOR_DEVICE) -> None:
        r = 9 if selected else 6
        pen = cosmetic_pen(color, 2.5 if selected else 1.5)
        for x0, y0, x1, y1 in ((-r, 0, r, 0), (0, -r, 0, r)):
            line = scene.addLine(x0, y0, x1, y1, pen)
            line.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
            line.setPos(x, y)
            items.append(line)
        label = scene.addSimpleText(name)
        label.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
        label.setBrush(QtGui.QBrush(color))
        label.setPos(x, y)
        items.append(label)

    def _draw(self) -> None:
        for it in self._left_items:
            self.left_scene.removeItem(it)
        for it in self._right_items:
            self.right_scene.removeItem(it)
        self._left_items, self._right_items = [], []
        sub = self.current_substrate()
        if self._has_left():
            for name, (u0, v0, u1, v1) in self.substrates:
                mine = name == sub[0]
                item = self.left_scene.addRect(QtCore.QRectF(u0, -v1, u1 - u0, v1 - v0),
                                               cosmetic_pen(COLOR_SUBSTRATE if mine else "#909090", 2 if mine else 1))
                self._left_items.append(item)
        selected = {i.row() for i in self.table.selectedIndexes()}
        for name, u, v in self.fixed:
            if self._has_left():
                self._cross(self.left_scene, u, -v, name, False, self._left_items, COLOR_FIXED)
            if self.t is not None:  # where the matching puts it on the device photo: a check of the points
                (x, y), = apply_homography(np.linalg.inv(self.t), [(u, v)])
                self._cross(self.right_scene, x, y, name, False, self._right_items, COLOR_FIXED)
        for row, d in enumerate(self.devices):
            if self._has_left():
                self._cross(self.left_scene, d.u, -d.v, d.name, row in selected, self._left_items)
            if d.px is not None:
                self._cross(self.right_scene, d.px[0], d.px[1], d.name, row in selected, self._right_items)
        if sub is not None and self.t is not None:
            # the substrate outline on the device photo (often outside it)
            u0, v0, u1, v1 = sub[1]
            q = apply_homography(np.linalg.inv(self.t), [(u0, v0), (u1, v0), (u1, v1), (u0, v1)])
            poly = self.right_scene.addPolygon(QtGui.QPolygonF([QtCore.QPointF(x, y) for x, y in q]),
                                               cosmetic_pen(COLOR_SUBSTRATE, 2))
            self._right_items.append(poly)
        for it in self._left_items + self._right_items:
            it.setZValue(15)
            it.setAcceptedMouseButtons(Qt.NoButton)

    # -- cursor ------------------------------------------------------------------
    def _show_cursor(self, u: float, v: float) -> None:
        text = f"cursor: x = {u:7.3f} mm, y = {v:7.3f} mm on the plate"
        sub = container(self.substrates, u, v)
        if sub:
            text += f"   dx = {u - sub[1][0]:.3f}, dy = {v - sub[1][1]:.3f} mm from the left / bottom of {sub[0]}"
        self.cursor_label.setText(text)

    def _on_right_hover(self, x: float, y: float) -> None:
        if self.t is not None:
            u, v = apply_homography(self.t, [(x, y)])[0]
            self._show_cursor(float(u), float(v))


class DeviceFromPhotoDialog(QtWidgets.QDialog):
    """New devices on a substrate already on the plate, from a device photo: no need to find the samples again.

    Left: the substrate as drawn (its corners and the devices already placed are the reference points), or a plate
    photo used earlier in this run (registered then). Right: the device photo. The devices clicked are added to the
    substrate; those already on it are not changed."""

    def __init__(self, sample: Sample, plate_key: str | None = None, taken_names=(), parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Devices of {sample.name} from a photo")
        self.resize(1300, 860)
        self.sample = sample
        self.panel = DeviceMatchPanel(schematic=True)
        self.panel.taken_names = set(taken_names)
        self.panel.set_substrates([(sample.name, sample.bounds())])
        self.panel.set_fixed([(d.name, *d.position(sample)) for d in sample.devices])
        self.panel.changed.connect(self._update)

        self.plate_photo = QtWidgets.QComboBox()
        self.plate_photo.addItem("none: the substrate as drawn", None)
        for c in photo_cache().of_kind(PLATE, plate_key, registered=True):
            self.plate_photo.addItem(f"plate photo {c.label}", c)
        self.plate_photo.setToolTip("Left view: the substrate as drawn (its corners and devices are the reference "
                                    "points), or a plate photo registered earlier in this run.\nWith a photo the "
                                    "devices are placed where the photo shows them: if the substrate was moved since "
                                    "(Found here), use the substrate as drawn.")
        self.plate_photo.currentIndexChanged.connect(self._on_plate_photo)
        self.plate_photo.setEnabled(self.plate_photo.count() > 1)

        self.instruction = QtWidgets.QLabel()
        self.instruction.setWordWrap(True)
        self.instruction.setStyleSheet("font-weight: bold; color: #00609a;")
        self.add_btn = QtWidgets.QPushButton("Add devices")
        self.add_btn.setStyleSheet("font-weight: bold;")
        self.add_btn.setAutoDefault(False)
        self.add_btn.clicked.connect(self.accept)
        cancel = QtWidgets.QPushButton("Cancel")
        cancel.setAutoDefault(False)
        cancel.clicked.connect(self.reject)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("left view"))
        row.addWidget(self.plate_photo, 1)
        bottom = QtWidgets.QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(self.add_btn)
        bottom.addWidget(cancel)
        box = QtWidgets.QVBoxLayout(self)
        box.addWidget(self.instruction)
        box.addLayout(row)
        box.addWidget(self.panel, 1)
        box.addLayout(bottom)
        self._update()

    def _on_plate_photo(self, index: int) -> None:
        c = self.plate_photo.itemData(index)
        rgb = read_photo(str(c.path), self) if c is not None else None
        self.panel.schematic = rgb is None
        self.panel.set_source(rgb, None if rgb is None else c.h)

    def _update(self) -> None:
        self.instruction.setText(self.panel.instruction())
        self.add_btn.setEnabled(bool(self.devices()))

    def devices(self) -> list[Device]:
        """The new devices on the substrate, placed relative to it (edges left / bottom)."""
        u0, v0, u1, v1 = self.sample.bounds()
        out = []
        for p in self.panel.devices:
            if u0 <= p.u <= u1 and v0 <= p.v <= v1:
                d = Device(p.name)
                d.set_position(self.sample, round(p.u, 3), round(p.v, 3))
                out.append(d)
        return out
