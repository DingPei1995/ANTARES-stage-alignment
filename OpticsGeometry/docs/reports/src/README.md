# Sources of 2026-11-17_zp_capillary_geometry.pdf

Python with numpy, matplotlib, h5py, reportlab, pillow. From the repository root:

1. `python OpticsGeometry/docs/reports/src/figures_2026-11-17.py`: 3-D views (perspective + orthographic, ZP and
   capillary mode), spot map, pivot plot in `report_figs/`, and `numbers.json`. Reads `OpticsGeometry/optics_geometry.json`
   and `Cav/*.nxs`; the 2026-11-17 test set is written at the top of the script.
2. `python OpticsGeometry/docs/reports/src/report_2026-11-17.py`: builds the PDF in `..`.
