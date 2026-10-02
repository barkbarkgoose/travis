"""
Command-line interface for the keychain.

Usage:
    python -m keychain init                              # create keychain.{json,key}
    python -m keychain init --from-example               # seed from keychain.example.json
    python -m keychain set KEY=VALUE [KEY=VALUE ...]      # set one or more values
    python -m keychain get KEY                            # print a single value
    python -m keychain list                              # list key names (no values)
    python -m keychain rotate-key                         # generate a new key, re-encrypt
    python -m keychain doctor                            # check files + permissions
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

from cryptography.fernet import Fernet

from . import core
from .core import (
    KEYS_PATH,
    KEY_PATH,
    KeychainCorruptedError,
    KeychainNotInitializedError,
    get,
    has,
    reload,
    set_value,
)


def _cmd_init(args: argparse.Namespace) -> int:
    if not args.force and (KEY_PATH.exists() or KEYS_PATH.exists()):
        print(
            f"refusing to overwrite existing files:\n  {KEY_PATH}\n  {KEYS_PATH}\n"
            "Re-run with --force to overwrite.",
            file=sys.stderr,
        )
        return 1

    if not KEY_PATH.exists():
        core.ensure_key_file()
        print(f"created {KEY_PATH} (mode 0600)")

    if not KEYS_PATH.exists():
        initial: Dict[str, Any] = {}
        if args.from_example:
            # Look for the example next to the package (so it ships with the
            # keychain module rather than floating in backend/).
            example_path = core.PACKAGE_DIR / "example.json"
            if example_path.exists():
                initial = json.loads(example_path.read_text())
                print(f"seeded {KEYS_PATH} from {example_path}")
            else:
                print(
                    f"warning: {example_path} not found, starting empty",
                    file=sys.stderr,
                )
        core.ensure_data_file(initial)
        print(f"created {KEYS_PATH}")

    core.reload()
    return 0


def _cmd_set(args: argparse.Namespace) -> int:
    if not args.pairs:
        print("error: at least one KEY=VALUE pair is required", file=sys.stderr)
        return 2
    try:
        for pair in args.pairs:
            if "=" not in pair:
                print(f"error: malformed argument {pair!r} (expected KEY=VALUE)", file=sys.stderr)
                return 2
            key, value = pair.split("=", 1)
            set_value(key.strip(), value)
            print(f"set {key.strip()}")
    except KeychainNotInitializedError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except KeychainCorruptedError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


def _cmd_get(args: argparse.Namespace) -> int:
    try:
        value = get(args.key)
    except KeychainNotInitializedError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except KeychainCorruptedError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if value is None:
        print(f"key {args.key!r} not set (and no default)", file=sys.stderr)
        return 1
    sys.stdout.write(value)
    if not value.endswith("\n"):
        sys.stdout.write("\n")
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    try:
        data = core._ensure_cache()
    except KeychainNotInitializedError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except KeychainCorruptedError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    for key in sorted(data):
        print(key)
    return 0


def _cmd_rotate_key(args: argparse.Namespace) -> int:
    try:
        existing = core._decrypt_all()
    except (KeychainNotInitializedError, KeychainCorruptedError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    new_key = Fernet.generate_key()
    KEY_PATH.write_bytes(new_key)
    try:
        os.chmod(KEY_PATH, 0o600)
    except OSError:
        pass

    fernet = Fernet(new_key)
    encrypted = fernet.encrypt(json.dumps(existing, indent=2, sort_keys=True).encode("utf-8"))
    envelope = {"_format": core._FORMAT_VERSION, "encrypted": encrypted.decode("utf-8")}
    tmp_path = KEYS_PATH.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(envelope, indent=2, sort_keys=True))
    os.replace(tmp_path, KEYS_PATH)
    reload()

    print(f"rotated keychain.key; {KEYS_PATH} re-encrypted with the new key")
    return 0


def _cmd_doctor(_args: argparse.Namespace) -> int:
    ok = True
    if KEY_PATH.exists():
        secure = core.is_key_file_secure()
        mode = oct(KEY_PATH.stat().st_mode & 0o777)
        status = "ok" if secure else "WARN: too permissive"
        print(f"  {KEY_PATH}  ({mode})  {status}")
        if not secure:
            ok = False
    else:
        print(f"  {KEY_PATH}  MISSING (run `python -m keychain init`)")
        ok = False

    if KEYS_PATH.exists():
        try:
            keys = list(core._decrypt_all().keys())
            print(f"  {KEYS_PATH}  ({len(keys)} keys)  ok")
        except KeychainCorruptedError as e:
            print(f"  {KEYS_PATH}  CORRUPTED: {e}")
            ok = False
    else:
        print(f"  {KEYS_PATH}  MISSING (run `python -m keychain init`)")
        ok = False

    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m keychain",
        description="Encrypted-config keychain for user-defined values.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Create keychain.key and keychain.json")
    p_init.add_argument("--from-example", action="store_true",
                        help="Seed initial values from keychain.example.json")
    p_init.add_argument("--force", action="store_true",
                        help="Overwrite existing files")
    p_init.set_defaults(func=_cmd_init)

    p_set = sub.add_parser("set", help="Set one or more KEY=VALUE pairs")
    p_set.add_argument("pairs", nargs="+", help="KEY=VALUE pairs")
    p_set.set_defaults(func=_cmd_set)

    p_get = sub.add_parser("get", help="Print the value for KEY")
    p_get.add_argument("key")
    p_get.set_defaults(func=_cmd_get)

    p_list = sub.add_parser("list", help="List all key names (no values)")
    p_list.set_defaults(func=_cmd_list)

    p_rotate = sub.add_parser("rotate-key", help="Generate a new key and re-encrypt")
    p_rotate.set_defaults(func=_cmd_rotate_key)

    p_doctor = sub.add_parser("doctor", help="Check files and permissions")
    p_doctor.set_defaults(func=_cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
