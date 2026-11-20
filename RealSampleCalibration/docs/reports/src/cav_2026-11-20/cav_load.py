"""Load every CavData scan with the ARPES viewer loader: integrated intensity on (y, x) + recorded motors -> npz."""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(r"D:\Codes\ANTARES-stage-alignment-main")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, r"D:\Codes\ARPES-viewer-main")
from arpes_viewer.loader.registry import load  # noqa: E402
from quickalignment.realsample.spem_nxs import read_positions  # noqa: E402

OUT = Path(__file__).parent / "cavdata"
OUT.mkdir(exist_ok=True)
for p in sorted((ROOT / "CavData").glob("*.nxs")):
    s = load(str(p))
    v4 = np.asarray(s.value4d[:, :, :, :], float)  # (y, x, angle, energy)
    x, y = np.asarray(s.x, float), np.asarray(s.y, float)
    s.close()
    pos = read_positions(p)
    ax = [a["motor"] for a in pos["scanned"]]
    np.savez(OUT / f"{p.stem}.npz", x=x, y=y, total=v4.sum(axis=(2, 3)), edc=v4.sum(axis=(0, 1, 2)),
             spec=v4.sum(axis=2), axes=np.array(ax),
             **{f"m_{k}": v for k, v in pos.items() if isinstance(v, float)})
    print(p.stem, v4.shape, ax)
