"""
Symmetric encryption helpers for sensitive user configuration at rest.

Used to encrypt sensitive fields (e.g. LLM API keys) stored inside the
`User.settings` JSON field, ensuring plain-text keys are never persisted to SQLite
or committed in database dumps.

Key resolution hierarchy:
1. `SETTINGS_ENCRYPTION_KEY` from Django settings / environment (base64 Fernet key).
2. `keychain.key` via `backend/keychain/core.py` if present on disk.
3. Deterministic derivation from Django's `SECRET_KEY` using SHA-256 (fallback for
   test environments or setups where keychain.key is not yet generated).
"""

from __future__ import annotations

import base64
import hashlib
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _derive_fernet_from_secret(secret: str) -> bytes:
    """Derive a URL-safe base64-encoded 32-byte key from a secret string."""
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def get_encryption_fernet() -> Fernet:
    """
    Return a Fernet cipher instance based on configured keys.
    """
    # 1. Check explicit SETTINGS_ENCRYPTION_KEY setting or env var
    env_key = getattr(settings, "SETTINGS_ENCRYPTION_KEY", None)
    if env_key:
        try:
            return Fernet(env_key.strip().encode("utf-8"))
        except (ValueError, TypeError):
            pass

    # 2. Check keychain.key file if present
    try:
        from keychain.core import KEY_PATH
        if KEY_PATH.exists():
            raw_key = KEY_PATH.read_bytes().strip()
            return Fernet(raw_key)
    except Exception:
        pass

    # 3. Fallback: derive deterministically from Django's SECRET_KEY
    secret_key = getattr(settings, "SECRET_KEY", "fallback-insecure-key-for-tests")
    return Fernet(_derive_fernet_from_secret(secret_key))


def is_encrypted(val: str) -> bool:
    """
    Check if a string is already a Fernet token.
    Fernet tokens are URL-safe base64 strings starting with 'gAAAAA'.
    """
    if not isinstance(val, str):
        return False
    # Fernet tokens start with version byte 0x80 which in base64 URL-safe starts with 'gAAAAA'
    return val.startswith("gAAAAA") and len(val) >= 64


def encrypt_secret(raw_val: Optional[str]) -> str:
    """
    Encrypt a plaintext secret string using Fernet.
    If the value is already encrypted, returns it unchanged.
    """
    if not raw_val or not isinstance(raw_val, str):
        return ""
    stripped = raw_val.strip()
    if not stripped:
        return ""
    if is_encrypted(stripped):
        return stripped

    fernet = get_encryption_fernet()
    return fernet.encrypt(stripped.encode("utf-8")).decode("utf-8")


def decrypt_secret(cipher_val: Optional[str]) -> str:
    """
    Decrypt a Fernet cipher string back to plaintext.
    If the value is not encrypted (e.g. legacy plain-text), returns the original string.
    """
    if not cipher_val or not isinstance(cipher_val, str):
        return ""
    stripped = cipher_val.strip()
    if not stripped:
        return ""
    if not is_encrypted(stripped):
        return stripped

    try:
        fernet = get_encryption_fernet()
        return fernet.decrypt(stripped.encode("utf-8")).decode("utf-8")
    except (InvalidToken, Exception):
        # In case of corrupted token or mismatched key, return raw value
        return cipher_val
