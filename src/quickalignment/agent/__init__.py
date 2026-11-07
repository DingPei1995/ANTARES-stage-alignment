"""Agent API and MCP server of QuickAlignment, RealSampleCalibration and GoldFrameCalibration (no Qt needed).

* `AgentAPI` (api.py): the three tools as Python objects returning JSON-friendly dicts.
* `mcp_server.py`: the same as MCP tools over stdio, for Claude Desktop / Claude Code or any MCP client
  (``python Agent/quickalignment_mcp.py`` or ``python -m quickalignment.agent.mcp_server``).
* `workflow.py`: how the agent leads the user (server instructions, prompts).
"""

from .api import AgentAPI
from .alignment import AlignmentSession
from .common import APIError
from .gold_frame import GoldFrameSession
from .real_sample import RealSampleCalibrationSession

__all__ = ["APIError", "AgentAPI", "AlignmentSession", "GoldFrameSession", "RealSampleCalibrationSession"]
