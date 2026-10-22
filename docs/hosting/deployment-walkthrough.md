# Deploy Travis Recovery to an Ubuntu Droplet

This walkthrough uses the project's current VPS configuration: Docker Compose
runs Django/Gunicorn and PostgreSQL; Caddy runs on Ubuntu and provides HTTPS.
Private photos live in a Docker volume and are served through authenticated Django
views. The default hostname is `travis.allbarker.com`.

Follow this in order for a **new server and empty database**. If there are existing
records, photos, or encrypted settings to keep, plan their migration first. The
script creates tables; it does not import another installation's data.

Commands marked **Mac** run on your computer. Commands marked **server** run over
SSH on Ubuntu. Replace `DROPLET_IP`, `YOUR_ADMIN_IP`, and `RELEASE_COMMIT` before
using them. Do not paste the whole document into a terminal at once.

For architecture decisions see [the hosting plan](digitalocean.md). For command
explanations and diagnosis see [the Ubuntu reference](ubuntu-admin.md).

## 1. Publish the release from your Mac

**Mac:**

```bash
cd /Users/jake/dev/active/travis-recovery
git status --short
bash scripts/docker-smoke-test.sh
```

Docker Desktop must be running for the smoke test. It uses disposable local data.
At the time this walkthrough was written, Docker's daemon was stopped, so a full
container smoke test had not yet been completed for the VPS changes.

Review, commit, and push the intended application/deployment changes through your
normal Git workflow. Include `Dockerfile`, `.dockerignore`, `compose.production.yaml`,
`deploy/digitalocean/`, the scripts, and the backend settings/readiness changes.
Check `git status` before committing so unrelated edits are not included by accident.

Then record the pushed commit:

```bash
git rev-parse HEAD
```

Use that value wherever this guide says `RELEASE_COMMIT`. The server cannot see
uncommitted local changes, and merely cloning the repository will not copy them.

## 2. Create or identify the Droplet

**DigitalOcean dashboard:**

- Use a supported Ubuntu LTS image; Ubuntu 24.04 LTS is the baseline for this guide.
- For an initial small installation, 2 vCPU / 4 GiB RAM is a starting estimate,
  especially when building the image on the server. Measure actual usage afterward.
- Add your existing SSH **public** key, select a region near users, and enable
  monitoring and backups. Record the public IPv4 address.
- Confirm recovery-console access and configure billing/usage alerts.

If the Droplet already exists, inventory it before installing anything. Do not
replace another application's proxy, firewall, or containers with this setup.
DigitalOcean's [recommended setup](https://docs.digitalocean.com/products/droplets/getting-started/recommended-droplet-setup/)
provides the provider-side background.

**Mac:**

```bash
ssh root@DROPLET_IP
```

Verify the SSH fingerprint through a trusted provider console before accepting a
new host key. If your Droplet already has an administrator, use that account and
skip creating another one.

**Server, initial root session:**

```bash
cat /etc/os-release
uname -m
free -h
df -h
ss -lntp
```

Expect Ubuntu and the CPU architecture you selected. Check ports 80/443 are free.

## 3. Create your everyday administrator

**Server, initial root session:**

```bash
adduser deploy
usermod -aG sudo deploy
install -d -m 0700 -o deploy -g deploy /home/deploy/.ssh
install -m 0600 -o deploy -g deploy /root/.ssh/authorized_keys /home/deploy/.ssh/authorized_keys
```

Choose a strong local password for `deploy`; it is used for `sudo`. The last
command assumes your root account was provisioned with the intended public keys.
Check which keys you copy if multiple people have access.

Keep this root session open. Open a **second terminal on your Mac**:

```bash
ssh deploy@DROPLET_IP
sudo -v
```

Continue in that administrator session. All remaining server commands assume
`deploy`, with `sudo` when needed. Verify login before restricting SSH.

## 4. Update Ubuntu and configure access

**Server:**

```bash
sudo apt update
sudo apt upgrade
sudo apt install ca-certificates curl gnupg git python3 util-linux ufw dnsutils
```

These are host utilities. Python and Node application dependencies will be
installed inside the image; do not run `pip install` or `pnpm install` on Ubuntu.

Check for a required reboot:

```bash
test -f /var/run/reboot-required && cat /var/run/reboot-required
```

No output/nonzero status when the file is absent is normal. If a reboot is needed,
run `sudo reboot`, wait for startup, and reconnect with `ssh deploy@DROPLET_IP`.

### Allow SSH before enabling the firewall

`YOUR_ADMIN_IP` means your Mac's public internet address, not its home LAN address.
The existing SSH session's `echo "$SSH_CONNECTION"` shows the client source IP the
server sees. If you use a VPN, consider its effect on that address.

**DigitalOcean dashboard:** attach a Cloud Firewall allowing inbound TCP 22 from
your admin address, and TCP 80/443 from the public internet. Keep outbound access
available for DNS, repositories, certificates, and backups. Cover IPv6 as well if
it is enabled. Do not add public rules for 8000 or 5432.

**Server, on a fresh host using SSH port 22:**

```bash
sudo ufw status numbered
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow from YOUR_ADMIN_IP to any port 22 proto tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status verbose
```

Review earlier rules if UFW was already configured; these commands do not remove
old broad allow rules. Open another SSH connection to verify access. When your
public IP changes, update both firewalls before relying on the new connection.

### Disable root/password SSH after key login works

**Server:**

```bash
sudoedit /etc/ssh/sshd_config.d/00-travis-recovery.conf
```

Add:

```text
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
```

Then validate and inspect effective values:

```bash
sudo sshd -t
sudo sshd -T | grep -E 'permitrootlogin|passwordauthentication|kbdinteractiveauthentication|pubkeyauthentication'
```

Expected values are `no`, `no`, `no`, and `yes`. If they differ, inspect existing
SSH/cloud-init configuration before proceeding. Once correct:

```bash
sudo systemctl reload ssh
```

Test a fresh `deploy` login before closing existing sessions. The
[Ubuntu SSH guide](https://ubuntu.com/server/docs/how-to/security/openssh-server/)
explains snippet precedence and configuration validation.

## 5. Install Docker Engine and Compose

These commands are for a fresh Ubuntu installation. If Docker/containerd is already
installed, inspect its installation and existing workloads before changing packages.
Use [Docker's official Ubuntu instructions](https://docs.docker.com/engine/install/ubuntu/)
if the supported OS/package setup changes.

**Server:**

```bash
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources > /dev/null <<EOF_DOCKER
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF_DOCKER
sudo apt update
sudo apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker run --rm hello-world
sudo docker compose version
```

Expect the hello-world confirmation and Compose **v2**. Commands below use `sudo`
for Docker; adding your login to the Docker group is unnecessary.

## 6. Give the server read access to the repository

The repository remote is `git@github.com:barkbarkgoose/travis.git`. For a private
repository, use a separate read-only GitHub deploy key for this server.

**Server, as deploy:**

```bash
ssh-keygen -t ed25519 -f ~/.ssh/travis-recovery-github -C travis-recovery-vps
cat ~/.ssh/travis-recovery-github.pub
```

Use a passphrase and `ssh-agent` for interactive Git access. Add the displayed
**public** key in the repository's GitHub Settings → Deploy keys; leave write
access disabled. Never upload the private key or copy your Mac's private key here.

Configure the key selection:

```bash
nano ~/.ssh/config
```

Append (merge with an existing GitHub entry if necessary):

```sshconfig
Host github.com
    HostName github.com
    User git
    IdentityFile ~/.ssh/travis-recovery-github
    IdentitiesOnly yes
```

```bash
chmod 600 ~/.ssh/config
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/travis-recovery-github
ssh -T git@github.com
```

Verify GitHub's host fingerprint against its published fingerprints. A successful
GitHub authentication message says shell access is unavailable and may return exit
status 1; that alone is not an authentication failure.

Clone as your ordinary administrator, not through `sudo git`:

```bash
sudo install -d -o deploy -g deploy -m 0755 /opt/travis-recovery
git clone git@github.com:barkbarkgoose/travis.git /opt/travis-recovery
cd /opt/travis-recovery
git checkout --detach RELEASE_COMMIT
git status --short
ls compose.production.yaml scripts/deploy-vps.sh deploy/digitalocean/Caddyfile
```

Expected: no local modifications, and all three files exist. If they are missing,
check that the deployment changes were pushed and the correct commit was selected.

## 7. Create the server's secrets file

**Only for a brand-new installation.** Existing encrypted data needs its original
effective encryption key. A new random key cannot decrypt it. Do not regenerate
keys for later deployments or casually change PostgreSQL credentials after the
persistent database has been initialized.

**Server, from /opt/travis-recovery:**

```bash
sudo install -d -m 0700 /etc/travis-recovery
sudo python3 - <<'PY'
import base64
import os
import secrets
from pathlib import Path

source = Path('deploy/digitalocean/app.env.example').read_text()
replacements = {
    'replace-with-a-strong-stable-secret': secrets.token_urlsafe(64),
    'replace-with-a-stable-fernet-key': base64.urlsafe_b64encode(os.urandom(32)).decode(),
    'replace-with-a-url-safe-random-password': secrets.token_urlsafe(32),
}
for placeholder, value in replacements.items():
    source = source.replace(placeholder, value)
path = '/etc/travis-recovery/app.env'
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as stream:
    stream.write(source)
print('Created root-readable server environment file; secrets were not printed.')
PY
sudoedit /etc/travis-recovery/app.env
```

Confirm `ALLOWED_HOSTS` is your real hostname, with no scheme/path. Keep
`MEDIA_STORAGE_BACKEND=filesystem` for this guide. `APP_IMAGE_TAG=initial` is a
starting placeholder that the deployment script replaces after success.

The file-creation command deliberately refuses to overwrite an existing file.
Use `sudoedit` for deliberate changes; do not delete it to make generation succeed.
Back up the file securely. Never commit it or paste it into support logs.

Validate configuration without printing secrets:

```bash
sudo docker compose --env-file /etc/travis-recovery/app.env -f compose.production.yaml config --quiet
```

Expected: no output, exit status zero. A missing-variable error means the named
setting must be fixed before deployment.

## 8. Deploy the application locally on the server

**Server, from /opt/travis-recovery:**

```bash
sudo scripts/deploy-vps.sh /etc/travis-recovery/app.env first-vps-20261021
```

Use a unique tag each time; the example is only a label, not a date you must reuse.
If an image with that tag exists (including after a failed attempt), choose another
tag. Do not delete a prior release image just to reuse its name.

The script builds the frontend/app image, starts PostgreSQL, checks Django,
stops any running app for a consistent local DB/media backup, runs migrations,
and starts the new app. It waits for the real `/health/` endpoint and updates
`APP_IMAGE_TAG` in the secrets file after success. Later releases have downtime
while the app is stopped for backup/migration/replacement.

Expect a final message saying the release is healthy locally. `check --deploy`
may report warnings: review them. A warning about HSTS preload/subdomains can be
intentional during initial HTTPS setup; do not enable broad HSTS blindly. Errors
or failed migrations need investigation before continuing.

Check status and the upstream response:

```bash
sudo docker compose --env-file /etc/travis-recovery/app.env -f compose.production.yaml ps
curl --fail --show-error --max-time 10 http://127.0.0.1:8000/health/ \
  -H 'Host: travis.allbarker.com' -H 'X-Forwarded-Proto: https'
```

Replace the Host value if using another domain. Expect healthy `app` and `db`, and
`{"status": "ok"}`. This loopback test intentionally supplies the proxy headers
that Caddy will set. Do not expose Gunicorn publicly to make the check work.

## 9. Point DNS at the Droplet and install Caddy

At your existing DNS provider, create/update an **A** record for
`travis.allbarker.com` to the Droplet IPv4. Only publish **AAAA** if IPv6 is configured
and reachable. Remove stale records that send clients to the old installation.
If this domain is already live elsewhere, coordinate the cutover rather than
changing it while data is still moving.

**Server or Mac:**

```bash
dig +short A travis.allbarker.com
dig +short AAAA travis.allbarker.com
```

Expect the intended address(es). DNS caches can retain earlier answers until TTLs
expire. For this first setup, use direct DNS without adding another CDN/proxy.

**Server:** install the stable Caddy package using its
[official Ubuntu instructions](https://caddyserver.com/docs/install#debian-ubuntu-raspbian).

```bash
sudo apt install debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg
sudo chmod o+r /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy
sudo cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.before-travis
sudo install -m 0644 deploy/digitalocean/Caddyfile /etc/caddy/Caddyfile
```

This replaces the packaged default Caddyfile on a **new server**. If Caddy already
hosts sites, merge the new site block instead. If your hostname differs, edit it
with `sudoedit /etc/caddy/Caddyfile` so it matches `ALLOWED_HOSTS` and DNS.

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl enable --now caddy
sudo systemctl reload caddy
sudo systemctl status caddy --no-pager
sudo journalctl -u caddy -n 50 --no-pager
```

Expect a valid configuration and running service. Caddy handles certificate
issuance/renewal. DNS, outbound access, and inbound 80/443 must work. Keep Django's
HTTPS settings enabled; do not add a public `/media` directory route.

## 10. Create the first family account and test the site

For a new empty database, create the family organization/admin. Replace the name
and email with yours; these values are examples.

**Server:**

```bash
sudo docker compose --env-file /etc/travis-recovery/app.env -f compose.production.yaml exec app \
  python manage.py bootstrap_family \
  --org-name "Travis's Family" \
  --admin "Your Name <you@example.com>" \
  --base-url https://travis.allbarker.com
```

The command prints a generated password for a newly created account and a private
join link. Store them privately. Re-running reuses existing objects and does not
reset an existing user's password. Family admin access is distinct from Django
superuser permissions. To set a password explicitly, use the interactive command:

```bash
sudo docker compose --env-file /etc/travis-recovery/app.env -f compose.production.yaml exec app \
  python manage.py changepassword you@example.com
```

Skip bootstrap for a migrated database until its existing organizations/accounts
are verified; creating a second organization is not a data migration.

**Mac:**

```bash
curl -I --max-time 10 http://travis.allbarker.com/
curl --fail --show-error --max-time 10 https://travis.allbarker.com/health/
nc -vz -w 5 DROPLET_IP 8000
nc -vz -w 5 DROPLET_IP 5432
```

Expect HTTP → HTTPS, a valid certificate and readiness JSON, and failed public
connections to 8000/5432. Docker ports can bypass UFW, so this external check matters.

In your browser, verify login, journal entry creation, bookings, admin styling,
and a deep-link page refresh. Upload a test photo, retrieve it while authorized,
and confirm an unauthenticated request for its actual photo endpoint is denied.
Use non-sensitive test data for these checks.

Then verify a restart preserves it:

```bash
sudo docker compose --env-file /etc/travis-recovery/app.env -f compose.production.yaml restart app
sudo docker compose --env-file /etc/travis-recovery/app.env -f compose.production.yaml ps
```

Wait for healthy status and repeat the browser check. During a maintenance window,
reboot the Droplet and verify Docker/Caddy/app startup too.

## 11. Set up backups and alerts before relying on the site

The script writes local pre-release backups under
`/var/backups/travis-recovery/TIMESTAMP-RELEASE-PID/`:

- `database.dump`: PostgreSQL custom-format export.
- `media.tar.gz`: local private photos.
- `app.env`: credentials and encryption keys, including the previous image tag.

It verifies archive readability, **not a full restore**. The first deployment's
backup is of an empty database/media set; it does not protect later user activity.
There is currently no scheduled backup job, automatic off-server transfer, or
backup-age alert in this repository.

Before putting important records on the site:

1. Choose the acceptable loss window and schedule coordinated DB/media backups
   accordingly. Deployment-only backups are insufficient for daily changes.
2. Encrypt and copy backups to storage outside the Droplet using separate access
   credentials. Include the secrets file; protect its keys separately too.
3. Restore a copy into an isolated environment and verify entries, users, photos,
   and encrypted settings. Record the recovery procedure and duration.
4. Configure alerts for external HTTPS failure, RAM/disk pressure, failed backup
   jobs, and stale backups. Enable the provider's system backups as another layer.

Inspect local backup directories without exposing their contents:

```bash
sudo ls -lt /var/backups/travis-recovery
sudo du -sh /var/backups/travis-recovery
```

Also plan security updates and maintenance reboots. Ubuntu updates do not rebuild
the app image; Python/Node dependencies need a tested new image release.

## 12. Deploy later updates

**Mac:** review, test, commit, and push the next release. Record its commit ID.

**Server, as deploy:**

```bash
cd /opt/travis-recovery
git status --short
git fetch origin
git checkout --detach RELEASE_COMMIT
sudo scripts/deploy-vps.sh /etc/travis-recovery/app.env UNIQUE_RELEASE_TAG
```

The worktree should be clean before switching commits; do not discard unexplained
changes. If your SSH agent is gone, start it and add the deploy key again as in
step 6. Keep the same secrets file and persistent volumes.

After success, repeat the public health/browser checks. The deployment script does
**not** install or reload Caddy. If its configuration changed, review and apply it
separately using the validate/reload sequence from step 9.

`restart app` only restarts the existing container. It does not build new code or
apply a new environment. Use the deployment script for a release.

## 13. If deployment fails

**Server:**

```bash
cd /opt/travis-recovery
sudo docker compose --env-file /etc/travis-recovery/app.env -f compose.production.yaml ps -a
sudo docker compose --env-file /etc/travis-recovery/app.env -f compose.production.yaml logs --tail=100 app
sudo docker compose --env-file /etc/travis-recovery/app.env -f compose.production.yaml logs --tail=100 db
sudo journalctl -u caddy -n 100 --no-pager
free -h
df -h
df -i
```

Read the first meaningful error. A failed build leaves the existing app alone;
a failure during backup may restart the existing container. A failed migration
can leave a partially changed schema. If startup fails after successful migration,
the script deliberately avoids automatically restoring old code.

If readiness fails after the new container starts, `APP_IMAGE_TAG` may still name
the previous image in the env file. Inspect actual container/image state before
running another `up` command.

For a code rollback, confirm the previous image is compatible with the current
schema, set its tag with `sudoedit /etc/travis-recovery/app.env`, and recreate the
app with `sudo docker compose --env-file /etc/travis-recovery/app.env -f
compose.production.yaml up -d --no-deps --wait app`. Database restore is a separate,
coordinated recovery operation and may lose writes since the backup.

Do not use `down -v`, volume removal, or volume-pruning commands to fix startup.
Do not change `POSTGRES_PASSWORD` in the env file as a connection-error workaround:
the existing PostgreSQL volume keeps its initialized password. Do not publish
8000/5432 or disable certificate checks to make a failing test pass.

This document describes the server procedure; it does not mean a real Droplet,
DNS cutover, full container deployment, or restore drill has already been tested.
