# Checkbox detection

Detects checkboxes in mortgage appraisal forms and classifies each as checked or unchecked.

- Live demo: https://homevision.alexisherrera.dev
- GitHub repo: https://github.com/AlexisHerrera/homevision-takehome

<img width="740" height="480" alt="live_demo" src="https://github.com/user-attachments/assets/1d512369-9eeb-4a81-830f-5ecdaec8b4f3" />

## Run

```bash
docker compose up --build
```

The app is at http://localhost:8080 and the API at http://localhost:8000 (interactive docs at http://localhost:8000/docs).

Layout: `backend/` (detector, API, evaluation tooling and data), `frontend/` (React UI), `infra/` (Terraform).

## API

`POST /detect` — multipart upload with a `file` field containing a document image (PNG, JPEG, TIFF, BMP or WebP).

```bash
curl -F file=@backend/data/sample_1.png http://localhost:8000/detect
```

```json
{
  "boxes": [
    { "bbox": [333, 510, 383, 550], "is_checked": true },
    { "bbox": [491, 510, 542, 550], "is_checked": false }
  ]
}
```

`bbox` is `[x1, y1, x2, y2]` in pixels.
Errors: `413` file size or pixel count over the limit, `415` unsupported file, `422` missing file.

`GET /health` — liveness check.

### Configuration

Environment variables, or a `backend/.env` file (also read by `docker compose`):

| Variable                      | Default    |                                                             |
| ----------------------------- | ---------- | ----------------------------------------------------------- |
| `CHECKBOXES_MAX_UPLOAD_BYTES` | `20971520` | Max upload size (20 MB)                                     |
| `CHECKBOXES_MAX_PIXELS`       | `50000000` | Max pixels per image                                        |
| `CHECKBOXES_CORS_ORIGINS`     | `[]`       | Browser origins allowed, e.g. `'["http://localhost:5173"]'` |

## Frontend

`frontend/` is a React + TypeScript app (Vite): upload an image or pick a sample, and the boxes are drawn over it (green = checked, red = unchecked).

For live reload while developing:

```bash
cd backend && uv run uvicorn checkboxes.api.app:app --reload
cd frontend && npm install && npm run dev   # http://localhost:5173, proxies /api to :8000
```

`npm run build && npm run preview` serves the production build the same way. Before pushing: `npm run lint && npm run build`.

## Deployment (AWS)

```
browser ──> CloudFront ──/*──────> S3 (frontend)
                       └─/api/*──> API Gateway (HTTP API, throttled) ──> Lambda (container image, arm64)
```

- The API runs on Lambda from the same Docker image, through the [Lambda Web Adapter](https://github.com/awslabs/aws-lambda-web-adapter); it scales to zero, so idle cost is ~$0.
- Frontend and API share the CloudFront domain, so there is no CORS.
- Limits: 4 MB uploads (Lambda's 6 MB payload limit, base64-encoded), 25 MP images, 30 s timeout. API Gateway throttles at 2 requests/s (burst 5), though it enforces this approximately; the account's Lambda concurrency limit (10) is the hard ceiling.
- Uploaded images are only held in memory; logs are kept 7 days.
- Cost guard: a kill switch sets the API throttle to 0 (every request gets 429) until the next `terraform apply`. It fires on 500+ invocations in 5 minutes (a CloudWatch alarm, reacts in minutes) or when the $20 monthly budget is reached (billing data lags hours). The budget also emails at $5 (actual) and $15 (forecast).

Infrastructure is Terraform in `infra/`:

- `infra/bootstrap/` (applied once, local state): Terraform state bucket, ECR repository, and the GitHub OIDC role that CI deploys with.
- `infra/`: Lambda, API Gateway, S3 + CloudFront, budget and kill switch.

Every push to `main` runs CI (`.github/workflows/ci.yml`): lint, tests, frontend build, Terraform validate, then deploy (build and push the image, `terraform apply`, upload the frontend). To deploy by hand:

```bash
aws sso login --profile homevision
AWS_PROFILE=homevision scripts/deploy.sh   # alert_email from infra/terraform.tfvars (gitignored) or TF_VAR_alert_email
```

Tear down everything with `terraform destroy` in `infra/`, then in `infra/bootstrap/`.

### Scaling further

This setup handles one page per synchronous request. For batch processing of whole loan files, the natural next step is asynchronous: upload to S3, enqueue one message per page in SQS, and have Lambda workers (the same image) write results to a store the UI polls, with concurrency and retries handled by the queue.

## Development

Requires [uv](https://docs.astral.sh/uv/). Python commands run from `backend/`.

```bash
git config core.hooksPath .githooks   # pre-commit hook: backend ruff + pytest, frontend lint + typecheck
cd backend
uv sync
uv run uvicorn checkboxes.api.app:app --reload
uv run ruff format . && uv run ruff check . && uv run pytest
```

### Evaluating the detector

`backend/data/labels.json` is hand-reviewed ground truth. Score the detector and track changes over time:

```bash
uv run scripts/evaluate.py --errors                      # metrics + every error
uv run scripts/evaluate.py --record --note "what changed" # append to evaluations/history.jsonl
uv run scripts/evaluate.py --history
```

### Labeling

`scripts/start_label_studio.sh` starts Label Studio (config in `label_studio/labeling_config.xml`).
`uv run scripts/detect_checkboxes.py` writes detector output to `output/tasks.json` as pre-annotations to import and correct.
