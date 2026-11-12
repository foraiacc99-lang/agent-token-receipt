"""Read-only usage collector for Google Gemini CLI chat session files."""

from datetime import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from collector._utils import (
    canonicalize_model_id,
    normalize_fs_path,
    parse_iso_timestamp,
    workspace_sha256_candidates,
    workspaces_match,
)
from collector.base import BaseUsageCollector, SessionDescriptor
from core.models import CanonicalUsageRecord


class GeminiCLIUsageCollector(BaseUsageCollector):
    """Collects verifiable usage metrics from ~/.gemini/tmp/<project>/chats/ transcripts."""

    agent_name = "Gemini CLI"
    provider_name = "Google"
    supports_token_telemetry = True
    telemetry_unavailable_reason: Optional[str] = None

    def __init__(self, gemini_dir: Optional[Path] = None):
        self.gemini_dir = Path(gemini_dir) if gemini_dir is not None else Path.home() / ".gemini"
        self.tmp_dir = self.gemini_dir / "tmp"
        self.projects_json_path = self.gemini_dir / "projects.json"

    def is_available(self) -> bool:
        """Return True when Gemini CLI's ~/.gemini/tmp directory is present."""
        return self.tmp_dir.is_dir()

    def _load_project_slug_map(self) -> Dict[str, str]:
        """Load optional ~/.gemini/projects.json mapping slug -> workspace path."""
        slug_to_path: Dict[str, str] = {}
        if not self.projects_json_path.is_file():
            return slug_to_path
        try:
            data = json.loads(self.projects_json_path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            return slug_to_path
        if isinstance(data, dict):
            projects = data.get("projects", data)
            if isinstance(projects, dict):
                for raw_path, slug in projects.items():
                    if isinstance(raw_path, str) and isinstance(slug, str):
                        slug_to_path[slug] = raw_path
        return slug_to_path

    def _project_dir_matches_workspace(
        self,
        project_dir: Path,
        project_hash: Optional[str],
        workspace_path: Optional[str],
        slug_map: Dict[str, str],
    ) -> Optional[str]:
        """Resolve project root path if known and check whether it matches workspace_path."""
        detected_root: Optional[str] = slug_map.get(project_dir.name)

        dot_root = project_dir / ".project_root"
        if dot_root.is_file():
            try:
                content = dot_root.read_text(encoding="utf-8", errors="replace").strip()
                if content:
                    detected_root = content
            except OSError:
                pass

        if workspace_path is None:
            return detected_root

        if detected_root is not None:
            return detected_root if workspaces_match(detected_root, workspace_path) else None

        ws_hashes = set(workspace_sha256_candidates(workspace_path))
        if project_dir.name.lower() in ws_hashes or (
            project_hash and project_hash.lower() in ws_hashes
        ):
            return normalize_fs_path(workspace_path)
        return None

    @staticmethod
    def _extract_uncached_input(tokens: Dict[str, Any]) -> Tuple[int, Optional[int]]:
        """Disambiguate whether Gemini CLI ``tokens.input`` already subtracted cached tokens.

        Uses the recorded ``tokens.total`` invariant when present so neither
        ``input = promptTokenCount`` nor ``input = promptTokenCount - cached``
        is double-counted or under-counted.
        """
        raw_input = max(0, int(tokens.get("input") or 0))
        cached_raw = tokens.get("cached")
        if cached_raw is None:
            return raw_input, None

        cached = max(0, int(cached_raw))
        if cached == 0:
            return raw_input, 0

        output = max(0, int(tokens.get("output") or 0))
        thoughts = max(0, int(tokens.get("thoughts") or 0))
        tool = max(0, int(tokens.get("tool") or 0))
        total_raw = tokens.get("total")

        if total_raw is not None:
            total = max(0, int(total_raw))
            sum_uncached = raw_input + output + cached + thoughts + tool
            sum_inclusive = raw_input + output + thoughts + tool
            if total == sum_inclusive and raw_input >= cached and sum_uncached != total:
                return max(0, raw_input - cached), cached
            return raw_input, cached

        return raw_input, cached

    def _scan_jsonl_session(self, file_path: Path) -> Dict[str, Any]:
        """Parse Gemini CLI delta-patched JSONL transcript cleanly."""
        session_id = file_path.stem
        project_hash: Optional[str] = None
        start_ts: Optional[datetime] = None
        last_ts: Optional[datetime] = None

        messages_by_id: Dict[str, Dict[str, Any]] = {}
        msg_order: List[str] = []

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                for idx, raw_line in enumerate(f):
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(ev, dict):
                        continue

                    if "sessionId" in ev and "projectHash" in ev:
                        if isinstance(ev.get("sessionId"), str) and ev["sessionId"].strip():
                            session_id = ev["sessionId"].strip()
                        if isinstance(ev.get("projectHash"), str) and ev["projectHash"].strip():
                            project_hash = ev["projectHash"].strip()
                        st = parse_iso_timestamp(ev.get("startTime"))
                        if st is not None:
                            start_ts = st
                        continue

                    ts = parse_iso_timestamp(ev.get("timestamp"))
                    if ts is not None:
                        if start_ts is None or ts < start_ts:
                            start_ts = ts
                        if last_ts is None or ts > last_ts:
                            last_ts = ts

                    ev_type = ev.get("type")
                    msg_id = str(ev.get("id") or f"line-{idx}")

                    if ev_type == "gemini":
                        if msg_id not in messages_by_id:
                            msg_order.append(msg_id)
                        messages_by_id[msg_id] = {
                            "raw_model": ev.get("model"),
                            "timestamp": ts,
                            "tokens": ev.get("tokens") if isinstance(ev.get("tokens"), dict) else None,
                        }
                    elif ev_type == "message_update":
                        existing = messages_by_id.get(msg_id)
                        if existing is not None:
                            if ts is not None:
                                existing["timestamp"] = ts
                            if isinstance(ev.get("model"), str):
                                existing["raw_model"] = ev.get("model")
                            if isinstance(ev.get("tokens"), dict):
                                existing["tokens"] = ev.get("tokens")
        except OSError:
            pass

        turns: List[Dict[str, Any]] = []
        for mid in msg_order:
            msg = messages_by_id[mid]
            tokens = msg.get("tokens")
            ts = msg.get("timestamp")
            if not isinstance(tokens, dict) or ts is None:
                continue
            if "input" not in tokens or "output" not in tokens:
                continue
            uncached_in, cached = self._extract_uncached_input(tokens)
            thoughts_raw = tokens.get("thoughts")
            thoughts = int(thoughts_raw) if thoughts_raw is not None and int(thoughts_raw) > 0 else None
            turns.append(
                {
                    "raw_model": msg.get("raw_model") or "gemini-2.5-pro",
                    "timestamp": ts,
                    "input_tokens": uncached_in,
                    "output_tokens": max(0, int(tokens.get("output") or 0)),
                    "cache_read_tokens": cached,
                    "reasoning_tokens": thoughts,
                }
            )

        return {
            "session_id": session_id,
            "project_hash": project_hash,
            "start_time": start_ts,
            "last_active_time": last_ts,
            "turns": turns,
        }

    def _scan_legacy_json_session(self, file_path: Path) -> Dict[str, Any]:
        """Parse legacy monolithic JSON session file in chats/session-*.json."""
        session_id = file_path.stem
        project_hash: Optional[str] = None
        start_ts: Optional[datetime] = None
        last_ts: Optional[datetime] = None
        turns: List[Dict[str, Any]] = []

        try:
            data = json.loads(file_path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            return {
                "session_id": session_id,
                "project_hash": None,
                "start_time": None,
                "last_active_time": None,
                "turns": [],
            }

        if not isinstance(data, dict):
            return {
                "session_id": session_id,
                "project_hash": None,
                "start_time": None,
                "last_active_time": None,
                "turns": [],
            }

        if isinstance(data.get("sessionId"), str) and data["sessionId"].strip():
            session_id = data["sessionId"].strip()
        if isinstance(data.get("projectHash"), str) and data["projectHash"].strip():
            project_hash = data["projectHash"].strip()

        start_ts = parse_iso_timestamp(data.get("startTime"))
        last_ts = parse_iso_timestamp(data.get("lastUpdated"))

        for msg in data.get("messages", []):
            if not isinstance(msg, dict) or msg.get("type") != "gemini":
                continue
            tokens = msg.get("tokens")
            ts = parse_iso_timestamp(msg.get("timestamp")) or last_ts or start_ts
            if not isinstance(tokens, dict) or ts is None:
                continue
            if "input" not in tokens or "output" not in tokens:
                continue
            uncached_in, cached = self._extract_uncached_input(tokens)
            thoughts_raw = tokens.get("thoughts")
            thoughts = int(thoughts_raw) if thoughts_raw is not None and int(thoughts_raw) > 0 else None
            turns.append(
                {
                    "raw_model": msg.get("model") or "gemini-2.5-pro",
                    "timestamp": ts,
                    "input_tokens": uncached_in,
                    "output_tokens": max(0, int(tokens.get("output") or 0)),
                    "cache_read_tokens": cached,
                    "reasoning_tokens": thoughts,
                }
            )

        return {
            "session_id": session_id,
            "project_hash": project_hash,
            "start_time": start_ts,
            "last_active_time": last_ts,
            "turns": turns,
        }

    def _iter_project_chat_files(self) -> List[Tuple[Path, Path]]:
        if not self.tmp_dir.is_dir():
            return []
        found: List[Tuple[Path, Path]] = []
        try:
            for project_dir in sorted(p for p in self.tmp_dir.iterdir() if p.is_dir()):
                chats_dir = project_dir / "chats"
                if not chats_dir.is_dir():
                    continue
                for chat_file in sorted(chats_dir.glob("session-*.jsonl")):
                    found.append((project_dir, chat_file))
                for legacy_file in sorted(chats_dir.glob("session-*.json")):
                    found.append((project_dir, legacy_file))
        except OSError:
            pass
        return found

    def _scan_chat_file(self, chat_file: Path) -> Dict[str, Any]:
        if chat_file.suffix == ".jsonl":
            return self._scan_jsonl_session(chat_file)
        return self._scan_legacy_json_session(chat_file)

    def discover_sessions(
        self, workspace_path: Optional[str] = None
    ) -> List[SessionDescriptor]:
        """Discover local Gemini CLI chat sessions, optionally scoped by workspace."""
        if not self.is_available():
            return []

        slug_map = self._load_project_slug_map()
        descriptors: List[SessionDescriptor] = []
        seen_ids = set()

        for project_dir, chat_file in self._iter_project_chat_files():
            parsed = self._scan_chat_file(chat_file)
            matched_ws = self._project_dir_matches_workspace(
                project_dir, parsed["project_hash"], workspace_path, slug_map
            )
            if workspace_path is not None and matched_ws is None:
                continue

            sid = parsed["session_id"]
            if sid in seen_ids:
                continue
            seen_ids.add(sid)

            descriptors.append(
                SessionDescriptor(
                    session_id=sid,
                    agent=self.agent_name,
                    provider=self.provider_name,
                    title=f"Gemini CLI ({sid[:8]})",
                    workspace_path=matched_ws,
                    start_time=parsed["start_time"],
                    last_active_time=parsed["last_active_time"],
                    turn_count=len(parsed["turns"]),
                )
            )

        descriptors.sort(
            key=lambda s: s.last_active_time.timestamp() if s.last_active_time else 0.0,
            reverse=True,
        )
        return descriptors

    def collect_records(self, session_id: str) -> List[CanonicalUsageRecord]:
        """Collect normalized usage records for a specific Gemini CLI session."""
        if not self.is_available():
            return []

        for _, chat_file in self._iter_project_chat_files():
            parsed = self._scan_chat_file(chat_file)
            if parsed["session_id"] == session_id or chat_file.stem == session_id:
                records: List[CanonicalUsageRecord] = []
                for idx, turn in enumerate(parsed["turns"]):
                    model_id, display_name = canonicalize_model_id(turn["raw_model"])
                    records.append(
                        CanonicalUsageRecord(
                            provider=self.provider_name,
                            agent=self.agent_name,
                            session_id=parsed["session_id"],
                            turn_index=idx,
                            model_display_name=display_name,
                            model_id=model_id,
                            timestamp=turn["timestamp"],
                            input_tokens=turn["input_tokens"],
                            output_tokens=turn["output_tokens"],
                            cache_read_tokens=turn["cache_read_tokens"],
                            cache_write_tokens=None,
                            reasoning_tokens=turn["reasoning_tokens"],
                            source="gemini_cli_chat",
                        )
                    )
                return records

        return []

