"""Native Windows tray UI: pystray tray icon + Tkinter popup window.

Threading model (the important part): Tkinter is not thread-safe and on
Windows its event loop must own the main thread, so the roles are inverted
compared to the other platforms - Tkinter's mainloop runs in the main thread
with a hidden root window, and pystray's icon loop runs in a background
thread. Tray callbacks fire on pystray's thread, so every UI action is
marshalled back with root.after(0, ...) instead of touching widgets directly.

Left-clicking (or double-clicking) the tray icon opens a borderless dark
popup positioned near the system tray, styled to match the macOS popover:
search field, tool rows with logos/status dots/toggles, and a footer.
It dismisses itself on focus loss.
"""
from __future__ import annotations

import os
import subprocess
import threading
import tkinter as tk
from typing import Optional

import pystray

from . import __version__, autostart, settings, sync_engine, updater
from .groups import group_for_tool
from .logos import get_badge
from .notifier import notify
from .platform_utils import open_path_in_file_manager
from .tray_icon import build_status_dot, build_toggle, build_windows_tray_icon
from .watcher import Watcher

APP_NAME = "MCP"
DOCS_URL = "https://github.com/AlyssonJalles/mcp-auto-synch"
PERIODIC_SYNC_SECONDS = 60
SELF_WRITE_SUPPRESS_SECONDS = 3.0
UPDATE_CHECK_INTERVAL_SECONDS = 24 * 60 * 60
STARTUP_UPDATE_CHECK_DELAY_SECONDS = 30

# --- palette (matches the dark popover in the macOS build) ---
BG = "#1c1c1e"
BG2 = "#2c2c2e"
BG3 = "#3a3a3c"
FG = "#ffffff"
FG_DIM = "#8e8e93"
ACCENT = "#c97358"  # copper brand color
GREEN = "#30d158"
TOGGLE_OFF = "#48484a"
BORDER = "#3a3a3c"
DISABLED_FG = "#5a5a5e"  # dimmed text on not-installed rows

POPUP_W = 360
ROW_H = 52
LOGO_SIZE = 28
APP_LOGO_SIZE = 66
APP_LOGO_PNG = os.path.join(
    os.path.dirname(__file__), "assets", "logos", "_mcp_synch.png")
MAX_LIST_H = 420
TASKBAR_GAP = 48


def _pil_to_photo(img, size: int):
    from PIL import Image, ImageTk

    return ImageTk.PhotoImage(img.resize((size, size), Image.LANCZOS))


_toggle_photos: dict = {}


def _toggle_image(on: bool, enabled: bool):
    """Cached PhotoImage for a switch state. The cache is also what keeps the
    images alive - Tkinter drops an image the moment its last Python
    reference goes, leaving a blank widget."""
    key = (on, enabled)
    if key not in _toggle_photos:
        from PIL import ImageTk

        _toggle_photos[key] = ImageTk.PhotoImage(build_toggle(on, enabled))
    return _toggle_photos[key]


class Toggle(tk.Label):
    """iOS-style on/off switch - Tkinter ships no such widget.

    Backed by a Pillow-rendered image rather than Canvas shapes because the
    Canvas primitives don't antialias (see tray_icon.build_toggle)."""

    def __init__(self, parent, value: bool, on_change, bg=BG, enabled: bool = True):
        super().__init__(parent, bg=bg, borderwidth=0, highlightthickness=0,
                         cursor="hand2" if enabled else "arrow")
        self._val = value
        self._enabled = enabled
        self._on_change = on_change
        self._render()
        if enabled:
            self.bind("<Button-1>", self._click)

    def _render(self):
        img = _toggle_image(self._val, self._enabled)
        self.configure(image=img)
        self.image = img

    def _click(self, _e):
        self._val = not self._val
        self._render()
        self._on_change(self._val)


class PopupWindow:
    """The popover. A Toplevel of the app's hidden root - never its own Tk()."""

    def __init__(self, app: "WindowsTrayApp", root: tk.Tk):
        self._app = app
        self._root = root
        self._win: Optional[tk.Toplevel] = None
        self._logo_cache: dict = {}
        self._dot_cache: dict = {}
        self._search_var: Optional[tk.StringVar] = None
        self._rows_frame: Optional[tk.Frame] = None
        # Top edge fixed the moment the popover first opens, so later growth
        # (Settings, the update banner) extends downward instead of the
        # window re-anchoring to the taskbar and displacing the tool list.
        self._anchor_y: Optional[int] = None

    @property
    def alive(self) -> bool:
        return bool(self._win and self._win.winfo_exists())

    def open(self):
        if self.alive:
            self._win.lift()
            self._win.focus_force()
            return
        self._build()

    def close(self):
        if self.alive:
            self._win.destroy()
        self._win = None
        self._app.on_popup_closed()

    # ------------------------------------------------------------------ build

    def _build(self):
        win = tk.Toplevel(self._root)
        self._win = win
        win.overrideredirect(True)
        win.configure(bg=BG)
        win.attributes("-topmost", True)

        outer = tk.Frame(win, bg=BORDER, padx=1, pady=1)
        outer.pack(fill=tk.BOTH, expand=True)
        inner = tk.Frame(outer, bg=BG)
        inner.pack(fill=tk.BOTH, expand=True)

        self._build_header(inner)
        self._build_search(inner)
        self._build_list(inner)
        self._build_footer(inner)

        win.bind("<Escape>", lambda _e: self.close())
        win.bind("<FocusOut>", self._on_focus_out)

        win.update_idletasks()
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        h = win.winfo_reqheight()
        self._anchor_y = max(8, sh - h - TASKBAR_GAP)
        win.geometry(f"{POPUP_W}x{h}+{sw - POPUP_W - 8}+{self._anchor_y}")
        win.deiconify()
        win.lift()
        win.focus_force()

    def _on_focus_out(self, _e):
        # Focus moving to a child widget also fires this; re-check once the
        # new focus has settled and only dismiss if it left the window.
        self._win.after(120, self._maybe_close)

    def _maybe_close(self):
        if not self.alive:
            return
        try:
            if not self._win.focus_displayof():
                self.close()
        except Exception:
            self.close()

    # ----------------------------------------------------------------- header

    def _build_header(self, parent):
        f = tk.Frame(parent, bg=BG, padx=14, pady=10)
        f.pack(fill=tk.X)

        # Same artwork as the Start Menu shortcut's icon, so the popover is
        # recognizably the app the user launched.
        logo = self._app_logo()
        if logo:
            badge = tk.Label(f, image=logo, bg=BG)
            badge.image = logo
            badge.pack(side=tk.RIGHT, anchor="n")

        text = tk.Frame(f, bg=BG)
        text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(text, text="MCP Sync", font=("Segoe UI", 14, "bold"),
                 bg=BG, fg=FG).pack(anchor="w")
        last = settings.load().get("last_sync_iso") or "Never"
        self._last_lbl = tk.Label(text, text=f"Last sync: {last}",
                                  font=("Segoe UI", 9), bg=BG, fg=FG_DIM)
        self._last_lbl.pack(anchor="w")

    def _app_logo(self):
        if "app" not in self._logo_cache:
            try:
                from PIL import Image, ImageTk

                img = Image.open(APP_LOGO_PNG).convert("RGBA")
                # The wordmark is 1600x1515, not square - fitting it to a
                # square box would visibly squash it.
                w, h = img.size
                height = round(APP_LOGO_SIZE * h / w)
                img = img.resize((APP_LOGO_SIZE, height), Image.LANCZOS)
                self._logo_cache["app"] = ImageTk.PhotoImage(img)
            except Exception:
                self._logo_cache["app"] = None
        return self._logo_cache["app"]

    # ----------------------------------------------------------------- search

    def _build_search(self, parent):
        f = tk.Frame(parent, bg=BG, padx=14, pady=4)
        f.pack(fill=tk.X)
        box = tk.Frame(f, bg=BG2, highlightbackground=BG3, highlightthickness=1)
        box.pack(fill=tk.X)
        tk.Label(box, text="\U0001F50D", bg=BG2, fg=FG_DIM,
                 font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=(8, 2))
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._rebuild_rows())
        e = tk.Entry(box, textvariable=self._search_var, bg=BG2, fg=FG,
                     insertbackground=FG, relief=tk.FLAT, font=("Segoe UI", 10), bd=4)
        e.pack(fill=tk.X, padx=(0, 6))

    # ------------------------------------------------------------------- list

    def _build_list(self, parent):
        container = tk.Frame(parent, bg=BG)
        container.pack(fill=tk.BOTH, expand=True, pady=4)

        canvas = tk.Canvas(container, bg=BG, highlightthickness=0, borderwidth=0)
        sb = tk.Scrollbar(container, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._rows_frame = tk.Frame(canvas, bg=BG)
        win_id = canvas.create_window((0, 0), window=self._rows_frame, anchor="nw")

        def _on_configure(_e):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.configure(height=min(self._rows_frame.winfo_reqheight(), MAX_LIST_H))

        self._rows_frame.bind("<Configure>", _on_configure)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win_id, width=e.width))
        canvas.bind("<MouseWheel>",
                    lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))
        self._rebuild_rows()

    def _rebuild_rows(self):
        if not self._rows_frame or not self._rows_frame.winfo_exists():
            return
        for w in self._rows_frame.winfo_children():
            w.destroy()

        cfg = settings.load()
        hide_missing = cfg.get("hide_not_installed", True)
        query = (self._search_var.get() if self._search_var else "").lower()

        statuses = sorted(sync_engine.build_statuses(), key=lambda s: s.name.lower())
        for st in statuses:
            if hide_missing and not st.installed:
                continue
            if query and query not in st.name.lower():
                continue
            self._build_row(self._rows_frame, st)

        if self._last_lbl.winfo_exists():
            last = cfg.get("last_sync_iso") or "Never"
            self._last_lbl.config(text=f"Last sync: {last}")

    def _logo(self, name: str, installed: bool = True):
        key = (name, installed)
        if key not in self._logo_cache:
            try:
                img = get_badge(name)
                if not installed:
                    # Stand-in for the Linux popover's row opacity: fading the
                    # badge toward the popover background is what actually
                    # reads as "dimmed", since Tkinter composites the image
                    # against BG with no alpha blending of its own.
                    from PIL import Image

                    img = img.convert("RGBA")
                    backdrop = Image.new("RGBA", img.size, (28, 28, 30, 255))
                    img = Image.blend(backdrop, img, 0.45)
                self._logo_cache[key] = _pil_to_photo(img, LOGO_SIZE)
            except Exception:
                self._logo_cache[key] = None
        return self._logo_cache[key]

    def _dot(self, color: str):
        if color not in self._dot_cache:
            try:
                self._dot_cache[color] = _pil_to_photo(build_status_dot(color), 10)
            except Exception:
                self._dot_cache[color] = None
        return self._dot_cache[color]

    def _build_row(self, parent, st):
        # A not-installed row stays visible but reads as inert: dimmed text,
        # an "off" dot, "not installed" instead of a server count, and a
        # switch/folder button that can't be operated. (Same treatment as the
        # Linux popover's 0.55 opacity - Tkinter has no per-widget opacity,
        # so the dimming is done with muted foreground colors.)
        installed = st.installed
        name_fg = FG if installed else FG_DIM
        sub_fg = FG_DIM if installed else DISABLED_FG

        f = tk.Frame(parent, bg=BG, height=ROW_H)
        f.pack(fill=tk.X)
        f.pack_propagate(False)
        tk.Frame(f, bg=BG3, height=1).place(relx=0, rely=0, relwidth=1)

        inner = tk.Frame(f, bg=BG)
        inner.pack(fill=tk.BOTH, expand=True, padx=14, pady=6)

        logo = self._logo(st.name, installed)
        if logo:
            lbl = tk.Label(inner, image=logo, bg=BG)
            lbl.image = logo
            lbl.pack(side=tk.LEFT, padx=(0, 10))

        col = tk.Frame(inner, bg=BG)
        col.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(col, text=st.name, font=("Segoe UI", 10, "bold"),
                 bg=BG, fg=name_fg, anchor="w").pack(fill=tk.X)

        company = group_for_tool(st.name) or "Independent"
        if installed:
            n = st.server_count
            sub = f"{company} · {n} server{'s' if n != 1 else ''}"
        else:
            sub = f"{company} · not installed"
        tk.Label(col, text=sub, font=("Segoe UI", 8),
                 bg=BG, fg=sub_fg, anchor="w").pack(fill=tk.X)

        right = tk.Frame(inner, bg=BG)
        right.pack(side=tk.RIGHT)

        if installed:
            dot_name = "green" if (st.enabled and st.in_sync) else ("gray" if st.enabled else "off")
        else:
            dot_name = "off"
        dot = self._dot(dot_name)
        if dot:
            d = tk.Label(right, image=dot, bg=BG)
            d.image = dot
            d.pack(side=tk.LEFT, padx=(0, 6))

        if st.path:
            tk.Button(right, text="\U0001F4C1", font=("Segoe UI", 14), bg=BG,
                      fg=FG_DIM if installed else DISABLED_FG,
                      relief=tk.FLAT, bd=0, activebackground=BG2,
                      cursor="hand2" if installed else "arrow",
                      state=tk.NORMAL if installed else tk.DISABLED,
                      disabledforeground=DISABLED_FG,
                      command=lambda p=st.path: open_path_in_file_manager(p),
                      ).pack(side=tk.LEFT, padx=(0, 8))

        def _toggled(val, name=st.name):
            settings.set_tool_enabled(name, val)
            self._app.sync_async(notify_result=False)

        Toggle(right, value=bool(installed and st.enabled), on_change=_toggled,
               enabled=installed).pack(side=tk.LEFT)

    # ----------------------------------------------------------------- footer

    def _build_footer(self, parent):
        tk.Frame(parent, bg=BG3, height=1).pack(fill=tk.X, pady=(4, 0))
        f = tk.Frame(parent, bg=BG, padx=14, pady=10)
        f.pack(fill=tk.X)

        self._sync_btn = tk.Button(
            f, text="Sync Now", font=("Segoe UI", 10), bg=BG3, fg=FG,
            activebackground=BG2, activeforeground=FG, relief=tk.FLAT,
            bd=0, pady=6, cursor="hand2", command=self._on_sync_now)
        self._sync_btn.pack(fill=tk.X, pady=(0, 8))

        self._build_settings_section(f, settings.load())
        self._build_update_banner(f)

        tk.Frame(f, bg=BG3, height=1).pack(fill=tk.X, pady=(8, 4))

        tk.Button(f, text="Quit", font=("Segoe UI", 10), bg=BG3, fg=FG,
                  activebackground=BG2, activeforeground=FG, relief=tk.FLAT,
                  bd=0, pady=6, cursor="hand2",
                  command=self._app.quit).pack(fill=tk.X)

    def _build_settings_section(self, parent, cfg):
        """Collapsible 'Settings' disclosure holding the less-used switches.

        Header and body live in a container of their own so that expanding
        keeps them together: packing the body straight into the footer would
        append it at the end of the pack order - i.e. below Quit - because
        the body is packed on expand, after Quit already claimed its slot."""
        section = tk.Frame(parent, bg=BG)
        section.pack(fill=tk.X)
        self._settings_section = section

        header = tk.Frame(section, bg=BG, cursor="hand2")
        header.pack(fill=tk.X, pady=(6, 0))
        self._settings_caret = tk.Label(
            header, text="▸", font=("Segoe UI", 9), bg=BG, fg=FG_DIM)
        self._settings_caret.pack(side=tk.LEFT, padx=(0, 6))
        title = tk.Label(header, text="Settings", font=("Segoe UI", 10),
                         bg=BG, fg=FG)
        title.pack(side=tk.LEFT)

        body = tk.Frame(section, bg=BG)
        self._settings_body = body
        self._settings_open = False

        for w in (header, title, self._settings_caret):
            w.bind("<Button-1>", lambda _e: self._toggle_settings())

        login_row = tk.Frame(body, bg=BG)
        login_row.pack(fill=tk.X, pady=2)
        tk.Label(login_row, text="Start at Login", font=("Segoe UI", 10),
                 bg=BG, fg=FG).pack(side=tk.LEFT)
        Toggle(login_row, value=cfg.get("start_at_login", True),
               on_change=self._on_toggle_login).pack(side=tk.RIGHT)

        row = tk.Frame(body, bg=BG)
        row.pack(fill=tk.X, pady=2)
        tk.Label(row, text="Auto-update", font=("Segoe UI", 10),
                 bg=BG, fg=FG).pack(side=tk.LEFT)
        Toggle(row, value=settings.is_auto_update_enabled(),
               on_change=self._on_toggle_auto_update).pack(side=tk.RIGHT)

        self._update_lbl = tk.Label(
            body, text=f"Version {__version__}",
            font=("Segoe UI", 8), bg=BG, fg=FG_DIM, anchor="w")
        self._update_lbl.pack(fill=tk.X)

        self._check_btn = tk.Button(
            body, text="Check for Updates", font=("Segoe UI", 9), bg=BG3, fg=FG,
            activebackground=BG2, activeforeground=FG, relief=tk.FLAT, bd=0,
            pady=4, cursor="hand2", command=self._on_check_updates)
        self._check_btn.pack(fill=tk.X, pady=(4, 2))

        row2 = tk.Frame(body, bg=BG)
        row2.pack(fill=tk.X, pady=2)
        tk.Label(row2, text="Hide not installed", font=("Segoe UI", 10),
                 bg=BG, fg=FG).pack(side=tk.LEFT)
        Toggle(row2, value=cfg.get("hide_not_installed", True),
               on_change=self._on_toggle_hide).pack(side=tk.RIGHT)

        tk.Button(body, text="About / Documentation", font=("Segoe UI", 9),
                  bg=BG3, fg=FG, activebackground=BG2, activeforeground=FG,
                  relief=tk.FLAT, bd=0, pady=4, cursor="hand2",
                  command=lambda: os.startfile(DOCS_URL)).pack(fill=tk.X, pady=(8, 0))

    def _build_update_banner(self, parent):
        """Pending-update call-to-action, packed above Settings instead of
        inside it - the highest-priority signal in the footer shouldn't be
        hidden behind a closed accordion. Built once and packed/forgotten as
        a pending update comes and goes (see _sync_update_buttons)."""
        self._update_banner = tk.Frame(parent, bg=BG2, padx=10, pady=8)

        self._update_banner_lbl = tk.Label(
            self._update_banner, text="", font=("Segoe UI", 9), bg=BG2,
            fg=ACCENT, anchor="w")
        self._update_banner_lbl.pack(fill=tk.X)

        btn_row = tk.Frame(self._update_banner, bg=BG2)
        btn_row.pack(fill=tk.X, pady=(6, 0))

        self._update_now_btn = tk.Button(
            btn_row, text="Update Now", font=("Segoe UI", 9, "bold"), bg=ACCENT,
            fg="white", activebackground=ACCENT, activeforeground="white",
            relief=tk.FLAT, bd=0, pady=4, cursor="hand2",
            command=self._on_update_now)
        self._update_now_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        self._skip_btn = tk.Button(
            btn_row, text="Skip", font=("Segoe UI", 9), bg=BG3,
            fg=FG_DIM, activebackground=BG2, activeforeground=FG,
            relief=tk.FLAT, bd=0, pady=4, cursor="hand2",
            command=self._on_skip_version)
        self._skip_btn.pack(side=tk.LEFT)

        self._sync_update_buttons()

    def _toggle_settings(self):
        self._settings_open = not self._settings_open
        if self._settings_open:
            self._settings_body.pack(fill=tk.X)
            self._settings_caret.config(text="▾")
        else:
            self._settings_body.pack_forget()
            self._settings_caret.config(text="▸")
        self._resize_to_fit()

    def _resize_to_fit(self):
        """Re-fit the popover, growing downward from the anchor set when it
        first opened - Settings and the update banner no longer displace the
        tool list above them. Falls back to the old bottom-anchor (re-jumping
        upward) only if growth would otherwise push the window past the
        taskbar, so it never runs off-screen or under the taskbar."""
        if not self.alive:
            return
        self._win.update_idletasks()
        h = self._win.winfo_reqheight()
        sw = self._win.winfo_screenwidth()
        sh = self._win.winfo_screenheight()
        y = self._anchor_y if self._anchor_y is not None else max(8, sh - h - TASKBAR_GAP)
        if y + h > sh - TASKBAR_GAP:
            y = max(8, sh - h - TASKBAR_GAP)
        self._win.geometry(f"{POPUP_W}x{h}+{sw - POPUP_W - 8}+{y}")

    def _sync_update_buttons(self):
        """Show the pending-update banner above Settings only while an
        update is pending."""
        info = self._app.pending_update
        if info is not None:
            self._update_now_btn.config(text=f"Update Now (v{info.version})")
            self._update_banner_lbl.config(
                text=f"Update available: v{info.version} (have {__version__})")
            self._update_banner.pack(fill=tk.X, pady=(0, 8), before=self._settings_section)
        else:
            self._update_banner.pack_forget()

    def _on_check_updates(self):
        self._check_btn.config(text="Checking…", state=tk.DISABLED)

        def work():
            try:
                info = updater.fetch_latest_release_info()
            except updater.UpdateCheckError as exc:
                self._root.after(0, self._show_check_failed, str(exc))
                return
            import datetime

            settings.set_last_update_check_iso(
                datetime.datetime.now().isoformat(timespec="seconds"))
            newer = (updater.is_newer(info.version, __version__)
                     and info.version != settings.get_skipped_version())
            self._root.after(0, self._show_check_result, info if newer else None)

        threading.Thread(target=work, daemon=True).start()

    def _show_check_failed(self, msg: str):
        if not self.alive or not self._check_btn.winfo_exists():
            return
        self._check_btn.config(text="Check for Updates", state=tk.NORMAL)
        self._update_lbl.config(text="Couldn't check — check your connection",
                                fg=FG_DIM)

    def _show_check_result(self, info):
        self._app.pending_update = info
        if not self.alive or not self._check_btn.winfo_exists():
            return
        self._check_btn.config(text="Check for Updates", state=tk.NORMAL)
        if info is None:
            self._update_lbl.config(text=f"Version {__version__} — up to date",
                                    fg=FG_DIM)
        self._sync_update_buttons()
        self._resize_to_fit()

    def _on_update_now(self):
        info = self._app.pending_update
        if info is None:
            return
        self._update_now_btn.config(text="Downloading…", state=tk.DISABLED)
        self._skip_btn.config(state=tk.DISABLED)

        def work():
            try:
                # On success this never returns: the app is replaced and this
                # process exits from inside perform_update().
                updater.perform_update(info)
            except Exception as exc:
                self._root.after(0, self._show_update_failed, str(exc))

        threading.Thread(target=work, daemon=True).start()

    def _show_update_failed(self, msg: str):
        notify(APP_NAME, f"Update failed: {msg}")
        if not self.alive or not self._update_now_btn.winfo_exists():
            return
        self._update_now_btn.config(text="Update Now", state=tk.NORMAL)
        self._skip_btn.config(state=tk.NORMAL)
        self._update_banner_lbl.config(text=f"Update failed: {msg}")

    def _on_skip_version(self):
        info = self._app.pending_update
        if info is None:
            return
        settings.set_skipped_version(info.version)
        self._app.pending_update = None
        self._update_lbl.config(text=f"Version {__version__}", fg=FG_DIM)
        self._sync_update_buttons()
        self._resize_to_fit()

    def _on_toggle_auto_update(self, val: bool):
        settings.set_auto_update_enabled(val)

    def _on_sync_now(self):
        self._sync_btn.config(text="Syncing…", state=tk.DISABLED)
        self._app.sync_async(notify_result=True, always_notify=True, backup=True,
                             done=self._after_sync)

    def _after_sync(self):
        if self.alive and self._sync_btn.winfo_exists():
            self._sync_btn.config(text="Sync Now", state=tk.NORMAL)
            self._rebuild_rows()

    def _on_toggle_login(self, val: bool):
        autostart.enable() if val else autostart.disable()
        settings.set_start_at_login(val)

    def _on_toggle_hide(self, val: bool):
        # set_hide_not_installed, not load/save: a background sync pass writes
        # last_sync_iso constantly, and a bare load/save pair would revert
        # whichever of the two landed first (see settings.update's docstring).
        settings.set_hide_not_installed(val)
        self._rebuild_rows()
        self._resize_to_fit()


class WindowsTrayApp:
    def __init__(self, instance=None):
        self._instance = instance
        self._root: Optional[tk.Tk] = None
        self._popup: Optional[PopupWindow] = None
        self._watcher = Watcher(on_change=self._on_files_changed)
        self._stop = threading.Event()
        self.pending_update: Optional[updater.UpdateInfo] = None
        self._icon = pystray.Icon(
            APP_NAME,
            build_windows_tray_icon(False),
            "MCP Sync",
            menu=pystray.Menu(
                pystray.MenuItem("Open MCP Sync", self._request_popup, default=True),
                pystray.MenuItem("Sync Now",
                                 lambda i, it: self.sync_async(notify_result=True,
                                                               always_notify=True,
                                                               backup=True)),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", lambda i, it: self.quit()),
            ),
        )

    # -------------------------------------------------------------- lifecycle

    def run(self):
        if settings.load().get("start_at_login", True) and not autostart.is_enabled():
            autostart.enable()

        # Hidden root: owns the Tkinter event loop for the process lifetime, so
        # the popup can be created and destroyed repeatedly without ever
        # starting a second mainloop.
        self._root = tk.Tk()
        self._root.withdraw()

        # A second launch (Start Menu shortcut, autostart firing while the app
        # is already up) exits immediately after poking us through here, so
        # clicking the launcher surfaces this instance instead of spawning a
        # duplicate tray icon.
        if self._instance is not None:
            self._instance.on_activate = self._request_popup

        self._watcher.start()
        threading.Thread(target=self._periodic_sync_loop, daemon=True).start()
        threading.Thread(target=self._update_check_loop, daemon=True).start()
        self.sync_async(notify_result=False, backup=True)

        # pystray owns a thread of its own; its callbacks marshal back to the
        # root via .after() (see _request_popup).
        threading.Thread(target=self._icon.run, daemon=True).start()

        self._root.mainloop()

    def quit(self):
        self._stop.set()
        self._watcher.stop()
        try:
            self._icon.stop()
        except Exception:
            pass
        if self._root:
            self._root.after(0, self._root.destroy)

    # ------------------------------------------------------------ popup access

    def _request_popup(self, icon=None, item=None):
        """Tray callback - runs on pystray's thread, so hop to Tkinter's."""
        if self._root:
            self._root.after(0, self._open_popup)

    def _open_popup(self):
        if self._popup and self._popup.alive:
            self._popup.close()
            return
        self._popup = PopupWindow(self, self._root)
        self._popup.open()

    def on_popup_closed(self):
        self._popup = None

    # ------------------------------------------------------------------- sync

    def sync_async(self, notify_result: bool = True, always_notify: bool = False,
                   backup: bool = False, done=None):
        threading.Thread(
            target=self._sync_worker,
            args=(notify_result, always_notify, backup, done),
            daemon=True,
        ).start()

    def _sync_worker(self, notify_result, always_notify, backup, done):
        self._set_icon(True)
        try:
            result = sync_engine.run_sync(backup=backup)
        finally:
            self._set_icon(False)

        if result.error:
            notify(APP_NAME, f"Sync error: {result.error}")
        elif result.changed_tools and (notify_result or always_notify):
            notify(APP_NAME, "Synced: " + ", ".join(result.changed_tools))
        elif always_notify:
            notify(APP_NAME, "Already in sync")

        if self._root:
            self._root.after(0, done or self._refresh_popup)

    def _refresh_popup(self):
        if self._popup and self._popup.alive:
            self._popup._rebuild_rows()

    def _periodic_sync_loop(self):
        while not self._stop.is_set():
            self._stop.wait(PERIODIC_SYNC_SECONDS)
            if not self._stop.is_set():
                self._sync_worker(False, False, False, None)

    def _update_check_loop(self):
        self._stop.wait(STARTUP_UPDATE_CHECK_DELAY_SECONDS)
        while not self._stop.is_set():
            if settings.is_auto_update_enabled():
                info = updater.check_for_update(__version__)
                if info is not None and info.version != settings.get_skipped_version():
                    self.pending_update = info
                    notify(APP_NAME, f"Update available: v{info.version}")
                    if self._root:
                        self._root.after(0, self._refresh_update_ui)
            self._stop.wait(UPDATE_CHECK_INTERVAL_SECONDS)

    def _refresh_update_ui(self):
        if self._popup and self._popup.alive:
            self._popup._sync_update_buttons()
            self._popup._resize_to_fit()

    def _on_files_changed(self, changed_paths: list):
        if sync_engine.seconds_since_last_sync() < SELF_WRITE_SUPPRESS_SECONDS:
            return
        self._sync_worker(True, False, False, None)

    def _set_icon(self, active: bool):
        try:
            self._icon.icon = build_windows_tray_icon(active)
        except Exception:
            pass
