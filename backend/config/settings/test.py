"""Test settings for config project."""

from .local import *  # noqa: F401,F403

# Deterministic secret so the suite runs without a developer-specific .env or
# an initialized keychain. Never use this value outside of tests.
SECRET_KEY = "test-secret-key-not-for-production"

DEBUG = True

# Run fast password hashing and keep the test database in memory.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
