"""Cursor integration for Agent Token Receipt (/agent-billing command + skill)."""

import os
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
    render_command_markdown,
)


class CursorIntegration(BaseAgentIntegration):
    """Installs Cursor custom command (/agent-billing) and skill cleanly."""

    agent_key = "cursor"
    display_name = "Cursor"
    command_name = "agent-billing"
    invocation_syntax = "/agent-billing"
    native_slash_supported = True
    integration_mechanism = "Slash Command (.cursor/commands/agent-billing.md) + Skill"
    telemetry_supported = False
    telemetry_status_note = (
        "Command supported, but Cursor meters token usage server-side; "
        "local receipts report Cursor token counts as Unavailable."
    )

    def detect_global(self) -> DetectionResult:
        candidates: List[Path] = [self.home_dir / ".cursor"]
        if self.probe_path_binaries:
            appdata = os.environ.get("APPDATA")
            if appdata:
                candidates.append(Path(appdata) / "Cursor")
            candidates.append(self.home_dir / "Library" / "Application Support" / "Cursor")
            candidates.append(self.home_dir / ".config" / "Cursor")

        return probe_environment(
            agent_key=self.agent_key,
            display_name=self.display_name,
            scope="global",
            candidate_paths=candidates,
            binary_names=["cursor"],
            probe_binaries=self.probe_path_binaries,
        )

    def detect_project(self, workspace: Path) -> DetectionResult:
        return probe_environment(
            agent_key=self.agent_key,
            display_name=self.display_name,
            scope="project",
            candidate_paths=[workspace / ".cursor"],
            probe_binaries=False,
        )

    def get_artifacts(
        self, scope: str, workspace: Optional[Path] = None
    ) -> List[InstallArtifact]:
        cmd_content = render_command_markdown("Cursor", "Slash Command")
        skill_content = render_billing_skill_md()

        if scope == "global":
            base = self.home_dir / ".cursor"
        elif scope == "project":
            if workspace is None:
                raise ValueError("workspace is required for project scope")
            base = workspace / ".cursor"
        else:
            raise ValueError(f"Unsupported scope '{scope}'")

        return [
            InstallArtifact(
                agent_key=self.agent_key,
                scope=scope,
                target_path=base / "commands" / "agent-billing.md",
                content=cmd_content,
                artifact_kind="command",
                description="Cursor /agent-billing custom slash command",
            ),
            InstallArtifact(
                agent_key=self.agent_key,
                scope=scope,
                target_path=base / "skills" / "agent-billing" / "SKILL.md",
                content=skill_content,
                artifact_kind="skill",
                description="Cursor Agent Skill for billing",
            ),
        ]

