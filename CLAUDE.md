# CLAUDE.md

## Rules

- Do not add Claude as a co-author in git commits or PR descriptions (no `Co-Authored-By: Claude ...` lines, no "Generated with Claude Code" footers).

## Environment

- Label Studio (used for image labeling) lives in its own venv: `.venv-labelstudio/` (Python 3.12). Run with `source .venv-labelstudio/bin/activate && label-studio`.
- The Python backend (to be added) should use a separate venv so its dependencies don't conflict with Label Studio's.
