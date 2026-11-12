"""Registry of supported coding-agent integrations for install/uninstall/doctor."""

from pathlib import Path
from typing import Dict, List, Optional

from agent_token_receipt.installer.base import BaseAgentIntegration
from agent_token_receipt.installer.integrations import (
    AntigravityIntegration,
    ClaudeCodeIntegration,
    CodexIntegration,
    CursorIntegration,
    GeminiCLIIntegration,
    WindsurfIntegration,
)
from collector.registry import canonical_agent_key


class IntegrationRegistry:
    """Instantiates and retrieves all built-in agent integrations."""

    def __init__(
        self,
        home_dir: Optional[Path] = None,
        probe_path_binaries: Optional[bool] = None,
    ):
        self.home_dir = home_dir
        self.probe_path_binaries = probe_path_binaries
        instances: List[BaseAgentIntegration] = [
            ClaudeCodeIntegration(home_dir=home_dir, probe_path_binaries=probe_path_binaries),
            CodexIntegration(home_dir=home_dir, probe_path_binaries=probe_path_binaries),
            CursorIntegration(home_dir=home_dir, probe_path_binaries=probe_path_binaries),
            WindsurfIntegration(home_dir=home_dir, probe_path_binaries=probe_path_binaries),
            AntigravityIntegration(home_dir=home_dir, probe_path_binaries=probe_path_binaries),
            GeminiCLIIntegration(home_dir=home_dir, probe_path_binaries=probe_path_binaries),
        ]
        self._integrations: Dict[str, BaseAgentIntegration] = {
            item.agent_key: item for item in instances
        }

    def all(self) -> List[BaseAgentIntegration]:
        return list(self._integrations.values())

    def keys(self) -> List[str]:
        return list(self._integrations.keys())

    def get(self, agent_name: str) -> Optional[BaseAgentIntegration]:
        return self._integrations.get(canonical_agent_key(agent_name))

    def select(self, agent_names: Optional[List[str]] = None) -> List[BaseAgentIntegration]:
        if not agent_names:
            return self.all()
        selected: List[BaseAgentIntegration] = []
        seen = set()
        for name in agent_names:
            key = canonical_agent_key(name)
            integration = self._integrations.get(key)
            if integration is None:
                raise ValueError(
                    f"Unsupported agent '{name}'. Supported: {', '.join(self._integrations.keys())}"
                )
            if key not in seen:
                seen.add(key)
                selected.append(integration)
        return selected

