"""Hermes CLI integration for hermes-secretary.

Adds `hermes secretary ...` so users can add/manage account profiles (tags)
and sign in with a headed browser before joining meetings.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from capture import list_secret_accounts


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
            "usage": "Add/sign in: hermes secretary add-account <tag> --headless=false",
        }
    )
    return 0


def cmd_add_account(args) -> int:
    """Open a persistent browser profile for an account tag so the user can sign in."""
    root = _secret_root(args)
    account = _sanitize_account(getattr(args, "account", None))
    if not account:
        print("Error: account/tag name is required (e.g. work, personal, user@example.com).", file=sys.stderr)
        return 2
    if account == "default" and any((root / n).exists() for n in ("Default", "Local State", "Preferences")) and not (root / "default").exists():
        profile_dir = root
    else:
        profile_dir = root / account
    profile_dir.mkdir(parents=True, exist_ok=True)

    headless = bool(getattr(args, "headless", False))
    url = getattr(args, "url", None) or "https://accounts.google.com/"
    print(f"Account tag: {account}")
    print(f"Profile dir: {profile_dir}")
    print(f"Headless: {headless}")
    if headless:
        print("Warning: headless sign-in is usually not possible. Re-run with --headless=false.", file=sys.stderr)
    print(f"Opening: {url}")
    print("Sign in with the Google account you want to use for this tag, then close the browser window.")
    print("Tip: if joining Meet, also visit https://meet.google.com/ while signed in to confirm access.\n")

    # Prefer Python Playwright (matches Hermes plugin capture path). Fallback to npx playwright.
    code = _launch_with_python_playwright(str(profile_dir), url, headless=headless)
    if code != 0:
        code = _launch_with_npx_playwright(str(profile_dir), url, headless=headless)

    _print({"ok": code == 0, "account": account, "profile_dir": str(profile_dir), "secret_root": str(root)})
    return 0 if code == 0 else 1


def _launch_with_python_playwright(profile_dir: str, url: str, *, headless: bool) -> int:
    script = r'''
import sys
from playwright.sync_api import sync_playwright
profile_dir, url, headless = sys.argv[1], sys.argv[2], sys.argv[3] == "1"
with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        profile_dir,
        headless=headless,
        viewport={"width": 1280, "height": 720},
        args=["--no-sandbox","--disable-setuid-sandbox"] if headless else [],
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    print("Browser open. Complete sign-in, then close the window (or press Ctrl+C here).")
    try:
        page.wait_for_timeout(10 * 60 * 1000)
    except Exception:
        pass
    try:
        ctx.close()
    except Exception:
        pass
'''
    try:
        return subprocess.call([sys.executable, "-c", script, profile_dir, url, "1" if headless else "0"])
    except Exception as e:
        print(f"Python Playwright launch unavailable: {e}", file=sys.stderr)
        return 1



def _launch_with_npx_playwright(profile_dir: str, url: str, *, headless: bool) -> int:
    # Best-effort fallback: open via node/playwright CLI isn't a direct profile-login flow.
    # Advise user to install playwright in the active environment.
    print(
        "Could not launch with Python Playwright. Install deps: pip install playwright && playwright install chromium",
        file=sys.stderr,
    )
    return 1


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

    p_add = sub.add_parser("add-account", help="Open a browser profile to sign in and save an account tag")
    p_add.add_argument("account", help="Account tag/name (e.g. work, personal, user@example.com)")
    p_add.add_argument("--secret-dir", default="./secret", help="Secret root (relative to plugin dir or absolute)")
    p_add.add_argument("--headless", action="store_true", help="Headless (not recommended for sign-in)")
    p_add.add_argument("--url", default="https://accounts.google.com/", help="URL to open for sign-in")
    p_add.set_defaults(_secretary_handler=cmd_add_account)


def handle_cli(args) -> int:
    handler = getattr(args, "_secretary_handler", None)
    if handler is None:
        print("Usage: hermes secretary {install|accounts|add-account} ...")
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
