# Deploying this app to Railway

This guide is specific to this repository and `travis.allbarker.com`. The repo is
connected to Railway, but the production service still needs to be configured and
verified. Read [`../SECURITY_AND_LEGAL.md`](../SECURITY_AND_LEGAL.md) before
putting real family records or photos on the service.

## Deployment shape

```text
Browser (https://travis.allbarker.com)
  → Railway HTTPS proxy
  → Django + Gunicorn
      ├── API and admin
      ├── WhiteNoise → Vue build included in the image
      ├── Railway PostgreSQL → records, metadata, audit history
      └── private Google Cloud Storage bucket → photo bytes
```

The frontend and API share one origin, so no CORS configuration is needed. The
photos are stored separately from the database, but the app serves them through
an authenticated Django endpoint. The GCS bucket must remain private.

## What the repository already supports

- The root `Dockerfile` builds Vue with the repository's pnpm version and runs
  Python 3.13, Django, and Gunicorn. `.dockerignore` excludes local secrets and
  data.
- `DJANGO_ENV=production` selects secure production settings. Railway's forwarded
  HTTPS scheme is trusted by default.
- The production frontend uses same-origin API URLs by default; Vite's local dev
  server still uses the local Django API.
- Django serves the built Vue app and its normal `/assets/...` paths. Do not set
  Vite's `base` to `/static/`.
- `DATABASE_URL` is parsed in `backend/config/settings/base.py`. PostgreSQL support
  is enabled by the `psycopg[binary]` dependency.
- Production settings support filesystem and private GCS media storage. The
  Railway Docker image selects GCS and refuses to start if its bucket, project,
  or credentials are missing; static files remain on WhiteNoise.
- `MEDIA_ROOT` remains configurable for filesystem storage (local development or
  a Railway Volume). It is not used by file fields while GCS is the active
  default storage.

## 1. Configure the Railway service

The app service should build from the repository root using the root `Dockerfile`.
In Railway, select the app service and confirm its **Settings** use the root as
its source/build context. The Dockerfile binds Gunicorn to Railway's `$PORT`.

In the app service's **Variables**, configure:

| Variable | Value |
|---|---|
| `DJANGO_ENV` | `production` (also the Dockerfile default) |
| `SECRET_KEY` | A unique random secret; keep it only in Railway Variables |
| `ALLOWED_HOSTS` | `travis.allbarker.com` plus the Railway hostname if you use it |
| `DATABASE_URL` | Reference the PostgreSQL service's `DATABASE_URL` |
| `MEDIA_STORAGE_BACKEND` | `gcs` (also the Railway Dockerfile default) |
| `GCS_PROJECT_ID` | Google Cloud project ID |
| `GCS_BUCKET_NAME` | Private GCS bucket name (not a URL) |
| `GCS_CREDENTIALS_JSON_B64` | Base64 service-account JSON; secret, never commit it |

For `DATABASE_URL`, use Railway's **Add Reference**/variable-reference picker to
select the PostgreSQL service's `DATABASE_URL`; do not copy a password-bearing
connection string into docs or source control. Railway's internal connection
reference is intended for service-to-service use in the same environment.

`GCS_PROJECT_ID` and `GCS_BUCKET_NAME` are identifiers, not credentials. GCS
credentials are secret. See [`google-cloud-storage.md`](google-cloud-storage.md)
for creating the private bucket, granting least-privilege access, and encoding the
service-account JSON for Railway. Setting `MEDIA_STORAGE_BACKEND=gcs` explicitly
in Railway Variables is recommended even though the Dockerfile already sets it.

Do not set `DEBUG=True`. `CORS_ALLOWED_ORIGINS` can remain empty for this
same-origin setup. Do not add `MEDIA_ROOT=/data/media` for the GCS deployment;
that setting is only for filesystem-backed media.

## 2. Create PostgreSQL and run migrations

Follow [`postgres.md`](postgres.md) to create Railway PostgreSQL, reference its
`DATABASE_URL`, and configure a one-time migration step.

The Dockerfile intentionally does **not** run migrations every time a web
container starts. Configure Railway's **Pre-deploy Command** to run:

```bash
python manage.py migrate --noinput
```

The Docker image's working directory is `/app/backend`, so `manage.py` is
available there. Migrations run once before the new app deployment rather than
concurrently in every web process. The Dockerfile runs `collectstatic` as the
container starts; this is for Django admin assets. The Vue build is already in
the image.

A new PostgreSQL service starts empty. Running `migrate` creates the schema; it
does not copy existing SQLite rows or files. If the SQLite database already has
records, back it up and plan a deliberate data migration before switching
`DATABASE_URL`. Photo bytes must also be copied to GCS under the same object names
stored in the database. Do not delete the SQLite volume or source media until
counts and retrieval have been checked.

## 3. Configure GCS media

This app stores original, display, and thumbnail photo files in Django
`FileField`s. With the GCS variables configured, those file bytes go to the
private bucket while the database stores their object names and metadata. The
existing photo API continues to check authorization and stream the file; it does
not expose public bucket URLs.

Complete the app and Google Cloud steps in
[`google-cloud-storage.md`](google-cloud-storage.md). There is no Railway media
Volume required when using GCS. The database still needs PostgreSQL persistence.

## 4. Backups and data protection

PostgreSQL and GCS are separate stores and need separate recovery plans:

- Enable/verify the Railway PostgreSQL backup or recovery option available on the
  selected plan. Check the retention window and restore procedure rather than
  assuming the database service is a backup.
- Keep an independent encrypted database export in a separate, private GCS
  backup bucket or another provider/account. Never store the only backup beside
  the live database.
- Back up/version photo objects independently. The bucket used by the app is
  private; do not apply automatic deletion rules while records must be retained.
- Test restoring both the database and photos before relying on the setup.

Backups reduce the amount of data that could be lost; they are not zero data loss
or high availability. Choose a backup interval that matches how much recent data
you could tolerate losing. Read `SECURITY_AND_LEGAL.md` before setting retention
or deletion policies.

## 5. Verify the deployment

- [ ] `bash scripts/docker-smoke-test.sh` passes before pushing Docker-related changes.
- [ ] Railway build uses the repository-root `Dockerfile` and service becomes healthy.
- [ ] Railway Variables include production host/secret and references to PostgreSQL and GCS.
- [ ] Railway pre-deploy logs show migrations completed against PostgreSQL.
- [ ] `https://travis.allbarker.com/` loads over HTTPS; direct refresh on a nested Vue route works.
- [ ] Browser API calls go to `https://travis.allbarker.com/api/...`, not localhost.
- [ ] `/admin/` works and has CSS.
- [ ] Upload a test image (including an iPhone HEIC); all variants appear in the GCS bucket.
- [ ] Authorized users can retrieve photos; unauthorized users and anonymous requests cannot.
- [ ] Restart/redeploy and verify database records and photos remain available.
- [ ] Create and restore-test encrypted backups of PostgreSQL and photo objects.
- [ ] Keep the old Google Sheet read-only as an archive; do not delete it.

## Related guides and files

- [`postgres.md`](postgres.md) — Railway PostgreSQL setup, variables, migrations, backups.
- [`google-cloud-storage.md`](google-cloud-storage.md) — private bucket setup and app storage configuration.
- [`docker-sanity-check.md`](docker-sanity-check.md) — local container smoke test.
- `backend/config/settings/base.py` — `DATABASE_URL`, `MEDIA_ROOT`, and app settings.
- `backend/config/settings/production.py` — GCS storage backend, WhiteNoise, HTTPS/security.
- `backend/apps/journal/views.py` — authenticated photo upload and retrieval.
- `docs/SECURITY_AND_LEGAL.md` — data preservation and access constraints.
