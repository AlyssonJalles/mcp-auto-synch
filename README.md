<table width="100%">
<tr>
<td width="20%"><img src="mcp_sync/assets/logos/_mcp_synch.png" alt="Demonstração do aplicativo" width="100%"></td>
<td width="100%"><h1 align="left">Complete MCP Synchronization</h1></td>
</tr>
</table>

A tiny, always-on **menu bar / system tray app** that keeps your **MCP
(Model Context Protocol) server configuration** in sync across every AI
coding tool installed on your machine — VS Code, Cursor, Claude Code, Claude
Desktop, GitHub Copilot CLI, Codex, Gemini CLI, Windsurf, Cline, Continue,
Roo Code, OpenCode, Amazon Q, Warp, Zed, Amp, Kiro, Goose, Trae, Antigravity,
LM Studio, Kilo Code, Zoo Code and Grok.

Runs on **macOS (Apple Silicon and Intel), Ubuntu/Linux, and Windows**.

![status](https://img.shields.io/badge/status-active-brightgreen)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)
[![Follow Alysson On LinkedIn](https://img.shields.io/badge/Follow--Alysson-On_LinkedIn-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/alyssonjalles)
[![Follow @AlyssonJalles on GitHub](https://img.shields.io/github/followers/AlyssonJalles?style=for-the-badge&logo=github&logoColor=white&label=Follow%20on%20GitHub&color=181717)](https://github.com/AlyssonJalles)

### The interface

<table width="100%">
<tr>
<td width="26%"><img src="mcp_sync/assets/App-working.gif" alt="Demonstração do aplicativo" width="100%"></td>
<td width="40%"><img src="mcp_sync/assets/all-synch.png" alt="Demonstração do aplicativo" width="100%"></td>
</tr>
</table>

## Install

![status](mcp_sync/assets/easy-to-install-en.jpg)

### macOS / Linux — install directly from GitHub (no clone needed)

```bash
curl -fsSL https://raw.githubusercontent.com/AlyssonJalles/mcp-auto-synch/main/installers/install.sh | bash
```

This downloads the latest [GitHub Release](https://github.com/AlyssonJalles/mcp-auto-synch/releases)
wheel and installs it — same result as the scripts below, without cloning the repo.

### macOS (from a local clone)

```bash
./installers/install_macos.sh
```

### Ubuntu / Linux (from a local clone)

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

## Opening the app

The installer launches the app right away and registers it to start
automatically at every login, so most of the time there's nothing to run.
If it's not currently running, here's how to start it back up:

**macOS**

```bash
launchctl load -w ~/Library/LaunchAgents/com.mcpsync.app.plist
```

**Linux**

```bash
~/.mcp-sync/venv/bin/python3 -m mcp_sync.app &
```

**Windows**

```powershell
& "$env:USERPROFILE\.mcp-sync\venv\Scripts\pythonw.exe" -m mcp_sync.app
```

It's a menu bar / system tray app, not a window — once running, look for its
icon in the menu bar (macOS) or system tray (Windows/Linux).

**On macOS**, the installer also adds a `/Applications/MCP Sync.app` shortcut
(a symlink to the real bundle under `~/.mcp-sync`, using the same icon shown
in Activity Monitor), so the app also shows up in Launchpad and Spotlight.

## Why

Every one of these tools stores its own list of MCP servers in its own
config file, in its own format. Add an MCP server in one tool and it simply
doesn't exist in the others. MCP Sync watches all of these files, merges
the servers it finds, and writes the merged set back to every tool — in
each tool's native format — so you only ever need to add a server once.

## What it looks like

A small "MCP" icon sits in your menu bar (macOS) / system tray (Windows,
Linux), turning green while a sync pass runs. Clicking it opens a searchable
list of every tool — logo, company, MCP server count, and a status dot per
row (🟢 in sync, ⚪ sync pending, ⚫ disabled) — with an on/off switch for
each, a "Sync Now" button, and a "Start at Login" toggle.

**On macOS** this is a native popover that stays open while you flip
switches or search — it only closes on an outside click. **On Windows/Linux**
it's the standard tray menu, which closes after each click as usual.

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

## Backups

Before overwriting a tool's config file, MCP Sync can save a full copy of it
first — but only for the two moments where a bad merge would actually be
your fault to fix:

- **Right after install**, on the app's very first startup sync.
- **Every time you click "Sync Now"** in the tray menu / popover.

The silent 60-second periodic sync and the instant sync triggered by the
file watcher (when a tool edits its own config) do **not** create backups —
otherwise this folder would fill up with near-identical copies every minute.

Backups are stored at:

```
~/.mcp-sync/backups/<date>_<time>/<tool name>/<original file name>
```

e.g. `~/.mcp-sync/backups/2026-09-08_22-43-09/Cursor/mcp.json`. Every file
touched by the same backup-triggering sync shares one timestamped folder,
so you can always tell what was overwritten together. Only the 30 most
recent backup folders are kept — older ones are pruned automatically.

## Supported tools and config paths

Sorted alphabetically. Each icon is standardized to 42×42 for a tidy column
(a couple of source logos aren't perfectly square, so those are very slightly
stretched to fit).

| Tool | macOS | Linux | Windows |
|---|---|---|---|
| **Amazon Q**<br><img src="mcp_sync/assets/logos/readme/amazon-q.png" width="42" height="42"> | `~/.aws/amazonq/mcp.json` | `~/.aws/amazonq/mcp.json` | `%USERPROFILE%\.aws\amazonq\mcp.json` |
| **Amp**<br><img src="mcp_sync/assets/logos/readme/amp.png" width="42" height="42"> | `~/.config/amp/settings.json` | `~/.config/amp/settings.json` | `%APPDATA%\amp\settings.json` |
| **Antigravity**<br><img src="mcp_sync/assets/logos/readme/antigravity.png" width="42" height="42"> | `~/.gemini/config/mcp_config.json` | `~/.gemini/config/mcp_config.json` | `%USERPROFILE%\.gemini\config\mcp_config.json` |
| **Claude Code**<br><img src="mcp_sync/assets/logos/readme/claude-code.png" width="42" height="42"> | `~/.claude.json` | `~/.claude.json` | `%USERPROFILE%\.claude.json` |
| **Claude Desktop**<br><img src="mcp_sync/assets/logos/readme/claude-desktop.png" width="42" height="42"> | `~/Library/Application Support/Claude/claude_desktop_config.json` | *(not supported by Claude Desktop on Linux)* | `%APPDATA%\Claude\claude_desktop_config.json` |
| **Cline**<br><img src="mcp_sync/assets/logos/readme/cline.png" width="42" height="42"> | `~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json` | `~/.config/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json` | `%APPDATA%\Code\User\globalStorage\saoudrizwan.claude-dev\settings\cline_mcp_settings.json` |
| **Cline (CLI)**<br><img src="mcp_sync/assets/logos/readme/cline-cli.png" width="42" height="42"> | `~/.cline/data/settings/cline_mcp_settings.json` | `~/.cline/data/settings/cline_mcp_settings.json` | `%USERPROFILE%\.cline\data\settings\cline_mcp_settings.json` |
| **Codex**<br><img src="mcp_sync/assets/logos/readme/codex.png" width="42" height="42"> | `~/.codex/config.toml` | `~/.codex/config.toml` | `%USERPROFILE%\.codex\config.toml` |
| **Continue**<br><img src="mcp_sync/assets/logos/readme/continue.png" width="42" height="42"> | `~/.continue/config.json` | `~/.continue/config.json` | `%USERPROFILE%\.continue\config.json` |
| **Cursor**<br><img src="mcp_sync/assets/logos/readme/cursor.png" width="42" height="42"> | `~/.cursor/mcp.json` | `~/.cursor/mcp.json` | `%USERPROFILE%\.cursor\mcp.json` |
| **Gemini CLI**<br><img src="mcp_sync/assets/logos/readme/gemini-cli.png" width="42" height="42"> | `~/.gemini/settings.json` | `~/.gemini/settings.json` | `%USERPROFILE%\.gemini\settings.json` |
| **GitHub Copilot CLI**<br><img src="mcp_sync/assets/logos/readme/github-copilot-cli.png" width="42" height="42"> | `~/.copilot/mcp-config.json` | `~/.copilot/mcp-config.json` | `%USERPROFILE%\.copilot\mcp-config.json` |
| **Goose**<br><img src="mcp_sync/assets/logos/readme/goose.png" width="42" height="42"> | `~/.config/goose/config.yaml` | `~/.config/goose/config.yaml` | `%APPDATA%\Block\goose\config\config.yaml` |
| **Grok**<br><img src="mcp_sync/assets/logos/readme/grok.png" width="42" height="42"> | `~/.grok/settings.json` | `~/.grok/settings.json` | `%USERPROFILE%\.grok\settings.json` |
| **Kilo Code**<br><img src="mcp_sync/assets/logos/readme/kilo-code.png" width="42" height="42"> | `~/Library/Application Support/Code/User/globalStorage/kilocode.kilo-code/settings/mcp_settings.json` | `~/.config/Code/User/globalStorage/kilocode.kilo-code/settings/mcp_settings.json` | `%APPDATA%\Code\User\globalStorage\kilocode.kilo-code\settings\mcp_settings.json` |
| **Kiro**<br><img src="mcp_sync/assets/logos/readme/kiro.png" width="42" height="42"> | `~/.kiro/settings/mcp.json` | `~/.kiro/settings/mcp.json` | `%USERPROFILE%\.kiro\settings\mcp.json` |
| **LM Studio**<br><img src="mcp_sync/assets/logos/readme/lm-studio.png" width="42" height="42"> | `~/.lmstudio/mcp.json` | `~/.lmstudio/mcp.json` | `%USERPROFILE%\.lmstudio\mcp.json` |
| **OpenCode**<br><img src="mcp_sync/assets/logos/readme/opencode.png" width="42" height="42"> | `~/.config/opencode/opencode.json` | `~/.config/opencode/opencode.json` | `%LOCALAPPDATA%\opencode\opencode.json` |
| **Roo Code**<br><img src="mcp_sync/assets/logos/readme/roo-code.png" width="42" height="42"> | `~/Library/Application Support/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings/mcp_settings.json` | `~/.config/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings/mcp_settings.json` | `%APPDATA%\Code\User\globalStorage\rooveterinaryinc.roo-cline\settings\mcp_settings.json` |
| **Trae**<br><img src="mcp_sync/assets/logos/readme/trae.png" width="42" height="42"> | `~/Library/Application Support/Trae/User/mcp.json` | `~/.config/Trae/User/mcp.json` | `%APPDATA%\Trae\User\mcp.json` |
| **Visual Studio Code**<br><img src="mcp_sync/assets/logos/readme/visual-studio-code.png" width="42" height="42"> | `~/Library/Application Support/Code/User/mcp.json` | `~/.config/Code/User/mcp.json` | `%APPDATA%\Code\User\mcp.json` |
| **Warp**<br><img src="mcp_sync/assets/logos/readme/warp.png" width="42" height="42"> | `~/.warp/.mcp.json` | `~/.warp/.mcp.json` | `%USERPROFILE%\.warp\.mcp.json` |
| **Windsurf**<br><img src="mcp_sync/assets/logos/readme/windsurf.png" width="42" height="42"> | `~/.codeium/windsurf/mcp_config.json` | `~/.codeium/windsurf/mcp_config.json` | `%USERPROFILE%\.codeium\windsurf\mcp_config.json` |
| **Zed**<br><img src="mcp_sync/assets/logos/readme/zed.png" width="42" height="42"> | `~/.config/zed/settings.json` | `~/.config/zed/settings.json` | `%APPDATA%\Zed\settings.json` |
| **Zoo Code**<br><img src="mcp_sync/assets/logos/readme/zoo-code.png" width="42" height="42"> | `~/Library/Application Support/Code/User/globalStorage/zoocodeorganization.zoo-code/settings/mcp_settings.json` | `~/.config/Code/User/globalStorage/zoocodeorganization.zoo-code/settings/mcp_settings.json` | `%APPDATA%\Code\User\globalStorage\zoocodeorganization.zoo-code\settings\mcp_settings.json` |

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

> **Note on the logo badges:** the round, white-ringed icons in the table
> above (`mcp_sync/assets/logos/readme/`) are **generated**, not hand-authored
> — they're the exact same circular-badge renderer the app uses
> (`logos.get_badge`), just called at a higher resolution. If you change a
> source logo under `mcp_sync/assets/logos/`, regenerate this folder — don't
> edit its PNGs by hand:
>
> ```python
> from mcp_sync.logos import get_badge
> get_badge("Kilo Code", size=112).save("mcp_sync/assets/logos/readme/kilo-code.png")
> ```

## Rebuilding after a code change

The installers do a **regular (copied) install**, not an editable one. Editing
files in this repo therefore does *not* affect the app that's already running —
you have to reinstall into its virtual environment and restart it:

```bash
# 1. reinstall the package into the app's venv (run from the repo root)
~/.mcp-sync/venv/bin/pip install --upgrade .
```

```bash
# 2a. restart — macOS
launchctl unload ~/Library/LaunchAgents/com.mcpsync.app.plist
launchctl load -w ~/Library/LaunchAgents/com.mcpsync.app.plist
```

```bash
# 2b. restart — Linux
pkill -f mcp_sync.app
~/.mcp-sync/venv/bin/python3 -m mcp_sync.app &
```

```powershell
# 2c. restart — Windows (PowerShell)
Get-Process pythonw -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "*mcp-sync*" } | Stop-Process
& "$env:USERPROFILE\.mcp-sync\venv\Scripts\pythonw.exe" -m mcp_sync.app
```

On macOS, if you changed the app icon (`mcp_sync/assets/logos/_mcp_synch.png`)
or anything in `autostart.py`, also regenerate the `.app` bundle — it's what
gives the process its name and icon in Activity Monitor:

```bash
~/.mcp-sync/venv/bin/python3 -c "from mcp_sync import autostart; autostart.enable()"
```

To confirm it came back up cleanly:

```bash
ps -p "$(pgrep -f mcp-auto-synch)" -o pid,etime,ucomm   # macOS/Linux
cat /tmp/mcp-sync.err                                   # should be empty
```

> **Note:** `last_sync_iso` in `~/.mcp-sync/settings.json` only advances when a
> sync actually *rewrites* a file. If everything is already in sync, the
> timestamp legitimately stays where it was — that's not a sign the app is stuck.

## Development

To run from source without touching the installed app, use a separate venv:

```bash
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
python -m mcp_sync.app
```

Settings (which tools are disabled, last sync time) are stored in
`~/.mcp-sync/settings.json`. Deleting that file resets the app to its
defaults (every tool enabled).

Adding support for a new tool is documented step by step, including the tests
to run, in [SKILL_ADD_NEW_PROVIDER.md](SKILL_ADD_NEW_PROVIDER.md).

### Releasing

Pushing a tag triggers [.github/workflows/release.yml](.github/workflows/release.yml),
which builds the wheel from whatever `version` is set in `pyproject.toml` at
that moment and publishes it as a GitHub Release — it does not bump the
version for you. Correct flow for every future release:

1. Edit `version = "0.0.2"` in `pyproject.toml` (regular commit).
2. `git tag v0.0.2 && git push origin v0.0.2`.

## FAQ

<details>
<summary>Does the app change anything besides the MCP server list?</summary>

No. It only touches each file's specific MCP servers key (`mcpServers`,
`servers`, `mcp_servers`, `context_servers` or `mcp`, depending on the tool)
and preserves everything else in the file as-is.

</details>

<details>
<summary>Do I have to configure the file paths manually?</summary>

No. The app scans your system for every supported tool and only shows the ones
it actually finds installed.

</details>

<details>
<summary>What if I don't want to sync a specific tool?</summary>

Flip its switch off. It stops being read from and written to until you turn it
back on — its file stays exactly as it was at the last sync.

</details>

<details>
<summary>Does it work offline?</summary>

Yes, the app makes no network calls at all — it's 100% local.

</details>

<details>
<summary>How do I restore a file from a backup?</summary>

Find the run you want under `~/.mcp-sync/backups/<date>_<time>/<tool name>/`
and copy that file back over the tool's real config path (shown in the app
next to each tool, or in the [table below](#supported-tools-and-config-paths)).
There's no restore button in the UI on purpose — copying the file back is a
single, obvious step you're fully in control of. See [Backups](#backups) for
where these live and when they're created.

</details>

<details>
<summary>What happens if the same server name exists in two tools with different settings?</summary>

The version from whichever file was **modified most recently wins**, and that
version gets written to every other tool — the two aren't merged field by
field. If that's not what you wanted, edit the server in whichever tool
should be the source of truth and let it sync again.

</details>

<details>
<summary>Does uninstalling the app delete my MCP server configs?</summary>

No. The uninstaller only removes MCP Sync itself (its venv, its login item,
its `.app` shortcut on macOS) — it never touches any AI tool's config file.
Your `~/.mcp-sync/settings.json` and `~/.mcp-sync/backups/` are also left in
place, in case you reinstall later.

</details>

<details>
<summary>Can I sync MCP servers across multiple computers?</summary>

Not directly — MCP Sync only reconciles the tools installed *on the machine
it's running on*, and it never makes a network call. If you want the same
servers on another machine, you'd sync that machine's own set of tools
separately (or copy one tool's config file over and let MCP Sync propagate
it from there).

</details>

<details>
<summary>Why does a tool I have installed show up as "not installed"?</summary>

MCP Sync requires real evidence — its CLI binary on `PATH`, its `.app`/`.exe`
bundle, a VS Code extension actually present, or (for most tools) its config
file already existing. If you just installed the tool and haven't opened it
yet, its config file may not exist yet; open the tool once, then click
"Sync Now".

</details>

<details>
<summary>How do I stop the app from starting at login?</summary>

Turn off "Start at Login" in the tray menu / popover — it toggles the
OS-level autostart entry (a LaunchAgent on macOS, a `.desktop` file on
Linux, or a `Run` registry key on Windows) without uninstalling anything.

</details>

## Function reference

A plain-language map of what each part of the codebase actually does, for
anyone reading the source without wanting to trace every line themselves.

### `sync_engine.py` — the sync engine itself

| Function                                   | What it does                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `merge_servers`                          | Takes the server lists from every enabled/detected tool and unions them into one set. Example: Cursor has`mcp1, mcp2`, VS Code has `mcp3, mcp4`, Codex has `mcp5` → merged result is `{mcp1, mcp2, mcp3, mcp4, mcp5}`. If the *same server name* exists in more than one tool with different settings, the version from whichever config file was **modified most recently wins** — the other one is discarded, not merged field-by-field. It also backfills a missing `type` on remote servers from another tool's copy, so a file that got touched for unrelated reasons (e.g. Claude Code updating its own usage stats) doesn't silently corrupt a remote server's record. |
| `run_sync`                               | The actual "do a sync" function. Reads every tool, calls`merge_servers`, removes any server that was deliberately deleted from the file that just changed (so it doesn't come back from another tool's copy), writes the merged set into every tool whose file differs from it, and records the last-sync timestamp. When called with `backup=True` (startup sync, "Sync Now"), it backs up each file via `backup.py` right before overwriting it.                                                                                                                                                                                                                                          |
| `build_statuses`                         | Builds the list shown in the UI: for every known tool, whether it's installed, enabled, in sync, and how many servers it has.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `_enabled_detected_tools`                | Filters the full list of known tools down to only the ones the user hasn't disabled*and* that are actually installed on this machine.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `_safe_read`                             | Reads a tool's server list; if the file is missing or corrupted, returns "no servers" instead of crashing the app.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `watched_paths` / `all_registry_paths` | List which config file paths the file-watcher should keep an eye on — the first only for tools currently installed, the second for*all* known tools (so a freshly-installed tool gets picked up automatically).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `seconds_since_last_sync`                | How long ago the last sync finished — used to ignore the app's own write as a false "file changed" event.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |

### `backup.py` — backing up a file before it's overwritten

| Function              | What it does                                                                                                                                                 |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `backup_file`       | Copies a tool's config file into`~/.mcp-sync/backups/<run_id>/<tool name>/` before `run_sync` overwrites it. Does nothing if the file doesn't exist yet. |
| `make_run_id`       | Builds the human-readable, timestamped folder name (e.g.`2026-09-08_22-43-09`) shared by every file backed up in the same run.                             |
| `prune_old_backups` | Deletes all but the 30 most recent backup run folders, so the directory doesn't grow forever.                                                                |

### `tools_registry.py` — one "translator" per tool

Each tool stores its MCP servers in a different file format and shape. This
module normalizes all of them into one common shape and back.

| Function                                                                                       | What it does                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| ---------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `build_registry`                                                                             | Builds the full catalog of every supported tool (Cursor, VS Code, Claude Code, Codex, Zed, Goose, OpenCode, etc.), with its config path per OS, its adapter, and how to detect if it's installed.                                                                                                                                                                                                                                                                                             |
| `ToolSpec.resolved_path`                                                                     | Turns a path template like`~/.cursor/mcp.json` into a real path on the current user's machine.                                                                                                                                                                                                                                                                                                                                                                                              |
| `ToolSpec.is_present`                                                                        | Decides whether a tool is genuinely installed — checks for its CLI binary on`PATH`, its `.app`/`.exe` in Applications, or a VS Code extension — rather than just trusting that a leftover config folder exists. This is what stops MCP Sync from "adopting" an old, uninstalled tool's config folder.                                                                                                                                                                                 |
| `_generic_mcp_servers_key_adapter`                                                           | Adapter used by most tools (Claude Code, Cursor, Claude Desktop, Gemini CLI, Continue, Amp, Kiro, Amazon Q, Warp, LM Studio, Grok…) that all store servers the same way, under an`mcpServers`-style key.                                                                                                                                                                                                                                                                                   |
| `_vscode_adapter`                                                                            | VS Code stores servers under`servers` (not `mcpServers`) and requires an explicit `type` field. This adapter strips the redundant `type` from local servers on read, but keeps it for remote ones — without it, Claude Code silently drops that remote server.                                                                                                                                                                                                                       |
| `_codex_toml_adapter`                                                                        | Translates Codex's TOML`[mcp_servers.<name>]` tables to/from the common shape.                                                                                                                                                                                                                                                                                                                                                                                                              |
| `_streamable_http_adapter`                                                                   | Used by Roo Code, Cline, Cline (CLI), Kilo Code, and Zoo Code. They store servers the same way as the generic adapter, but their strict schema rejects a remote server whose`type` is the plain `"http"` used elsewhere in this app — they require `"streamable-http"` or `"streamableHttp"` (the exact spelling varies by tool) instead, or the whole settings file gets rejected with "Invalid MCP settings format". This adapter translates that one field on the way in and out. |
| `_zed_adapter`                                                                               | Zed only supports local (stdio) servers, under a differently-nested`context_servers` structure; remote servers are simply skipped on write since Zed has no way to represent them. Rebuilds the whole section on every write, so a server removed elsewhere also disappears from Zed.                                                                                                                                                                                                       |
| `_opencode_adapter`                                                                          | OpenCode's`mcp` map uses `local`/`remote` types and a single `command` array (executable + args combined), unlike the common shape which keeps them separate.                                                                                                                                                                                                                                                                                                                         |
| `_goose_adapter`                                                                             | Goose stores servers in a YAML`extensions` map with its own field names (`cmd`, `envs`, `uri`).                                                                                                                                                                                                                                                                                                                                                                                       |
| `_read_json`/`_write_json`, `_read_yaml`/`_write_yaml`, `_read_toml`/`_write_toml` | Safe file I/O helpers: reading returns an empty result instead of crashing on a missing/corrupt file; writing goes through a temp file first so a crash mid-write can't corrupt the real config.                                                                                                                                                                                                                                                                                              |

### `settings.py` — the app's own preferences

| Function                                   | What it does                                                                                                                                                |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `load` / `save`                        | Read/write MCP Sync's own settings file (`~/.mcp-sync/settings.json`), always merged with defaults so an old settings file doesn't break after an update. |
| `is_tool_enabled` / `set_tool_enabled` | Check/set whether a specific tool should be synced at all (the on/off toggle per tool in the UI).                                                           |
| `set_start_at_login`                     | Turns "launch MCP Sync at login" on or off.                                                                                                                 |
| `set_hide_not_installed`                 | Turns on/off hiding not-installed tools from the tool list in the UI.                                                                                       |

### `watcher.py` — reacting to file changes instantly

| Function                                                | What it does                                                                                                                                                      |
| ------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `start` / `stop`                                    | Start or stop watching every known tool's config file. Prefers the`watchdog` library for instant, low-CPU reactions; falls back to polling if it's unavailable. |
| `_start_watchdog` / `_start_polling`                | The two implementations: instant filesystem events vs. checking file modification times every 5 seconds.                                                          |
| `_schedule_debounced_sync` / `_flush_pending_paths` | Groups multiple rapid file changes (e.g. an editor saving a file several times in under 1.5s) into a single sync instead of triggering one per write.             |

### `app.py` / `mac_ui.py` — the tray icon and macOS popover

| Function                               | What it does                                                                                                                                                             |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `main`                               | Entry point: uses the native macOS popover (`mac_ui.py`) when available, otherwise falls back to the cross-platform tray icon (`app.py`).                            |
| `run` / `start`                    | Turns on "start at login" if configured, starts the file watcher and the 60-second periodic sync, and runs the first sync.                                               |
| `sync_now`                           | Runs one sync pass and shows a notification if anything changed or failed.                                                                                               |
| `_periodic_sync_loop`                | Safety-net sync every 60 seconds, even with no detected file changes.                                                                                                    |
| `_on_files_changed`                  | Triggered by the watcher; re-syncs and (unlike the periodic loop) notifies the user if something actually changed.                                                       |
| `_menu_items` / `_rebuild_content` | Build the list shown in the tray menu / popover: one row per tool with a status dot (🟢 synced, ⚪ out of sync, ⚫ disabled) and a server count, e.g. "Claude Code (5)". |
| `toggleTool_`                        | Handles clicking a tool's on/off switch: saves the preference and re-syncs.                                                                                              |
| `revealConfig_`                      | Opens the file manager at that tool's exact config file.                                                                                                                 |
| `openDocumentation_`                 | Opens this repo in the browser.                                                                                                                                          |

### `autostart.py` — launch at login

| Function                                  | What it does                                                                                                                                                                                                   |
| ----------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `enable` / `disable` / `is_enabled` | Turn "start MCP Sync at login" on/off or check its state, delegating to the right OS-specific mechanism: a LaunchAgent`.plist` on macOS, a `.desktop` file on Linux, or a `Run` registry key on Windows. |

### UI & utilities

| Function                                                                      | What it does                                                                                                                                                |
| ----------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `group_for_tool` / `get_group` (`groups.py`)                            | Maps a tool to the company that makes it (e.g. Cursor → Anthropic-adjacent group), for grouping the tool list visually.                                    |
| `get_badge` / `get_company_logo` (`logos.py`)                           | Loads a tool's or company's logo image, falling back to a generated colored monogram (e.g. "CC" for Claude Code) if no logo asset exists.                   |
| `build_icon` / `build_status_dot` (`tray_icon.py`)                      | Draws the menu-bar icon (turns green while syncing) and the small colored status dots shown next to each tool.                                              |
| `notify` (`notifier.py`)                                                  | Shows a native OS notification (macOS banner, Linux`notify-send`, Windows toast); never throws — a failed notification is just silently skipped.         |
| `home` / `expand` / `open_path_in_file_manager` (`platform_utils.py`) | Cross-platform helpers: get the home folder, expand a path template like`~/.cursor/mcp.json` into a real path, and open the file manager at a given file. |

## Versão em português

Veja [README.pt-BR.md](README.pt-BR.md) para instruções de instalação e uso
em português.

## License

MIT
