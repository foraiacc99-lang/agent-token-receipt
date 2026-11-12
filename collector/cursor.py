"""Read-only environment & capability detector for Cursor.

Empirical audit of local Cursor storage (~/.cursor/ai-tracking/ai-code-tracking.db,
~/.cursor/projects/*/agent-transcripts/*.jsonl, and Cursor state.vscdb) confirms
that Cursor performs token billing and metering server-side rather than storing
verifiable per-turn token counts locally on disk.

This collector detects Cursor sessions/activity cleanly without fabricating tokens.
"""

from pathlib import Path
import re
from typing import List, Optional

from collector._utils import normalize_fs_path
from collector.base import BaseUsageCollector, SessionDescriptor
from core.models import CanonicalUsageRecord


def _encode_cursor_workspace_slug(workspace_path: str) -> str:
    """Encode a filesystem path into Cursor's dash-separated project folder naming."""
    norm = normalize_fs_path(workspace_path)
    # Remove drive colon, replace path separators and spaces cleanly
    cleaned = norm.replace(":", "")
    parts = [p for p in re.split(r"[\\/ ]+", cleaned) if p]
    return "-".join(parts).lower()


class CursorUsageCollector(BaseUsageCollector):
    """Detects local Cursor presence and reports honest token unavailability."""

    agent_name = "Cursor"
    provider_name = "Cursor (Server-Side)"
    supports_token_telemetry = False
    telemetry_unavailable_reason = (
        "Token metrics unavailable locally: Cursor meters token usage server-side "
        "and does not persist verifiable per-turn token counts on disk."
    )

    def __init__(self, cursor_dir: Optional[Path] = None):
        self.cursor_dir = Path(cursor_dir) if cursor_dir is not None else Path.home() / ".cursor"
        self.projects_dir = self.cursor_dir / "projects"

    def is_available(self) -> bool:
        """Return True if local Cursor configuration directory exists."""
        return self.cursor_dir.is_dir()

    def discover_sessions(
        self, workspace_path: Optional[str] = None
    ) -> List[SessionDescriptor]:
        """Discover Cursor agent transcript files (metadata only; no local tokens)."""
        if not self.projects_dir.is_dir():
            return []

        target_slug = _encode_cursor_workspace_slug(workspace_path) if workspace_path else None
        descriptors: List[SessionDescriptor] = []

        try:
            project_dirs = sorted(p for p in self.projects_dir.iterdir() if p.is_dir())
        except OSError:
            return []

        for proj_dir in project_dirs:
            if target_slug is not None and proj_dir.name.lower() != target_slug:
                continue
            transcripts_dir = proj_dir / "agent-transcripts"
            if not transcripts_dir.is_dir():
                continue
            try:
                for tfile in sorted(transcripts_dir.glob("*.jsonl")):
                    descriptors.append(
                        SessionDescriptor(
                            session_id=tfile.stem,
                            agent=self.agent_name,
                            provider=self.provider_name,
                            title=f"Cursor Transcript ({tfile.stem[:8]}) - Tokens Unavailable Locally",
                            workspace_path=workspace_path,
                            start_time=None,
                            last_active_time=None,
                            turn_count=None,
                        )
                    )
            except OSError:
                continue

        return descriptors

    def collect_records(self, session_id: str) -> List[CanonicalUsageRecord]:
        """Return empty list strictly — Cursor does not expose local verifiable token counts."""
        return []

