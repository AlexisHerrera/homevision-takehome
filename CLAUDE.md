# CLAUDE.md

## Rules

- Do not add Claude as a co-author in git commits or PR descriptions (no `Co-Authored-By: Claude ...` lines, no "Generated with Claude Code" footers).

## Project

Detect checkboxes in US mortgage appraisal form images (`data/`, e.g. URAR 1004, 1004MC, 1004C) and classify each as `checked` / `unchecked`.

- `src/checkboxes/detector.py` — OpenCV detector core: `detect(image) -> list[Detection]`, no I/O. Bump `MODEL_VERSION` when its logic or parameters change.
- `src/checkboxes/images.py` — decodes uploaded images (OpenCV) and enforces the pixel limit.
- `src/checkboxes/api/` — FastAPI app (`app.py` factory, `config.py` settings from `CHECKBOXES_*` env vars, `schemas.py`, `routes/`). `POST /detect` (multipart `file`) returns `{"boxes": [{"bbox": [x1, y1, x2, y2], "is_checked"}]}`; `GET /health`.
- `scripts/detect_checkboxes.py` — CLI: writes Label Studio pre-annotations to `output/tasks.json`; `--debug output/debug` writes overlay images (green = checked, red = unchecked).
- `data/labels.json` — hand-reviewed ground truth (Label Studio JSON export: detector pre-annotations corrected in the UI). Use it to evaluate the detector.
- `scripts/evaluate.py` — scores the detector against `data/labels.json` (IoU ≥ 0.5 matching: precision/recall/F1, classification and end-to-end accuracy). `--errors` lists every error; `--record --note "..."` appends the run to `evaluations/history.jsonl`; `--history` prints past runs. Record with a clean working tree so the run is tied to a commit.
- `label_studio/labeling_config.xml` — Label Studio config (RectangleLabels `checked` / `unchecked`, `from_name="label"`, `to_name="image"`; must match the detector output).
- `scripts/start_label_studio.sh` — starts Label Studio (via `uvx`, isolated from the project env) with local file serving rooted at the repo.
- `Dockerfile`, `compose.yaml` — production image of the API (uv multi-stage, non-root, port 8000); `docker compose up --build` runs it.

## Environment

- Managed with uv (Python 3.12, `.python-version`). `uv sync` creates `.venv/`; run things with `uv run ...`.
- Before committing: `uv run ruff format . && uv run ruff check . && uv run pytest`.
- Dev server: `uv run uvicorn checkboxes.api.app:app --reload` (docs at `/docs`).
- Label Studio is not a project dependency (heavy, conflicting deps); the start script runs it with `uvx`. Its data (users, projects) lives in `~/Library/Application Support/label-studio/`, not in the repo.
