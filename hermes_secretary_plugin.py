"""Package entrypoint for pip-installed Hermes Secretary.

Hermes native/local plugins load `__init__.py` via plugin discovery; this module
provides the same `register()` surface for pip entry-point loading.
"""

from __future__ import annotations

try:
    # When loaded as part of the local plugin directory.
    from __init__ import register as register  # type: ignore
except Exception:  # pragma: no cover
    # Fallback for package-style installs.
    from capture import MeetCaptureManager  # noqa: F401

    def register(ctx):  # type: ignore
        raise RuntimeError(
            "Hermes Secretary package entrypoint could not load local register(). "
            "Install/use the plugin directory form or ensure package modules are present."
        )


def capabilities():
    return []
