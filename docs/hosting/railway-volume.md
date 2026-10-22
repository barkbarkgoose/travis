# Railway Volume storage for this app

This is an **alternative** for a small, single-replica deployment that chooses
SQLite and local filesystem media instead of the recommended PostgreSQL + GCS
setup. A Railway Volume is persistent disk attached to a service; it is not a
backup, and it is not an object-storage bucket. See [`railway.md`](railway.md)
for the recommended PostgreSQL + GCS architecture.

For this app the database **and** media must be persisted. Persisting only
`db.sqlite3` leaves photo files vulnerable to loss; persisting only `media/`
leaves database records behind. Read `../SECURITY_AND_LEGAL.md` before putting
real records or photos on the service.

## What will change

The app currently defaults to:

- SQLite at `backend/db.sqlite3` (from `DATABASE_URL=sqlite:///db.sqlite3`).
- Uploaded files at `backend/media` (`MEDIA_ROOT` is currently fixed in
  `backend/config/settings/base.py`).

Both paths are on the container's ordinary filesystem today. The plan below puts
both under the Railway mount `/data`:

```text
/data/db.sqlite3
/data/media/...
```

The `Photo` database rows contain the relative names of the original, display,
and thumbnail files. The bytes are separate files. The app already serves those
files through an authenticated view; do not add a public media URL or expose
`/data` to the internet.

## Before opening the Railway UI

The app already supports environment-configurable `MEDIA_ROOT` and
`DATABASE_URL`; no model change is needed to use the mounted paths. The root
Dockerfile also supports the filesystem media override needed for this
alternative. No code changes are required for the steps below.

### Ensure the container is ready

The repository has the root Dockerfile, Gunicorn dependency, production settings,
and same-origin frontend API fallback described in [`railway.md`](railway.md).
For SQLite, make sure only one service replica runs; do not run migrations
concurrently in multiple containers.

## Create and mount a volume in Railway

Railway's labels can shift slightly, but the flow is generally:

1. Open the **Railway dashboard** and select the project containing this app.
2. Select the Django/Docker service on the project canvas.
3. Open the service's **Settings** (or its **Volumes** section/tab).
4. Choose **Add Volume** / **New Volume**.
5. Set the mount path to exactly:

   ```text
   /data
   ```

6. Create/save the volume and redeploy if Railway prompts you. Confirm the
   volume is attached to the application service, not a database service.

The mount path is an absolute path inside the running container. Paths in
Railway Variables must match it exactly.

## Set Railway Variables

On the service, open **Variables** → **Add Variable** (or the equivalent
variables editor). Add:

| Name | Value |
|---|---|
| `DJANGO_ENV` | `production` |
| `SECRET_KEY` | A unique random secret; do not put it in Git or the Dockerfile |
| `ALLOWED_HOSTS` | `travis.allbarker.com` and the Railway hostname if you will use it |
| `DATABASE_URL` | `sqlite:////data/db.sqlite3` |
| `MEDIA_ROOT` | `/data/media` |
| `MEDIA_STORAGE_BACKEND` | `filesystem` |

The four slashes in `sqlite:////data/db.sqlite3` indicate an absolute path. The
existing settings use `django-environ` to parse `DATABASE_URL`. Keep
`TRUST_PROXY_SSL_HEADER` enabled (the production default); Railway's HTTPS proxy
sets the forwarded scheme.

If the keychain is initialized and has values for settings such as `SECRET_KEY`
or `ALLOWED_HOSTS`, its values override environment fallbacks. For a Railway
deployment, prefer Railway Variables and do not copy a local `keychain.json` or
`keychain.key` into the image.

## Migrate and start the service

The repository-root Dockerfile starts in `/app/backend`, runs `collectstatic`,
then starts Gunicorn. It intentionally does not run migrations at startup; the
recommended PostgreSQL setup uses a Railway pre-deploy command. With SQLite,
run `python manage.py migrate --noinput` once in the deployed app container after
the volume is attached, before relying on the app. Do not run this concurrently
in multiple containers against the same SQLite file.

Set `DJANGO_ENV`, `SECRET_KEY`, `ALLOWED_HOSTS`, `DATABASE_URL`, `MEDIA_ROOT`,
and `MEDIA_STORAGE_BACKEND=filesystem` in Railway before starting. The Railway
Dockerfile defaults media storage to GCS and requires GCS variables; override it
to `filesystem` for this volume-backed alternative, and do not set GCS variables.

`collectstatic` prepares Django admin assets; the Vue build is served from the
image and is not stored in `/data`.

## Verify it persists

After the app is healthy:

1. Submit a test entry with a photo; confirm all three variants can be viewed
   through the app by an authorized user.
2. Confirm an unauthorized account cannot retrieve that photo. Its object/file
   must not be reachable through a public URL.
3. Redeploy or restart the service.
4. Confirm the database record and photo still load.
5. Confirm the app is still running only one replica.

Test with non-sensitive data first. A successful upload before a restart does not
prove persistence; the post-restart check does.

## Backups and limits

- A volume is persistent storage, **not a backup**. Arrange independent,
  encrypted off-Railway backups of both the SQLite database and `/data/media`.
- SQLite is appropriate only while the app remains a modest single-instance
  service. Do not scale this service horizontally with one shared SQLite file.
- The app stores the original and two derivatives. Budget storage for all three,
  and watch Railway usage/quota.
- SQLite uses WAL mode in production. Do not make an ad hoc copy of only
  `db.sqlite3` while it is live and assume it is consistent; use a SQLite-aware
  backup or a quiesced/verified backup procedure, and test restoring it.
- Do not add automatic deletion or retention rules without checking the record
  preservation requirements in `SECURITY_AND_LEGAL.md`.

## When to prefer GCS instead

Choose Google Cloud Storage if you want media storage separated from the Railway
container, expect more media volume, or want the object-storage workflow. GCS
does **not** persist this app's SQLite database; the database still needs a
Railway Volume or a managed database. See [`google-cloud-storage.md`](google-cloud-storage.md).
