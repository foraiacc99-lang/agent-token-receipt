"""Google-style read-only collector for local Claude Code session transcripts."""

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


class ClaudeCodeUsageCollector(BaseUsageCollector):
    """Collects verifiable usage telemetry from local Claude Code JSONL transcripts."""

    agent_name = "Claude Code"
    provider_name = "Anthropic"
    supports_token_telemetry = True
    telemetry_unavailable_reason: Optional[str] = None

    def __init__(self, claude_dir: Optional[Path] = None):
        self.claude_dir = Path(claude_dir) if claude_dir is not None else Path.home() / ".claude"
        self.projects_dir = self.claude_dir / "projects"

    def is_available(self) -> bool:
        """Return True if Claude Code's local projects transcript directory exists."""
        return self.projects_dir.is_dir()

    def _iter_session_file_groups(self) -> List[Tuple[str, List[Path]]]:
        """Discover session root JSONL files alongside any subagent JSONL files."""
        if not self.projects_dir.is_dir():
            return []

        groups: Dict[str, List[Path]] = {}
        try:
            project_dirs = sorted(p for p in self.projects_dir.iterdir() if p.is_dir())
        except OSError:
            return []

        for project_dir in project_dirs:
            try:
                jsonl_files = sorted(project_dir.glob("*.jsonl"))
            except OSError:
                continue

            for root_file in jsonl_files:
                sid = root_file.stem
                file_list = [root_file]
                subagent_dir = project_dir / sid / "subagents"
                if subagent_dir.is_dir():
                    try:
                        file_list.extend(sorted(subagent_dir.glob("*.jsonl")))
                    except OSError:
                        pass
                groups.setdefault(sid, []).extend(file_list)

        return list(groups.items())

    def _scan_session_files(
        self, fallback_session_id: str, files: List[Path]
    ) -> Dict[str, Any]:
        """Parse session metadata and deduplicated assistant usage turns read-only.

        Claude Code writes multiple streaming progress lines sharing the same
        ``message.id``. We keep only the latest/most complete token snapshot per
        unique ``message.id`` across the root transcript and its subagents, and
        never read prompt, thinking, or tool-output text.
        """
        session_id = fallback_session_id
        session_cwd: Optional[str] = None
        custom_title: Optional[str] = None
        ai_title: Optional[str] = None
        slug_title: Optional[str] = None
        first_ts: Optional[datetime] = None
        last_ts: Optional[datetime] = None

        deduped_turns: Dict[str, Tuple[Tuple[int, int, int], int, Dict[str, Any]]] = {}
        seq = 0

        for file_path in files:
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

                        seq += 1
                        ev_sid = event.get("sessionId")
                        if isinstance(ev_sid, str) and ev_sid.strip() and file_path.stem == fallback_session_id:
                            session_id = ev_sid.strip()

                        ev_cwd = event.get("cwd")
                        if isinstance(ev_cwd, str) and ev_cwd.strip() and session_cwd is None:
                            session_cwd = ev_cwd.strip()

                        ev_type = event.get("type")
                        if ev_type == "custom-title":
                            ct = event.get("customTitle")
                            if isinstance(ct, str) and ct.strip():
                                custom_title = ct.strip()
                        elif ev_type == "ai-title":
                            at = event.get("aiTitle")
                            if isinstance(at, str) and at.strip():
                                ai_title = at.strip()
                        elif not slug_title:
                            sl = event.get("slug")
                            if isinstance(sl, str) and sl.strip():
                                slug_title = sl.strip()

                        ts = parse_iso_timestamp(event.get("timestamp"))
                        if ts is not None:
                            if first_ts is None or ts < first_ts:
                                first_ts = ts
                            if last_ts is None or ts > last_ts:
                                last_ts = ts

                        if ev_type != "assistant":
                            continue

                        message = event.get("message")
                        if not isinstance(message, dict):
                            continue

                        raw_model = message.get("model")
                        if not isinstance(raw_model, str) or raw_model.strip() in ("", "<synthetic>"):
                            continue

                        usage = message.get("usage")
                        if not isinstance(usage, dict):
                            continue
                        if "input_tokens" not in usage or "output_tokens" not in usage:
                            continue
                        if ts is None:
                            continue

                        in_tok = int(usage.get("input_tokens") or 0)
                        out_tok = int(usage.get("output_tokens") or 0)
                        cr_raw = usage.get("cache_read_input_tokens")
                        cw_raw = usage.get("cache_creation_input_tokens")
                        cr_tok = int(cr_raw) if cr_raw is not None else None
                        cw_tok = int(cw_raw) if cw_raw is not None else None

                        msg_id = message.get("id")
                        dedup_key = (
                            f"id:{msg_id}"
                            if isinstance(msg_id, str) and msg_id.strip()
                            else f"line:{file_path.name}:{seq}"
                        )
                        completeness = (
                            out_tok,
                            in_tok + (cr_tok or 0) + (cw_tok or 0),
                            seq,
                        )
                        existing = deduped_turns.get(dedup_key)
                        if existing is None or completeness >= existing[0]:
                            deduped_turns[dedup_key] = (
                                completeness,
                                existing[1] if existing is not None else seq,
                                {
                                    "raw_model": raw_model.strip(),
                                    "timestamp": ts,
                                    "input_tokens": max(0, in_tok),
                                    "output_tokens": max(0, out_tok),
                                    "cache_read_tokens": max(0, cr_tok) if cr_tok is not None else None,
                                    "cache_write_tokens": max(0, cw_tok) if cw_tok is not None else None,
                                },
                            )
            except OSError:
                continue

        ordered_turns = [
            item[2]
            for item in sorted(
                deduped_turns.values(),
                key=lambda x: (x[2]["timestamp"], x[1]),
            )
        ]

        title = custom_title or ai_title or slug_title or f"Claude Code ({session_id[:8]})"
        return {
            "session_id": session_id,
            "cwd": session_cwd,
            "title": title,
            "start_time": first_ts,
            "last_active_time": last_ts,
            "turns": ordered_turns,
        }

    def discover_sessions(
        self, workspace_path: Optional[str] = None
    ) -> List[SessionDescriptor]:
        """Discover local Claude Code sessions, optionally filtered by workspace."""
        if not self.is_available():
            return []

        descriptors: List[SessionDescriptor] = []
        seen_ids = set()

        for sid, files in self._iter_session_file_groups():
            parsed = self._scan_session_files(sid, files)
            if not parsed["turns"] and parsed["cwd"] is None:
                continue
            if not workspaces_match(parsed["cwd"], workspace_path):
                continue

            resolved_sid = parsed["session_id"]
            if resolved_sid in seen_ids:
                continue
            seen_ids.add(resolved_sid)

            descriptors.append(
                SessionDescriptor(
                    session_id=resolved_sid,
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
        """Extract normalized per-turn usage records for a specific Claude Code session."""
        if not self.is_available():
            return []

        target_files: Optional[List[Path]] = None
        for sid, files in self._iter_session_file_groups():
            if sid == session_id:
                target_files = files
                break
            parsed_meta = self._scan_session_files(sid, files)
            if parsed_meta["session_id"] == session_id:
                target_files = files
                break

        if not target_files:
            return []

        parsed = self._scan_session_files(session_id, target_files)
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
                    reasoning_tokens=None,
                    source="claude_code_jsonl",
                )
            )

        return records

