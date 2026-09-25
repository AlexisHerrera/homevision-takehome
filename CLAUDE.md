# CLAUDE.md

## Rules

- Do not add Claude as a co-author in git commits or PR descriptions (no `Co-Authored-By: Claude ...` lines, no "Generated with Claude Code" footers).

## Project

Detect checkboxes in US mortgage appraisal form images (`backend/data/`, e.g. URAR 1004, 1004MC, 1004C) and classify each as `checked` / `unchecked`.

Layout: `backend/` (Python project: detector, API, evaluation tooling, data), `frontend/` (React UI), `infra/` (Terraform). Paths below under `src/`, `scripts/`, `data/`, `tests/`, `evaluations/`, `label_studio/` are relative to `backend/`; run Python commands from there.

- `src/checkboxes/detector.py` — OpenCV detector core: `detect(image, params=DetectorParams()) -> list[Detection]`, no I/O. Tunables live in the frozen `DetectorParams` dataclass. Bump `MODEL_VERSION` when its logic or parameters change.
- `src/checkboxes/images.py` — checks the pixel limit from the image header (Pillow) before decoding with OpenCV.
- `src/checkboxes/api/` — FastAPI app (`app.py` factory, `config.py` settings from `CHECKBOXES_*` env vars, `schemas.py`, `routes/`). `POST /detect` (multipart `file`) returns `{"boxes": [{"bbox": [x1, y1, x2, y2], "is_checked"}]}`; `GET /health`.
- `scripts/detect_checkboxes.py` — CLI: writes Label Studio pre-annotations to `output/tasks.json`; `--debug output/debug` writes overlay images (green = checked, red = unchecked).
- `data/labels.json` — hand-reviewed ground truth (Label Studio JSON export: detector pre-annotations corrected in the UI). Use it to evaluate the detector.
- `scripts/evaluate.py` — scores the detector against `data/labels.json` (IoU ≥ 0.5 matching: precision/recall/F1, classification and end-to-end accuracy). `--errors` lists every error; `--record --note "..."` appends the run to `evaluations/history.jsonl`; `--history` prints past runs. Record with a clean working tree so the run is tied to a commit. `--labels` scores another set; `--group-by REGEX` / `--breakdown` give per-group and per-tag totals; `--images REGEX` and `--params key=value,...` are for experiments (not recordable).
- `data/holdout/` — held-out sets (images gitignored, labels committed): `real.json` (12 real PDFs at 100/150/200/300 DPI; `scripts/holdout_real.py fetch && ... render`) and `synthetic.json` (filled forms with 8 degradation profiles and per-box mark/condition tags; `scripts/holdout_synthetic.py --seed 0 --per-profile 20`).
- `evaluations/known-issues.md` — the detector's open problems on the held-out sets, current numbers, and the session workflow for improving it. Start detector work there and update it at the end. The explanation of each detector change goes in its commit message, not in files.
- `tests/test_samples.py` — fails on any regression on the 4 samples in `data/labels.json`.
- `label_studio/labeling_config.xml` — Label Studio config (RectangleLabels `checked` / `unchecked`, `from_name="label"`, `to_name="image"`; must match the detector output).
- `scripts/start_label_studio.sh` — starts Label Studio (via `uvx`, isolated from the project env) with local file serving rooted at `backend/`.
- `backend/Dockerfile` — production image of the API (uv multi-stage, non-root, port 8000). The same image runs on Lambda via the Lambda Web Adapter extension (inert outside Lambda).
- `compose.yaml` (repo root) — `docker compose up --build` runs the API (:8000) and the frontend behind nginx (:8080, `/api` proxied like CloudFront; `frontend/Dockerfile`, `frontend/nginx.conf`).
- `frontend/` — React + TypeScript (Vite) UI calling `/api/*`; `npm run dev` proxies `/api` to `localhost:8000`. Samples are copied from `backend/data/` at dev/build time.
- `infra/` — Terraform. `infra/bootstrap/` (local state, applied once): state bucket, ECR, GitHub OIDC deploy role. `infra/`: Lambda (arm64, `CHECKBOXES_ROOT_PATH=/api`), API Gateway HTTP API (throttled), S3 + CloudFront (optional `domain_name`: ACM cert in us-east-1 + Route 53 alias; GitHub variable `DOMAIN_NAME` in CI), kill switch (throttle to 0) triggered by a CloudWatch invocations alarm or the $20 budget. Region `us-west-2`, account pinned with `allowed_account_ids`; always use `AWS_PROFILE=homevision`.
- `.github/workflows/ci.yml` — lint/test/frontend/terraform checks; on `main` also deploys (OIDC role). `scripts/deploy.sh` (repo root) does the same deploy by hand.

## Environment

- Backend managed with uv (Python 3.12, `backend/.python-version`). `uv sync` in `backend/` creates `backend/.venv/`; run things with `uv run ...`.
- Before committing: in `backend/`, `uv run ruff format . && uv run ruff check . && uv run pytest`; in `frontend/`, `npm run lint && npm run build`. The tracked pre-commit hook (`.githooks/pre-commit`, enabled with `git config core.hooksPath .githooks`) runs these checks and blocks the commit if they fail.
- Dev server: `uv run uvicorn checkboxes.api.app:app --reload` (docs at `/docs`).
- Label Studio is not a project dependency (heavy, conflicting deps); the start script runs it with `uvx`. Its data (users, projects) lives in `~/Library/Application Support/label-studio/`, not in the repo.
