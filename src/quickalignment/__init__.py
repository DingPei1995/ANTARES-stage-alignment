"""Quick sample / optics alignment helpers for the ANTARES beamline."""

from .core.geometry import Device, PlateGeometry, Sample, SampleLayout

__all__ = ["Device", "PlateGeometry", "Sample", "SampleLayout"]

# The CAD collision model lives in CAD/src/cadmodel but is imported as quickalignment.cadmodel.
import os as _os

_cad_src = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))), "CAD", "src")
if _os.path.isdir(_cad_src):
    __path__.append(_cad_src)
