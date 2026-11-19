"""OpticsGeometry: the ZP / capillary 3-D geometry model, run on its own (does not change the other programs).

    python OpticsGeometry/OpticsGeometry.py                      reference geometry + 3-D schematic
    python OpticsGeometry/OpticsGeometry.py --nxs Cav/*.nxs      optic in use, focus, ST0 / SZ0 shift per file
    python OpticsGeometry/OpticsGeometry.py --focus capillary 0 0 0   motors putting that focus at a lab point
"""

from __future__ import annotations

import argparse
import glob
from pathlib import Path

from .geometry import CAP_RZ_SIGN, OpticsGeometry, OpticsGeometryConfig, OpticsMotors, default_config

DEFAULT_CONFIG = Path(__file__).resolve().parents[3] / "OpticsGeometry" / "optics_geometry.json"


def _v(p) -> str:
    return "(" + ", ".join(f"{float(x):+.4f}" for x in p) + ")"


def reference_text(g: OpticsGeometry) -> str:
    zp, cap = g.config.zone_plate, g.config.capillary
    rz = "tip towards the analyzer = negative" if CAP_RZ_SIGN < 0 else "tip towards the analyzer = positive"
    return "\n".join([
        "Lab frame: origin = analyzer focus, +x right, +y beam (downstream), +z up; analyzer on the -x side.",
        f"Zone plate reference (focus at the origin at {zp.energy:g} eV): ZPS {zp.zps:.4f}, ZPX {zp.zpx:.4f}, ZPZ {zp.zpz:.4f};"
        f" parked at ZPS {zp.zps_parked:g}.",
        f"Zone plate focal length f = {zp.focal_per_ev:g} * E = {zp.focal_length():.2f} mm at {zp.energy:g} eV"
        f" (ZPS refocuses by {-zp.focal_per_ev:g} mm/eV); lens (ZP centre) in the lab:"
        f" x = -(ZPX - {zp.zpx:g}), y = (ZPS - {zp.zps:g}) - {zp.focal_length():.2f}, z = ZPZ - {zp.zpz:g}.",
        f"OSA working position S {g.config.osa.s:g}, X {g.config.osa.x:g}, Z {g.config.osa.z:g}: shield on the beam"
        f" {g.config.osa.distance:g} mm before the focus; lab y = (OSA S - {g.config.osa.s:g}) - {g.config.osa.distance:g},"
        f" z = OSA Z - {g.config.osa.z:g} (OSA X not used).",
        f"Capillary reference: CPS {cap.cps:.4f}, CPX {cap.cpx:.4f}, ZPZ {cap.zpz:.4f}, Cap Rz {cap.cap_rz:.4f},"
        f" Cap Rx {cap.cap_rx:.4f}; parked at CPS / CPX {cap.parked[0]:g} / {cap.parked[1]:g}.",
        f"Capillary focus at the reference, lab mm: {_v(cap.focus)}; beam direction {_v(cap.direction)}"
        " (taken parallel to the ZP beam).",
        f"ZPZ carriage: capillary {zp.zpz - cap.zpz:.4f} mm above the zone plate.",
        f"Open: Cap Rz sign PROVISIONAL ({rz}); Rz / Rx pivot {cap.pivot_to_focus:g} mm from the focus"
        f" (unknown); Cap Rz / Rx in {cap.angle_unit}.",
    ])


def file_report(g: OpticsGeometry, path: str) -> str:
    from .nxs import read_motors

    m, found = read_motors(path)
    lines = [f"== {Path(path).name}",
             "   " + ", ".join(f"{k} {v:.4f}" for k, v in found.items())]
    optic = g.active_optic(m)
    if optic == "none":
        return "\n".join(lines + ["   no optic in the beam (ZP and capillary parked)"])
    o = g.stage_offsets(m)
    lines.append(f"   optic: {optic}; focus {_v(o['focus'])}, direction {_v(o['direction'])}")
    if optic == "zone plate":
        lines.append(f"   zone plate (lens) at {_v(g.zone_plate_lens(m))}; OSA shield on the axis at {_v(g.osa_position(m))}"
                     f" (energy {m.energy if m.energy is not None else g.config.zone_plate.energy:g} eV)")
    lines.append(f"   spot on the sample surface (SN_f, SRz 0): {_v(o['spot'])}; vs the ZP reference spot:"
                 f" ST0 {o['dst0']:+.4f}, SZ0 {o['dsz0']:+.4f}; focus {o['focus_along_beam']:+.4f} mm along the beam")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="OpticsGeometry", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", help=f"geometry file (default {DEFAULT_CONFIG.name} if present, else built in)")
    ap.add_argument("--write-config", metavar="PATH", help="write the geometry in use to PATH and stop")
    ap.add_argument("--nxs", nargs="+", help=".nxs files (wildcards allowed) to report")
    ap.add_argument("--focus", nargs=4, metavar=("OPTIC", "X", "Y", "Z"),
                    help="motors putting the focus of OPTIC (zp | capillary) at lab X Y Z (mm)")
    ap.add_argument("--energy", type=float, help="photon energy (eV) for --focus zp (default: the ZP reference)")
    ap.add_argument("--plot", action="store_true", help="show the 3-D schematic (default when nothing else is asked)")
    ap.add_argument("--save-plot", metavar="PNG", help="save the 3-D schematic instead of showing it")
    a = ap.parse_args(argv)

    path = Path(a.config) if a.config else (DEFAULT_CONFIG if DEFAULT_CONFIG.exists() else None)
    cfg = OpticsGeometryConfig.load(path) if path else default_config()
    g = OpticsGeometry(cfg)
    if a.write_config:
        cfg.save(a.write_config)
        print(f"written {a.write_config}")
        return 0

    print(reference_text(g))
    for pattern in a.nxs or []:
        for f in sorted(glob.glob(pattern)) or [pattern]:
            print(file_report(g, f))
    if a.focus:
        optic, xyz = a.focus[0].lower(), [float(v) for v in a.focus[1:]]
        if optic in ("zp", "zone_plate", "zone plate"):
            m = g.zone_plate_motors_for(xyz, energy=a.energy)
            print(f"ZP focus at {_v(xyz)}: ZPS {m.zps:.4f}, ZPX {m.zpx:.4f}, ZPZ {m.zpz:.4f}")
        elif optic in ("cap", "capillary"):
            m = g.capillary_motors_for(xyz)
            print(f"Capillary focus at {_v(xyz)}: CPS {m.cps:.4f}, CPX {m.cpx:.4f}, ZPZ {m.zpz:.4f}"
                  f" (Cap Rz {m.cap_rz:.4f}, Cap Rx {m.cap_rx:.4f} kept)")
        else:
            ap.error("OPTIC is zp or capillary")
    if a.plot or a.save_plot or not (a.nxs or a.focus):
        from .schematic3d import show

        zp, cap = cfg.zone_plate, cfg.capillary
        zp_mode = OpticsMotors(zps=zp.zps, zpx=zp.zpx, zpz=zp.zpz, cps=cap.parked[0], cpx=cap.parked[1],
                               cap_rz=cap.cap_rz, cap_rx=cap.cap_rx)
        cap_mode = OpticsMotors(zps=zp.zps_parked, zpx=zp.zpx, zpz=cap.zpz, cps=cap.cps, cpx=cap.cpx,
                                cap_rz=cap.cap_rz, cap_rx=cap.cap_rx)
        show(g, [zp_mode, cap_mode], ["Zone plate in the beam", "Capillary in the beam"], a.save_plot)
    return 0


__all__ = ["main", "reference_text", "file_report"]
