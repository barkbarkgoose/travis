"""Base settings for config project."""

import sys
from datetime import timedelta
from pathlib import Path

import environ

env = environ.Env()

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Make the `keychain` package importable when settings load through a plain
# `python manage.py` invocation (dev.sh already adds backend/ to sys.path).
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

environ.Env.read_env(BASE_DIR / ".env")

from keychain import (  # noqa: E402
    KeychainNotInitializedError,
    get as keychain_get,
    get_int as keychain_get_int,
    get_list as keychain_get_list,
)


def _keychain_or_env(key: str, env_var: str, default: str | None = None) -> str | None:
    """Resolve a scalar setting from the keychain, falling back to the environment.

    The keychain is optional during first-run bootstrap: if it has not been
    initialized, values are read from `.env` so management commands keep working
    before `python -m keychain init`.
    """
    try:
        value = keychain_get(key)
    except KeychainNotInitializedError:
        value = None
    if value is not None:
        return value
    return env(env_var, default=default)


def _keychain_or_env_list(
    key: str, env_var: str, default: list[str] | None = None
) -> list[str]:
    """Resolve a comma-separated list setting from keychain or environment."""
    try:
        value = keychain_get_list(key)
    except KeychainNotInitializedError:
        value = None
    if value is not None:
        return value
    return env.list(env_var, default=default if default is not None else [])


SECRET_KEY = _keychain_or_env("SECRET_KEY", "SECRET_KEY")

DEBUG = env.bool("DEBUG", default=False)

# Real hostnames come from the keychain/env (comma separated). local.py overrides
# this for development; production.py refuses to start with it empty.
ALLOWED_HOSTS = _keychain_or_env_list("ALLOWED_HOSTS", "ALLOWED_HOSTS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "django_filters",
    "corsheaders",
    "apps.organizations",
    "apps.users",
    "apps.journal",
    "apps.visits",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

APPEND_SLASH = False

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASE_URL = _keychain_or_env(
    "DATABASE_URL", "DATABASE_URL", default="sqlite:///db.sqlite3"
)
DATABASES = {"default": env.db_url_config(DATABASE_URL)}

AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"  # storage is always UTC
USE_I18N = True
USE_TZ = True

# Where people actually are (Provo, UT). Used when formatting times for humans
# (exports); the frontend mirrors this value.
DISPLAY_TIME_ZONE = "America/Denver"

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# The built Vue app (`frontend/dist`, from `pnpm build`) — same-origin
# serving, see docs/HOSTING.md. In production this is served directly by
# WhiteNoise (config.settings.production) and as the fallback for any route
# vue-router handles client-side (config.spa.serve_frontend). Not present in
# local dev unless you've run a build yourself; ./dev.sh uses Vite's own dev
# server instead and never touches this.
FRONTEND_DIST_DIR = BASE_DIR.parent / "frontend" / "dist"

# Uploaded evidence (photos). There is deliberately no MEDIA_URL and no URL
# route serving this directory: files are only ever streamed through
# authenticated views, so a guessed path never returns a photo.
MEDIA_ROOT = BASE_DIR / "media"
MAX_PHOTO_UPLOAD_BYTES = 25 * 1024 * 1024
# Bodies bigger than this spill to a temp file instead of living in memory.
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

# How long after submission an entry's author can still edit it before further
# corrections must go in as an addendum. See apps.journal.models.Entry.is_locked.
try:
    ENTRY_EDIT_WINDOW_HOURS = keychain_get_int("ENTRY_EDIT_WINDOW_HOURS", default=24) or 24
except KeychainNotInitializedError:
    ENTRY_EDIT_WINDOW_HOURS = 24

# How many visitors can have overlapping bookings at once — matches the
# hospital's stated limit on the public info page. See apps.visits.views.
try:
    MAX_CONCURRENT_VISITORS = keychain_get_int("MAX_CONCURRENT_VISITORS", default=3) or 3
except KeychainNotInitializedError:
    MAX_CONCURRENT_VISITORS = 3

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# CORS
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = _keychain_or_env_list(
    "CORS_ALLOWED_ORIGINS", "CORS_ALLOWED_ORIGINS"
)

# REST Framework
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "DEFAULT_THROTTLE_RATES": {"join": "10/min"},
    # Number of reverse proxies in front of Django (0 in dev, 1 behind nginx or
    # Caddy). Without it every visitor shares the proxy's IP for throttling.
    "NUM_PROXIES": env.int("NUM_PROXIES", default=0),
}


def _jwt_lifetimes() -> tuple[timedelta, timedelta]:
    """Resolve JWT lifetimes from the keychain, falling back to safe defaults.

    These are read from the keychain so token lifetimes can be tuned per
    environment without editing code. Falls back to 60 minutes / 60 days when the
    keychain has not been initialized yet (e.g. during the first migration).
    Refresh is long because visitors join by link on their phones; the refresh
    endpoint slides the session forward each time it is used.
    """
    try:
        access_minutes = (
            keychain_get_int("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", default=60) or 60
        )
    except KeychainNotInitializedError:
        access_minutes = 60
    try:
        refresh_days = (
            keychain_get_int("JWT_REFRESH_TOKEN_LIFETIME_DAYS", default=60) or 60
        )
    except KeychainNotInitializedError:
        refresh_days = 60
    return timedelta(minutes=access_minutes), timedelta(days=refresh_days)


_ACCESS_LIFETIME, _REFRESH_LIFETIME = _jwt_lifetimes()

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": _ACCESS_LIFETIME,
    "REFRESH_TOKEN_LIFETIME": _REFRESH_LIFETIME,
}

# User settings / secrets-at-rest encryption. Optional: when unset, the users
# crypto helper falls back to keychain.key and then to a SHA-256 derivation of
# SECRET_KEY (see apps/users/crypto.py).
SETTINGS_ENCRYPTION_KEY = env("SETTINGS_ENCRYPTION_KEY", default="")
