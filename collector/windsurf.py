"""Read-only environment & capability detector for Windsurf.

Windsurf meters Cascade credits server-side and provides no documented local
SQLite or JSONL token telemetry log. This collector detects installation/workspace
markers honestly without fabricating token or cost data.
"""

from pathlib import Path
from typing import List, Optional

from collector.base import BaseUsageCollector, SessionDescriptor
from core.models import CanonicalUsageRecord


class WindsurfUsageCollector(BaseUsageCollector):
    """Detects local Windsurf environment and reports honest token unavailability."""

    agent_name = "Windsurf"
    provider_name = "Windsurf (Server-Side)"
    supports_token_telemetry = False
    telemetry_unavailable_reason = (
        "Token metrics unavailable locally: Windsurf meters Cascade usage server-side "
        "without a documented local per-turn token log."
    )

    def __init__(
        self,
        codeium_windsurf_dir: Optional[Path] = None,
        dot_windsurf_dir: Optional[Path] = None,
    ):
        self.codeium_windsurf_dir = (
            Path(codeium_windsurf_dir)
            if codeium_windsurf_dir is not None
            else Path.home() / ".codeium" / "windsurf"
        )
        self.dot_windsurf_dir = (
            Path(dot_windsurf_dir)
            if dot_windsurf_dir is not None
            else Path.home() / ".windsurf"
        )

    def is_available(self) -> bool:
        """Return True if local Windsurf directories exist."""
        return self.codeium_windsurf_dir.is_dir() or self.dot_windsurf_dir.is_dir()

    def discover_sessions(
        self, workspace_path: Optional[str] = None
    ) -> List[SessionDescriptor]:
        """Return empty list cleanly because Windsurf exposes no local token sessions."""
        return []

    def collect_records(self, session_id: str) -> List[CanonicalUsageRecord]:
        """Return empty list strictly without fabricating usage records."""
        return []

