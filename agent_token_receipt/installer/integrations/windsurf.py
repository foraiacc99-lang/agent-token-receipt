"""Windsurf integration for Agent Token Receipt (/agent-billing workflow + skill)."""

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


class WindsurfIntegration(BaseAgentIntegration):
    """Installs Windsurf workflow (/agent-billing) and skill cleanly."""

    agent_key = "windsurf"
    display_name = "Windsurf"
    command_name = "agent-billing"
    invocation_syntax = "/agent-billing"
    native_slash_supported = True
    integration_mechanism = "Workflow (.md -> /agent-billing) + Skill"
    telemetry_supported = False
    telemetry_status_note = (
        "Command supported, but Windsurf meters Cascade credits server-side; "
        "local receipts report Windsurf token counts as Unavailable."
    )

    def detect_global(self) -> DetectionResult:
        return probe_environment(
            agent_key=self.agent_key,
            display_name=self.display_name,
            scope="global",
            candidate_paths=[
                self.home_dir / ".codeium" / "windsurf",
                self.home_dir / ".windsurf",
            ],
            binary_names=["windsurf"],
            probe_binaries=self.probe_path_binaries,
        )

    def detect_project(self, workspace: Path) -> DetectionResult:
        return probe_environment(
            agent_key=self.agent_key,
            display_name=self.display_name,
            scope="project",
            candidate_paths=[workspace / ".windsurf"],
            probe_binaries=False,
        )

    def get_artifacts(
        self, scope: str, workspace: Optional[Path] = None
    ) -> List[InstallArtifact]:
        wf_content = render_command_markdown("Windsurf", "Workflow")
        skill_content = render_billing_skill_md()

        if scope == "global":
            wf_path = self.home_dir / ".codeium" / "windsurf" / "global_workflows" / "agent-billing.md"
            skill_path = self.home_dir / ".codeium" / "windsurf" / "skills" / "agent-billing" / "SKILL.md"
        elif scope == "project":
            if workspace is None:
                raise ValueError("workspace is required for project scope")
            wf_path = workspace / ".windsurf" / "workflows" / "agent-billing.md"
            skill_path = workspace / ".windsurf" / "skills" / "agent-billing" / "SKILL.md"
        else:
            raise ValueError(f"Unsupported scope '{scope}'")

        return [
            InstallArtifact(
                agent_key=self.agent_key,
                scope=scope,
                target_path=wf_path,
                content=wf_content,
                artifact_kind="workflow",
                description="Windsurf /agent-billing workflow",
            ),
            InstallArtifact(
                agent_key=self.agent_key,
                scope=scope,
                target_path=skill_path,
                content=skill_content,
                artifact_kind="skill",
                description="Windsurf Agent Skill for billing",
            ),
        ]

