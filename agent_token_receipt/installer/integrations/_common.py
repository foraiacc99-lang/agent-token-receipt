"""Shared directory/binary detection helpers for agent integrations."""

from pathlib import Path
import shutil
from typing import Iterable, List, Optional

from agent_token_receipt.installer.base import DetectionResult


def probe_environment(
    agent_key: str,
    display_name: str,
    scope: str,
    candidate_paths: Iterable[Path],
    binary_names: Iterable[str] = (),
    probe_binaries: bool = True,
) -> DetectionResult:
    """Detect an agent installation cleanly from candidate paths and optional CLI binaries."""
    found_paths: List[Path] = [p for p in candidate_paths if p.exists()]
    found_binary: Optional[str] = None
    if probe_binaries:
        for b in binary_names:
            located = shutil.which(b)
            if located:
                found_binary = located
                break

    detected = bool(found_paths or found_binary)
    if found_paths and found_binary:
        reason = f"Found config path(s) ({', '.join(str(p) for p in found_paths)}) and CLI binary ({found_binary})"
    elif found_paths:
        reason = f"Found config path(s): {', '.join(str(p) for p in found_paths)}"
    elif found_binary:
        reason = f"Found CLI binary on PATH: {found_binary}"
    else:
        reason = f"No {display_name} configuration paths found for {scope} scope"

    return DetectionResult(
        agent_key=agent_key,
        display_name=display_name,
        scope=scope,
        detected=detected,
        reason=reason,
        detected_paths=found_paths,
        cli_binary=found_binary,
    )

