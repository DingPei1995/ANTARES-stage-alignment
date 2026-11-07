"""Photos for the agent: reading (EXIF orientation applied), pixel grids to read coordinates from, overlays.

An agent reads positions on a photo by eye. To make that precise it looks at the photo with a labelled pixel
grid (`grid_png`), zooms into a region to place a corner within a few pixels, and checks the result on an
overlay of the plate model drawn back onto the photo (`overlay_png`). All coordinates are pixels of the
photo as stored on disk after its EXIF rotation, x to the right and y down, origin at the top left corner.

Needs Pillow (installed with matplotlib).
"""

from __future__ import annotations

import io
import math
from pathlib import Path

import numpy as np

from ..alignment.photo import apply_homography
from ..core.geometry import PlateGeometry, SampleLayout
from .common import APIError

MAX_SIZE = 1400  # px, longest side of an image sent to the agent (vision models downscale larger images)


def _pil():
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageOps
    except ImportError:  # pragma: no cover - Pillow comes with matplotlib
        raise APIError("Reading photos needs Pillow: pip install pillow") from None
    return Image, ImageDraw, ImageFont, ImageOps


def read_image(path: str | Path) -> np.ndarray:
    """(rows, cols, 3) uint8 RGB of a photo, turned upright by its EXIF orientation (as photo viewers show it)."""
    Image, _, _, ImageOps = _pil()
    path = Path(path).expanduser()
    if not path.is_file():
        raise APIError(f"No photo at {path}. Give the full path of the image file.")
    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)
            return np.asarray(im.convert("RGB"))
    except OSError as exc:
        raise APIError(f"The photo {path} could not be read: {exc}") from None


def _font(size: int):
    _, _, ImageFont, _ = _pil()
    for name in ("DejaVuSans.ttf", "Arial.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def _png(im) -> bytes:
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def nice_step(span: float, lines: int = 10) -> float:
    """A round grid step (1, 2, 5 x 10^n) giving about `lines` lines over `span`."""
    raw = max(span / max(lines, 1), 1e-9)
    p = 10 ** math.floor(math.log10(raw))
    return next(m * p for m in (1, 2, 5, 10) if m * p >= raw)


def crop_box(shape, region) -> tuple[int, int, int, int]:
    """(x0, y0, x1, y1) integer pixel box of `region` ([x0, y0, x1, y1], None: the whole photo), clipped."""
    rows, cols = shape[:2]
    if region is None:
        return 0, 0, cols, rows
    if len(region) != 4:
        raise APIError("region: give [x0, y0, x1, y1] in photo pixels.")
    x0, y0, x1, y1 = (float(v) for v in region)
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    x0, y0 = max(0, int(math.floor(x0))), max(0, int(math.floor(y0)))
    x1, y1 = min(cols, int(math.ceil(x1))), min(rows, int(math.ceil(y1)))
    if x1 - x0 < 4 or y1 - y0 < 4:
        raise APIError(f"region {region} is not on the photo ({cols} x {rows} px).")
    return x0, y0, x1, y1


def grid_png(rgb: np.ndarray, region=None, step: float | None = None, marks=(), max_size: int = MAX_SIZE) -> tuple[bytes, dict]:
    """The photo (or a region of it) with a pixel grid labelled in photo pixels, and optional marks.

    marks: [{"x": .., "y": .., "label": "1", "color": "red"}] drawn as cross-hairs at photo pixels.
    Returns (PNG bytes, info: the region shown, the grid step, the scale of the image sent)."""
    Image, ImageDraw, _, _ = _pil()
    x0, y0, x1, y1 = crop_box(rgb.shape, region)
    im = Image.fromarray(rgb[y0:y1, x0:x1])
    scale = min(1.0 if region is None else 8.0, max_size / max(im.size))  # zoom regions up to 8x
    size = (max(1, round(im.size[0] * scale)), max(1, round(im.size[1] * scale)))
    im = im.resize(size, Image.LANCZOS if scale < 1 else Image.NEAREST if scale >= 3 else Image.BICUBIC)
    # a white margin for the labels
    pad_l, pad_t = 58, 22
    canvas = Image.new("RGB", (size[0] + pad_l, size[1] + pad_t), "white")
    canvas.paste(im, (pad_l, pad_t))
    draw = ImageDraw.Draw(canvas)
    font = _font(13)
    step = step or nice_step(max(x1 - x0, y1 - y0), 10)

    def to_img(x, y):
        return pad_l + (x - x0) * scale, pad_t + (y - y0) * scale

    gx = math.ceil(x0 / step) * step
    while gx <= x1:
        px = to_img(gx, y0)[0]
        draw.line([(px, pad_t), (px, pad_t + size[1])], fill=(0, 255, 255), width=1)
        draw.text((px + 2, 3), f"{gx:g}", fill="black", font=font)
        gx += step
    gy = math.ceil(y0 / step) * step
    while gy <= y1:
        py = to_img(x0, gy)[1]
        draw.line([(pad_l, py), (pad_l + size[0], py)], fill=(0, 255, 255), width=1)
        draw.text((2, py - 7), f"{gy:g}", fill="black", font=font)
        gy += step
    for mark in marks or ():
        x, y = to_img(float(mark["x"]), float(mark["y"]))
        color = mark.get("color", "red")
        r = 9
        draw.line([(x - r, y), (x + r, y)], fill=color, width=2)
        draw.line([(x, y - r), (x, y + r)], fill=color, width=2)
        if mark.get("label"):
            draw.text((x + 6, y + 4), str(mark["label"]), fill=color, font=_font(15))
    info = {"region": [x0, y0, x1, y1], "grid_step_px": step, "image_scale": round(scale, 4),
            "photo_size": [int(rgb.shape[1]), int(rgb.shape[0])],
            "how_to_read": "grid lines (cyan) are labelled in photo pixels: x along the top, y down the left side"}
    return _png(canvas), info


def _poly(h_plate_to_photo, pts, n: int = 12):
    """Plate polygon -> photo pixel polygon (edges subdivided, the homography bends nothing but this is exact)."""
    out = []
    for a, b in zip(pts, pts[1:] + pts[:1]):
        for t in np.linspace(0, 1, n, endpoint=False):
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return [tuple(p) for p in apply_homography(h_plate_to_photo, out)]


def overlay_png(rgb: np.ndarray, h_plate_to_photo: np.ndarray, plate: PlateGeometry, layout: SampleLayout | None,
                corners_px=(), max_size: int = MAX_SIZE, region=None) -> bytes:
    """The photo with the plate model drawn on it: sample area (green), samples (blue, with names), devices (red),
    the clicked corners (numbered, yellow), and the plate outline (white)."""
    Image, ImageDraw, _, _ = _pil()
    x0, y0, x1, y1 = crop_box(rgb.shape, region)
    im = Image.fromarray(rgb).convert("RGB")
    draw = ImageDraw.Draw(im, "RGBA")
    width = max(2, round(max(im.size) / 600))
    font = _font(max(14, round(max(im.size) / 70)))
    draw.line(_poly(h_plate_to_photo, plate.outline(), 4) + [_poly(h_plate_to_photo, plate.outline(), 4)[0]],
              fill=(255, 255, 255, 200), width=width)
    u0, v0, u1, v1 = plate.riser_bounds()
    area = _poly(h_plate_to_photo, [(u0, v1), (u1, v1), (u1, v0), (u0, v0)])
    draw.line(area + [area[0]], fill=(0, 220, 0, 255), width=width)
    for s in (layout.samples if layout else []):
        a, b, c, d = s.bounds()
        quad = _poly(h_plate_to_photo, [(a, d), (c, d), (c, b), (a, b)])
        draw.polygon(quad, outline=(30, 120, 255, 255), fill=(30, 120, 255, 40))
        draw.line(quad + [quad[0]], fill=(30, 120, 255, 255), width=width)
        cx, cy = apply_homography(h_plate_to_photo, [(s.u, s.v)])[0]
        draw.text((cx, cy), s.name, fill=(255, 255, 0, 255), font=font, anchor="mm", stroke_width=2,
                  stroke_fill=(0, 0, 0, 255))
        for dev in s.devices:
            du, dv = dev.position(s)
            px, py = apply_homography(h_plate_to_photo, [(du, dv)])[0]
            r = 2.5 * width
            draw.ellipse([px - r, py - r, px + r, py + r], outline=(255, 40, 40, 255), width=width)
            draw.text((px + 2 * r, py), dev.name, fill=(255, 80, 80, 255), font=font, anchor="lm", stroke_width=2,
                      stroke_fill=(0, 0, 0, 255))
    for i, (x, y) in enumerate(corners_px):
        r = 3 * width
        draw.line([(x - r, y), (x + r, y)], fill=(255, 230, 0, 255), width=width)
        draw.line([(x, y - r), (x, y + r)], fill=(255, 230, 0, 255), width=width)
        draw.text((x + r, y + r), str(i + 1), fill=(255, 230, 0, 255), font=font, stroke_width=2,
                  stroke_fill=(0, 0, 0, 255))
    im = im.crop((x0, y0, x1, y1))
    scale = min(1.0 if region is None else 4.0, max_size / max(im.size))
    if abs(scale - 1) > 1e-6:
        im = im.resize((max(1, round(im.size[0] * scale)), max(1, round(im.size[1] * scale))), Image.LANCZOS)
    return _png(im)


def plate_png(layout: SampleLayout, title: str = "", marks=(), size_in: float = 6.0) -> bytes:
    """The plate front view (tab up) with the samples and devices, axes in plate mm."""
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from matplotlib.patches import Polygon, Rectangle

    plate = layout.plate
    fig = Figure(figsize=(size_in, size_in * 1.15), dpi=110)
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    ax.add_patch(Polygon(plate.outline(), closed=True, fc="#d9d9d9", ec="#555", lw=1))
    u0, v0, u1, v1 = plate.riser_bounds()
    ax.add_patch(Rectangle((u0, v0), u1 - u0, v1 - v0, fc="#bfbfbf", ec="#2a8a2a", lw=1.5, label="sample area"))
    if plate.contact_block:
        b0, c0, b1, c1 = plate.contact_block
        ax.add_patch(Rectangle((b0, c0), b1 - b0, c1 - c0, fc="#e8d9a0", ec="#8a7a30", lw=1))
    for s in layout.samples:
        a, b, c, d = s.bounds()
        ax.add_patch(Rectangle((a, b), c - a, d - b, fc="#7fb0ff", ec="#1f5fbf", lw=1.2, alpha=0.8))
        ax.text(s.u, s.v, f"{s.name}\nH {s.height:g}", ha="center", va="center", fontsize=8)
        for dev in s.devices:
            du, dv = dev.position(s)
            ax.plot(du, dv, "o", ms=5, mfc="none", mec="#d01010")
            ax.text(du, dv - 0.25, dev.name, ha="center", va="top", fontsize=7, color="#d01010")
    for mark in marks or ():
        ax.plot(mark["x"], mark["y"], "x", color=mark.get("color", "#d01010"), ms=9, mew=2)
        if mark.get("label"):
            ax.text(mark["x"] + 0.2, mark["y"] + 0.2, mark["label"], color=mark.get("color", "#d01010"), fontsize=8)
    ax.plot(0, 0, "+", color="k", ms=8)
    w, h = plate.width / 2, plate.height / 2
    ax.set_xlim(-w - 0.7, w + 0.7)
    ax.set_ylim(min(-h, plate.lowest_v()) - 0.7, h + plate.neck_height + plate.tab_height + 0.5)
    ax.set_aspect("equal")
    ax.set_xlabel("x (mm, plate frame, front view)")
    ax.set_ylabel("y (mm, tab up)")
    ax.grid(True, lw=0.4, alpha=0.5)
    ax.set_title(title or plate.name, fontsize=9)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    return buf.getvalue()


__all__ = ["MAX_SIZE", "crop_box", "grid_png", "nice_step", "overlay_png", "plate_png", "read_image"]
