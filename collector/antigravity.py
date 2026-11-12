"""Google Antigravity session discovery and usage collector.

Reads genuine Gemini token metrics from local Antigravity session records:
- Session index: ~/.gemini/antigravity/conversation_summaries.db (SQLite read-only)
- Traces: ~/.gemini/antigravity/brain/<id>/.system_generated/logs/transcript.jsonl (JSON Lines)

Strictly read-only: never modifies files, never executes writes, never extracts private text.
"""

import json
import logging
import re
import sqlite3
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union

from collector.base import BaseUsageCollector, SessionDescriptor
from core.models import CanonicalUsageRecord

logger = logging.getLogger(__name__)

# Known verified Gemini and multi-provider model mappings: (canonical_id, provider)
VERIFIED_MODEL_MAP: Dict[str, Tuple[str, str]] = {
    "gemini 3.8 flash": ("gemini-3.8-flash", "Google"),
    "gemini 3.8 pro": ("gemini-3.8-pro", "Google"),
    "gemini 2.5 flash": ("gemini-2.5-flash", "Google"),
    "gemini 2.5 pro": ("gemini-2.5-pro", "Google"),
    "gemini 1.5 flash": ("gemini-1.5-flash", "Google"),
    "gemini 1.5 pro": ("gemini-1.5-pro", "Google"),
    "claude opus 4.6": ("claude-opus-4-6", "Anthropic"),
    "claude sonnet 3.5": ("claude-3-5-sonnet", "Anthropic"),
    "claude 3.5 sonnet": ("claude-3-5-sonnet", "Anthropic"),
    "claude 3.7 sonnet": ("claude-3-7-sonnet", "Anthropic"),
}

# Regex to detect user settings change blocks in transcript content
_MODEL_SETTINGS_BLOCK = re.compile(
    r"<USER_SETTINGS_CHANGE>(.*?)</USER_SETTINGS_CHANGE>",
    re.DOTALL | re.IGNORECASE,
)

# Regex to extract target model display name from the setting change text
_TARGET_MODEL_PATTERN = re.compile(
    r"The user changed setting\s+`Model Selection`\s+(?:from\s+.*?\s+)?to\s+(?P<model>.*?)(?:\.\s+No need to comment|\.\s*$|\s*$|\.$)",
    re.DOTALL | re.IGNORECASE,
)


def _normalize_path(p: str) -> str:
    """Normalizes file URI or local path for case-insensitive matching across OSes."""
    if p.startswith("file://"):
        parsed = urllib.parse.urlparse(p)
        p = urllib.parse.unquote(parsed.path or "")
        # On Windows file:///C:/... parses as /C:/...; strip leading slash before drive letter
        if re.match(r"^/[A-Za-z]:", p):
            p = p[1:]
    else:
        p = urllib.parse.unquote(p)
    return str(Path(p).resolve()).lower()


def _resolve_model_metadata(display_name: str) -> Tuple[Optional[str], str]:
    """Resolves canonical model ID and provider from a display name.
    
    Returns (canonical_id, provider). If unmapped, canonical_id is None.
    """
    if not display_name or display_name.strip().lower() == "unknown":
        return None, "Unknown"

    # Strip parenthesized suffixes (e.g. ' (High)', ' (Medium)', ' (Thinking)')
    cleaned = re.sub(r"\s*\([^)]*\)", "", display_name).strip().lower()

    if cleaned in VERIFIED_MODEL_MAP:
        return VERIFIED_MODEL_MAP[cleaned]

    # Provider heuristic without guessing model ID
    if "gemini" in cleaned:
        return None, "Google"
    if "claude" in cleaned:
        return None, "Anthropic"
    if "gpt" in cleaned or "openai" in cleaned:
        return None, "OpenAI"

    return None, "Unknown"


class AntigravityUsageCollector(BaseUsageCollector):
    """Collector for Google Antigravity session traces."""

    def __init__(
        self,
        antigravity_dir: Optional[Union[str, Path]] = None,
        db_path: Optional[Union[str, Path]] = None,
        brain_dir: Optional[Union[str, Path]] = None,
    ):
        base_dir = Path(antigravity_dir) if antigravity_dir else (Path.home() / ".gemini" / "antigravity")
        self.antigravity_dir = base_dir
        self.db_path = Path(db_path) if db_path else (self.antigravity_dir / "conversation_summaries.db")
        self.brain_dir = Path(brain_dir) if brain_dir else (self.antigravity_dir / "brain")

    @property
    def agent_name(self) -> str:
        return "Google Antigravity"

    @property
    def provider_name(self) -> str:
        return "Google"

    def is_available(self) -> bool:
        """Returns True if local Antigravity directory or session database is detected."""
        return self.db_path.exists() or self.brain_dir.exists()

    def discover_sessions(self, workspace_path: Optional[str] = None) -> List[SessionDescriptor]:
        """Discovers sessions from conversation_summaries.db in strict read-only mode.
        
        If workspace_path is provided, filters for sessions matching that workspace root.
        """
        if not self.db_path.exists():
            logger.warning(f"Antigravity session database not found: {self.db_path}")
            return []

        norm_workspace = _normalize_path(workspace_path) if workspace_path else None
        results: List[SessionDescriptor] = []

        file_uri = self.db_path.resolve().as_uri() + "?mode=ro"

        try:
            conn = sqlite3.connect(file_uri, uri=True)
            cur = conn.cursor()
            cur.execute(
                """
                SELECT conversation_id, title, step_count, last_modified_time, workspace_uris
                FROM conversation_summaries
                ORDER BY last_modified_time DESC
                """
            )
            rows = cur.fetchall()
            conn.close()
        except sqlite3.Error as e:
            logger.error(f"Failed to query Antigravity session database: {e}")
            return []

        for row in rows:
            conv_id, title, step_count, last_mod_str, ws_uris_json = row

            ws_match = False
            first_ws_path: Optional[str] = None

            if ws_uris_json:
                try:
                    uris = json.loads(ws_uris_json)
                    if isinstance(uris, list) and uris:
                        first_ws_path = uris[0]
                        if norm_workspace:
                            for u in uris:
                                if _normalize_path(u) == norm_workspace:
                                    ws_match = True
                                    break
                except Exception:
                    pass

            # Filter if workspace_path was specified
            if norm_workspace and not ws_match:
                continue

            last_active: Optional[datetime] = None
            if last_mod_str:
                try:
                    last_active = datetime.fromisoformat(last_mod_str)
                    if last_active.tzinfo is None:
                        last_active = last_active.replace(tzinfo=timezone.utc)
                except Exception:
                    pass

            results.append(
                SessionDescriptor(
                    session_id=conv_id,
                    agent=self.agent_name,
                    provider=self.provider_name,
                    title=title or None,
                    workspace_path=first_ws_path,
                    start_time=None,
                    last_active_time=last_active,
                    turn_count=step_count or 0,
                )
            )

        return results

    def get_latest_session(self, workspace_path: Optional[str] = None) -> Optional[SessionDescriptor]:
        """Returns the most recent session, optionally filtered by workspace."""
        sessions = self.discover_sessions(workspace_path=workspace_path)
        return sessions[0] if sessions else None

    def get_session_by_id(self, session_id: str) -> Optional[SessionDescriptor]:
        """Finds a specific session by its unique ID."""
        if not self.db_path.exists():
            return None

        file_uri = self.db_path.resolve().as_uri() + "?mode=ro"
        try:
            conn = sqlite3.connect(file_uri, uri=True)
            cur = conn.cursor()
            cur.execute(
                """
                SELECT conversation_id, title, step_count, last_modified_time, workspace_uris
                FROM conversation_summaries
                WHERE conversation_id = ?
                """,
                (session_id,),
            )
            row = cur.fetchone()
            conn.close()
        except sqlite3.Error as e:
            logger.error(f"Error querying session {session_id}: {e}")
            return None

        if not row:
            return None

        conv_id, title, step_count, last_mod_str, ws_uris_json = row
        first_ws: Optional[str] = None
        if ws_uris_json:
            try:
                uris = json.loads(ws_uris_json)
                if isinstance(uris, list) and uris:
                    first_ws = uris[0]
            except Exception:
                pass

        last_active: Optional[datetime] = None
        if last_mod_str:
            try:
                last_active = datetime.fromisoformat(last_mod_str)
                if last_active.tzinfo is None:
                    last_active = last_active.replace(tzinfo=timezone.utc)
            except Exception:
                pass

        return SessionDescriptor(
            session_id=conv_id,
            agent=self.agent_name,
            provider=self.provider_name,
            title=title or None,
            workspace_path=first_ws,
            start_time=None,
            last_active_time=last_active,
            turn_count=step_count or 0,
        )

    def collect_records(self, session_id: str) -> List[CanonicalUsageRecord]:
        """Parses the transcript for a given session into canonical usage records."""
        if not session_id or session_id in (".", "..") or "/" in session_id or "\\" in session_id or ".." in session_id:
            logger.warning(f"Rejected invalid session identifier: {session_id!r}")
            return []

        brain_root = self.brain_dir.resolve()
        session_dir = (self.brain_dir / session_id).resolve()
        if not session_dir.is_relative_to(brain_root) or session_dir == brain_root:
            logger.warning(f"Rejected session path outside brain directory: {session_id!r}")
            return []

        transcript_path = session_dir / ".system_generated" / "logs" / "transcript.jsonl"
        if not transcript_path.exists():
            return []
        return self.parse_transcript_file(transcript_path, session_id=session_id)

    def parse_transcript_file(
        self,
        transcript_path: Union[str, Path],
        session_id: str = "unknown-session",
    ) -> List[CanonicalUsageRecord]:
        """Parses a specific transcript.jsonl file into validated CanonicalUsageRecord objects.
        
        Guarantees:
        - Line-by-line streaming without loading whole file into memory.
        - Robust handling of corrupt/partial JSON lines.
        - Non-generation events (USER_INPUT, GENERIC, SYSTEM_MESSAGE) are excluded from usage records.
        - Accurate model-switch tracking: each generation is linked to the model active at that step.
        - Missing token counts are preserved as None.
        - No private prompt or thinking content is extracted or stored.
        - Duplicate turn events with the same step_index are ignored.
        """
        path = Path(transcript_path)
        if not path.exists():
            logger.warning(f"Transcript file not found: {path}")
            return []

        records: List[CanonicalUsageRecord] = []
        seen_turn_indices: Set[int] = set()

        # State tracking for active model in the session
        current_display_name: str = "Unknown"
        current_model_id: Optional[str] = None
        current_provider: str = self.provider_name

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line_str = line.strip()
                    if not line_str:
                        continue

                    try:
                        event = json.loads(line_str)
                    except Exception:
                        # Skip corrupt or partial JSON lines safely
                        continue

                    if not isinstance(event, dict):
                        continue

                    event_type = event.get("type")

                    # 1. Track Model Selection Switches from user input metadata
                    if event_type == "USER_INPUT":
                        content = event.get("content", "")
                        if isinstance(content, str) and "<USER_SETTINGS_CHANGE>" in content:
                            block_match = _MODEL_SETTINGS_BLOCK.search(content)
                            if block_match:
                                block_text = block_match.group(1)
                                target_match = _TARGET_MODEL_PATTERN.search(block_text)
                                if target_match:
                                    raw_model_name = target_match.group("model").strip().rstrip(".\r\n ")
                                    if raw_model_name:
                                        current_display_name = raw_model_name
                                        m_id, prov = _resolve_model_metadata(raw_model_name)
                                        current_model_id = m_id
                                        current_provider = prov

                    # 2. Extract Generation Metrics from PLANNER_RESPONSE
                    elif event_type == "PLANNER_RESPONSE":
                        turn_idx = event.get("step_index")
                        if turn_idx is None or not isinstance(turn_idx, int) or turn_idx < 0:
                            continue

                        # Deduplicate: Avoid counting the same step twice
                        if turn_idx in seen_turn_indices:
                            continue

                        # Validate numeric token counts
                        input_tok = event.get("input_tokens")
                        output_tok = event.get("output_tokens")

                        if input_tok is None or not isinstance(input_tok, int) or input_tok < 0:
                            continue
                        if output_tok is None or not isinstance(output_tok, int) or output_tok < 0:
                            continue

                        cache_tok = event.get("cache_read_tokens")
                        if cache_tok is not None and (not isinstance(cache_tok, int) or cache_tok < 0):
                            cache_tok = None

                        # Parse timestamp
                        created_at_str = event.get("created_at")
                        if not created_at_str or not isinstance(created_at_str, str):
                            # Missing timestamp - skip invalid turn
                            continue

                        try:
                            ts = datetime.fromisoformat(created_at_str)
                            if ts.tzinfo is None:
                                ts = ts.replace(tzinfo=timezone.utc)
                        except Exception:
                            continue

                        # Build canonical record (strictly excludes prompt/thinking text)
                        record = CanonicalUsageRecord(
                            provider=current_provider,
                            agent=self.agent_name,
                            session_id=session_id,
                            turn_index=turn_idx,
                            model_display_name=current_display_name,
                            model_id=current_model_id,
                            timestamp=ts,
                            input_tokens=input_tok,
                            output_tokens=output_tok,
                            cache_read_tokens=cache_tok,
                            cache_write_tokens=None,
                            reasoning_tokens=None,
                            source="transcript.jsonl",
                        )

                        seen_turn_indices.add(turn_idx)
                        records.append(record)
        except OSError as e:
            logger.error(f"Failed to read transcript file {path}: {e}")
            return []

        return records

