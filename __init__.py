"""Hermes Secretary plugin.

Provides async-friendly (non-blocking) tools for joining Google Meet and
capturing live captions. Long-running browser capture runs in a background
thread; tool handlers return immediately with status.

Joins as an anonymous guest (Google blocks automated sign-in); the host admits the bot.
"""

from __future__ import annotations

import importlib.util
import json
import platform
import re
from pathlib import Path
from typing import Any, Optional

try:  # loaded by Hermes as a package (directory plugin)
    from .secretary_capture import MeetCaptureManager
except ImportError:  # loaded as a plain script/module from the check-out
    from secretary_capture import MeetCaptureManager


def check_secretary_requirements() -> bool:
    """Passive availability probe used by Hermes (must never install).

    Returns True when the local platform/Python deps look usable. Playwright's
    Chromium browser binary may still need `hermes secretary install`.
    """
    if platform.system().lower() not in {"linux", "darwin"}:
        return False
    return importlib.util.find_spec("playwright") is not None

# Single manager per Hermes process (Hermes loads plugin once).
# One active capture at a time.
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


JOIN_SCHEMA = {
    "name": "secretary_join_meet",
    "description": "Join a Google Meet as a guest and start caption capture in the background. Returns immediately; use secretary_status/secretary_get_transcript to monitor. Google blocks automated sign-in, so the bot joins anonymously and the host must admit it.",
    "parameters": {
        "type": "object",
        "properties": {
            "meet": {"type": "string", "description": "Google Meet code (abc-defg-hij) or full https://meet.google.com/... URL."},
            "guest_name": {"type": "string", "description": "Display name shown in the meeting. Defaults to "<OS username>'s Secretary"."},
            "headless": {"type": "boolean", "description": "Override headless mode (default from plugin config)."},
        },
        "required": ["meet"],
    },
}

STATUS_SCHEMA = {
    "name": "secretary_status",
    "description": "Get current Hermes Secretary capture status (state, meet, segment count, errors).",
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


def secretary_join_meet(args: dict, **kwargs) -> str:
    try:
        args = args or {}
        meet = args.get("meet")
        if not meet:
            return _json({"ok": False, "error": "Missing required argument: meet"})
        headless = args.get("headless")
        if headless is None:
            headless = bool(_cfg("headless", False))
        source = _cfg("capture_source", "google_meet_captions")
        if source != "google_meet_captions":
            return _json({"ok": False, "error": f"capture_source '{source}' not implemented yet; set capture_source=google_meet_captions"})
        result = _MANAGER.start(str(meet), headless=bool(headless), guest_name=(str(args.get("guest_name") or "").strip() or None))
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
    ctx.register_tool(name="secretary_status", toolset="hermes-secretary", schema=STATUS_SCHEMA, handler=secretary_status)
    ctx.register_tool(name="secretary_get_transcript", toolset="hermes-secretary", schema=TRANSCRIPT_SCHEMA, handler=secretary_get_transcript)
    ctx.register_tool(name="secretary_stop_capture", toolset="hermes-secretary", schema=STOP_SCHEMA, handler=secretary_stop_capture)

    # CLI: `hermes secretary install ...`
    try:
        try:
            from .secretary_cli import register_cli, handle_cli
        except ImportError:
            from secretary_cli import register_cli, handle_cli

        ctx.register_cli_command(
            name="secretary",
            help="Hermes Secretary: install prerequisites for Meet guest capture",
            description="Install Playwright and Chromium so Secretary can join Google Meet as a guest.",
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
