"""Backs up a tool's config file before sync_engine overwrites it.

Safety principle: every write to a target file must be preceded by a
complete, restorable copy of what was there before - so a bad merge or an
unwanted server is always one file-copy away from being undone.

Layout (rooted next to the app's own settings, ~/.mcp-sync):
    ~/.mcp-sync/backups/<run_id>/<tool_name>/<original_filename>

`run_id` is a human-readable, lexicographically-sortable timestamp (e.g.
"2026-09-08_22-39-00") shared by every file touched in the same backup run,
so they land in one folder instead of one per file. Nesting under the
tool's own name (rather than mirroring its absolute path) keeps the tree
shallow and readable while still avoiding collisions between tools that
happen to share a filename (many use "mcp.json").

Unlike a plain sync, a backup run is not automatic on every pass - it only
happens right before a write triggered by the user clicking "Sync Now" or
by the app's own startup sync (which also covers the first sync right after
install). Silent background syncs (the periodic timer, the file watcher
reacting to an external edit) skip it, so this directory only grows on
deliberate/first-run actions instead of every minute.
"""
from __future__ import annotations

import datetime
import os
import re
import shutil
from typing import Optional

from .platform_utils import home

BACKUP_ROOT = os.path.join(home(), ".mcp-sync", "backups")

_RUN_ID_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}(-\d+)?$")

# How many backup runs to retain; older ones are pruned after each run that
# produces new backups. Keeps disk usage bounded without needing a settings
# UI for it.
DEFAULT_RETENTION = 30


def make_run_id() -> str:
    """A new id for one backup run, e.g. '2026-09-08_22-39-00'. Disambiguated
    with a numeric suffix in the rare case two runs land in the same second."""
    base = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    candidate = base
    n = 2
    while os.path.exists(os.path.join(BACKUP_ROOT, candidate)):
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def backup_file(path: str, tool_name: str, run_id: str) -> Optional[str]:
    """Copy `path` (if it exists) into this run's backup folder. Returns the
    backup's path, or None if there was nothing to back up."""
    if not os.path.exists(path):
        return None
    dest_dir = os.path.join(BACKUP_ROOT, run_id, tool_name)
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, os.path.basename(path))
    shutil.copy2(path, dest_path)
    return dest_path


def prune_old_backups(keep: int = DEFAULT_RETENTION) -> None:
    """Delete all but the `keep` most recent run folders under BACKUP_ROOT."""
    if not os.path.isdir(BACKUP_ROOT):
        return
    try:
        run_dirs = [d for d in os.listdir(BACKUP_ROOT) if _RUN_ID_RE.match(d)]
    except OSError:
        return
    run_dirs.sort(reverse=True)
    for stale in run_dirs[keep:]:
        shutil.rmtree(os.path.join(BACKUP_ROOT, stale), ignore_errors=True)
