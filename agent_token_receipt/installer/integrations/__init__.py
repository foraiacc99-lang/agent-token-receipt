"""Supported coding-agent platform integrations."""

from .antigravity import AntigravityIntegration
from .claude_code import ClaudeCodeIntegration
from .codex import CodexIntegration
from .cursor import CursorIntegration
from .gemini_cli import GeminiCLIIntegration
from .windsurf import WindsurfIntegration

__all__ = [
    "AntigravityIntegration",
    "ClaudeCodeIntegration",
    "CodexIntegration",
    "CursorIntegration",
    "GeminiCLIIntegration",
    "WindsurfIntegration",
]

