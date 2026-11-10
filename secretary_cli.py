"""Hermes CLI integration for hermes-secretary.

Adds `hermes secretary ...` for installing prerequisites.
Joining is done as a guest (no Google sign-in).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

def _plugin_root() -> Path:
    return Path(__file__).resolve().parent


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


def handle_cli(args) -> int:
    handler = getattr(args, "_secretary_handler", None)
    if handler is None:
        print("Usage: hermes secretary {install} ...")
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
