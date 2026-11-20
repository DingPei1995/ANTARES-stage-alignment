import sys
from pathlib import Path

ROOT = Path(r"D:\Codes\ANTARES-stage-alignment-main")
sys.path.insert(0, str(ROOT / "src"))
from quickalignment.realsample.spem_nxs import read_positions  # noqa: E402

for p in sorted((ROOT / "CavData").glob("*.nxs")):
    try:
        r = read_positions(p)
    except Exception as e:  # noqa: BLE001
        print(p.name, "ERR", e)
        continue
    sc = "; ".join(f"{a['motor']} {a['from']:g}->{a['to']:g} d{a['step']:g}" for a in r["scanned"])
    g = lambda k: r.get(k, float("nan"))  # noqa: E731
    print(f"{p.name[15:23]} ST {g('st'):8.4f} SZ {g('sz'):7.3f} SN {g('sn'):7.4f} SRn {g('srn'):7.2f} "
          f"SRz {g('srz'):6.2f} PIX {g('pix'):6.1f} PIY {g('piy'):6.1f} ZPS {g('zps'):7.3f} | {sc}")
