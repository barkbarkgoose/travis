Based on what we’ve set up, the main remaining work is Railway and Google Cloud configuration. The code changes are **local and uncommitted**; they haven’t been pushed to Railway.

1. **Decide whether there’s existing data to preserve.** A new PostgreSQL database starts empty. Changing `DATABASE_URL` does not copy SQLite records or photo files. If the current app has records or uploads you need, back them up and plan their transfer before cutover.

2. **Run the local checks, then commit and push the deployment changes.** The Docker smoke test and 140 backend tests passed in the previous checks. Once the changes are in the connected branch, Railway can build from the repo.

3. **Create a Railway PostgreSQL service** in the same project and environment as the app. In the app service’s Variables, reference the database service’s `DATABASE_URL`—don’t paste credentials into source or docs.

4. **Follow `docs/hosting/google-cloud-storage.md`** to create the private bucket and service account. Add these app-service variables in Railway:
   - `MEDIA_STORAGE_BACKEND=gcs`
   - `GCS_PROJECT_ID`
   - `GCS_BUCKET_NAME`
   - `GCS_CREDENTIALS_JSON_B64` (secret)
   
   Also set `SECRET_KEY` and `ALLOWED_HOSTS`. The Railway image selects GCS by default and won’t start without its configuration, so set these before deploying it.

5. **Configure the app service** to build from the repository root using the root `Dockerfile`. Set Railway’s pre-deploy command to:
   ```bash
   python manage.py migrate --noinput
   ```
   The container does not run migrations on every startup.

6. **Deploy and verify** the build, migration logs, HTTPS site, admin styling, and same-origin API requests. Upload a test image and confirm its variants are in the private bucket and can only be retrieved through the authenticated app endpoint.

7. **Confirm the custom domain and recovery plan.** Check that `travis.allbarker.com` is attached and serving HTTPS. Set up independent backups for both PostgreSQL and GCS, then test restoring them.

The walkthroughs are in `docs/hosting/railway.md`, `docs/hosting/postgres.md`, and `docs/hosting/google-cloud-storage.md`.
