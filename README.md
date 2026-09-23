# Checkbox detection API

Detects checkboxes in mortgage appraisal forms (URAR 1004, 1004MC, 1004C, ...) and classifies each as checked or unchecked.

## Run

```bash
docker compose up --build
```

The API is at http://localhost:8000 (interactive docs at http://localhost:8000/docs).

## API

`POST /detect` — multipart upload with a `file` field containing a document image (PNG, JPEG, TIFF, BMP or WebP).

```bash
curl -F file=@data/sample_1.png http://localhost:8000/detect
```

```json
{
  "boxes": [
    {"bbox": [333, 510, 383, 550], "is_checked": true},
    {"bbox": [491, 510, 542, 550], "is_checked": false}
  ]
}
```

`bbox` is `[x1, y1, x2, y2]` in pixels.
Errors: `413` file size or pixel count over the limit, `415` unsupported file, `422` missing file.

`GET /health` — liveness check.

### Configuration

Environment variables, or a `.env` file (also read by `docker compose`):

| Variable | Default | |
|---|---|---|
| `CHECKBOXES_MAX_UPLOAD_BYTES` | `20971520` | Max upload size (20 MB) |
| `CHECKBOXES_MAX_PIXELS` | `50000000` | Max pixels per image |
| `CHECKBOXES_CORS_ORIGINS` | `[]` | Browser origins allowed, e.g. `'["http://localhost:5173"]'` |

## Development

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run uvicorn checkboxes.api.app:app --reload
uv run ruff format . && uv run ruff check . && uv run pytest
```

### Evaluating the detector

`data/labels.json` is hand-reviewed ground truth. Score the detector and track changes over time:

```bash
uv run scripts/evaluate.py --errors                      # metrics + every error
uv run scripts/evaluate.py --record --note "what changed" # append to evaluations/history.jsonl
uv run scripts/evaluate.py --history
```

### Labeling

`scripts/start_label_studio.sh` starts Label Studio (config in `label_studio/labeling_config.xml`).
`uv run scripts/detect_checkboxes.py` writes detector output to `output/tasks.json` as pre-annotations to import and correct.
