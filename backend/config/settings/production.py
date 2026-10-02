"""Production settings for config project."""

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403

DEBUG = False

# ALLOWED_HOSTS is resolved in base.py from the keychain/env. There is no
# wildcard fallback: a mis-set host should fail loudly, not serve any Host header.
#   python -m keychain set ALLOWED_HOSTS=recovery.example.com
if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:  # noqa: F405
    raise ImproperlyConfigured(
        "Set ALLOWED_HOSTS (keychain or env) to your real hostname(s), not '*'."
    )

# CORS_ALLOWED_ORIGINS is resolved in base.py from the keychain/env. Serving the
# built frontend from the same origin as the API means it can stay empty.

# Use PostgreSQL/MySQL in production (optional; SQLite + backups is fine here).
# DATABASES = {
#     'default': env.db('DATABASE_URL')
# }

# SQLite only: WAL mode lets reads and writes overlap instead of locking the
# whole database file, which matters once photo uploads (slow, hold a write)
# and everyone else's page loads (reads) happen at the same time.
if DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3":  # noqa: F405
    DATABASES["default"].setdefault("OPTIONS", {})["init_command"] = (  # noqa: F405
        "PRAGMA journal_mode=wal;"
    )

# --------------------------------------------------------------------------
# Same-origin static serving: WhiteNoise serves both Django's own static
# files (admin, DRF browsable API — collected into STATIC_ROOT as usual) and
# the built frontend's JS/CSS bundle directly from frontend/dist, at the
# exact paths its index.html already references (e.g. /assets/index-xxxx.js)
# — no Vite base-path change needed. config.urls' catch-all route then
# serves that same index.html for every path vue-router handles client-side.
# See docs/HOSTING.md.
# --------------------------------------------------------------------------
MIDDLEWARE = [MIDDLEWARE[0], "whitenoise.middleware.WhiteNoiseMiddleware", *MIDDLEWARE[1:]]  # noqa: F405

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# Root-relative files WhiteNoise serves as-is alongside STATIC_ROOT — the
# frontend's hashed JS/CSS under /assets/, plus whatever else `pnpm build`
# copied from frontend/public/ (robots.txt, favicon, ...).
WHITENOISE_ROOT = FRONTEND_DIST_DIR  # noqa: F405

# Security settings
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"

# Adds X-Robots-Tag: noindex to every response. Defense in depth alongside
# the frontend's own <meta name="robots"> and public/robots.txt (see
# docs/SECURITY_AND_LEGAL.md) — it matters more here than on a VPS behind
# nginx/Caddy, because shared hosting gives you no reverse-proxy layer to set
# response headers at, so it has to come from Django itself.
MIDDLEWARE = [*MIDDLEWARE, "config.middleware.NoIndexHeaderMiddleware"]

# HTTPS. Only trust X-Forwarded-Proto when something in front of this process
# actually sets it — a VPS behind nginx/Caddy, or a host's own load balancer.
# On shared hosting (Namecheap cPanel's "Setup Python App"/Passenger), Apache
# usually terminates TLS itself with nothing in between, and WSGI's own
# wsgi.url_scheme already reflects that correctly — trusting a header that
# never arrives makes Django think every request is insecure, which causes an
# HTTPS redirect loop with SECURE_SSL_REDIRECT below. See docs/HOSTING.md.
#   python -m keychain set TRUST_PROXY_SSL_HEADER=0
if env.bool("TRUST_PROXY_SSL_HEADER", default=True):  # noqa: F405
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)  # noqa: F405
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
# Start short: a wrong HSTS value is sticky in browsers. Raise it (e.g.
# 31536000) once HTTPS is confirmed working.
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=86400)  # noqa: F405
