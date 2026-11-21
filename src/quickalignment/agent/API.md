# QuickAlignment, RealSampleCalibration -- the agent's reference

*Generated from the program by `python -m quickalignment.agent.catalog --write`; do not edit by hand. A test
fails when it is out of date.*

Read this before anything else: it is everything an agent can do, by name.

## How to use it

- **MCP** (stdio, no window needed): `python Agent/quickalignment_mcp.py`, `python -m quickalignment.agent`
  (with `src/` on the path) or `quickalignment-mcp`. Same protocol as ARPES viewer: `readOnlyHint` is true
  for every tool that only reads; an error inside a tool comes back as a tool error with its text -- read it.
- **Python**: `from quickalignment.agent import AgentAPI; api = AgentAPI()`, then `api.alignment.*`,
  `api.real_sample.*` (section 3). Every method returns a JSON-friendly dict or raises
  `APIError` with a message for the user.
- Numbers always in the standard format (`1234.5`), never the system locale.

## 1. Workflow (the MCP server instructions)

```
QuickAlignment tools for the ANTARES beamline (SOLEIL) sample stage: find samples on a plate from photos
(alignment), and calibrate the stage (real-sample calibration). Talk to the user in
their language; keep the tool names and numbers as they are. Numbers always use "." as decimal separator.

START OF A CONVERSATION (also when the user just sends photos of a sample plate):
1. Ask what they want to do: (a) find samples / align (QuickAlignment), or (b) calibrate the stage.
2. Ask which sample plate is mounted: standard Ta plate, gating plate (contact block, 4 screws), or a custom plate
   (block length, width, height above the back face, centre y). Ask which focusing optic: capillary or zone
   plate (+ OSA). Do not guess these: they change every position.

(a) FIND SAMPLES
1. align_start(plate, optic). It returns the four sample-area corners to read on a photo and their order:
   1 top left (tab side), 2 top right, 3 bottom right, 4 bottom left (front view: sample side, tab up).
2. The photo must be a file the server can read: ask for its path if you only see it in the chat. Call
   align_photo_grid(path) to see it with a pixel grid, read the 4 corners approximately, then zoom on each corner
   (align_photo_grid with region=[x0, y0, x1, y1], ~60-150 px wide) and read it to a few pixels. Corners are those of
   the sample area (standard plate: the 11 mm wide raised riser; gating plate: the riser above the contact block).
   If the photo is rotated, the order follows the plate (tab = top), not the image edges.
   (No file at all: read the corners on the image you see and pass image_size=[width, height] instead of path;
   say that this is less precise and that detect_samples / overlays are not available.)
   OPTIONAL 3D correction (off by default; only when the photo is clearly oblique, or the user asks): read also
   corners at another height (back plate top corners, tab top corners: align_photo_points_3d) and use
   align_register_photo_3d with >= 6 points instead of align_register_photo. It corrects the perspective for thick
   samples and devices; check its rms_px and residuals.
3. align_register_photo(corners_px, path). Then align_photo_overlay and LOOK at it: the green outline must lie on
   the sample-area edges. Show it to the user and ask them to confirm; fix the corners if it is off.
4. Samples: align_detect_samples (colour; pick a pixel on a sample with sample_colors_px to leave out silver paint)
   and/or read each sample's corners on the photo yourself -> align_add_sample_from_photo(points_px, height, name).
   The height H (sample thickness above the plate surface) is NOT visible from above: ask the user (default
   0.525 mm, a Si wafer). Name the samples as the user calls them. Check with align_photo_overlay.
   Many users do not know H: offer SET SN BY EYE (before step 6): at SRn 120, SRz 0 they drive the sample top
   surface onto the camera reference line (the analyzer focal plane) and read SN there (by eye, about ±0.05 mm);
   align_check_height(sample, sn) sets H from it (rough). Ask them to confirm that SN before the positions. Once the
   sample is found in focus with the zone plate / capillary, the program's 'Fine tunings by ZPS/CPS' corrects H
   precisely (the optic's focal distance is fixed) and brings the sample back onto the analyzer focus.
5. Devices (small structures on a substrate): read them on the plate photo (align_add_device with photo_px), or on a
   microscope photo of the substrate registered with align_register_device_photo: first the same DIRECTION on both
   (two points A -> B along a substrate edge on the microscope photo and on the plate photo; only the direction
   counts; the two photos are often not turned the same way), then >= 2 point pairs (the same corners / marks on
   both). The direction fixes the orientation, the pairs the scale and the shift by least squares (more pairs
   average the clicking errors, never distort). Show align_photo_overlay again.
5b. ALWAYS ASK whether the user is satisfied with the samples found (show the overlay). If not, offer:
   (i) they tell you what to change (which sample, where, its size or height) -> align_update_sample /
   align_remove_sample / align_add_sample; (ii) MANUAL ANNOTATION: align_manual_annotation opens the photo window on
   their screen with the photo already registered; they draw the samples / devices themselves and press OK; then
   align_load_annotation. Use only what the user confirms; mark only the samples they want.
6. align_sample_positions: ST / SZ / SN of every sample and device at the start rotation (SRn 120, SRz 0, piezo
   150 / 150). Give the user this table.
7. Feedback from the beamline:
   - The user is at some position and wants another target: align_bring_to_beam(target, motors) (SN kept; a
     height-checked sample keeps the SN of its check: do not correct SN then unless the user asks; otherwise, if the
     result says the target is too far from the analyzer focus, call again with correct_sn=true).
   - "Found S1 at ST=…, SZ=…, SN=…" (on the beam, in focus): align_found_here(target, motors). ST is usually right;
     SZ can be 0-2 mm off because the plate does not always go into the holder at the same height (not the beam):
     the SZ shift moves the whole plate (plate offset, every sample's SZ), the ST shift and H correct that sample.
     Positions are recomputed. A large ST shift (> 0.3 mm) points rather to the beam spot (optic realigned): if
     several samples show it, suggest an optics recalibration instead of moving samples. Ask whether the sample
     height is known precisely (e.g. a Si wafer of known thickness, mounted within 0.02 mm; default: no): then
     height_exact=true keeps H and corrects only x / y (the photo error and the plate offset). Users often forget
     to give H until now: ask for the value and pass it as height=... . Trust: a known exact H > the ZPS / CPS focus
     > the SN set by eye: never call an H from the SN set by eye exact (refused) unless the user gives the known one.
   - The user says a sample is elsewhere / bigger / has another height: align_update_sample.
   - Rotation: align_rotate(srn, srz, motors=position with the point on the beam) gives ST, SZ, SN and the optic
     position (two answers: SN kept, and SN corrected; follow "recommended"). To turn an edge seen on the photo
     along the slit: align_align_edge(p1, p2) then align_rotate. For a Brillouin-zone point: align_bz_angles (Γ and a
     K / M point on the map, point to the slit centre). To move a K / M point read on a map to chosen angles at another
     hv: align_bz_point_to (Γ optional; ask whether the slit is already along Γ–K / Γ–M: then keep_srn=true, only
     SRz turns, θ is left to the deflector). Ask the map's SRn / SRz and hv; do not assume them.
   - Not in focus, or old positions: align_found_here(at_focus=false) when SN was not put at the analyzer focus
     (H kept); configuration=<older file> for positions noted with an older configuration (x, y converted, H kept).
   - Before sending the user to a new position, mention any out_of_range or collisions in the result.
8. align_save_session(path) so the user can open the plate in the QuickAlignment program.

(b) CALIBRATION (RealSampleCalibration, with one feature of a real sample):
- Ask whether only the focusing optic was realigned (mode "optics", the usual case) or the motors were re-homed / maintenance / first use (mode "full"), the optic, the plate, and a small sharp
  reference feature near the plate centre (plate x, y; height H). rsc_start(...), then follow rsc_guide: for every
  set tell the user exactly what to set and measure (the result says where the feature is expected), collect the
  numbers they read, rsc_measure_set, then rsc_fit; go through the test points one by one (rsc_answer_test), fit
  again, until a round is all found. rsc_save only after the user confirms.
  Full mode, how each set is measured matters: set 1 goes to the analyzer focus with SN (it fixes SN_f); the
  rotated sets keep that SN and refocus the optic (sn_kept, the default). If the user measured a set the other way,
  say so in rsc_measure_set(sn_kept=...): a set read with SN kept but fitted as "at the analyzer focus" gives a wrong
  SRz axis. Always ask for the optic position. Each measured set updates the expected positions of the others
  (expected_from): give the user the new ones. If they want other angles (e.g. no positive SRz), rsc_add_set
  (it returns the expected position; a planned set left unmeasured is not fitted) instead of predicting by hand.
  Optics mode after changing the optic (capillary <-> zone plate): the newest configuration of the new optic may be
  old; keep the mechanics of a recent one of the other optic with rsc_start(configuration=...).
  SPEM maps: rsc_read_spem(path) gives the motor and optic values in the file; ask the user at which PIX / PIY the
  tracked point is on the map (the file's PIX / PIY are where the scan ended) and pass them to rsc_measure_set.
  The fit weights positions and optic positions by their reading errors (rsc_fit: reading_errors_mm). The SRz axis
  across the beam shows almost only in the optic positions (least_determined): a capillary focus does not fix it;
  use the zone plate and SRz down to -20 / -25. When readings contradict the model (chi2_per_dof large, a focus far
  from the prediction), list the mismatches and possible causes for the user to judge; do not free more constants
  to absorb them.

RULES
- Never invent measured values (motor positions, optic positions): ask the user.
- Positions are absolute motor values: ST, SN, SZ in mm, SRn, SRz in degrees, PIX, PIY in µm. Plate coordinates are
  mm in the front view (tab up, origin at the centre of the back plate, x right, y up).
- Writing a configuration (rsc_save) changes what QuickAlignment uses for everyone: only on the user's
  explicit request.
- Photo reading is approximate: say so when it matters, and prefer the user's beamline feedback (found_here).
```

Prompts: `start`, `find_samples`, `calibrate`

## 2. MCP tools (52)

`*` = required. **acts**: changes the session, a file or a window; the others only read.

| Tool | | Arguments | What it does |
|---|---|---|---|
| `workflow` | reads | - | How to lead the user through alignment or calibration (read when unsure). |
| `status` | reads | - | What each tool (alignment, real-sample calibration) is doing now. |
| `align_plates` | reads | - | The sample plates known (standard, gating, custom) and their sample area. |
| `align_configurations` | reads | `optic` (string) | The calibration configurations in configs/ (newest first). |
| `align_start` | **acts** | `plate*` (string), `optic*` (string), `custom_plate_mm` (object), `configuration` (string) | Start finding samples on a plate: plate type, optic and (default newest) configuration. Clears the samples. |
| `align_status` | reads | - | Plate, configuration, samples, photos and stage position of the session. |
| `align_photo_corners` | reads | - | The four sample-area corners to read on a plate photo, in their order, with their plate coordinates. |
| `align_photo_info` | reads | `path*` (string) | Size in pixels of a photo file (after its EXIF rotation). |
| `align_photo_grid` | reads | `path` (string), `photo_id` (string), `region` (array), `step` (number), `marks` (array) | A photo (or a zoomed region of it) with a pixel grid labelled in photo pixels, to read positions precisely; optional marks to check points. Use a path, or photo_id of a registered photo. |
| `align_register_photo` | **acts** | `corners_px*` (array), `path` (string), `image_size` (array), `photo_id` (string) | Map a plate photo onto the plate from the 4 sample-area corners (photo px, order of align_photo_corners). |
| `align_photo_points_3d` | reads | - | OPTIONAL 3D correction: the plate points at several heights that can be read on an oblique photo. |
| `align_register_photo_3d` | **acts** | `points*` (array), `path` (string), `image_size` (array), `photo_id` (string) | OPTIONAL (off by default): register an oblique photo with a camera model from >= 6 points at 2+ heights (sample-area corners + back plate / tab corners). Use only when the photo is clearly not from straight above or the user asks for it. |
| `align_manual_annotation` | **acts** | `photo_id` (string) | Open the photo window on the user's screen (photo already registered) so the user marks the samples by hand. Use when the user is not satisfied with the samples found. |
| `align_load_annotation` | **acts** | `path` (string), `wait` (boolean) | Read the samples the user marked in the manual-annotation window (after they pressed OK). |
| `align_photo_overlay` | reads | `photo_id` (string), `region` (array) | The registered plate photo with the model drawn on it (sample area, samples, devices): check it. |
| `align_plate_view` | reads | - | Drawing of the plate model with samples and devices (mm). |
| `align_photo_to_plate` | reads | `points_px*` (array), `photo_id` (string), `height` (number) | Photo pixels -> plate mm. |
| `align_plate_to_photo` | reads | `points_mm*` (array), `photo_id` (string), `height` (number) | Plate mm -> photo pixels. |
| `align_detect_samples` | reads | `photo_id` (string), `threshold` (number), `min_area_mm2` (number), `sample_colors_px` (array), `background_px` (array) | Samples found by colour on the registered plate photo (boxes in plate mm; nothing is added). |
| `align_add_sample` | **acts** | `x*` (number), `y*` (number), `length*` (number), `width*` (number), `height` (number), `name` (string) | Add a rectangular sample (plate mm). |
| `align_add_sample_from_photo` | **acts** | `points_px*` (array), `height` (number), `name` (string), `photo_id` (string) | Add a sample from its corners read on the plate photo (4 corners, or 2 opposite corners). |
| `align_update_sample` | **acts** | `name*` (string), `x` (number), `y` (number), `length` (number), `width` (number), `height` (number), `new_name` (string) | Change a sample (centre, size, height, name). |
| `align_check_height` | **acts** | `sample*` (string), `sn*` (number) | Set SN by eye (button 'Set SN by eye'): SN read when the sample top surface is on the camera reference line (analyzer focal plane) at SRn ref, SRz 0 gives its height H roughly (about ±0.05 mm); bring_to_beam then keeps this SN for its targets. A zone-plate / capillary focus ('Fine tunings by ZPS/CPS' in the program) gives H more precisely. |
| `align_remove_sample` | **acts** | `name*` (string) | Remove a sample. |
| `align_clear_samples` | **acts** | - | Remove all samples. |
| `align_add_device` | **acts** | `sample*` (string), `name` (string), `x` (number), `y` (number), `photo_px` (array), `photo_id` (string), `x_edge` (string), `y_edge` (string), `size_mm` (number) | Add a device on a substrate at plate (x, y) mm or at a pixel of a registered photo (plate or microscope). |
| `align_remove_device` | **acts** | `target*` (string) | Remove a device ('sample/device'). |
| `align_register_device_photo` | **acts** | `pairs*` (array), `direction` (object), `path` (string), `photo_id` (string), `plate_photo_id` (string) | Map a microscope photo of a substrate onto the plate: the same direction on both (orientation) and >= 2 point pairs (scale + shift, least squares, no distortion). |
| `align_samples` | reads | - | The samples and devices with their warnings. |
| `align_sample_positions` | reads | - | ST / SZ / SN of every sample and device at the start rotation (SRn ref, SRz 0, piezo centred). |
| `align_set_position` | **acts** | `motors*` (object), `optic_position` (number) | The stage as it is now (motor values read by the user) and the optic position; returns what the beam hits. |
| `align_bring_to_beam` | reads | `target*` (string), `motors` (object), `correct_sn` (boolean) | ST / SZ putting a target on the beam with SN kept (height-checked sample: the SN of its check; correct_sn: also SN, onto the analyzer focus). |
| `align_beam_on` | reads | `motors` (object), `optic_position` (number) | What the beam hits at these positions and the optic focus position. |
| `align_found_here` | **acts** | `target*` (string), `motors*` (object), `apply` (boolean), `at_focus` (boolean), `configuration` (string), `height_exact` (boolean), `height` (number) | A target was found on the beam at these positions: the y (SZ) shift moves the whole plate in the holder (plate offset, all samples), x and H correct its sample (at_focus false: SN not corrected, H kept; height_exact: H known precisely, kept, only x / y corrected; configuration: positions read with an older configuration: the sample moves, H kept). |
| `align_rotate` | reads | `srn*` (number), `srz` (number), `motors` (object), `measured_optic` (number), `target` (string) | New ST / SZ / SN and optic position after turning SRn / SRz, keeping the point now on the beam. |
| `align_align_edge` | reads | `p1*` (array), `p2*` (array), `along` (string), `photo_id` (string), `plate_mm` (boolean), `current_srn` (number) | SRn turning an edge (two points: photo px, or plate mm with plate_mm=true) along or across the slit. |
| `align_bz_angles` | reads | `lattice_a*` (number), `hv_map*` (number), `gamma*` (array), `ref_point*` (array), `ref_label` (string), `feature` (string), `line` (integer), `hv` (number), `map_srn` (number), `map_srz` (number), `binding` (number) | SRn / SRz putting a hexagonal Brillouin-zone point at the slit centre (from a measured map's angles). |
| `align_bz_point_to` | reads | `lattice_a*` (number), `hv_map*` (number), `ref_point*` (array), `map_srn*` (number), `map_srz*` (number), `ref_label` (string), `hv` (number), `target_angles` (array), `gamma` (array), `keep_srn` (boolean), `binding` (number), `sample` (string) | SRn / SRz putting a K / M point read on a map at chosen analyzer angles at another hv (Γ optional; keep_srn: turn SRz only). |
| `align_collision_check` | reads | `motors` (object), `optic_position` (number) | Does the plate touch the analyzer / optic at these positions; collision-free motor ranges. |
| `align_save_session` | **acts** | `path*` (string) | Save the plate (samples, devices, stage) as a session file. |
| `align_load_session` | **acts** | `path*` (string), `optic` (string) | Load a QuickAlignment session file. |
| `rsc_guide` | reads | - | Real-sample calibration: where it stands and what to do next. |
| `rsc_start` | **acts** | `mode*` (string), `optic*` (string), `plate*` (string), `feature_x*` (number), `feature_y*` (number), `feature_height*` (number), `sn_kept` (boolean), `configuration` (string) | Start a real-sample calibration with one reference feature. |
| `rsc_status` | reads | - | The sets, what is measured, where the feature is expected. |
| `rsc_read_spem` | reads | `path*` (string) | Motor and optic positions (ST, SZ, SN, SRn, SRz, ZPS, CPS, hv, scanned axes) recorded in a SPEM map file. |
| `rsc_add_set` | **acts** | `name*` (string), `srn*` (number), `srz*` (number), `sn_kept` (boolean) | Another measurement set at other angles. |
| `rsc_measure_set` | **acts** | `name*` (string), `st*` (number), `sz*` (number), `sn*` (number), `optic` (number), `pix` (number), `piy` (number), `srn` (number), `srz` (number), `use` (boolean), `sn_kept` (boolean) | The values read for a set. |
| `rsc_fit` | **acts** | - | Fit the constants; predicts a round of test points. |
| `rsc_test_points` | reads | - | The open test points: where to go. |
| `rsc_answer_test` | **acts** | `name*` (string), `found` (boolean), `st` (number), `sz` (number), `optic` (number) | A test point: found at the prediction, or the real ST, SZ (and optic). |
| `rsc_change_test_angles` | **acts** | `name*` (string), `srn*` (number), `srz*` (number) | Other SRn / SRz for an open test point. |
| `rsc_save` | **acts** | `comment` (string) | Save the configuration in configs/ (only when the user asks). |

## 3. Agent API (Python)

### `api.alignment` (AlignmentSession)

| Method | What it does |
|---|---|
| `add_device(sample: 'str', name: 'str \| None' = None, x: 'float \| None' = None, y: 'float \| None' = None, photo_px=None, photo_id: 'str \| None' = None, x_edge: 'str' = 'left', y_edge: 'str' = 'bottom', size_mm: 'float' = 0.2) -> 'dict'` | A device on a substrate: at plate (x, y) mm, or at a pixel of a registered photo (plate or microscope). It is stored relative to the substrate edges (x_edge left/right, y_edge bottom/top), so it moves with it. |
| `add_sample(x: 'float', y: 'float', length: 'float', width: 'float', height: 'float \| None' = None, name: 'str \| None' = None) -> 'dict'` | A rectangular sample: centre (x, y), length along x, width along y (plate mm), height H (mm). |
| `add_sample_from_photo(points_px, height: 'float \| None' = None, name: 'str \| None' = None, photo_id: 'str \| None' = None) -> 'dict'` | A sample from points read on the plate photo: its 4 corners (any order), or 2 opposite corners of its box. The sample is the plate rectangle around them; its in-plane angle is reported. |
| `align_edge(p1, p2, along: 'str' = 'slit', photo_id: 'str \| None' = None, plate_mm: 'bool' = False, current_srn: 'float \| None' = None) -> 'dict'` | SRn turning a straight edge (two points on it: photo pixels of a registered photo, or plate mm with plate_mm=true) along the analyzer slit (horizontal at ANTARES) or across it ('vertical'). |
| `beam_on(motors: 'dict \| None' = None, optic_position: 'float \| None' = None) -> 'dict'` | What the beam hits at these (or the current) positions, and the optic position focusing there. |
| `bring_to_beam(target: 'str', motors: 'dict \| None' = None, correct_sn: 'bool' = False) -> 'dict'` | ST / SZ putting a target on the beam with SN kept (how the stage is run), at the given (or current) SRn, SRz, piezo; with correct_sn also SN, so that it is on the analyzer focus. A target whose sample height was checked (check_height) keeps the SN of that check unless `motors` gives SN. |
| `bz_angles(lattice_a: 'float', hv_map: 'float', gamma: 'list', ref_point: 'list', ref_label: 'str' = 'K', feature: 'str' = 'K', line: 'int' = 0, hv: 'float \| None' = None, map_srn: 'float \| None' = None, map_srz: 'float \| None' = None, binding: 'float' = 0.0) -> 'dict'` | SRn / SRz putting a 2-D hexagonal Brillouin-zone point (Γ, K, K', M) at the slit centre with the slit along a high-symmetry line, from a measured map (ARPES viewer angles θ = deflector, φ = along the slit). |
| `bz_point_to(lattice_a: 'float', hv_map: 'float', ref_point: 'list', map_srn: 'float', map_srz: 'float', ref_label: 'str' = 'K', hv: 'float \| None' = None, target_angles: 'list \| None' = None, gamma: 'list \| None' = None, keep_srn: 'bool' = False, binding: 'float' = 0.0, sample: 'str \| None' = None) -> 'dict'` | SRn / SRz putting a K or M point read on a map (θ = deflector, φ = slit, ARPES viewer) at chosen analyzer angles at another photon energy. Γ is optional: without it the surface tilt is estimated from \|Γ–point\|. keep_srn: keep the in-plane orientation (slit already along Γ–K / Γ–M) and turn SRz only. With `sample`, also the ST / SZ / SN putting it at the analyzer focus there. |
| `check_height(sample: 'str', sn: 'float') -> 'dict'` | Set SN by eye: the top surface of `sample` was driven onto the camera reference line (the analyzer focal plane) at SRn ref, SRz 0, at SN = sn (read by eye, about ±0.05 mm). Its height H follows roughly; bring_to_beam then keeps this SN for its targets (right at SRn ref, SRz 0, as the height was set with it). A zone-plate / capillary focus ('Fine tunings by ZPS/CPS' in the program) gives H more precisely. |
| `clear_samples() -> 'dict'` | - |
| `collision_check(motors: 'dict \| None' = None, optic_position: 'float \| None' = None) -> 'dict'` | Does the plate touch the analyzer / optic at these positions, and how far can each motor go. |
| `configurations(optic: 'str \| None' = None) -> 'dict'` | - |
| `current_optic() -> 'float'` | - |
| `detect_samples(photo_id: 'str \| None' = None, threshold: 'float' = 12.0, min_area_mm2: 'float' = 0.2, sample_colors_px=None, background_px=None) -> 'dict'` | Samples found by colour on the registered plate photo (nothing is added): boxes in plate mm. |
| `found_here(target: 'str', motors: 'dict', apply: 'bool' = True, at_focus: 'bool' = True, configuration: 'str \| None' = None, height_exact: 'bool' = False, height: 'float \| None' = None) -> 'dict'` | The target was found on the beam at these stage positions. ST is usually right; SZ is off (0-2 mm) because the plate does not always go into the holder at the same height, not because of the beam: the y shift moves the whole plate in the holder (plate offset: SZ of every sample changes, the configuration and the drawing stay), the x shift moves its sample (with its devices) and the height shift changes its H. |
| `load_annotation(path: 'str \| None' = None, wait: 'bool' = False) -> 'dict'` | Read the result of the manual-annotation window into the plate (replacing the samples if the user chose so in the window, else adding them). |
| `load_session(path: 'str', optic: 'str \| None' = None) -> 'dict'` | - |
| `manual_annotation(photo_id: 'str \| None' = None) -> 'dict'` | Open the "Samples from a photo" window on the user's screen with this photo and its registration, so the user marks / corrects the samples and devices by hand (when they are not satisfied with what was found). Returns at once; call load_annotation when the user has pressed OK. |
| `photo_corners() -> 'dict'` | The four points to read on a plate photo, in this order (plate mm). |
| `photo_grid(path: 'str \| None' = None, photo_id: 'str \| None' = None, region=None, step: 'float \| None' = None, marks=None) -> 'dict'` | The photo (or a zoomed region [x0, y0, x1, y1]) with a pixel grid, to read coordinates precisely. |
| `photo_info(path: 'str') -> 'dict'` | - |
| `photo_overlay(photo_id: 'str \| None' = None, region=None) -> 'dict'` | The registered plate photo with the model drawn on it, to check the corners and the samples. |
| `photo_points_3d() -> 'dict'` | Points that can be used for the optional 3D correction of an oblique photo, with their plate (x, y) and height w above the back face (mm). |
| `photo_to_plate(points_px, photo_id: 'str \| None' = None, height: 'float \| None' = None) -> 'dict'` | Photo pixels -> plate mm, in the plane `height` mm above the plate surface (only with the 3D correction; default 0: the sample-area plane). |
| `plate_to_photo(points_mm, photo_id: 'str \| None' = None, height: 'float \| None' = None) -> 'dict'` | - |
| `plate_view() -> 'dict'` | The plate model (front view, tab up) with the samples and devices, axes in plate mm. |
| `plates() -> 'dict'` | The sample plates the program knows, with their sample area and the photo corners. |
| `register_device_photo(pairs, path: 'str \| None' = None, photo_id: 'str \| None' = None, plate_photo_id: 'str \| None' = None, direction: 'dict \| None' = None) -> 'dict'` | A close-up (microscope) photo of a substrate, mapped onto the plate. Recommended: `direction`, the same direction on both, as two points A -> B along a substrate edge or a long pattern line on each, {"photo": [[x, y], [x, y]], "plate_mm": [[x, y], [x, y]] or "plate_photo_px": [...]} (only the direction counts: A and B need not be the same places on both): it sets the in-plane orientation, and the point `pairs` (>= 2) then set the scale and the shift by least squares, without distorting the photo. `pairs`: the same feature (substrate corner, mark) seen on this photo (`photo` px) and on the plate (`plate_mm`, or `plate_photo_px` on the registered plate photo). Without `direction` (former way): 2 pairs similarity, 3 affine, >= 4 perspective. |
| `register_photo(corners_px, path: 'str \| None' = None, image_size=None, photo_id: 'str \| None' = None) -> 'dict'` | Map a plate photo onto the plate from the four sample-area corners read on it (photo pixels, in the order of photo_corners). `path`: the image file (needed for detect_samples and the overlays); without it give `image_size` [width, height] of the image the corners were read on. |
| `register_photo_3d(points, path: 'str \| None' = None, image_size=None, photo_id: 'str \| None' = None) -> 'dict'` | OPTIONAL 3D correction for an oblique photo: a camera model from >= 6 points at several heights ([{"name" or "number" from photo_points_3d, "px": [x, y]}] or [{"plate_mm": [x, y, w], "px": [x, y]}]). Positions at any height (thick samples, devices) are then corrected for the perspective. |
| `remove_device(target: 'str') -> 'dict'` | - |
| `remove_sample(name: 'str') -> 'dict'` | - |
| `rotate(srn: 'float', srz: 'float \| None' = None, motors: 'dict \| None' = None, measured_optic: 'float \| None' = None, target: 'str \| None' = None) -> 'dict'` | New ST / SZ (/ SN) and optic position keeping the point now on the beam there after turning to (srn, srz). |
| `sample_positions() -> 'dict'` | ST / SZ / SN putting each sample / device centre on the beam at the analyzer focus at the start rotation (SRn ref, SRz 0, piezo centred). |
| `samples() -> 'dict'` | - |
| `save_session(path: 'str') -> 'dict'` | - |
| `set_position(motors: 'dict', optic_position: 'float \| None' = None) -> 'dict'` | The stage as it is now (absolute motor values read at the beamline); missing motors keep their value. |
| `start(plate: 'str' = 'standard', optic: 'str \| None' = 'capillary', custom_plate_mm: 'dict \| None' = None, configuration: 'str \| None' = None) -> 'dict'` | Begin with an empty plate: plate type, optic and configuration (default: the newest for the optic). |
| `status() -> 'dict'` | - |
| `update_sample(name: 'str', x=None, y=None, length=None, width=None, height=None, new_name=None) -> 'dict'` | - |

### `api.real_sample` (RealSampleCalibrationSession)

| Method | What it does |
|---|---|
| `add_set(name: 'str', srn: 'float', srz: 'float', sn_kept: 'bool \| None' = None) -> 'dict'` | Another set at other angles (more redundancy); `sn_kept` default: as the session (start). |
| `answer_test(name: 'str', found: 'bool' = False, st: 'float \| None' = None, sz: 'float \| None' = None, optic: 'float \| None' = None) -> 'dict'` | A test point: found at the prediction (within 0.05 mm), or the real ST, SZ (and optic) with the feature on the beam in focus, SRn / SRz / SN as given. |
| `change_test_angles(name: 'str', srn: 'float', srz: 'float') -> 'dict'` | Other angles for an open test point (e.g. out of range), predicted again. |
| `fit() -> 'dict'` | Fit the sets and the measured test points; predict a new round of test points. |
| `guide() -> 'dict'` | Where the calibration stands and the next thing to do. |
| `measure_set(name: 'str', st: 'float', sz: 'float', sn: 'float', optic: 'float \| None' = None, pix: 'float' = 150.0, piy: 'float' = 150.0, srn: 'float \| None' = None, srz: 'float \| None' = None, use: 'bool' = True, sn_kept: 'bool \| None' = None) -> 'dict'` | The values read for a set (the feature on the beam; in mode 'full' at the analyzer focus, or with SN kept and the optic refocused when the set is sn_kept). `sn_kept` overrides how this set was measured. |
| `previous()` | The configuration giving the start values and the kept mechanics (chosen at start, else the newest). |
| `read_spem(path: 'str') -> 'dict'` | Motor values of a SPEM map file (.nxs): what to enter in measure_set / answer_test, with the PIX / PIY of the tracked point read on the map by the user (the file's PIX / PIY are where the scan ended). |
| `save(comment: 'str' = '') -> 'dict'` | Save the fitted configuration in configs/ (only after the user agreed). |
| `sets_table() -> 'list[dict]'` | The sets with where the feature is expected (a start for the search): from the newest configuration, from set 1 once it is measured, from the fit once there is one. |
| `start(mode: 'str' = 'optics', optic: 'str \| None' = None, plate: 'str' = 'standard', feature_x: 'float' = 0.0, feature_y: 'float' = 0.0, feature_height: 'float' = 0.0, sn_kept: 'bool' = True, configuration: 'str \| None' = None) -> 'dict'` | Begin a calibration: mode "optics" (optic realigned: ST0, SZ0, optic reference; the mechanics are kept from the newest configuration) or "full" (optics + motors: all constants), the optic, the plate and the reference feature (plate x, y in mm and its height H above the plate surface). `sn_kept` (full mode): the rotated sets keep the SN of set 1 and refocus the optic (usual); false: every set is moved to the analyzer focus with SN. `configuration` (label or file name): keep the mechanics from this configuration instead of the newest of the optic; it may be one of the other optic (e.g. the zone plate calibrated with the axes of a recent capillary calibration). The optic reference is still compared with the newest of the chosen optic. |
| `status() -> 'dict'` | - |
| `test_points() -> 'dict'` | The test points of the open round: where to go (SRn, SRz, ST, SZ, SN, optic). |
