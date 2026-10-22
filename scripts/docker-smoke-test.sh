#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_ID="$$"
IMAGE="travis-recovery:docker-smoke-${RUN_ID}"
CONTAINER="travis-recovery-docker-smoke-${RUN_ID}"
VOLUME="travis-recovery-docker-smoke-${RUN_ID}"
PORT="${DOCKER_SMOKE_PORT:-18080}"
BASE_URL="http://127.0.0.1:${PORT}"

cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  docker volume rm "$VOLUME" >/dev/null 2>&1 || true
  docker image rm "$IMAGE" >/dev/null 2>&1 || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo "==> Building VPS image"
docker build --tag "$IMAGE" "$ROOT_DIR"

echo "==> Creating temporary container storage"
docker volume create "$VOLUME" >/dev/null
SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"

echo "==> Starting container on http://127.0.0.1:${PORT}"
docker run --detach \
  --name "$CONTAINER" \
  --publish "127.0.0.1:${PORT}:8000" \
  --mount "type=volume,source=${VOLUME},target=/data" \
  --env DJANGO_ENV=production \
  --env MEDIA_STORAGE_BACKEND=filesystem \
  --env "SECRET_KEY=${SECRET_KEY}" \
  --env ALLOWED_HOSTS=127.0.0.1,localhost \
  --env DATABASE_URL=sqlite:////data/db.sqlite3 \
  --env MEDIA_ROOT=/data/media \
  --env SECURE_SSL_REDIRECT=0 \
  --env PORT=8000 \
  "$IMAGE" >/dev/null

ready=0
for ((attempt = 1; attempt <= 40; attempt++)); do
  if curl --fail --silent --show-error --max-time 2 "$BASE_URL/" >/dev/null 2>&1; then
    ready=1
    break
  fi
  if [[ "$(docker inspect --format '{{.State.Running}}' "$CONTAINER" 2>/dev/null || true)" != "true" ]]; then
    break
  fi
  sleep 1
done

if [[ "$ready" != "1" ]]; then
  echo "Docker container did not become ready. Container logs:" >&2
  docker logs "$CONTAINER" >&2 || true
  exit 1
fi

echo "==> Checking Django and running the deployment migration step"
docker exec "$CONTAINER" python manage.py check
docker exec "$CONTAINER" python manage.py migrate --noinput
python3 - "$BASE_URL" <<'PY'
import re
import sys
from urllib.request import urlopen

base_url = sys.argv[1]
import json
with urlopen(f"{base_url}/health/", timeout=5) as response:
    assert json.load(response) == {"status": "ok"}
with urlopen(f"{base_url}/", timeout=5) as response:
    html = response.read().decode("utf-8")
    assert response.status == 200, f"Home returned HTTP {response.status}"

assert 'id="app"' in html, "The response does not look like the Vue SPA index.html"
assets = re.findall(r'(?:src|href)="(/assets/[^\"]+)"', html)
assert assets, "No built /assets/ references found in the SPA HTML"

for asset in assets:
    with urlopen(f"{base_url}{asset}", timeout=5) as response:
        assert response.status == 200, f"Asset {asset} returned HTTP {response.status}"
print(f"SPA HTML and {len(assets)} built asset(s) returned HTTP 200.")
PY

echo "==> Checking the mounted database and media paths survive a restart"
docker exec "$CONTAINER" python manage.py shell -c \
  "from django.db import connection; c=connection.cursor(); c.execute('CREATE TABLE IF NOT EXISTS docker_smoke_marker (value TEXT)'); c.execute('INSERT INTO docker_smoke_marker VALUES (?)', ['persisted'])"
docker exec "$CONTAINER" python manage.py shell -c \
  "from django.conf import settings; p=settings.MEDIA_ROOT / '.docker-smoke-marker'; p.parent.mkdir(parents=True, exist_ok=True); p.write_text('persisted')"

docker restart "$CONTAINER" >/dev/null
ready=0
for ((attempt = 1; attempt <= 40; attempt++)); do
  if curl --fail --silent --show-error --max-time 2 "$BASE_URL/" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done

if [[ "$ready" != "1" ]]; then
  echo "Container did not recover after restart. Container logs:" >&2
  docker logs "$CONTAINER" >&2 || true
  exit 1
fi

docker exec "$CONTAINER" python manage.py shell -c \
  "from django.db import connection; c=connection.cursor(); c.execute('SELECT value FROM docker_smoke_marker'); assert c.fetchone()[0] == 'persisted'"
docker exec "$CONTAINER" python manage.py shell -c \
  "from django.conf import settings; assert (settings.MEDIA_ROOT / '.docker-smoke-marker').read_text() == 'persisted'"

echo "Docker smoke check passed. Temporary container, volume, and image will be removed."
