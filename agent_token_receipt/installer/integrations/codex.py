"""OpenAI Codex CLI integration for Agent Token Receipt ($agent-billing skill)."""

from pathlib import Path
from typing import List, Optional

from agent_token_receipt.installer.base import (
    BaseAgentIntegration,
    DetectionResult,
    InstallArtifact,
)
from agent_token_receipt.installer.integrations._common import probe_environment
from agent_token_receipt.installer.templates import render_billing_skill_md


class CodexIntegration(BaseAgentIntegration):
    """Installs Agent Skill for OpenAI Codex CLI ($agent-billing / /skills)."""

    agent_key = "codex"
    display_name = "OpenAI Codex"
    command_name = "agent-billing"
    invocation_syntax = "$agent-billing (or /skills menu)"
    native_slash_supported = False
    integration_mechanism = "Agent Skill (SKILL.md -> $agent-billing; legacy slash prompts deprecated in Codex)"
    telemetry_supported = True
    telemetry_status_note = "Full local token collection from ~/.codex/sessions/**/rollout-*.jsonl"

    def detect_global(self) -> DetectionResult:
        return probe_environment(
            agent_key=self.agent_key,
            display_name=self.display_name,
            scope="global",
            candidate_paths=[self.home_dir / ".codex"],
            binary_names=["codex"],
            probe_binaries=self.probe_path_binaries,
        )

    def detect_project(self, workspace: Path) -> DetectionResult:
        return probe_environment(
            agent_key=self.agent_key,
            display_name=self.display_name,
            scope="project",
            candidate_paths=[workspace / ".codex", workspace / ".agents"],
            probe_binaries=False,
        )

    def get_artifacts(
        self, scope: str, workspace: Optional[Path] = None
    ) -> List[InstallArtifact]:
        content = render_billing_skill_md()
        if scope == "global":
            target = self.home_dir / ".codex" / "skills" / "agent-billing" / "SKILL.md"
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
                description="OpenAI Codex skill invoked via $agent-billing or /skills",
            )
        ]

