"""MCP Sync - keeps MCP server configuration in sync across AI coding tools."""
from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

_FALLBACK_VERSION = "0.0.1"  # keep in sync with pyproject.toml's `version =`


def _resolve_version() -> str:
    try:
        return _pkg_version("mcp-sync-tray")
    except PackageNotFoundError:
        return _FALLBACK_VERSION


__version__ = _resolve_version()
