# MCP Sync

A tiny, always-on **menu bar / system tray app** that keeps your **MCP
(Model Context Protocol) server configuration** in sync across every AI
coding tool installed on your machine — Codex, Claude Code, Cursor, Gemini
CLI, GitHub Copilot CLI, VS Code, OpenCode, Windsurf, Antigravity, Zed,
Continue, Roo Code, Claude Desktop, Cline, Kilo Code, Zoo Code, Amp, Kiro,
Amazon Q, Goose, Warp, Trae, LM Studio and Grok.

Runs on **macOS (Apple Silicon and Intel), Ubuntu/Linux, and Windows**.

![status](https://img.shields.io/badge/status-active-brightgreen)

## Why

Every one of these tools stores its own list of MCP servers in its own
config file, in its own format. Add an MCP server in one tool and it simply
doesn't exist in the others. MCP Sync watches all of these files, merges
the servers it finds, and writes the merged set back to every tool — in
each tool's native format — so you only ever need to add a server once.

## What it looks like

- A small "MCP" wordmark + sync-arrows icon lives in your menu bar (macOS) /
  system tray (Windows, Linux) at all times, and starts automatically at
  login. It turns green while a sync pass is actively running.
- **On macOS**, clicking it opens a native popover panel (not a plain OS
  menu) with a search field right under the last-sync time — type to filter
  the list by tool name or by company (e.g. typing "google" finds Gemini
  CLI and Antigravity). Tools are listed alphabetically by name; each row
  shows its own logo, the tool name prominently, and — discreetly, in small
  gray text with a tiny logo — the company that makes it (e.g. Claude Code
  shows "Anthropic" underneath), plus its MCP server count, a status dot,
  and an on/off switch:
  - 🟢 green dot — installed, enabled, and fully in sync
  - ⚪ gray dot — installed and enabled, but a sync is pending (resolves on
    the next pass, normally within a couple of seconds)
  - ⚫ black dot — installed but **you turned sync off** for this tool
  - Tools that aren't installed on this machine are listed separately and
    skipped entirely.

  Flipping a tool's switch off/on, or typing in the search field, **keeps
  the panel open** and updates in place — it doesn't close the way a
  normal menu would. Clicking anywhere outside the panel closes it.
- **On Windows/Linux**, the same information is shown via the native tray
  menu (pystray); as is standard for OS tray menus there, it closes after a
  click, and reflects the new state the next time you open it.
- "Sync Now" forces an immediate pass. "Start at Login" toggles the
  OS-level autostart entry.

## How syncing works

1. On startup, and whenever any watched config file changes (instant, via
   filesystem events) or every 60 seconds as a safety net, MCP Sync reads
   the MCP server list from every **enabled** and **detected** tool.
2. It merges all servers into one set. If the same server name exists in
   more than one tool with different settings, **the most recently edited
   file wins** for that server.
3. It writes the merged set back into every enabled/detected tool's config
   file, translated into that tool's native schema — without touching any
   of that file's other settings (VS Code's `inputs`, Claude's other keys,
   etc. are preserved as-is).
4. A file is only re-written if its content actually needs to change, so
   this never triggers false "file modified" notifications elsewhere and
   never spams your disk with writes.

Nothing is ever sent over the network — this only reads/writes local files
already on your machine.

## Supported tools and config paths

| Tool | macOS | Linux | Windows |
|---|---|---|---|
| Codex | `~/.codex/config.toml` | `~/.codex/config.toml` | `%USERPROFILE%\.codex\config.toml` |
| Claude Code | `~/.claude.json` | `~/.claude.json` | `%USERPROFILE%\.claude.json` |
| Cursor | `~/.cursor/mcp.json` | `~/.cursor/mcp.json` | `%USERPROFILE%\.cursor\mcp.json` |
| Gemini CLI | `~/.gemini/settings.json` | `~/.gemini/settings.json` | `%USERPROFILE%\.gemini\settings.json` |
| GitHub Copilot CLI | `~/.copilot/mcp-config.json` | `~/.copilot/mcp-config.json` | `%USERPROFILE%\.copilot\mcp-config.json` |
| Visual Studio Code | `~/Library/Application Support/Code/User/mcp.json` | `~/.config/Code/User/mcp.json` | `%APPDATA%\Code\User\mcp.json` |
| OpenCode | `~/.config/opencode/opencode.json` | `~/.config/opencode/opencode.json` | `%LOCALAPPDATA%\opencode\opencode.json` |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` | `~/.codeium/windsurf/mcp_config.json` | `%USERPROFILE%\.codeium\windsurf\mcp_config.json` |
| Antigravity | `~/.gemini/config/mcp_config.json` | `~/.gemini/config/mcp_config.json` | `%USERPROFILE%\.gemini\config\mcp_config.json` |
| Zed | `~/.config/zed/settings.json` | `~/.config/zed/settings.json` | `%APPDATA%\Zed\settings.json` |
| Continue | `~/.continue/config.json` | `~/.continue/config.json` | `%USERPROFILE%\.continue\config.json` |
| Roo Code | `~/Library/Application Support/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings/mcp_settings.json` | `~/.config/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings/mcp_settings.json` | `%APPDATA%\Code\User\globalStorage\rooveterinaryinc.roo-cline\settings\mcp_settings.json` |
| Claude Desktop | `~/Library/Application Support/Claude/claude_desktop_config.json` | *(not supported by Claude Desktop on Linux)* | `%APPDATA%\Claude\claude_desktop_config.json` |
| Cline | `~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json` | `~/.config/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json` | `%APPDATA%\Code\User\globalStorage\saoudrizwan.claude-dev\settings\cline_mcp_settings.json` |
| Cline (CLI) | `~/.cline/data/settings/cline_mcp_settings.json` | `~/.cline/data/settings/cline_mcp_settings.json` | `%USERPROFILE%\.cline\data\settings\cline_mcp_settings.json` |
| Kilo Code | `~/Library/Application Support/Code/User/globalStorage/kilocode.kilo-code/settings/mcp_settings.json` | `~/.config/Code/User/globalStorage/kilocode.kilo-code/settings/mcp_settings.json` | `%APPDATA%\Code\User\globalStorage\kilocode.kilo-code\settings\mcp_settings.json` |
| Zoo Code | `~/Library/Application Support/Code/User/globalStorage/zoocodeorganization.zoo-code/settings/mcp_settings.json` | `~/.config/Code/User/globalStorage/zoocodeorganization.zoo-code/settings/mcp_settings.json` | `%APPDATA%\Code\User\globalStorage\zoocodeorganization.zoo-code\settings\mcp_settings.json` |
| Amp | `~/.config/amp/settings.json` | `~/.config/amp/settings.json` | `%APPDATA%\amp\settings.json` |
| Kiro | `~/.kiro/settings/mcp.json` | `~/.kiro/settings/mcp.json` | `%USERPROFILE%\.kiro\settings\mcp.json` |
| Amazon Q | `~/.aws/amazonq/mcp.json` | `~/.aws/amazonq/mcp.json` | `%USERPROFILE%\.aws\amazonq\mcp.json` |
| Goose | `~/.config/goose/config.yaml` | `~/.config/goose/config.yaml` | `%APPDATA%\Block\goose\config\config.yaml` |
| Warp | `~/.warp/.mcp.json` | `~/.warp/.mcp.json` | `%USERPROFILE%\.warp\.mcp.json` |
| Trae | `~/Library/Application Support/Trae/User/mcp.json` | `~/.config/Trae/User/mcp.json` | `%APPDATA%\Trae\User\mcp.json` |
| LM Studio | `~/.lmstudio/mcp.json` | `~/.lmstudio/mcp.json` | `%USERPROFILE%\.lmstudio\mcp.json` |
| Grok | `~/.grok/settings.json` | `~/.grok/settings.json` | `%USERPROFILE%\.grok\settings.json` |

> **Note:** Firebase Studio is not included — its MCP config
> (`.idx/mcp.json`) is strictly project-scoped with no stable global/user-level
> file to watch, so it doesn't fit this app's per-user sync model.

A tool only shows up as "installed" once MCP Sync finds real evidence it's
actually on your machine — its config file already existing, its CLI binary
on your `PATH`, its `.app` bundle in Applications, or (for VS Code
extensions like Continue/Roo Code) the extension actually being installed.
A leftover config folder alone is *not* enough evidence, specifically to
avoid the app treating an old/unrelated folder as "installed" and start
writing to it. Tools that aren't detected are listed separately (or hidden
entirely via "Hide not installed") and are never written to.

> **Note on Zed and OpenCode:** these two use meaningfully different MCP
> schemas (`context_servers` with a nested `command` object for Zed; a
> `mcp` map with `local`/`remote` types for OpenCode). MCP Sync translates
> to/from these formats on a best-effort basis for simple stdio and remote
> HTTP servers; double-check the result if you use advanced options for
> either tool.

> **Note on the logo badges:** the small provider/company icons shown in the
> macOS popover (`mcp_sync/assets/logos/`) are sourced from openly available
> icon sets — [OmniRoute's `public/providers`](https://github.com/AlyssonJalles/OmniRoute/tree/release/v3.8.51/public/providers)
> folder, with [thesvg.org](https://thesvg.org) as a fallback for the couple
> of tools missing there (Visual Studio Code, OpenCode) — used purely to
> visually identify each tool; all logos remain trademarks of their
> respective owners. Any tool without a bundled logo falls back to a small
> generated colored monogram instead (`mcp_sync/logos.py`).

## Install

### macOS
```bash
./installers/install_macos.sh
```

### Ubuntu / Linux
```bash
./installers/install_linux.sh
```
Requires a system tray/AppIndicator (enabled by default on Ubuntu's GNOME).
If the icon doesn't show up, see the note the installer prints about
`gir1.2-ayatana-appindicator3-0.1`.

### Windows
In PowerShell:
```powershell
powershell -ExecutionPolicy Bypass -File installers\install_windows.ps1
```

Each installer creates an isolated Python virtual environment under
`~/.mcp-sync/venv` (keeping the app "light" and not polluting your system
Python), registers the app to start at login, and launches it immediately.

**Uninstall**: run the matching `installers/uninstall_*` script for your OS.

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
python -m mcp_sync.app
```

Settings (which tools are disabled, last sync time) are stored in
`~/.mcp-sync/settings.json`.

## Function reference

A plain-language map of what each part of the codebase actually does, for
anyone reading the source without wanting to trace every line themselves.

### `sync_engine.py` — the sync engine itself

| Function | What it does |
|---|---|
| `merge_servers` | Takes the server lists from every enabled/detected tool and unions them into one set. Example: Cursor has `mcp1, mcp2`, VS Code has `mcp3, mcp4`, Codex has `mcp5` → merged result is `{mcp1, mcp2, mcp3, mcp4, mcp5}`. If the *same server name* exists in more than one tool with different settings, the version from whichever config file was **modified most recently wins** — the other one is discarded, not merged field-by-field. It also backfills a missing `type` on remote servers from another tool's copy, so a file that got touched for unrelated reasons (e.g. Claude Code updating its own usage stats) doesn't silently corrupt a remote server's record. |
| `run_sync` | The actual "do a sync" function. Reads every tool, calls `merge_servers`, removes any server that was deliberately deleted from the file that just changed (so it doesn't come back from another tool's copy), writes the merged set into every tool whose file differs from it, and records the last-sync timestamp. |
| `build_statuses` | Builds the list shown in the UI: for every known tool, whether it's installed, enabled, in sync, and how many servers it has. |
| `_enabled_detected_tools` | Filters the full list of known tools down to only the ones the user hasn't disabled *and* that are actually installed on this machine. |
| `_safe_read` | Reads a tool's server list; if the file is missing or corrupted, returns "no servers" instead of crashing the app. |
| `watched_paths` / `all_registry_paths` | List which config file paths the file-watcher should keep an eye on — the first only for tools currently installed, the second for *all* known tools (so a freshly-installed tool gets picked up automatically). |
| `seconds_since_last_sync` | How long ago the last sync finished — used to ignore the app's own write as a false "file changed" event. |

### `tools_registry.py` — one "translator" per tool

Each tool stores its MCP servers in a different file format and shape. This
module normalizes all of them into one common shape and back.

| Function | What it does |
|---|---|
| `build_registry` | Builds the full catalog of every supported tool (Cursor, VS Code, Claude Code, Codex, Zed, Goose, OpenCode, etc.), with its config path per OS, its adapter, and how to detect if it's installed. |
| `ToolSpec.resolved_path` | Turns a path template like `~/.cursor/mcp.json` into a real path on the current user's machine. |
| `ToolSpec.is_present` | Decides whether a tool is genuinely installed — checks for its CLI binary on `PATH`, its `.app`/`.exe` in Applications, or a VS Code extension — rather than just trusting that a leftover config folder exists. This is what stops MCP Sync from "adopting" an old, uninstalled tool's config folder. |
| `_generic_mcp_servers_key_adapter` | Adapter used by most tools (Claude Code, Cursor, Claude Desktop, Gemini CLI, Continue, Amp, Kiro, Amazon Q, Warp, LM Studio, Grok…) that all store servers the same way, under an `mcpServers`-style key. |
| `_vscode_adapter` | VS Code stores servers under `servers` (not `mcpServers`) and requires an explicit `type` field. This adapter strips the redundant `type` from local servers on read, but keeps it for remote ones — without it, Claude Code silently drops that remote server. |
| `_codex_toml_adapter` | Translates Codex's TOML `[mcp_servers.<name>]` tables to/from the common shape. |
| `_streamable_http_adapter` | Used by Roo Code, Cline, Cline (CLI), Kilo Code, and Zoo Code. They store servers the same way as the generic adapter, but their strict schema rejects a remote server whose `type` is the plain `"http"` used elsewhere in this app — they require `"streamable-http"` or `"streamableHttp"` (the exact spelling varies by tool) instead, or the whole settings file gets rejected with "Invalid MCP settings format". This adapter translates that one field on the way in and out. |
| `_zed_adapter` | Zed only supports local (stdio) servers, under a differently-nested `context_servers` structure; remote servers are simply skipped on write since Zed has no way to represent them. Rebuilds the whole section on every write, so a server removed elsewhere also disappears from Zed. |
| `_opencode_adapter` | OpenCode's `mcp` map uses `local`/`remote` types and a single `command` array (executable + args combined), unlike the common shape which keeps them separate. |
| `_goose_adapter` | Goose stores servers in a YAML `extensions` map with its own field names (`cmd`, `envs`, `uri`). |
| `_read_json`/`_write_json`, `_read_yaml`/`_write_yaml`, `_read_toml`/`_write_toml` | Safe file I/O helpers: reading returns an empty result instead of crashing on a missing/corrupt file; writing goes through a temp file first so a crash mid-write can't corrupt the real config. |

### `settings.py` — the app's own preferences

| Function | What it does |
|---|---|
| `load` / `save` | Read/write MCP Sync's own settings file (`~/.mcp-sync/settings.json`), always merged with defaults so an old settings file doesn't break after an update. |
| `is_tool_enabled` / `set_tool_enabled` | Check/set whether a specific tool should be synced at all (the on/off toggle per tool in the UI). |
| `set_start_at_login` | Turns "launch MCP Sync at login" on or off. |
| `set_hide_not_installed` | Turns on/off hiding not-installed tools from the tool list in the UI. |

### `watcher.py` — reacting to file changes instantly

| Function | What it does |
|---|---|
| `start` / `stop` | Start or stop watching every known tool's config file. Prefers the `watchdog` library for instant, low-CPU reactions; falls back to polling if it's unavailable. |
| `_start_watchdog` / `_start_polling` | The two implementations: instant filesystem events vs. checking file modification times every 5 seconds. |
| `_schedule_debounced_sync` / `_flush_pending_paths` | Groups multiple rapid file changes (e.g. an editor saving a file several times in under 1.5s) into a single sync instead of triggering one per write. |

### `app.py` / `mac_ui.py` — the tray icon and macOS popover

| Function | What it does |
|---|---|
| `main` | Entry point: uses the native macOS popover (`mac_ui.py`) when available, otherwise falls back to the cross-platform tray icon (`app.py`). |
| `run` / `start` | Turns on "start at login" if configured, starts the file watcher and the 60-second periodic sync, and runs the first sync. |
| `sync_now` | Runs one sync pass and shows a notification if anything changed or failed. |
| `_periodic_sync_loop` | Safety-net sync every 60 seconds, even with no detected file changes. |
| `_on_files_changed` | Triggered by the watcher; re-syncs and (unlike the periodic loop) notifies the user if something actually changed. |
| `_menu_items` / `_rebuild_content` | Build the list shown in the tray menu / popover: one row per tool with a status dot (🟢 synced, ⚪ out of sync, ⚫ disabled) and a server count, e.g. "Claude Code (5)". |
| `toggleTool_` | Handles clicking a tool's on/off switch: saves the preference and re-syncs. |
| `revealConfig_` | Opens the file manager at that tool's exact config file. |
| `openDocumentation_` | Opens this repo in the browser. |

### `autostart.py` — launch at login

| Function | What it does |
|---|---|
| `enable` / `disable` / `is_enabled` | Turn "start MCP Sync at login" on/off or check its state, delegating to the right OS-specific mechanism: a LaunchAgent `.plist` on macOS, a `.desktop` file on Linux, or a `Run` registry key on Windows. |

### UI & utilities

| Function | What it does |
|---|---|
| `group_for_tool` / `get_group` (`groups.py`) | Maps a tool to the company that makes it (e.g. Cursor → Anthropic-adjacent group), for grouping the tool list visually. |
| `get_badge` / `get_company_logo` (`logos.py`) | Loads a tool's or company's logo image, falling back to a generated colored monogram (e.g. "CC" for Claude Code) if no logo asset exists. |
| `build_icon` / `build_status_dot` (`tray_icon.py`) | Draws the menu-bar icon (turns green while syncing) and the small colored status dots shown next to each tool. |
| `notify` (`notifier.py`) | Shows a native OS notification (macOS banner, Linux `notify-send`, Windows toast); never throws — a failed notification is just silently skipped. |
| `home` / `expand` / `open_path_in_file_manager` (`platform_utils.py`) | Cross-platform helpers: get the home folder, expand a path template like `~/.cursor/mcp.json` into a real path, and open the file manager at a given file. |

## Versão em português

Veja [README.pt-BR.md](README.pt-BR.md) para instruções de instalação e uso
em português.

## License

MIT
