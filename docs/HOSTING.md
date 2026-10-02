# Hosting: deploying to Namecheap shared hosting

A step-by-step guide for getting this app running on Namecheap's shared (cPanel)
hosting — the Stellar Plus/Business tiers, which include SSH and cPanel's "Setup
Python App" feature. Read `SECURITY_AND_LEGAL.md` alongside this.

> [!NOTE]
> The original plan for this app assumed a small VPS with nginx/Caddy in front of
> gunicorn. Shared hosting doesn't give you a reverse proxy, root access, or a
> process manager you control — it hands you one thing: a Python process cPanel
> starts and restarts for you (via Phusion Passenger), sitting behind Apache. This
> guide is written for that reality. Where it differs from a "real" deployment,
> the reasoning is called out so a future move to a VPS is a config change, not a
> rewrite.

## What "shared hosting, running as a Python app" actually means here

| On a VPS you'd have... | On shared hosting you get instead |
|---|---|
| nginx/Caddy in front of Django | Apache + Passenger. No custom reverse-proxy config. |
| gunicorn, a systemd unit | Passenger manages the process for you. Restart = touch a file. |
| Root, a firewall you configure, fail2ban | None of that. cPanel's own protections are what you get. |
| A dedicated frontend server, or nginx serving `dist/` | Django serves the built frontend itself (WhiteNoise) — this is the "put the frontend into the backend's static resources" part. |
| Postgres if you want it | Shared hosting plans mostly offer MySQL, not Postgres. SQLite (already the default) sidesteps the question entirely. |
| As much disk as you provisioned | A quota set by your plan. Check it — photos are what grows. |

The practical upshot: **one Python process serves everything** — the API, the
Django admin, and the built Vue app — from one origin. No CORS to configure, no
separate frontend host, no nginx config to write.

## Before you start

- [ ] Your domain's DNS points at the Namecheap hosting account (if the domain is
      also registered at Namecheap, this is usually already true; otherwise point
      an A/CNAME record at it).
- [ ] cPanel login for the hosting account.
- [ ] SSH access enabled on the plan, and you can `ssh` in (Namecheap's cPanel
      shows the SSH port and your username under "SSH Access").
- [ ] You know the disk quota on your plan. Set a reminder to check it monthly —
      see "Rough sizing" below.

## 1. SSH in and clone the repo

```bash
ssh yourusername@yourdomain.com -p <port from cPanel>
git clone <your repo URL> travis-recovery
cd travis-recovery
```

You now have `travis-recovery/backend` and `travis-recovery/frontend` side by
side — the rest of this guide assumes that layout, since `backend/config/settings/base.py`
finds the frontend build via `BASE_DIR.parent / "frontend" / "dist"`.

## 2. Create the Python app in cPanel

cPanel → **Setup Python App** → **Create Application**:

| Field | Value |
|---|---|
| Python version | The highest 3.x available, **3.10 or newer** (Django 5.2 requires it) |
| Application root | `travis-recovery/backend` — the folder with `manage.py` and the `passenger_wsgi.py` this repo already has |
| Application URL | Your domain (or a subdomain, e.g. `recovery.yourdomain.com`) |
| Application startup file | `passenger_wsgi.py` (should already be the default) |
| Application Entry point | `application` (should already be the default) |

Click **Create**. cPanel builds a dedicated virtualenv and shows you a command
like:

```bash
source /home/yourusername/virtualenv/travis-recovery/backend/3.11/bin/activate && cd /home/yourusername/travis-recovery/backend
```

**Copy that exact line down** — you'll run it at the start of every SSH session
where you manage this app. Everything below assumes that virtualenv is active.

> [!WARNING]
> Use the `pip` this activation gives you, not `uv` (which the rest of this
> project's tooling uses locally). cPanel's virtualenv is what Passenger actually
> runs against; installing with anything else won't reach it.

Still on the "Setup Python App" page, add these **Environment variables** (the
UI has a section for this — it persists across restarts, which is why this guide
prefers it over hardcoding values):

| Variable | Value |
|---|---|
| `DJANGO_ENV` | `production` |

(`passenger_wsgi.py` also defaults this to `production` on its own, so setting it
here is redundant but explicit — do it anyway in case you ever point Passenger at
a different startup file.)

## 3. Install dependencies and set up the keychain

```bash
# (the cPanel-provided activate command, then:)
pip install -r requirements.txt

python -m keychain init
python -m keychain set "SECRET_KEY=$(python -c 'import secrets; print(secrets.token_urlsafe(50))')"
python -m keychain set "ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com"
python -m keychain doctor
```

`keychain.key` is the master key — **back it up somewhere other than this
server** (a password manager, or print it) before you do anything else.
Without it, `keychain.json` can't be decrypted, ever.

Two more keychain values matter specifically because this is shared hosting —
see the "Why" column:

```bash
python -m keychain set "TRUST_PROXY_SSL_HEADER=0"
```

| Setting | Why it's different here |
|---|---|
| `TRUST_PROXY_SSL_HEADER=0` | On a VPS behind nginx, Django trusts the `X-Forwarded-Proto` header nginx sets. On cPanel, Apache usually terminates HTTPS itself with nothing in between — no header ever arrives, and if Django is still told to trust one, it wrongly concludes every request is insecure and redirect-loops. See the comment in `config/settings/production.py` for the mechanism. |

Everything else — `ENTRY_EDIT_WINDOW_HOURS`, `MAX_CONCURRENT_VISITORS`,
`JWT_ACCESS_TOKEN_LIFETIME_MINUTES`, `JWT_REFRESH_TOKEN_LIFETIME_DAYS` — has a
sane default and only needs setting if you want to change it. `CORS_ALLOWED_ORIGINS`
doesn't need setting at all: same-origin serving means there's no cross-origin
request to allow.

## 4. Build the frontend

**Recommended: build it on your own machine, then upload it.** Shared hosting
often has no Node.js at all, and even where it does, `vite build` + `vue-tsc`
can be slow or memory-constrained under a shared-hosting resource cap. Building
locally is faster and removes a whole category of "does this host even have
Node" uncertainty.

> [!WARNING]
> `VITE_API_URL` is baked into the build at build time, not read at runtime. The
> frontend defaults to `http://localhost:8800` when it's unset — fine for local
> dev, broken in production. Before building, create `frontend/.env.production`
> (git-ignored, so this stays local to your machine) with your real domain:
>
> ```
> VITE_API_URL=https://yourdomain.com
> ```
>
> Skip this and the deployed site will try to call your laptop from a stranger's
> browser.

On your own machine:

```bash
cd frontend
pnpm install
pnpm build
```

Then upload the result to the server, replacing whatever's there:

```bash
rsync -avz --delete dist/ yourusername@yourdomain.com:travis-recovery/frontend/dist/
```

**Alternative: build on the server.** If Node/pnpm are available via SSH (check
with `node -v`; enable pnpm with `corepack enable` if Node has Corepack, or
`npm install -g pnpm` otherwise), you can build in place instead:

```bash
cd travis-recovery/frontend
echo "VITE_API_URL=https://yourdomain.com" > .env.production
pnpm install
pnpm build
```

`./deploy.sh --build-frontend` (see step 6) does this same thing for you on
later deploys.

## 5. Migrate, collect static files, create the family admin

Back in the activated virtualenv, in `backend/`:

```bash
python manage.py migrate

python manage.py collectstatic --noinput

python manage.py bootstrap_family --org-name "Travis's Family" \
    --admin "Your Name <you@example.com>" --base-url https://yourdomain.com
```

`bootstrap_family` is safe to re-run — it reuses the organization if it exists,
and only sets a password on admins it actually creates. It prints a one-time
password for each new admin and the join link to hand out to visitors. Save the
password somewhere and change it after first login (there's no in-app "change
password" flow yet — reset it with `python manage.py changepassword <email>` if
you need to).

`collectstatic` only touches Django's own static files (the admin, DRF's
browsable API) — the frontend's JS/CSS bundle is served straight out of
`frontend/dist` by WhiteNoise and never goes through this step. See
`config/settings/production.py` and `config/spa.py` if you want the mechanism.

## 6. Restart and check it

Passenger restarts the app when a file at `tmp/restart.txt` (relative to the
application root) changes:

```bash
mkdir -p tmp && touch tmp/restart.txt
```

Visit `https://yourdomain.com`. You should get the login page. If you get a
Passenger error page or a 500 instead, see Troubleshooting below — and check
the app's error log, linked from the "Setup Python App" page in cPanel (or at
`~/travis-recovery/backend/stderr.log`, depending on cPanel version).

### For every deploy after this one

```bash
cd ~/travis-recovery
git pull
./deploy.sh              # backend deps, migrate, collectstatic, restart
# or, if you'd rather build the frontend on the server:
./deploy.sh --build-frontend
```

If you built the frontend locally instead, `rsync` it up (step 4) before or
after running `./deploy.sh` — order doesn't matter, since `deploy.sh` only
touches the backend and only restarts at the end.

## 7. HTTPS

cPanel's AutoSSL issues and renews a free certificate automatically for
domains pointed at the account — check **SSL/TLS Status** in cPanel to confirm
it's issued, and enable **Force HTTPS Redirect** under **Domains** if it isn't
already on. `SECURE_SSL_REDIRECT` (on by default in `config.settings.production`)
then makes Django itself redirect any request that somehow arrives over plain
HTTP, as a second layer.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Browser stuck in a redirect loop | `TRUST_PROXY_SSL_HEADER` wasn't set to `0` | `python -m keychain set "TRUST_PROXY_SSL_HEADER=0"`, then `touch tmp/restart.txt` |
| Blank white page, or the raw text "Frontend build not found" | `frontend/dist/index.html` doesn't exist on the server | Build locally and `rsync` it up (step 4), or run `./deploy.sh --build-frontend` |
| Page loads but every API call fails (check the browser's Network tab) | The frontend was built with the wrong `VITE_API_URL` (or the default) | Rebuild with `frontend/.env.production` set correctly, re-upload |
| Admin page has no CSS | `collectstatic` hasn't been run, or `STATIC_ROOT` is stale | `python manage.py collectstatic --noinput`, then restart |
| `ImproperlyConfigured: Set ALLOWED_HOSTS...` in the error log | `ALLOWED_HOSTS` isn't set (or is `*`) in the keychain | `python -m keychain set "ALLOWED_HOSTS=yourdomain.com"` |
| Passenger error page immediately on load | Bad `passenger_wsgi.py` path, or dependencies not installed in *this* app's venv | Re-run the cPanel activate command, confirm `pip list` shows Django, check the error log |
| Photo uploads fail past a certain size | Shared hosting's own upload limit (Apache/PHP-style `LimitRequestBody`, if cPanel applies one) is lower than Django's 25 MB cap | Check **MultiPHP INI Editor** / your plan's upload limits in cPanel; there's no way around a hard host-level cap short of raising it there |

## What you don't get here, and what to do instead

A VPS-based deploy gets you a firewall you configure, fail2ban, disk
encryption you control, and root to fix anything. Shared hosting doesn't offer
any of that — here's the adjusted checklist:

- [ ] **Firewall / brute-force protection**: cPanel/WHM-level protections
      (often ModSecurity, sometimes cPHulk) are managed by Namecheap, not you.
      Nothing to configure on your end beyond keeping SSH key-only if the plan
      supports it (cPanel → SSH Access → Manage SSH Keys).
- [ ] **Disk encryption at rest**: out of your control on shared hosting — this
      is a reason backups matter *more*, not less (below).
- [ ] **`DEBUG=False`**, unique `SECRET_KEY` in the keychain — same as any deploy.
- [ ] **`ALLOWED_HOSTS`** is your real domain, not `*` — `production.py` refuses
      to start otherwise.
- [ ] HTTPS-only cookies, HSTS — already on by default in `production.py`.
- [ ] `noindex` — the frontend's `<meta>` tag and `public/robots.txt` handle
      this, and `config.middleware.NoIndexHeaderMiddleware` adds the
      `X-Robots-Tag` header too, since there's no reverse proxy to set it at.
- [ ] No analytics, no third-party scripts or fonts — unchanged, still true.
- [ ] Upload size: Django's own cap is 25 MB (`MAX_PHOTO_UPLOAD_BYTES` in
      `config/settings/base.py`); check your plan doesn't cap lower (see
      Troubleshooting).

## Backups

You still need off-server, encrypted, *tested* backups — this is evidence, and
losing the account doesn't get to mean losing the record.

1. **cPanel's own backups** (Backup Wizard, or JetBackup if your plan includes
   it) are the easiest starting point — schedule a full or home-directory
   backup and set it to download or push to remote storage (FTP/S3/etc.) if
   the option's available on your plan, rather than only keeping a copy on the
   same account.
2. **A cron job as a second, independent copy.** cPanel → **Cron Jobs** →
   nightly, something like:

   ```bash
   cd ~/travis-recovery/backend && tar czf - db.sqlite3 media/ keychain.json | \
     gpg --batch --yes --passphrase-file ~/.backup-passphrase -c -o \
     ~/backups/travis-recovery-$(date +\%Y\%m\%d).tar.gz.gpg
   ```

   Then get that file *off* the account — `rclone` to Backblaze B2 or S3 if
   your plan lets you install it in your home directory, or even a simple
   scheduled `scp`/`rsync` pull from another machine you control.
3. **`keychain.key` backed up separately** from everything else (a password
   manager, or printed) — it's the one thing that makes `keychain.json`
   readable at all.
4. **Do a restore drill once, before you rely on this.** Decrypt the backup
   somewhere else, `tar xzf` it, and actually open a photo.
5. **Retention**: keep everything until the case is fully resolved (see
   `SECURITY_AND_LEGAL.md`). Don't purge on a schedule.

## Rough sizing

- 5 visitors a day × 6 photos × 5 MB ≈ 150 MB/day ≈ 4.5 GB/month. A busy month
  might be 10 GB.
- Each photo is stored three times (original, a display copy, a thumbnail),
  roughly 1.3× the original's size.
- **Check your specific plan's disk quota** — shared hosting quotas are
  usually much smaller than the 40 GB a VPS volume would give you, and cPanel
  will start refusing writes once you hit it. Watch **cPanel → Disk Usage**,
  and delete nothing to make room without asking the attorney first (see
  `SECURITY_AND_LEGAL.md` on preservation).

## Cutover

1. Deploy, create the family admin accounts, generate the invite link
   (`bootstrap_family` prints one, or use the dashboard's "Create a link").
2. Send the link to a couple of relatives and have them submit a test entry —
   including at least one real iPhone photo, to confirm HEIC conversion works
   end to end on the actual server.
3. Point the info page's "Sign up to visit →" link at the app.
4. Keep the old Google Sheet, read-only, as an archive. Don't delete it.

## Reference: what each new file is for

| File | Purpose |
|---|---|
| `backend/passenger_wsgi.py` | The entry point cPanel's Passenger imports. Not used locally, not used on a VPS with its own gunicorn setup. |
| `config/middleware.py` | Adds the `X-Robots-Tag: noindex` header — see "What you don't get here" above. |
| `config/spa.py` | Serves the built `index.html` for any route vue-router handles client-side. |
| `config/settings/production.py` | WhiteNoise setup, the SQLite WAL pragma, and the `TRUST_PROXY_SSL_HEADER` toggle — all explained inline with comments. |
| `deploy.sh` (repo root) | Re-runs the install/migrate/collectstatic/restart sequence for every deploy after the first. Run it *on the server*, inside the activated virtualenv — never locally. |
