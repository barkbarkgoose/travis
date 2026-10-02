#!/usr/bin/env bash
set -euo pipefail

# Prefer the project virtualenv when it exists; otherwise let uv provision the
# backend dependencies so a fresh checkout can boot without manual setup.
if [ -x ".venv/bin/python" ]; then
  exec .venv/bin/python dev.py "$@"
fi

exec uv run --with-requirements backend/requirements.txt python dev.py "$@"
