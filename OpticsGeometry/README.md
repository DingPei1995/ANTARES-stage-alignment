# OpticsGeometry

3-D geometry of the zone plate and the capillary on the shared ZPZ carriage. It is a separate
program: QuickAlignment, RealSampleCalibration and GoldFrameCalibration do not use it.

```
python OpticsGeometry/OpticsGeometry.py                      # reference geometry + 3-D schematic
python OpticsGeometry/OpticsGeometry.py --nxs "Cav/*.nxs"    # optic in use, focus, ST0 / SZ0 shift per file
python OpticsGeometry/OpticsGeometry.py --focus capillary 0 0 0   # CPS / CPX / ZPZ for a focus point
python OpticsGeometry/OpticsGeometry.py --save-plot geometry.png
```

- Model: `src/quickalignment/optics/` (`geometry.py`, `nxs.py`, `schematic3d.py`, `cli.py`).
- Reference geometry: `optics_geometry.json` (regenerate the built-in one with `--write-config`).
- Lab frame of the stage model: origin = analyzer focus, +x right, +y beam, +z up, analyzer on -x.
  The ZP beam is the reference line; the capillary beam is taken parallel to it for now.
- Element list, motor directions, decisions and open items: `optics_elements.md`.
- Tests: `tests/test_optics_geometry.py`.
- Report 2026-11-17 (model, capillary spot discrepancy, test plan, alignment procedure outline):
  `docs/reports/2026-11-17_zp_capillary_geometry.pdf` (sources in `docs/reports/src/`).
