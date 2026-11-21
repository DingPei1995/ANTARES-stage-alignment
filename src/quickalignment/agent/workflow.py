"""How an agent leads a user through alignment and calibration: the MCP server instructions and prompts.

The text is written for the agent (an LLM with vision) that calls the tools of `mcp_server.py`. It is also
the reference for anyone driving `quickalignment.agent.AgentAPI` from Python.
"""

INSTRUCTIONS = """\
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
"""

PROMPTS = {
    "start": {
        "description": "Start a QuickAlignment conversation: alignment from photos, or a calibration.",
        "arguments": [{"name": "photos", "description": "Paths of the plate photos (optional)", "required": False}],
        "text": ("I want help at the ANTARES sample stage. {photos}Ask me first whether I want to find samples or to "
                 "calibrate, which sample plate is mounted and which optic is used, then guide me step by step with "
                 "the QuickAlignment tools."),
    },
    "find_samples": {
        "description": "Find the samples of a plate photo and give their stage positions.",
        "arguments": [{"name": "photo", "description": "Path of the plate photo", "required": True},
                      {"name": "plate", "description": "standard, gating or custom", "required": False},
                      {"name": "optic", "description": "capillary or zone plate", "required": False}],
        "text": ("Find the samples on the plate photo {photo} (plate: {plate}, optic: {optic}; ask me if unknown), "
                 "locate the four corners of the sample area, check the overlay with me, ask me the sample heights "
                 "and whether I am satisfied (else let me annotate by hand), then give me the ST / SZ / SN of every sample."),
    },
    "calibrate": {
        "description": "Calibrate the stage step by step with a real sample (RealSampleCalibration).",
        "arguments": [],
        "text": ("I want to calibrate the stage with a real sample. Ask me what is needed and guide me one step at a time; "
                 "tell me exactly what to set and what to read at each step."),
    },
}


def render_prompt(name: str, arguments: dict | None = None) -> str:
    p = PROMPTS[name]
    args = {a["name"]: "" for a in p["arguments"]}
    args.update({k: v for k, v in (arguments or {}).items() if v})
    if name == "start":
        args["photos"] = f"My photos: {args['photos']}. " if args.get("photos") else ""
    for key in ("plate", "optic"):
        if key in args and not args[key]:
            args[key] = "not given"
    return p["text"].format(**args)


__all__ = ["INSTRUCTIONS", "PROMPTS", "render_prompt"]
