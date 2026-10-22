# DigitalOcean Ubuntu VPS hosting plan

Prepared October 21, 2026, from the current local working tree. This is a plan;
no Droplet, DNS record, firewall, database, or application configuration has been
changed. Companion: [Ubuntu administration commands](ubuntu-admin.md).

## 1. What we are deploying

The app is Django + Django REST Framework with a Vue 3/TypeScript frontend.
The root `Dockerfile` already builds Vue with Node 24/pnpm and runs Django on
Python 3.13 with Gunicorn. Production Django serves the built frontend and static
assets through WhiteNoise. There is no need to run Vite or a separate Node server
in production.

Existing deployment material targets Railway and cPanel. A Droplet gives us the
Linux machine, but we must supply HTTPS, process supervision, durable storage,
updates, monitoring, and recovery. `deploy.sh` currently restarts cPanel Passenger
by touching `backend/tmp/restart.txt`; it is **not** a VPS deployment script.

The inspected checkout has uncommitted deployment changes. Review and preserve
those before choosing the release to deploy. Git commit IDs only identify a
reproducible release after its source files have been committed.

## 2. Proposed architecture

Use one Ubuntu LTS Droplet, Docker Compose for the app, and Caddy installed as a
host systemd service. Caddy handles public HTTPS and forwards to a localhost-only
Docker port. This reuses the existing image and keeps certificate administration
small. [Caddy proxy documentation](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)
explains its forwarded headers.

```text
Browser → DNS → Droplet public IP
                    │
             TCP 80/443 → Caddy (host service, HTTPS)
                              │
                     127.0.0.1:8000
                              │
                     Docker app / Gunicorn
                       ├── Django API + admin
                       ├── WhiteNoise + Vue build
                       ├── PostgreSQL → records and file metadata
                       └── private media → photo bytes
```

This is one server, so maintenance or server failure can interrupt service.
Compose restart policies help recover a stopped process, but do not provide
multiple-server availability. A container marked unhealthy also needs monitoring
or recovery logic; a health check alone does not restart it.

### Database and media decisions

Proposed starting point: PostgreSQL in Compose with a persistent volume, and
filesystem media on a separate persistent mount. This keeps the initial setup
on one provider and works with existing settings. We take responsibility for
database updates and independent backups.

Alternatives:

| Choice | Tradeoff / project implication |
|---|---|
| DigitalOcean Managed PostgreSQL | Less database maintenance, additional cost. Use its private/VPC endpoint, trusted-source restrictions, required TLS settings, and verified restore options. |
| Existing private GCS bucket | Already supported; can keep it while moving the app to DigitalOcean. Follow [the GCS guide](google-cloud-storage.md). |
| SQLite | Supported for a small workload, but needs its own backup/concurrency plan. PostgreSQL is the proposed production default. |
| DigitalOcean Spaces | Would require an S3-compatible storage backend/configuration and private-media tests; current settings select only `filesystem` or `gcs`. Not a drop-in GCS variable change. |

Do not assume Railway-private database hostnames are reachable from the VPS.
Decide whether existing records/photos must move before provisioning an empty DB.

## 3. Work to add to this repository

These are proposed files/changes, **not files already implemented by this plan**.

| Proposed artifact | Purpose / acceptance criteria |
|---|---|
| `compose.production.yaml` | App and PostgreSQL; root image build context; fixed release tags; persistent DB/media; DB readiness check; app restart policy; bounded logs. Publish only `127.0.0.1:8000:8000` for the app and no database port. |
| `deploy/digitalocean/Caddyfile` | Real hostname → `127.0.0.1:8000`; HTTPS; upload body limit large enough for a 25 MiB photo plus multipart overhead; no public file-server route for media. |
| `deploy/digitalocean/app.env.example` | Non-secret template documenting all required runtime variables and storage choice. Real file lives outside the checkout. |
| `scripts/deploy-vps.sh` | Fail on errors; select/build release; verify backup; run production checks and migrations once; replace app; verify readiness; retain prior image. Never delete persistent volumes. |
| Backup job + restore instructions | Consistent PostgreSQL export, media backup, encrypted off-server copies, retention, failure alerts, and restore drill. Use a systemd timer or cron with overlap protection. |
| Health/readiness endpoint | Add an explicit endpoint outside the SPA catch-all. Return simple status without sensitive details; readiness should check DB connectivity with a timeout. |
| Docker runtime hardening | Plan a non-root app user and writable mount ownership, retain writable static/temp paths, enable Gunicorn stdout/stderr/access logs with sensitive URL handling, pin tested dependencies/images. |
| Docs entry points | Link this guide from `README_2.md`; update `nextsteps.md` if DigitalOcean becomes the chosen target. Retain other hosting guides as alternatives. |

No Redis, Celery, Kubernetes, or extra worker service is required by the inspected
runtime configuration. Add them only when a feature needs them.

### Environment contract specific to this app

| Setting | VPS value / behavior |
|---|---|
| `DJANGO_ENV` | `production`; otherwise settings default to local. |
| `DEBUG` | `False`; production settings also force it off. |
| `SECRET_KEY` | Stable strong secret, preserved during migration if existing encrypted settings depend on it. |
| `ALLOWED_HOSTS` | `travis.allbarker.com` if that remains the chosen domain; no scheme and no wildcard. Production startup rejects missing hosts. |
| `DATABASE_URL` | PostgreSQL connection string using Compose service name (e.g. `db`), or managed DB endpoint. `localhost` inside the app container is the app itself. URL-encode password characters. |
| `MEDIA_STORAGE_BACKEND` | Explicitly `filesystem` for local disk, or `gcs` with the existing GCS variables. **The Dockerfile currently defaults to GCS**, so filesystem deployment must override it. |
| `MEDIA_ROOT` | `/data/media` for filesystem mode, mounted persistently. Omit GCS variables in this mode: production settings reject the mismatch. |
| `PORT` | `8000` inside the container. The host mapping binds only to loopback. |
| `TRUST_PROXY_SSL_HEADER` | `True` behind the proposed Caddy proxy. Keep Gunicorn inaccessible publicly so clients cannot bypass that trust boundary. |
| `SECURE_SSL_REDIRECT` | `True` in production. Caddy supplies `X-Forwarded-Proto` for HTTPS requests. |
| `NUM_PROXIES` | `1` for this single-proxy architecture, so DRF throttling sees the intended client IP. Revisit if adding a CDN/proxy. |
| `CORS_ALLOWED_ORIGINS` | Empty for same-origin frontend/API. Do not enable wildcard CORS. |
| `SETTINGS_ENCRYPTION_KEY` | Stable Fernet key for a new deployment. For existing encrypted data, preserve the effective previous key; changing it can make stored secrets unreadable. |
| `SECURE_HSTS_SECONDS` | Keep the current short initial value while verifying HTTPS; increase deliberately after validation. |

Some settings (`SECRET_KEY`, `DATABASE_URL`, hosts, CORS) prefer the app's encrypted
keychain over environment variables. `.dockerignore` excludes the local keychain
and `.env` files, so they do not automatically travel with the image. Prefer an
explicit runtime env file for a new VPS; if moving a keychain, mount it privately
and deliberately using `KEYCHAIN_JSON_PATH` / `KEYCHAIN_KEY_PATH`, and account for
its precedence. Back up its decryption key separately and securely.

Compose's `.env` is primarily an interpolation source; it does not automatically
inject all values into the app. Declare `env_file`/`environment` explicitly.
Never place secrets in `VITE_*`: those values are compiled into browser JavaScript.
The current production frontend defaults to same-origin requests; leave its local
`VITE_API_URL=http://localhost:8800` override out of the production build.

Private photos must continue through authenticated Django views. Do not add a
Caddy `/media` alias or make the media bucket public. The app's existing
`MEDIA_ROOT` intentionally has no public URL mapping.

## 4. Provision and prepare Ubuntu

1. Confirm the domain, current DNS provider, existing data location, budget, and
   acceptable outage/data-loss windows. Confirm whether a Droplet already exists.
2. Choose a supported Ubuntu LTS image. Ubuntu 24.04 LTS is a conservative candidate;
   verify the image and Docker support when provisioning. Prefer x86_64 initially
   unless deliberately building/testing ARM images.
3. For initial sizing, consider 2 vCPU / 4 GiB RAM as a planning estimate for app +
   DB and occasional builds, then measure. This is not a capacity guarantee.
   Building images in CI and pulling them reduces Droplet memory/CPU requirements.
4. Choose a region near users, enable monitoring and backups, and record the VPC,
   Droplet identifier, IPs, OS version, and billing alerts. Include backups, storage,
   outbound traffic, domain, and any managed DB in the cost estimate. Follow
   [DigitalOcean's setup guide](https://docs.digitalocean.com/products/droplets/getting-started/recommended-droplet-setup/).
5. Add your SSH **public** key at creation; keep the private key on your computer.
   Verify the server fingerprint through a trusted provider console before accepting
   first contact. Create a non-root sudo administrator and verify a second SSH session.
6. Apply package/security updates; check whether a reboot is required. Install Docker
   Engine and the Compose plugin following the [official Ubuntu instructions](https://docs.docker.com/engine/install/ubuntu/).
   Install Caddy using its official distribution instructions. Enable Docker and
   Caddy at boot. Docker-group membership grants root-equivalent control; otherwise
   run Docker through sudo.
7. Harden SSH only after key login and console recovery access work. Validate syntax
   with `sudo sshd -t`, inspect `sudo sshd -T`, then reload `ssh`. Account for Ubuntu
   cloud-init snippets; merely appending a setting may not override an earlier one.
   Keep the original session open until a new login succeeds.
8. Review [Ubuntu automatic security updates](https://ubuntu.com/server/docs/how-to/software/automatic-updates/).
   Schedule reboots and remember OS updates do not rebuild Python/Node containers.

### Network exposure

| Inbound port | Who should reach it? |
|---|---|
| TCP 22 | Your admin IP/CIDR or trusted VPN. Plan how to update the rule when your IP changes. |
| TCP 80 | Public, for HTTP → HTTPS and certificate validation. |
| TCP 443 | Public HTTPS. |
| TCP 8000 | Host loopback only; no cloud firewall allow rule. |
| TCP 5432 | Internal Compose network only; no public mapping/rule. Managed DB uses restricted private access. |

Apply rules in the DigitalOcean Cloud Firewall and host UFW for IPv4 and, if used,
IPv6. Allow the actual SSH port/source **before** enabling/changing firewalls.
Initially retain outbound connectivity for DNS, package repositories, certificate
issuance, backups, and any external media service. Restrict outbound later only
with the dependencies mapped.

Docker-published ports can bypass UFW rules. This is why the explicit loopback app
mapping and no DB port mapping matter; inspect Docker configuration and verify
from another machine. See [Docker's firewall warning](https://docs.docker.com/engine/install/ubuntu/).

## 5. Server files and DNS

Suggested layout (create ownership/permissions deliberately):

```text
/opt/travis-recovery/                  reviewed release checkout
/etc/travis-recovery/app.env           runtime secrets, mode 0600
/etc/caddy/Caddyfile                   host proxy configuration
/srv/travis-recovery/media/            durable private uploads
Docker named volume                   PostgreSQL data
```

The app process needs write access to media and temporary upload storage; a
non-root container must have matching ownership. Use a version-appropriate
PostgreSQL data-volume mount path for the selected image. Avoid mounting over
`/app/backend` or the built frontend: that would hide application files.

Create an A record for the chosen domain pointing at the Droplet IPv4. Add AAAA
only if IPv6 works end to end. Check both; a stale AAAA can cause intermittent
failures even when IPv4 is correct. The domain can keep its current DNS provider.

Conceptual Caddy configuration (to become a reviewed deployment file):

```caddyfile
travis.allbarker.com {
    reverse_proxy 127.0.0.1:8000
}
```

Configure DNS/reachability before expecting a public certificate. Validate and
reload Caddy; verify automatic issuance and renewal rather than adding a second
certificate manager. Never solve a certificate failure by permanently disabling
Django's HTTPS settings.

## 6. First deployment and later releases

Implement the proposed Compose file and deploy script before using this sequence.
All example Compose commands assume repository root, service names `app`/`db`,
and `compose.production.yaml`; these do not exist yet.

1. Review local changes, commit the intended release, and build a unique image tag.
   Keep Python/Node dependency versions reproducible. Build for the Droplet's CPU
   architecture; do not assume a locally built Apple Silicon image fits x86_64.
2. Put runtime secrets on the server and confirm the deployment process can read
   them without making them world-readable. Avoid printing resolved Compose config
   or environment dumps into logs/support messages.
3. Start PostgreSQL and wait for readiness. Confirm the app connects to the intended
   database before running migrations.
4. Before an update or data import, take and verify recoverable DB/media backups.
   For a migration from another host, stop writes, export/import data, preserve photo
   object names and encryption keys, validate counts and retrieval, then cut over.
   Changing `DATABASE_URL` does not copy records; DB exports do not contain photos.
5. Run production checks and migrations once using the **new release image**:

   ```bash
   sudo docker compose -f compose.production.yaml run --rm app python manage.py check --deploy
   sudo docker compose -f compose.production.yaml run --rm app python manage.py migrate --noinput
   sudo docker compose -f compose.production.yaml up -d app
   ```

   These commands assume the new image has already been built/pulled and selected
   by Compose. Review deployment-check warnings rather than ignoring them. The image
   runs `collectstatic` at app startup, but intentionally does **not** run migrations.
6. Configure Caddy, verify HTTP redirects and HTTPS, and test the checks below.
   Later releases repeat the backup/check/migrate/replace/verify sequence. A single
   app container may briefly interrupt service during replacement.
7. Keep the prior image and release configuration. An application rollback is safe
   only if the database schema remains compatible. Do not blindly reverse migrations;
   a DB restore may lose post-backup writes and needs a coordinated recovery plan.

## 7. Backups, monitoring, and routine operations

Back up PostgreSQL with a consistent logical export (or a documented database-aware
backup system), media including original/display/thumbnail files, and the required
secrets/keychain keys. Do not copy live PostgreSQL data files as a casual file backup.
For SQLite, use its backup API or stop writes; a plain copy of only the main file
can miss active WAL data.

Send encrypted backups off the Droplet with separate credentials. Droplet backups
are another recovery layer, not proof that a database/media pair can be restored
consistently. For a consistent export/media set, stop uploads/writes or implement a
coordinated backup process. Choose and record retention and acceptable data loss:
nightly backups can lose up to a day's new records.

Before launch, restore into an isolated environment and verify users, entries,
audit history, bookings, photo retrieval, and encrypted settings. Record the time
required. A backup job must alert on failure and excessive backup age, not just
create local files.

Monitor external HTTPS availability, CPU/RAM, disk bytes and inodes, DB connections,
container restarts, certificate problems, and backup freshness. Set log size limits;
keep tokens, invite links, credentials, and private record content out of logs.
Review alerts weekly and patch images/dependencies regularly. The existing
[security document](../SECURITY_AND_LEGAL.md) remains relevant to this app's data.

## 8. Launch acceptance checklist

- [ ] Domain, Droplet OS/architecture, storage choices, budget, and data migration confirmed.
- [ ] SSH key login and console recovery verified; only intended inbound ports reachable.
- [ ] Explicit production env, stable encryption keys, and persistent media/DB verified.
- [ ] Existing Docker smoke check passes on a development machine: `bash scripts/docker-smoke-test.sh`.
- [ ] VPS Compose/PostgreSQL integration and production checks pass; migrations applied once.
- [ ] HTTPS and redirect behavior work; no mixed content; admin CSS and Vue deep-link refresh work.
- [ ] A real readiness endpoint is used: the current SPA fallback can return HTML/200 for arbitrary paths, so `/health` is not a valid check today.
- [ ] Login, journal, booking, and photo upload/retrieval work; anonymous photo requests are denied.
- [ ] Records/photos survive app replacement and a planned Droplet reboot; Docker/Caddy start automatically.
- [ ] Off-server backup restore and prior-image rollback procedure tested.
- [ ] Monitoring, update schedule, backup owner, and recovery instructions recorded.

The local smoke script uses SQLite and HTTP with disposable data. A pass does not
prove real PostgreSQL, Caddy/TLS, cloud firewall, or backup behavior. This planning
change has not run a deployment or validated the server.
