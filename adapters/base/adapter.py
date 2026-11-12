"""Abstract base class for AI coding agent adapters."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict, Any


@dataclass
class SessionInfo:
    """High-level metadata about a detected coding agent session."""
    session_id: str
    agent_name: str
    workspace_path: Optional[str]
    title: Optional[str]
    start_time: Optional[datetime]
    last_active_time: Optional[datetime]
    step_count: Optional[int] = 0
    extra_metadata: Optional[Dict[str, Any]] = None


class BaseAgentAdapter(ABC):
    """Universal interface for coding agent adapters.
    
    Every agent adapter (Antigravity, Claude Code, Cursor, etc.) implements
    these methods to feed normalized data into the core pipeline.
    """

    @abstractmethod
    def get_agent_name(self) -> str:
        """Returns the canonical name of the coding agent (e.g. 'Google Antigravity')."""
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Returns the primary underlying model provider (e.g. 'Google')."""
        pass

    @abstractmethod
    def discover_sessions(self, workspace_path: Optional[str] = None) -> List[SessionInfo]:
        """Finds accessible sessions for this agent, optionally filtered by workspace."""
        pass

    @abstractmethod
    def collect_usage(self, session_id: str) -> List[Dict[str, Any]]:
        """Collects raw usage records for a specific session."""
        pass

