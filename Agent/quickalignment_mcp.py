#!/usr/bin/env python3
"""MCP server of QuickAlignment, RealSampleCalibration and GoldFrameCalibration (stdio).

Registered in .mcp.json at the repository root (Claude Code) or in the Claude Desktop configuration; see
Agent/README.md. Needs numpy, matplotlib (and h5py for the gold-frame .nxs files); no Qt, no MCP SDK.

    python Agent/quickalignment_mcp.py [--configs FOLDER] [--list-tools]
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from quickalignment.agent.mcp_server import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
