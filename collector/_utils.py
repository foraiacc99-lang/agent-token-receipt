"""Shared utility helpers for multi-agent usage collectors."""

from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
from typing import Dict, Iterable, Optional

KNOWN_MODEL_DISPLAY_NAMES: Dict[str, str] = {
    "gemini-3.8-flash": "Gemini 3.8 Flash",
    "gemini-3.8-pro": "Gemini 3.8 Pro",
    "gemini-2.5-flash": "Gemini 2.5 Flash",
    "gemini-2.5-pro": "Gemini 2.5 Pro",
    "gemini-1.5-flash": "Gemini 1.5 Flash",
    "gemini-1.5-pro": "Gemini 1.5 Pro",
    "claude-opus-4-6": "Claude Opus 4.6",
    "claude-sonnet-4-6": "Claude Sonnet 4.6",
    "claude-haiku-4-5": "Claude Haiku 4.5",
    "claude-3-7-sonnet": "Claude 3.7 Sonnet",
    "claude-3-5-sonnet": "Claude 3.5 Sonnet",
    "gpt-5.4": "GPT-5.4",
    "gpt-5": "GPT-5",
    "gpt-4.1": "GPT-4.1",
    "o3": "o3",
}

_KNOWN_DATED_PREFIXES = tuple(KNOWN_MODEL_DISPLAY_NAMES.keys())

_DATE_SUFFIX_RE = re.compile(r"^(?P<base>.+?)-(?:20\d{6}|20\d{2}-\d{2}-\d{2})$")


def normalize_fs_path(path_value: str | Path) -> str:
    """Normalize a local filesystem path cleanly for workspace comparison."""
    raw = str(path_value).strip()
    if not raw:
        return ""
    try:
        resolved = str(Path(raw).expanduser().resolve())
    except OSError:
        resolved = os.path.normpath(raw)
    resolved = os.path.normpath(resolved)
    if os.name == "nt":
        resolved = resolved.lower()
    return resolved


def workspaces_match(session_cwd: Optional[str], workspace_path: Optional[str]) -> bool:
    """Return True when a session cwd matches the requested workspace path filter."""
    if not workspace_path:
        return True
    if not session_cwd:
        return False
    return normalize_fs_path(session_cwd) == normalize_fs_path(workspace_path)


def parse_iso_timestamp(ts_value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp into a timezone-aware datetime (UTC default)."""
    if not ts_value or not isinstance(ts_value, str):
        return None
    cleaned = ts_value.strip()
    if not cleaned:
        return None
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def canonicalize_model_id(raw_model: Optional[str]) -> tuple[Optional[str], str]:
    """Resolve raw provider model strings to canonical catalogue IDs and display names.

    Only known published models with optional YYYYMMDD / YYYY-MM-DD release suffixes
    are stripped to a canonical catalogue ID; unknown models preserve their exact raw ID
    so the pricing engine cleanly marks them as unknown without guessing.
    """
    if not raw_model or not isinstance(raw_model, str):
        return None, "Unknown Model"

    cleaned = raw_model.strip()
    if not cleaned:
        return None, "Unknown Model"

    lowered = cleaned.lower()
    if lowered in KNOWN_MODEL_DISPLAY_NAMES:
        return lowered, KNOWN_MODEL_DISPLAY_NAMES[lowered]

    match = _DATE_SUFFIX_RE.match(lowered)
    if match:
        base = match.group("base")
        if base in KNOWN_MODEL_DISPLAY_NAMES:
            return base, KNOWN_MODEL_DISPLAY_NAMES[base]

    return cleaned, cleaned


def infer_provider_from_model(model_id: Optional[str], default_provider: str) -> str:
    """Infer model vendor name conservatively from a canonical or raw model ID."""
    if not model_id:
        return default_provider
    low = model_id.lower()
    if low.startswith("claude"):
        return "Anthropic"
    if low.startswith("gemini"):
        return "Google"
    if low.startswith(("gpt-", "o1", "o3", "o4", "codex")):
        return "OpenAI"
    return default_provider


def workspace_sha256_candidates(workspace_path: str | Path) -> Iterable[str]:
    """Yield SHA-256 hex digests for common workspace path representations."""
    p = Path(workspace_path).expanduser()
    try:
        resolved = str(p.resolve())
    except OSError:
        resolved = os.path.normpath(str(p))

    candidates = [str(workspace_path), resolved, resolved.lower(), resolved.replace("\\", "/")]
    seen = set()
    for c in candidates:
        if not c:
            continue
        digest = hashlib.sha256(c.encode("utf-8")).hexdigest()
        if digest not in seen:
            seen.add(digest)
            yield digest

