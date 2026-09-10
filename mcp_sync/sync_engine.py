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

from . import backup as backup_mod
from . import settings
from .tools_registry import REGISTRY, ServerMap, ToolSpec

_sync_lock = threading.Lock()
_last_sync_end_ts = 0.0
_known_servers: Dict[str, set[str]] = {
    name: set(names)
    for name, names in settings.load().get("known_servers_by_tool", {}).items()
}


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


def _normalize_server(cfg: dict) -> dict:
    """A server config with the canonical shape's optional keys filled in
    with their defaults, so two spellings of the same server compare equal.

    Some adapters always emit "args"/"env" (Zed nests them under a required
    "command" object, so reading one back always produces them) while
    pass-through adapters return only what the file actually had. Comparing
    those two spellings directly makes a server permanently differ from
    itself, so every pass would call the tool out of sync and rewrite +
    notify for it forever.

    This is used ONLY for comparison - see _comparable. The values written
    to disk keep whatever shape they already had, so syncing never injects
    empty "args"/"env"/"headers" keys into a user's config files."""
    cfg = dict(cfg)
    if "url" in cfg:
        cfg.setdefault("headers", {})
    else:
        cfg.setdefault("args", [])
        cfg.setdefault("env", {})
    return cfg


def _comparable(servers: ServerMap) -> ServerMap:
    """The normalized view of a server map, for equality checks only."""
    return {name: _normalize_server(cfg) for name, cfg in servers.items()}


def _safe_read(tool: ToolSpec) -> ServerMap:
    """The tool's servers exactly as its adapter reports them - deliberately
    NOT normalized, so what gets merged and written back preserves the
    original files' shape."""
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


def _representable(tool: ToolSpec, merged: Dict[str, dict]) -> Dict[str, dict]:
    """The subset of `merged` this tool's format can actually store (see
    Adapter.supports) - what "in sync" means for a tool whose format can't
    represent every kind of server (e.g. Zed only supports local stdio
    commands, not remote/http ones). Comparing against the full `merged`
    for such a tool would never match, so it would look permanently out of
    sync and get rewritten (and reported as "synced") on every pass even
    though there's nothing more it could ever do."""
    return {name: cfg for name, cfg in merged.items() if tool.adapter.supports(cfg)}


def run_sync(changed_paths: Optional[List[str]] = None, backup: bool = False) -> SyncResult:
    """Perform one full sync pass across all enabled + detected tools.

    `backup` gates whether each about-to-be-overwritten file is copied to
    ~/.mcp-sync/backups first. It's opt-in per call (not "every sync writes a
    backup") so silent/periodic passes don't fill that directory - callers
    pass True only for the app's startup sync and the user-initiated "Sync
    Now" action."""
    global _last_sync_end_ts
    with _sync_lock:
        result = SyncResult()
        try:
            tools = _enabled_detected_tools()
            merged = merge_servers(tools)
            by_path = {tool.resolved_path(): tool for tool in tools}
            if changed_paths:
                for path in changed_paths:
                    tool = by_path.get(os.path.abspath(path))
                    if tool is None:
                        continue
                    current_names = set(_safe_read(tool))
                    previous_names = _known_servers.get(tool.name, current_names)
                    removed_names = previous_names - current_names
                    for removed_name in removed_names:
                        merged.pop(removed_name, None)
            result.merged_server_names = sorted(merged.keys())

            run_id = backup_mod.make_run_id() if backup else None
            for tool in tools:
                current = _safe_read(tool)
                target = _representable(tool, merged)
                # Compare normalized, write `target` as-is: an equal-but
                # differently-spelled config must not count as a change (see
                # _normalize_server), and a config that genuinely does need
                # writing goes in with the winning file's own shape rather
                # than a normalized one.
                if _comparable(current) != _comparable(target):
                    if run_id is not None:
                        try:
                            # Safety principle: a write must never happen
                            # without a restorable copy of what was there
                            # before it. If the backup itself fails, skip
                            # writing this tool rather than proceeding
                            # unprotected.
                            backup_mod.backup_file(tool.resolved_path(), tool.name, run_id)
                        except Exception as exc:
                            result.error = f"backup {tool.name}: {exc}"
                            continue
                    try:
                        # `target`, not `merged`: writing exactly what the
                        # comparison above tested against is what guarantees
                        # the next pass sees this tool as in sync. (Handing
                        # the adapter the full set happens to work today only
                        # because a lossy adapter drops what it can't store
                        # on the way out - that's the adapter repeating the
                        # supports() filter, not a property to rely on.)
                        tool.adapter.write(tool.resolved_path(), target)
                        result.changed_tools.append(tool.name)
                        # Mark "last write" the instant it happens, not after
                        # the whole pass finishes - the watcher's debounced
                        # file-change event needs this to land close enough
                        # to the actual write for the self-write suppression
                        # window (SELF_WRITE_SUPPRESS_SECONDS) to catch it,
                        # otherwise a slow pass makes its own write look like
                        # an external change and re-triggers a visible sync.
                        _last_sync_end_ts = time.time()
                    except Exception as exc:  # keep going for other tools
                        result.error = f"{tool.name}: {exc}"

            if result.changed_tools:
                if run_id is not None:
                    backup_mod.prune_old_backups()
                import datetime

                stamp = datetime.datetime.now().isoformat(timespec="seconds")
                # settings.update (not load/save) so this doesn't clobber a
                # tool's on/off switch the user flipped mid-pass - see the
                # lost-update note in settings.update's docstring.
                settings.update(lambda data: data.__setitem__("last_sync_iso", stamp))

            result.statuses = build_statuses(merged)
            _known_servers.clear()
            _known_servers.update({tool.name: set(_safe_read(tool)) for tool in tools})
            known = {name: sorted(names) for name, names in _known_servers.items()}
            settings.update(lambda data: data.__setitem__("known_servers_by_tool", known))
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
        in_sync = installed and enabled and _comparable(current) == _comparable(_representable(tool, merged))
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
