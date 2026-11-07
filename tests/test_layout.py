"""The repository layout: every launcher finds the shared package from its tool folder."""

import runpy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LAUNCHERS = {
    "QuickAlignment/QuickAlignment.py": "quickalignment.ui.main_window",
    "RealSampleCalibration/RealSampleCalibration.py": "quickalignment.ui.real_sample_window",
    "GoldFrameCalibration/GoldFrameCalibration.py": "quickalignment.ui.gold_frame_window",
    "GoldFrameCalibration/GoldFrameSimulator.py": "quickalignment.goldframe.cli",
    "Agent/quickalignment_mcp.py": "quickalignment.agent.mcp_server",
}


@pytest.mark.parametrize("launcher", sorted(LAUNCHERS))
def test_launcher_finds_the_package(launcher, monkeypatch):
    monkeypatch.setattr(sys, "path", list(sys.path))
    path = ROOT / launcher
    assert path.exists() and path.with_suffix(".pyw").exists() or launcher.startswith("Agent")
    runpy.run_path(str(path), run_name="not_main")  # puts src/ on the path, imports the launcher helper
    assert str(ROOT / "src") in [str(Path(p).resolve()) for p in sys.path if p]
    __import__(LAUNCHERS[launcher])


def test_no_folder_differs_from_the_package_only_by_case():
    """Windows / macOS file systems ignore case: QuickAlignment/ and quickalignment/ must not share a parent."""
    names = [p.name.lower() for p in ROOT.iterdir()]
    assert len(names) == len(set(names))


def test_configuration_folder_is_at_the_repository_root():
    from quickalignment.core.calibration import DEFAULT_FOLDER
    assert DEFAULT_FOLDER == ROOT / "configs"
