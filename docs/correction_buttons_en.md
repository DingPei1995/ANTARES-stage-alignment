# Correction buttons: what each one assumes and what it changes

Memo, 2026-11-20. For every button of QuickAlignment and RealSampleCalibration that corrects something: what you
enter, what it assumes, how it computes, and what it changes. Two kinds:

- **model corrections** change the stored description (sample position / height, plate offset, configuration);
  they act on every later prediction;
- **position computations** only fill the motor / optic fields; nothing in the model changes.

Symbols: plate point (x, y, w) with w = plate top + H; SN_f = SN of the standard riser top (5.0 mm) on the analyzer
focal plane; Δy = position along the beam from the analyzer focus (+ downstream).

## Model corrections

| button (tab) | you enter / it assumes | computation | changes |
|---|---|---|---|
| **Set SN by eye** (Samples; confirmed at *Samples placed → Stage*) | the sample's top surface is on the camera reference line (= analyzer focal plane) at SRn 120°, SRz 0°; the SN read there by eye | H = SN − SN_f + 5.0 − plate top (`height_from_sn`); refused if H < 0 | **H** of the sample (rough); the SN is remembered (*H checked*): *Bring target onto the beam* then uses it for that sample. *Samples placed → Stage* asks whether this SN is right (also for an SN typed but not set). Accuracy: eye, ~±0.05 mm, and SN_f |
| **Fine tunings by ZPS/CPS** — *position and H* (Stage & Optics; replaces the former *Found here*) | the optic's focal distance is fixed. The Target was found on the beam and in focus at the entered motors and optic position | **SRz 0**: the plate point at the optic focus (y along the beam from the optic position) minus the target's point: Δx, Δy, ΔH (`found_offset(..., y)`, no rotation axis involved; ΔH zone plate ±0.014, capillary ±0.07 mm). With the optic at the configuration's position for the analyzer focus (y = 0) this is what *Found here* computed. **After an SRz turn** (\|SRz\| ≥ 0.01°, optic more than 0.05 mm off its prediction): one ΔH is fitted to the ST, SZ and optic errors together (weights: positions ±0.02 mm, optic ±0.02 zone plate / ±0.10 capillary; `fit_height`); it **explains** them if all three errors left are ≤ 0.03 mm | if you answer *Yes*: at SRz 0 **Δy → plate offset** (the plate sits elsewhere in the holder: SZ of every sample changes), **Δx → this sample's x**, **ΔH → its H** (with its devices; a set SN follows); nothing offered below 0.001 mm in x, y and 0.002 mm in H. Warns if Δx or ΔH > 0.3 mm (configuration outdated? wrong Target?) or plate offset > 2.5 mm. After an SRz turn **H** only; not explained: nothing changes, the result line names the likely causes (plate position x, y → this button at SRz 0; SRz axis; SN_f) |
| **Change plate…** (toolbar) | another plate is mounted | – | the plate; the plate offset of *Fine tunings by ZPS/CPS* is reset; samples kept and checked |
| **Use selected** (*Configuration…*) | an older configuration for this session | – | the configuration in use (ST0, SZ0, SN_f, axes, optics reference) |
| **Apply limits / Defaults** (*Configuration…*, *Motor limits*) | motor travel | – | the limits of the input fields, out-of-range and anti-collision checks; saved in `configs/motor_limits.json` |
| working distances (fields under the optic, Stage & Optics) | the real front distances of the optic solids | – | anti-collision solids, this session only |

Why SRz 0 and turned are handled differently: at SRz 0 the sample surface is parallel to the analyzer focal plane,
so the focus gives its height directly, without the rotation axes. After an SRz turn the focus also depends on the
SRz axis: an H error moves ST and the focus **together** (both ~ sin SRz); an SRz-axis error across the beam moves
only the focus, a wrong x, y only ST / SZ. Only the first is corrected as H.

## Position computations (the model is not changed)

| button (tab) | computation | notes |
|---|---|---|
| **Bring target onto the beam** (Stage & Optics) | ST, SZ putting the target on the beam with **SN kept** (or the SN of its height check), for the entered SRn, SRz, piezo (`motors_on_beam`); reports Δy from the analyzer focus (red > 50 µm) and the ΔSN that would remove it | refused if out of range or colliding |
| **Correct SN** (Stage & Optics) | SN, ST, SZ putting the target **on the analyzer focus** (`motors_for_target`) | absolute: relies on ST0, SZ0, SN_f, axes **and H** (an H error δ leaves the point ~√2·δ off the focus) |
| **Fine tunings by ZPS/CPS** (back onto the analyzer focus) | optic position → Δy of the focus (optics reference, focal distance fixed); the point at that focus gives x, y, H (shown); **ΔSN = −Δy/√2, ΔST = +Δy/√2** (point stays on the beam, SZ kept), optic → the configuration's exact position for the analyzer focus | not moved if out of range or colliding (an H correction already made is kept) |
| **Update schematic & optics** (Stage & Optics) | beam spot, optic position needed for focus, collision-free ranges | – |
| **Compute new position** (Rotate sample) | the plate point under the beam at the current position (uses the sample's **H**) is turned to the new SRn / SRz: ST, SZ with **SN kept** and the optic that refocuses (`relocate`); tick **Correct SN** for SN, ST, SZ on the analyzer focus | H enters through the point followed and *Correct SN* |
| **Send to Stage & Optics tab** (Rotate sample) | copies the shown solution | refused if out of range / colliding |
| **Centre the piezo: correct ST / SZ / SN and the optic** (Rotate sample, Quick rotation, step 4) | the sample is seen at PIX, PIY ≠ 150 µm: the piezo offset is a translation of the plate; ST, SN, SZ take it over (`same_point`, optic unchanged), then SN is kept with ST compensating: the point slides √2·ΔSN along the beam and the optic refocuses by it (`recentre_piezo`) | only the rotation angles and piezo directions enter, not ST0 / SZ0 / SN_f / axes |
| **Locate the sample and compute the new position** (Quick sample rotation) | as *Fine tunings by ZPS/CPS*: the plate point at the optic focus (x, y, H from the optic position), then `relocate` about it | stand-alone; uses nothing from the other tabs and changes nothing |

## RealSampleCalibration (beamline staff)

| button | computation | changes |
|---|---|---|
| **Compute** | least-squares fit of the stage constants to the sets (mode *optics*: ST0, SZ0, optic reference; *full*: also SN_f, SRn and SRz axes), weighted by the reading errors; residuals, least-determined combination, test points | nothing saved |
| **Correct the configuration with the test results → new test points** | found test points confirm, entered ones are added as equations; fit again, new round | nothing saved |
| **Save as new configuration** | – | a new file `configs/calibration_<date>_<optic>.json`; QuickAlignment loads the newest of each optic at its next start |
