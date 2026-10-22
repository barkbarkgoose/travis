# Google Cloud Storage for this app's private photos

This walkthrough stores uploaded photo bytes in a **private Google Cloud Storage
(GCS) bucket**, while Django continues to store photo metadata and object names
in the database. The app's database still needs its own persistent home—GCS is
not a database.

This app keeps each photo as an original, a display copy, and a thumbnail. Its
existing API checks authorization and streams each file; this guide keeps that
behavior. Do **not** make the bucket public and do not replace the protected API
URLs with permanent public object URLs.

Read `../SECURITY_AND_LEGAL.md` before creating retention, deletion, or versioning
policies for real records.

## How the pieces fit together

```text
Browser → authenticated Django photo endpoint → private GCS object
                      │                         └── original/display/thumb bytes
                      └── database row stores object names and photo metadata
```

Django's `FileField`s currently use local filesystem storage by default. Django
storage backends let the same `photo.original.save(...)` and `field.open(...)`
code use GCS instead. The database stores a relative object name, such as
`journal/2026/10/123/display/<hash>-display.jpg`, not the image bytes.

## Part A: Google Cloud Console setup

Google's console wording may change; the usual navigation is described below.

### 1. Select or create a Google Cloud project

1. Open **Google Cloud Console** at `https://console.cloud.google.com/`.
2. Use the project selector in the top bar to select an existing project or
   choose **New Project**.
3. Make sure billing is enabled for the project. Cloud Storage usage may incur
   charges.
4. Note the project ID (not just the display name); the app configuration will
   use it.

### 2. Enable Cloud Storage

1. Open **APIs & Services** → **Library**.
2. Search for **Cloud Storage API**.
3. Open it and choose **Enable** if it is not already enabled.

### 3. Create a private bucket

1. Open **Cloud Storage** → **Buckets**.
2. Choose **Create**.
3. Choose a globally unique bucket name. Bucket names are public identifiers,
   so do not include family names, patient names, or other sensitive information.
4. Choose a location near the Railway service region, while considering any
   applicable data-location requirements.
5. Choose **Standard** storage for photos that users may read regularly. Other
   storage classes can have retrieval charges or minimum storage durations.
6. Enable **Uniform bucket-level access**.
7. Enforce **Public access prevention**. Do not grant `allUsers` or `allAuthenticatedUsers`
   access and do not set a public-read ACL.
8. Create the bucket.

Do not set a lifecycle rule that automatically deletes objects. Object versioning
can help recover overwritten/deleted objects but adds storage cost and is not a
backup by itself. Do not lock a retention policy until the record-retention
requirements and operational consequences are understood.

### 4. Create a narrowly scoped service account

The Django process needs an identity that can read/write objects in this bucket.

1. Open **IAM & Admin** → **Service Accounts**.
2. Choose **Create Service Account** and give it a descriptive name, for example
   `railway-photo-storage`.
3. Do not grant broad project Owner/Editor permissions.
4. Open the new bucket's **Permissions** tab (or **Permissions** → **Grant
   access**).
5. Add the service account's email and grant **Storage Object User** on this
   bucket only. This is the app's object read/write role; avoid a project-wide
   grant if bucket-level access is sufficient.

### 5. Create credentials for Railway

For a straightforward Railway setup, use a service-account JSON key stored only
as a Railway secret:

1. In **IAM & Admin** → **Service Accounts**, open the service account.
2. Open **Keys** → **Add Key** → **Create new key** → **JSON**.
3. Download the file once and keep it out of the repository, shared folders,
   screenshots, and build context. Do not commit it.
4. If the key is exposed, delete/revoke it in the same Keys page and create a
   replacement.

Service-account keys are long-lived credentials. Restrict the account to this
bucket, store the key as an encrypted Railway variable, and rotate it. If a
short-lived identity/federation integration is available for your Railway plan
and setup, prefer that over a downloaded key.

## Part B: app configuration (implemented)

### 1. Dependency and backend selection

`django-storages[google]` is now included in `backend/requirements.txt`. In
`backend/config/settings/production.py`, GCS becomes Django's default file
storage when `MEDIA_STORAGE_BACKEND=gcs`. It then requires `GCS_BUCKET_NAME`,
`GCS_PROJECT_ID`, and `GCS_CREDENTIALS_JSON_B64`. The Railway Dockerfile selects
GCS by default, so a missing or malformed configuration stops startup instead
of silently writing uploads to the ephemeral container disk. Other production
hosts retain filesystem storage unless they opt into GCS.

The GCS configuration changes only the `default` storage backend. Django static
files stay on WhiteNoise. Local development also stays on filesystem storage.

The production settings decode the base64 JSON credentials and pass them to
`storages.backends.gcloud.GoogleCloudStorage` with the configured bucket and
project ID. The backend uses `default_acl=None`; together with Uniform
bucket-level access and Public access prevention this keeps objects private.
No public ACL or public bucket URL is configured.

No model migration is needed just to switch the storage backend. `MEDIA_ROOT`
does not control uploads while GCS is active; it remains the filesystem-storage
path for local development or a Railway Volume setup.

### 2. Preserve the app's authorization flow

`backend/apps/journal/views.py` checks the authenticated user and organization,
then opens the `FileField` and streams it with `FileResponse`. Keep that check.
The serializer returns the Django photo endpoint URL, not a GCS object URL.

With the default-storage switch, `field.open("rb")` should read from GCS through
the storage backend. Test the complete upload-and-view path after wiring it up.
Do not make `MEDIA_URL` a public bucket URL. Do not issue long-lived signed URLs
without an explicit design review; a signed URL is a bearer link usable by
anyone who obtains it until it expires.

This proxy-through-Django design preserves the app's existing authorization
behavior, but photo bytes still flow through Railway. Signed URL delivery can be
a later performance optimization, with short expirations and authorization
performed by Django before issuing the URL.

### 3. Existing photos and database migration

Changing a `FileField` storage backend generally does not require a schema
migration: the database continues to store the relative object name. However,
existing file bytes must be copied to the bucket under the **same object names**
before the app switches to GCS. Otherwise existing rows point to objects that
aren't there.

If there are no production uploads yet, enable GCS before accepting real photos.
If local or production files already exist, plan a verified one-time copy (for
example, preserving each path with the Google Cloud CLI or a purpose-built
management command), compare file counts/checksums, and test retrieval before
switching traffic. Do not delete the source files until the copy and restore
checks pass.

## Part C: Railway configuration

1. Open the **Railway dashboard** → select the project → select the app service.
2. Open **Variables** → **Add Variable**.
3. Add the following runtime variables:

   | Variable | Value |
   |---|---|
   | `DJANGO_ENV` | `production` |
   | `DATABASE_URL` | Reference the Railway PostgreSQL service; see [`postgres.md`](postgres.md) |
   | `SECRET_KEY` | Keep the actual secret in Railway Variables |
   | `ALLOWED_HOSTS` | `travis.allbarker.com` plus the Railway hostname if used |
   | `MEDIA_STORAGE_BACKEND` | `gcs` (also the Dockerfile default) |
   | `GCS_PROJECT_ID` | The Google Cloud project ID |
   | `GCS_BUCKET_NAME` | The private bucket name (not a URL) |
   | `GCS_CREDENTIALS_JSON_B64` | Base64 encoding of the service-account JSON file |

4. To encode the downloaded JSON file on macOS, run locally (replace the path):

   ```bash
   python3 -c 'import base64,pathlib; print(base64.b64encode(pathlib.Path("service-account.json").read_bytes()).decode())'
   ```

   Paste the output into Railway Variables. Do not print it in a public terminal,
   commit it, or place it in a Docker build argument. If Railway's variable editor
   supports a protected multiline secret and the app is written to parse it, the
   raw JSON can be used instead; base64 only makes the value easier to transport,
   it is **not encryption**.

5. Save the variables and redeploy so the running container receives them. The
   current repository Dockerfile selects GCS storage, so configure these values
   before deploying that image.

The app needs a persistent database separately. The recommended Railway setup
uses PostgreSQL; see [`postgres.md`](postgres.md). GCS does not persist or back up
the database.

## Verify before real uploads

- [ ] Bucket has Uniform bucket-level access and Public access prevention enabled.
- [ ] No public principals or public object ACLs exist.
- [ ] Railway has the correct project ID, bucket name, and credentials secret.
- [ ] A test upload creates the original, display, and thumbnail objects in GCS.
- [ ] The app can read each variant through its authenticated photo endpoint.
- [ ] An unauthorized user cannot read photos, including by guessing an object name.
- [ ] The bucket itself does not expose a public object URL.
- [ ] Restart/redeploy the Railway service and verify photos still load.
- [ ] Verify database rows and object names match; perform a restore test.
- [ ] Back up database and GCS objects independently and retain them appropriately.

## Cost, retention, and operational notes

- GCS charges depend on stored bytes, request volume, region, storage class, and
  network egress. This app stores three variants for each uploaded photo.
- Standard storage is generally the straightforward choice for frequently
  viewed photos. Compare current pricing before selecting a region or class.
- Object versioning can protect against accidental overwrite/deletion but also
  retains extra bytes. It is not a substitute for an independent backup.
- Do not configure automatic object deletion for this app without reviewing
  `docs/SECURITY_AND_LEGAL.md` and the applicable preservation requirements.
- Keep the service account limited to the bucket and rotate credentials if they
  are exposed or no longer needed.

## Related app files

- `backend/config/settings/production.py` — current `STORAGES` configuration.
- `backend/config/settings/base.py` — database, `MEDIA_ROOT`, and environment settings.
- `backend/apps/journal/models.py` — three photo `FileField`s and storage names.
- `backend/apps/journal/views.py` — authorization and authenticated file streaming.
- `backend/apps/journal/serializers.py` — API returns the app's protected photo URLs.
- `docs/SECURITY_AND_LEGAL.md` — preservation/security constraints.
