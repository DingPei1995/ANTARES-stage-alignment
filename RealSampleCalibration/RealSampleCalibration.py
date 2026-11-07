#!/usr/bin/env python3
"""ANTARES QuickAlignment - real-sample calibration (optics realigned, first start, motors re-homed).

Double-click to start. Generates a calibration configuration in configs/ from a few measurement sets of one
reference feature of a real sample; see the protocol in the window and docs/protocol.md.
On Windows you can also double-click RealSampleCalibration.pyw (no console window).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from quickalignment.launcher import launch  # noqa: E402

if __name__ == "__main__":
    sys.exit(launch("quickalignment.ui.real_sample_window", "RealSampleCalibration"))
