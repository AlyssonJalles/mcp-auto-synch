"""Groups tools by the company that makes them, for the accordion sections
in the popover UI. Order here is the display order."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class CompanyGroup:
    company: str
    tool_names: List[str]
    logo: str  # filename under mcp_sync/assets/logos/, or "" for none


GROUPS: List[CompanyGroup] = [
    CompanyGroup("Anthropic", ["Claude Code", "Claude Desktop"], "company_anthropic.png"),
    CompanyGroup("OpenAI", ["Codex"], "company_openai.png"),
    CompanyGroup("Google", ["Gemini CLI", "Antigravity"], "company_google.png"),
    CompanyGroup("Microsoft", ["Visual Studio Code", "GitHub Copilot CLI", "GitHub Copilot Chat"], "company_microsoft.png"),
    CompanyGroup("SpaceX", ["Cursor"], "company_spacex.png"),
    CompanyGroup("Zed", ["Zed"], "zed-hosted.png"),
    CompanyGroup("Codeium", ["Windsurf"], "windsurf.png"),
    CompanyGroup("Continue", ["Continue"], "continue.png"),
    CompanyGroup("SST", ["OpenCode"], "opencode.png"),
    CompanyGroup("Roo Code", ["Roo Code"], "roocode.png"),
    CompanyGroup("Cline Bot", ["Cline", "Cline (CLI)"], "cline.png"),
    CompanyGroup("Kilo Code", ["Kilo Code"], "kilo-code.png"),
    CompanyGroup("Zoo Code", ["Zoo Code"], "zoo-code.png"),
    CompanyGroup("Sourcegraph", ["Amp"], "Amp.jpeg"),
    CompanyGroup("AWS", ["Kiro", "Amazon Q"], "amazon-q.png"),
    CompanyGroup("Block", ["Goose"], "goose.png"),
    CompanyGroup("Warp", ["Warp"], "warp.png"),
    CompanyGroup("ByteDance", ["Trae"], "trae.png"),
    CompanyGroup("Element Labs", ["LM Studio"], "lm-studio.png"),
    CompanyGroup("xAI", ["Grok"], "grok.png"),
]


def group_for_tool(tool_name: str) -> str:
    for group in GROUPS:
        if tool_name in group.tool_names:
            return group.company
    return "Other"


def get_group(tool_name: str) -> "CompanyGroup | None":
    for group in GROUPS:
        if tool_name in group.tool_names:
            return group
    return None
