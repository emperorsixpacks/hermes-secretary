"""Hermes Secretary plugin.

Provides async-friendly (non-blocking) tools for joining Google Meet and
capturing live captions. Long-running browser capture runs in a background
thread; tool handlers return immediately with status.

Multi-account: each account uses its own browser profile under
  <secret_root>/<account>/  (default root: ./secret relative to plugin dir)
Sign in once per account (headed), then reuse headless/headed as needed.
"""

from __future__ import annotations

import importlib.util
import json
import platform
import re
from pathlib import Path
from typing import Any, Optional

from capture import MeetCaptureManager, list_secret_accounts


def check_secretary_requirements() -> bool:
    """Passive availability probe used by Hermes (must never install).

    Returns True when the local platform/Python deps look usable. Playwright's
    Chromium browser binary may still need `hermes secretary install`.
    """
    if platform.system().lower() not in {"linux", "darwin"}:
        return False
    return importlib.util.find_spec("playwright") is not None

# Single manager per Hermes process (Hermes loads plugin once).
# One active capture at a time; account selects which saved profile to load.
_MANAGER = MeetCaptureManager()
_CTX = None


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False)


def _cfg(name: str, default: Any = None) -> Any:
    if _CTX is None:
        return default
    try:
        return _CTX.get_config(name, default)
    except Exception:
        return default


def _secret_root() -> Path:
    configured = _cfg("secret_dir", "./secret")
    base = Path(getattr(_CTX, "plugin_base_dir", Path(__file__).resolve().parent))
    p = Path(str(configured))
    if not p.is_absolute():
        p = (base / p).resolve()
    return p


def _sanitize_account(name: Optional[str]) -> Optional[str]:
    if name is None:
        return None
    cleaned = re.sub(r"[^a-zA-Z0-9._@-]+", "-", str(name).strip()).strip("-")
    return cleaned or None


def _secret_dir(account: Optional[str] = None) -> str:
    root = _secret_root()
    account = _sanitize_account(account) or _sanitize_account(_cfg("default_account"))
    if not account:
        return str(root)
    # Legacy "default" maps to root if it looks like an existing single profile.
    if account == "default":
        if any((root / n).exists() for n in ("Default", "Local State", "Preferences")) and not (root / "default").exists():
            return str(root)
    return str(root / account)


JOIN_SCHEMA = {
    "name": "secretary_join_meet",
    "description": "Join a Google Meet using a saved account profile and start caption capture in the background. Returns immediately; use secretary_status/secretary_get_transcript to monitor. First run for an account may require headed Google sign-in (headless=false).",
    "parameters": {
        "type": "object",
        "properties": {
            "meet": {"type": "string", "description": "Google Meet code (abc-defg-hij) or full https://meet.google.com/... URL."},
            "account": {"type": "string", "description": "Account/profile name under secret root (e.g. work, personal, user@example.com). Each account has its own signed-in browser session."},
            "headless": {"type": "boolean", "description": "Override headless mode (default from plugin config). Use false for first-time sign-in."},
        },
        "required": ["meet"],
    },
}

ACCOUNTS_SCHEMA = {
    "name": "secretary_list_accounts",
    "description": "List available Google account browser profiles under the Hermes Secretary secret root. Use these account names with secretary_join_meet/account.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}

STATUS_SCHEMA = {
    "name": "secretary_status",
    "description": "Get current Hermes Secretary capture status (account, state, meet, segment count, errors).",
    "parameters": {"type": "object", "properties": {}, "required": []},
}

TRANSCRIPT_SCHEMA = {
    "name": "secretary_get_transcript",
    "description": "Get captured caption transcript segments. Use limit to return only the most recent N segments.",
    "parameters": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "description": "Return only the last N segments (optional)."},
            "save": {"type": "boolean", "description": "Persist transcript to the plugin data dir (default false)."},
        },
        "required": [],
    },
}

STOP_SCHEMA = {
    "name": "secretary_stop_capture",
    "description": "Stop the active meeting caption capture. Persists the latest transcript to the plugin data dir.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}

START_SCHEMA = {
    "name": "secretary_start_capture",
    "description": "Alias of secretary_join_meet: join a meeting and start background caption capture.",
    "parameters": JOIN_SCHEMA["parameters"],
}


def secretary_list_accounts(args: dict, **kwargs) -> str:
    try:
        root = _secret_root()
        accounts = list_secret_accounts(root)
        return _json(
            {
                "ok": True,
                "secret_root": str(root),
                "accounts": accounts,
                "default_account": _sanitize_account(_cfg("default_account")),
                "usage": "Pass account to secretary_join_meet. Each account gets ./secret/<account>/ (or legacy ./secret/ as default). Sign in once with headless=false.",
            }
        )
    except Exception as e:
        return _json({"ok": False, "error": str(e)})


def secretary_join_meet(args: dict, **kwargs) -> str:
    try:
        args = args or {}
        meet = args.get("meet")
        if not meet:
            return _json({"ok": False, "error": "Missing required argument: meet"})
        account = _sanitize_account(args.get("account"))
        headless = args.get("headless")
        if headless is None:
            headless = bool(_cfg("headless", False))
        source = _cfg("capture_source", "google_meet_captions")
        if source != "google_meet_captions":
            return _json({"ok": False, "error": f"capture_source '{source}' not implemented yet; set capture_source=google_meet_captions"})
        secret_dir = _secret_dir(account)
        result = _MANAGER.start(str(meet), secret_dir=secret_dir, headless=bool(headless), account=account)
        result["account"] = account
        result["secret_dir"] = secret_dir
        result["secret_root"] = str(_secret_root())
        result["capture_source"] = source
        result["note"] = "Runs in a background thread. Poll secretary_status / secretary_get_transcript."
        return _json(result)
    except Exception as e:
        return _json({"ok": False, "error": str(e)})


def secretary_start_capture(args: dict, **kwargs) -> str:
    return secretary_join_meet(args, **kwargs)


def secretary_status(args: dict, **kwargs) -> str:
    try:
        st = _MANAGER.status()
        return _json(
            {
                "ok": True,
                "status": st,
                "secret_root": str(_secret_root()),
                "secret_dir": st.get("secret_dir") or _secret_dir(st.get("account")),
            }
        )
    except Exception as e:
        return _json({"ok": False, "error": str(e)})


def secretary_get_transcript(args: dict, **kwargs) -> str:
    try:
        args = args or {}
        result = _MANAGER.transcript(limit=args.get("limit"))
        if args.get("save") and _CTX is not None:
            try:
                data_dir = Path(_CTX.plugin_data_dir)
                path = _MANAGER.save_transcript(data_dir)
                result["saved_to"] = str(path) if path else None
            except Exception as e:
                result["save_error"] = str(e)
        return _json(result)
    except Exception as e:
        return _json({"ok": False, "error": str(e)})


def secretary_stop_capture(args: dict, **kwargs) -> str:
    try:
        result = _MANAGER.stop()
        if _CTX is not None:
            try:
                path = _MANAGER.save_transcript(Path(_CTX.plugin_data_dir))
                result["saved_to"] = str(path) if path else None
            except Exception as e:
                result["save_error"] = str(e)
        result["status"] = _MANAGER.status()
        return _json(result)
    except Exception as e:
        return _json({"ok": False, "error": str(e)})


def register(ctx) -> None:
    global _CTX
    _CTX = ctx
    tool_kwargs = dict(check_fn=check_secretary_requirements)
    ctx.register_tool(name="secretary_join_meet", toolset="hermes-secretary", schema=JOIN_SCHEMA, handler=secretary_join_meet, **tool_kwargs)
    ctx.register_tool(name="secretary_start_capture", toolset="hermes-secretary", schema=START_SCHEMA, handler=secretary_start_capture, **tool_kwargs)
    ctx.register_tool(name="secretary_list_accounts", toolset="hermes-secretary", schema=ACCOUNTS_SCHEMA, handler=secretary_list_accounts)
    ctx.register_tool(name="secretary_status", toolset="hermes-secretary", schema=STATUS_SCHEMA, handler=secretary_status)
    ctx.register_tool(name="secretary_get_transcript", toolset="hermes-secretary", schema=TRANSCRIPT_SCHEMA, handler=secretary_get_transcript)
    ctx.register_tool(name="secretary_stop_capture", toolset="hermes-secretary", schema=STOP_SCHEMA, handler=secretary_stop_capture)

    # CLI: `hermes secretary install|accounts|add-account ...`
    try:
        from cli import register_cli, handle_cli

        ctx.register_cli_command(
            name="secretary",
            help="Hermes Secretary: install, manage Meet account profiles/tags, and join/capture setup",
            description="Install prerequisites and add/list Google account browser profiles (tags) under ./secret so Secretary can join Google Meet as the right account.",
            setup_fn=register_cli,
            handler_fn=handle_cli,
        )
    except Exception as e:
        try:
            ctx.logger.warning("secretary CLI not registered: %s", e)
        except Exception:
            pass

    # Best-effort cleanup hook (Hermes google_meet uses on_session_end).
    try:
        ctx.register_hook("on_session_end", lambda **_kw: _MANAGER.stop())
    except Exception:
        pass
