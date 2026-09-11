"""Tray application entrypoint: shows the MCP sync icon, a menu listing
every detected tool with a green/gray status dot and an on/off toggle, and
runs the file watcher + periodic sync loop in the background."""
from __future__ import annotations

import threading
import time

import pystray

from . import __version__, autostart, settings, sync_engine, updater
from .notifier import notify
from .platform_utils import IS_MAC
from .tray_icon import build_icon, build_tray_icon
from .watcher import Watcher

APP_NAME = "MCP"
PERIODIC_SYNC_SECONDS = 60
SELF_WRITE_SUPPRESS_SECONDS = 3.0
UPDATE_CHECK_INTERVAL_SECONDS = 24 * 60 * 60
STARTUP_UPDATE_CHECK_DELAY_SECONDS = 30
GREEN_DOT = "\U0001F7E2"  # 🟢
GRAY_DOT = "\u26AA"  # ⚪
OFF_DOT = "\u2B1B"  # ⬛


def _fallback_tray_icon(active: bool = False):
    """Icon for this pystray fallback UI, picked per platform.

    macOS's menu bar renders build_icon()'s flat-black artwork as a template
    image (auto-inverting for light/dark menu bars), so it stays correct
    there; the white-filled, black-outlined build_tray_icon() exists
    precisely for the platforms that *don't* do that. Using the
    Linux/Windows one on macOS would put a hand-outlined icon in a menu bar
    that was going to recolor the plain one properly anyway."""
    return build_icon(active=active) if IS_MAC else build_tray_icon(active=active)


class MCPSyncApp:
    def __init__(self) -> None:
        self._icon = pystray.Icon(APP_NAME, _fallback_tray_icon(False), "MCP Sync", menu=self._build_menu())
        self._watcher = Watcher(on_change=self._on_files_changed)
        self._stop = threading.Event()
        self._busy_until = 0.0
        self._pending_update: updater.UpdateInfo | None = None

    # ------------------------------------------------------------ lifecycle

    def run(self) -> None:
        if settings.load().get("start_at_login", True) and not autostart.is_enabled():
            autostart.enable()
        self._watcher.start()
        threading.Thread(target=self._periodic_sync_loop, daemon=True).start()
        threading.Thread(target=self._update_check_loop, daemon=True).start()
        self.sync_now(notify_result=False, backup=True)
        self._icon.run()

    def _periodic_sync_loop(self) -> None:
        while not self._stop.is_set():
            self._stop.wait(PERIODIC_SYNC_SECONDS)
            if not self._stop.is_set():
                self.sync_now(notify_result=False)

    def _update_check_loop(self) -> None:
        self._stop.wait(STARTUP_UPDATE_CHECK_DELAY_SECONDS)
        while not self._stop.is_set():
            if settings.is_auto_update_enabled():
                self._check_for_update(manual=False)
            self._stop.wait(UPDATE_CHECK_INTERVAL_SECONDS)

    def _on_files_changed(self, changed_paths: list[str]) -> None:
        if sync_engine.seconds_since_last_sync() < SELF_WRITE_SUPPRESS_SECONDS:
            return  # our own write just triggered this event, not a real external change
        self.sync_now(notify_result=True, changed_paths=changed_paths)

    # ----------------------------------------------------------------- sync

    def sync_now(
        self,
        notify_result: bool = True,
        always_notify: bool = False,
        backup: bool = False,
        changed_paths: list[str] | None = None,
    ) -> None:
        self._set_busy(True)
        try:
            result = sync_engine.run_sync(changed_paths=changed_paths, backup=backup)
        finally:
            self._set_busy(False)
        self._refresh_menu()
        if result.error:
            notify(APP_NAME, f"Sync error: {result.error}")
        elif result.changed_tools and (notify_result or always_notify):
            notify(APP_NAME, "Synced: " + ", ".join(result.changed_tools))
        elif always_notify:
            notify(APP_NAME, "Already in sync")

    def _set_busy(self, busy: bool) -> None:
        try:
            self._icon.icon = _fallback_tray_icon(active=busy)
        except Exception:
            pass

    # -------------------------------------------------------------- updates

    def _check_for_update(self, manual: bool) -> None:
        if manual:
            try:
                info = updater.fetch_latest_release_info()
            except updater.UpdateCheckError:
                notify(APP_NAME, "Couldn't check for updates. Check your connection.")
                return
            import datetime

            settings.set_last_update_check_iso(datetime.datetime.now().isoformat(timespec="seconds"))
            if updater.is_newer(info.version, __version__) and info.version != settings.get_skipped_version():
                self._pending_update = info
                notify(APP_NAME, f"Update available: v{info.version}")
            else:
                notify(APP_NAME, "You're up to date")
        else:
            info = updater.check_for_update(__version__)
            if info is not None and info.version != settings.get_skipped_version():
                self._pending_update = info
                notify(APP_NAME, f"Update available: v{info.version}")
        self._refresh_menu()

    def _on_check_for_updates(self, icon, item) -> None:
        threading.Thread(target=lambda: self._check_for_update(manual=True), daemon=True).start()

    def _on_update_now(self, icon, item) -> None:
        info = self._pending_update
        if info is None:
            return
        threading.Thread(target=lambda: self._perform_update(info), daemon=True).start()

    def _perform_update(self, info: updater.UpdateInfo) -> None:
        notify(APP_NAME, f"Downloading update v{info.version}…")
        try:
            updater.perform_update(info)  # never returns on success
        except Exception as exc:
            notify(APP_NAME, f"Update failed: {exc}")

    def _on_skip_version(self, icon, item) -> None:
        if self._pending_update is not None:
            settings.set_skipped_version(self._pending_update.version)
            self._pending_update = None
            self._refresh_menu()

    def _toggle_auto_update(self, icon, item) -> None:
        settings.set_auto_update_enabled(not item.checked)

    # ----------------------------------------------------------------- menu

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(self._menu_items)

    def _refresh_menu(self) -> None:
        try:
            self._icon.update_menu()
        except Exception:
            pass

    def _menu_items(self):
        statuses = sync_engine.build_statuses()
        last_sync = settings.load().get("last_sync_iso")
        header = f"{APP_NAME} Sync" + (f" \u2013 last sync {last_sync}" if last_sync else "")
        yield pystray.MenuItem(header, None, enabled=False)
        yield pystray.Menu.SEPARATOR

        for status in statuses:
            if not status.installed:
                continue
            if not status.enabled:
                dot = OFF_DOT
            elif status.in_sync:
                dot = GREEN_DOT
            else:
                dot = GRAY_DOT
            label = f"{dot} {status.name} ({status.server_count})"
            yield pystray.MenuItem(
                label,
                self._make_toggle_handler(status.name),
                checked=self._make_checked_getter(status.name),
            )

        not_installed = [s.name for s in statuses if not s.installed]
        if not_installed:
            yield pystray.Menu.SEPARATOR
            yield pystray.MenuItem(f"Not detected: {', '.join(not_installed)}", None, enabled=False)

        yield pystray.Menu.SEPARATOR
        yield pystray.MenuItem("Sync Now", lambda icon, item: self.sync_now(notify_result=True, always_notify=True, backup=True))
        yield pystray.MenuItem("Settings", self._build_settings_submenu())
        yield pystray.Menu.SEPARATOR
        yield pystray.MenuItem("Quit", self._quit)

    def _build_settings_submenu(self) -> pystray.Menu:
        items = [
            pystray.MenuItem(
                "Start at Login",
                self._toggle_start_at_login,
                checked=lambda item: autostart.is_enabled(),
            ),
            pystray.MenuItem("Check for Updates", self._on_check_for_updates),
            pystray.MenuItem(
                "Auto-update",
                self._toggle_auto_update,
                checked=lambda item: settings.is_auto_update_enabled(),
            ),
        ]
        if self._pending_update is not None:
            items.append(pystray.Menu.SEPARATOR)
            items.append(pystray.MenuItem(f"Update Now (v{self._pending_update.version})", self._on_update_now))
            items.append(pystray.MenuItem("Skip This Version", self._on_skip_version))
        return pystray.Menu(*items)

    def _make_toggle_handler(self, tool_name: str):
        def handler(icon, item):
            settings.set_tool_enabled(tool_name, not item.checked)
            self.sync_now(notify_result=False)

        return handler

    def _make_checked_getter(self, tool_name: str):
        return lambda item: settings.is_tool_enabled(tool_name)

    def _toggle_start_at_login(self, icon, item) -> None:
        if item.checked:
            autostart.disable()
            settings.set_start_at_login(False)
        else:
            autostart.enable()
            settings.set_start_at_login(True)
        self._refresh_menu()

    def _quit(self, icon, item) -> None:
        self._stop.set()
        self._watcher.stop()
        icon.stop()


def main() -> None:
    """On macOS, prefer the native AppKit popover (stays open while you
    toggle a tool and looks like a real app, not a plain OS menu); on Linux,
    prefer the AppIndicator tray icon plus a real GTK popover window (same
    provider list/search/switches - see linux_ui.py for why the indicator's
    own menu can't carry them). Falls back to the cross-platform pystray
    tray icon everywhere else, or if the platform-native UI's dependencies
    aren't installed."""
    try:
        import setproctitle

        # Otherwise this shows up as "Python"/"python3" in Activity Monitor,
        # Task Manager, `ps`, etc. - not the interpreter's own name.
        setproctitle.setproctitle("mcp-auto-synch")
    except ImportError:
        pass

    from . import single_instance
    from .platform_utils import IS_LINUX, IS_MAC, IS_WINDOWS

    # Every launcher click (app grid, .desktop entry, autostart firing while
    # the app is already up) runs this same entry point, and each process
    # would add its own tray icon. Only the first one continues; the rest ask
    # it to show itself and exit.
    instance = single_instance.acquire()
    if instance is None:
        return
    instance.start_activation_listener()

    if IS_MAC:
        try:
            from .mac_ui import MacPopoverApp

            MacPopoverApp().run()
            return
        except ImportError:
            pass
    elif IS_LINUX:
        try:
            from . import autostart

            # Makes the app show up as a clickable icon in GNOME's
            # Activities/app-grid search - independent of the "Start at
            # Login" setting, and cheap enough to self-heal on every start.
            autostart.ensure_application_launcher()
        except Exception:
            pass
        try:
            from .linux_ui import LinuxIndicatorApp

            LinuxIndicatorApp(instance=instance).run()
            return
        except (ImportError, ValueError):
            pass
    elif IS_WINDOWS:
        from .windows_ui import WindowsTrayApp

        WindowsTrayApp(instance=instance).run()
        return
    MCPSyncApp().run()


if __name__ == "__main__":
    main()
