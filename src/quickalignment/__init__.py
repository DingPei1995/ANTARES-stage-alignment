"""Quick sample / optics alignment helpers for the ANTARES beamline."""

from pathlib import Path as _Path

# The CAD anti-collision model (quickalignment.cadmodel, program CadCollision) lives in the top-level CAD/ folder,
# kept out of the repository (.gitignore): when it is there, it is importable as quickalignment.cadmodel.
_CAD_SRC = _Path(__file__).resolve().parents[2] / "CAD" / "src"
if (_CAD_SRC / "cadmodel").is_dir():
    __path__.append(str(_CAD_SRC))  # noqa: F821 (package __path__)

from .core.geometry import Device, PlateGeometry, Sample, SampleLayout

__all__ = ["Device", "PlateGeometry", "Sample", "SampleLayout"]
