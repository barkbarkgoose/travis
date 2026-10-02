#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Run this ON THE SERVER, inside the virtualenv cPanel's "Setup Python App"
# page activates for you (see docs/HOSTING.md) — not on your own machine,
# and not for local development (use ./dev.sh for that).
#
# Skips the frontend build by default: shared hosting often has no Node.js,
# or too little memory for `vite build` + `vue-tsc` to run comfortably.
# Build it on your own machine instead and upload frontend/dist/ (the guide
# has the exact rsync command). Pass --build-frontend if Node is available
# on the server and you'd rather build it there.

BUILD_FRONTEND=0
for arg in "$@"; do
  case "$arg" in
    --build-frontend) BUILD_FRONTEND=1 ;;
    *)
      echo "Unknown option: $arg" >&2
      echo "Usage: ./deploy.sh [--build-frontend]" >&2
      exit 1
      ;;
  esac
done

echo "==> Installing backend dependencies"
pip install -r backend/requirements.txt

if [ "$BUILD_FRONTEND" = "1" ]; then
  echo "==> Building frontend"
  (cd frontend && pnpm install --frozen-lockfile && pnpm build)
else
  echo "==> Skipping frontend build (pass --build-frontend to build it here instead)"
  if [ ! -f frontend/dist/index.html ]; then
    echo "    frontend/dist/index.html not found — upload a build before restarting." >&2
  fi
fi

echo "==> Applying migrations"
(cd backend && DJANGO_ENV=production python manage.py migrate --noinput)

echo "==> Collecting Django's own static files (admin, DRF browsable API)"
(cd backend && DJANGO_ENV=production python manage.py collectstatic --noinput)

echo "==> Restarting the app"
mkdir -p backend/tmp
touch backend/tmp/restart.txt

echo "Done."
