# opencv-v4: known problems from the held-out evaluation

Baseline: `MODEL_VERSION = "opencv-v4"`, commit `d91c29a`, recorded runs in `evaluations/history.jsonl`
(notes starting with `holdout:`). Each section is meant to be one improvement session.

## Measuring

```sh
# Regenerate the (gitignored) images first
uv run scripts/holdout_real.py fetch && uv run scripts/holdout_real.py render
uv run scripts/holdout_synthetic.py --seed 0 --per-profile 20

# Design set (don't regress; it's optimistic because the rules were designed on it)
uv run scripts/evaluate.py
# Real held-out, by DPI / by source
uv run scripts/evaluate.py --labels data/holdout/real.json --group-by '/real/(\d+)/'
uv run scripts/evaluate.py --labels data/holdout/real.json --group-by '/\d+/([a-z]\d)_'
# Synthetic, by degradation profile and per mark/condition tag
uv run scripts/evaluate.py --labels data/holdout/synthetic.json --group-by '/synthetic/([^/]+)/' --breakdown
```

Baseline numbers (e2e = found with the right label / all GT boxes):

| Set | GT | Precision | Recall | Cls acc | e2e |
|---|---|---|---|---|---|
| data/labels.json (design) | 288 | 1.000 | 1.000 | 0.997 | 0.997 |
| real 300 DPI | 1831 | 0.990 | 0.841 | 1.000 | 0.841 |
| real 200 DPI | 1831 | 0.988 | 0.837 | 1.000 | 0.837 |
| real 150 DPI | 1831 | 0.963 | 0.790 | 1.000 | 0.790 |
| real 100 DPI | 1831 | 0.000 | 0.000 | – | 0.000 |
| synthetic (all) | 5760 | 0.989 | 0.836 | 0.949 | 0.794 |

To avoid tuning to the held-out set, fix one problem per session, check the design set and the whole held-out set
(not just the targeted slice), bump `MODEL_VERSION`, and record with `--record --note`. Regenerating the synthetic
set with a new `--seed` gives a fresh check that the fix didn't just fit seed 0.

---

## 1. Resolution dependence: nothing found at 100 DPI, degraded at 150 DPI and ~1600 px

Boxes affected: ~2,700 (the largest).

- Real: e2e 0.00 at 100 DPI (850 px wide page, ~10 px boxes; 2 detections on a 118-box page). At 150 DPI: filled
  1004s drop to 0.75 (RealVals) / 0.82 (Ocrolus), mostly checked boxes missed (58).
- Synthetic: `lowres` (~1600 px wide) e2e 0.73, `scan` 0.57. Marks that are fine on clean images fail at low
  resolution: filled 0.88 → 0.16, off-center 0.96 → 0.59, x 1.00 → 0.79.
- Repro: `data/holdout/real/100/b1_1004_p01.png` (GT box `[93, 159, 103, 169]`, not found).

Cause (confirmed for 100 DPI): binarization keeps the 1 px border intact, and the same page upscaled 2x gives
118/118. Fixed pixel constants are large relative to ~10 px boxes: the 3x3 dilation in `line_masks`, the
"hole within 2 px of the edge" border search, `max(..., 5)` minimum line length, `max(w // 3, 3)` margins. At
~1600 px, marks touching the border merge with it after downscaling (see #3).

Techniques to try:
- Normalize scale: upscale to a target box size (estimated from a first pass or from page width) before detecting,
  then map boxes back.
- Make every pixel constant proportional to the expected box side instead of absolute.
- Multi-scale detection with merge.

Watch: runtime and pixel limits when upscaling; IoU of mapped-back boxes (mean IoU is already 0.83 at 150 DPI
because the detector returns the inner hole).

## 2. Size gate is a fixed fraction of page width: embedded or scaled forms missed

Boxes affected: ~860 (Plaza 150 + MGIC checklist 138, at each of 150/200/300 DPI).

- Real: Plaza e2e 0.00 at every DPI; MGIC 0.43 (all 138 checklist boxes on pp. 26-28 missed).
- Median box side / page width: GSE forms 0.011, RealVals 0.0125, Plaza 0.0075, MGIC 0.0076; `min_side_frac`
  is 0.008.
- Repro: `data/holdout/real/300/f3_plaza_p10.png`, `f2_mgic_p27.png`. The pre-annotation override
  `min_side_frac=0.003` (plus looser fill/border) finds them; see `scripts/detect_checkboxes.py` docstring.

Cause: `min_side_frac` / `max_side_frac` / `min_line_frac` are relative to page width, which assumes the form fills
the page. Screenshots, booklets and reduced-scale prints break that.

Techniques to try:
- Wide candidate size range, then keep the dominant size cluster(s) on the page (boxes on a form share a size;
  v4 recovery already uses the page median).
- Tie line length to the candidate's own size, not page width.

Watch: letters "o", "c", "D" and sidebar glyphs become candidates at small sizes (they did in the relaxed
pre-annotation); precision on text-heavy pages (blank pp. 4-5 of each form have zero boxes: any detection there is
an FP).

## 3. Marks touching or crossing the border break the "enclosed square" test

Boxes affected: ~500.

- Synthetic misses on clean images, no condition: crossing stroke 0.50 e2e, filled 0.88, erased-X-at-edge; at low
  res filled/off-center/overshoot/small degrade sharply (#1).
- Real: 4 Ocrolus checked boxes with big check marks overshooting the border
  (`f4_ocrolus_1004_p01.png`, `p03.png` at 300 DPI); 58 checked boxes lost at 150 DPI on filled 1004s.
- Repro: `synthetic/clean/clean_000_b6_2055_p06.png` box `[1374, 3456, 1402, 3484]` (crossing stroke, missed);
  `synthetic/clean/clean_010_b3_1025_p01.png` box `[2034, 2583, 2062, 2611]` (filled, missed);
  `synthetic/clean/clean_016_b4_1073_p02.png` box `[306, 3344, 334, 3372]` (off-center, missed).

Suspected cause (verify): boxes are found as holes in the line mask; strokes connected to the border split the
hole or lower `min_fill` / break `has_solid_border`. A filled interior leaves only a thin ring as the "hole".

Techniques to try:
- Find boxes from the four border lines (h/v line segments forming a square) rather than from the hole.
- Remove non-line ink (strokes that are not long h/v runs) before the hole test.
- Template/shape matching against the page's dominant box size as a recovery pass.

## 4. Broken box edges (gap near a corner)

Boxes affected: 282 of 295 (`cond:broken_corner`, recall 0.04), all profiles including clean.

- Repro: `synthetic/clean/clean_001_b7_1004mc_p01.png` box `[2041, 1053, 2070, 1082]`.
- Cause: the v4 gap bridging closes at most `recover_gap_frac` × width ≈ 8 px at 2550 px; the synthetic breaks are
  30-50 % of a side (~9-14 px). They may be harsher than the sample_2 case v4 was built for; the real set has no
  broken boxes, so this is synthetic-only evidence.

Techniques to try:
- Accept three-sided / partially drawn squares when the size matches the page's dominant box size.
- Corner-based detection (L-junctions) instead of closed contours.
- Bridge gaps proportional to the expected box side rather than page width.

Watch: table cells and brackets that look like three-sided boxes (FPs, #7).

## 5. Stray ink inside the box counted as a check (misclassification)

Wrong calls: 223 of 244 synthetic misclassifications.

- `mark:erased_x` (whited-out X leaving corner remains): 133 called checked (e2e 0.58).
- `mark:crossing_stroke` (stroke through the box and section, labeled unchecked): 65 called checked, plus the misses
  in #3.
- Repro: `synthetic/clean/clean_003_b5_1075_p06.png` box `[1319, 3426, 1347, 3454]` (erased X);
  `synthetic/clean/clean_001_b7_1004mc_p01.png` box `[2266, 1000, 2295, 1029]` (crossing stroke).

Cause: classification is an ink ratio inside the box (`checked_ink_ratio` 0.06). v3 ignores strokes that cross the
box, but only those it recognises as lines; wavy hand strokes and corner remains still count.

Techniques to try:
- Features beyond the ink ratio: ink near the center vs corners, connected components that stay inside the box vs
  ones that continue outside, stroke crossing count.
- A small learned classifier on box crops (the synthetic generator can produce unlimited labeled crops; keep the
  real set for evaluation only).

Watch: small and off-center real checks (currently 0.81 / 0.69 e2e) must stay checked.

## 6. Faint or gray boxes next to dark content

Boxes affected: 141 (`cond:faint`, e2e 0.61); 0.06 in the `scan` profile, 0.50-0.54 in lowres/blur.

- Repro: `synthetic/clean/clean_004_b2_1004c_p04.png` box `[1291, 3340, 1319, 3368]`.
- Cause: the adaptive threshold (block 31, C 15) drops the light border when a dark block is inside the window; the
  v4 faint recovery (`faint_ink_contrast` 30) fails once blur/noise/JPEG reduce the contrast further.

Techniques to try: local-contrast normalization (background division, CLAHE) before binarizing; multi-threshold
candidates; checking border contrast against the local paper level only.

## 7. False positives: table grid cells and shaded cells

Low volume: 16 at 300 DPI (13 on the blank 1025 p2), 54 synthetic, 127 at 100 DPI (noise from #1).

- Repro: `data/holdout/real/300/b3_1025_p02.png`: the "Tot / Br / Ba" header cells (called checked because of the
  text) and the empty "Unit # 4" row cells; `b8_2055_legacy_p01.png`: a gray shaded cell next to "Predominant";
  `f3_plaza_p09.png`: black sidebar letter "D".
- Cause: a small square cell of a table is geometrically a checkbox. Nothing checks context.

Techniques to try: reject candidates that share edges with neighbours (part of a grid); require white margin on at
least one side; reject cells whose border lines continue past the corners.

Watch: `cond:table_line` (box touching a table line, e2e 0.83) and `cond:adjacent` (boxes with a ruled label cell
between them, e2e 0.75) must not get worse.

## 8. Adjacent boxes and boxes touching table lines (minor)

`cond:adjacent` e2e 0.75 (31 missed), `cond:table_line` 0.83 (27 missed, 11 misclassified). Mostly fails in
lowres/blur/scan. The touching line merges into the border and changes the hole shape or adds ink inside. Likely
improves with #1 and #3; re-check after those.

---

## Dataset caveats

- Real labels: one reviewer, starting from detector pre-annotations. An audit found no errors, but boxes missed by
  both the reviewer and every detector pass can't be ruled out.
- The real set has only 171 checked boxes, all printed or software marks. There is no handwriting, so real
  classification accuracy (1.000) says little. Handwriting is only in the synthetic set.
- The blank 1004-family forms share a layout with `data/`; their 1.00 at 200/300 DPI is weak evidence. The filled
  samples and the 1025/1073/1075/2055/legacy layouts are the real test.
- Synthetic severities (break length, faintness, stroke shapes) are the generator's choices. Compare a category
  before and after a change, not across categories.
