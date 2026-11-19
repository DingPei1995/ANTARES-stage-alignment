#!/usr/bin/env python3
"""ANTARES - 3-D geometry of the zone plate and the capillary (separate model; the other programs are unchanged).

    python OpticsGeometry/OpticsGeometry.py                    reference geometry + 3-D schematic
    python OpticsGeometry/OpticsGeometry.py --nxs Cav/*.nxs    optic in use and focus for each file
    python OpticsGeometry/OpticsGeometry.py --help
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from quickalignment.launcher import launch  # noqa: E402

if __name__ == "__main__":
    sys.exit(launch("quickalignment.optics.cli", "OpticsGeometry", sys.argv[1:]))
