# To do at the next zone-plate beamtime: ZPS vs SRz, and the effect of a height error

Reminder, 2026-11-20. Purpose: measure again how the zone-plate focus follows SRz, and find out how much of what is
left is a **sample height (H) error** rather than a stage constant (SRz axis, SN_f, SN direction).

## Why

- On 2026-11-15 the SRz series −5 … −20° (SN kept) showed the SRz axis 0.97 mm off across the beam; with the new axis
  the series is reproduced within ±40 µm in ZPS. An H error cannot explain that series (it would have put ST
  0.1–0.38 mm off; ST agreed within 1 µm).
- Still open: at SRz −25° with SN moved by ~1.5 mm, the focus stays **0.14 mm short** of the prediction and the point
  20–25 µm off across the beam. An H error explains at most a third of it (best ΔH from the series: +0.04 mm).
- Expected signature of an H error of +0.1 mm (stage model, SN kept, SRn 120°):

  | SRz | −5° | −10° | −15° | −20° | −25°, SN corrected |
  |---|---|---|---|---|---|
  | ST | −17 µm | −35 µm | −51 µm | −68 µm | −61 µm across |
  | ZPS | +13 µm | +27 µm | +41 µm | +57 µm | +128 µm |

- *Fine tunings by ZPS/CPS* now checks this automatically after an SRz turn (optic > 0.05 mm off:
  is there one ΔH that explains ST, SZ and ZPS together?). This test checks that the rule is right.

## Measurement (zone plate, 95 eV, same plate)

1. **Two points of different height**, both sharp on SPEM maps: e.g. a feature on a thick substrate and one on a thin
   one (H differing by ≥ 0.3 mm), or on the plate riser. Their heights must be known independently (thickness
   measured, or *Set SN by eye* on the camera line **and** ZPS at SRz 0).
2. For each point at SRn 120°, SRz 0°: on the beam (map, piezo centred), focus with ZPS; note ST, SZ, SN, ZPS, PIX,
   PIY. Note also the SN where its surface is on the camera line.
3. **SRz series, SN kept**: SRz 0, −5, −10, −15, −20, −25 (and back to 0 to check the return). At each: bring the point
   back on the beam with ST / SZ (map), refocus with ZPS; note ST, SZ, ZPS, the map file.
4. **SN moved at large SRz**: at SRz −20 and −25, *Correct SN* position; note ST, SZ, SN, ZPS and where the point is
   on the map (the 0.14 mm open point).
5. **SN slide at SRz 0** (control): SN ± 1.5 mm with ST compensating; ZPS should follow 1:1 (1.015 on 2026-11-15).
6. Optional: repeat 3 at SRn 140° (separates the SRn and SRz axes).
7. Note the temperature and the time of every point (drift).

## Analysis

- For every point and angle: errors measured − predicted (ST, SZ, ZPS) with the configuration in use, and
  `fit_height` (src/quickalignment/core/stage.py) for one ΔH per point.
- **Same ΔH for all angles of a point, different for the two points** → H errors: correct H (procedure of *Fine
  tunings by ZPS/CPS*); the configuration is right.
- **Same ZPS pattern for both points, ST right** → SRz axis (across the beam) or SN_f: recalibrate with these series
  (RealSampleCalibration, SRz sets with ZPS).
- **Error only when SN is moved at large SRz** → SN direction / straightness with SRz turned: not in the model yet.
- Then decide: keep the 0.05 mm trigger and 0.03 mm tolerance of the height check, or change them
  (`HEIGHT_CHECK_OPTIC`, `HEIGHT_EXPLAIN_TOL` in `core/stage.py`).

Background: `docs/alignment_procedure/alignment_procedure.pdf` (section *Height error or SRz-axis error?*),
`RealSampleCalibration/docs/reports/2026-11-15_zone_plate_calibration_srz_axis.pdf` (sections 4–7).
