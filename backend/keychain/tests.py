"""Unit tests for the keychain module."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from keychain import core
from keychain.core import (
    KEYS_PATH,
    KEY_PATH,
    KeychainCorruptedError,
    KeychainNotInitializedError,
    get,
    get_int,
    get_list,
    has,
    reload,
    set_value,
)


@pytest.fixture
def isolated_keychain(tmp_path, monkeypatch):
    """Redirect the keychain to a tmp dir for the duration of one test."""
    key_path = tmp_path / "keychain.key"
    data_path = tmp_path / "keychain.json"
    monkeypatch.setattr(core, "KEYS_PATH", data_path)
    monkeypatch.setattr(core, "KEY_PATH", key_path)
    core.reload()
    yield {"key": key_path, "data": data_path}
    core.reload()


# ---------------------------------------------------------------------------
# init / file creation
# ---------------------------------------------------------------------------


class TestInit:
    def test_init_creates_files_with_sentinels(self, isolated_keychain):
        core.ensure_key_file()
        core.ensure_data_file({})
        assert isolated_keychain["key"].exists()
        assert isolated_keychain["data"].exists()

    def test_key_file_permissions_are_600(self, isolated_keychain):
        core.ensure_key_file()
        # Skip on Windows where chmod is a no-op
        if os.name == "nt":
            return
        mode = stat.S_IMODE(isolated_keychain["key"].stat().st_mode)
        assert mode == 0o600

    def test_existing_files_are_not_overwritten(self, isolated_keychain):
        core.ensure_key_file()
        original = isolated_keychain["key"].read_bytes()
        core.ensure_key_file()
        assert isolated_keychain["key"].read_bytes() == original

    def test_is_key_file_secure(self, isolated_keychain):
        core.ensure_key_file()
        assert core.is_key_file_secure() is True

    def test_is_key_file_secure_missing(self, isolated_keychain):
        assert core.is_key_file_secure() is False


# ---------------------------------------------------------------------------
# get / set / has
# ---------------------------------------------------------------------------


class TestGetSet:
    def test_set_then_get_round_trips(self, isolated_keychain):
        core.ensure_key_file()
        core.ensure_data_file({})
        set_value("HELLO", "world")
        assert get("HELLO") == "world"

    def test_missing_key_returns_default(self, isolated_keychain):
        core.ensure_key_file()
        core.ensure_data_file({})
        assert get("ABSENT", default="fallback") == "fallback"
        assert get("ABSENT") is None

    def test_has(self, isolated_keychain):
        core.ensure_key_file()
        core.ensure_data_file({})
        set_value("PRESENT", "1")
        assert has("PRESENT") is True
        assert has("ABSENT") is False

    def test_get_int_coerces_string(self, isolated_keychain):
        core.ensure_key_file()
        core.ensure_data_file({})
        set_value("PORT", "8800")
        assert get_int("PORT") == 8800

    def test_get_int_invalid_raises(self, isolated_keychain):
        core.ensure_key_file()
        core.ensure_data_file({})
        set_value("BAD", "not-a-number")
        with pytest.raises(KeychainCorruptedError):
            get_int("BAD")

    def test_get_list_splits_on_comma(self, isolated_keychain):
        core.ensure_key_file()
        core.ensure_data_file({})
        set_value("ORIGINS", "http://a, http://b ,http://c")
        assert get_list("ORIGINS") == ["http://a", "http://b", "http://c"]


# ---------------------------------------------------------------------------
# error paths
# ---------------------------------------------------------------------------


class TestErrors:
    def test_missing_key_file(self, isolated_keychain):
        # keychain.json exists, keychain.key does not
        isolated_keychain["data"].write_text('{"_format":"fernet-v1","encrypted":"x"}')
        with pytest.raises(KeychainNotInitializedError):
            get("ANY")

    def test_missing_data_file(self, isolated_keychain):
        core.ensure_key_file()
        with pytest.raises(KeychainNotInitializedError):
            get("ANY")

    def test_tampered_blob_raises_corrupted(self, isolated_keychain):
        core.ensure_key_file()
        core.ensure_data_file({"FOO": "bar"})
        core.reload()
        envelope = json.loads(isolated_keychain["data"].read_text())
        envelope["encrypted"] = envelope["encrypted"][:-4] + "AAAA"
        isolated_keychain["data"].write_text(json.dumps(envelope))
        core.reload()
        with pytest.raises(KeychainCorruptedError):
            get("FOO")

    def test_wrong_key_raises_corrupted(self, isolated_keychain):
        core.ensure_key_file()
        core.ensure_data_file({"FOO": "bar"})
        # Replace the key with a different valid Fernet key
        isolated_keychain["key"].write_bytes(Fernet.generate_key())
        core.reload()
        with pytest.raises(KeychainCorruptedError):
            get("FOO")

    def test_bad_envelope_format(self, isolated_keychain):
        core.ensure_key_file()
        core.ensure_data_file({"FOO": "bar"})
        core.reload()
        isolated_keychain["data"].write_text(json.dumps({"foo": "bar"}))
        core.reload()
        with pytest.raises(KeychainCorruptedError):
            get("ANY")

    def test_invalid_json_envelope(self, isolated_keychain):
        core.ensure_key_file()
        isolated_keychain["data"].write_text("not json at all")
        with pytest.raises(KeychainCorruptedError):
            get("ANY")

    def test_invalid_key_bytes(self, isolated_keychain):
        # Both files exist but key is garbage
        core.ensure_key_file()
        core.ensure_data_file({"FOO": "bar"})
        core.reload()
        isolated_keychain["key"].write_bytes(b"not-a-fernet-key")
        core.reload()
        with pytest.raises(KeychainCorruptedError):
            get("ANY")


# ---------------------------------------------------------------------------
# reload / cache invalidation
# ---------------------------------------------------------------------------


class TestReload:
    def test_reload_picks_up_external_changes(self, isolated_keychain):
        core.ensure_key_file()
        core.ensure_data_file({"X": "1"})
        assert get("X") == "1"

        # Mutate the file out-of-band (simulate another process)
        core.set_value("X", "2")  # this also reloads
        assert get("X") == "2"

        core.reload()
        assert get("X") == "2"


# ---------------------------------------------------------------------------
# atomic write
# ---------------------------------------------------------------------------


class TestAtomicWrite:
    def test_set_writes_valid_envelope(self, isolated_keychain):
        core.ensure_key_file()
        core.ensure_data_file({})
        set_value("K", "v")
        envelope = json.loads(isolated_keychain["data"].read_text())
        assert envelope["_format"] == "fernet-v1"
        assert isinstance(envelope["encrypted"], str)
        assert "encrypted" in envelope

    def test_no_tmp_file_left_behind(self, isolated_keychain):
        core.ensure_key_file()
        core.ensure_data_file({})
        set_value("K", "v")
        assert not (isolated_keychain["data"].parent / "keychain.json.tmp").exists()
