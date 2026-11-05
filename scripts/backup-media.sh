#!/usr/bin/env bash
# backup-media.sh: daily snapshot of uploaded media (photos). The provision script's
# bin/backup-db only covers the database, so this covers MEDIA_ROOT when media is on disk.
# With MEDIA_STORAGE_BACKEND=gcs it does nothing (the bucket holds the photos).
#
# Install on the server next to backup-db, then add a line to /srv/NAME/cron.local and
# re-run provision-django-vue.sh so it lands in /etc/cron.d/NAME (runs as the app user):
#   scp scripts/backup-media.sh HOST:/srv/NAME/bin/backup-media
#   45 3 * * *  /srv/NAME/bin/backup-media 2>&1 | logger -t NAME-backup
#
# Each day is a full-looking folder in /srv/NAME/backups/media/YYYY-MM-DD, but files that
# didn't change are hard links to the previous day, so a snapshot only costs new photos.
set -euo pipefail
umask 077
cd /

ROOT=$(dirname "$(dirname "$(readlink -f "$0")")")   # /srv/NAME
ENV_FILE=$ROOT/.env
DEST=$ROOT/backups/media
KEEP=${KEEP:-14}   # snapshots to keep

env_value() { sed -n "s/^$1=//p" "$ENV_FILE" | tail -n 1 | sed "s/^[\"']//; s/[\"']\$//"; }

backend=$(env_value MEDIA_STORAGE_BACKEND)
if [ "${backend,,}" = gcs ]; then
  echo "media backup skipped: photos are in GCS bucket $(env_value GCS_BUCKET_NAME)"
  exit 0
fi

src=$(env_value MEDIA_ROOT)
[ -n "$src" ] || { echo "media backup FAILED: MEDIA_ROOT is not set in $ENV_FILE" >&2; exit 1; }
if [ ! -d "$src" ]; then echo "media backup skipped: no media folder yet at $src"; exit 0; fi

mkdir -p "$DEST"
stamp=$(date +%F)
latest=$(ls -1d "$DEST"/20??-??-?? 2>/dev/null | tail -n 1 || true)
tmp="$DEST/.tmp-$stamp"
trap 'rm -rf "$tmp"' EXIT
rm -rf "$tmp"

# --chmod keeps the backups private (provision --check expects 700 dirs, 600 files)
rsync -a --delete --chmod=D700,F600 ${latest:+--link-dest="$latest"} "$src/" "$tmp/"

want=$(find "$src" -type f | wc -l)
got=$(find "$tmp" -type f | wc -l)
if [ "$want" != "$got" ]; then
  echo "media backup FAILED: copied $got of $want files" >&2
  exit 1
fi

rm -rf "${DEST:?}/$stamp"
mv "$tmp" "$DEST/$stamp"

# keep the newest KEEP snapshots
ls -1d "$DEST"/20??-??-?? | head -n -"$KEEP" | while read -r d; do rm -rf "$d"; done

echo "media backup ok: $stamp ($got files)"
