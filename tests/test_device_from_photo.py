"""Devices added to a substrate already on the plate, the orientation line and the least-squares matching, undo of
the last point, photos kept for the run."""

import os
import time

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
qt = pytest.importorskip("quickalignment.ui._qt")
from quickalignment.alignment.photo import apply_homography  # noqa: E402
from quickalignment.core.geometry import STANDARD_PLATE, Device, Sample  # noqa: E402
from quickalignment.ui.device_match import DeviceFromPhotoDialog, DeviceMatchPanel  # noqa: E402
from quickalignment.ui.photo_cache import DEVICE, PLATE, PREFIX, PhotoCache, photo_cache, remove_stale  # noqa: E402
from quickalignment.ui.photo_dialog import PhotoImportDialog  # noqa: E402
from quickalignment.ui.plate_editor import PlateEditor  # noqa: E402

from test_photo import PHOTO_CORNERS, synthetic_photo  # noqa: E402

QtGui, QtWidgets = qt.QtGui, qt.QtWidgets

# device photo: 200 px/mm, turned by 25 deg (plate mm -> photo px through T_TRUE^-1)
_c, _s = np.cos(np.radians(25)), np.sin(np.radians(25))
T_TRUE = np.array([[_c, -_s, 1.0], [_s, _c, 4.0], [0, 0, 1]]) @ np.diag([1 / 200, -1 / 200, 1])


def px(u, v):
    (x, y), = apply_homography(np.linalg.inv(T_TRUE), [(u, v)])
    return float(x), float(y)


@pytest.fixture
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _save(img, path):
    from quickalignment.ui.photo_widgets import array_to_qimage
    assert array_to_qimage(img).save(str(path))
    return str(path)


def draw_line(panel, a, b):
    """Step 1: the same direction (plate mm a -> b) clicked on the left, then on the device photo."""
    panel.line_radio.setChecked(True)
    for u, v in (a, b):
        panel._on_left_click(u, -v)
    for u, v in (a, b):
        panel._on_right_click(*px(u, v))


def test_undo_last_point_removes_only_it(app):
    p = DeviceMatchPanel(schematic=True)
    p.set_substrates([("S1", (0.0, 0.0, 4.0, 5.0))])
    p.set_photo(np.full((300, 300, 3), 90, np.uint8))
    assert p.step() == 1 and "point A of the direction line on the left" in p.instruction()
    draw_line(p, (0.0, 0.0), (4.0, 0.0))
    assert p.lines_done() and p.step() == 2  # both lines drawn: on to the point pairs
    for u, v in ((1.0, 1.0), (3.0, 1.5)):
        p._on_left_click(u, -v)
        p._on_right_click(*px(u, v))
    p._on_left_click(2.0, -4.0)  # third left point, not matched yet
    assert (len(p.left_pts), len(p.right_pts)) == (3, 2) and p.t is not None
    assert p.undo_point() and (len(p.left_pts), len(p.right_pts)) == (2, 2)
    assert p.undo_point() and (len(p.left_pts), len(p.right_pts)) == (2, 1) and p.t is None
    assert p.left_pts[0].pos().x() == pytest.approx(1.0)  # the first points stay
    p._on_right_click(*px(3.0, 1.5))  # the pair is completed again
    assert p.t is not None and p.rms < 1e-6
    p.clear_pairs()
    assert p.lines_done() and p.t is None  # the lines stay
    assert p.undo_point() and len(p.right_line) == 1 and not p.lines_done() and p.step() == 1
    p.clear_all()
    assert not p.undo_point()


def test_line_sets_the_orientation_and_points_never_distort(app):
    p = DeviceMatchPanel(schematic=True)
    p.set_substrates([("S1", (0.0, 0.0, 4.0, 5.0))])
    p.set_photo(np.full((900, 900, 3), 90, np.uint8))
    # along the bottom edge, not between the same places, and pointing opposite ways: the same orientation
    p.line_radio.setChecked(True)
    for u, v in ((0.0, 0.0), (4.0, 0.0)):
        p._on_left_click(u, -v)
    for u, v in ((3.0, 0.0), (0.5, 0.0)):
        p._on_right_click(*px(u, v))
    assert p.lines_done()
    # four pairs, two of them clicked 40 µm off (low resolution plate photo): no perspective, a least-squares fit
    good = [(1.0, 1.0), (3.0, 1.5), (1.2, 4.0), (3.5, 4.2)]
    clicked = [(1.04, 1.0), (3.0, 1.46), (1.2, 4.0), (3.5, 4.2)]
    for (u, v), (cu, cv) in zip(good, clicked):
        p._on_left_click(cu, -cv)
        p._on_right_click(*px(u, v))
    assert p.t is not None and np.allclose(p.t[2], [0, 0, 1])  # rotation + scale + shift only
    assert p.fit.angle == pytest.approx(25.0, abs=1e-6)  # from the direction, exactly
    a = p.t[:2, :2]
    assert np.allclose(a @ a.T, np.eye(2) * abs(np.linalg.det(a)))  # no shear, no stretch
    assert 0.005 < p.rms < 0.04 and "least squares" in p.match_label.text()
    (u, v), = apply_homography(p.t, [px(2.0, 3.0)])
    assert (u, v) == pytest.approx((2.0, 3.0), abs=0.03)


def test_device_from_photo_on_a_drawn_substrate(app):
    ed = PlateEditor()
    s = ed.add_sample(Sample("S1", u=2.0, v=2.5, length=4.0, width=5.0))
    old = Device("D1")
    old.set_position(s, 1.5, 3.0)
    ed.add_device(s, old)
    dlg = ed.devices_from_photo(s)
    panel = dlg.panel
    assert panel.schematic and panel.fixed == [("D1", 1.5, 3.0)]
    assert not dlg.add_btn.isEnabled()
    panel.set_photo(np.full((900, 900, 3), 90, np.uint8))
    assert "edge of the substrate" in dlg.instruction.text()
    # Step 1: the bottom edge of the substrate (clicks a little off snap to its corners), on both
    for u, v in ((0.0, 0.0), (4.0, 0.0)):
        panel._on_left_click(u + 0.03, -(v - 0.02))
    for u, v in ((0.0, 0.0), (4.0, 0.0)):
        panel._on_right_click(*px(u, v))
    assert "corner of the substrate" in dlg.instruction.text()
    # Step 2, reference points: two substrate corners and the device already placed; clicks snap to them
    for u, v in ((0.0, 0.0), (4.0, 0.0), (1.5, 3.0)):
        panel._on_left_click(u + 0.03, -(v - 0.02))
        panel._on_right_click(*px(u, v))
    assert panel.t is not None and panel.rms < 1e-6
    assert (panel.left_pts[2].pos().x(), -panel.left_pts[2].pos().y()) == (1.5, 3.0)
    # the new device clicked on the device photo
    panel.device_radio.setChecked(True)
    panel._on_right_click(*px(3.2, 4.1))
    assert [d.name for d in panel.devices] == ["D2"]  # D1 is taken
    assert dlg.add_btn.isEnabled()
    new = dlg.devices()
    assert len(new) == 1 and new[0].position(s) == pytest.approx((3.2, 4.1), abs=1e-3)
    ed.import_devices(s, new)
    assert [d.name for d in s.devices] == ["D1", "D2"]
    assert old.position(s) == pytest.approx((1.5, 3.0))  # the device already there is not changed


def test_photo_cache_keeps_copies_and_deletes_them(tmp_path):
    src = tmp_path / "plate.jpg"
    src.write_bytes(b"x")
    cache = PhotoCache(tmp_path)
    e = cache.add(PLATE, str(src))
    assert e.path.exists() and e.path.parent.name.startswith(PREFIX) and e.h is None
    assert cache.add(PLATE, str(src)) is e  # once per file
    cache.remember_registration(str(src), "standard", [(1, 2), (3, 4)], False, np.eye(3))
    assert cache.of_kind(PLATE, "standard", registered=True) == [e] and cache.of_kind(PLATE, "gating") == []
    assert cache.of_kind(DEVICE) == [] and "(registered)" in e.label
    folder = cache.folder
    src.unlink()  # the original may go: the copy stays for the run
    assert e.path.exists()
    cache.clear()
    assert not folder.exists() and cache.photos == []
    # a folder left by a run that did not exit normally is deleted once old
    old = tmp_path / (PREFIX + "old")
    old.mkdir()
    os.utime(old, (time.time() - 5 * 86400,) * 2)
    young = tmp_path / (PREFIX + "young")
    young.mkdir()
    remove_stale(tmp_path)
    assert not old.exists() and young.exists()


def test_plate_photo_kept_with_its_points_for_the_run(app, tmp_path):
    img, _ = synthetic_photo()
    path = _save(img, tmp_path / "plate.png")
    dlg = PhotoImportDialog(STANDARD_PLATE, 0.5)
    assert dlg.load_photo(path)
    dlg.set_corners(PHOTO_CORNERS)
    h = dlg.reg.h.copy()
    # undo the last corner only
    assert dlg.reg.undo_corner() and len(dlg.reg.corners) == 3 and dlg.reg.h is None
    dlg.set_corners(PHOTO_CORNERS)
    dlg.done(0)  # also kept on Cancel
    c, = photo_cache().of_kind(PLATE, "standard", registered=True)
    assert np.allclose(c.h, h)
    # From photo again: the photo and its points come back, nothing to click
    dlg2 = PhotoImportDialog(STANDARD_PLATE, 0.5)
    assert dlg2.recent.count() == 2 and dlg2.recent.isEnabled()
    assert dlg2.load_recent(dlg2.recent.itemData(1))
    assert np.allclose(dlg2.reg.h, h) and len(dlg2.reg.corners) == 4
    # Device from photo can use it as the left view
    s = Sample("S1", u=-2.0, v=1.0, length=3.0, width=3.0)
    d3 = DeviceFromPhotoDialog(s, "standard")
    assert d3.plate_photo.count() == 2 and d3.plate_photo.isEnabled()
    d3.plate_photo.setCurrentIndex(1)
    assert not d3.panel.schematic and np.allclose(d3.panel.h1, h) and d3.panel.crop_item.pixmap().width() > 0
    d3.plate_photo.setCurrentIndex(0)
    assert d3.panel.schematic and d3.panel.h1 is None
    # device photos are kept too
    dev_path = _save(np.full((50, 60, 3), 120, np.uint8), tmp_path / "dev.png")
    assert d3.panel.load_photo(dev_path)
    assert d3.panel.recent.count() == 2
    d3.panel.set_photo(np.zeros((10, 10, 3), np.uint8))
    d3.panel._on_recent(1)
    assert d3.panel.photo2.shape[:2] == (50, 60)
