#!/usr/bin/env python3
"""ANTARES QuickAlignment - gold-frame SPEM simulator.

Double-click to open it: sliders for the frame (offset, rotation, tilt, height), the stage (SRn axis,
SRz offsets, ST scale), the analyzer acceptance and the beam offset; the SZ lines of the gold-frame
calibration are drawn against the perfect case. On Windows you can also double-click
GoldFrameSimulator.pyw (no console window). The calibration itself is GoldFrameCalibration.py.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from quickalignment.launcher import launch  # noqa: E402

if __name__ == "__main__":
    sys.exit(launch("quickalignment.goldframe.cli", "GoldFrameSimulator", ["simulator"]))
