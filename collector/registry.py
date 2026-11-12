"""Central registry coordinating multi-agent discovery and workspace billing collection."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from collector.antigravity import AntigravityUsageCollector
from collector.base import BaseUsageCollector, SessionDescriptor
from collector.claude_code import ClaudeCodeUsageCollector
from collector.codex import CodexUsageCollector
from collector.cursor import CursorUsageCollector
from collector.gemini_cli import GeminiCLIUsageCollector
from collector.windsurf import WindsurfUsageCollector
from core.models import CanonicalUsageRecord

AGENT_ALIASES: Dict[str, str] = {
    "antigravity": "antigravity",
    "google-antigravity": "antigravity",
    "google_antigravity": "antigravity",
    "claude": "claude_code",
    "claude-code": "claude_code",
    "claude_code": "claude_code",
    "codex": "codex",
    "openai-codex": "codex",
    "openai_codex": "codex",
    "gemini": "gemini_cli",
    "gemini-cli": "gemini_cli",
    "gemini_cli": "gemini_cli",
    "cursor": "cursor",
    "windsurf": "windsurf",
}


def canonical_agent_key(name: str) -> str:
    """Resolve user-provided agent names cleanly to canonical registry keys."""
    normalized = name.strip().lower()
    return AGENT_ALIASES.get(normalized, normalized.replace("-", "_"))


@dataclass
class WorkspaceCollectionResult:
    """Aggregated result of collecting verifiable usage across one or more agents."""

    records: List[CanonicalUsageRecord] = field(default_factory=list)
    collected_sessions: List[SessionDescriptor] = field(default_factory=list)
    unavailable_agents: List[Dict[str, str]] = field(default_factory=list)
    queried_agents: List[str] = field(default_factory=list)


class CollectorRegistry:
    """Manages available coding-agent usage collectors and unified multi-agent queries."""

    def __init__(self, collectors: Optional[Dict[str, BaseUsageCollector]] = None):
        if collectors is not None:
            self._collectors = dict(collectors)
        else:
            self._collectors = {
                "antigravity": AntigravityUsageCollector(),
                "claude_code": ClaudeCodeUsageCollector(),
                "codex": CodexUsageCollector(),
                "gemini_cli": GeminiCLIUsageCollector(),
                "cursor": CursorUsageCollector(),
                "windsurf": WindsurfUsageCollector(),
            }

    @property
    def collectors(self) -> Dict[str, BaseUsageCollector]:
        return dict(self._collectors)

    def get(self, agent_name: str) -> Optional[BaseUsageCollector]:
        key = canonical_agent_key(agent_name)
        return self._collectors.get(key)

    def _select_keys(self, agents: Optional[List[str]] = None) -> List[str]:
        if not agents:
            return list(self._collectors.keys())
        keys: List[str] = []
        for a in agents:
            key = canonical_agent_key(a)
            if key not in self._collectors:
                raise ValueError(
                    f"Unsupported agent '{a}'. Supported: {', '.join(self._collectors.keys())}"
                )
            if key not in keys:
                keys.append(key)
        return keys

    def discover_all_sessions(
        self,
        workspace_path: Optional[str] = None,
        agents: Optional[List[str]] = None,
    ) -> List[Tuple[str, SessionDescriptor]]:
        """Discover sessions across selected agents, sorted newest first."""
        keys = self._select_keys(agents)
        found: List[Tuple[str, SessionDescriptor]] = []
        for key in keys:
            collector = self._collectors[key]
            if not collector.is_available():
                continue
            for session in collector.discover_sessions(workspace_path=workspace_path):
                found.append((key, session))

        found.sort(
            key=lambda item: (
                item[1].last_active_time.timestamp() if item[1].last_active_time else 0.0
            ),
            reverse=True,
        )
        return found

    def collect_workspace_usage(
        self,
        workspace_path: Optional[str] = None,
        agents: Optional[List[str]] = None,
        session_id: Optional[str] = None,
        latest_per_agent: bool = False,
    ) -> WorkspaceCollectionResult:
        """Collect verifiable usage records across selected agents and track unavailable ones."""
        keys = self._select_keys(agents)
        result = WorkspaceCollectionResult()

        for key in keys:
            collector = self._collectors[key]
            if not collector.is_available():
                continue
            result.queried_agents.append(collector.agent_name)

            supports_telemetry = getattr(collector, "supports_token_telemetry", True)
            unavailable_reason = getattr(
                collector,
                "telemetry_unavailable_reason",
                "Local token telemetry is unavailable for this environment.",
            )

            sessions = collector.discover_sessions(workspace_path=workspace_path)
            if not supports_telemetry:
                has_workspace_marker = bool(sessions)
                if workspace_path:
                    ws = Path(workspace_path)
                    if key == "windsurf" and (ws / ".windsurf").is_dir():
                        has_workspace_marker = True
                    elif key == "cursor" and (ws / ".cursor").is_dir():
                        has_workspace_marker = True
                # Report unavailable agent if explicitly requested or active in workspace/install
                if agents is not None or has_workspace_marker:
                    result.unavailable_agents.append(
                        {
                            "agent": collector.agent_name,
                            "model": "Unavailable",
                            "input_tokens": "Unavailable",
                            "output_tokens": "Unavailable",
                            "reason": unavailable_reason,
                        }
                    )
                continue

            if session_id:
                matching = [s for s in sessions if s.session_id == session_id or s.session_id.startswith(session_id)]
                if matching:
                    for s in matching:
                        recs = collector.collect_records(s.session_id)
                        if recs:
                            result.collected_sessions.append(s)
                            result.records.extend(recs)
                else:
                    # Direct fallback check when session_id exists without workspace match
                    recs = collector.collect_records(session_id)
                    if recs:
                        result.records.extend(recs)
                continue

            target_sessions = sessions[:1] if (latest_per_agent and sessions) else sessions
            for s in target_sessions:
                recs = collector.collect_records(s.session_id)
                if recs:
                    result.collected_sessions.append(s)
                    result.records.extend(recs)

        return result

