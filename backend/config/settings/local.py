"""Local settings for config project."""

import sys
from pathlib import Path

# Make the `keychain` package importable from `backend/` at settings load time.
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from keychain import KeychainNotInitializedError, get_list as keychain_get_list  # noqa: E402

from .base import *  # noqa: F401,F403

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0", "testserver"]

CORS_ALLOW_ALL_ORIGINS = env.bool("CORS_ALLOW_ALL_ORIGINS", default=True)


def _dev_cors_origins() -> list[str]:
    """Resolve the dev CORS allow-list from the keychain and environment.

    Falls back to the bundled dev defaults when the keychain is not initialized
    yet (e.g. during first-time `manage.py migrate` before `init`).
    """
    env_cors = env.list("CORS_ALLOWED_ORIGINS", default=[])
    defaults = [
        "http://localhost:5177",
        "http://127.0.0.1:5177",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    try:
        keychain_cors = keychain_get_list("DEV_CORS_ORIGINS", default=defaults) or defaults
    except KeychainNotInitializedError:
        keychain_cors = defaults
    return list(set([*keychain_cors, *env_cors]))


CORS_ALLOWED_ORIGINS = _dev_cors_origins()

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
