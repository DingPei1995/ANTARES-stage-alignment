#!/usr/bin/env python3
"""ANTARES QuickAlignment - double-click this file to start the program.

On Windows you can also double-click QuickAlignment.pyw (no console window).
From a console: python QuickAlignment/QuickAlignment.py [session.json]
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from quickalignment.launcher import launch  # noqa: E402

if __name__ == "__main__":
    sys.exit(launch("quickalignment.ui.main_window", "QuickAlignment"))
