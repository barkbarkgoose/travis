#!/usr/bin/env bash
# deploy.sh: build locally, rsync to the server, then back up, install, migrate and restart there.
# Template from vpshome/provision. Copy it to your project root as deploy.sh, edit the settings
# block (and the test/build commands), chmod 755. Needs the server set up by
# provision-django-vue.sh first. Guide: provision/django-vue.md in vpshome.
set -euo pipefail
cd "$(dirname "$0")"

# ---- settings
HOST=drop2          # ssh alias from ~/.ssh/config (required)
NAME=travis         # the --name given to provision-django-vue.sh (required)
BACKEND=backend     # local folder with manage.py; lands at app/<its basename> (= --backend-dir)
FRONTEND=frontend   # local Vue project; its build output is $FRONTEND/dist
EXTRA=()            # other local folders the backend imports, copied next to it under app/
[ -n "$HOST" ] && [ -n "$NAME" ] || { echo "deploy.sh: set HOST and NAME in its settings block first" >&2; exit 1; }
APP=/srv/$NAME
SERVER_BACKEND=$APP/app/$(basename "$BACKEND")

# 1. tests + frontend build (locally)
(cd "$BACKEND" && .venv/bin/python -m pytest -q)
(cd "$FRONTEND" && pnpm build)

# 2. copy code. Excludes keep secrets, local databases and server-side state out of the transfer,
#    and --delete leaves excluded paths on the server alone.
rsync -az --delete \
  --exclude='__pycache__/' --exclude='*.pyc' --exclude='.pytest_cache/' \
  --exclude='.env' --exclude='db.sqlite3*' --exclude='media/' \
  --exclude='staticfiles/' --exclude='tests/' --exclude='conftest.py' \
  --exclude='.venv/' --exclude='keychain.key' --exclude='keychain.json' \
  "$BACKEND" ${EXTRA[@]+"${EXTRA[@]}"} "$HOST:$APP/app/"
rsync -az --delete "$FRONTEND/dist/" "$HOST:$APP/frontend/"

# 3. on the server: back up first, install deps, migrate, restart
ssh -t "$HOST" "
  set -e
  umask 022
  sudo -u $NAME $APP/bin/backup-db
  $APP/venv/bin/pip install --no-cache-dir -q -r $SERVER_BACKEND/requirements.txt
  sudo -u $NAME $APP/bin/manage migrate --noinput
  $APP/bin/manage collectstatic --noinput
  sudo systemctl restart $NAME
"
echo 'Deployed.'
