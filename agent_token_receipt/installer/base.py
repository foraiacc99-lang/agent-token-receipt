"""Core data structures and abstract contract for IDE/agent integrations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class DetectionResult:
    """Result of probing whether a coding agent is installed or configured."""

    agent_key: str
    display_name: str
    scope: str  # "global" or "project"
    detected: bool
    reason: str
    detected_paths: List[Path] = field(default_factory=list)
    cli_binary: Optional[str] = None


@dataclass
class InstallArtifact:
    """Single command, workflow, or skill file to install for an agent."""

    agent_key: str
    scope: str  # "global" or "project"
    target_path: Path
    content: str
    artifact_kind: str  # "skill", "command", "workflow"
    description: str


@dataclass
class ArtifactActionResult:
    """Outcome recorded for a single target file during install or uninstall."""

    agent_key: str
    target_path: Path
    status: str  # "installed", "updated", "unchanged", "skipped_conflict", "would_install", "removed", "restored_backup", "kept_shared", "not_found", "error"
    backup_path: Optional[Path] = None
    message: str = ""


@dataclass
class InstallPlan:
    """Preview of all artifacts to install before requesting user confirmation."""

    scope: str
    detected_agents: List[DetectionResult] = field(default_factory=list)
    artifacts: List[InstallArtifact] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class InstallSummary:
    """Final report produced after executing install or uninstall."""

    action: str  # "install" or "uninstall"
    aborted: bool = False
    actions: List[ArtifactActionResult] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class BaseAgentIntegration(ABC):
    """Abstract base class defining platform integration & command generation."""

    agent_key: str
    display_name: str
    command_name: str = "agent-billing"
    invocation_syntax: str = "/agent-billing"
    native_slash_supported: bool = True
    integration_mechanism: str = "Skill"
    telemetry_supported: bool = True
    telemetry_status_note: str = ""

    def __init__(
        self,
        home_dir: Optional[Path] = None,
        probe_path_binaries: Optional[bool] = None,
    ):
        self.home_dir = Path(home_dir) if home_dir is not None else Path.home()
        # Only probe system PATH binaries automatically when using the live home dir
        self.probe_path_binaries = (
            (home_dir is None) if probe_path_binaries is None else probe_path_binaries
        )

    @abstractmethod
    def detect_global(self) -> DetectionResult:
        """Detect global installation or configuration directories for this agent."""

    @abstractmethod
    def detect_project(self, workspace: Path) -> DetectionResult:
        """Detect project-local configuration folders inside workspace."""

    @abstractmethod
    def get_artifacts(
        self, scope: str, workspace: Optional[Path] = None
    ) -> List[InstallArtifact]:
        """Return target files and rendered templates for ``scope`` ('global' or 'project')."""
