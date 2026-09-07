"""Core merge/sync logic: reads every enabled+detected tool's MCP servers,
merges them (most recently modified file wins per server name), and writes
the merged set back to every enabled+detected tool - only touching files
whose content actually needs to change."""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import settings
from .tools_registry import REGISTRY, ServerMap, ToolSpec

_sync_lock = threading.Lock()
_last_sync_end_ts = 0.0


def seconds_since_last_sync() -> float:
    return time.time() - _last_sync_end_ts


@dataclass
class ToolStatus:
    name: str
    installed: bool
    enabled: bool
    server_count: int
    in_sync: bool
    path: str


@dataclass
class SyncResult:
    changed_tools: List[str] = field(default_factory=list)
    statuses: List[ToolStatus] = field(default_factory=list)
    merged_server_names: List[str] = field(default_factory=list)
    error: Optional[str] = None


def _enabled_detected_tools() -> List[ToolSpec]:
    cfg = settings.load()
    disabled = set(cfg.get("disabled_tools", []))
    return [t for t in REGISTRY.values() if t.name not in disabled and t.is_present()]


def _safe_read(tool: ToolSpec) -> ServerMap:
    try:
        return tool.adapter.read(tool.resolved_path())
    except Exception:
        return {}


def merge_servers(tools: List[ToolSpec]) -> Dict[str, dict]:
    """Union of all servers across tools; on name collisions, the version
    from the most recently modified file wins."""
    best: Dict[str, dict] = {}
    best_mtime: Dict[str, float] = {}

    for tool in tools:
        path = tool.resolved_path()
        try:
            mtime = os.path.getmtime(path) if os.path.exists(path) else 0.0
        except OSError:
            mtime = 0.0
        servers = _safe_read(tool)
        for name, cfg in servers.items():
            if name not in best or mtime >= best_mtime.get(name, -1):
                best[name] = cfg
                best_mtime[name] = mtime

    return best


def run_sync() -> SyncResult:
    """Perform one full sync pass across all enabled + detected tools."""
    global _last_sync_end_ts
    with _sync_lock:
        result = SyncResult()
        try:
            tools = _enabled_detected_tools()
            merged = merge_servers(tools)
            result.merged_server_names = sorted(merged.keys())

            for tool in tools:
                current = _safe_read(tool)
                if current != merged:
                    try:
                        tool.adapter.write(tool.resolved_path(), merged)
                        result.changed_tools.append(tool.name)
                    except Exception as exc:  # keep going for other tools
                        result.error = f"{tool.name}: {exc}"

            if result.changed_tools:
                data = settings.load()
                import datetime

                data["last_sync_iso"] = datetime.datetime.now().isoformat(timespec="seconds")
                settings.save(data)

            result.statuses = build_statuses(merged)
        except Exception as exc:
            result.error = str(exc)
        finally:
            _last_sync_end_ts = time.time()
        return result


def build_statuses(merged: Optional[Dict[str, dict]] = None) -> List[ToolStatus]:
    cfg = settings.load()
    disabled = set(cfg.get("disabled_tools", []))
    if merged is None:
        merged = merge_servers(_enabled_detected_tools())

    statuses: List[ToolStatus] = []
    for tool in REGISTRY.values():
        installed = tool.is_present()
        enabled = tool.name not in disabled
        current = _safe_read(tool) if installed else {}
        in_sync = installed and enabled and current == merged
        statuses.append(
            ToolStatus(
                name=tool.name,
                installed=installed,
                enabled=enabled,
                server_count=len(current),
                in_sync=in_sync,
                path=tool.resolved_path(),
            )
        )
    return statuses


def watched_paths() -> List[str]:
    """Paths of enabled+installed tools, for the file watcher."""
    return [t.resolved_path() for t in _enabled_detected_tools()]


def all_registry_paths() -> List[str]:
    """Every known tool path (installed or not), so the watcher also notices
    a config file being created for the first time."""
    return [t.resolved_path() for t in REGISTRY.values()]
