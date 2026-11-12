"""Claude Code integration for Agent Token Receipt (/agent-billing skill)."""

from pathlib import Path
from typing import List, Optional

from agent_token_receipt.installer.base import (
    BaseAgentIntegration,
    DetectionResult,
    InstallArtifact,
)
from agent_token_receipt.installer.integrations._common import probe_environment
from agent_token_receipt.installer.templates import render_billing_skill_md


class ClaudeCodeIntegration(BaseAgentIntegration):
    """Installs native /agent-billing skill under Claude Code skills directories."""

    agent_key = "claude_code"
    display_name = "Claude Code"
    command_name = "agent-billing"
    invocation_syntax = "/agent-billing"
    native_slash_supported = True
    integration_mechanism = "Agent Skill (SKILL.md -> /agent-billing)"
    telemetry_supported = True
    telemetry_status_note = "Full local token collection from ~/.claude/projects/*.jsonl"

    def detect_global(self) -> DetectionResult:
        return probe_environment(
            agent_key=self.agent_key,
            display_name=self.display_name,
            scope="global",
            candidate_paths=[self.home_dir / ".claude"],
            binary_names=["claude"],
            probe_binaries=self.probe_path_binaries,
        )

    def detect_project(self, workspace: Path) -> DetectionResult:
        return probe_environment(
            agent_key=self.agent_key,
            display_name=self.display_name,
            scope="project",
            candidate_paths=[workspace / ".claude"],
            probe_binaries=False,
        )

    def get_artifacts(
        self, scope: str, workspace: Optional[Path] = None
    ) -> List[InstallArtifact]:
        content = render_billing_skill_md()
        if scope == "global":
            target = self.home_dir / ".claude" / "skills" / "agent-billing" / "SKILL.md"
        elif scope == "project":
            if workspace is None:
                raise ValueError("workspace is required for project scope")
            target = workspace / ".claude" / "skills" / "agent-billing" / "SKILL.md"
        else:
            raise ValueError(f"Unsupported scope '{scope}'")

        return [
            InstallArtifact(
                agent_key=self.agent_key,
                scope=scope,
                target_path=target,
                content=content,
                artifact_kind="skill",
                description="Claude Code native /agent-billing skill",
            )
        ]

