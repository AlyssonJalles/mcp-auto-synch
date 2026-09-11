"""Native Linux tray UI built directly on AppIndicator3/Ayatana + GTK3.

Why not a plain AppIndicator Gtk.Menu (what this module started as): GNOME's
AppIndicator/StatusNotifierItem support does not render your Gtk.Menu
in-process at all - it ships the menu's structure to the shell over the
`com.canonical.dbusmenu` D-Bus protocol, and the shell (its "AppIndicator and
KStatusNotifierItem Support" extension) reconstructs it using its *own*
widgets. That protocol only carries a handful of primitives per item - a text
label, an optional themed icon, a checkbox/radio toggle state, a submenu -
so any Gtk.Switch, Gtk.Image, Gtk.Button or Gtk.SearchEntry embedded in a
menu item is silently dropped; only a plain Gtk.Label survives. That's a hard
protocol limitation, not something fixable by changing the widgets.

So instead, the indicator's menu is a one-item decoy: the moment it's shown
we immediately close it and pop up a real Gtk.Window instead, styled
borderless, positioned near the top-right of the screen (GNOME doesn't
expose the indicator icon's on-screen position to third-party apps, so this
can't be placed precisely under the icon the way macOS's NSPopover is - a
real, unavoidable platform gap) and dismissed on focus-out, like a popover.
Because it's a plain window rendered by our own process, none of it goes
through dbusmenu, so Gtk.Switch/Gtk.Image/Gtk.SearchEntry all work exactly
as they do in any other GTK app - this carries the same information as the
macOS popover (see mac_ui.py): a search field, one row per tool with its
logo/status/switch/folder button, and a footer with Sync Now / Start at
Login / Hide not installed / About / Quit.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import threading

import gi

gi.require_version("Gtk", "3.0")
try:
    gi.require_version("AppIndicator3", "0.1")
    from gi.repository import AppIndicator3 as AppIndicator
except ValueError:
    gi.require_version("AyatanaAppIndicator3", "0.1")
    from gi.repository import AyatanaAppIndicator3 as AppIndicator

from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango

from . import __version__, autostart, settings, sync_engine, updater
from .groups import get_group, group_for_tool
from .logos import get_badge
from .notifier import notify
from .platform_utils import open_path_in_file_manager
from .tray_icon import build_status_dot, build_tray_icon
from .watcher import Watcher

APP_NAME = "MCP"
PERIODIC_SYNC_SECONDS = 60
SELF_WRITE_SUPPRESS_SECONDS = 3.0
UPDATE_CHECK_INTERVAL_SECONDS = 24 * 60 * 60
STARTUP_UPDATE_CHECK_DELAY_SECONDS = 30
FLASH_ICON_SECONDS = 0.6
DOCS_URL = "https://github.com/AlyssonJalles/mcp-auto-synch"
ROW_LOGO_SIZE = 28
APP_LOGO_WIDTH = 66
ROW_HEIGHT = 48  # approx height of one ToolRow, for sizing the scroll area
POPOVER_WIDTH = 340
POPOVER_MAX_LIST_HEIGHT = 420
POPOVER_MARGIN = 8
# Matches mac_ui.MARGIN - the popover's inner gutter. Every row and button
# uses it so nothing sits flush against the window edge.
MARGIN = 14


def _pil_to_pixbuf(img) -> GdkPixbuf.Pixbuf:
    img = img.convert("RGBA")
    data = img.tobytes()
    w, h = img.size
    return GdkPixbuf.Pixbuf.new_from_bytes(
        GLib.Bytes.new(data), GdkPixbuf.Colorspace.RGB, True, 8, w, h, w * 4
    )


def _dot_pixbuf(color_name: str) -> GdkPixbuf.Pixbuf:
    return _pil_to_pixbuf(build_status_dot(color_name))


def _app_logo_pixbuf() -> GdkPixbuf.Pixbuf | None:
    """Load the application wordmark at its natural aspect ratio."""
    try:
        path = os.path.join(os.path.dirname(__file__), "assets", "logos", "_mcp_synch.png")
        original = GdkPixbuf.Pixbuf.new_from_file(path)
        height = max(1, round(APP_LOGO_WIDTH * original.get_height() / original.get_width()))
        return original.scale_simple(APP_LOGO_WIDTH, height, GdkPixbuf.InterpType.BILINEAR)
    except Exception:
        return None


class ToolRow:
    """One provider row: logo, name + "<company> · N servers" subtitle,
    a folder button that reveals its config file, a status dot, and a
    switch to enable/disable it for sync. Mirrors mac_ui.py's _build_row -
    same left-to-right order (text, folder, dot, switch), all the way at
    the row's right edge."""

    def __init__(self, app: "LinuxIndicatorApp", tool_name: str):
        self._app = app
        self.tool_name = tool_name
        self._path = ""

        # A plain Gtk.Box, NOT a Gtk.MenuItem: a MenuItem reserves an
        # indent on its left for the checkmark/submenu-arrow column that
        # menus draw (which is what pushed every row's content inward and
        # kept the switches away from the right edge), and it intercepts
        # button presses to "activate" itself - swallowing clicks meant for
        # a nested Gtk.Button, which is why the folder button did nothing.
        self.item = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.item.set_hexpand(True)
        self.item.set_margin_start(MARGIN)
        self.item.set_margin_end(MARGIN)
        self.item.set_margin_top(4)
        self.item.set_margin_bottom(4)

        self._logo = Gtk.Image()
        self._logo.set_valign(Gtk.Align.CENTER)
        self.item.pack_start(self._logo, False, False, 0)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        text_box.set_valign(Gtk.Align.CENTER)
        self._name_label = Gtk.Label(xalign=0)
        self._name_label.set_ellipsize(Pango.EllipsizeMode.END)
        self._sub_label = Gtk.Label(xalign=0)
        self._sub_label.set_ellipsize(Pango.EllipsizeMode.END)
        self._sub_label.get_style_context().add_class("dim-label")
        self._sub_label.get_style_context().add_class("mcp-sync-subtitle")
        text_box.pack_start(self._name_label, False, False, 0)
        text_box.pack_start(self._sub_label, False, False, 0)
        self.item.pack_start(text_box, True, True, 0)

        self._switch = Gtk.Switch()
        self._switch.set_valign(Gtk.Align.CENTER)
        self._switch_handler = self._switch.connect("state-set", self._on_switch_toggled)
        self.item.pack_end(self._switch, False, False, 0)

        self._dot = Gtk.Image()
        self._dot.set_valign(Gtk.Align.CENTER)
        self.item.pack_end(self._dot, False, False, 0)

        self._folder_btn = Gtk.Button()
        self._folder_btn.set_relief(Gtk.ReliefStyle.NONE)
        self._folder_btn.set_valign(Gtk.Align.CENTER)
        self._folder_btn.add(Gtk.Image.new_from_icon_name("folder-symbolic", Gtk.IconSize.BUTTON))
        self._folder_btn.connect("clicked", self._on_folder_clicked)
        self.item.pack_end(self._folder_btn, False, False, 0)

    def update(self, status, is_installed: bool) -> None:
        self._path = status.path
        pixbuf = _pil_to_pixbuf(get_badge(self.tool_name)).scale_simple(
            ROW_LOGO_SIZE, ROW_LOGO_SIZE, GdkPixbuf.InterpType.BILINEAR
        )
        self._logo.set_from_pixbuf(pixbuf)

        if is_installed:
            dot_name = "green" if (status.enabled and status.in_sync) else ("gray" if status.enabled else "off")
        else:
            dot_name = "off"
        self._dot.set_from_pixbuf(_dot_pixbuf(dot_name))
        self._name_label.set_markup(f"<b>{GLib.markup_escape_text(self.tool_name)}</b>")

        group = get_group(self.tool_name)
        company = group.company if group else "Independent"
        if is_installed:
            n = status.server_count
            sub = f"{company} · {n} server{'s' if n != 1 else ''}"
        else:
            sub = f"{company} · not installed"
        self._sub_label.set_text(sub)

        self._folder_btn.set_sensitive(is_installed)
        self._folder_btn.set_tooltip_text(self._path)

        self._switch.handler_block(self._switch_handler)
        self._switch.set_active(bool(is_installed and status.enabled))
        self._switch.set_sensitive(is_installed)
        self._switch.handler_unblock(self._switch_handler)

        self.item.set_opacity(1.0 if is_installed else 0.55)
        # Deliberately no show_all() here: update() is also called by
        # _refresh_rows_in_place after every background sync, and show_all()
        # would un-hide rows the user has filtered out with the search box.
        # All child widgets exist from __init__, so the window's own
        # show_all() at build time is enough to make them visible.

    def matches(self, query: str) -> bool:
        if not query:
            return True
        return query in self.tool_name.lower() or query in group_for_tool(self.tool_name).lower()

    def _on_folder_clicked(self, _btn) -> None:
        path = self._path
        threading.Thread(target=lambda: open_path_in_file_manager(path), daemon=True).start()

    def _on_switch_toggled(self, _switch, state: bool) -> bool:
        settings.set_tool_enabled(self.tool_name, state)
        threading.Thread(target=lambda: self._app.sync_now(notify_result=False), daemon=True).start()
        return False  # let GTK apply the new visual state


class SwitchRow:
    """A footer settings row: a label plus a switch (Start at Login, Hide
    not installed)."""

    def __init__(self, label_text: str, on_toggle):
        self._on_toggle = on_toggle
        # Plain Gtk.Box for the same reasons as ToolRow.item above.
        self.item = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.item.set_hexpand(True)
        self.item.set_margin_start(MARGIN)
        self.item.set_margin_end(MARGIN)
        self.item.set_margin_top(4)
        self.item.set_margin_bottom(4)

        label = Gtk.Label(label=label_text, xalign=0)
        self.item.pack_start(label, True, True, 0)

        self._switch = Gtk.Switch()
        self._switch.set_valign(Gtk.Align.CENTER)
        self._switch.connect("state-set", self._on_state_set)
        self.item.pack_end(self._switch, False, False, 0)

    def set_active(self, active: bool) -> None:
        self._switch.set_active(active)

    def _on_state_set(self, _switch, state: bool) -> bool:
        self._on_toggle(state)
        return False


class LinuxIndicatorApp:
    """Entrypoint used by mcp_sync.app when running on Linux with a working
    AppIndicator backend."""

    def __init__(self, instance=None) -> None:
        # `instance` is the single_instance handle this process holds; a
        # later launcher click lands on it as an activation request, which
        # we answer by opening the popover (from the GTK thread - the
        # request arrives on the listener's own thread).
        self._instance = instance
        if instance is not None:
            instance.on_activate = lambda: GLib.idle_add(self._activate_from_other_instance)
        self._stop = threading.Event()
        self._watcher = Watcher(on_change=self._on_files_changed)
        self._search_query = ""
        self._rows: dict[str, ToolRow] = {}
        self._icon_path: str | None = None
        self._flash_source: int | None = None
        self._popover: Gtk.Window | None = None
        self._popover_focused = False
        self._pending_update: updater.UpdateInfo | None = None
        self._settings_expanded = False
        self._app_logo = _app_logo_pixbuf()

        self._indicator = AppIndicator.Indicator.new(
            "mcp-sync", "", AppIndicator.IndicatorCategory.APPLICATION_STATUS
        )
        self._indicator.set_title("MCP Sync")
        self._set_icon(active=False)
        self._indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)

        self._follow_system_color_scheme()
        self._install_css()

        # A one-item decoy menu - AppIndicator requires *some* menu to be
        # clickable at all, and refuses to show a genuinely empty one. The
        # shell renders this menu itself from a DBusMenu export of this
        # widget tree, not by displaying our Gtk.Menu object directly, so
        # our local "show" signal never actually fires when the user opens
        # it on their screen - only "activate" on an item does, relayed
        # back over D-Bus when it's clicked. That's the hook that opens the
        # real popover window (see module docstring for why the menu itself
        # can't carry the real content).
        self._menu = Gtk.Menu()
        open_item = Gtk.MenuItem(label="Open MCP Sync")
        open_item.connect("activate", lambda _i: GLib.idle_add(self._toggle_popover))
        self._menu.append(open_item)
        self._menu.show_all()
        self._indicator.set_menu(self._menu)

        self._search_entry = Gtk.SearchEntry()
        self._search_entry.set_placeholder_text("Search providers…")
        self._search_entry.connect("changed", self._on_search_changed)

        self._subtitle_label = Gtk.Label(xalign=0)
        self._no_match_label = Gtk.Label(xalign=0)
        self._no_match_label.get_style_context().add_class("dim-label")

        self._start_at_login_row = SwitchRow("Start at Login", self._on_toggle_start_at_login)
        self._hide_not_installed_row = SwitchRow("Hide not installed", self._on_toggle_hide_not_installed)
        self._auto_update_row = SwitchRow("Auto-update", self._on_toggle_auto_update)

    def _follow_system_color_scheme(self) -> None:
        """Makes the popover honour the desktop's light/dark preference.

        GTK3 does not do this on its own: the `color-scheme` GSetting that
        GNOME's dark-mode switch actually flips is only read automatically by
        GTK4/libadwaita apps, so a GTK3 app stays light on a dark desktop
        until it sets `gtk-application-prefer-dark-theme` for itself. Also
        subscribes to the setting so toggling the desktop theme restyles an
        already-running app, instead of only applying at launch."""
        gtk_settings = Gtk.Settings.get_default()
        if gtk_settings is None:
            return

        def apply(*_args) -> None:
            try:
                scheme = gsettings.get_string("color-scheme")
            except Exception:
                return
            gtk_settings.set_property("gtk-application-prefer-dark-theme", scheme == "prefer-dark")

        try:
            source = Gio.SettingsSchemaSource.get_default()
            if source is None or source.lookup("org.gnome.desktop.interface", True) is None:
                return  # not a GNOME-schema desktop; leave the theme alone
            gsettings = Gio.Settings.new("org.gnome.desktop.interface")
        except Exception:
            return
        self._interface_settings = gsettings  # keep alive so the signal stays connected
        gsettings.connect("changed::color-scheme", apply)
        apply()

    def _install_css(self) -> None:
        """Row spacing/sizing to read more like the macOS popover's list -
        deliberately doesn't touch colors so it doesn't fight the user's
        light/dark GTK theme the way a hardcoded palette would (see
        _follow_system_color_scheme for how that theme gets picked)."""
        css = b"""
        .mcp-sync-popover { border: 1px solid alpha(#888888, 0.35); }
        .mcp-sync-popover separator { margin: 6px 0; }
        .mcp-sync-subtitle { font-size: 90%; }
        .mcp-sync-update-banner {
            border: 1px solid alpha(#3584e4, 0.55);
            border-radius: 6px;
            padding: 8px;
        }
        .mcp-sync-update-label { font-weight: bold; }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    # ------------------------------------------------------------ lifecycle

    def run(self) -> None:
        if settings.load().get("start_at_login", True) and not autostart.is_enabled():
            autostart.enable()
        self._watcher.start()
        GLib.timeout_add_seconds(PERIODIC_SYNC_SECONDS, self._periodic_sync_tick)
        GLib.timeout_add_seconds(STARTUP_UPDATE_CHECK_DELAY_SECONDS, self._startup_update_check)
        GLib.timeout_add_seconds(UPDATE_CHECK_INTERVAL_SECONDS, self._periodic_update_check_tick)
        threading.Thread(target=lambda: self.sync_now(notify_result=False, backup=True), daemon=True).start()
        Gtk.main()

    def _periodic_sync_tick(self) -> bool:
        threading.Thread(target=lambda: self.sync_now(notify_result=False), daemon=True).start()
        return True  # keep the GLib timeout running

    # -------------------------------------------------------------- updates

    def _startup_update_check(self) -> bool:
        if settings.is_auto_update_enabled():
            threading.Thread(target=lambda: self._check_for_update(manual=False), daemon=True).start()
        return False  # one-shot

    def _periodic_update_check_tick(self) -> bool:
        if settings.is_auto_update_enabled():
            threading.Thread(target=lambda: self._check_for_update(manual=False), daemon=True).start()
        return True  # keep the GLib timeout running

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
                GLib.idle_add(self._rebuild_popover_preserving_search)
            else:
                notify(APP_NAME, "You're up to date")
        else:
            info = updater.check_for_update(__version__)
            if info is not None and info.version != settings.get_skipped_version():
                self._pending_update = info
                notify(APP_NAME, f"Update available: v{info.version}")
                GLib.idle_add(self._rebuild_popover_preserving_search)

    def _on_check_for_updates_clicked(self) -> None:
        threading.Thread(target=lambda: self._check_for_update(manual=True), daemon=True).start()

    def _on_update_now_clicked(self) -> None:
        info = self._pending_update
        if info is None:
            return
        threading.Thread(target=lambda: self._perform_update(info), daemon=True).start()

    def _perform_update(self, info) -> None:
        notify(APP_NAME, f"Downloading update v{info.version}…")
        try:
            updater.perform_update(info)  # never returns on success
        except Exception as exc:
            notify(APP_NAME, f"Update failed: {exc}")

    def _on_skip_version_clicked(self) -> None:
        if self._pending_update is not None:
            settings.set_skipped_version(self._pending_update.version)
            self._pending_update = None
            GLib.idle_add(self._rebuild_popover_preserving_search)

    def _on_toggle_auto_update(self, enabled: bool) -> None:
        settings.set_auto_update_enabled(enabled)

    def _on_settings_expander_toggled(self, expander, _param) -> None:
        self._settings_expanded = expander.get_expanded()

    # ----------------------------------------------------------------- sync

    def sync_now(
        self,
        notify_result: bool = True,
        always_notify: bool = False,
        backup: bool = False,
        changed_paths: list[str] | None = None,
    ) -> None:
        result = sync_engine.run_sync(changed_paths=changed_paths, backup=backup)
        if result.changed_tools and notify_result:
            GLib.idle_add(self._flash_icon)
        GLib.idle_add(self._refresh_rows_in_place)
        if result.error:
            notify(APP_NAME, f"Sync error: {result.error}")
        elif result.changed_tools and (notify_result or always_notify):
            notify(APP_NAME, "Synced: " + ", ".join(result.changed_tools))
        elif always_notify:
            notify(APP_NAME, "Already in sync")

    def _on_files_changed(self, changed_paths: list[str]) -> None:
        if sync_engine.seconds_since_last_sync() < SELF_WRITE_SUPPRESS_SECONDS:
            return  # our own write just triggered this event, not a real external change
        self.sync_now(notify_result=True, changed_paths=changed_paths)

    def _refresh_rows_in_place(self) -> bool:
        """Updates already-built rows' status dot/switch without tearing
        down the popover - safe to call while it's open (e.g. right after a
        background sync finishes)."""
        if self._popover is None or not self._popover.get_visible():
            # Rows belong to a popover that's closed (and whose widgets may
            # already be destroyed). Nothing to refresh - the next open
            # rebuilds the list from disk anyway.
            return False
        statuses = {s.name: s for s in sync_engine.build_statuses()}
        for name, row in list(self._rows.items()):
            status = statuses.get(name)
            if status is not None:
                row.update(status, status.installed)
        last_sync = settings.load().get("last_sync_iso")
        self._subtitle_label.set_text(f"Last sync: {last_sync}" if last_sync else "Not synced yet")
        return False

    # ----------------------------------------------------------------- icon

    def _set_icon(self, active: bool) -> None:
        old_path = self._icon_path
        fd, path = tempfile.mkstemp(prefix="mcp-sync-", suffix=".png")
        os.close(fd)
        build_tray_icon(active=active).save(path, "PNG")
        self._icon_path = path
        self._indicator.set_icon_full(path, "MCP Sync")
        if old_path:
            try:
                os.unlink(old_path)
            except OSError:
                pass

    def _flash_icon(self) -> bool:
        if self._flash_source is not None:
            GLib.source_remove(self._flash_source)
        self._set_icon(active=True)
        self._flash_source = GLib.timeout_add(
            int(FLASH_ICON_SECONDS * 1000), self._clear_flash
        )
        return False

    def _clear_flash(self) -> bool:
        self._flash_source = None
        self._set_icon(active=False)
        return False

    # -------------------------------------------------------------- popover

    def _activate_from_other_instance(self) -> bool:
        """Someone launched the app again (app grid, .desktop entry). Show
        the popover rather than toggling it - a second click on the launcher
        means "show me the app", never "hide it"."""
        self._show_popover()
        return False

    def _toggle_popover(self) -> bool:
        if self._popover is not None and self._popover.get_visible():
            self._popover.hide()
        else:
            self._show_popover()
        return False

    def _detach_persistent_widgets(self) -> None:
        """Unparents the widgets that survive across popover rebuilds
        (search entry, no-match label, the two footer switch rows) so a
        subsequent `self._popover.destroy()` doesn't recursively destroy
        them along with the rest of the old window's tree - reusing an
        already-destroyed GObject on the next build segfaults."""
        for widget in (
            self._search_entry,
            self._subtitle_label,
            self._no_match_label,
            self._start_at_login_row.item,
            self._hide_not_installed_row.item,
            self._auto_update_row.item,
        ):
            parent = widget.get_parent()
            if parent is not None:
                parent.remove(widget)

    def _show_popover(self, reset_search: bool = True) -> None:
        """Opens (or rebuilds) the popover. `reset_search=False` keeps the
        current search text and filter, for rebuilds triggered from inside
        the popover itself - opening it fresh from the tray starts clean."""
        if self._popover is not None:
            self._detach_persistent_widgets()
            self._popover.destroy()
        self._popover_focused = False
        self._popover = self._build_popover(reset_search=reset_search)
        self._popover.show_all()
        self._no_match_item.set_visible(False)
        if not reset_search and self._search_query:
            self._apply_search_filter()
        self._position_popover(self._popover)
        self._popover.present()

    def _position_popover(self, window: Gtk.Window) -> None:
        # GNOME doesn't expose the indicator icon's on-screen coordinates to
        # third-party apps (a deliberate sandboxing choice, not an
        # oversight) - there's no API call that gets us "put this under the
        # icon you just clicked" the way NSStatusItem does on macOS. The
        # top-right corner is the closest fixed approximation, since that's
        # where GNOME/Ubuntu's indicator icons live.
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        geo = monitor.get_geometry()
        width, height = window.get_size()
        x = geo.x + geo.width - width - POPOVER_MARGIN
        y = geo.y + POPOVER_MARGIN + 28  # ~top panel height
        window.move(x, y)

    def _build_popover(self, reset_search: bool = True) -> Gtk.Window:
        window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        window.set_decorated(False)
        window.set_resizable(False)
        window.set_skip_taskbar_hint(True)
        window.set_skip_pager_hint(True)
        # POPUP_MENU (and other hints implying an xdg_popup) needs a parent
        # surface under Wayland and silently fails to map at all without
        # one ("Couldn't map as window ... as popup because it doesn't have
        # a parent") - UTILITY floats like a tool panel without requiring
        # one, which is what a standalone borderless window like this needs.
        window.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        window.set_default_size(POPOVER_WIDTH, -1)
        window.get_style_context().add_class("mcp-sync-popover")
        # A brand-new window gets a spurious focus-out immediately on
        # showing (it never really had focus yet to lose) - dismissing on
        # that would close the popover the instant it appears. Only arm the
        # dismiss-on-focus-out once a real focus-in has been observed first.
        window.connect("focus-in-event", self._on_popover_focus_in)
        window.connect("focus-out-event", self._on_popover_focus_out)
        window.connect("key-press-event", self._on_popover_key_press)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.set_hexpand(True)
        window.add(root)

        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        header_box.set_margin_start(MARGIN)
        header_box.set_margin_end(MARGIN)
        header_box.set_margin_top(12)
        header_box.set_margin_bottom(6)
        header_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        header_text.set_hexpand(True)
        title_label = Gtk.Label(xalign=0)
        title_label.set_markup('<span size="large" weight="bold">MCP Sync</span>')
        last_sync = settings.load().get("last_sync_iso")
        self._subtitle_label.set_text(f"Last sync: {last_sync}" if last_sync else "Not synced yet")
        self._subtitle_label.get_style_context().add_class("dim-label")
        self._subtitle_label.get_style_context().add_class("mcp-sync-subtitle")
        header_text.pack_start(title_label, False, False, 0)
        if self._subtitle_label.get_parent() is not None:
            self._subtitle_label.get_parent().remove(self._subtitle_label)
        header_text.pack_start(self._subtitle_label, False, False, 0)
        header_box.pack_start(header_text, True, True, 0)
        if self._app_logo is not None:
            app_logo = Gtk.Image.new_from_pixbuf(self._app_logo)
            app_logo.set_valign(Gtk.Align.START)
            header_box.pack_end(app_logo, False, False, 0)
        root.pack_start(header_box, False, False, 0)

        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        search_box.set_margin_start(MARGIN)
        search_box.set_margin_end(MARGIN)
        search_box.set_margin_bottom(8)
        if self._search_entry.get_parent() is not None:
            self._search_entry.get_parent().remove(self._search_entry)
        search_box.pack_start(self._search_entry, True, True, 0)
        root.pack_start(search_box, False, False, 0)
        root.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0)

        self._rows.clear()
        list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        list_box.set_hexpand(True)
        statuses = sync_engine.build_statuses()
        hide_not_installed = settings.load().get("hide_not_installed", True)
        rows = sorted(
            (s for s in statuses if s.installed or not hide_not_installed),
            key=lambda s: s.name.lower(),
        )
        for status in rows:
            row = ToolRow(self, status.name)
            row.update(status, status.installed)
            self._rows[status.name] = row
            list_box.pack_start(row.item, False, False, 0)

        self._no_match_item = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._no_match_item.set_margin_start(MARGIN)
        self._no_match_item.set_margin_end(MARGIN)
        self._no_match_item.set_margin_top(8)
        self._no_match_item.set_margin_bottom(8)
        if self._no_match_label.get_parent() is not None:
            self._no_match_label.get_parent().remove(self._no_match_label)
        self._no_match_item.pack_start(self._no_match_label, True, True, 0)
        self._no_match_item.set_visible(False)
        list_box.pack_start(self._no_match_item, False, False, 0)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_max_content_height(POPOVER_MAX_LIST_HEIGHT)
        scroller.set_propagate_natural_height(True)
        scroller.set_hexpand(True)
        # A ScrolledWindow's *minimum* height is a single line, and that (not
        # its natural height) is what gets allocated whenever the surrounding
        # window is sized to its minimum - collapsing the whole provider list
        # to one visible row. Asking for the real list height up front, capped
        # at the scroll limit, keeps every row visible until there are enough
        # of them to actually need scrolling.
        scroller.set_min_content_height(min(len(rows) * ROW_HEIGHT, POPOVER_MAX_LIST_HEIGHT))
        scroller.add(list_box)
        root.pack_start(scroller, False, False, 0)

        root.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0)

        root.pack_start(
            self._action_button(
                "Sync Now",
                lambda: threading.Thread(
                    target=lambda: self.sync_now(notify_result=True, always_notify=True, backup=True),
                    daemon=True,
                ).start(),
            ),
            False,
            False,
            0,
        )

        if self._pending_update is not None:
            update_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            update_box.set_margin_start(MARGIN)
            update_box.set_margin_end(MARGIN)
            update_box.set_margin_top(4)
            update_box.set_margin_bottom(4)
            update_box.get_style_context().add_class("mcp-sync-update-banner")

            update_label = Gtk.Label(
                label=f"Update available: v{self._pending_update.version}", xalign=0
            )
            update_label.get_style_context().add_class("mcp-sync-update-label")
            update_box.pack_start(update_label, False, False, 0)

            update_box.pack_start(
                self._action_button(
                    f"Update Now (v{self._pending_update.version})",
                    self._on_update_now_clicked,
                ),
                False,
                False,
                0,
            )
            update_box.pack_start(
                self._action_button("Skip This Version", self._on_skip_version_clicked),
                False,
                False,
                0,
            )
            root.pack_start(update_box, False, False, 0)

        settings_expander = Gtk.Expander(label="Settings")
        settings_expander.set_margin_start(MARGIN)
        settings_expander.set_margin_end(MARGIN)
        settings_expander.set_margin_top(4)
        settings_expander.set_margin_bottom(4)
        settings_expander.set_expanded(self._settings_expanded)
        settings_expander.connect("notify::expanded", self._on_settings_expander_toggled)
        settings_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        if self._start_at_login_row.item.get_parent() is not None:
            self._start_at_login_row.item.get_parent().remove(self._start_at_login_row.item)
        self._start_at_login_row.set_active(autostart.is_enabled())
        settings_box.pack_start(self._start_at_login_row.item, False, False, 0)

        if self._auto_update_row.item.get_parent() is not None:
            self._auto_update_row.item.get_parent().remove(self._auto_update_row.item)
        self._auto_update_row.set_active(settings.is_auto_update_enabled())
        settings_box.pack_start(self._auto_update_row.item, False, False, 0)

        version_label = Gtk.Label(label=f"Version {__version__}", xalign=0)
        version_label.set_margin_start(MARGIN)
        version_label.set_margin_end(MARGIN)
        version_label.get_style_context().add_class("dim-label")
        version_label.get_style_context().add_class("mcp-sync-subtitle")
        settings_box.pack_start(version_label, False, False, 0)

        settings_box.pack_start(self._action_button("Check for Updates", self._on_check_for_updates_clicked), False, False, 0)

        if self._hide_not_installed_row.item.get_parent() is not None:
            self._hide_not_installed_row.item.get_parent().remove(self._hide_not_installed_row.item)
        self._hide_not_installed_row.set_active(hide_not_installed)
        settings_box.pack_start(self._hide_not_installed_row.item, False, False, 0)

        settings_box.pack_start(self._action_button("About / Documentation", self._open_documentation), False, False, 0)
        settings_expander.add(settings_box)
        root.pack_start(settings_expander, False, False, 0)
        root.pack_start(self._action_button("Quit", self._quit), False, False, 0)

        if reset_search:
            self._search_entry.set_text("")
            self._search_query = ""
        return window

    def _action_button(self, label: str, on_click) -> Gtk.Button:
        """A full-width footer button with the popover's gutter on both
        sides - the counterpart of mac_ui._build_action_button (an NSButton
        inset by MARGIN), rather than a menu row flush to the window edge."""
        btn = Gtk.Button(label=label)
        btn.set_margin_start(MARGIN)
        btn.set_margin_end(MARGIN)
        btn.set_margin_top(4)
        btn.set_margin_bottom(4)
        btn.connect("clicked", lambda _b: on_click())
        return btn

    def _on_popover_key_press(self, _widget, event) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            self._popover.hide()
            return True
        return False

    def _on_popover_focus_in(self, _widget, _event) -> bool:
        self._popover_focused = True
        return False

    def _on_popover_focus_out(self, _widget, _event) -> bool:
        if self._popover_focused:
            self._popover_focused = False
            self._popover.hide()
        return False

    def _on_search_changed(self, entry) -> None:
        self._search_query = (entry.get_text() or "").strip().lower()
        self._apply_search_filter()

    def _apply_search_filter(self) -> None:
        any_visible = False
        for row in self._rows.values():
            visible = row.matches(self._search_query)
            row.item.set_visible(visible)
            any_visible = any_visible or visible
        self._no_match_label.set_text(f'No provider matches "{self._search_query}"')
        self._no_match_item.set_visible(bool(self._search_query) and not any_visible)

    def _on_toggle_start_at_login(self, enabled: bool) -> None:
        if enabled:
            autostart.enable()
        else:
            autostart.disable()
        settings.set_start_at_login(enabled)

    def _on_toggle_hide_not_installed(self, hidden: bool) -> None:
        settings.set_hide_not_installed(hidden)
        # The row list is built once per popover from this setting, so saving
        # it isn't enough - without rebuilding, the not-installed providers
        # only appear the next time the popover is opened from scratch (the
        # macOS popover calls _rebuild_content here for the same reason).
        # Deferred to an idle callback because this runs inside the switch's
        # own signal handler, and the rebuild destroys the window that switch
        # currently lives in.
        GLib.idle_add(self._rebuild_popover_preserving_search)

    def _rebuild_popover_preserving_search(self) -> bool:
        if self._popover is None or not self._popover.get_visible():
            return False
        self._show_popover(reset_search=False)
        return False

    def _open_documentation(self) -> None:
        try:
            subprocess.run(["xdg-open", DOCS_URL], check=False)
        except Exception:
            pass

    def _quit(self) -> None:
        self._stop.set()
        self._watcher.stop()
        Gtk.main_quit()
