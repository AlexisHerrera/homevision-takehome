#!/usr/bin/env bash
# Start Label Studio with local file serving enabled, rooted at the repo,
# so tasks can reference images as /data/local-files/?d=data/<file>.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export LABEL_STUDIO_LOCAL_FILES_SERVING_ENABLED=true
export LABEL_STUDIO_LOCAL_FILES_DOCUMENT_ROOT="$ROOT"
exec "$ROOT/.venv/bin/label-studio" "$@"
