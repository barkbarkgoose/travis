"""
Encrypted-config keychain for user-defined values.

Secrets and user-tunable values live in `keychain.json` (encrypted blob) and are
decrypted at runtime using the Fernet key stored in `keychain.key`. Both files
live in the same directory as this package (`backend/`).

Quick start:
    cd backend
    python -m keychain init
    python -m keychain set SECRET_KEY='replace-with-a-unique-secret'
    python -m keychain get SECRET_KEY

Public API:
    get(key, default=None) -> str
    get_int(key, default=None) -> int
    get_list(key, sep=",", default=None) -> list[str]
    has(key) -> bool
    set(key, value)  # programmatic, used by CLI and tests
    reload()         # clear the in-memory cache
"""

from __future__ import annotations

from .core import (
    KEY_PATH,
    KEYS_PATH,
    KeychainCorruptedError,
    KeychainKeyError,
    KeychainNotInitializedError,
    get,
    get_int,
    get_list,
    has,
    reload,
    set_value,
)

__all__ = [
    "KEY_PATH",
    "KEYS_PATH",
    "KeychainCorruptedError",
    "KeychainKeyError",
    "KeychainNotInitializedError",
    "get",
    "get_int",
    "get_list",
    "has",
    "reload",
    "set_value",
]
