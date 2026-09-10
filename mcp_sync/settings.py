"""Persisted user settings: which tools are enabled/disabled for sync."""
from __future__ import annotations

import json
import os
import threading
from typing import Any, Callable, Dict

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


def _load_locked() -> Dict[str, Any]:
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


def _save_locked(data: Dict[str, Any]) -> None:
    _ensure_dir()
    tmp_path = SETTINGS_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    os.replace(tmp_path, SETTINGS_PATH)


def load() -> Dict[str, Any]:
    with _lock:
        return _load_locked()


def save(data: Dict[str, Any]) -> None:
    with _lock:
        _save_locked(data)


def update(mutate: Callable[[Dict[str, Any]], None]) -> Dict[str, Any]:
    """Atomically read-modify-write the settings file: `mutate` is handed the
    current settings dict and edits it in place, all while the lock is held.

    Every caller that changes a *subset* of the settings must go through this
    rather than a bare load() ... save() pair. Those two calls each take the
    lock separately, so an interleaving thread's write to a different key is
    silently reverted by whichever save() lands last (a classic lost update).
    That is not theoretical here: a sync pass persists `last_sync_iso` and
    `known_servers_by_tool` on every run - and runs constantly, because
    watched tools rewrite their own config files on their own schedule - so a
    tool's on/off switch, flipped by the user at the wrong moment, would flip
    itself straight back on."""
    with _lock:
        data = _load_locked()
        mutate(data)
        _save_locked(data)
        return data


def is_tool_enabled(tool_name: str) -> bool:
    return tool_name not in load().get("disabled_tools", [])


def set_tool_enabled(tool_name: str, enabled: bool) -> None:
    def mutate(data: Dict[str, Any]) -> None:
        disabled = set(data.get("disabled_tools", []))
        if enabled:
            disabled.discard(tool_name)
        else:
            disabled.add(tool_name)
        data["disabled_tools"] = sorted(disabled)

    update(mutate)


def set_start_at_login(enabled: bool) -> None:
    update(lambda data: data.__setitem__("start_at_login", enabled))


def set_hide_not_installed(hidden: bool) -> None:
    update(lambda data: data.__setitem__("hide_not_installed", hidden))
