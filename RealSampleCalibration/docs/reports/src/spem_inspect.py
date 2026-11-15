"""Load the two SPEM files with ARPES viewer's loader and print axes / metadata."""
import sys

import numpy as np

sys.path.insert(0, r"D:\Codes\ARPES-viewer-main")
from arpes_viewer.loader.registry import load

for name in ("Real_2026-11-14_18-08-53.nxs", "Real_2026-11-14_18-16-15.nxs"):
    path = rf"D:\Codes\ANTARES-stage-alignment-main\Photos\{name}"
    scan = load(path)
    print("\n==", name, scan.kind, scan.info.get("loader.name"))
    for a in ("x", "y", "k", "z"):
        v = getattr(scan, a)
        if v is not None:
            v = np.asarray(v)
            print(f"  {a}: n={v.size} {v.min():.4f}..{v.max():.4f}  label={scan.labels.get(a)}")
    print("  value", None if scan.value is None else np.shape(scan.value), "value4d", None if scan.value4d is None else scan.value4d.shape)
    keys = [k for k in scan.info if any(s in k.lower() for s in ("srn", "srz", "st", "sz", "sn", "cps", "pix", "piy", "pol", "tilt", "theta", "phi", "energy", "hv", "x", "y", "z"))]
    for k in keys[:80]:
        print("   ", k, "=", scan.info[k])
    print("  previews", list(scan.previews))
    scan.close()
