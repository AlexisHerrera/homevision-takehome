# Detector: known issues and work plan

Living document: the open problems of the current detector, measured on the held-out sets, and how to work on
them. Update it at the end of every session (status table, current numbers, the section you worked on). The
explanation of each change lives in its commit message (`uv run scripts/evaluate.py --history`, then
`git log <hash>`); the numbers of every recorded run live in `evaluations/history.jsonl`.

Current detector: `opencv-v6` (commit `e8a26c6`). Next suggested: #5 (classifier) or #3 (marks crossing the border).

| # | Issue | Status | Main metric now |
|---|---|---|---|
| 1 | Resolution dependence | Mostly fixed in v5 | real 100 DPI e2e 0.975 (v4 0.000); synthetic scan 0.759 |
| 2 | Size gate relative to page width | Mostly fixed in v6 | Plaza 0.965 (v5 0.000), MGIC 0.996 (v5 0.430) |
| 3 | Marks touching/crossing the border | Open, improved by v5 | crossing_stroke recall 0.520, filled 0.864 |
| 4 | Broken box edges | Open | broken_corner recall 0.037 |
| 5 | Stray ink counted as a check | Open | erased_x e2e 0.589, crossing_stroke 0.270; 292 synthetic miscls |
| 6 | Faint boxes | Open, improved by v5 | faint e2e 0.660; scan 0.224 |
| 7 | False positives: table/shaded cells, glyphs | Open, improved by v5 | 77 real FP, 60 of them on b3_1025_p02 |
| 8 | Adjacent boxes / touching table lines | Open, improved by v5 | adjacent 0.803, table_line 0.875 |

## Session workflow

1. Setup. The held-out images are gitignored; regenerate them (a few minutes):
   ```sh
   uv sync
   uv run scripts/holdout_real.py fetch && uv run scripts/holdout_real.py render
   uv run scripts/holdout_synthetic.py --seed 0 --per-profile 20
   ```
2. Check the baseline reproduces the numbers below:
   ```sh
   uv run scripts/evaluate.py                                                    # design set (the samples)
   uv run scripts/evaluate.py --labels data/holdout/real.json --group-by '/real/(\d+)/'       # by DPI
   uv run scripts/evaluate.py --labels data/holdout/real.json --group-by '/\d+/([a-z]\d)_'    # by source
   uv run scripts/evaluate.py --labels data/holdout/synthetic.json --group-by '/synthetic/([^/]+)/' --breakdown
   ```
3. Pick one issue. Explore with `--errors`, `--images REGEX` (subset) and `--params key=value,...` (try parameter
   values without editing the detector), e.g.
   `uv run scripts/evaluate.py --labels data/holdout/synthetic.json --images '/scan/' --params min_width=0`.
4. Guardrail: `tests/test_samples.py` fails on any missed/extra box on the 4 samples, or a misclassification beyond
   the known one (sample_2's erased X). If a fix corrects that one, set `KNOWN_MISCLASSIFIED` to `{}`.
5. Check the whole held-out set, not just the targeted slice: every group and tag should be equal or better, or the
   regression explained. Then check a fresh synthetic seed so the fix doesn't just fit seed 0:
   ```sh
   uv run scripts/holdout_synthetic.py --seed 1 --per-profile 20   # overwrites data/holdout/synthetic.json
   # evaluate old vs new: `git stash push src/checkboxes/detector.py` (not a bare `git stash`: it would also
   # stash the regenerated synthetic.json and pair seed-0 labels with seed-1 images)
   uv run scripts/holdout_synthetic.py --seed 0 --per-profile 20   # restore; synthetic.json must end unchanged
   ```
6. Finish:
   - Bump `MODEL_VERSION`; `uv run ruff format . && uv run ruff check . && uv run pytest`.
   - Commit the detector change with a detailed message: problem, what and why, how, rejected alternatives,
     results old -> new (design, real by DPI/source, synthetic by profile/tag, fresh seed), limitations.
     No Claude co-author lines.
   - Record from a clean tree (only `history.jsonl` changes between the three), then commit `history.jsonl`:
     ```sh
     uv run scripts/evaluate.py --record --note "<short change description>"
     uv run scripts/evaluate.py --labels data/holdout/real.json --group-by '/real/(\d+)/' \
         --record --note "holdout: real forms (12 PDFs, 60 pages x 100/150/200/300 DPI)"
     uv run scripts/evaluate.py --labels data/holdout/synthetic.json --group-by '/synthetic/([^/]+)/' --breakdown \
         --record --note "holdout: synthetic seed 0, 8 profiles x 20"
     ```
   - Update this document.

Rules of thumb: fix one problem per session; prefer changes that only add to what the strict pass finds (the
recovery passes' pattern) so the samples can only regress through new false positives; the design set is
optimistic because the rules were designed on it.

## Current numbers (opencv-v6)

e2e = found with the right label / all GT boxes.

| Set | GT | Precision | Recall | Cls acc | e2e | v5 e2e |
|---|---|---|---|---|---|---|
| data/labels.json (design) | 288 | 1.000 | 1.000 | 0.997 | 0.997 | 0.997 |
| real 300 DPI | 1831 | 0.992 | 0.995 | 1.000 | 0.995 | 0.841 |
| real 200 DPI | 1831 | 0.990 | 0.995 | 1.000 | 0.995 | 0.841 |
| real 150 DPI | 1831 | 0.989 | 0.992 | 1.000 | 0.992 | 0.837 |
| real 100 DPI | 1831 | 0.987 | 0.975 | 1.000 | 0.975 | 0.824 |
| synthetic seed 0 (all) | 5760 | 0.989 | 0.890 | 0.943 | 0.839 | 0.839 |

Real by source (all DPIs): blank forms b1-b8 recall 1.000 (b3 60 FP, b2 6, b8 4); RealVals (f1) 0.947;
MGIC (f2) 0.996; Plaza (f3) 0.965; Ocrolus (f4) 0.964.

Synthetic by profile: clean 0.890, jpeg 0.878, lighting 0.862, noise 0.863, rotate 0.854, lowres 0.835,
blur 0.798, scan 0.759.

---

## 1. Resolution dependence — mostly fixed in v5

v5 upscales images narrower than 2550 px (capped at 12 MP) and drops boxes under 0.8x the page's median size
(the upscale exposed white-on-black sidebar letters as candidates). Details and numbers: `git log 5743f11`.

Remaining:
- 100 DPI mean IoU 0.874 (vs 1.000 at 300 DPI): the hole mapped back from the upscaled image is not the one the GT
  was drawn from. Matches still pass IoU 0.5 comfortably.
- `scan` (0.759) and `blur` (0.798) still trail `clean` (0.890). Their weak tags are faint (#6), offcenter
  (scan 0.559, blur 0.588) and crossing strokes (#3/#5).
- 100 DPI pages now cost as much as 300 DPI pages.

Lessons: text height is a worse scale proxy than page width here (box/text height 0.59-2.5, box/page width
0.0063-0.016). Features around a hole (outer-ring ink, per-side paper, border thickness) do not separate glyph
holes from real boxes at 100 DPI; page-level size consistency does.

## 2. Size gate relative to page width — mostly fixed in v6

The size gate (`min_side_frac`, `max_side_frac`, `min_line_frac`) is a fraction of page width. Plaza (median box
side / page width 0.0075) and the MGIC checklist pp. 26-28 (0.0076) fall under `min_side_frac` 0.008; GSE forms are
0.011. v6 retries pages where the normal pass finds < 3 boxes with the fractions / 1.5 and a 1.5x larger upscale,
and filters rounded glyph holes on that retry with `corner_ratio`. Details and rejected alternatives:
`git log e8a26c6`.

Remaining:
- Only pages with < 3 boxes are retried. A page mixing normal and small boxes, or with 1-2 small boxes, still misses
  the small ones. Boxes under 0.0053 of page width or over `max_side_frac` (0.025) are still missed; the real set
  has neither.
- Misses: `f3_plaza_p24` 4 boxes per DPI, `f2_mgic_p28` 1 per DPI, `f3_plaza_p11` 3 small tall boxes at 100 DPI
  (corner ratio under 0.6).
- Text-only pages now run the detector twice (the retry at up to 27 MP): the real set takes ~29 s instead of ~21 s.

Lessons: these forms fill the page (ink spans 0.88-0.92 of the width) and just use small boxes, so there is no
"form scale" to estimate from the page. Hole aspect, hole corner fill and border thickness don't separate glyph
holes from real boxes at 100 DPI; the ink depth along the corner diagonals vs the sides does (boxes ~1, glyphs
<= 0.53).

## 3. Marks touching or crossing the border break the "enclosed square" test

- Synthetic (all profiles): crossing_stroke recall 0.520, filled 0.864, offcenter 0.804, overshoot 0.915. On clean
  images: crossing_stroke recall 0.576, filled 0.875.
- Real: Ocrolus 22 checked boxes missed across DPIs (`f4_ocrolus_1004_p01.png` 8, `p03.png` 12: big check marks
  overshooting the border). The v4 loss at 150 DPI on filled 1004s is fixed by v5.
- Repro (still missed in v5): `synthetic/clean/clean_000_b6_2055_p06.png` box `[1374, 3456, 1402, 3484]` (crossing
  stroke); `clean_010_b3_1025_p01.png` `[2034, 2583, 2062, 2611]` (filled); `clean_016_b4_1073_p02.png`
  `[306, 3344, 334, 3372]` (off-center).

Suspected cause (verify): boxes are found as holes in the line mask; strokes connected to the border split the
hole or lower `min_fill` / break `has_solid_border`. A filled interior leaves only a thin ring as the "hole".

Techniques to try:
- Find boxes from the four border lines (h/v segments forming a square; `cv2.createLineSegmentDetector` exists in
  the installed OpenCV 5.0) rather than from the hole.
- Template matching with the page's own median empty box, masked to the border ring (interior marks don't matter).
- Remove non-line ink before the hole test.

## 4. Broken box edges (gap near a corner)

Boxes affected: 284 of 295 missed (`cond:broken_corner`, recall 0.037), all profiles including clean.

- Repro: `synthetic/clean/clean_001_b7_1004mc_p01.png` box `[2041, 1053, 2070, 1082]` (still missed).
- Cause: the v4 gap bridging closes at most `recover_gap_frac` x width ~ 8 px; the synthetic breaks are 30-50 % of a
  side (~9-14 px). May be harsher than the sample_2 case v4 was built for; the real set has no broken boxes, so
  this is synthetic-only evidence.

Techniques to try: accept three-sided squares at the page's dominant box size; corner (L-junction) detection;
bridge gaps proportional to the expected box side; the border-template matching from #3.

Watch: table cells and brackets that look like three-sided boxes (#7).

## 5. Stray ink inside the box counted as a check (misclassification)

Wrong calls: 292 synthetic (v4: 244; v5 finds more hard boxes and misclassifies them). Also sample_2's one
remaining design-set error (erased X at `[197, 614, 218, 635]`).

- `mark:erased_x` (whited-out X leaving corner remains): 158 called checked (e2e 0.589).
- `mark:crossing_stroke` (stroke through the box, labeled unchecked): 95 called checked (e2e 0.270).
- `mark:overshoot`: 30 checked called unchecked.
- Repro (still wrong in v5): `synthetic/clean/clean_003_b5_1075_p06.png` box `[1319, 3426, 1347, 3454]` (erased X);
  `clean_001_b7_1004mc_p01.png` `[2266, 1000, 2295, 1029]` (crossing stroke).

Cause: classification is an ink ratio inside the box (`checked_ink_ratio` 0.06). v3 ignores strokes that cross the
box, but only those it recognises as lines; wavy hand strokes and corner remains still count.

Techniques to try:
- Features beyond the ink ratio: ink near the center vs corners (erased-X remains sit in the corners), strokes that
  stay inside vs continue outside, ink darkness from the gray image (erased marks are lighter), blob count.
  Start with a logistic regression on these.
- A small CNN on box crops (~48x48 with half a box of margin), trained with PyTorch in a dev dependency group and
  exported to ONNX; run with `cv2.dnn.readNetFromONNX` so production still only needs opencv. Later it can become
  3-class (not a box / unchecked / checked) and filter looser candidates (#2, #7).
- Data hygiene: train on synthetic seeds other than 0, never on `real.json`; the synthetic templates are the same
  blank forms as the real `b*` sources, so split by form type to avoid learning layouts.

Watch: small and off-center checks must stay checked; the real set has no handwriting (171 checked boxes, all
printed), so real classification accuracy says little.

## 6. Faint or gray boxes next to dark content

Boxes affected: 107 missed and 17 misclassified of 365 (`cond:faint`, e2e 0.660); scan 0.224, blur 0.542, lowres 0.660, clean 0.789.

- Repro (still missed in v5): `synthetic/clean/clean_004_b2_1004c_p04.png` box `[1291, 3340, 1319, 3368]`.
- Cause: the adaptive threshold (block 31, C 15) drops the light border when a dark block is inside the window; the
  v4 faint recovery (`faint_ink_contrast` 30) fails once blur/noise/JPEG reduce the contrast further.

Techniques to try: background division or CLAHE before binarizing; Sauvola thresholding; multi-threshold
candidates; checking border contrast against the local paper level only; the border-template matching from #3.
A binarization change affects every image: check sample_2 (JPEG) carefully.

## 7. False positives: table grid cells, shaded cells, glyphs

Real: 77 FP (v4 217). By page (all DPIs): `b3_1025_p02` 60, `f1_realvals_1004_p04` 5, `b8_2055_legacy_p01` 4,
`b2_1004c_p01`/`p03` 6 (sidebar letters at low DPI), `f1_realvals_1004_p05` 2. Synthetic 56.

- Repro: `data/holdout/real/300/b3_1025_p02.png`: the "Tot / Br / Ba" header cells (called checked because of the
  text) and the empty "Unit # 4" row cells; `b8_2055_legacy_p01.png`: a gray shaded cell next to "Predominant". (The Plaza sidebar "D" FP is gone
  in v6: `corner_ratio` on the small-box retry rejects it.)
- Cause: a small square cell of a table is geometrically a checkbox. Nothing checks context.

Techniques to try: reject candidates that share edges with neighbours (part of a grid); require white margin on at
least one side; reject cells whose border lines continue past the corners; `corner_ratio` (v6, only on the small-box retry now) on every pass; the learned verifier from #5.

Watch: `cond:table_line` and `cond:adjacent` (#8) must not get worse.

## 8. Adjacent boxes and boxes touching table lines (minor)

`cond:adjacent` e2e 0.803 (v4 0.750), `cond:table_line` 0.875 (v4 0.830; 22 missed, 14 misclassified). Weakest in
blur (adjacent 0.600). The touching line merges into the border and changes the hole shape or adds ink inside.
Re-check after #3.

---

## Dataset caveats

- Real labels: one reviewer, starting from detector pre-annotations. An audit found no errors, but boxes missed by
  both the reviewer and every detector pass can't be ruled out.
- The real set has only 171 checked boxes, all printed or software marks. There is no handwriting, so real
  classification accuracy (1.000) says little. Handwriting is only in the synthetic set.
- The blank 1004-family forms share a layout with `data/`; their 1.00 recall is weak evidence. The filled samples
  and the 1025/1073/1075/2055/legacy layouts are the real test.
- Synthetic severities (break length, faintness, stroke shapes) are the generator's choices. Compare a category
  before and after a change, not across categories.
- Design-set GT boxes are v4's holes at native resolution, so IoU on upscaled images (sample_2: 0.939) is slightly
  lower without being worse.
