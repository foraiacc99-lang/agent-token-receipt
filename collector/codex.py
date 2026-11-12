"""Read-only usage collector for OpenAI Codex CLI rollout session logs."""

from datetime import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from collector._utils import (
    canonicalize_model_id,
    infer_provider_from_model,
    parse_iso_timestamp,
    workspaces_match,
)
from collector.base import BaseUsageCollector, SessionDescriptor
from core.models import CanonicalUsageRecord


class CodexUsageCollector(BaseUsageCollector):
    """Collects verifiable usage records from local ~/.codex/sessions rollout JSONL files."""

    agent_name = "OpenAI Codex"
    provider_name = "OpenAI"
    supports_token_telemetry = True
    telemetry_unavailable_reason: Optional[str] = None

    def __init__(self, codex_dir: Optional[Path] = None):
        self.codex_dir = Path(codex_dir) if codex_dir is not None else Path.home() / ".codex"
        self.sessions_dir = self.codex_dir / "sessions"
        self.index_path = self.codex_dir / "session_index.jsonl"

    def is_available(self) -> bool:
        """Return True when Codex local rollout session storage exists."""
        return self.sessions_dir.is_dir()

    def _load_session_titles(self) -> Dict[str, str]:
        """Read optional session titles from ~/.codex/session_index.jsonl."""
        titles: Dict[str, str] = {}
        if not self.index_path.is_file():
            return titles
        try:
            with open(self.index_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    raw = line.strip()
                    if not raw:
                        continue
                    try:
                        entry = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(entry, dict):
                        sid = entry.get("id")
                        name = entry.get("thread_name")
                        if isinstance(sid, str) and isinstance(name, str) and name.strip():
                            titles[sid.strip()] = name.strip()
        except OSError:
            pass
        return titles

    def _iter_rollout_files(self) -> List[Path]:
        if not self.sessions_dir.is_dir():
            return []
        try:
            return sorted(self.sessions_dir.rglob("rollout-*.jsonl"))
        except OSError:
            return []

    def _scan_rollout_file(self, file_path: Path, titles: Dict[str, str]) -> Dict[str, Any]:
        """Parse metadata and token_count events from one Codex rollout JSONL file.

        In OpenAI Codex CLI telemetry (verified against v0.156.1 logs),
        ``last_token_usage.input_tokens`` INCLUDES ``cached_input_tokens``
        (``total_tokens == input_tokens + output_tokens``). We therefore store
        ``uncached_input = max(0, input_tokens - cached_input_tokens)`` to
        prevent double-counting cached tokens.
        """
        session_id = file_path.stem
        session_cwd: Optional[str] = None
        active_model: Optional[str] = None
        first_ts: Optional[datetime] = None
        last_ts: Optional[datetime] = None
        seen_total_snapshots = set()
        turns: List[Dict[str, Any]] = []

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(event, dict):
                        continue

                    ts = parse_iso_timestamp(event.get("timestamp"))
                    if ts is not None:
                        if first_ts is None or ts < first_ts:
                            first_ts = ts
                        if last_ts is None or ts > last_ts:
                            last_ts = ts

                    ev_type = event.get("type")
                    payload = event.get("payload")
                    if not isinstance(payload, dict):
                        continue

                    if ev_type == "session_meta":
                        sid = payload.get("id")
                        if isinstance(sid, str) and sid.strip():
                            session_id = sid.strip()
                        cwd = payload.get("cwd")
                        if isinstance(cwd, str) and cwd.strip() and session_cwd is None:
                            session_cwd = cwd.strip()
                        meta_ts = parse_iso_timestamp(payload.get("timestamp"))
                        if meta_ts is not None and (first_ts is None or meta_ts < first_ts):
                            first_ts = meta_ts

                    elif ev_type == "turn_context":
                        model = payload.get("model")
                        if isinstance(model, str) and model.strip():
                            active_model = model.strip()
                        cwd = payload.get("cwd")
                        if isinstance(cwd, str) and cwd.strip() and session_cwd is None:
                            session_cwd = cwd.strip()

                    elif ev_type == "event_msg" and payload.get("type") == "token_count":
                        info = payload.get("info")
                        if not isinstance(info, dict):
                            continue
                        last_usage = info.get("last_token_usage")
                        if not isinstance(last_usage, dict):
                            continue
                        if ts is None:
                            continue

                        total_usage = info.get("total_token_usage")
                        if isinstance(total_usage, dict):
                            snap_key = (
                                int(total_usage.get("input_tokens") or 0),
                                int(total_usage.get("cached_input_tokens") or 0),
                                int(total_usage.get("output_tokens") or 0),
                                int(total_usage.get("reasoning_output_tokens") or 0),
                                int(total_usage.get("total_tokens") or 0),
                            )
                            if snap_key in seen_total_snapshots:
                                continue
                            seen_total_snapshots.add(snap_key)

                        raw_input = int(last_usage.get("input_tokens") or 0)
                        cached_raw = last_usage.get("cached_input_tokens")
                        cached_int = int(cached_raw) if cached_raw is not None else 0
                        uncached_input = max(0, raw_input - max(0, cached_int))
                        output = max(0, int(last_usage.get("output_tokens") or 0))

                        cw_raw = last_usage.get("cache_write_input_tokens")
                        cache_write_tokens = (
                            int(cw_raw) if cw_raw is not None and int(cw_raw) > 0 else None
                        )
                        reason_raw = last_usage.get("reasoning_output_tokens")
                        reasoning_tokens = (
                            int(reason_raw)
                            if reason_raw is not None and int(reason_raw) > 0
                            else None
                        )

                        turns.append(
                            {
                                "raw_model": active_model,
                                "timestamp": ts,
                                "input_tokens": uncached_input,
                                "output_tokens": output,
                                "cache_read_tokens": max(0, cached_int)
                                if cached_raw is not None
                                else None,
                                "cache_write_tokens": cache_write_tokens,
                                "reasoning_tokens": reasoning_tokens,
                            }
                        )
        except OSError:
            pass

        title = titles.get(session_id) or f"Codex Session ({session_id[:8]})"
        return {
            "session_id": session_id,
            "cwd": session_cwd,
            "title": title,
            "start_time": first_ts,
            "last_active_time": last_ts,
            "turns": turns,
        }

    def discover_sessions(
        self, workspace_path: Optional[str] = None
    ) -> List[SessionDescriptor]:
        """Discover local OpenAI Codex sessions filtered optionally by workspace."""
        if not self.is_available():
            return []

        titles = self._load_session_titles()
        descriptors: List[SessionDescriptor] = []
        seen_ids = set()

        for file_path in self._iter_rollout_files():
            parsed = self._scan_rollout_file(file_path, titles)
            if not parsed["turns"] and parsed["cwd"] is None:
                continue
            if not workspaces_match(parsed["cwd"], workspace_path):
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
                    title=parsed["title"],
                    workspace_path=parsed["cwd"],
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
        """Collect normalized per-turn usage records for one Codex session."""
        if not self.is_available():
            return []

        titles = self._load_session_titles()
        for file_path in self._iter_rollout_files():
            parsed = self._scan_rollout_file(file_path, titles)
            if parsed["session_id"] == session_id or file_path.stem == session_id:
                records: List[CanonicalUsageRecord] = []
                for idx, turn in enumerate(parsed["turns"]):
                    model_id, display_name = canonicalize_model_id(turn["raw_model"])
                    provider = infer_provider_from_model(model_id, self.provider_name)
                    records.append(
                        CanonicalUsageRecord(
                            provider=provider,
                            agent=self.agent_name,
                            session_id=parsed["session_id"],
                            turn_index=idx,
                            model_display_name=display_name,
                            model_id=model_id,
                            timestamp=turn["timestamp"],
                            input_tokens=turn["input_tokens"],
                            output_tokens=turn["output_tokens"],
                            cache_read_tokens=turn["cache_read_tokens"],
                            cache_write_tokens=turn["cache_write_tokens"],
                            reasoning_tokens=turn["reasoning_tokens"],
                            source="codex_rollout_jsonl",
                        )
                    )
                return records

        return []

