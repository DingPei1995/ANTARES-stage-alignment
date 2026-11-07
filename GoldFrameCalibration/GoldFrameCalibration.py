#!/usr/bin/env python3
"""ANTARES QuickAlignment - gold-frame calibration from SPEM intensity lines.

Double-click to open the calibration window: measurement plan, load the measured SZ lines over the gold
frame, fit them and save the configuration that QuickAlignment loads.
On Windows you can also double-click GoldFrameCalibration.pyw (no console window).
The simulator is GoldFrameSimulator.py. From a console:

    python GoldFrameCalibration.py plan [--csv plan.csv]
    python GoldFrameCalibration.py fit FILE... [--sn-gold SN] [--save]
    python GoldFrameCalibration.py simulate --frame-u 0.2 --srz-offset-n 3.0

See docs/GOLD_FRAME_REPORT_en.md (and the PDFs in docs/pdf/) for the method and
docs/pdf/GoldFrame_experiment_plan_en.pdf for the experiment plan.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from quickalignment.launcher import launch  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) > 1:
        from quickalignment.goldframe.cli import main

        sys.exit(main())
    sys.exit(launch("quickalignment.ui.gold_frame_window", "GoldFrameCalibration"))
