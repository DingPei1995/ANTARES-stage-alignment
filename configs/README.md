# Configurations

- `calibration_YYYY-MM-DD_HHMMSS_<optic>.json` (`<optic>`: `capillary` or `zone_plate`): one file per calibration made by
  beamline staff with RealSampleCalibration.py (what was measured is kept in the file's `check` record). Older files are kept as history and can be selected again in
  the Configuration window.

QuickAlignment only reads configurations; it writes none.

- `archive/`: retired configurations (2026-11-17 … 2026-11-20 zone plate, made without the plate tilt). The programs
  do not read this folder; move a file back here to use it again.

- `motor_limits.json` (optional): the ST, SZ, SN, SRn, SRz limits set by hand in the Configuration window
  (*Motor limits*, `{"st": [min, max], ...}`). Without it the built-in limits are used.

At start-up QuickAlignment loads the newest of these files made with the chosen optic, by their time stamp.
