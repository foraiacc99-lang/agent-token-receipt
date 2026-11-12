"""Safe, idempotent universal installer, uninstaller, and doctor for coding agents."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any, Callable, Dict, List, Optional

from agent_token_receipt.installer.base import (
    ArtifactActionResult,
    InstallArtifact,
    InstallPlan,
    InstallSummary,
)
from agent_token_receipt.installer.detector import EnvironmentDetector
from agent_token_receipt.installer.registry import IntegrationRegistry
from agent_token_receipt.installer.templates import (
    MANAGED_MARKER_MD,
    MANAGED_MARKER_TOML,
)
from collector.antigravity import AntigravityUsageCollector
from collector.claude_code import ClaudeCodeUsageCollector
from collector.codex import CodexUsageCollector
from collector.cursor import CursorUsageCollector
from collector.gemini_cli import GeminiCLIUsageCollector
from collector.registry import CollectorRegistry, canonical_agent_key
from collector.windsurf import WindsurfUsageCollector
from pricing.calculator import CostCalculator


@dataclass
class DoctorAgentReport:
    """Verification report for one supported agent environment."""

    agent_key: str
    display_name: str
    detected_global: bool
    detected_project: bool
    invocation_syntax: str
    native_slash_supported: bool
    telemetry_supported: bool
    telemetry_available: bool
    telemetry_note: str
    installed_artifacts: List[Path] = field(default_factory=list)
    missing_artifacts: List[Path] = field(default_factory=list)


@dataclass
class DoctorReport:
    """Overall installation and environment health check report."""

    cli_on_path: Optional[str]
    catalogue_loaded: bool
    catalogue_model_count: int
    manifest_path: Path
    agents: List[DoctorAgentReport] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _has_managed_marker(text: str) -> bool:
    return MANAGED_MARKER_MD in text or MANAGED_MARKER_TOML in text


def _normalize_path_key(path: Path) -> str:
    norm = os.path.normpath(str(path.resolve()))
    return norm.lower() if os.name == "nt" else norm


class UniversalInstaller:
    """Orchestrates safe detection, planning, permission prompts, backups, install, uninstall, and doctor."""

    SUPPORTED_SCOPES = ("auto", "global", "project", "both")

    def __init__(
        self,
        home_dir: Optional[Path] = None,
        state_dir: Optional[Path] = None,
        probe_path_binaries: Optional[bool] = None,
    ):
        self.home_dir = Path(home_dir) if home_dir is not None else Path.home()
        self.state_dir = (
            Path(state_dir)
            if state_dir is not None
            else self.home_dir / ".agent-token-receipt"
        )
        self.manifest_path = self.state_dir / "install_manifest.json"
        self.registry = IntegrationRegistry(
            home_dir=self.home_dir,
            probe_path_binaries=probe_path_binaries,
        )
        self.detector = EnvironmentDetector(self.registry)

    def _load_manifest(self) -> Dict[str, Any]:
        if not self.manifest_path.is_file():
            return {"version": 1, "artifacts": {}}
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            return {"version": 1, "artifacts": {}}
        if not isinstance(data, dict) or not isinstance(data.get("artifacts"), dict):
            return {"version": 1, "artifacts": {}}
        return data

    def _save_manifest(self, manifest: Dict[str, Any]) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def plan_install(
        self,
        scope: str = "auto",
        workspace: Optional[Path] = None,
        agents: Optional[List[str]] = None,
    ) -> InstallPlan:
        """Build a transparent dry-run installation plan without writing files."""
        norm_scope = scope.strip().lower()
        if norm_scope not in self.SUPPORTED_SCOPES:
            raise ValueError(
                f"Unsupported scope '{scope}'. Choose from: {', '.join(self.SUPPORTED_SCOPES)}"
            )

        ws = Path(workspace).resolve() if workspace is not None else Path.cwd().resolve()
        statuses = self.detector.detect_all(workspace=ws, agents=agents)
        plan = InstallPlan(scope=norm_scope)

        explicit_agents = agents is not None and len(agents) > 0
        for st in statuses:
            if st.global_detection.detected:
                plan.detected_agents.append(st.global_detection)
            elif st.project_detection and st.project_detection.detected:
                plan.detected_agents.append(st.project_detection)

            target_scopes: List[str] = []
            if norm_scope == "global":
                if st.global_detection.detected or explicit_agents:
                    target_scopes.append("global")
            elif norm_scope == "project":
                if (
                    explicit_agents
                    or st.global_detection.detected
                    or (st.project_detection and st.project_detection.detected)
                ):
                    target_scopes.append("project")
            elif norm_scope == "both":
                if st.global_detection.detected or explicit_agents:
                    target_scopes.append("global")
                if (
                    explicit_agents
                    or st.global_detection.detected
                    or (st.project_detection and st.project_detection.detected)
                ):
                    target_scopes.append("project")
            else:  # "auto"
                if st.global_detection.detected or explicit_agents:
                    target_scopes.append("global")
                elif st.project_detection and st.project_detection.detected:
                    target_scopes.append("project")

            for sc in target_scopes:
                artifacts = st.integration.get_artifacts(scope=sc, workspace=ws)
                plan.artifacts.extend(artifacts)

            if target_scopes and not st.integration.native_slash_supported:
                plan.warnings.append(
                    f"{st.integration.display_name}: native /agent-billing slash command is deprecated; "
                    f"use '{st.integration.invocation_syntax}' instead."
                )
            if target_scopes and not st.integration.telemetry_supported:
                plan.warnings.append(
                    f"{st.integration.display_name}: {st.integration.telemetry_status_note}"
                )

        return plan

    def execute_install(
        self,
        plan: InstallPlan,
        yes: bool = False,
        dry_run: bool = False,
        force: bool = False,
        confirm_callback: Optional[Callable[[InstallPlan], bool]] = None,
    ) -> InstallSummary:
        """Install planned artifacts after explicit user consent unless dry_run=True."""
        summary = InstallSummary(action="install", warnings=list(plan.warnings))
        if not plan.artifacts:
            return summary

        if dry_run:
            for artifact in plan.artifacts:
                summary.actions.append(
                    ArtifactActionResult(
                        agent_key=artifact.agent_key,
                        target_path=artifact.target_path,
                        status="would_install",
                        message=f"[{artifact.scope}] {artifact.description}",
                    )
                )
            return summary

        if not yes:
            approved = confirm_callback(plan) if confirm_callback is not None else False
            if not approved:
                summary.aborted = True
                return summary

        manifest = self._load_manifest()
        artifacts_map: Dict[str, Any] = manifest["artifacts"]

        for artifact in plan.artifacts:
            target = artifact.target_path
            key = _normalize_path_key(target)
            entry = artifacts_map.get(key)

            try:
                if target.exists():
                    existing_text = target.read_text(encoding="utf-8", errors="replace")
                    if existing_text == artifact.content:
                        owners = set(entry.get("owners", [])) if isinstance(entry, dict) else set()
                        owners.add(artifact.agent_key)
                        artifacts_map[key] = {
                            "path": str(target),
                            "scope": artifact.scope,
                            "artifact_kind": artifact.artifact_kind,
                            "owners": sorted(owners),
                            "content_sha256": _sha256_text(artifact.content),
                            "backup_path": entry.get("backup_path") if isinstance(entry, dict) else None,
                            "created_parent_dir": entry.get("created_parent_dir") if isinstance(entry, dict) else None,
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }
                        summary.actions.append(
                            ArtifactActionResult(
                                agent_key=artifact.agent_key,
                                target_path=target,
                                status="unchanged",
                                message="Already installed and up to date.",
                            )
                        )
                        continue

                    is_managed = _has_managed_marker(existing_text) or (
                        isinstance(entry, dict)
                        and entry.get("content_sha256") == _sha256_text(existing_text)
                    )
                    if not is_managed and not force:
                        summary.actions.append(
                            ArtifactActionResult(
                                agent_key=artifact.agent_key,
                                target_path=target,
                                status="skipped_conflict",
                                message=(
                                    "Existing user-managed file preserved (re-run with --force to back up and replace)."
                                ),
                            )
                        )
                        continue

                    backup_path: Optional[Path] = None
                    if not is_managed:
                        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
                        backup_path = target.with_name(f"{target.name}.atr.bak.{stamp}")
                        shutil.copy2(target, backup_path)
                    elif isinstance(entry, dict) and entry.get("backup_path"):
                        backup_path = Path(entry["backup_path"])

                    target.write_text(artifact.content, encoding="utf-8")
                    owners = set(entry.get("owners", [])) if isinstance(entry, dict) else set()
                    owners.add(artifact.agent_key)
                    artifacts_map[key] = {
                        "path": str(target),
                        "scope": artifact.scope,
                        "artifact_kind": artifact.artifact_kind,
                        "owners": sorted(owners),
                        "content_sha256": _sha256_text(artifact.content),
                        "backup_path": str(backup_path) if backup_path else None,
                        "created_parent_dir": entry.get("created_parent_dir") if isinstance(entry, dict) else None,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                    summary.actions.append(
                        ArtifactActionResult(
                            agent_key=artifact.agent_key,
                            target_path=target,
                            status="updated",
                            backup_path=backup_path,
                            message="Updated existing managed artifact." if is_managed else "Backed up existing file and installed.",
                        )
                    )
                else:
                    parent_existed = target.parent.exists()
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(artifact.content, encoding="utf-8")

                    created_dir = (
                        str(target.parent)
                        if (not parent_existed and target.parent.name == "agent-billing")
                        else None
                    )
                    owners = set(entry.get("owners", [])) if isinstance(entry, dict) else set()
                    owners.add(artifact.agent_key)
                    artifacts_map[key] = {
                        "path": str(target),
                        "scope": artifact.scope,
                        "artifact_kind": artifact.artifact_kind,
                        "owners": sorted(owners),
                        "content_sha256": _sha256_text(artifact.content),
                        "backup_path": None,
                        "created_parent_dir": created_dir,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                    summary.actions.append(
                        ArtifactActionResult(
                            agent_key=artifact.agent_key,
                            target_path=target,
                            status="installed",
                            message=f"Installed ({artifact.scope}).",
                        )
                    )
            except OSError as exc:
                summary.actions.append(
                    ArtifactActionResult(
                        agent_key=artifact.agent_key,
                        target_path=target,
                        status="error",
                        message=str(exc),
                    )
                )

        self._save_manifest(manifest)
        return summary

    def uninstall(
        self,
        scope: str = "all",
        workspace: Optional[Path] = None,
        agents: Optional[List[str]] = None,
        yes: bool = False,
        confirm_callback: Optional[Callable[[List[Path]], bool]] = None,
    ) -> InstallSummary:
        """Safely remove managed Agent Token Receipt artifacts and restore backups."""
        ws = Path(workspace).resolve() if workspace is not None else Path.cwd().resolve()
        target_agent_keys = (
            {canonical_agent_key(a) for a in agents} if agents else set(self.registry.keys())
        )
        norm_scope = scope.strip().lower()
        scopes_filter = {"global", "project"} if norm_scope in ("all", "both", "auto") else {norm_scope}

        manifest = self._load_manifest()
        artifacts_map: Dict[str, Any] = manifest["artifacts"]

        # Build candidate paths from manifest PLUS standard integration paths (in case manifest missing)
        candidates: Dict[str, Dict[str, Any]] = {}
        for k, entry in artifacts_map.items():
            if not isinstance(entry, dict):
                continue
            if entry.get("scope") not in scopes_filter:
                continue
            owners = set(entry.get("owners", []))
            if owners & target_agent_keys:
                candidates[k] = dict(entry)

        # Fallback discovery by managed marker if file wasn't recorded in current manifest
        for integration in self.registry.select(list(target_agent_keys)):
            for sc in scopes_filter:
                if sc == "project" and ws is None:
                    continue
                for art in integration.get_artifacts(scope=sc, workspace=ws):
                    pk = _normalize_path_key(art.target_path)
                    if pk not in candidates and art.target_path.is_file():
                        try:
                            text = art.target_path.read_text(encoding="utf-8", errors="replace")
                        except OSError:
                            continue
                        if _has_managed_marker(text):
                            candidates[pk] = {
                                "path": str(art.target_path),
                                "scope": sc,
                                "owners": [integration.agent_key],
                                "backup_path": None,
                                "created_parent_dir": (
                                    str(art.target_path.parent)
                                    if art.target_path.parent.name == "agent-billing"
                                    else None
                                ),
                            }

        summary = InstallSummary(action="uninstall")
        if not candidates:
            return summary

        preview_paths = [Path(e["path"]) for e in candidates.values()]
        if not yes:
            approved = confirm_callback(preview_paths) if confirm_callback is not None else False
            if not approved:
                summary.aborted = True
                return summary

        for pk, entry in candidates.items():
            target = Path(entry["path"])
            owners = set(entry.get("owners", []))
            removed_for = sorted(owners & target_agent_keys)
            remaining_owners = sorted(owners - target_agent_keys)
            label_agent = removed_for[0] if removed_for else "unknown"

            if remaining_owners and target.exists():
                artifacts_map[pk]["owners"] = remaining_owners
                summary.actions.append(
                    ArtifactActionResult(
                        agent_key=label_agent,
                        target_path=target,
                        status="kept_shared",
                        message=f"Kept shared artifact still required by: {', '.join(remaining_owners)}",
                    )
                )
                continue

            backup_raw = entry.get("backup_path")
            backup_path = Path(backup_raw) if backup_raw else None

            try:
                if backup_path and backup_path.is_file():
                    shutil.copy2(backup_path, target)
                    backup_path.unlink()
                    artifacts_map.pop(pk, None)
                    summary.actions.append(
                        ArtifactActionResult(
                            agent_key=label_agent,
                            target_path=target,
                            status="restored_backup",
                            backup_path=backup_path,
                            message="Restored original file from backup.",
                        )
                    )
                    continue

                if target.is_file():
                    text = target.read_text(encoding="utf-8", errors="replace")
                    if pk in artifacts_map or _has_managed_marker(text):
                        target.unlink()
                        created_dir_raw = entry.get("created_parent_dir")
                        if created_dir_raw:
                            created_dir = Path(created_dir_raw)
                            try:
                                if created_dir.is_dir() and not any(created_dir.iterdir()):
                                    created_dir.rmdir()
                            except OSError:
                                pass
                        artifacts_map.pop(pk, None)
                        summary.actions.append(
                            ArtifactActionResult(
                                agent_key=label_agent,
                                target_path=target,
                                status="removed",
                                message="Removed installed artifact cleanly.",
                            )
                        )
                    else:
                        summary.actions.append(
                            ArtifactActionResult(
                                agent_key=label_agent,
                                target_path=target,
                                status="skipped_conflict",
                                message="Skipped file not managed by Agent Token Receipt.",
                            )
                        )
                else:
                    artifacts_map.pop(pk, None)
                    summary.actions.append(
                        ArtifactActionResult(
                            agent_key=label_agent,
                            target_path=target,
                            status="not_found",
                            message="File already removed; cleaned manifest entry.",
                        )
                    )
            except OSError as exc:
                summary.actions.append(
                    ArtifactActionResult(
                        agent_key=label_agent,
                        target_path=target,
                        status="error",
                        message=str(exc),
                    )
                )

        self._save_manifest(manifest)
        return summary

    def doctor(
        self,
        workspace: Optional[Path] = None,
        collector_registry: Optional[CollectorRegistry] = None,
    ) -> DoctorReport:
        """Inspect installed integrations, telemetry readiness, CLI binary, and pricing catalogue."""
        ws = Path(workspace).resolve() if workspace is not None else Path.cwd().resolve()
        cli_path = shutil.which("agent-token-receipt")
        issues: List[str] = []

        catalogue_ok = False
        model_count = 0
        try:
            calc = CostCalculator()
            model_count = len(calc.catalogue.models)
            catalogue_ok = model_count > 0
        except Exception as exc:
            issues.append(f"Pricing catalogue failed to load: {exc}")

        if not cli_path:
            issues.append(
                "'agent-token-receipt' command was not found on PATH; agents may need "
                "'python -m agent_token_receipt' or the installer Python fallback."
            )
        elif sys.prefix != sys.base_prefix:
            try:
                if Path(cli_path).resolve().is_relative_to(Path(sys.prefix).resolve()):
                    issues.append(
                        f"CLI is inside virtual environment '{sys.prefix}'; external agent shells "
                        "without this venv activated rely on the installed Python fallback path "
                        "(or install globally / via pipx for direct PATH access)."
                    )
            except OSError:
                pass

        if collector_registry is None:
            collector_registry = CollectorRegistry(
                {
                    "antigravity": AntigravityUsageCollector(
                        antigravity_dir=self.home_dir / ".gemini" / "antigravity"
                    ),
                    "claude_code": ClaudeCodeUsageCollector(
                        claude_dir=self.home_dir / ".claude"
                    ),
                    "codex": CodexUsageCollector(codex_dir=self.home_dir / ".codex"),
                    "gemini_cli": GeminiCLIUsageCollector(
                        gemini_dir=self.home_dir / ".gemini"
                    ),
                    "cursor": CursorUsageCollector(cursor_dir=self.home_dir / ".cursor"),
                    "windsurf": WindsurfUsageCollector(
                        codeium_windsurf_dir=self.home_dir / ".codeium" / "windsurf",
                        dot_windsurf_dir=self.home_dir / ".windsurf",
                    ),
                }
            )

        statuses = self.detector.detect_all(workspace=ws)
        agent_reports: List[DoctorAgentReport] = []

        for st in statuses:
            integ = st.integration
            coll = collector_registry.get(integ.agent_key)
            telemetry_avail = bool(
                coll
                and coll.is_available()
                and getattr(coll, "supports_token_telemetry", True)
            )
            installed_paths: List[Path] = []
            missing_paths: List[Path] = []

            check_scopes: List[str] = []
            if st.global_detection.detected:
                check_scopes.append("global")
            if st.project_detection and st.project_detection.detected:
                check_scopes.append("project")

            for sc in check_scopes:
                for art in integ.get_artifacts(scope=sc, workspace=ws):
                    if art.target_path.is_file():
                        installed_paths.append(art.target_path)
                    else:
                        missing_paths.append(art.target_path)

            if not check_scopes:
                # Also report if artifacts were manually installed in global scope anyway
                for art in integ.get_artifacts(scope="global", workspace=ws):
                    if art.target_path.is_file():
                        installed_paths.append(art.target_path)

            note = integ.telemetry_status_note
            if integ.telemetry_supported and not telemetry_avail:
                note = "Supported when local session logs exist (no session logs detected yet)."

            agent_reports.append(
                DoctorAgentReport(
                    agent_key=integ.agent_key,
                    display_name=integ.display_name,
                    detected_global=st.global_detection.detected,
                    detected_project=bool(st.project_detection and st.project_detection.detected),
                    invocation_syntax=integ.invocation_syntax,
                    native_slash_supported=integ.native_slash_supported,
                    telemetry_supported=integ.telemetry_supported,
                    telemetry_available=telemetry_avail,
                    telemetry_note=note,
                    installed_artifacts=installed_paths,
                    missing_artifacts=missing_paths,
                )
            )

        return DoctorReport(
            cli_on_path=cli_path,
            catalogue_loaded=catalogue_ok,
            catalogue_model_count=model_count,
            manifest_path=self.manifest_path,
            agents=agent_reports,
            issues=issues,
        )
