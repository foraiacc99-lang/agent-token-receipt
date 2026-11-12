"""Usage data normalizer for Agent Token Receipt.

Transforms disparate raw usage dictionaries or objects into validated
CanonicalUsageRecord instances, enforcing strict zero-fabrication and typing rules.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from core.models import CanonicalUsageRecord


class UsageNormalizer:
    """Normalizes raw usage records into CanonicalUsageRecord models."""

    @staticmethod
    def normalize_record(
        raw: Union[Dict[str, Any], CanonicalUsageRecord],
        default_agent: str = "Google Antigravity",
        default_provider: str = "Google",
    ) -> Optional[CanonicalUsageRecord]:
        """Normalizes a single record or dictionary into CanonicalUsageRecord.
        
        Returns None if mandatory fields are missing or invalid.
        """
        if isinstance(raw, CanonicalUsageRecord):
            return raw

        if not isinstance(raw, dict):
            return None

        # Mandatory fields
        agent = str(raw.get("agent") or default_agent).strip()
        provider = str(raw.get("provider") or default_provider).strip()
        session_id = str(raw.get("session_id") or "unknown-session").strip()
        turn_index = raw.get("turn_index", raw.get("step_index", 0))

        if not isinstance(turn_index, int) or turn_index < 0:
            return None

        model_display_name = str(raw.get("model_display_name") or raw.get("model") or "Unknown").strip()
        model_id = raw.get("model_id")
        if model_id is not None:
            model_id = str(model_id).strip() or None

        # Timestamp parsing
        ts = raw.get("timestamp", raw.get("created_at"))
        if isinstance(ts, str):
            try:
                parsed_ts = datetime.fromisoformat(ts)
                if parsed_ts.tzinfo is None:
                    parsed_ts = parsed_ts.replace(tzinfo=timezone.utc)
                ts = parsed_ts
            except Exception:
                return None
        elif isinstance(ts, datetime):
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        else:
            return None

        # Token validation (non-negative)
        input_tokens = raw.get("input_tokens")
        output_tokens = raw.get("output_tokens")

        if input_tokens is None or not isinstance(input_tokens, int) or input_tokens < 0:
            return None
        if output_tokens is None or not isinstance(output_tokens, int) or output_tokens < 0:
            return None

        cache_read = raw.get("cache_read_tokens")
        if cache_read is not None and (not isinstance(cache_read, int) or cache_read < 0):
            cache_read = None

        cache_write = raw.get("cache_write_tokens")
        if cache_write is not None and (not isinstance(cache_write, int) or cache_write < 0):
            cache_write = None

        reasoning = raw.get("reasoning_tokens")
        if reasoning is not None and (not isinstance(reasoning, int) or reasoning < 0):
            reasoning = None

        source = str(raw.get("source") or "normalized-record")

        try:
            return CanonicalUsageRecord(
                provider=provider,
                agent=agent,
                session_id=session_id,
                turn_index=turn_index,
                model_display_name=model_display_name,
                model_id=model_id,
                timestamp=ts,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read_tokens=cache_read,
                cache_write_tokens=cache_write,
                reasoning_tokens=reasoning,
                source=source,
            )
        except Exception:
            return None

    @classmethod
    def normalize_records(
        cls,
        raw_list: List[Any],
        default_agent: str = "Google Antigravity",
        default_provider: str = "Google",
    ) -> List[CanonicalUsageRecord]:
        """Normalizes a list of raw records, skipping invalid entries without crashing."""
        normalized = []
        for item in raw_list:
            rec = cls.normalize_record(item, default_agent=default_agent, default_provider=default_provider)
            if rec is not None:
                normalized.append(rec)
        return normalized

