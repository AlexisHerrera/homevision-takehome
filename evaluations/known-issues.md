# Detector: known issues and work plan

Living document: the open problems of the current detector, measured on the held-out sets, and how to work on
them. Update it at the end of every session (status table, current numbers, the section you worked on). The
explanation of each change lives in its commit message (`uv run scripts/evaluate.py --history`, then
`git log <hash>`); the numbers of every recorded run live in `evaluations/history.jsonl`.

Current detector: `opencv-v8` (commit `dcfcedd`). Next suggested: #5 (crossing strokes called checked): v8 now
finds 91% of the crossing-stroke boxes, but calls 81 of them (seed 0) checked; they are the largest error left on
the synthetic set.

| # | Issue | Status | Main metric now |
|---|---|---|---|
| 1 | Resolution dependence | Mostly fixed in v5 | real 100 DPI e2e 0.984 (v4 0.000); synthetic scan 0.890 |
| 2 | Size gate relative to page width | Mostly fixed in v6 | Plaza 0.967 (v5 0.000), MGIC 0.996 (v5 0.430) |
| 3 | Marks touching/crossing the border | Mostly fixed in v8 | crossing_stroke recall 0.908 (v7 0.520), filled 0.916, offcenter 0.905 |
| 4 | Broken box edges | Half fixed in v8 | broken_corner recall 0.549 (v7 0.037) |
| 5 | Stray ink counted as a check | Open again: v8 finds boxes v7 missed | crossing_stroke e2e 0.696 with 81 miscls; 130 synthetic miscls (v7 75) |
| 6 | Faint boxes | Open, improved by v5 | faint e2e 0.704; scan 0.286 |
| 7 | False positives: table/shaded cells, glyphs | Open, improved by v5 | 78 real FP, 60 of them on b3_1025_p02 |
| 8 | Adjacent boxes / touching table lines | Open, improved by v5/v8 | adjacent 0.879, table_line 0.948 |

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
4. Guardrail: `tests/test_samples.py` fails on any missed/extra box or misclassification on the 4 samples
   (`KNOWN_MISCLASSIFIED` is empty since v7). `tests/test_detector.py` has synthetic cases (e.g. a check whose
   vertex is below the box) that encode intended behavior; don't loosen them to make a change pass.
5. Check the whole held-out set, not just the targeted slice: every group and tag should be equal or better, or the
   regression explained. Then check a fresh synthetic seed so the fix doesn't just fit seed 0:
   ```sh
   uv run scripts/holdout_synthetic.py --seed 1 --per-profile 20   # overwrites data/holdout/synthetic.json
   # evaluate old vs new: `git stash push src/checkboxes/detector.py` (not a bare `git stash`: it would also
   # stash the regenerated synthetic.json and pair seed-0 labels with seed-1 images)
   uv run scripts/holdout_synthetic.py --seed 0 --per-profile 20   # restore; synthetic.json must end unchanged
   ```
   Tune on other seeds, not on 0 and 1. The generator's output paths are module constants; v8 was tuned on seeds 2
   and 3 written to `data/holdout/dev2/` + `dev2.json` (etc.) by a wrapper that sets `OUT_DIR` / `LABELS` and calls
   `main()`, then scored with `--labels data/holdout/dev2.json`. Move them out of the repo before recording.
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

## Current numbers (opencv-v8)

e2e = found with the right label / all GT boxes.

| Set | GT | Precision | Recall | Cls acc | e2e | v7 e2e |
|---|---|---|---|---|---|---|
| data/labels.json (design) | 288 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| real 300 DPI | 1831 | 0.992 | 0.995 | 1.000 | 0.995 | 0.995 |
| real 200 DPI | 1831 | 0.990 | 0.995 | 1.000 | 0.995 | 0.995 |
| real 150 DPI | 1831 | 0.989 | 0.993 | 1.000 | 0.993 | 0.992 |
| real 100 DPI | 1831 | 0.987 | 0.984 | 1.000 | 0.984 | 0.975 |
| synthetic seed 0 (all) | 5760 | 0.989 | 0.952 | 0.976 | 0.929 | 0.877 |
| synthetic seed 1 (all, fresh) | 6643 | 0.982 | 0.948 | 0.976 | 0.925 | 0.865 |

Real by source (all DPIs): blank forms b1-b8 recall 1.000 (b3 60 FP, b2 6, b8 5); RealVals (f1) 0.967;
MGIC (f2) 0.996; Plaza (f3) 0.967; Ocrolus (f4) 0.972.

Synthetic by profile: clean 0.959, jpeg 0.951, lighting 0.948, noise 0.948, rotate 0.936, lowres 0.922,
blur 0.898, scan 0.890.

Runtime: the real set (240 pages) takes ~44 s (v7 ~28 s); the v8 border matching adds ~65 ms per 10 MP page.

---

## 1. Resolution dependence — mostly fixed in v5

v5 upscales images narrower than 2550 px (capped at 12 MP) and drops boxes under 0.8x the page's median size
(the upscale exposed white-on-black sidebar letters as candidates). Details and numbers: `git log 5743f11`.

Remaining:
- 100 DPI mean IoU 0.874 (vs 1.000 at 300 DPI): the hole mapped back from the upscaled image is not the one the GT
  was drawn from. Matches still pass IoU 0.5 comfortably.
- `scan` (0.890) and `blur` (0.898) still trail `clean` (0.959). Their weak tags are faint (#6) and crossing
  strokes called checked (#5).
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

## 3. Marks touching or crossing the border — mostly fixed in v8

Cause (confirmed on dev seeds): near-horizontal/vertical hand strokes pass the morphological line filter, so they
split the box's hole in the line mask, intrude on it (fill) or close it off. v8 adds a recovery pass,
`match_border`: it learns the page's box border (thickness per side) from the mean of the strict boxes, then scores
every hole position by ink on the four border sides without corners (>= 0.9), in a thin band inside the hole
(<= 0.4) and in a band outside the border (<= 0.8, rejects white-on-black letters). Details, rejected alternatives
and numbers: `git log dcfcedd`.

Remaining:
- Seed 0 misses: crossing_stroke 35 (most also faint or broken), filled 24, offcenter 30, overshoot 26. Most
  remaining misses carry `cond:faint` or `cond:broken_corner`.
- Real: Ocrolus 17 missed (checks on gray squares with no drawn border: nothing to match), RealVals 19 (software
  X's whose gray bottom edge drops out of the adaptive binary at 100/150 DPI; the ring scores 0.85-0.89). The
  ring threshold can't go lower: 0.87 adds 14 real FPs (table cells), 0.85 adds 67.
- Only runs on pages with >= 3 strict boxes of the median size, and only finds boxes of the median size: a second
  box size on the same page is not recovered.
- New FP: `real/200/b8_2055_legacy_p01.png` `[483, 1425, 507, 1448]`, a small glyph rectangle whose missing sides
  are supplied by thick table rules.

Techniques to try next: match with `faint_ink` added only for the ring (adding it to all bands cost +20 real FP);
several templates when a page has two box sizes.

## 4. Broken box edges (gap near a corner) — half fixed in v8

Boxes affected: 133 of 295 missed (`cond:broken_corner`, recall 0.549; v7 0.037). v8's border matching leaves the
corners out of the ring, so a break near a corner costs little of the score; breaks that run far along a side
still drop the ring under 0.9.

- Repro (v7): `synthetic/clean/clean_001_b7_1004mc_p01.png` box `[2041, 1053, 2070, 1082]`.
- Cause: the v4 gap bridging closes at most `recover_gap_frac` x width ~ 8 px; the synthetic breaks are 30-50 % of a
  side (~9-14 px). May be harsher than the sample_2 case v4 was built for; the real set has no broken boxes, so
  this is synthetic-only evidence.

Techniques to try: per-side ring scores in `match_border` (accept three full sides plus a partial fourth);
corner (L-junction) detection; bridge gaps proportional to the expected box side.

Watch: table cells and brackets that look like three-sided boxes (#7).

## 5. Stray ink inside the box counted as a check (misclassification) — improved in v7, crossing strokes open

v7 treats line pixels inside the box as strokes, so the in-box piece of a crossing stroke is removed with the rest
of it, and calls a box checked if its core (25% margin) has ink, or the inner area (15% margin) has enough ink
outside pieces confined to one corner (erased marks leave their ends in the corners). Details, rejected
alternatives and numbers: `git log 3935312`.

Wrong calls now: 130 synthetic seed 0 (v7 75, v6 292), 152 seed 1 (v7 87); design set 0. The increase is v8
finding crossing-stroke boxes v7 missed: they are the boxes whose stroke is line-like, which is also why they
are called checked.

- `mark:crossing_stroke`: 81 called checked (seed 0; v7 29, when most of these boxes were missed). The part of
  the stroke outside the box is straight enough to be a line, so the chain to the window edge breaks (outside the
  box, line pixels are not strokes). Repro: seed 2 (dev, see the workflow) `clean_004_b4_1073_p01.png` `[1285, 2328, 1313, 2357]`
  (a near-horizontal stroke); on seed 0 list them with `--errors | grep misclassified`. Making short line pieces outside the box strokes fixes most of these but links X arms to nearby text
  (overshoot 48 -> 110+ on the dev seeds).
- `mark:overshoot`: 34 checked called unchecked (v6 30). The arms run into nearby text or rules and the whole mark
  is linked to the window edge and removed. Mostly in noisy/low-res profiles, where the binary is busy.
- `scan` has 31 of the 75 wrong calls.
- Thin margin on real data: an Ocrolus software check crossing the left border of a split hole (#3) scores 0.122
  against the 0.1 core threshold at 300 DPI; `core_margin` 0.3 broke it.
- Repro: the v6 repros (`clean_003_b5_1075_p06.png` erased X, `clean_001_b7_1004mc_p01.png` crossing stroke) are
  fixed. The only wrong calls left on `clean` are `clean_009_b5_1075_p02.png` `[1437, 2057, 1465, 2086]` (erased
  X on a faint box, called checked) and `clean_012_b5_1075_p01.png` `[2033, 2461, 2061, 2489]` (overshooting X on a
  broken corner, called unchecked); the crossing-stroke errors are in the degraded profiles.

Techniques to try next:
- Tell a stroke's straight outer pieces from form lines by length on the whole page (form lines run far past the
  window; stroke pieces are ~1 box side) instead of treating every line pixel outside the box as a form line.
- For overshoot: follow a stroke out of the box only while it keeps its direction, instead of any connection to
  the window edge.
- A small CNN on box crops (~48x48 with half a box of margin), trained with PyTorch in a dev dependency group and
  exported to ONNX; run with `cv2.dnn.readNetFromONNX` so production still only needs opencv. Later it can become
  3-class (not a box / unchecked / checked) and filter looser candidates (#2, #7). Train on synthetic seeds other
  than 0 and 1, never on `real.json`; split by form type to avoid learning layouts.

Watch: small and off-center checks must stay checked; the real set has no handwriting (171 checked boxes, all
printed), so real classification accuracy says little.

## 6. Faint or gray boxes next to dark content

Boxes affected: 107 missed and 1 misclassified of 365 (`cond:faint`, e2e 0.704); scan 0.286, blur 0.562, lowres 0.720, clean 0.789.

- Repro (still missed in v5): `synthetic/clean/clean_004_b2_1004c_p04.png` box `[1291, 3340, 1319, 3368]`.
- Cause: the adaptive threshold (block 31, C 15) drops the light border when a dark block is inside the window; the
  v4 faint recovery (`faint_ink_contrast` 30) fails once blur/noise/JPEG reduce the contrast further.

Techniques to try: background division or CLAHE before binarizing; Sauvola thresholding; multi-threshold
candidates; checking border contrast against the local paper level only; the border-template matching from #3.
A binarization change affects every image: check sample_2 (JPEG) carefully.

## 7. False positives: table grid cells, shaded cells, glyphs

Real: 78 FP (v4 217). By page (all DPIs): `b3_1025_p02` 60, `f1_realvals_1004_p04` 5, `b8_2055_legacy_p01` 5,
`b2_1004c_p01`/`p03` 6 (sidebar letters at low DPI), `f1_realvals_1004_p05` 2. Synthetic 56.

- Repro: `data/holdout/real/300/b3_1025_p02.png`: the "Tot / Br / Ba" header cells (called checked because of the
  text) and the empty "Unit # 4" row cells; `b8_2055_legacy_p01.png`: a gray shaded cell next to "Predominant". (The Plaza sidebar "D" FP is gone
  in v6: `corner_ratio` on the small-box retry rejects it.)
- Cause: a small square cell of a table is geometrically a checkbox. Nothing checks context.

Techniques to try: reject candidates that share edges with neighbours (part of a grid); require white margin on at
least one side; reject cells whose border lines continue past the corners; `corner_ratio` (v6, only on the small-box retry now) on every pass; the learned verifier from #5.

Watch: `cond:table_line` and `cond:adjacent` (#8) must not get worse.

## 8. Adjacent boxes and boxes touching table lines (minor)

`cond:adjacent` e2e 0.879 (v7 0.818), `cond:table_line` 0.948 (v7 0.910; 9 missed, 6 misclassified). v8's border
matching recovers many: the touching line only adds ink to the ring. The misses left merge into the border and
change its thickness on that side.

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
