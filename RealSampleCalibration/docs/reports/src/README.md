# Sources of 2026-11-14_capillary_real_sample_calibration.pdf

Run from this folder, in this order (Python with numpy, scipy, matplotlib, h5py, reportlab, pillow; ARPES viewer
at `D:\Codes\ARPES-viewer-main` or set `ARPES_VIEWER`):

1. `spem_maps.py`, `spem_shift.py`, `spem_compare.py`: section 8, device test (Photos/Real_2026-11-14_*.nxs).
2. `cav_maps.py`, `cav_compare.py`, `cav_schematic.py`: section 9, Cav test (Cav/Cav_2026-11-14_*.nxs) and the
   three SN schematics.
3. `report.py`: builds the PDF in `..` (intermediate files in `spem/` and `report_figs/`, both can be deleted).

`spem_inspect.py` and `spem_h5.py` only print the axes / motor values of the SPEM files.
The scripts of sections 1-8 were recovered from the sessions of 2026-11-14 (they were in temporary folders).
