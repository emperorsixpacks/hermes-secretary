"""Pip entry-point shim for Hermes Secretary.

The real implementation lives in `__init__.py` (directory-plugin form). This shim
loads it by path as a proper package so relative imports work, and re-exports
`register` / `capabilities`.

pyproject.toml entry points:
    hermes_agent.plugins -> hermes_secretary_plugin:register
    hermes_agent.plugin_capabilities -> hermes_secretary_plugin:capabilities
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent
_NAME = "_hermes_secretary_impl"

try:
    _mod = sys.modules.get(_NAME)
    if _mod is None:
        _spec = importlib.util.spec_from_file_location(
            _NAME, _DIR / "__init__.py", submodule_search_locations=[str(_DIR)]
        )
        _mod = importlib.util.module_from_spec(_spec)
        sys.modules[_NAME] = _mod
        _spec.loader.exec_module(_mod)
    register = _mod.register
except Exception as _e:  # pragma: no cover
    sys.modules.pop(_NAME, None)
    _err = _e

    def register(ctx):  # type: ignore
        raise RuntimeError(f"Hermes Secretary failed to load: {_err}")


def capabilities() -> list:
    return []
