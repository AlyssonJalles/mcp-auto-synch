"""Native macOS menu-bar UI built directly on AppKit (PyObjC).

Why not just use pystray here: pystray's tray menu on macOS is a plain
NSMenu, and NSMenu always closes itself the instant any item is clicked -
that's a hard OS/AppKit convention, not something a Python library can
override. To let the user toggle a tool on/off and see the list update
*without the panel closing*, we render our own NSPopover with plain
NSView/NSSwitch controls instead of an NSMenu; clicking a switch inside a
popover does not close it, only clicking outside (or the status icon again)
does.
"""
from __future__ import annotations

import io
import os
import threading

import AppKit
import Foundation
import objc
from PyObjCTools import AppHelper

from . import __version__, autostart, settings, sync_engine, updater
from .groups import get_group, group_for_tool
from .logos import get_badge, get_company_logo
from .notifier import notify
from .platform_utils import open_path_in_file_manager
from .tray_icon import build_icon, build_status_dot
from .watcher import Watcher

APP_NAME = "MCP"
DOCS_URL = "https://github.com/AlyssonJalles/mcp-auto-synch"
PERIODIC_SYNC_SECONDS = 60
SELF_WRITE_SUPPRESS_SECONDS = 3.0
MENUBAR_ICON_POINT_HEIGHT = 18.0  # standard macOS menu bar glyph height
FLASH_ICON_SECONDS = 0.6  # how long the icon stays green after an actual write
UPDATE_CHECK_INTERVAL_SECONDS = 24 * 60 * 60
STARTUP_UPDATE_CHECK_DELAY_SECONDS = 30

WIDTH = 320
ROW_H = 44
HEADER_H = 60
SEARCH_H = 26
FOOTER_ROW_H = 36
VERSION_ROW_H = 18
CHECK_UPDATES_ROW_H = 30
UPDATE_BANNER_H = 74
SEP_H = 9
MARGIN = 14
MAX_POPOVER_HEIGHT = 780
LIST_VIEWPORT_HEIGHT = 440
APP_LOGO_HEIGHT = 45.0  # 50% larger than the original 30pt fit
APP_LOGO_PNG = os.path.join(os.path.dirname(__file__), "assets", "logos", "_mcp_synch.png")


def _pil_to_nsimage(img, point_height: "float | None" = None) -> "AppKit.NSImage":
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data = buf.getvalue()
    ns_data = AppKit.NSData.dataWithBytes_length_(data, len(data))
    ns_image = AppKit.NSImage.alloc().initWithData_(ns_data)
    if point_height is not None and img.height:
        aspect = img.width / img.height
        ns_image.setSize_(Foundation.NSMakeSize(point_height * aspect, point_height))
    return ns_image


def _label(text, frame, size=13, bold=False, color=None) -> "AppKit.NSTextField":
    tf = AppKit.NSTextField.alloc().initWithFrame_(frame)
    tf.setStringValue_(text)
    tf.setBezeled_(False)
    tf.setDrawsBackground_(False)
    tf.setEditable_(False)
    tf.setSelectable_(False)
    tf.setFont_(AppKit.NSFont.boldSystemFontOfSize_(size) if bold else AppKit.NSFont.systemFontOfSize_(size))
    if color is not None:
        tf.setTextColor_(color)
    return tf


def _separator(frame) -> "AppKit.NSBox":
    box = AppKit.NSBox.alloc().initWithFrame_(frame)
    box.setBoxType_(AppKit.NSBoxSeparator)
    return box


class MCPMenuBarController(AppKit.NSObject):
    """The NSObject-backed controller: owns the status item, the popover,
    and all UI action callbacks (AppKit requires target/action callbacks to
    live on an NSObject subclass)."""

    def initApp(self) -> "MCPMenuBarController":
        self._stop = threading.Event()
        self._watcher = Watcher(on_change=self._on_files_changed)
        self._search_query = ""
        self._chrome_built = False
        self._tool_order: list = []
        self._tool_paths: list = []
        self._settings_open = False
        self._pending_update: "updater.UpdateInfo | None" = None
        self._version_status_text = f"Version {__version__}"
        self._logo_cache: dict = {}
        self._search_field = AppKit.NSSearchField.alloc().initWithFrame_(Foundation.NSMakeRect(0, 0, 10, SEARCH_H))
        self._search_field.setPlaceholderString_("Search providers\u2026")
        self._search_field.setTarget_(self)
        self._search_field.setAction_("searchFieldChanged:")
        self._search_field.setDelegate_(self)
        self._status_item = AppKit.NSStatusBar.systemStatusBar().statusItemWithLength_(
            AppKit.NSVariableStatusItemLength
        )
        self._set_menubar_icon(active=False)
        button = self._status_item.button()
        button.setTarget_(self)
        button.setAction_("statusItemClicked:")

        self._popover = None
        self._view_controller = AppKit.NSViewController.alloc().init()
        self._rebuild_content()
        return self

    # ------------------------------------------------------------ lifecycle

    def start(self) -> None:
        if settings.load().get("start_at_login", True) and not autostart.is_enabled():
            autostart.enable()
        self._watcher.start()
        self._timer = Foundation.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            PERIODIC_SYNC_SECONDS, self, "periodicSyncTick:", None, True
        )
        threading.Thread(target=lambda: self.sync_now(notify_result=False, backup=True), daemon=True).start()
        threading.Thread(target=self._update_check_loop, daemon=True).start()

    def _update_check_loop(self) -> None:
        self._stop.wait(STARTUP_UPDATE_CHECK_DELAY_SECONDS)
        while not self._stop.is_set():
            if settings.is_auto_update_enabled():
                self._check_for_update(manual=False)
            self._stop.wait(UPDATE_CHECK_INTERVAL_SECONDS)

    def _check_for_update(self, manual: bool) -> None:
        import datetime

        if manual:
            try:
                info = updater.fetch_latest_release_info()
            except updater.UpdateCheckError:
                AppHelper.callAfter(self._show_check_failed)
                return
            settings.set_last_update_check_iso(datetime.datetime.now().isoformat(timespec="seconds"))
            newer = updater.is_newer(info.version, __version__) and info.version != settings.get_skipped_version()
            self._pending_update = info if newer else None
            AppHelper.callAfter(self._show_check_result, not newer)
        else:
            info = updater.check_for_update(__version__)
            if info is not None and info.version != settings.get_skipped_version():
                self._pending_update = info
                notify(APP_NAME, f"Update available: v{info.version}")
                AppHelper.callAfter(self._rebuild_content)

    def _show_check_failed(self) -> None:
        notify(APP_NAME, "Couldn't check for updates. Check your connection.")
        self._version_status_text = "Couldn't check — check your connection"
        self._rebuild_content()

    def _show_check_result(self, up_to_date: bool) -> None:
        if up_to_date:
            notify(APP_NAME, "You're up to date")
            self._version_status_text = f"Version {__version__} — up to date"
        else:
            notify(APP_NAME, f"Update available: v{self._pending_update.version}")
        self._rebuild_content()

    # ----------------------------------------------------------------- sync

    def sync_now(
        self,
        notify_result: bool = True,
        changed_paths: list[str] | None = None,
        always_rebuild: bool = True,
        backup: bool = False,
    ) -> None:
        # A watched tool often rewrites its own config file for reasons that
        # have nothing to do with MCP servers (e.g. Claude Code persisting
        # session/usage state every few seconds) - that's a real external
        # file change, so it's correct to check it, but it's not something
        # worth showing. Gate the icon flash and the popover rebuild on
        # result.changed_tools (something this app actually wrote) instead
        # of on "a sync ran", or every such unrelated touch flashes the icon
        # and - worse - tears down/rebuilds the popover's buttons while it's
        # open, which can swallow a click if it lands mid-track (e.g. on
        # Quit). always_rebuild=True (user-initiated actions: toggling a
        # tool, clicking Sync Now, first load) keeps the previous
        # always-refresh behavior since those need immediate UI feedback
        # even when nothing needed rewriting. sync_now() always runs on a
        # background thread, so every AppKit call here must go through
        # AppHelper.callAfter - touching AppKit directly off the main thread
        # is what caused the intermittent layout/rendering glitches.
        result = sync_engine.run_sync(changed_paths=changed_paths, backup=backup)
        if result.changed_tools:
            if notify_result:
                AppHelper.callAfter(self._flash_menubar_icon)
            AppHelper.callAfter(self._rebuild_content)
        elif always_rebuild:
            AppHelper.callAfter(self._rebuild_content)
        if notify_result and result.changed_tools and not result.error:
            notify(APP_NAME, "Synced: " + ", ".join(result.changed_tools))
        elif result.error:
            notify(APP_NAME, f"Sync error: {result.error}")

    def _on_files_changed(self, changed_paths: list[str]) -> None:
        if sync_engine.seconds_since_last_sync() < SELF_WRITE_SUPPRESS_SECONDS:
            return  # our own write just triggered this event, not a real external change
        threading.Thread(
            target=lambda: self.sync_now(notify_result=True, changed_paths=changed_paths, always_rebuild=False),
            daemon=True,
        ).start()

    def periodicSyncTick_(self, timer) -> None:
        threading.Thread(target=lambda: self.sync_now(notify_result=False, always_rebuild=False), daemon=True).start()

    def _set_menubar_icon(self, active: bool) -> None:
        img = _pil_to_nsimage(build_icon(active=active), point_height=MENUBAR_ICON_POINT_HEIGHT)
        img.setTemplate_(not active)
        self._status_item.button().setImage_(img)

    def _flash_menubar_icon(self) -> None:
        self._set_menubar_icon(True)
        Foundation.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            FLASH_ICON_SECONDS, self, "clearMenubarFlash:", None, False
        )

    def clearMenubarFlash_(self, timer) -> None:
        self._set_menubar_icon(False)

    # ----------------------------------------------------------------- menu

    def statusItemClicked_(self, sender) -> None:
        if self._popover is not None and self._popover.isShown():
            self._popover.performClose_(sender)
            return
        self._rebuild_content()
        self._show_popover()

    def _show_popover(self) -> None:
        # Reusing the same NSPopover instance across multiple show/hide cycles
        # (or resizing one that's already shown) can leave its window geometry
        # out of sync with its content view (content ends up rendered shifted
        # left) - always creating a fresh popover right before showing it
        # sidesteps that entirely.
        self._popover = AppKit.NSPopover.alloc().init()
        self._popover.setBehavior_(AppKit.NSPopoverBehaviorTransient)
        self._popover.setAnimates_(False)
        self._popover.setContentViewController_(self._view_controller)
        self._popover.setContentSize_(Foundation.NSMakeSize(WIDTH, self._last_total_h))
        # Activating the app (even though it has no Dock icon/menu bar menu)
        # makes the popover properly become key, which is what makes AppKit
        # reliably auto-close it on an outside click for accessory-policy apps.
        AppKit.NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        button = self._status_item.button()
        self._popover.showRelativeToRect_ofView_preferredEdge_(button.bounds(), button, AppKit.NSMinYEdge)

    def _search_field_has_focus(self) -> bool:
        window = self._search_field.window()
        if window is None:
            return False
        editor = self._search_field.currentEditor()
        return editor is not None and window.firstResponder() is editor

    def _restore_search_focus(self) -> None:
        window = self._search_field.window()
        if window is None:
            return
        window.makeFirstResponder_(self._search_field)
        editor = self._search_field.currentEditor()
        if editor is not None:
            end = len(self._search_field.stringValue())
            editor.setSelectedRange_(Foundation.NSMakeRange(end, 0))

    def toggleTool_(self, sender) -> None:
        tool_name = self._tool_order[sender.tag()]
        enabled = sender.state() == AppKit.NSControlStateValueOn
        settings.set_tool_enabled(tool_name, enabled)
        threading.Thread(target=lambda: self.sync_now(notify_result=False), daemon=True).start()

    def revealConfig_(self, sender) -> None:
        index = sender.tag()
        if 0 <= index < len(self._tool_paths):
            path = self._tool_paths[index]
            threading.Thread(target=lambda: open_path_in_file_manager(path), daemon=True).start()

    def searchFieldChanged_(self, sender) -> None:
        self._search_query = (sender.stringValue() or "").strip().lower()
        self._rebuild_content()

    def controlTextDidChange_(self, notification) -> None:
        field = notification.object()
        self._search_query = (field.stringValue() or "").strip().lower()
        self._rebuild_content()

    def syncNowClicked_(self, sender) -> None:
        threading.Thread(target=lambda: self.sync_now(notify_result=True, backup=True), daemon=True).start()

    def toggleStartAtLogin_(self, sender) -> None:
        enabled = sender.state() == AppKit.NSControlStateValueOn
        if enabled:
            autostart.enable()
        else:
            autostart.disable()
        settings.set_start_at_login(enabled)

    def toggleHideNotInstalled_(self, sender) -> None:
        hidden = sender.state() == AppKit.NSControlStateValueOn
        settings.set_hide_not_installed(hidden)
        self._rebuild_content()

    def toggleSettingsSection_(self, sender) -> None:
        self._settings_open = not self._settings_open
        self._rebuild_content()

    def toggleAutoUpdate_(self, sender) -> None:
        enabled = sender.state() == AppKit.NSControlStateValueOn
        settings.set_auto_update_enabled(enabled)

    def checkForUpdatesClicked_(self, sender) -> None:
        sender.setEnabled_(False)
        sender.setTitle_("Checking…")
        threading.Thread(target=lambda: self._check_for_update(manual=True), daemon=True).start()

    def updateNowClicked_(self, sender) -> None:
        info = self._pending_update
        if info is None:
            return
        sender.setEnabled_(False)
        sender.setTitle_("Downloading…")
        threading.Thread(target=lambda: self._perform_update(info), daemon=True).start()

    def _perform_update(self, info) -> None:
        try:
            updater.perform_update(info)  # never returns on success
        except Exception as exc:
            AppHelper.callAfter(self._show_update_failed, str(exc))

    def _show_update_failed(self, msg: str) -> None:
        notify(APP_NAME, f"Update failed: {msg}")
        self._rebuild_content()

    def skipVersionClicked_(self, sender) -> None:
        info = self._pending_update
        if info is None:
            return
        settings.set_skipped_version(info.version)
        self._pending_update = None
        self._version_status_text = f"Version {__version__}"
        self._rebuild_content()

    def openDocumentation_(self, sender) -> None:
        url = Foundation.NSURL.URLWithString_(DOCS_URL)
        AppKit.NSWorkspace.sharedWorkspace().openURL_(url)

    def quitClicked_(self, sender) -> None:
        self._stop.set()
        self._watcher.stop()
        AppKit.NSApplication.sharedApplication().terminate_(self)

    # --------------------------------------------------------- view builder

    def _app_logo(self) -> "AppKit.NSImage | None":
        if "app" not in self._logo_cache:
            try:
                # Same wordmark artwork used elsewhere in the app (Start Menu
                # shortcut icon on Windows) so the popover is recognizably
                # this app's own, not a generic menu-bar glyph.
                img = AppKit.NSImage.alloc().initByReferencingFile_(APP_LOGO_PNG)
                if img is not None and img.isValid():
                    size = img.size()
                    if size.height:
                        aspect = size.width / size.height
                        img.setSize_(Foundation.NSMakeSize(APP_LOGO_HEIGHT * aspect, APP_LOGO_HEIGHT))
                else:
                    img = None
                self._logo_cache["app"] = img
            except Exception:
                self._logo_cache["app"] = None
        return self._logo_cache["app"]

    def _ensure_chrome(self) -> None:
        """Builds the parts of the UI that must never be destroyed/recreated
        (title, subtitle, search field) exactly once. Recreating a focused
        NSTextField's superview chain on every keystroke is what used to make
        the search box disappear while typing - now only its *frame* moves,
        and its window/superview identity never changes."""
        if self._chrome_built:
            return
        self._root_view = AppKit.NSView.alloc().initWithFrame_(Foundation.NSMakeRect(0, 0, WIDTH, 10))
        logo_img = self._app_logo()
        logo_w = logo_img.size().width if logo_img is not None else 0.0
        title_w = WIDTH - 2 * MARGIN - (logo_w + 8 if logo_img is not None else 0)
        self._app_logo_view = AppKit.NSImageView.alloc().initWithFrame_(
            Foundation.NSMakeRect(WIDTH - MARGIN - logo_w, 0, logo_w, APP_LOGO_HEIGHT)
        )
        if logo_img is not None:
            self._app_logo_view.setImage_(logo_img)
        self._title_label = _label("MCP Sync", Foundation.NSMakeRect(MARGIN, 0, title_w, 20), size=15, bold=True)
        self._subtitle_label = _label(
            "", Foundation.NSMakeRect(MARGIN, 0, title_w, 16), size=11, color=AppKit.NSColor.secondaryLabelColor()
        )
        self._top_separator = _separator(Foundation.NSMakeRect(MARGIN, 0, WIDTH - 2 * MARGIN, 1))
        self._list_view = AppKit.NSView.alloc().initWithFrame_(Foundation.NSMakeRect(0, 0, WIDTH, 10))
        self._list_scroll = AppKit.NSScrollView.alloc().initWithFrame_(Foundation.NSMakeRect(0, 0, WIDTH, LIST_VIEWPORT_HEIGHT))
        self._list_scroll.setHasVerticalScroller_(True)
        self._list_scroll.setHasHorizontalScroller_(False)
        self._list_scroll.setAutohidesScrollers_(True)
        self._list_scroll.setBorderType_(AppKit.NSNoBorder)
        self._list_scroll.setDrawsBackground_(False)
        self._list_scroll.setDocumentView_(self._list_view)
        self._footer_view = AppKit.NSView.alloc().initWithFrame_(Foundation.NSMakeRect(0, 0, WIDTH, FOOTER_ROW_H * 4 + SEP_H))
        for subview in (self._app_logo_view, self._title_label, self._subtitle_label, self._search_field, self._top_separator, self._list_scroll, self._footer_view):
            self._root_view.addSubview_(subview)
        self._view_controller.setView_(self._root_view)
        self._chrome_built = True

    def _rebuild_content(self) -> None:
        self._ensure_chrome()
        was_shown = self._popover is not None and self._popover.isShown()
        had_focus = was_shown and self._search_field_has_focus()
        if was_shown:
            self._popover.performClose_(None)

        statuses = sync_engine.build_statuses()
        installed = sorted((s for s in statuses if s.installed), key=lambda s: s.name.lower())
        not_installed = sorted((s for s in statuses if not s.installed), key=lambda s: s.name.lower())

        query = self._search_query
        if query:
            installed = [s for s in installed if query in s.name.lower() or query in group_for_tool(s.name).lower()]
            not_installed = [s for s in not_installed if query in s.name.lower() or query in group_for_tool(s.name).lower()]

        hide_not_installed = settings.load().get("hide_not_installed", True)
        visible_not_installed = [] if hide_not_installed else not_installed

        # Merge installed + (optionally) not-installed into one alphabetical
        # list; not-installed rows render the same way but muted/disabled.
        rows = sorted(
            [(s, True) for s in installed] + [(s, False) for s in visible_not_installed],
            key=lambda pair: pair[0].name.lower(),
        )

        self._tool_order = [s.name for s, _ in rows]
        self._tool_paths = [s.path for s, _ in rows]

        blocks = []  # list of (kind, payload, height)
        for status, is_installed in rows:
            blocks.append(("row", (status, is_installed), ROW_H))

        if not rows and query:
            blocks.append(("dim_label", f'No provider matches "{query}"', FOOTER_ROW_H))

        rows_h = sum(h for _, _, h in blocks)
        list_h = max(rows_h, LIST_VIEWPORT_HEIGHT)

        for old_subview in list(self._list_view.subviews()):
            old_subview.removeFromSuperview()
        for old_subview in list(self._footer_view.subviews()):
            old_subview.removeFromSuperview()

        y = rows_h
        for kind, payload, h in blocks:
            y -= h
            if kind == "row":
                status, is_installed = payload
                index = self._tool_order.index(status.name)
                self._list_view.addSubview_(self._build_row(status, y, index, is_installed))
            elif kind == "separator":
                self._list_view.addSubview_(_separator(Foundation.NSMakeRect(MARGIN, y + 4, WIDTH - 2 * MARGIN, 1)))
            elif kind == "dim_label":
                self._list_view.addSubview_(
                    _label(
                        payload,
                        Foundation.NSMakeRect(MARGIN, y, WIDTH - 2 * MARGIN, h),
                        size=10,
                        color=AppKit.NSColor.tertiaryLabelColor(),
                    )
                )

        self._list_view.setFrame_(Foundation.NSMakeRect(0, 0, WIDTH, max(rows_h, LIST_VIEWPORT_HEIGHT)))

        footer_blocks = self._build_footer_blocks(hide_not_installed)
        footer_h = sum(h for _, _, h in footer_blocks)
        footer_y = footer_h
        for kind, payload, h in footer_blocks:
            footer_y -= h
            view = self._build_footer_block(kind, payload, footer_y, h)
            if view is not None:
                self._footer_view.addSubview_(view)
        self._footer_view.setFrame_(Foundation.NSMakeRect(0, 0, WIDTH, footer_h))

        total_h = min(MAX_POPOVER_HEIGHT, HEADER_H + SEARCH_H + 6 + SEP_H + LIST_VIEWPORT_HEIGHT + footer_h)

        y2 = total_h
        y2 -= HEADER_H
        self._title_label.setFrame_(Foundation.NSMakeRect(MARGIN, y2 + 24, self._title_label.frame().size.width, 20))
        last_sync = settings.load().get("last_sync_iso")
        self._subtitle_label.setStringValue_(f"Last sync: {last_sync}" if last_sync else "Not synced yet")
        self._subtitle_label.setFrame_(Foundation.NSMakeRect(MARGIN, y2 + 4, self._subtitle_label.frame().size.width, 16))
        self._app_logo_view.setFrameOrigin_(
            Foundation.NSMakePoint(self._app_logo_view.frame().origin.x, y2 + (HEADER_H - APP_LOGO_HEIGHT) / 2)
        )

        y2 -= SEARCH_H + 6
        self._search_field.setFrame_(Foundation.NSMakeRect(MARGIN, y2, WIDTH - 2 * MARGIN, SEARCH_H))

        y2 -= SEP_H
        self._top_separator.setFrame_(Foundation.NSMakeRect(MARGIN, y2 + 4, WIDTH - 2 * MARGIN, 1))

        list_viewport_y = y2 - LIST_VIEWPORT_HEIGHT
        self._list_scroll.setFrame_(Foundation.NSMakeRect(0, list_viewport_y, WIDTH, LIST_VIEWPORT_HEIGHT))
        self._list_view.setFrame_(Foundation.NSMakeRect(0, 0, WIDTH, max(rows_h, LIST_VIEWPORT_HEIGHT)))
        self._footer_view.setFrame_(Foundation.NSMakeRect(0, 0, WIDTH, footer_h))
        footer_y = list_viewport_y - footer_h
        self._footer_view.setFrameOrigin_(Foundation.NSMakePoint(0, footer_y))
        self._root_view.setFrame_(Foundation.NSMakeRect(0, 0, WIDTH, total_h))

        self._last_total_h = total_h
        if was_shown:
            self._show_popover()
            if had_focus:
                self._restore_search_focus()

    def _build_row(self, status, y: float, index: int, is_installed: bool = True) -> "AppKit.NSView":
        row = AppKit.NSView.alloc().initWithFrame_(Foundation.NSMakeRect(0, y, WIDTH, ROW_H))

        badge_img = _pil_to_nsimage(get_badge(status.name))
        badge_view = AppKit.NSImageView.alloc().initWithFrame_(Foundation.NSMakeRect(MARGIN, (ROW_H - 26) / 2, 26, 26))
        badge_view.setImage_(badge_img)
        row.addSubview_(badge_view)

        name_x = MARGIN + 26 + 10
        row.addSubview_(_label(status.name, Foundation.NSMakeRect(name_x, ROW_H / 2, WIDTH - name_x - 90, 18), size=12.5, bold=True))

        # Discreet "company owner" line: a tiny company logo + company name,
        # plus a button to reveal the config file's folder in Finder.
        group = get_group(status.name)
        company = group.company if group else "Independent"
        sec_y = ROW_H / 2 - 16
        cursor_x = name_x
        company_logo = get_company_logo(group.logo) if group else None
        if company_logo is not None:
            tiny_view = AppKit.NSImageView.alloc().initWithFrame_(Foundation.NSMakeRect(cursor_x, sec_y + 1, 12, 12))
            tiny_view.setImage_(_pil_to_nsimage(company_logo))
            row.addSubview_(tiny_view)
            cursor_x += 15
        folder_x = WIDTH - 127
        secondary_text = f"{company} \u00b7 {status.server_count} server{'s' if status.server_count != 1 else ''}"
        if not is_installed:
            secondary_text = f"{company} \u00b7 not installed"
        row.addSubview_(
            _label(
                secondary_text,
                Foundation.NSMakeRect(cursor_x, sec_y, max(20, folder_x - cursor_x - 8), 14),
                size=10,
                color=AppKit.NSColor.secondaryLabelColor(),
            )
        )

        reveal_btn = self._build_reveal_button(status.path, index, folder_x, sec_y - 2)
        reveal_btn.setEnabled_(is_installed)
        row.addSubview_(reveal_btn)

        if is_installed:
            dot_color = "green" if (status.enabled and status.in_sync) else ("off" if not status.enabled else "gray")
        else:
            dot_color = "off"
        dot_img = _pil_to_nsimage(build_status_dot(dot_color))
        dot_view = AppKit.NSImageView.alloc().initWithFrame_(Foundation.NSMakeRect(WIDTH - 70, (ROW_H - 12) / 2, 12, 12))
        dot_view.setImage_(dot_img)
        row.addSubview_(dot_view)

        switch = AppKit.NSSwitch.alloc().initWithFrame_(Foundation.NSMakeRect(WIDTH - 55, (ROW_H - 20) / 2, 40, 20))
        switch.setState_(AppKit.NSControlStateValueOn if (is_installed and status.enabled) else AppKit.NSControlStateValueOff)
        switch.setEnabled_(is_installed)
        switch.setTarget_(self)
        switch.setAction_("toggleTool:")
        switch.setTag_(index)
        row.addSubview_(switch)

        if not is_installed:
            row.setAlphaValue_(0.45)  # mute the whole row: detected but nothing to sync

        return row

    def _build_reveal_button(self, path: str, index: int, x: float, y: float) -> "AppKit.NSButton":
        btn = AppKit.NSButton.alloc().initWithFrame_(Foundation.NSMakeRect(x, y, 18, 18))
        btn.setBordered_(False)
        icon = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_("folder", "Reveal config file")
        if icon is not None:
            btn.setImage_(icon)
            btn.setImagePosition_(AppKit.NSImageOnly)
        else:
            btn.setTitle_("\U0001F4C2")
        btn.setTarget_(self)
        btn.setAction_("revealConfig:")
        btn.setTag_(index)
        btn.setToolTip_(os.path.basename(path) or path)
        return btn

    def _build_action_button(self, title: str, action: str, y: float) -> "AppKit.NSButton":
        btn = AppKit.NSButton.alloc().initWithFrame_(Foundation.NSMakeRect(MARGIN, y + 3, WIDTH - 2 * MARGIN, 26))
        btn.setTitle_(title)
        btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        btn.setTarget_(self)
        btn.setAction_(action)
        return btn

    def _build_switch_row(self, title: str, on: bool, action: str, y: float) -> "AppKit.NSView":
        row = AppKit.NSView.alloc().initWithFrame_(Foundation.NSMakeRect(0, y, WIDTH, FOOTER_ROW_H))
        row.addSubview_(_label(title, Foundation.NSMakeRect(MARGIN, (FOOTER_ROW_H - 18) / 2, WIDTH - 2 * MARGIN - 55, 18), size=12.5))
        switch = AppKit.NSSwitch.alloc().initWithFrame_(Foundation.NSMakeRect(WIDTH - 55, (FOOTER_ROW_H - 20) / 2, 40, 20))
        switch.setState_(AppKit.NSControlStateValueOn if on else AppKit.NSControlStateValueOff)
        switch.setTarget_(self)
        switch.setAction_(action)
        row.addSubview_(switch)
        return row

    # ------------------------------------------------------- settings + updates

    def _build_footer_blocks(self, hide_not_installed: bool) -> list:
        """Same top-down (kind, payload, height) block list the row list
        uses: Sync Now, then the update banner (only while a newer version is
        pending - the highest-priority signal in the footer, so it isn't
        hidden behind a closed accordion), then the collapsible Settings
        disclosure, then Quit."""
        blocks = [
            ("separator", None, SEP_H),
            ("action_button", ("Sync Now", "syncNowClicked:"), FOOTER_ROW_H),
        ]
        if self._pending_update is not None:
            blocks.append(("update_banner", self._pending_update, UPDATE_BANNER_H))
        blocks.append(("settings_header", None, FOOTER_ROW_H))
        if self._settings_open:
            blocks.append(("switch", ("Start at Login", autostart.is_enabled(), "toggleStartAtLogin:"), FOOTER_ROW_H))
            blocks.append(("switch", ("Auto-update", settings.is_auto_update_enabled(), "toggleAutoUpdate:"), FOOTER_ROW_H))
            blocks.append(("version_label", None, VERSION_ROW_H))
            blocks.append(("check_updates_button", None, CHECK_UPDATES_ROW_H))
            blocks.append(("switch", ("Hide not installed", hide_not_installed, "toggleHideNotInstalled:"), FOOTER_ROW_H))
            blocks.append(("action_button", ("About / Documentation", "openDocumentation:"), FOOTER_ROW_H))
        blocks.append(("separator", None, SEP_H))
        blocks.append(("action_button", ("Quit", "quitClicked:"), FOOTER_ROW_H))
        return blocks

    def _build_footer_block(self, kind: str, payload, y: float, h: float) -> "AppKit.NSView | None":
        if kind == "separator":
            return _separator(Foundation.NSMakeRect(MARGIN, y + 4, WIDTH - 2 * MARGIN, 1))
        if kind == "action_button":
            title, action = payload
            return self._build_action_button(title, action, y)
        if kind == "switch":
            title, on, action = payload
            return self._build_switch_row(title, on, action, y)
        if kind == "settings_header":
            return self._build_settings_header(y)
        if kind == "version_label":
            return self._build_version_label(y)
        if kind == "check_updates_button":
            return self._build_check_updates_button(y)
        if kind == "update_banner":
            return self._build_update_banner_view(payload, y, h)
        return None

    def _build_settings_header(self, y: float) -> "AppKit.NSButton":
        # A borderless button rather than a plain label so the whole row is
        # one click target for expanding/collapsing the accordion.
        caret = "▾" if self._settings_open else "▸"
        btn = AppKit.NSButton.alloc().initWithFrame_(Foundation.NSMakeRect(MARGIN, y + (FOOTER_ROW_H - 20) / 2, WIDTH - 2 * MARGIN, 20))
        btn.setTitle_(f"{caret}  Settings")
        btn.setBordered_(False)
        btn.setAlignment_(AppKit.NSTextAlignmentLeft)
        btn.setFont_(AppKit.NSFont.systemFontOfSize_(12.5))
        btn.setTarget_(self)
        btn.setAction_("toggleSettingsSection:")
        return btn

    def _build_version_label(self, y: float) -> "AppKit.NSTextField":
        text = getattr(self, "_version_status_text", None) or f"Version {__version__}"
        return _label(
            text,
            Foundation.NSMakeRect(MARGIN, y + 2, WIDTH - 2 * MARGIN, 14),
            size=10,
            color=AppKit.NSColor.secondaryLabelColor(),
        )

    def _build_check_updates_button(self, y: float) -> "AppKit.NSButton":
        btn = AppKit.NSButton.alloc().initWithFrame_(Foundation.NSMakeRect(MARGIN, y + 2, WIDTH - 2 * MARGIN, 24))
        btn.setTitle_("Check for Updates")
        btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        btn.setFont_(AppKit.NSFont.systemFontOfSize_(11))
        btn.setTarget_(self)
        btn.setAction_("checkForUpdatesClicked:")
        return btn

    def _build_update_banner_view(self, info, y: float, h: float) -> "AppKit.NSView":
        banner = AppKit.NSBox.alloc().initWithFrame_(Foundation.NSMakeRect(MARGIN, y + 4, WIDTH - 2 * MARGIN, h - 8))
        banner.setBoxType_(AppKit.NSBoxCustom)
        banner.setBorderType_(AppKit.NSNoBorder)
        banner.setFillColor_(AppKit.NSColor.quaternaryLabelColor())
        banner.setCornerRadius_(8)

        content = banner.contentView()
        inner_w = WIDTH - 2 * MARGIN - 16
        content.addSubview_(
            _label(
                f"Update available: v{info.version} (have {__version__})",
                Foundation.NSMakeRect(8, h - 8 - 20, inner_w, 16),
                size=11,
                color=AppKit.NSColor.controlAccentColor(),
            )
        )
        update_btn = AppKit.NSButton.alloc().initWithFrame_(Foundation.NSMakeRect(8, 8, inner_w * 0.62, 24))
        update_btn.setTitle_(f"Update Now (v{info.version})")
        update_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        update_btn.setFont_(AppKit.NSFont.boldSystemFontOfSize_(11))
        update_btn.setTarget_(self)
        update_btn.setAction_("updateNowClicked:")
        content.addSubview_(update_btn)

        skip_btn = AppKit.NSButton.alloc().initWithFrame_(
            Foundation.NSMakeRect(8 + inner_w * 0.62 + 8, 8, inner_w * 0.38 - 8, 24)
        )
        skip_btn.setTitle_("Skip")
        skip_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        skip_btn.setFont_(AppKit.NSFont.systemFontOfSize_(11))
        skip_btn.setTarget_(self)
        skip_btn.setAction_("skipVersionClicked:")
        content.addSubview_(skip_btn)

        return banner


class MacPopoverApp:
    """Entrypoint used by mcp_sync.app when running on macOS."""

    def run(self) -> None:
        app = AppKit.NSApplication.sharedApplication()
        app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
        controller = MCPMenuBarController.alloc().initApp()
        controller.start()
        self._controller = controller  # keep a strong Python-side reference
        AppHelper.runEventLoop()
