"""Environment detection across global and workspace-local agent configurations."""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from agent_token_receipt.installer.base import BaseAgentIntegration, DetectionResult
from agent_token_receipt.installer.registry import IntegrationRegistry


@dataclass
class AgentEnvironmentStatus:
    """Combined global and optional project detection status for one agent."""

    integration: BaseAgentIntegration
    global_detection: DetectionResult
    project_detection: Optional[DetectionResult] = None

    @property
    def is_detected_anywhere(self) -> bool:
        return self.global_detection.detected or bool(
            self.project_detection and self.project_detection.detected
        )


class EnvironmentDetector:
    """Probes supported coding environments safely without mutating any configuration."""

    def __init__(self, registry: Optional[IntegrationRegistry] = None):
        self.registry = registry or IntegrationRegistry()

    def detect_all(
        self,
        workspace: Optional[Path] = None,
        agents: Optional[List[str]] = None,
    ) -> List[AgentEnvironmentStatus]:
        """Return global and optional project detection statuses for selected agents."""
        integrations = self.registry.select(agents)
        statuses: List[AgentEnvironmentStatus] = []
        for integration in integrations:
            global_res = integration.detect_global()
            proj_res = (
                integration.detect_project(workspace)
                if workspace is not None
                else None
            )
            statuses.append(
                AgentEnvironmentStatus(
                    integration=integration,
                    global_detection=global_res,
                    project_detection=proj_res,
                )
            )
        return statuses

