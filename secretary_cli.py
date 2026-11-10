"""Hermes CLI integration for hermes-secretary.

Adds `hermes secretary ...` for installing prerequisites and listing saved profiles.
Joining is done as a guest (no Google sign-in).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

try:
    from .secretary_capture import list_secret_accounts
except ImportError:
    from secretary_capture import list_secret_accounts


def _plugin_root() -> Path:
    return Path(__file__).resolve().parent


def _secret_root(args) -> Path:
    configured = getattr(args, "secret_dir", None) or "./secret"
    p = Path(str(configured))
    if not p.is_absolute():
        p = (_plugin_root() / p).resolve()
    return p


def _print(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _sanitize_account(name: Optional[str]) -> Optional[str]:
    if name is None:
        return None
    import re

    cleaned = re.sub(r"[^a-zA-Z0-9._@-]+", "-", str(name).strip()).strip("-")
    return cleaned or None


def cmd_accounts(args) -> int:
    root = _secret_root(args)
    _print(
        {
            "ok": True,
            "secret_root": str(root),
            "accounts": list_secret_accounts(root),
            "usage": "Join as a guest: secretary_join_meet with guest_name (no sign-in needed).",
        }
    )
    return 0


def cmd_install(args) -> int:
    """Install/check Secretary runtime prerequisites (Hermes-friendly setup step)."""
    root = _plugin_root()
    setup = root / "setup.sh"
    if setup.exists():
        print("Running Secretary setup (Python deps + Playwright Chromium + Hermes plugin link)...")
        code = subprocess.call(["bash", str(setup)])
        _print({"ok": code == 0, "ran": str(setup), "plugin_root": str(root)})
        return 0 if code == 0 else 1

    # Fallback if setup.sh is unavailable.
    print("setup.sh not found; installing minimal prerequisites with Python Playwright...")
    code = subprocess.call([sys.executable, "-m", "pip", "install", "playwright>=1.40"])
    if code == 0:
        code = subprocess.call([sys.executable, "-m", "playwright", "install", "chromium"])
    _print({"ok": code == 0, "plugin_root": str(root)})
    return 0 if code == 0 else 1


def register_cli(subparser) -> None:
    """Set up `hermes secretary` argparse subcommands."""
    sub = subparser.add_subparsers(dest="secretary_cmd")

    p_install = sub.add_parser("install", help="Install Secretary prerequisites (Playwright + Chromium) and link plugin")
    p_install.set_defaults(_secretary_handler=cmd_install)

    p_accounts = sub.add_parser("accounts", help="List saved account/profile tags under the secret root")
    p_accounts.add_argument("--secret-dir", default="./secret", help="Secret root (relative to plugin dir or absolute)")
    p_accounts.set_defaults(_secretary_handler=cmd_accounts)


def handle_cli(args) -> int:
    handler = getattr(args, "_secretary_handler", None)
    if handler is None:
        print("Usage: hermes secretary {install|accounts} ...")
        return 2
    return int(handler(args) or 0)

def main(argv: Optional[list[str]] = None) -> int:
    """Standalone entrypoint (works without Hermes)."""
    import argparse

    parser = argparse.ArgumentParser(prog="hermes-secretary", description="Hermes Secretary local helper")
    register_cli(parser)
    args = parser.parse_args(argv)
    return handle_cli(args)


if __name__ == "__main__":
    raise SystemExit(main())
