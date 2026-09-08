# MCP Sync

A tiny, always-on **menu bar / system tray app** that keeps your **MCP
(Model Context Protocol) server configuration** in sync across every AI
coding tool installed on your machine — Codex, Claude Code, Cursor, Gemini
CLI, GitHub Copilot CLI, VS Code, OpenCode, Windsurf, Antigravity, Zed,
Continue, Roo Code, Claude Desktop, Cline, Amp, Kiro, Amazon Q, Goose, Warp,
Trae, LM Studio and Grok.

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

## Versão em português

Veja [README.pt-BR.md](README.pt-BR.md) para instruções de instalação e uso
em português.

## License

MIT
