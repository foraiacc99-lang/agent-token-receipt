"""Gemini CLI integration for Agent Token Receipt (/agent-billing.toml command + skill)."""

from pathlib import Path
from typing import List, Optional

from agent_token_receipt.installer.base import (
    BaseAgentIntegration,
    DetectionResult,
    InstallArtifact,
)
from agent_token_receipt.installer.integrations._common import probe_environment
from agent_token_receipt.installer.templates import (
    render_billing_skill_md,
    render_gemini_cli_toml,
)


class GeminiCLIIntegration(BaseAgentIntegration):
    """Installs Gemini CLI custom TOML command (~/.gemini/commands/agent-billing.toml)."""

    agent_key = "gemini_cli"
    display_name = "Gemini CLI"
    command_name = "agent-billing"
    invocation_syntax = "/agent-billing"
    native_slash_supported = True
    integration_mechanism = "Custom Slash Command (.gemini/commands/agent-billing.toml) + Skill"
    telemetry_supported = True
    telemetry_status_note = "Full local token collection from ~/.gemini/tmp/*/chats/"

    def detect_global(self) -> DetectionResult:
        # Probe Gemini CLI-specific directories/files only so Antigravity's
        # ~/.gemini/antigravity directory does not trigger a false positive.
        gemini_root = self.home_dir / ".gemini"
        return probe_environment(
            agent_key=self.agent_key,
            display_name=self.display_name,
            scope="global",
            candidate_paths=[
                gemini_root / "tmp",
                gemini_root / "commands",
                gemini_root / "skills",
                gemini_root / "settings.json",
            ],
            binary_names=["gemini"],
            probe_binaries=self.probe_path_binaries,
        )

    def detect_project(self, workspace: Path) -> DetectionResult:
        return probe_environment(
            agent_key=self.agent_key,
            display_name=self.display_name,
            scope="project",
            candidate_paths=[workspace / ".gemini"],
            probe_binaries=False,
        )

    def get_artifacts(
        self, scope: str, workspace: Optional[Path] = None
    ) -> List[InstallArtifact]:
        toml_content = render_gemini_cli_toml()
        skill_content = render_billing_skill_md()

        if scope == "global":
            cmd_path = self.home_dir / ".gemini" / "commands" / "agent-billing.toml"
            skill_path = self.home_dir / ".gemini" / "skills" / "agent-billing" / "SKILL.md"
        elif scope == "project":
            if workspace is None:
                raise ValueError("workspace is required for project scope")
            cmd_path = workspace / ".gemini" / "commands" / "agent-billing.toml"
            skill_path = workspace / ".agents" / "skills" / "agent-billing" / "SKILL.md"
        else:
            raise ValueError(f"Unsupported scope '{scope}'")

        return [
            InstallArtifact(
                agent_key=self.agent_key,
                scope=scope,
                target_path=cmd_path,
                content=toml_content,
                artifact_kind="command",
                description="Gemini CLI /agent-billing TOML command",
            ),
            InstallArtifact(
                agent_key=self.agent_key,
                scope=scope,
                target_path=skill_path,
                content=skill_content,
                artifact_kind="skill",
                description="Gemini CLI Agent Skill",
            ),
        ]

