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

from . import autostart, settings, sync_engine
from .groups import get_group, group_for_tool
from .logos import get_badge, get_company_logo
from .notifier import notify
from .platform_utils import open_path_in_file_manager
from .tray_icon import build_icon, build_status_dot
from .watcher import Watcher

APP_NAME = "MCP"
PERIODIC_SYNC_SECONDS = 60
SELF_WRITE_SUPPRESS_SECONDS = 3.0
MENUBAR_ICON_POINT_HEIGHT = 18.0  # standard macOS menu bar glyph height
FLASH_ICON_SECONDS = 0.6  # how long the icon stays green after an actual write

WIDTH = 320
ROW_H = 44
HEADER_H = 50
SEARCH_H = 26
FOOTER_ROW_H = 36
SEP_H = 9
MARGIN = 14
MAX_POPOVER_HEIGHT = 780
LIST_VIEWPORT_HEIGHT = 440


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

    def openDocumentation_(self, sender) -> None:
        url = Foundation.NSURL.URLWithString_("https://github.com/AlyssonJalles/mcp-auto-synch")
        AppKit.NSWorkspace.sharedWorkspace().openURL_(url)

    def quitClicked_(self, sender) -> None:
        self._stop.set()
        self._watcher.stop()
        AppKit.NSApplication.sharedApplication().terminate_(self)

    # --------------------------------------------------------- view builder

    def _ensure_chrome(self) -> None:
        """Builds the parts of the UI that must never be destroyed/recreated
        (title, subtitle, search field) exactly once. Recreating a focused
        NSTextField's superview chain on every keystroke is what used to make
        the search box disappear while typing - now only its *frame* moves,
        and its window/superview identity never changes."""
        if self._chrome_built:
            return
        self._root_view = AppKit.NSView.alloc().initWithFrame_(Foundation.NSMakeRect(0, 0, WIDTH, 10))
        self._title_label = _label("MCP Sync", Foundation.NSMakeRect(MARGIN, 0, WIDTH - 2 * MARGIN, 20), size=15, bold=True)
        self._subtitle_label = _label(
            "", Foundation.NSMakeRect(MARGIN, 0, WIDTH - 2 * MARGIN, 16), size=11, color=AppKit.NSColor.secondaryLabelColor()
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
        for subview in (self._title_label, self._subtitle_label, self._search_field, self._top_separator, self._list_scroll, self._footer_view):
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
        footer_h = SEP_H + FOOTER_ROW_H * 5
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

        footer_y = footer_h
        footer_y -= SEP_H
        self._footer_view.addSubview_(_separator(Foundation.NSMakeRect(MARGIN, footer_y + 4, WIDTH - 2 * MARGIN, 1)))
        footer_y -= FOOTER_ROW_H
        self._footer_view.addSubview_(self._build_action_button("Sync Now", "syncNowClicked:", footer_y))
        footer_y -= FOOTER_ROW_H
        self._footer_view.addSubview_(self._build_switch_row("Start at Login", autostart.is_enabled(), "toggleStartAtLogin:", footer_y))
        footer_y -= FOOTER_ROW_H
        self._footer_view.addSubview_(self._build_switch_row("Hide not installed", hide_not_installed, "toggleHideNotInstalled:", footer_y))
        footer_y -= FOOTER_ROW_H
        self._footer_view.addSubview_(self._build_action_button("About / Documentation", "openDocumentation:", footer_y))
        footer_y -= FOOTER_ROW_H
        self._footer_view.addSubview_(self._build_action_button("Quit", "quitClicked:", footer_y))
        self._footer_view.setFrame_(Foundation.NSMakeRect(0, 0, WIDTH, footer_h))

        total_h = min(MAX_POPOVER_HEIGHT, HEADER_H + SEARCH_H + 6 + SEP_H + LIST_VIEWPORT_HEIGHT + footer_h)

        y2 = total_h
        y2 -= HEADER_H
        self._title_label.setFrame_(Foundation.NSMakeRect(MARGIN, y2 + 24, WIDTH - 2 * MARGIN, 20))
        last_sync = settings.load().get("last_sync_iso")
        self._subtitle_label.setStringValue_(f"Last sync: {last_sync}" if last_sync else "Not synced yet")
        self._subtitle_label.setFrame_(Foundation.NSMakeRect(MARGIN, y2 + 4, WIDTH - 2 * MARGIN, 16))

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


class MacPopoverApp:
    """Entrypoint used by mcp_sync.app when running on macOS."""

    def run(self) -> None:
        app = AppKit.NSApplication.sharedApplication()
        app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
        controller = MCPMenuBarController.alloc().initApp()
        controller.start()
        self._controller = controller  # keep a strong Python-side reference
        AppHelper.runEventLoop()
