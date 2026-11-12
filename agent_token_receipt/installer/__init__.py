"""Universal multi-agent installer package for Agent Token Receipt."""

from .base import (
    ArtifactActionResult,
    BaseAgentIntegration,
    DetectionResult,
    InstallArtifact,
    InstallPlan,
    InstallSummary,
)
from .detector import AgentEnvironmentStatus, EnvironmentDetector
from .installer import DoctorAgentReport, DoctorReport, UniversalInstaller
from .registry import IntegrationRegistry

__all__ = [
    "AgentEnvironmentStatus",
    "ArtifactActionResult",
    "BaseAgentIntegration",
    "DetectionResult",
    "DoctorAgentReport",
    "DoctorReport",
    "EnvironmentDetector",
    "InstallArtifact",
    "InstallPlan",
    "InstallSummary",
    "IntegrationRegistry",
    "UniversalInstaller",
]

