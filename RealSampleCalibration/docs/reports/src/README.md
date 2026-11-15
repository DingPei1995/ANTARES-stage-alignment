# Sources of 2026-11-14_capillary_real_sample_calibration.pdf

Run from this folder, in this order (Python with numpy, scipy, matplotlib, h5py, reportlab, pillow; ARPES viewer
at `D:\Codes\ARPES-viewer-main` or set `ARPES_VIEWER`):

1. `spem_maps.py`, `spem_shift.py`, `spem_compare.py`: section 8, device test (Photos/Real_2026-11-14_*.nxs).
2. `cav_maps.py`, `cav_compare.py`, `cav_schematic.py`: section 9, Cav test (Cav/Cav_2026-11-14_*.nxs) and the
   three SN schematics.
3. `report.py`: builds the PDF in `..` (intermediate files in `spem/` and `report_figs/`, both can be deleted).

`spem_inspect.py` and `spem_h5.py` only print the axes / motor values of the SPEM files.

# Sources of 2026-11-15_zone_plate_calibration_srz_axis.pdf

Run from this folder: `zp_maps.py` (the two SPEM maps Cav/Cav_2026-11-15_*.nxs, ARPES viewer loader), `zp_figs.py`
(figures and `spem/zp_numbers.json`, from the beamline values listed at its top and the configurations in
`configs/`), `zp_schematics.py` (section 10: beam spots and rotation axes, `spem/zp_schem.json`), then
`report_2026-11-15.py`. The configurations `calibration_2026-11-15_151356_*.json` must exist.
The scripts of sections 1-8 were recovered from the sessions of 2026-11-14 (they were in temporary folders).
