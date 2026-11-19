# Optical elements that may matter for the beam geometry

Working list (2026-11-17) for the separate optics-geometry model. Today only the zone
plate and the capillary are modelled; the rest is kept here to think about later.
Tango names and labels from `D:\AntaresSupervision\PythonVersion\config\layout.json`;
readings from the Cav NeXus files (`Cav/*.nxs`).

Lab frame of `src/quickalignment/core/stage.py`: origin = analyzer focus, +x right,
**+y along the beam (downstream)**, +z up. The analyzer sits at -n = (-1, -1, 0)/sqrt2,
so "towards the analyzer" across the beam is **-x**.

## Upstream (not modelled yet)

| Element | Chamber | Motors (Tango) | Cav readings 11-14 (capillary) / 11-15 (ZP) | Possible effect at the sample |
|---|---|---|---|---|
| Undulator HU60 / HU256 | ring | gap / phase (not beamline-controlled) | - | source position / divergence vs energy |
| Mirror M1 (A+B+C) | C02 | `i12-m-c02/op/mir1-mt_rz.1`, `mir1-mt_rz.2` (M1A) | rz.1 -46949 / -46948; rz.2 -567 / -582 | horizontal beam angle -> lateral spot drift |
| Monochromator | C04 | `mono1-mt_rx.1` (grating), `mono1-mt_rx.2` (mirror), `mono1-mt_tx.1` (grating T) | 11.539 / 8.068 / 35.448 (same both days) | vertical beam angle vs energy / grating |
| Vertical slits | C04 | `fent_v.1-mt_ec` (gap), `fent_v.1-mt_tx.1` (pos) | 80000 / 84000 | secondary source size / position (vertical) |
| Horizontal slit | C05 | `fent_h.1-mt_ec` (gap) | not recorded | secondary source size (horizontal) |
| Wolter mirrors M3 / M4 | C08 | `wolt-mt_tz.1` (M3Z), `wolt-mt_tz.2` (M4Z), `wolt-mt_rz.1` | 34398 / 35491 / 22486 | beam height and angle into the chamber |
| Pinhole | CX1 | `pin-mt_ps`, `pin-mt_px`, `pin-mt_pz` | -0.0035 / -7.0006 / -4.998 | defines the beam entering the focusing optic |

## Focusing optics in the main chamber (CX1)

| Element | Motors (Tango -> name) | Capillary mode (Cav 2026-11-14 19:48) | ZP mode (Cav 2026-11-15 11:13) |
|---|---|---|---|
| Zone plate | `zp-mt_zs` ZPS, `zp-mt_zx` ZPX, `zp-mt_zz` ZPZ | ZPS -20.002, ZPX 0.4681, ZPZ 3.2395 | ZPS 53.7502, ZPX 0.4683, ZPZ 23.511 |
| OSA | `osa-mt_os` OS, `osa-mt_ox` OX, `osa-mt_oz` OZ | 20.0005 / -0.5042 / -6.3369 | 71.9997 / -0.5043 / -5.0022 |
| Capillary | `cap-mt-ts` CPS, `cap-mt-tx` CPX, `cap-mt-rz` Cap Rz (the one used), `cap_rx` Cap Rx; height = ZPZ (shared); `cap_rz` (other device) not used | CPS 61.38, CPX 57.14, cap-mt-rz -0.408, Cap Rx 3.9056 | CPS 0, CPX 0 (parked), Cap Rx 3.9143 |

Parking positions: zone plate ZPS -20 (capillary mode); capillary CPS 0 / CPX 0 (zone-plate mode).
The ZPZ carriage carries both: ZPZ 23.511 (ZP in the beam) vs 3.2395 (capillary in the beam),
so the capillary sits 20.27 mm above the zone plate on the carriage.

Spot positions from the calibration configs (`configs/calibration_2026-11-15_151356_*.json`):
ZP spot vs capillary spot: ST0 +0.80 mm, SZ0 +0.19 mm (same SN_f), i.e. the capillary spot is at
lab (-0.566, +0.566, -0.190) mm from the ZP spot (on the sample surface at SN_f).

## Motor directions (user, 2026-11-17)

- ZPS: + downstream (+y). ZPZ: + up (+z). ZPX: + towards the analyzer (-x).
- Capillary: height = ZPZ. CPS: + downstream (+y). CPX: + towards the analyzer (-x).
  Cap Rz (`cap-mt-rz`): tip turning towards the analyzer is negative (**provisional, to be confirmed**).
  Cap Rx: tip turning up is positive.

## Decisions and open items (2026-11-17)

- Code convention kept: beam along +y, +x right, +z up, analyzer on the -x side.
- The ZP beam is the reference straight line (+y through the analyzer focus).
- The capillary beam is taken parallel to the ZP beam for now (to be corrected later).
- Cap Rz / Rx are in degrees (user, 2026-11-17).
- Open: Cap Rz direction (confirm with the user); Cap Rz / Rx rotation centre (pivot); the order of
  the Rz / Rx stages.

## Zone plate focal length and OSA (user, 2026-11-17)

- ZPS energy coefficient -0.256 mm/eV; ZPS taken 1:1 with the lens (user's choice), so f = 0.256 E:
  24.32 mm at 95 eV (25.60 at 100 eV). Replaces 26.613 mm at 100 eV (25.28 at 95 eV) in the collision model.
  Note: 26.613 @ 100 eV would agree with the coefficient if 1 mm of ZPS moved the focus 0.962 mm (SN-slide checks
  of 11-15 gave 0.95-0.97, one 1.015); not adopted.
- ZP lens in the lab: x = -(ZPX - 0.4683), y = (ZPS - 53.7502) - 0.256*95, z = ZPZ - 23.511 (focus at the origin
  at 95 eV for the reference ZPS 53.7502, ZPX 0.4683, ZPZ 23.511); ZPS for the focus at the origin at E:
  53.7502 - 0.256 (E - 95).
- OSA working position: S 80 (+ downstream, as ZPS), X 0.5 (direction unknown, hardly moved), Z 26.63 (+ up, as
  ZPZ). The shield is taken 3.5 mm before the focus there (collision-model estimate): lab y = (OSA S - 80) - 3.5,
  z = OSA Z - 26.63.
- Open: the Cav files of 2026-11-15 (ZP in use) read OSA S 72.00 / X -0.504 / Z -5.002, which this reference puts
  31.6 mm below the beam and 8 mm further upstream: OSA out of the beam then, or another OSA zero (re-homing).

## Test data 2026-11-17 (same sample, "0.1 mm (to be confirmed)" on the 5 mm plate, SN -0.15)

| Optic | Optics motors | ST | SZ |
|---|---|---|---|
| ZP | ZPS 54.22, ZPX 0.47, ZPZ 23.51 | -1.55 | 41.25 |
| Capillary | CPS 61.34, CPX 57.14, ZPZ 3.24, Cap Rx 3.886, Cap Rz -0.408 | -1.75 | 41.25 |

Against the model (configs 2026-11-15 15:13:56):
- ST / SZ between the two optics: measured -0.20 / 0.00; model -0.80 / -0.19 (from Cav 11-14 capillary vs
  Cav 11-15 ZP). With parallel beams and SN kept this does NOT depend on the thickness: contradiction of
  0.60 mm in ST and 0.19 mm in SZ. Open, hypotheses with the user.
- ZP focus: ZPS 54.22 puts the focus 0.47 mm downstream; with H 0.1 the surface would be 0.775 mm
  downstream (ZPS ~54.5). Consistent if H ~0.30-0.32 mm (or the plate top is not at w = 5.0).
- Capillary focus: with the measured position and H ~0.31, CPS 61.34 puts the focus 0.21 mm upstream of
  the spot (CPS judged to ~0.1-0.2 before); with H 0.1 it would be 0.5 mm.
