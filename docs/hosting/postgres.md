# Railway PostgreSQL for this app

This guide connects the app's existing Django `DATABASE_URL` support to a
Railway-managed PostgreSQL service. PostgreSQL will hold journal entries,
accounts, bookings, audit history, and photo metadata. It does **not** hold photo
bytes; those go to the private GCS bucket configured in
[`google-cloud-storage.md`](google-cloud-storage.md).

Read [`../SECURITY_AND_LEGAL.md`](../SECURITY_AND_LEGAL.md) before using real
records. PostgreSQL improves the managed database story, but it does not remove
the need for independent backups and a tested restore.

## What is already implemented

- `backend/config/settings/base.py` parses `DATABASE_URL` with `django-environ`.
- `psycopg[binary]` is in `backend/requirements.txt` as Django's PostgreSQL driver.
- Production settings add SQLite WAL behavior only when the configured database
  is SQLite. PostgreSQL is selected automatically from its `DATABASE_URL`.
- The Dockerfile no longer runs migrations during every web-container startup;
  Railway's pre-deploy command runs them once.

No database-specific settings rewrite is needed. `DATABASE_URL` overrides the
SQLite default in `base.py`.

## Create the Railway PostgreSQL service

1. Open the **Railway dashboard** and select the project and environment where
   the app service is deployed (for example, **Production**).
2. On the project canvas, choose **+ New** → **Database** → **Add PostgreSQL**.
3. If Railway asks for a region, choose the same region as the app service where
   possible.
4. Wait for the PostgreSQL service to finish provisioning and show as healthy.
5. Select the PostgreSQL service and find its `DATABASE_URL` variable in its
   **Variables** view. Keep the connection private; it contains credentials.

## Reference its URL from the app service

1. Select the Django app service on the project canvas.
2. Open **Variables**.
3. Remove/replace any SQLite `DATABASE_URL` configured directly on the app.
4. Choose **Add Reference** (or the Railway variable-reference control), select
   the PostgreSQL service, then select its `DATABASE_URL` variable.
5. Confirm the app service now has a `DATABASE_URL` reference to that database
   in the same Railway environment. Prefer the internal reference rather than
   copying the credential-bearing URL into source or documentation.

Keep these app variables too:

```text
DJANGO_ENV=production
SECRET_KEY=<unique secret stored in Railway>
ALLOWED_HOSTS=travis.allbarker.com,<Railway hostname if used>
```

If you later create a staging environment, give it a separate PostgreSQL service
and reference. Never point staging at production data.

## Run Django migrations once per deploy

The repo-root Dockerfile's working directory is `/app/backend`, and it starts
Gunicorn without applying schema changes. In the app service's **Settings** →
**Deploy** (the exact section label may vary), set **Pre-deploy Command** to:

```bash
python manage.py migrate --noinput
```

Railway runs this against the deployment environment before starting the new web
container. Confirm the pre-deploy logs show migrations applied successfully. The
container then runs `collectstatic` and starts Gunicorn.

Do not also add `migrate` to a per-worker startup command. A single pre-deploy
step avoids concurrent migration attempts when the web service has multiple
replicas. If the chosen Railway plan does not offer pre-deploy commands, use a
single controlled migration command before routing traffic to the new build.

## New database versus existing SQLite data

For a new/empty app, create PostgreSQL and run migrations. Migrations create the
schema; no rows are copied from SQLite.

If SQLite already contains records:

1. Stop accepting writes during the cutover and make a verified backup of the
   SQLite database and all media files.
2. Plan a data transfer from SQLite to PostgreSQL; changing `DATABASE_URL` does
   not transfer data. Include users, organizations, journal rows, bookings,
   audit events, and photo metadata, and validate counts/references.
3. Copy the photo objects into GCS using the same object names referenced by the
   `FileField`s. Database fixtures do not contain the photo bytes.
4. Test the destination, access controls, and photo retrieval before sending
   users to it. Preserve the original SQLite backup until restore testing and
   retention review are complete.

Do not use a simple `dumpdata`/`loaddata` run as the only migration plan for
important records without testing ordering, custom user relations, audit data,
and file references on a copy first.

## Backups: a minimum plan

1. In the Railway PostgreSQL service, inspect the available **Backups** or
   recovery options for the selected plan. Record its schedule, retention, and
   restore steps. Do not assume those settings without checking them.
2. Add an independent encrypted export to storage outside the live database
   service—for example, a separate private GCS backup bucket or a separate
   Google Cloud project/account. Restrict access separately from the app's media
   bucket.
3. Back up GCS photo objects separately from PostgreSQL. A database dump alone
   contains only their object names/metadata.
4. Set the backup frequency based on how much recent data can be lost; nightly
   backups can still lose a day's writes.
5. Perform a restore drill: restore a database copy, restore/verify photo
   objects, and confirm a record can retrieve its photo through the app's
   authenticated endpoint.

Backups reduce the impact of data loss; they do not guarantee zero loss or
continuous availability. Do not apply auto-delete policies to records or backup
objects before checking preservation requirements.

## Verify the switch

- [ ] Docker build/smoke test passes: `bash scripts/docker-smoke-test.sh`.
- [ ] Railway app service references the PostgreSQL service's `DATABASE_URL`.
- [ ] Railway pre-deploy logs show successful migrations.
- [ ] Runtime logs show Gunicorn starts and no database connection/driver errors.
- [ ] Create a test account/entry and verify it persists after a service redeploy.
- [ ] Photo upload and retrieval work after GCS is configured.
- [ ] A backup exists outside the live database service and has been restore-tested.

## Troubleshooting

| Symptom | Check |
|---|---|
| `No module named psycopg` | Confirm the updated image installed `psycopg[binary]`; rebuild and redeploy. |
| Database connection refused | Confirm PostgreSQL service is healthy, in the same Railway environment, and the app uses the internal `DATABASE_URL` reference. |
| App still creates SQLite data | Check whether an app-level `DATABASE_URL` overrides the Railway reference; inspect `settings.DATABASES` in the running environment without printing credentials. |
| Migrations run against an empty/wrong DB | Verify pre-deploy uses the app environment's PostgreSQL variable reference, not a staging or stale URL. |
| Records exist but photos are missing | Database migration does not move media; copy objects to GCS while preserving their relative names. |

Related: [`railway.md`](railway.md), [`google-cloud-storage.md`](google-cloud-storage.md),
and [`docker-sanity-check.md`](docker-sanity-check.md).
