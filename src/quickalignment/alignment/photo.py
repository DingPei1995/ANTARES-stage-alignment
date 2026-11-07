"""Find samples on a photo of the plate taken from above (sample side).

The user clicks the four corners of the sample area on the photo; a
perspective transform (homography) maps the photo onto the plate frame, so
the photo is resampled on a regular grid in plate mm ("rectified") and laid
over the plate model. Samples are the parts of the sample area whose colour
differs from the bare plate (CIELAB colour difference ΔE): the mask is
cleaned up, split into connected regions and each region gives a rectangle
(its bounding box) in plate coordinates.

Only numpy; images are (rows, cols, 3) uint8 RGB arrays. The photo shows
positions only: the sample height H is entered by the user.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

from ..core.geometry import PlateGeometry, Rect

PX_PER_MM = 20  # rectified grid: 0.05 mm per pixel


def rect_corners(rect: Rect) -> list[tuple[str, tuple[float, float]]]:
    """The corners of a plate rectangle in click order (clockwise from top left, front view, tab up)."""
    u0, v0, u1, v1 = rect
    return [
        ("top left (tab side)", (u0, v1)),
        ("top right (tab side)", (u1, v1)),
        ("bottom right", (u1, v0)),
        ("bottom left", (u0, v0)),
    ]


def corner_points(plate: PlateGeometry) -> list[tuple[str, tuple[float, float]]]:
    """The four reference points clicked on a plate photo: the sample area corners, in click order."""
    return rect_corners(plate.riser_bounds())


def homography(src, dst) -> np.ndarray:
    """3 x 3 matrix H with dst ~ H @ src (normalised DLT, at least 4 point pairs)."""
    src, dst = np.asarray(src, float), np.asarray(dst, float)
    if src.shape != dst.shape or src.ndim != 2 or src.shape[1] != 2 or len(src) < 4:
        raise ValueError("At least 4 point pairs are needed.")

    def normalise(p):
        c = p.mean(axis=0)
        d = np.sqrt(((p - c) ** 2).sum(axis=1)).mean()
        if d < 1e-12:
            raise ValueError("The points coincide.")
        s = np.sqrt(2) / d
        t = np.array([[s, 0, -s * c[0]], [0, s, -s * c[1]], [0, 0, 1]])
        return t, (p - c) * s

    ts, ps = normalise(src)
    td, pd = normalise(dst)
    rows = []
    for (x, y), (u, v) in zip(ps, pd):
        rows.append([-x, -y, -1, 0, 0, 0, u * x, u * y, u])
        rows.append([0, 0, 0, -x, -y, -1, v * x, v * y, v])
    _, sv, vt = np.linalg.svd(np.asarray(rows))
    if sv[-2] < 1e-9 * sv[0]:
        raise ValueError("The points are degenerate (three of them on a line?).")
    h = np.linalg.inv(td) @ vt[-1].reshape(3, 3) @ ts
    return h / h[2, 2]


def apply_homography(h: np.ndarray, pts) -> np.ndarray:
    pts = np.asarray(pts, float)
    q = np.c_[pts, np.ones(len(pts))] @ h.T
    return q[:, :2] / q[:, 2:3]


def pair_transform(photo_pts, plate_pts) -> tuple[np.ndarray, float]:
    """Photo pixels -> plate mm from point pairs the user marked as the same place on both.

    2 pairs: rotation + scale + shift (photo from above, not mirrored); 3: affine;
    4 or more: perspective (least squares). Returns the 3 x 3 matrix and the rms
    residual of the pairs in mm (0 when there are no more pairs than needed)."""
    src, dst = np.asarray(photo_pts, float), np.asarray(plate_pts, float)
    n = len(src)
    if n < 2 or src.shape != dst.shape:
        raise ValueError("At least 2 point pairs are needed.")
    flip = np.diag([1.0, -1.0, 1.0])  # image y points down, plate v up
    s = src * [1, -1]
    if n == 2:
        z0, z1 = complex(*s[0]), complex(*s[1])
        w0, w1 = complex(*dst[0]), complex(*dst[1])
        if abs(z1 - z0) < 1e-9 or abs(w1 - w0) < 1e-12:
            raise ValueError("The two points of a photo coincide.")
        a = (w1 - w0) / (z1 - z0)
        b = w0 - a * z0
        t = np.array([[a.real, -a.imag, b.real], [a.imag, a.real, b.imag], [0, 0, 1]]) @ flip
    elif n == 3:
        m = np.c_[src, np.ones(3)]
        if abs(np.linalg.det(m)) < 1e-9 * max(1.0, np.abs(src).max() ** 2):
            raise ValueError("The three points are on a line.")
        t = np.vstack([np.linalg.solve(m, dst).T, [0, 0, 1]])
    else:
        t = homography(src, dst)
    res = apply_homography(t, src) - dst
    return t, float(np.sqrt((res ** 2).sum(axis=1).mean()))


def check_corners(ref_pts, photo_pts) -> None:
    """Raise ValueError if the points clicked on the photo cannot be the reference points (plate
    coordinates, e.g. the corners of the sample area) seen from the sample side."""
    p = np.asarray(photo_pts, float)
    if len(p) != 4:
        raise ValueError("Click the four reference points.")
    # convex, in the same turning sense as the plate corners (image y points down: a front view keeps
    # the sense; a mirrored photo, or corners clicked in the wrong order, reverse it or cross over)
    q = np.array(ref_pts, float)
    q[:, 1] *= -1
    cross = []
    for i in range(4):
        a, b, c = p[i], p[(i + 1) % 4], p[(i + 2) % 4]
        cross.append((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]))
    ref = (q[1, 0] - q[0, 0]) * (q[2, 1] - q[1, 1]) - (q[1, 1] - q[0, 1]) * (q[2, 0] - q[1, 0])
    if not all(np.sign(c) == np.sign(ref) and abs(c) > 1e-9 for c in cross):
        raise ValueError("The points must be clicked in the order of the numbers in the right view "
                         "(1 top left, 2 top right, 3 bottom right, 4 bottom left, tab at the top); "
                         "drag the markers or clear them.")


@dataclass
class Rectified:
    """A photo resampled on the plate grid: pixel (row, col) has its centre at
    u = u0 + (col + 0.5) / px_per_mm, v = v1 - (row + 0.5) / px_per_mm."""

    pixels: np.ndarray  # (rows, cols, 3) uint8
    valid: np.ndarray  # (rows, cols) bool: inside the photo
    u0: float
    v1: float
    px_per_mm: float

    def plate_bounds(self) -> Rect:
        rows, cols = self.valid.shape
        return (self.u0, self.v1 - rows / self.px_per_mm, self.u0 + cols / self.px_per_mm, self.v1)

    def index(self, u: float, v: float) -> tuple[int, int]:
        """(row, col) of the pixel holding the plate point (u, v)."""
        return int(np.floor((self.v1 - v) * self.px_per_mm)), int(np.floor((u - self.u0) * self.px_per_mm))

    def mask_of(self, rect: Rect) -> np.ndarray:
        """Pixels whose centre lies in the plate rectangle (u0, v0, u1, v1)."""
        rows, cols = self.valid.shape
        u = self.u0 + (np.arange(cols) + 0.5) / self.px_per_mm
        v = self.v1 - (np.arange(rows) + 0.5) / self.px_per_mm
        return ((v >= rect[1]) & (v <= rect[3]))[:, None] & ((u >= rect[0]) & (u <= rect[2]))[None, :]


def plate_view_bounds(plate: PlateGeometry, margin: float = 0.5) -> Rect:
    top = plate.height / 2 + plate.neck_height + plate.tab_height
    return (-plate.width / 2 - margin, plate.lowest_v() - margin, plate.width / 2 + margin, top + margin)


def rectify(image: np.ndarray, h_plate_to_photo: np.ndarray, bounds: Rect, px_per_mm: float = PX_PER_MM) -> Rectified:
    """Resample the photo on a plate grid covering `bounds` (bilinear)."""
    u0, v0, u1, v1 = bounds
    cols, rows = int(round((u1 - u0) * px_per_mm)), int(round((v1 - v0) * px_per_mm))
    u = u0 + (np.arange(cols) + 0.5) / px_per_mm
    v = v1 - (np.arange(rows) + 0.5) / px_per_mm
    uu, vv = np.meshgrid(u, v)
    xy = apply_homography(h_plate_to_photo, np.c_[uu.ravel(), vv.ravel()])
    # photo pixel (r, c) has its centre at x = c + 0.5, y = r + 0.5
    x, y = xy[:, 0] - 0.5, xy[:, 1] - 0.5
    hgt, wid = image.shape[:2]
    valid = (x >= 0) & (y >= 0) & (x <= wid - 1) & (y <= hgt - 1)
    x, y = np.clip(x, 0, wid - 1), np.clip(y, 0, hgt - 1)
    c0, r0 = np.minimum(x.astype(int), wid - 2 if wid > 1 else 0), np.minimum(y.astype(int), hgt - 2 if hgt > 1 else 0)
    c1, r1 = np.minimum(c0 + 1, wid - 1), np.minimum(r0 + 1, hgt - 1)
    fx, fy = (x - c0)[:, None], (y - r0)[:, None]
    img = image.astype(np.float32)
    out = (img[r0, c0] * (1 - fx) * (1 - fy) + img[r0, c1] * fx * (1 - fy)
           + img[r1, c0] * (1 - fx) * fy + img[r1, c1] * fx * fy)
    out[~valid] = 0
    pixels = np.clip(out + 0.5, 0, 255).astype(np.uint8).reshape(rows, cols, 3)
    return Rectified(pixels, valid.reshape(rows, cols), u0, v1, px_per_mm)


def rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """sRGB (uint8) -> CIELAB (D65), float32, same leading shape."""
    c = rgb.astype(np.float32) / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    m = np.array([[0.4124564, 0.3575761, 0.1804375],
                  [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]], np.float32)
    xyz = c @ m.T / np.array([0.95047, 1.0, 1.08883], np.float32)
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    lab = np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], axis=-1)
    return lab.astype(np.float32)


def _box_blur(a: np.ndarray, r: int) -> np.ndarray:
    """Mean over a (2r+1)^2 window (edges replicated), along the first two axes."""
    if r <= 0:
        return a
    pad = [(r, r), (r, r)] + [(0, 0)] * (a.ndim - 2)
    p = np.pad(a, pad, mode="edge").astype(np.float64)
    c = np.cumsum(np.cumsum(p, axis=0), axis=1)
    c = np.pad(c, [(1, 0), (1, 0)] + [(0, 0)] * (a.ndim - 2))
    k = 2 * r + 1
    s = c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]
    return (s / (k * k)).astype(a.dtype)


def _dilate(m: np.ndarray, r: int) -> np.ndarray:
    if r <= 0:
        return m
    return _box_blur(m.astype(np.float32), r) > 1e-6


def _erode(m: np.ndarray, r: int) -> np.ndarray:
    if r <= 0:
        return m
    return _box_blur(m.astype(np.float32), r) > 1 - 1e-6


def label_regions(mask: np.ndarray) -> list[np.ndarray]:
    """Connected (8-neighbour) regions of a boolean mask, each as an (n, 2) array of (row, col)."""
    rows, cols = mask.shape
    seen = np.zeros_like(mask, bool)
    regions = []
    for r0, c0 in zip(*np.nonzero(mask)):
        if seen[r0, c0]:
            continue
        seen[r0, c0] = True
        queue, pts = deque([(r0, c0)]), []
        while queue:
            r, c = queue.popleft()
            pts.append((r, c))
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < rows and 0 <= cc < cols and mask[rr, cc] and not seen[rr, cc]:
                        seen[rr, cc] = True
                        queue.append((rr, cc))
        regions.append(np.asarray(pts))
    return regions


@dataclass
class Detection:
    """A sample found on the photo: bounding box in plate mm and its mean colour difference
    (from the bare plate, or from the nearest picked sample colour)."""

    u0: float
    v0: float
    u1: float
    v1: float
    area: float  # mm^2 of the region (not of the box)
    delta_e: float
    manual: bool = False  # drawn or merged by the user (kept when the detection is run again)

    @classmethod
    def merged(cls, parts: list[Detection]) -> Detection:
        """One box around several pieces (a sample broken up by paint or wires)."""
        area = sum(d.area for d in parts)
        return cls(min(d.u0 for d in parts), min(d.v0 for d in parts), max(d.u1 for d in parts),
                   max(d.v1 for d in parts), area, sum(d.delta_e * d.area for d in parts) / area, manual=True)

    @property
    def rect(self) -> Rect:
        return self.u0, self.v0, self.u1, self.v1

    @property
    def center(self) -> tuple[float, float]:
        return (self.u0 + self.u1) / 2, (self.v0 + self.v1) / 2

    @property
    def size(self) -> tuple[float, float]:
        return self.u1 - self.u0, self.v1 - self.v0


def overlap(a: Rect, b: Rect) -> float:
    """Intersection over union of two plate rectangles (0 … 1)."""
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    inter = w * h
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


@dataclass
class DetectionResult:
    detections: list[Detection]
    mask: np.ndarray  # final foreground mask on the rectified grid
    background: np.ndarray  # Lab colour of the bare plate used (NaN in sample colour mode without one)
    delta_e: np.ndarray  # colour difference used, rectified grid


def background_lab(lab: np.ndarray, area: np.ndarray, threshold: float) -> np.ndarray:
    """Colour of the bare sample area: median, refined over the pixels close to it.

    Works while the bare plate is the largest uniform part of the area;
    otherwise the user picks the background on the photo."""
    pts = lab[area]
    if len(pts) == 0:
        raise ValueError("The sample area is not on the photo.")
    bg = np.median(pts, axis=0)
    for _ in range(4):
        close = pts[np.linalg.norm(pts - bg, axis=1) < threshold]
        if len(close) < 0.05 * len(pts):
            break
        bg = np.median(close, axis=0)
    return bg


def detect_samples(rect: Rectified, area_rect: Rect, threshold: float = 12.0, min_area: float = 0.2,
                   margin: float = 0.15, smooth: float = 0.1, background: np.ndarray | None = None,
                   sample_colors=None) -> DetectionResult:
    """Samples in the plate rectangle `area_rect` (the sample area).

    Two modes: without `sample_colors` a sample is what differs from the bare
    plate by more than `threshold`; with them (Lab colours picked on samples)
    it is what is within `threshold` of one of them, which leaves out other
    things on the plate (silver paint, glue, wires).

    threshold: ΔE (CIELAB) above which a pixel is not bare plate / not a sample colour;
    min_area: smaller regions (mm^2) are dropped (dust, scratches);
    margin: mm left out along the sample area border (its edge on the photo);
    smooth: mm, radius of the noise filter and of the clean-up of the mask;
    background: Lab colour of the bare plate (None: estimated)."""
    s = rect.px_per_mm
    u0, v0, u1, v1 = area_rect
    area = rect.mask_of((u0 + margin, v0 + margin, u1 - margin, v1 - margin)) & _erode(rect.valid, 1)
    r = max(0, int(round(smooth * s)))
    lab = rgb_to_lab(_box_blur(rect.pixels.astype(np.float32), max(1, r // 2)).clip(0, 255))
    if sample_colors is not None and len(sample_colors):
        bg = np.asarray(background, np.float32) if background is not None else np.full(3, np.nan, np.float32)
        de = np.min([np.linalg.norm(lab - np.asarray(c, np.float32), axis=-1) for c in sample_colors], axis=0)
        de[~area] = np.inf
        fg = de < threshold
    else:
        bg = np.asarray(background, np.float32) if background is not None else background_lab(lab, area, threshold)
        de = np.linalg.norm(lab - bg, axis=-1)
        de[~area] = 0
        fg = de > threshold
    # opening removes specks, closing fills small gaps (glare, grain) inside a sample
    fg = _dilate(_erode(fg, r), r)
    fg = _erode(_dilate(fg, r), r) & area
    detections = []
    for pts in label_regions(fg):
        n_mm2 = len(pts) / s ** 2
        if n_mm2 < min_area:
            continue
        rows, cols = pts[:, 0], pts[:, 1]
        d = Detection(
            u0=rect.u0 + cols.min() / s, u1=rect.u0 + (cols.max() + 1) / s,
            v0=rect.v1 - (rows.max() + 1) / s, v1=rect.v1 - rows.min() / s,
            area=n_mm2, delta_e=float(de[rows, cols].mean()),
        )
        # a sample cut by the left-out border reaches the sample area edge
        tol = 1.5 / s
        if d.u0 < u0 + margin + tol:
            d.u0 = u0
        if d.u1 > u1 - margin - tol:
            d.u1 = u1
        if d.v0 < v0 + margin + tol:
            d.v0 = v0
        if d.v1 > v1 - margin - tol:
            d.v1 = v1
        detections.append(d)
    # reading order: top to bottom, then left to right
    detections.sort(key=lambda d: (-round(d.center[1]), d.center[0]))
    return DetectionResult(detections, fg, bg, de)


# -- oblique photos: a camera model from points at several heights ---------------------------------------------
# A homography maps one plane exactly (the sample-area plane, from its four corners), whatever the viewing angle.
# Things at other heights (thick samples, the back plate, the tab) appear shifted on an oblique photo (parallax).
# With points at two or more heights a full pinhole camera P (3 x 4, photo ~ P (u, v, w, 1)) is fitted; the plane
# at any height w then maps with the homography [p1, p2, w p3 + p4]. Optional: the four corners are enough for
# photos taken from about straight above.

def reference_points_3d(plate: PlateGeometry) -> list[tuple[str, tuple[float, float, float]]]:
    """Points that can be clicked on a plate photo, with their plate coordinates (u, v, w) in mm, w = height above
    the back face. The first eight (sample-area corners, back-plate top corners, tab top corners) are the ones the
    photo window asks for in 3D mode; the others are optional extras."""
    top = plate.total_thickness
    base = plate.base_thickness
    w, h = plate.width / 2, plate.height / 2
    tab_top = h + plate.neck_height + plate.tab_height
    tw = plate.tab_width / 2
    out = [(name, (u, v, top)) for name, (u, v) in corner_points(plate)]
    out += [("back plate top left corner", (-w, h, base)), ("back plate top right corner", (w, h, base)),
            ("tab top left corner", (-tw, tab_top, base)), ("tab top right corner", (tw, tab_top, base)),
            ("back plate bottom left (end of the chamfer)", (-w + plate.chamfer_width, -h, base)),
            ("back plate bottom right (end of the chamfer)", (w - plate.chamfer_width, -h, base)),
            ("tab bottom left (shoulder)", (-tw, h + plate.neck_height, base)),
            ("tab bottom right (shoulder)", (tw, h + plate.neck_height, base))]
    if plate.contact_block:
        b0, c0, b1, _ = plate.contact_block
        out += [("contact block bottom left", (b0, c0, plate.contact_block_top)),
                ("contact block bottom right", (b1, c0, plate.contact_block_top))]
    return out


GUI_POINTS_3D = 8  # the photo window asks for the first eight of reference_points_3d


def project(p: np.ndarray, pts3d) -> np.ndarray:
    """Photo pixels of plate points (u, v, w) with the camera matrix p."""
    x = np.c_[np.asarray(pts3d, float).reshape(-1, 3), np.ones(len(np.asarray(pts3d).reshape(-1, 3)))] @ p.T
    return x[:, :2] / x[:, 2:3]


def camera_matrix(pts3d, pts2d, refine: bool = True) -> tuple[np.ndarray, float, np.ndarray]:
    """3 x 4 camera matrix from plate points (u, v, w) and their photo pixels: normalised DLT, then a least-squares
    refinement of the pixel residuals. Returns (P, rms residual in px, residual per point in px).

    Needs at least 6 points, not all at the same height (on one plane the camera is not determined: use the
    four-corner homography)."""
    X, x = np.asarray(pts3d, float), np.asarray(pts2d, float)
    if X.ndim != 2 or X.shape[1] != 3 or x.shape != (len(X), 2):
        raise ValueError("Give (u, v, w) plate points and their (x, y) photo pixels.")
    if len(X) < 6:
        raise ValueError(f"The 3D correction needs at least 6 points ({len(X)} given).")
    if np.ptp(X[:, 2]) < 0.5:
        raise ValueError("The points must be at different heights (e.g. sample-area corners on the riser and "
                         "corners of the back plate or of the tab).")
    cx, sx = X.mean(axis=0), np.sqrt(((X - X.mean(axis=0)) ** 2).sum(axis=1)).mean() / np.sqrt(3)
    cp, sp = x.mean(axis=0), np.sqrt(((x - x.mean(axis=0)) ** 2).sum(axis=1)).mean() / np.sqrt(2)
    T3 = np.diag([1 / sx] * 3 + [1.0])
    T3[:3, 3] = -cx / sx
    T2 = np.diag([1 / sp, 1 / sp, 1.0])
    T2[:2, 2] = -cp / sp
    Xn = (np.c_[X, np.ones(len(X))] @ T3.T)
    xn = (np.c_[x, np.ones(len(x))] @ T2.T)[:, :2]
    rows = []
    for (a, b, c, d), (u, v) in zip(Xn, xn):
        rows.append([a, b, c, d, 0, 0, 0, 0, -u * a, -u * b, -u * c, -u * d])
        rows.append([0, 0, 0, 0, a, b, c, d, -v * a, -v * b, -v * c, -v * d])
    _, sv, vt = np.linalg.svd(np.asarray(rows))
    if sv[-2] < 1e-8 * sv[0]:
        raise ValueError("The points do not determine the camera (degenerate layout).")
    pn = vt[-1].reshape(3, 4)
    if refine:
        def res(q):
            return (project(q.reshape(3, 4), Xn[:, :3]) - xn).ravel()
        q = pn.ravel() / np.linalg.norm(pn)
        for _ in range(20):
            r = res(q)
            jac = np.column_stack([(res(q + e) - r) / 1e-7 for e in np.eye(12) * 1e-7])
            step = np.linalg.lstsq(jac, -r, rcond=None)[0]
            q = q + step
            q /= np.linalg.norm(q)
            if np.max(np.abs(step)) < 1e-12:
                break
        pn = q.reshape(3, 4)
    p = np.linalg.inv(T2) @ pn @ T3
    p /= np.linalg.norm(p[2, :3])
    if (np.c_[X, np.ones(len(X))] @ p[2]).mean() < 0:  # points in front of the camera: positive depth
        p = -p
    r = np.linalg.norm(project(p, X) - x, axis=1)
    return p, float(np.sqrt((r ** 2).mean())), r


def plane_homography(p: np.ndarray, w: float) -> np.ndarray:
    """Plate (u, v) at height w -> photo pixels, from the camera matrix p."""
    h = np.column_stack([p[:, 0], p[:, 1], w * p[:, 2] + p[:, 3]])
    return h / h[2, 2]


def check_mirror_3d(p: np.ndarray, w: float) -> None:
    """A photo seen from the sample side keeps the turning sense of the plate (raises ValueError if mirrored)."""
    h = plane_homography(p, w)
    corners = np.array([(-1.0, 1.0), (1.0, 1.0), (1.0, -1.0), (-1.0, -1.0)])
    check_corners([tuple(c) for c in corners], apply_homography(h, corners))
