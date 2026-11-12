"""Google Antigravity integration for Agent Token Receipt (/agent-billing skill)."""

from pathlib import Path
from typing import List, Optional

from agent_token_receipt.installer.base import (
    BaseAgentIntegration,
    DetectionResult,
    InstallArtifact,
)
from agent_token_receipt.installer.integrations._common import probe_environment
from agent_token_receipt.installer.templates import render_billing_skill_md


class AntigravityIntegration(BaseAgentIntegration):
    """Installs native Antigravity Skill (~/.gemini/config/skills/agent-billing/SKILL.md)."""

    agent_key = "antigravity"
    display_name = "Google Antigravity"
    command_name = "agent-billing"
    invocation_syntax = "/agent-billing"
    native_slash_supported = True
    integration_mechanism = "Agent Skill (SKILL.md -> /agent-billing)"
    telemetry_supported = True
    telemetry_status_note = "Full local token collection from ~/.gemini/antigravity/"

    def detect_global(self) -> DetectionResult:
        return probe_environment(
            agent_key=self.agent_key,
            display_name=self.display_name,
            scope="global",
            candidate_paths=[
                self.home_dir / ".gemini" / "antigravity",
                self.home_dir / ".gemini" / "config",
            ],
            binary_names=["agy"],
            probe_binaries=self.probe_path_binaries,
        )

    def detect_project(self, workspace: Path) -> DetectionResult:
        return probe_environment(
            agent_key=self.agent_key,
            display_name=self.display_name,
            scope="project",
            candidate_paths=[workspace / ".agents", workspace / ".agent"],
            probe_binaries=False,
        )

    def get_artifacts(
        self, scope: str, workspace: Optional[Path] = None
    ) -> List[InstallArtifact]:
        content = render_billing_skill_md()
        if scope == "global":
            target = (
                self.home_dir
                / ".gemini"
                / "config"
                / "skills"
                / "agent-billing"
                / "SKILL.md"
            )
        elif scope == "project":
            if workspace is None:
                raise ValueError("workspace is required for project scope")
            target = workspace / ".agents" / "skills" / "agent-billing" / "SKILL.md"
        else:
            raise ValueError(f"Unsupported scope '{scope}'")

        return [
            InstallArtifact(
                agent_key=self.agent_key,
                scope=scope,
                target_path=target,
                content=content,
                artifact_kind="skill",
                description="Google Antigravity /agent-billing skill",
            )
        ]

