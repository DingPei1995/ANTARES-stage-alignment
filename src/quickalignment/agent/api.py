"""The internal API: one object with the three tools, for an agent or a script.

    from quickalignment.agent import AgentAPI
    api = AgentAPI()
    api.alignment.start("gating", "capillary")
    api.alignment.register_photo(corners_px, path="plate.jpg")
    api.alignment.add_sample_from_photo([[300, 400], [380, 480]], height=0.525, name="WSe2")
    api.alignment.sample_positions()
    api.real_sample.start("optics", "capillary", "standard", 0.5, 1.0, 0.3)
    api.gold_frame.start("capillary", gold_height=0.05)

Every method returns a JSON-friendly dict (images as PNG bytes under "image_png") or raises APIError with a
message for the user. The MCP server (`mcp_server.py`) exposes the same methods as tools.
"""

from __future__ import annotations

from pathlib import Path

from .alignment import AlignmentSession
from .gold_frame import GoldFrameSession
from .real_sample import RealSampleCalibrationSession
from .workflow import INSTRUCTIONS


class AgentAPI:
    def __init__(self, configs: str | Path | None = None):
        self.configs = configs
        self.alignment = AlignmentSession(configs)
        self.real_sample = RealSampleCalibrationSession(configs)
        self.gold_frame = GoldFrameSession(configs)

    @staticmethod
    def workflow() -> dict:
        """How to lead the user (the same text as the MCP server instructions)."""
        return {"workflow": INSTRUCTIONS}

    def status(self) -> dict:
        """What each of the three tools is doing."""
        return {
            "alignment": self.alignment.status() if self.alignment.started else "not started (align_start)",
            "real_sample_calibration": self.real_sample.status(),
            "gold_frame_calibration": self.gold_frame.status(),
        }


__all__ = ["AgentAPI"]
