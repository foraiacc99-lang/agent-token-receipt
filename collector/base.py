"""Abstract base interface for usage data collectors.

Defines the contract for agent-specific collectors (Antigravity, Claude Code, Cursor, etc.).
Core logic interacts only with this abstract interface, keeping domain models decoupled
from agent log structures.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
from core.models import CanonicalUsageRecord


@dataclass(frozen=True)
class SessionDescriptor:
    """Metadata describing a discovered agent session."""
    session_id: str
    agent: str
    provider: str
    title: Optional[str] = None
    workspace_path: Optional[str] = None
    start_time: Optional[datetime] = None
    last_active_time: Optional[datetime] = None
    turn_count: Optional[int] = 0


class BaseUsageCollector(ABC):
    """Abstract contract for coding agent usage collectors.
    
    Implementations of this class parse agent-specific logs or APIs
    and emit standardized CanonicalUsageRecord instances.
    """

    @property
    @abstractmethod
    def agent_name(self) -> str:
        """The canonical name of the coding agent (e.g. 'Google Antigravity')."""
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """The underlying model provider (e.g. 'Google')."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Checks if this agent environment or its local session logs are detected."""
        pass

    @abstractmethod
    def discover_sessions(self, workspace_path: Optional[str] = None) -> List[SessionDescriptor]:
        """Discovers accessible sessions, optionally filtered by workspace root path."""
        pass

    @abstractmethod
    def collect_records(self, session_id: str) -> List[CanonicalUsageRecord]:
        """Reads usage traces for a session and returns canonical records.
        
        Must strictly return verified records without guessing missing metrics.
        """
        pass

