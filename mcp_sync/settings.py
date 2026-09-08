"""Persisted user settings: which tools are enabled/disabled for sync."""
from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict

from .platform_utils import home

SETTINGS_DIR = os.path.join(home(), ".mcp-sync")
SETTINGS_PATH = os.path.join(SETTINGS_DIR, "settings.json")

_lock = threading.Lock()

_DEFAULTS: Dict[str, Any] = {
    "disabled_tools": [],
    "start_at_login": True,
    "last_sync_iso": None,
    "hide_not_installed": True,
    "known_servers_by_tool": {},
}


def _ensure_dir() -> None:
    os.makedirs(SETTINGS_DIR, exist_ok=True)


def load() -> Dict[str, Any]:
    with _lock:
        _ensure_dir()
        if not os.path.exists(SETTINGS_PATH):
            return dict(_DEFAULTS)
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            return dict(_DEFAULTS)
        merged = dict(_DEFAULTS)
        merged.update(data or {})
        return merged


def save(data: Dict[str, Any]) -> None:
    with _lock:
        _ensure_dir()
        tmp_path = SETTINGS_PATH + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        os.replace(tmp_path, SETTINGS_PATH)


def is_tool_enabled(tool_name: str) -> bool:
    return tool_name not in load().get("disabled_tools", [])


def set_tool_enabled(tool_name: str, enabled: bool) -> None:
    data = load()
    disabled = set(data.get("disabled_tools", []))
    if enabled:
        disabled.discard(tool_name)
    else:
        disabled.add(tool_name)
    data["disabled_tools"] = sorted(disabled)
    save(data)


def set_start_at_login(enabled: bool) -> None:
    data = load()
    data["start_at_login"] = enabled
    save(data)


def set_hide_not_installed(hidden: bool) -> None:
    data = load()
    data["hide_not_installed"] = hidden
    save(data)
