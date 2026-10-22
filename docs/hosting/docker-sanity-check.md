# Check the Docker deployment before pushing

Use this as a quick pre-push check when changing the Dockerfile, Python
dependencies, frontend build, Django settings, migrations, or storage paths. It
builds and boots the same root Docker image Railway will use, but with disposable
local storage and a generated test secret. It does not connect to Railway or
touch real data.

## One-command check

From the repository root, with Docker Desktop/the Docker daemon running:

```bash
bash scripts/docker-smoke-test.sh
```

The script will:

1. Build the repository-root `Dockerfile` (including the Vue production build).
2. Start a temporary container with production Django settings, a generated
   throwaway secret, SQLite, and a disposable Docker volume mounted at `/data`.
   It explicitly selects filesystem media storage so no real GCS credentials or
   cloud resources are needed for this local check.
3. Run the Railway-style pre-deploy migration command, check Django's system
   configuration, and confirm the SPA page and built assets return HTTP 200.
4. Write temporary markers to the SQLite database and configured media path,
   restart the container, and verify both markers remain.
5. Remove the temporary container, volume, and image when finished.

The test uses HTTP locally, so it sets `SECURE_SSL_REDIRECT=0` only inside this
throwaway container. Do not copy that override to Railway; Railway should use
the production HTTPS redirect.

If local port `18080` is occupied, choose another port:

```bash
DOCKER_SMOKE_PORT=18081 bash scripts/docker-smoke-test.sh
```

## What a pass does and doesn't prove

A pass proves the image can build, Django starts with the container's production
settings, migrations and `collectstatic` run, the built frontend is in the path
Django expects, the app serves its assets, and the `/data` database/media paths
survive a container restart while the volume remains attached.

It does **not** prove Railway variables, DNS, HTTPS termination, Railway resource
limits, a real PostgreSQL connection, GCS credentials/network access, a production
backup/restore, or the app's full user workflow. Do a test upload and a Railway
restart/redeploy check after the Railway services are configured.

If the script fails, it prints the container logs before cleanup. Fix the first
build/startup error, then rerun the script. The script deliberately runs fresh
migrations on an empty database volume so migration failures are caught early.

## Manual equivalent

For troubleshooting, the core steps are (the migration runs separately, like
Railway's pre-deploy step):

```bash
docker build -t travis-recovery:check .
docker run --rm --name travis-recovery-check -p 127.0.0.1:18080:8000 \
  -e DJANGO_ENV=production \
  -e MEDIA_STORAGE_BACKEND=filesystem \
  -e SECRET_KEY=throwaway-local-only \
  -e ALLOWED_HOSTS=127.0.0.1,localhost \
  -e DATABASE_URL=sqlite:////data/db.sqlite3 \
  -e MEDIA_ROOT=/data/media \
  -e SECURE_SSL_REDIRECT=0 \
  -e PORT=8000 \
  -v travis-recovery-check:/data \
  travis-recovery:check
```

In another terminal, run `docker exec travis-recovery-check python manage.py migrate
--noinput`, then open `http://127.0.0.1:18080/`. The script is preferable
because it also checks asset requests and restart persistence, and cleans up
only its own temporary resources.

## Related files

- `Dockerfile` — the multi-stage build and Railway container start command.
- `.dockerignore` — files intentionally excluded from the build context.
- `docs/hosting/railway-volume.md` — Railway's persistent SQLite/media volume setup.
- `docs/hosting/google-cloud-storage.md` — private GCS photo storage setup.
