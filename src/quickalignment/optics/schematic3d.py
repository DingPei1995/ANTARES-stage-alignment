"""Matplotlib 3-D schematic of the ZP / capillary geometry (lab frame, mm, to scale).

Only the optic in the beam is drawn (ZP + OSA, or the capillary), with the bodies and working distances of the
QuickAlignment anti-collision model (`core.collision.DEFAULT_OPTIC_BODIES`, `ANALYZER_A1`), placed at the focus the
optics model gives for the motors. The motor arrows show the + directions.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from ..core.collision import ANALYZER_A1, DEFAULT_OPTIC_BODIES, SheetBody, SolidBody
from ..core.stage import N_HAT, T_HAT, Z_HAT
from .geometry import CPX_DIR, ZPX_DIR, OpticsGeometry, OpticsMotors

BEAM, ZP, CAP, GRAY, MOTOR, AXES = "#EF9F27", "#7F77DD", "#1D9E75", "#888780", "#D85A30", "#378ADD"
X_HAT = np.array([1.0, 0.0, 0.0])
ARROW = 5.0  # mm, length of the motor arrows

VIEWS = {  # name: (elev, azim, orthographic, axis seen end-on)
    "perspective": (22, -55, False, None),
    "top (from +z)": (90, -90, True, "z"),
    "side (from +x)": (0, 0, True, "x"),
    "along the beam (from downstream)": (0, 90, True, "y"),
}


def _circle(c, r, u, v, n=40):
    t = np.linspace(0, 2 * np.pi, n)
    return np.asarray(c)[:, None] + r * (np.outer(u, np.cos(t)) + np.outer(v, np.sin(t)))


def _rect(c, half_w, half_h, u, v):
    pts = [c + a * half_w * u + b * half_h * v for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1), (-1, -1))]
    return np.array(pts).T


class _Painter:
    def __init__(self, ax, labels: str):
        self.ax, self.labels = ax, labels  # labels: "all", "motors" or "none"

    def text(self, p, s, color, kind="all"):
        if self.labels == "all" or (self.labels == "motors" and kind == "motors"):
            self.ax.text(*np.asarray(p, float), s, color=color, fontsize=8.5)

    def arrow(self, p, d, s, color=MOTOR, length=ARROW, kind="motors"):
        p, d = np.asarray(p, float), np.asarray(d, float)
        self.ax.quiver(*p, *(length * d), color=color, arrow_length_ratio=0.25, linewidth=1.4)
        self.text(p + 1.15 * length * d, s, color, kind)


def _solid(ax, body: SolidBody, focus, axis, color, lw=1.2):
    """Wireframe of a collision body: front and back outlines and the edges between them."""
    axis = axis / np.linalg.norm(axis)
    side = np.cross(axis, Z_HAT)
    side = side / np.linalg.norm(side) if np.linalg.norm(side) > 1e-9 else X_HAT
    up = np.cross(side, axis)
    origin = np.asarray(focus, float) + body.offset * side
    s0, s1 = body.distance, body.distance + body.length
    r0, r1 = body.radius_at(s0), body.radius_at(s1)
    c0, c1 = origin + s0 * axis, origin + s1 * axis
    if body.square:
        h0 = r0 + body.extra_height
        h1 = r1 + body.extra_height
        f0, f1 = _rect(c0, r0, h0, side, up), _rect(c1, r1, h1, side, up)
        for p0, p1 in zip(f0.T[:4], f1.T[:4]):
            ax.plot(*np.c_[p0, p1], color=color, linewidth=lw * 0.7)
    else:
        f0, f1 = _circle(c0, r0, side, up), _circle(c1, r1, side, up)
        for k in (0, 10, 20, 30):
            ax.plot(*np.c_[f0[:, k], f1[:, k]], color=color, linewidth=lw * 0.7)
    ax.plot(*f0, color=color, linewidth=lw)
    ax.plot(*f1, color=color, linewidth=lw)
    return c0, c1, side


def _sheet(ax, body: SheetBody, focus, axis, color):
    """Bent upright sheet (OSA shield): its top-view polyline at the top and bottom, and the bends."""
    axis = axis / np.linalg.norm(axis)
    side = np.cross(axis, Z_HAT)
    side = side / np.linalg.norm(side)  # + towards the analyzer side (-x for a beam along +y)
    pts = [np.asarray(focus, float) + (body.distance + a) * axis + x * side for a, x in body.points]
    for dz in (-body.height / 2, body.height / 2):
        ax.plot(*np.array([p + dz * Z_HAT for p in pts]).T, color=color, linewidth=1.0)
    for p in pts:
        ax.plot(*np.c_[p - body.height / 2 * Z_HAT, p + body.height / 2 * Z_HAT], color=color, linewidth=0.6)


def _analyzer(pt: _Painter, ax):
    a = ANALYZER_A1  # front face at its distance from the focus, cone widening behind it
    shown = SolidBody(a.name, a.distance, a.tip_radius, a.half_angle, length=15.0)
    _solid(ax, shown, np.zeros(3), -N_HAT, GRAY, lw=0.8)
    ax.plot(*np.c_[np.zeros(3), -a.distance * N_HAT], color=GRAY, linestyle=":", linewidth=0.8)
    pt.text(-(a.distance + 15.0) * N_HAT + [0, 0, 12], f"analyzer (-n), front {a.distance:g} mm", GRAY)


def draw(ax, geometry: OpticsGeometry, motors: OpticsMotors, view: str = "perspective", labels: str = "all") -> None:
    pt = _Painter(ax, labels)
    optic = geometry.active_optic(motors)

    ax.plot([0, 0], [-45, 15], [0, 0], color=BEAM, linewidth=2)
    pt.text((0, 15, 1.5), "ZP beam (reference) +y", BEAM)
    corners = [(-7, -7), (7, -7), (7, 7), (-7, 7), (-7, -7)]
    plate = np.array([a * T_HAT + np.array([0, 0, b]) for a, b in corners]).T
    ax.plot(*plate, color=GRAY)
    pt.text(7 * T_HAT + [0, 0, -9], "sample at SN_f (origin)", GRAY)
    _analyzer(pt, ax)

    # only the optic in the beam is drawn (nothing when both are parked)
    if optic == "zone plate":
        _zone_plate(pt, ax, geometry, motors)
    elif optic == "capillary":
        b = geometry.capillary_beam(motors)
        _capillary(pt, ax, b.focus, b.direction)
        ax.plot(*np.c_[b.focus - 45 * b.direction, b.focus + 15 * b.direction], color=CAP, linestyle="--",
                linewidth=1.0)
        pt.text(b.focus + 15 * b.direction + [0, 0, -3], "capillary beam", CAP)

    o = np.array([12.0, -40.0, -17.0])
    for d, name in (([1, 0, 0], "+x"), ([0, 1, 0], "+y"), ([0, 0, 1], "+z")):
        pt.arrow(o, d, name, color=AXES)
    ax.set_xlim(-45, 20)
    ax.set_ylim(-45, 15)
    ax.set_zlim(-20, 20)
    ax.set_box_aspect((65, 60, 40))
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("y, beam (mm)")
    ax.set_zlabel("z (mm)")
    elev, azim, ortho, end_on = VIEWS[view]
    ax.view_init(elev=elev, azim=azim)
    if ortho:
        ax.set_proj_type("ortho")
    if end_on:  # its ticks collapse onto one point
        axis = {"x": ax.xaxis, "y": ax.yaxis, "z": ax.zaxis}[end_on]
        axis.set_ticklabels([])
        axis.set_label_text("")


def _zone_plate(pt: _Painter, ax, geometry: OpticsGeometry, motors: OpticsMotors) -> None:
    """Zone plate at the lens position of the optics model (f = 0.256 E upstream of its focus), OSA shield at the
    position its motors give; shapes from the anti-collision model."""
    up = np.array([0.0, -1.0, 0.0])  # from the focus into the optic (upstream)
    focus = geometry.zone_plate_focus(motors)
    lens = geometry.zone_plate_lens(motors)
    osa = geometry.osa_position(motors)
    for body in DEFAULT_OPTIC_BODIES["zone plate + OSA"]:
        if isinstance(body, SheetBody):
            sheet = replace(body, distance=0.0)
            _sheet(ax, sheet, osa, up, ZP)
            pt.text(osa + 2 * up + [-6, 0, body.height / 2 + 1], f"OSA ({-osa[1]:.1f} mm before the focus)", ZP)
        else:
            wd = float(focus[1] - lens[1])
            c0, _, _ = _solid(ax, replace(body, distance=wd), focus, up, ZP, lw=1.5)
            pt.text(c0 + [6, 0, -7], f"zone plate (WD {wd:.2f})", ZP)
            pt.arrow(c0, [0, 1, 0], "+ZPS")
            pt.arrow(c0 + [0, 0, body.tip_radius], [0, 0, 1], "+ZPZ")
            pt.arrow(c0 + body.tip_radius * ZPX_DIR, ZPX_DIR, "+ZPX")


def _capillary(pt: _Painter, ax, focus, direction) -> None:
    up = -np.asarray(direction, float)
    bodies = DEFAULT_OPTIC_BODIES["capillary"]
    ends = []
    for body in bodies:
        ends.append(_solid(ax, body, focus, up, CAP, lw=1.3))
    front, rear = ends[0][0], ends[-1][1]
    pt.text(rear + [0, 0, -10], f"capillary (WD {bodies[0].distance:g})", CAP)
    mid = 0.5 * (ends[2][0] + ends[2][1])
    pt.arrow(mid + [0, 0, 4.0], [0, 0, 1], "+ZPZ (shared)")
    pt.arrow(mid + 5.0 * CPX_DIR, CPX_DIR, "+CPX")
    pt.arrow(rear, -up, "")
    pt.text(rear + [2, -4, -5], "+CPS (+y)", MOTOR, "motors")
    # rotations about an unknown pivot, drawn at the rear end
    length = np.linalg.norm(front - rear)
    a = np.linspace(0, np.radians(12), 13)
    side = np.cross(up, Z_HAT)
    side = side / np.linalg.norm(side)
    arc_rz = np.array([rear + length * (np.cos(t) * -up - np.sin(t) * side) for t in a]).T  # tip to +x
    arc_rx = np.array([rear + length * (np.cos(t) * -up + np.sin(t) * Z_HAT) for t in a]).T  # tip up
    ax.plot(*arc_rz, color=MOTOR)
    ax.plot(*arc_rx, color=MOTOR)
    pt.text(arc_rz[:, -1] + [1, 0, -4], "+Cap Rz (provisional)", MOTOR, "motors")
    pt.text(arc_rx[:, -1] + [0, 0, 3.5], "+Cap Rx (tip up)", MOTOR, "motors")
    ax.scatter(*rear, color=MOTOR, s=12)
    pt.text(rear + [-9, 0, 3], "pivot ?", MOTOR)


def show(geometry: OpticsGeometry, motors_list, titles, save: str | None = None) -> None:
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=(7 * len(motors_list), 6.5))
    for i, (m, t) in enumerate(zip(motors_list, titles)):
        ax = fig.add_subplot(1, len(motors_list), i + 1, projection="3d")
        draw(ax, geometry, m)
        ax.set_title(t, fontsize=10)
    fig.tight_layout()
    if save:
        fig.savefig(save, dpi=130)
    else:
        plt.show()


__all__ = ["VIEWS", "draw", "show"]
