#!/usr/bin/env python3
"""Run the Django and Vite development servers together."""

from __future__ import annotations

import os
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"
ENV_PATH = BACKEND_DIR / ".env"
ENV_EXAMPLE_PATH = BACKEND_DIR / ".env.example"

# Read defaults from the encrypted keychain (DEV_BACKEND_PORT_DEFAULT /
# DEV_FRONTEND_PORT_DEFAULT). Fall back to the bundled defaults if the
# keychain has not been initialized yet so first-time setup is friendly.
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from keychain import (  # noqa: E402
    KeychainNotInitializedError,
    get as keychain_get,
    get_int as keychain_get_int,
)


def _keychain_int(key: str, fallback: int) -> int:
    """Read an int from the keychain, returning ``fallback`` when unavailable."""
    try:
        value = keychain_get_int(key, default=fallback)
    except KeychainNotInitializedError:
        return fallback
    return value if value is not None else fallback


DEFAULT_BACKEND_PORT = _keychain_int("DEV_BACKEND_PORT_DEFAULT", 8800)
DEFAULT_FRONTEND_PORT = _keychain_int("DEV_FRONTEND_PORT_DEFAULT", 5177)

# ANSI color codes for clean terminal output
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
MAGENTA = "\033[95m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

# Values that look set but are really the bundled placeholders.
PLACEHOLDER_SECRET_KEYS = {"", "change-me-in-production", "change-me"}

_SECRET_KEY_HELP = (
    "Set SECRET_KEY in backend/.env, export it in your shell, or store it in the\n"
    "keychain with `python -m keychain set SECRET_KEY=<value>`."
)


def _dotenv_values(path: Path) -> dict[str, str]:
    """Parse a dotenv file into a dict, ignoring comments and blank lines."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _upsert_env_value(path: Path, key: str, value: str) -> None:
    """Set ``key=value`` in a dotenv file, preserving all other lines."""
    lines = path.read_text().splitlines() if path.exists() else []

    prefix = f"{key}="
    for index, line in enumerate(lines):
        if line.strip().startswith(prefix):
            lines[index] = f"{key}={value}"
            break
    else:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"{key}={value}")

    path.write_text("\n".join(lines) + "\n")


def _secret_key_from_keychain() -> str | None:
    """Read SECRET_KEY from the encrypted keychain, if it is initialized."""
    try:
        return keychain_get("SECRET_KEY")
    except KeychainNotInitializedError:
        return None


def _resolve_secret_key() -> str | None:
    """Return the first usable SECRET_KEY, mirroring the settings precedence.

    Checks the shell environment, then the keychain, then ``backend/.env``.
    Placeholder values (e.g. the one shipped in ``.env.example``) count as
    unset so a fresh checkout is prompted to generate a real key.
    """
    candidates = (
        os.environ.get("SECRET_KEY"),
        _secret_key_from_keychain(),
        _dotenv_values(ENV_PATH).get("SECRET_KEY"),
    )
    for candidate in candidates:
        if candidate and candidate not in PLACEHOLDER_SECRET_KEYS:
            return candidate
    return None


def ensure_secret_key() -> bool:
    """Guarantee a usable SECRET_KEY before Django starts.

    If the setting is missing or still a placeholder, prompt the developer to
    generate one and persist it to ``backend/.env`` (creating the file from
    ``.env.example`` when needed). Set ``DEV_GENERATE_SECRET_KEY=1`` to generate
    without prompting (useful for CI/devcontainers). Returns False when no key
    is available and the user declines or the session is non-interactive.
    """
    if _resolve_secret_key():
        return True

    print(f"{YELLOW}[Setup] SECRET_KEY is not set.{RESET}")
    print("Django requires a unique SECRET_KEY for local development.")

    auto_generate = os.environ.get("DEV_GENERATE_SECRET_KEY", "").lower() in {
        "1",
        "true",
        "yes",
    }
    if not auto_generate:
        if not sys.stdin.isatty():
            print(_SECRET_KEY_HELP)
            return False
        answer = input("Generate one and save it to backend/.env now? [Y/n]: ")
        if answer.strip().lower() not in ("", "y", "yes"):
            print(_SECRET_KEY_HELP)
            return False

    if not ENV_PATH.exists() and ENV_EXAMPLE_PATH.exists():
        ENV_PATH.write_text(ENV_EXAMPLE_PATH.read_text())
        ENV_PATH.chmod(0o600)

    secret_key = secrets.token_urlsafe(64)
    _upsert_env_value(ENV_PATH, "SECRET_KEY", secret_key)
    os.environ["SECRET_KEY"] = secret_key
    print(f"{GREEN}[Setup]{RESET} Generated SECRET_KEY and saved it to {ENV_PATH}.")
    return True


def is_port_available(port: int, host: str = "127.0.0.1") -> bool:
    """Return whether a TCP port is free to bind on ``host``."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def find_next_available_port(
    start_port: int, max_attempts: int = 50, host: str = "127.0.0.1"
) -> int:
    """Return the first free port at or above ``start_port``."""
    for port in range(start_port, start_port + max_attempts):
        if is_port_available(port, host):
            return port
    raise RuntimeError(
        f"Could not find an available port in range {start_port}-{start_port + max_attempts}"
    )


def stream_logs(process: subprocess.Popen, prefix: str, color: str) -> None:
    """Stream a child process's combined output with an identifiable prefix."""
    try:
        assert process.stdout is not None
        for line in iter(process.stdout.readline, ""):
            if not line:
                break
            print(f"{color}{BOLD}[{prefix}]{RESET} {line}", end="", flush=True)
    except Exception:
        pass


def get_python_executable() -> str:
    """Return the project virtualenv Python, falling back to ``sys.executable``."""
    venv_python = ROOT_DIR / ".venv" / "bin" / "python3"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def _backend_environment(frontend_port: int) -> dict[str, str]:
    """Build the Django environment, wiring CORS to the discovered ports.

    Combines (a) ``DEV_CORS_ORIGINS`` from the keychain, (b) the runtime
    frontend port so the proxy origin is always allowed, and (c) whatever the
    shell already exports.
    """
    backend_env = os.environ.copy()
    backend_env["DJANGO_SETTINGS_MODULE"] = "config.settings.local"
    backend_env["PYTHONUNBUFFERED"] = "1"

    from keychain import get_list as keychain_get_list  # local import

    try:
        keychain_origins = keychain_get_list("DEV_CORS_ORIGINS", default=[]) or []
    except KeychainNotInitializedError:
        keychain_origins = []

    runtime_origins = [
        f"http://localhost:{frontend_port}",
        f"http://127.0.0.1:{frontend_port}",
    ]
    backend_env["CORS_ALLOWED_ORIGINS"] = ",".join(
        dict.fromkeys([*keychain_origins, *runtime_origins])
    )
    return backend_env


def run_migrations(python_bin: str, backend_env: dict[str, str]) -> int:
    """Apply pending migrations, returning a non-zero code on failure."""
    print(f"\n{MAGENTA}[Setup]{RESET} Checking database migrations...")
    try:
        subprocess.run(
            [python_bin, "manage.py", "migrate", "--no-input"],
            cwd=BACKEND_DIR,
            env=backend_env,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        print(f"{RED}[Setup] Migration failed with exit code {error.returncode}.{RESET}")
        if error.stderr:
            print(error.stderr.rstrip())
        return error.returncode
    print(f"{GREEN}[Setup]{RESET} Database is up-to-date.")
    return 0


def main() -> int:
    project_name = ROOT_DIR.name.replace("-", " ").replace("_", " ").title()
    print(f"{CYAN}{BOLD}===================================================={RESET}")
    print(f"{CYAN}{BOLD}   {project_name} - Full Stack Dev Runner{RESET}")
    print(f"{CYAN}{BOLD}===================================================={RESET}\n")

    backend_port = find_next_available_port(DEFAULT_BACKEND_PORT)
    frontend_port = find_next_available_port(DEFAULT_FRONTEND_PORT)

    if backend_port != DEFAULT_BACKEND_PORT:
        print(
            f"{YELLOW}* Default backend port {DEFAULT_BACKEND_PORT} is in use; "
            f"using {backend_port}.{RESET}"
        )
    if frontend_port != DEFAULT_FRONTEND_PORT:
        print(
            f"{YELLOW}* Default frontend port {DEFAULT_FRONTEND_PORT} is in use; "
            f"using {frontend_port}.{RESET}"
        )

    if not ensure_secret_key():
        return 1

    python_bin = get_python_executable()
    backend_env = _backend_environment(frontend_port)

    migration_code = run_migrations(python_bin, backend_env)
    if migration_code != 0:
        return migration_code

    backend_url = f"http://127.0.0.1:{backend_port}"
    frontend_url = f"http://localhost:{frontend_port}"

    frontend_env = os.environ.copy()
    frontend_env["PORT"] = str(frontend_port)
    frontend_env["VITE_API_URL"] = backend_url
    frontend_env["VITE_BACKEND_TARGET"] = backend_url

    processes: list[subprocess.Popen] = []

    def shutdown_processes(*_args: object) -> None:
        print(f"\n{YELLOW}[Shutdown] Stopping servers...{RESET}")
        for process in processes:
            if process.poll() is None:
                process.terminate()
        time.sleep(0.5)
        for process in processes:
            if process.poll() is None:
                process.kill()
        print(f"{GREEN}[Shutdown] Done.{RESET}")
        raise SystemExit(0)

    signal.signal(signal.SIGINT, shutdown_processes)
    signal.signal(signal.SIGTERM, shutdown_processes)

    print(f"\n{GREEN}{BOLD}Starting Django backend at {backend_url}{RESET}")
    backend_process = subprocess.Popen(
        [python_bin, "manage.py", "runserver", f"127.0.0.1:{backend_port}"],
        cwd=BACKEND_DIR,
        env=backend_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    processes.append(backend_process)

    print(f"{CYAN}{BOLD}Starting Vite frontend at {frontend_url}{RESET}")
    frontend_process = subprocess.Popen(
        ["pnpm", "run", "dev", "--port", str(frontend_port), "--host"],
        cwd=FRONTEND_DIR,
        env=frontend_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    processes.append(frontend_process)

    threading.Thread(
        target=stream_logs, args=(backend_process, "Django", GREEN), daemon=True
    ).start()
    threading.Thread(
        target=stream_logs, args=(frontend_process, "Vue", CYAN), daemon=True
    ).start()

    print(f"{BOLD}Press Ctrl+C to stop both servers.{RESET}\n")

    try:
        while True:
            for process, name in ((backend_process, "Django"), (frontend_process, "Vue")):
                return_code = process.poll()
                if return_code is not None:
                    print(f"{RED}[{name}] Process exited with code {return_code}.{RESET}")
                    shutdown_processes()
            time.sleep(0.5)
    except KeyboardInterrupt:
        shutdown_processes()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
