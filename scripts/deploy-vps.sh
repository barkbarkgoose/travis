#!/usr/bin/env bash
# Run on the VPS from the reviewed release checkout as an administrator.
# Usage: sudo scripts/deploy-vps.sh /etc/travis-recovery/app.env RELEASE_TAG
# Existing data must already have been imported. This does not copy another host.
# A database migration can make the previous app image incompatible.
set -euo pipefail
if [[ $# != 2 || "$1" != /* || ! "$2" =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$ ]]; then
  echo "Usage: $0 /absolute/path/app.env RELEASE_TAG" >&2
  exit 2
fi
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$1"
export APP_IMAGE_TAG="$2"
cd "$ROOT_DIR"
[[ -r "$ENV_FILE" ]] || { echo "Cannot read server env file." >&2; exit 1; }
command -v flock >/dev/null || { echo "Requires Ubuntu flock (util-linux)." >&2; exit 1; }
exec 9>/var/lock/travis-recovery-deploy.lock
flock -n 9 || { echo "Another deployment/backup is running." >&2; exit 1; }
compose=(docker compose --env-file "$ENV_FILE" -f "$ROOT_DIR/compose.production.yaml")
"${compose[@]}" config --quiet
# Validate the password before Compose interpolates it into a database URL.
"${compose[@]}" config --format json | python3 -c '
import json, re, sys
c = json.load(sys.stdin)
p = c["services"]["db"]["environment"]["POSTGRES_PASSWORD"]
if not re.fullmatch(r"[A-Za-z0-9_-]{24,}", p):
    sys.exit("POSTGRES_PASSWORD must be at least 24 URL-safe letters/numbers/_/-.")
e = c["services"]["app"]["environment"]
if str(e["SECRET_KEY"]).startswith("replace-") or str(e["SETTINGS_ENCRYPTION_KEY"]).startswith("replace-"):
    sys.exit("Replace placeholder secrets before deploying.")
'
echo "Building release ${APP_IMAGE_TAG}"
# Never rebuild a tag that still identifies a previous release/rollback image.
if docker image inspect "travis-recovery:${APP_IMAGE_TAG}" >/dev/null 2>&1; then
  echo "Release image already exists; choose a new release tag." >&2
  exit 1
fi
"${compose[@]}" build app
"${compose[@]}" up -d --wait --wait-timeout 120 db
"${compose[@]}" run --rm --no-deps -T app python manage.py check --deploy
# Preserve an independent, consistent local pre-release backup with writes stopped.
# Copy/encrypt this backup off-server separately; local backups alone are insufficient.
umask 077
BACKUP_DIR="/var/backups/travis-recovery/$(date -u +%Y%m%dT%H%M%SZ)-${APP_IMAGE_TAG}-$$"
mkdir -p "$BACKUP_DIR"
was_running=0
if [[ -n "$("${compose[@]}" ps --status running -q app)" ]]; then
  was_running=1
fi
recover() {
  if [[ "$was_running" == 1 ]]; then
    # Start the existing container, not an unverified new image, after a failed step.
    "${compose[@]}" start app || true
  fi
}
trap recover EXIT
"${compose[@]}" stop app
"${compose[@]}" exec -T db pg_dump -U travis -d travis_recovery -Fc > "$BACKUP_DIR/database.dump"
"${compose[@]}" run --rm --no-deps -T app python -c \
  'import sys, tarfile; t=tarfile.open(fileobj=sys.stdout.buffer, mode="w|gz"); t.add("/data/media", arcname="media"); t.close()' \
  > "$BACKUP_DIR/media.tar.gz"
"${compose[@]}" exec -T db pg_restore --list < "$BACKUP_DIR/database.dump" >/dev/null
tar -tzf "$BACKUP_DIR/media.tar.gz" >/dev/null
cp "$ENV_FILE" "$BACKUP_DIR/app.env"
# This checks archive readability, not a full restore. Keep a tested restore drill.
# GCS users must also maintain independent bucket backups; this archive covers local media only.
echo "Pre-release backup: $BACKUP_DIR (contains secrets; copy securely off-server)"
"${compose[@]}" run --rm --no-deps -T app python manage.py migrate --noinput
# Schema may now have changed: do not auto-start old code after this point.
was_running=0
"${compose[@]}" up -d --no-deps --wait --wait-timeout 120 app
# Persist the selected tag so later Compose commands use the running release.
python3 - "$ENV_FILE" "$APP_IMAGE_TAG" <<'PYTHON'
import os, re, stat, sys, tempfile
from pathlib import Path
path = Path(sys.argv[1])
text = path.read_text()
line = "APP_IMAGE_TAG=" + sys.argv[2]
text, count = re.subn(r"(?m)^APP_IMAGE_TAG=.*$", line, text)
if not count:
    text = text.rstrip() + "\n" + line + "\n"
fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".app-env-")
try:
    with os.fdopen(fd, "w") as stream:
        stream.write(text)
    os.chmod(temporary, stat.S_IMODE(path.stat().st_mode))
    os.replace(temporary, path)
finally:
    if os.path.exists(temporary):
        os.unlink(temporary)
PYTHON
trap - EXIT
echo "Release ${APP_IMAGE_TAG} is healthy locally. Verify public HTTPS and authenticated workflows."
