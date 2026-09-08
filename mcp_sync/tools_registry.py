"""
Registry of supported tools: where each one's MCP config lives per OS, and
how to translate between that tool's native JSON/TOML shape and our
canonical server dict shape.

Canonical server shape (a plain dict, one per MCP server name):
    stdio server -> {"command": str, "args": [str, ...], "env": {str: str}}
    remote server -> {"url": str, "headers": {str: str}, "type": "http"|"sse"}

Only "command"/"args"/"env" (local) or "url"/"headers"/"type" (remote) are
treated specially by adapters; any other keys a tool already had for a
server are preserved verbatim and passed through untouched.
"""
from __future__ import annotations

import copy
import glob
import json
import os
import shutil
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

from .platform_utils import IS_LINUX, IS_MAC, IS_WINDOWS, expand

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

import tomli_w


ServerMap = Dict[str, dict]


def _read_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            content = fh.read().strip()
            if not content:
                return {}
            return json.loads(content)
    except Exception:
        return {}


def _write_json(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = path + ".mcpsync.tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp_path, path)


def _read_toml(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    except Exception:
        return {}


def _write_toml(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = path + ".mcpsync.tmp"
    with open(tmp_path, "wb") as fh:
        tomli_w.dump(data, fh)
    os.replace(tmp_path, path)


# --------------------------------------------------------------------------
# Adapter interface: each adapter knows how to read/write ONE tool's file,
# extracting/injecting only the MCP server section and leaving the rest of
# the file (other settings) untouched.
# --------------------------------------------------------------------------


@dataclass
class Adapter:
    read: Callable[[str], ServerMap]
    write: Callable[[str, ServerMap], None]


def _generic_mcp_servers_key_adapter(key: str = "mcpServers", loader=_read_json, dumper=_write_json) -> Adapter:
    """Tools that store `{"<key>": {name: {...}}}` and pass canonical fields through as-is."""

    def read(path: str) -> ServerMap:
        data = loader(path)
        servers = data.get(key) or {}
        return copy.deepcopy(servers) if isinstance(servers, dict) else {}

    def write(path: str, servers: ServerMap) -> None:
        data = loader(path)
        data[key] = copy.deepcopy(servers)
        dumper(path, data)

    return Adapter(read=read, write=write)


def _vscode_adapter() -> Adapter:
    """VS Code's mcp.json uses top-level "servers" and requires an explicit "type"."""

    def read(path: str) -> ServerMap:
        data = _read_json(path)
        raw = data.get("servers") or {}
        servers: ServerMap = {}
        for name, cfg in raw.items():
            cfg = copy.deepcopy(cfg)
            cfg.pop("type", None)
            servers[name] = cfg
        return servers

    def write(path: str, servers: ServerMap) -> None:
        data = _read_json(path)
        out = {}
        for name, cfg in servers.items():
            cfg = copy.deepcopy(cfg)
            cfg["type"] = "http" if "url" in cfg else "stdio"
            out[name] = cfg
        data["servers"] = out
        _write_json(path, data)

    return Adapter(read=read, write=write)


def _codex_toml_adapter() -> Adapter:
    """Codex's config.toml uses a [mcp_servers.<name>] table per server."""

    def read(path: str) -> ServerMap:
        data = _read_toml(path)
        servers = data.get("mcp_servers") or {}
        return copy.deepcopy(servers) if isinstance(servers, dict) else {}

    def write(path: str, servers: ServerMap) -> None:
        data = _read_toml(path)
        data["mcp_servers"] = copy.deepcopy(servers)
        _write_toml(path, data)

    return Adapter(read=read, write=write)


def _zed_adapter() -> Adapter:
    """Zed's settings.json uses "context_servers": {name: {"source": "custom", "command": {...}}}."""

    def read(path: str) -> ServerMap:
        data = _read_json(path)
        raw = data.get("context_servers") or {}
        servers: ServerMap = {}
        for name, cfg in raw.items():
            if not isinstance(cfg, dict):
                continue
            command = cfg.get("command")
            if isinstance(command, dict):
                servers[name] = {
                    "command": command.get("path", ""),
                    "args": command.get("args", []),
                    "env": command.get("env", {}) or {},
                }
        return servers

    def write(path: str, servers: ServerMap) -> None:
        data = _read_json(path)
        out = data.get("context_servers") or {}
        for name, cfg in servers.items():
            if "command" not in cfg:
                continue  # Zed's custom context servers only support local stdio commands
            out[name] = {
                "source": "custom",
                "command": {
                    "path": cfg.get("command", ""),
                    "args": cfg.get("args", []),
                    "env": cfg.get("env", {}) or {},
                },
            }
        data["context_servers"] = out
        _write_json(path, data)

    return Adapter(read=read, write=write)


def _opencode_adapter() -> Adapter:
    """OpenCode's opencode.json uses top-level "mcp": {name: {type, command[], environment, url, headers}}."""

    def read(path: str) -> ServerMap:
        data = _read_json(path)
        raw = data.get("mcp") or {}
        servers: ServerMap = {}
        for name, cfg in raw.items():
            if not isinstance(cfg, dict):
                continue
            if cfg.get("type") == "remote":
                servers[name] = {
                    "url": cfg.get("url", ""),
                    "headers": cfg.get("headers", {}) or {},
                }
            else:
                command_list = cfg.get("command") or []
                servers[name] = {
                    "command": command_list[0] if command_list else "",
                    "args": command_list[1:] if len(command_list) > 1 else [],
                    "env": cfg.get("environment", {}) or {},
                }
        return servers

    def write(path: str, servers: ServerMap) -> None:
        data = _read_json(path)
        out = data.get("mcp") or {}
        for name, cfg in servers.items():
            if "url" in cfg:
                out[name] = {
                    "type": "remote",
                    "url": cfg.get("url", ""),
                    "headers": cfg.get("headers", {}) or {},
                    "enabled": True,
                }
            else:
                out[name] = {
                    "type": "local",
                    "command": [cfg.get("command", "")] + list(cfg.get("args", []) or []),
                    "environment": cfg.get("env", {}) or {},
                    "enabled": True,
                }
        data["mcp"] = out
        _write_json(path, data)

    return Adapter(read=read, write=write)


# --------------------------------------------------------------------------
# Tool definitions
# --------------------------------------------------------------------------


@dataclass
class ToolSpec:
    name: str
    path: str  # already OS-appropriate template using ~ and env vars
    adapter: Adapter
    doc_url: str = ""
    # Strong signals used to decide if a tool is actually installed, WITHOUT
    # requiring its config file to exist yet. A bare leftover config folder is
    # NOT enough evidence on its own (that caused false "installed" detections
    # for tools the user never had, e.g. from an old uninstalled app leaving
    # its config dir behind) - so we look for concrete proof instead: the
    # CLI binary on PATH, the .app bundle in Applications, or (for VS Code
    # extensions) the extension actually being installed.
    binary_names: tuple = field(default_factory=tuple)
    app_bundle_names: tuple = field(default_factory=tuple)
    extension_globs: tuple = field(default_factory=tuple)
    require_presence_signal: bool = False

    def resolved_path(self) -> str:
        return expand(self.path)

    def is_present(self) -> bool:
        if not self.require_presence_signal and os.path.exists(self.resolved_path()):
            return True
        for binary in self.binary_names:
            if shutil.which(binary):
                return True
        for pattern in self.extension_globs:
            if glob.glob(expand(pattern)):
                return True
        if self.app_bundle_names:
            if IS_MAC:
                search_dirs = ("/Applications", os.path.expanduser("~/Applications"))
            elif IS_WINDOWS:
                search_dirs = (
                    os.environ.get("ProgramFiles", ""),
                    os.environ.get("ProgramFiles(x86)", ""),
                    os.environ.get("LOCALAPPDATA", ""),
                )
            else:
                search_dirs = ("/usr/share/applications", os.path.expanduser("~/.local/share/applications"))
            for app_name in self.app_bundle_names:
                for base in search_dirs:
                    if base and os.path.exists(os.path.join(base, app_name)):
                        return True
        return False


def _mac_windows_linux(mac: str, linux: str, windows: str) -> str:
    if IS_MAC:
        return mac
    if IS_WINDOWS:
        return windows
    return linux


def build_registry() -> Dict[str, ToolSpec]:
    tools = [
        ToolSpec(
            name="Codex",
            path=_mac_windows_linux("~/.codex/config.toml", "~/.codex/config.toml", "%USERPROFILE%\\.codex\\config.toml"),
            adapter=_codex_toml_adapter(),
            doc_url="https://developers.openai.com/codex/mcp",
            binary_names=("codex",),
        ),
        ToolSpec(
            name="Claude Code",
            path=_mac_windows_linux("~/.claude.json", "~/.claude.json", "%USERPROFILE%\\.claude.json"),
            adapter=_generic_mcp_servers_key_adapter(),
            doc_url="https://code.claude.com/docs/en/mcp",
            binary_names=("claude",),
        ),
        ToolSpec(
            name="Cursor",
            path=_mac_windows_linux("~/.cursor/mcp.json", "~/.cursor/mcp.json", "%USERPROFILE%\\.cursor\\mcp.json"),
            adapter=_generic_mcp_servers_key_adapter(),
            doc_url="https://cursor.com/docs/mcp",
            binary_names=("cursor",),
            app_bundle_names=("Cursor.app",),
        ),
        ToolSpec(
            name="Gemini CLI",
            path=_mac_windows_linux("~/.gemini/settings.json", "~/.gemini/settings.json", "%USERPROFILE%\\.gemini\\settings.json"),
            adapter=_generic_mcp_servers_key_adapter(),
            doc_url="https://github.com/google-gemini/gemini-cli/blob/main/docs/tools/mcp-server.md",
            binary_names=("gemini",),
        ),
        ToolSpec(
            name="GitHub Copilot CLI",
            path=_mac_windows_linux("~/.copilot/mcp-config.json", "~/.copilot/mcp-config.json", "%USERPROFILE%\\.copilot\\mcp-config.json"),
            adapter=_generic_mcp_servers_key_adapter(),
            doc_url="https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers",
            binary_names=("copilot",),
        ),
        ToolSpec(
            name="GitHub Copilot Chat",
            path=_mac_windows_linux(
                "~/Library/Application Support/Code/User/mcp.json",
                "~/.config/Code/User/mcp.json",
                "%APPDATA%\\Code\\User\\mcp.json",
            ),
            adapter=_vscode_adapter(),
            doc_url="https://code.visualstudio.com/docs/copilot/chat/mcp-servers",
            extension_globs=(
                "~/.vscode/extensions/github.copilot-chat-*",
                "~/Library/Application Support/Code/User/workspaceStorage/*/GitHub.copilot-chat",
            ),
            require_presence_signal=True,
        ),
        ToolSpec(
            name="Visual Studio Code",
            path=_mac_windows_linux(
                "~/Library/Application Support/Code/User/mcp.json",
                "~/.config/Code/User/mcp.json",
                "%APPDATA%\\Code\\User\\mcp.json",
            ),
            adapter=_vscode_adapter(),
            doc_url="https://code.visualstudio.com/docs/agent-customization/mcp-servers",
            binary_names=("code",),
            app_bundle_names=("Visual Studio Code.app",),
        ),
        ToolSpec(
            name="OpenCode",
            path=_mac_windows_linux(
                "~/.config/opencode/opencode.json",
                "~/.config/opencode/opencode.json",
                "%LOCALAPPDATA%\\opencode\\opencode.json",
            ),
            adapter=_opencode_adapter(),
            doc_url="https://opencode.ai/docs/mcp-servers/",
            binary_names=("opencode",),
        ),
        ToolSpec(
            name="Windsurf",
            path=_mac_windows_linux(
                "~/.codeium/windsurf/mcp_config.json",
                "~/.codeium/windsurf/mcp_config.json",
                "%USERPROFILE%\\.codeium\\windsurf\\mcp_config.json",
            ),
            adapter=_generic_mcp_servers_key_adapter(),
            binary_names=("windsurf",),
            app_bundle_names=("Windsurf.app",),
        ),
        ToolSpec(
            name="Antigravity",
            path=_mac_windows_linux(
                "~/.gemini/config/mcp_config.json",
                "~/.gemini/config/mcp_config.json",
                "%USERPROFILE%\\.gemini\\config\\mcp_config.json",
            ),
            adapter=_generic_mcp_servers_key_adapter(),
            app_bundle_names=("Antigravity.app",),
        ),
        ToolSpec(
            name="Zed",
            path=_mac_windows_linux("~/.config/zed/settings.json", "~/.config/zed/settings.json", "%APPDATA%\\Zed\\settings.json"),
            adapter=_zed_adapter(),
            binary_names=("zed",),
            app_bundle_names=("Zed.app",),
        ),
        ToolSpec(
            name="Continue",
            path=_mac_windows_linux("~/.continue/config.json", "~/.continue/config.json", "%USERPROFILE%\\.continue\\config.json"),
            adapter=_generic_mcp_servers_key_adapter(),
            extension_globs=("~/.vscode/extensions/continue.continue-*",),
        ),
        ToolSpec(
            name="Roo Code",
            path=_mac_windows_linux(
                "~/Library/Application Support/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings/mcp_settings.json",
                "~/.config/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings/mcp_settings.json",
                "%APPDATA%\\Code\\User\\globalStorage\\rooveterinaryinc.roo-cline\\settings\\mcp_settings.json",
            ),
            adapter=_generic_mcp_servers_key_adapter(),
            doc_url="https://docs.roocode.com/features/mcp/using-mcp-in-roo-code",
            extension_globs=("~/.vscode/extensions/rooveterinaryinc.roo-cline-*",),
        ),
    ]

    if IS_MAC:
        tools.append(
            ToolSpec(
                name="Claude Desktop",
                path="~/Library/Application Support/Claude/claude_desktop_config.json",
                adapter=_generic_mcp_servers_key_adapter(),
                app_bundle_names=("Claude.app",),
            )
        )
    elif IS_WINDOWS:
        tools.append(
            ToolSpec(
                name="Claude Desktop",
                path="%APPDATA%\\Claude\\claude_desktop_config.json",
                adapter=_generic_mcp_servers_key_adapter(),
                app_bundle_names=("Claude.exe",),
            )
        )

    return {tool.name: tool for tool in tools}


REGISTRY: Dict[str, ToolSpec] = build_registry()
