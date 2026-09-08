# Skill: Add a New Provider (MCP Client/Tool)

Purpose-built checklist for adding a new AI coding tool to MCP Sync. Input
needed from the user is just **one or both** of:

- a link to the tool's MCP documentation, and/or
- a link to its git repo (or a local clone path)

Everything else below should be derivable from those sources plus this
repo's existing patterns. Work through the checklist top to bottom; don't
skip the testing section even if the addition "looks obviously right" —
every adapter here has a subtly different on-disk shape and the only way
to be sure is to round-trip real data through it.

## 0. Before touching any file

Read `mcp_sync/tools_registry.py` in full first (it's one file, ~700
lines). It documents the canonical server shape in its module docstring
and contains every adapter and tool this app already supports — the new
provider almost certainly matches one of the existing patterns closely
(most VS Code-extension forks of Roo Code/Cline do). Don't design a new
adapter before confirming an existing one doesn't already fit.

## 1. Research the provider (from docs link and/or repo)

Answer these concretely — don't guess, verify from source:

1. **Config file path per OS** (macOS / Linux / Windows), using `~` and
   `%ENVVAR%` style placeholders consistent with the rest of the registry.
   - If it's a VS Code extension: the path is almost always
     `.../Code/User/globalStorage/<publisher>.<extension-name>/settings/<file>.json`.
     Get the exact `<publisher>.<extension-name>` from the extension's
     `package.json` (`"publisher"` + `"name"` fields) — don't assume it
     matches the display name. Search the repo:
     `grep -E '"name"|"publisher"' path/to/extension/package.json`
   - If it's a standalone CLI/app: check its own docs or search the repo
     for where it reads/writes its MCP config (`grep -rn "mcp" --include=*.ts`
     or equivalent, look for a settings/config module).
2. **On-disk JSON/YAML/TOML shape**: what's the top-level key
   (`mcpServers`, `servers`, `mcp`, `context_servers`, ...)? Is it a
   dict-keyed-by-name or a list of entries? Are local (stdio) and remote
   (http/sse) servers shaped differently?
3. **Remote server "type" field quirk**: many Roo Code/Cline forks use a
   strict schema that rejects the plain `"http"` type this app uses
   internally, requiring `"streamable-http"` or `"streamableHttp"` (spelling
   varies per tool) or `"sse"` instead — or the whole file gets rejected.
   Grep the repo for `streamable` and `"sse"` to confirm which spelling (if
   any) this tool needs.
4. **Presence-detection signal** — how to tell the tool is actually
   *installed*, not just that a leftover config folder exists:
   - CLI binary name (`shutil.which`-able) → `binary_names`
   - `.app` (macOS) / `.exe` dir (Windows) bundle name → `app_bundle_names`
   - VS Code extension folder glob, e.g.
     `~/.vscode/extensions/<publisher>.<name>-*` → `extension_globs`
   A bare config-file-exists check is NOT enough on its own (that causes
   false "installed" detections from old uninstalled tools) — set
   `require_presence_signal=True` if the config path alone shouldn't count.
5. **Doc URL** for the "Learn more" link, if the tool has public MCP docs.

## 2. Add the `ToolSpec` in `mcp_sync/tools_registry.py`

- If the on-disk shape exactly matches an existing adapter (very likely for
  Roo Code/Cline forks), reuse it — e.g.
  `_streamable_http_adapter("streamable-http")` or `_generic_mcp_servers_key_adapter()`.
  Do **not** write a near-duplicate adapter for a shape that's already covered.
- Only write a new adapter function (following the existing ones' pattern:
  `read`/`write` closures returning an `Adapter`) if the shape is genuinely
  different — e.g. a list-of-entries format, a nested `command` array, or a
  non-JSON format.
- Place the new `ToolSpec(...)` near its closest sibling in the list (e.g.
  next to "Cline (CLI)" for another Roo/Cline fork) — the list order is the
  fallback sort order before the UI's own alphabetical sort, so grouping
  related tools together keeps diffs readable.
- Double-check `_mac_windows_linux(...)` path strings use the *exact*
  publisher/extension-name or binary name found in step 1 — a typo here
  silently produces a tool that's never detected as installed.

## 3. Add the logo/icon

- Find a square icon in the provider's repo (app icon, extension icon,
  favicon) — prefer one that already has its own solid background (dark
  square, brand color, etc.) since the badge renderer pastes it directly
  onto a white circle with no extra treatment by default. Check size/mode
  with `file <path>`.
- Copy it into `mcp_sync/assets/logos/<tool-slug>.png` (kebab-case,
  matching the naming convention of existing files like `roocode.png`,
  `kilo-code.png`).
- If the source art reaches the image edge with a transparent background
  (not a filled square), you likely need an entry in `_WIDE_INSET_FILES`
  and/or `_BADGE_BACKGROUNDS` in `mcp_sync/logos.py` — check how `Amp` or
  `LM Studio` handle this before adding a new one.
- Add `"<Tool Name>": "<tool-slug>.png"` to `_LOGO_FILES` in
  `mcp_sync/logos.py`. A monogram fallback (`_MONOGRAM_BADGES`) is optional
  since the real logo file always takes priority when present — only add
  one if you want a graceful fallback should the asset ever go missing.

## 4. Add the company group

Add a `CompanyGroup("<Company>", ["<Tool Name>"], "<logo-or-company-logo>.png")`
entry to `GROUPS` in `mcp_sync/groups.py`. If the tool doesn't have a
distinct "company" logo, reuse its own tool logo file for the group header
(that's what Roo Code, Kilo Code, and Zoo Code do — one-tool companies just
repeat the tool's own badge).

## 5. Update documentation

- `README.md`:
  - Add the tool name to the provider list sentence near the top.
  - Add a row to the "Supported tools and config paths" table (keep OS
    column order: macOS, Linux, Windows).
  - If you reused an existing adapter, add the tool name to that adapter's
    row in the "Function reference" table (e.g. the `_streamable_http_adapter`
    row already lists every tool that shares it — extend that list rather
    than adding a new row). If you wrote a new adapter, add a new row.
- `README.pt-BR.md`: add the tool name to the equivalent provider list
  sentence near the top (this file doesn't mirror the full tables, just the
  intro list).

## 6. Test — do not skip this

This repo has no test suite; verify by hand with a throwaway venv and
inline scripts. All of the following must pass before considering the
provider done:

```bash
# one-time throwaway venv with the runtime deps (skip if one already exists)
python3 -m venv /tmp/mcpsyncvenv
/tmp/mcpsyncvenv/bin/pip install -q tomli_w pyyaml pillow
```

**6.1 — Registry resolves and detects correctly:**
```bash
/tmp/mcpsyncvenv/bin/python -c "
from mcp_sync.tools_registry import REGISTRY
ts = REGISTRY['<Tool Name>']
print('path:', ts.resolved_path())
print('is_present (should be False on a machine without it, True if you have it installed):', ts.is_present())
"
```

**6.2 — Group and badge resolve:**
```bash
/tmp/mcpsyncvenv/bin/python -c "
from mcp_sync.groups import group_for_tool
from mcp_sync.logos import get_badge
print('group:', group_for_tool('<Tool Name>'))
badge = get_badge('<Tool Name>')
print('badge:', badge.size, badge.mode)  # must be (40, 40) RGBA
"
```
Visually confirm the badge doesn't look wrong (e.g. mostly white with a
tiny logo in the corner) — if so, revisit the inset/background handling in
step 3.

**6.3 — Adapter round-trip, including the remote-server type quirk:**
```bash
/tmp/mcpsyncvenv/bin/python -c "
import tempfile, os, json
from mcp_sync.tools_registry import REGISTRY

ts = REGISTRY['<Tool Name>']
with tempfile.TemporaryDirectory() as d:
    path = os.path.join(d, os.path.basename(ts.resolved_path()))
    servers = {
        'local1': {'command': 'npx', 'args': ['-y', 'foo'], 'env': {'X': '1'}},
        'remote1': {'url': 'https://example.com', 'headers': {'Authorization': 'Bearer x'}, 'type': 'http'},
    }
    ts.adapter.write(path, servers)
    print('on-disk shape:', json.dumps(json.load(open(path)) if path.endswith('.json') else open(path).read(), indent=2, default=str))
    back = ts.adapter.read(path)
    assert back == servers, f'ROUND-TRIP MISMATCH: {back!r} != {servers!r}'
    print('round-trip OK')
"
```
This must both print a native shape that matches what step 1 found in the
provider's real source/docs, AND assert equal on round-trip. If the tool
needs `streamable-http`/`streamableHttp`, confirm the on-disk dump shows
that exact string, not `"http"`.

**6.4 — Deletion/rename actually removes the server:**
Adapters that rebuild their section from scratch on every write (most of
them) must make a removed server actually disappear, not linger from a
merge. Verify:
```bash
/tmp/mcpsyncvenv/bin/python -c "
import tempfile, os
from mcp_sync.tools_registry import REGISTRY

ts = REGISTRY['<Tool Name>']
with tempfile.TemporaryDirectory() as d:
    path = os.path.join(d, os.path.basename(ts.resolved_path()))
    ts.adapter.write(path, {'a': {'command': 'x', 'args': [], 'env': {}}, 'b': {'command': 'y', 'args': [], 'env': {}}})
    ts.adapter.write(path, {'a': {'command': 'x', 'args': [], 'env': {}}})  # 'b' removed
    result = ts.adapter.read(path)
    assert 'b' not in result, 'removed server still present after write'
    print('deletion OK:', result)
"
```

**6.5 — Existing file's unrelated settings survive a write:**
Confirms the adapter only touches its own MCP-server key, per this app's
core guarantee. Pre-populate the file with an unrelated top-level key,
write servers, and confirm the unrelated key is untouched:
```bash
/tmp/mcpsyncvenv/bin/python -c "
import tempfile, os, json
from mcp_sync.tools_registry import REGISTRY

ts = REGISTRY['<Tool Name>']
with tempfile.TemporaryDirectory() as d:
    path = os.path.join(d, os.path.basename(ts.resolved_path()))
    if path.endswith('.json'):
        with open(path, 'w') as f:
            json.dump({'someUnrelatedSetting': True}, f)
        ts.adapter.write(path, {'a': {'command': 'x', 'args': [], 'env': {}}})
        data = json.load(open(path))
        assert data.get('someUnrelatedSetting') is True, 'unrelated setting was clobbered'
        print('preserved unrelated settings OK:', data)
    else:
        print('skip (non-JSON adapter — verify manually with its native format)')
"
```

**6.6 — No other hardcoded tool-name lists were missed:**
```bash
grep -rn '"<Tool Name>"\|"<other names the tool might be referenced by>"' mcp_sync/*.py
```
Everything outside `tools_registry.py`/`groups.py`/`logos.py` should
iterate the registry generically (the UI, sync engine, and tray code all
do today) — if this grep turns up a hit in some other file, that file has
a hardcoded tool list that also needs updating, which would be a
regression against how this app is structured.

**6.7 — Clean up:**
```bash
rm -rf /tmp/mcpsyncvenv
```

## 7. Optional — real-world sanity check

If the tool is actually installed on the machine (or can be installed
quickly), run the real app and confirm:
- the tool shows up in the popover/tray under the correct company group,
  with a badge that looks right
- toggling it off/on works
- adding a server in another tool and running a sync pass makes it appear
  in this tool's real config file, in the exact shape the tool itself
  expects (bonus: open the tool and confirm it actually loads the server
  without an error)

This step needs the user's own machine/environment and can't always be
automated — do it when feasible, and say plainly when it wasn't possible
(e.g. "not installed on this machine, verified via adapter round-trip
only") rather than implying full verification happened.

## Common gotchas seen so far

- Assuming a fork's extension ID matches its display name (Kilo Code:
  publisher `kilocode`, name `kilo-code`; Zoo Code: publisher
  `ZooCodeOrganization`, name `zoo-code` — neither obvious from the tool's
  marketing name alone). Always verify from the real `package.json`.
- Assuming the remote-server `type` spelling — check the actual validator/
  schema in source (`streamable-http` vs `streamableHttp` vs `sse`-only).
- Reaching for a solid monogram fallback or `_BADGE_BACKGROUNDS` entry when
  the source icon already has a filled background — check the rendered
  badge before adding workarounds preemptively.
- Forgetting the `README.pt-BR.md` intro-sentence update (it's easy to miss
  since that file doesn't mirror the full tables).
