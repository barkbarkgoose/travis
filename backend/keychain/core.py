"""
Core keychain loader, cache, and exception types.

Storage format on disk (`keychain.json`):
    {
        "_format": "fernet-v1",
        "encrypted": "<url-safe-base64 Fernet blob>",
    }

The inner plaintext is a JSON object: `{"KEY": "value", ...}`.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any, Optional

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError as e:  # pragma: no cover - fail fast at first use
    raise ImportError(
        "cryptography is required for the keychain. "
        "Install it via `pip install -r backend/requirements.txt`."
    ) from e


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

# `keychain/` package lives in `backend/`, so the data files sit one level up
# (i.e. in `backend/keychain.json` and `backend/keychain.key`).
PACKAGE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = PACKAGE_DIR.parent

DEFAULT_KEYS_PATH = BACKEND_DIR / "keychain.json"
DEFAULT_KEY_PATH = BACKEND_DIR / "keychain.key"

# Allow tests / CI to redirect the storage locations via env vars.
KEYS_PATH = Path(os.environ.get("KEYCHAIN_JSON_PATH", DEFAULT_KEYS_PATH))
KEY_PATH = Path(os.environ.get("KEYCHAIN_KEY_PATH", DEFAULT_KEY_PATH))

_FORMAT_VERSION = "fernet-v1"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class KeychainNotInitializedError(RuntimeError):
    """Raised when keychain.key or keychain.json is missing."""


class KeychainCorruptedError(RuntimeError):
    """Raised when the encrypted blob cannot be decrypted (wrong key / tampered)."""


class KeychainKeyError(KeyError):
    """Raised when a requested key is not present in the keychain."""


# ---------------------------------------------------------------------------
# Loader / cache
# ---------------------------------------------------------------------------

_CACHE: Optional[dict[str, Any]] = None
_FERNET: Optional[Fernet] = None


def _load_fernet() -> Fernet:
    global _FERNET
    if _FERNET is not None:
        return _FERNET

    try:
        raw = KEY_PATH.read_bytes()
    except FileNotFoundError as e:
        raise KeychainNotInitializedError(
            f"keychain.key not found at {KEY_PATH}. "
            "Run `cd backend && python -m keychain init` to create it."
        ) from e
    raw = raw.strip()
    try:
        _FERNET = Fernet(raw)
    except (ValueError, TypeError) as e:
        raise KeychainCorruptedError(
            f"keychain.key at {KEY_PATH} is not a valid Fernet key: {e}"
        ) from e
    return _FERNET


def _decrypt_all() -> dict[str, Any]:
    """Decrypt and parse the keychain.json contents."""
    try:
        raw_bytes = KEYS_PATH.read_bytes()
    except FileNotFoundError as e:
        raise KeychainNotInitializedError(
            f"keychain.json not found at {KEYS_PATH}. "
            "Run `cd backend && python -m keychain init` to create it, "
            "then `python -m keychain set KEY=VALUE` to populate values."
        ) from e
    try:
        envelope = json.loads(raw_bytes)
    except json.JSONDecodeError as e:
        raise KeychainCorruptedError(
            f"keychain.json at {KEYS_PATH} is not valid JSON: {e}"
        ) from e

    if envelope.get("_format") != _FORMAT_VERSION:
        raise KeychainCorruptedError(
            f"keychain.json has unknown _format={envelope.get('_format')!r}; "
            f"expected {_FORMAT_VERSION!r}."
        )

    blob = envelope.get("encrypted")
    if not isinstance(blob, str):
        raise KeychainCorruptedError(
            "keychain.json is missing the 'encrypted' string field."
        )

    fernet = _load_fernet()
    try:
        plaintext = fernet.decrypt(blob.encode("utf-8"))
    except InvalidToken as e:
        raise KeychainCorruptedError(
            "Failed to decrypt keychain.json. The keychain.key file may have "
            "rotated, or the JSON has been tampered with."
        ) from e

    try:
        data = json.loads(plaintext.decode("utf-8"))
    except json.JSONDecodeError as e:
        raise KeychainCorruptedError(
            "Decrypted keychain contents are not valid JSON."
        ) from e

    if not isinstance(data, dict):
        raise KeychainCorruptedError(
            "Decrypted keychain contents must be a JSON object."
        )
    return data


def _ensure_cache() -> dict[str, Any]:
    global _CACHE
    if _CACHE is None:
        _CACHE = _decrypt_all()
    return _CACHE


def reload() -> None:
    """Clear the in-memory cache so the next get() re-reads + re-decrypts."""
    global _CACHE, _FERNET
    _CACHE = None
    _FERNET = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def has(key: str) -> bool:
    """Return True if the key exists (does not raise)."""
    try:
        data = _ensure_cache()
    except (KeychainNotInitializedError, KeychainCorruptedError):
        return False
    return key in data


def get(key: str, default: Optional[str] = None) -> Optional[str]:
    """Return the string value for `key`, or `default` if absent."""
    data = _ensure_cache()
    if key in data:
        value = data[key]
        if value is None:
            return default
        return str(value)
    return default


def get_int(key: str, default: Optional[int] = None) -> Optional[int]:
    """Return the value as int (coerced from string if needed)."""
    raw = get(key, default=None)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError) as e:
        raise KeychainCorruptedError(
            f"keychain key {key!r} expected an int, got {raw!r}"
        ) from e


def get_list(key: str, sep: str = ",", default: Optional[list[str]] = None) -> Optional[list[str]]:
    """Return the value as a list, splitting on `sep` (default ','), trimming whitespace."""
    raw = get(key, default=None)
    if raw is None:
        return default
    items = [item.strip() for item in raw.split(sep)]
    return [item for item in items if item]


def set_value(key: str, value: str) -> None:
    """Programmatic setter used by the CLI and tests.

    Decrypts the file, applies the change, re-encrypts, and atomically writes.
    """
    if not KEY_PATH.exists() or not KEYS_PATH.exists():
        raise KeychainNotInitializedError(
            "Keychain is not initialized. Run `python -m keychain init` first."
        )

    data = dict(_ensure_cache())
    data[key] = value

    fernet = _load_fernet()
    encrypted = fernet.encrypt(json.dumps(data, indent=2, sort_keys=True).encode("utf-8"))
    envelope = {"_format": _FORMAT_VERSION, "encrypted": encrypted.decode("utf-8")}

    tmp_path = KEYS_PATH.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(envelope, indent=2, sort_keys=True))
    os.replace(tmp_path, KEYS_PATH)
    reload()


# ---------------------------------------------------------------------------
# Initialization helpers (used by the CLI)
# ---------------------------------------------------------------------------


def ensure_key_file(mode: int = 0o600) -> Path:
    """Create keychain.key with a fresh Fernet key if it doesn't exist.

    Returns the path to the key file.
    """
    if KEY_PATH.exists():
        return KEY_PATH
    KEY_PATH.write_bytes(Fernet.generate_key())
    try:
        os.chmod(KEY_PATH, mode)
    except OSError:
        # On Windows / some filesystems chmod is a no-op; that's fine.
        pass
    return KEY_PATH


def ensure_data_file(initial: Optional[dict[str, Any]] = None) -> Path:
    """Create keychain.json with an encrypted empty dict if it doesn't exist."""
    if KEYS_PATH.exists():
        return KEYS_PATH

    fernet = _load_fernet()
    payload = dict(initial or {})
    encrypted = fernet.encrypt(json.dumps(payload, indent=2, sort_keys=True).encode("utf-8"))
    envelope = {"_format": _FORMAT_VERSION, "encrypted": encrypted.decode("utf-8")}

    KEYS_PATH.write_text(json.dumps(envelope, indent=2, sort_keys=True))
    return KEYS_PATH


def is_key_file_secure(path: Optional[Path] = None) -> bool:
    """Return True if the key file is owner-readable/writable only (or on Windows).

    `path` is resolved at call time so monkeypatching `KEY_PATH` in tests works.
    """
    if path is None:
        path = KEY_PATH
    if not path.exists():
        return False
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError:
        return False
    # Accept 0o600 or stricter; on Windows this is always False.
    return (mode & 0o077) == 0
