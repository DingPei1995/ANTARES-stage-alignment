"""Zone-plate calibration 2026-11-15: the two SPEM maps of Cav (SRn 120 and SRn 140), integrated intensity and the
motor values recorded in the files. Saves spem/zp_srn120.npz and spem/zp_srn140.npz (read by report_2026-11-15.py)."""
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, os.environ.get("ARPES_VIEWER", r"D:\Codes\ARPES-viewer-main"))
from arpes_viewer.loader.registry import load  # noqa: E402
from quickalignment.goldframe.spem_nxs import read_positions  # noqa: E402

OUT = Path(__file__).parent / "spem"
OUT.mkdir(exist_ok=True)
FILES = {"zp_srn120": "Cav_2026-11-15_11-13-55.nxs", "zp_srn140": "Cav_2026-11-15_11-33-22.nxs"}

for tag, name in FILES.items():
    path = ROOT / "Cav" / name
    s = load(str(path))
    total = np.asarray(s.value4d[:, :, :, :], float).sum(axis=(2, 3))  # (PIY, PIX)
    x, y = np.asarray(s.x), np.asarray(s.y)
    s.close()
    pos = read_positions(path)
    np.savez(OUT / f"{tag}.npz", x=x, y=y, total=total,
             **{f"m_{k}": v for k, v in pos.items() if isinstance(v, float)})
    print(tag, name, total.shape, "x", x.min(), x.max(), "y", y.min(), y.max(),
          {k: round(v, 4) for k, v in pos.items() if isinstance(v, float)})
