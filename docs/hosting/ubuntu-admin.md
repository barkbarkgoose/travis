# Ubuntu VPS administration reference

Companion to [the DigitalOcean plan](digitalocean.md). Run commands on the Ubuntu
Droplet unless labeled **your computer**. Examples assume the proposed architecture;
Caddy/Compose names and paths only work after those deployment files are implemented.
Replace `DROPLET_IP`, `YOUR_ADMIN_IP`, and the hostname before running commands.

`sudo` uses administrator privileges. `Ctrl+C` stops a foreground command or log
follow; `q` exits pagers such as `less` and the interactive `systemctl status` view.
Read-only inspection commands come first; changes are called out separately.

## Identify the machine and see what it is doing

| Question | Command | What to look for |
|---|---|---|
| Which Ubuntu version? | `cat /etc/os-release` | Distribution and version, not just the kernel. |
| Kernel and CPU architecture? | `uname -a` | Kernel version; `x86_64` vs `aarch64`. |
| Host identity? | `hostnamectl` | Hostname, OS and architecture. |
| Who am I / what groups? | `id` | Admin/Docker group membership. |
| Uptime and load? | `uptime` | Load averages relative to CPU count; load also includes some waiting tasks. |
| CPUs? | `lscpu` | CPU count and architecture. |
| Processes? | `ps aux --sort=-%cpu` | Highest CPU first; arguments may contain secrets. |
| Live resource usage? | `top` | CPU, processes, memory; press `q` to exit. |
| RAM/swap? | `free -h` | Check **available** memory; filesystem cache is normal. |
| Disk free space? | `df -h` | Root, Docker storage and media filesystem utilization. |
| Inodes exhausted? | `df -i` | A disk can reject new files even with bytes available. |
| Block devices/mounts? | `lsblk -f` | Filesystems and mountpoints. |
| Which directories are growing? | `sudo du -xhd1 /var /srv /opt` | Read-only but can be slow on a busy server. |
| Current time/timezone? | `timedatectl` | Correct time sync matters to TLS and token expiration. |
| Logged-in users? | `who` | Active sessions; `last -n 10` shows recent login history. |

## Services, failures, and logs

```bash
systemctl list-units --type=service --state=running
systemctl --failed
systemctl status docker caddy ssh --no-pager
systemctl is-enabled docker caddy
sudo journalctl -u caddy --since '1 hour ago' --no-pager
sudo journalctl -u docker -n 100 --no-pager
sudo journalctl -u ssh -n 100 --no-pager
sudo journalctl -u caddy -f
sudo journalctl -k -b --no-pager
journalctl --disk-usage
```

A service can be enabled at boot but currently failed, or running now but not
enabled at boot. Check both. Kernel logs can explain out-of-memory kills and disk
errors. Logs may contain private information; redact before sharing.

Changing commands, use after inspecting the failure:

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
sudo systemctl restart caddy
```

Validate configuration before reloading. A restart interrupts active work; repeated
restarts can hide the original problem. `systemctl restart docker` affects **all**
containers and should not be a routine app restart.

## Ports: listening is different from reachable

```bash
sudo ss -lntp
sudo ss -lnup
sudo ss -tnp
ip -br address
ip route
sudo ufw status verbose
sudo ufw status numbered
```

`ss -lntp`: listening TCP sockets with process names. `ss -lnup`: UDP listeners.
`ss -tnp`: established TCP connections and related state. With `sudo`, process
information is more complete.

| Address in listener output | Meaning |
|---|---|
| `127.0.0.1:8000` | IPv4 loopback, only reachable on that host. Expected app publication. |
| `0.0.0.0:443` | All IPv4 interfaces; reachability still depends on routing/firewalls. |
| `[::]:443` | IPv6 wildcard; IPv4 handling depends on socket/system settings. Verify both. |

Docker uses network namespaces and forwarding rules, so host `ss` alone may not
show every published container port. Also inspect `sudo docker ps` and
`sudo docker compose -f compose.production.yaml ps`. Database port 5432 must have
no public publication; app port 8000 must be bound only to host loopback.

Check the DigitalOcean Cloud Firewall in the control panel too. UFW does not show
cloud rules, and [Docker publication can bypass UFW](https://docs.docker.com/engine/install/ubuntu/).

**Your computer**, from outside the Droplet:

```bash
nc -vz -w 5 DROPLET_IP 22
nc -vz -w 5 DROPLET_IP 443
nc -vz -w 5 DROPLET_IP 8000
nc -vz -w 5 DROPLET_IP 5432
curl -I --max-time 10 https://travis.allbarker.com/
```

With the proposed firewall, 22 succeeds only from your admin source and 443
succeeds publicly. 8000/5432 must fail externally. A timeout can indicate filtering
or a routing problem; refusal often means no listener. Neither identifies the
full cause alone. Test IPv6 separately if enabled.

Optional **your computer**: if Nmap is installed, scan only your own server:
`nmap -Pn -p 22,80,443,8000,5432 DROPLET_IP`. This checks selected TCP ports,
not every port/protocol. `ping` failure alone does not prove a server is down.

## DNS, TLS, and proxy diagnosis

```bash
# Run from your computer (dig requires a DNS utilities package).
dig +short A travis.allbarker.com
dig +short AAAA travis.allbarker.com
curl -I --max-time 10 http://travis.allbarker.com/
curl -I --max-time 10 https://travis.allbarker.com/
curl --resolve travis.allbarker.com:443:DROPLET_IP -I https://travis.allbarker.com/
```

`--resolve` tests the target IP while retaining the real hostname for TLS and HTTP.
It is useful before DNS cutover. Do not add `-k`: that would hide certificate
validation failures. Public certificate issuance still needs valid domain control
and an appropriate validation path.

On the **Droplet**, test the app behind the proxy:

```bash
curl -I --max-time 10 http://127.0.0.1:8000/ \
  -H 'Host: travis.allbarker.com' \
  -H 'X-Forwarded-Proto: https'
```

This intentionally simulates trusted proxy headers over loopback; never use it
as a reason to expose Gunicorn publicly. If loopback works but public HTTPS does
not, inspect Caddy, DNS and both firewalls. An HTTP redirect loop often means
Django does not recognize the original HTTPS scheme.

## Docker and the application

Run from `/opt/travis-recovery` after the proposed Compose file exists. The
examples assume Compose service names `app` and `db`.

```bash
sudo docker version
sudo docker compose version
sudo docker ps -a
sudo docker stats --no-stream
sudo docker system df
sudo docker compose -f compose.production.yaml ps
sudo docker compose -f compose.production.yaml logs --tail=100 app
sudo docker compose -f compose.production.yaml logs --tail=100 db
sudo docker compose -f compose.production.yaml logs -f --tail=100 app
sudo docker compose -f compose.production.yaml exec app python manage.py check --deploy
sudo docker compose -f compose.production.yaml exec app python manage.py showmigrations --plan
```

These Django commands use the **running container's** production environment.
A failed/stopped container cannot accept `exec`; inspect logs first, then use a
controlled one-off `run --rm` if needed.

`docker stats` helps distinguish app load from DB load. `docker system df` shows
storage consumption; it does not authorize deleting images or volumes.

Changing commands:

- `sudo docker compose -f compose.production.yaml restart app` restarts the
  existing container; it does **not** apply a new image or changed environment.
- `sudo docker compose -f compose.production.yaml up -d app` recreates it when
  configuration/image changes require that. Follow the release/migration plan first.
- `sudo docker compose -f compose.production.yaml down` stops/removes this stack's
  containers/network, causing downtime; persistent named volumes normally remain.
- **Do not use `down -v`, `docker volume rm`, or volume-pruning commands as cleanup.**
  They can remove the database or media. Keep rollback images until no longer needed.

## Updates and access changes

Inspect first:

```bash
apt list --upgradable
systemctl status unattended-upgrades --no-pager
systemctl list-timers --all
test -f /var/run/reboot-required && cat /var/run/reboot-required
sudo sshd -t
sudo sshd -T
```

`sshd -t` returning no output with exit code zero means configuration syntax is
valid; `sshd -T` displays effective defaults/settings. Match rules may depend on
connection details. The reboot-file check returning a nonzero exit code when the
file is absent is normal.

Changing commands, in a maintenance window:

```bash
sudo apt update
sudo apt upgrade
sudo systemctl reload ssh
sudo reboot
```

`apt update` refreshes package metadata; `apt upgrade` installs eligible package
updates. Review the proposed changes. A reboot disconnects SSH and interrupts the
site; reconnect and verify the app afterward. Ubuntu package upgrades do not update
libraries embedded in the app image: rebuild/test/redeploy that separately.

Example **initial UFW rules**, only after replacing the source IP and confirming
that SSH really uses port 22:

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow from YOUR_ADMIN_IP to any port 22 proto tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status verbose
```

Inspect existing rules first; these commands add rules and do not remove earlier
broad allow rules. Mirror the intended policy in the Cloud Firewall, include
IPv6 if used, and keep your current SSH connection open. Verify a second login
before closing it. Ubuntu's [UFW guide](https://ubuntu.com/server/docs/firewalls/)
and [OpenSSH guide](https://ubuntu.com/server/docs/how-to/security/openssh-server/)
provide the underlying configuration details.

## When the site is down

1. From your computer, test HTTPS and confirm A/AAAA records. Note whether the
   failure is DNS, timeout, certificate error, redirect loop, or HTTP error.
2. Check provider status, Droplet power/console access and the cloud firewall.
3. On the Droplet, check `uptime`, `free -h`, `df -h`, `df -i`, and `systemctl --failed`.
4. Inspect Caddy logs, Docker/Compose status, and recent app/database logs.
5. Test the loopback upstream with the correct Host/proxy headers.
6. If containers exit, read their first startup error: missing GCS configuration,
   wrong DB address, permission failures, and missing hosts have distinct fixes.
7. Restore the service using the tested deployment/recovery procedure. Record the
   cause, action and outcome; verify a real authenticated workflow after recovery.

Never paste `.env` contents, database URLs, `docker inspect` environment output,
private keys, or unredacted private request logs into a public issue or chat.
