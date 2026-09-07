"""Watches every known tool config directory for changes and triggers a
debounced re-sync. Falls back to simple polling if watchdog isn't available."""
from __future__ import annotations

import os
import threading
import time
from typing import Callable, Set

from .sync_engine import all_registry_paths

DEBOUNCE_SECONDS = 1.5
POLL_INTERVAL_SECONDS = 5


class Watcher:
    def __init__(self, on_change: Callable[[], None]):
        self._on_change = on_change
        self._stop = threading.Event()
        self._debounce_timer: threading.Timer | None = None
        self._observer = None
        self._poll_thread: threading.Thread | None = None

    def start(self) -> None:
        try:
            self._start_watchdog()
        except Exception:
            self._start_polling()

    def stop(self) -> None:
        self._stop.set()
        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=2)
            except Exception:
                pass
        if self._debounce_timer is not None:
            self._debounce_timer.cancel()

    # -- watchdog backend (preferred: instant reaction, low CPU) -----------

    def _start_watchdog(self) -> None:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer

        watcher = self

        class Handler(FileSystemEventHandler):
            def on_any_event(self, event):  # noqa: ANN001
                if event.is_directory:
                    return
                watcher._schedule_debounced_sync()

        dirs: Set[str] = set()
        for path in all_registry_paths():
            d = os.path.dirname(path)
            if d:
                dirs.add(d)

        observer = Observer()
        handler = Handler()
        for d in dirs:
            os.makedirs(d, exist_ok=True)
            observer.schedule(handler, d, recursive=False)
        observer.daemon = True
        observer.start()
        self._observer = observer

    # -- polling fallback (used only if watchdog isn't installed) ----------

    def _start_polling(self) -> None:
        def loop():
            last_mtimes: dict[str, float] = {}
            while not self._stop.is_set():
                changed = False
                for path in all_registry_paths():
                    try:
                        mtime = os.path.getmtime(path)
                    except OSError:
                        mtime = 0.0
                    if last_mtimes.get(path) not in (None, mtime):
                        changed = True
                    last_mtimes[path] = mtime
                if changed:
                    self._on_change()
                self._stop.wait(POLL_INTERVAL_SECONDS)

        thread = threading.Thread(target=loop, daemon=True)
        thread.start()
        self._poll_thread = thread

    # -- shared debounce ------------------------------------------------

    def _schedule_debounced_sync(self) -> None:
        if self._debounce_timer is not None:
            self._debounce_timer.cancel()
        self._debounce_timer = threading.Timer(DEBOUNCE_SECONDS, self._on_change)
        self._debounce_timer.daemon = True
        self._debounce_timer.start()
