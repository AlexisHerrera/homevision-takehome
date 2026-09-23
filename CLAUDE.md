# CLAUDE.md

## Rules

- Do not add Claude as a co-author in git commits or PR descriptions (no `Co-Authored-By: Claude ...` lines, no "Generated with Claude Code" footers).

## Project

Detect checkboxes in US mortgage appraisal form images (`data/`, e.g. URAR 1004, 1004MC, 1004C) and classify each as `checked` / `unchecked`.

- `scripts/detect_checkboxes.py` — OpenCV detector. Writes Label Studio pre-annotations to `output/tasks.json`; `--debug output/debug` writes overlay images (green = checked, red = unchecked).
- `data/labels.json` — hand-reviewed ground truth (Label Studio JSON export: detector pre-annotations corrected in the UI). Use it to evaluate the detector.
- `label_studio/labeling_config.xml` — Label Studio config (RectangleLabels `checked` / `unchecked`, `from_name="label"`, `to_name="image"`; must match the detector output).
- `scripts/start_label_studio.sh` — starts Label Studio with local file serving rooted at the repo.

## Environment

- Single venv at `.venv/` (Python 3.12 via pyenv; the system Python is 3.14, which Label Studio may not support yet). Setup:
  `~/.pyenv/versions/3.12.13/bin/python -m venv .venv && .venv/bin/pip install -r requirements.txt`
- Label Studio data (users, projects) lives in `~/Library/Application Support/label-studio/`, not in the repo.
