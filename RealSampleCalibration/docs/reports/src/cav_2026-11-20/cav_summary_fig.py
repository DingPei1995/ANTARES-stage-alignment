"""Summary: measured focus ZPS (edge sharpness) minus model, for the 11-17 config, fit A (SN-moved sets) and the
SN-kept axis; and the edge-B lateral position from the rotated sets against the slides."""
import json
import sys
from dataclasses import replace
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).parent
sys.argv = [sys.argv[0], "53.717"]
sys.path.insert(0, str(HERE))
import io, contextlib  # noqa: E401,E402
with contextlib.redirect_stdout(io.StringIO()):
    import cav_compare as cc  # noqa: E402

order = ["13-23-52", "A", "14-13-13", "14-23-15", "14-41-25", "13-37-04", "SRz-10", "13-43-52", "13-54-20",
         "15-06-02", "SRz-25 first", "SRz-25 final"]
lab = ["SRz0 slide\nSN -1.86", "SRz0\nanchor", "SRz0 slide\nSN +0.48", "SRz0 slide\nSN +0.80", "SRz0 slide\nSN +1.15",
       "SRz -5", "SRz -10", "SRz -15", "SRz -20", "SRn140\nSRz -15", "SRz -25\nSN moved 1", "SRz -25\nSN moved 2"]
models = {"11-17 config": cc.C1117, "fit A (SN-moved sets)": cc.CNEW, "SN-kept axis": cc.CSER}
cols = {"11-17 config": "#999999", "fit A (SN-moved sets)": "#d62728", "SN-kept axis": "#2ca02c"}
fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 7.5), gridspec_kw={"height_ratios": [1.3, 1]})
x = np.arange(len(order))
for i, (name, cfg) in enumerate(models.items()):
    d = [cc.sets[g]["zps"] - cc.plane_zps(cfg, cc.sets[g]) for g in order]
    a1.plot(x + (i - 1) * 0.18, d, "o", color=cols[name], label=name)
end = [cc.sets[g]["at_end"] for g in order]
for xi, e in zip(x, end):
    if e:
        a1.annotate("bound", (xi, 0), xytext=(0, -26), textcoords="offset points", ha="center", fontsize=6,
                    color="#555")
a1.axhline(0, color="k", lw=0.8)
a1.axhspan(-0.02, 0.02, color="#2ca02c", alpha=0.08)
a1.axvspan(9.5, 11.5, color="#ffcc00", alpha=0.15)
a1.set_xticks(x, lab, fontsize=7)
a1.set_ylabel("focus ZPS measured - model (mm)", fontsize=8)
a1.set_title("Focus from the edge sharpness of the fine PIX x ZPS scans (anchor focus ZPS 53.717 from the slides)",
             fontsize=9)
a1.legend(fontsize=7)
# lateral: edge B u from rotated sets minus slides
ser = ["13-37-04", "SRz-10", "13-43-52", "13-54-20"]
for i, (name, cfg) in enumerate(models.items()):
    if name == "11-17 config":
        ref = np.mean([cc.on_beam_plate(cfg, cc.sets[g], cc.sets[g]["pix"])[0] for g in
                       ("13-23-52", "14-13-13", "14-23-15", "14-41-25")])
    else:
        ref = cc.UB
    d = [1000 * (cc.on_beam_plate(cfg, cc.sets[g], cc.sets[g]["pix"])[0] - ref) for g in ser]
    a2.plot(np.array([-5, -10, -15, -20]) + (i - 1) * 0.4, d, "o-", color=cols[name], label=name)
a2.axhline(0, color="k", lw=0.8)
a2.axhspan(-5, 5, color="#2ca02c", alpha=0.08)
a2.set_xlabel("SRz (deg), SN kept", fontsize=8)
a2.set_ylabel("stripe left edge on the plate:\nrotated - SRz 0 slides (um)", fontsize=8)
a2.set_title("Lateral: the same edge (PIY 40) located with the measured edge PIX", fontsize=9)
a2.invert_xaxis()
a2.legend(fontsize=7)
fig.tight_layout()
fig.savefig(HERE / "cav_summary.png", dpi=150)
print(HERE / "cav_summary.png")
