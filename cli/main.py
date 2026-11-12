"""Command-line interface for Agent Token Receipt.

Tagline: Every token has a receipt.
Provides simple, beginner-friendly commands to:
- List available Antigravity sessions (`sessions`).
- Interactively or directly generate thermal PDF receipts (`generate`).
- View version and help with full usage examples.
"""

from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple
import click

from agent_token_receipt import __version__
from agent_token_receipt.installer import InstallPlan, UniversalInstaller
from agent_token_receipt.mcp_server import LocalMCPServer
from collector.antigravity import AntigravityUsageCollector
from collector.base import SessionDescriptor
from collector.registry import CollectorRegistry
from core.aggregator import UsageAggregator
from generator.pdf import ReceiptPDFGenerator
from pricing.calculator import CostCalculator


def _format_dt(dt: Optional[datetime]) -> str:
    """Formats a datetime cleanly for terminal display."""
    if not dt:
        return "N/A"
    tz = getattr(dt.tzinfo, "zone", str(dt.tzinfo)) if dt.tzinfo else "UTC"
    return dt.strftime(f"%Y-%m-%d %H:%M:%S {tz}")


@click.group(invoke_without_command=True)
@click.version_option(version=__version__, prog_name="agent-token-receipt")
@click.pass_context
def cli(ctx: click.Context):
    """AGENT TOKEN RECEIPT — Every token has a receipt.

    A local-first, open-source tool that collects genuine AI coding-agent usage
    from local session logs and generates authentic 80mm thermal-printer-style PDF receipts.

    \b
    Examples:
      agent-token-receipt install
      agent-token-receipt agents
      agent-token-receipt doctor
      agent-token-receipt sessions
      agent-token-receipt generate
      agent-token-receipt generate --workspace . --all-agents --non-interactive
      agent-token-receipt generate --session 99d16623-30c3-4cc5-a071-6c3e3c47ac15
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


def _is_safe_session_arg(session: str) -> bool:
    """Validate that a user-supplied session ID/prefix does not contain path traversal."""
    return bool(session) and session not in (".", "..") and "/" not in session and "\\" not in session and ".." not in session


def _discover_sessions_with_fallback(
    collector: AntigravityUsageCollector,
    workspace: Optional[str] = None,
    all_workspaces: bool = False,
) -> List[SessionDescriptor]:
    """Discover sessions for the requested workspace, falling back to all discovered sessions."""
    ws_filter = None
    if workspace:
        ws_filter = workspace
    elif not all_workspaces:
        ws_filter = str(Path.cwd())

    sessions = collector.discover_sessions(workspace_path=ws_filter)
    if not sessions and ws_filter:
        sessions = collector.discover_sessions()
    return sessions


@cli.command("sessions")
@click.option("--workspace", "-w", default=None, help="Filter sessions by workspace directory path.")
@click.option("--all-workspaces", "-a", is_flag=True, default=False, help="List sessions across all workspaces.")
@click.option("--agent", "agents", multiple=True, help="Filter by specific agent key (e.g. claude_code, codex, antigravity, gemini_cli).")
@click.option("--all-agents", is_flag=True, default=False, help="List sessions across all supported local coding agents.")
def sessions_cmd(
    workspace: Optional[str],
    all_workspaces: bool,
    agents: Tuple[str, ...],
    all_agents: bool,
):
    """List discovered coding-agent sessions."""
    if agents or all_agents:
        try:
            registry = CollectorRegistry()
            ws_filter = None if all_workspaces else (workspace or str(Path.cwd()))
            agent_list = list(agents) if agents else None
            discovered = registry.discover_all_sessions(
                workspace_path=ws_filter,
                agents=agent_list,
            )
            if not discovered and ws_filter and not workspace:
                discovered = registry.discover_all_sessions(agents=agent_list)
        except (OSError, ValueError) as exc:
            click.echo(f"[-] Error reading agent sessions: {exc}")
            raise SystemExit(1)

        if not discovered:
            click.echo("[-] No local sessions matched across selected agents.")
            return

        click.echo("\nAGENT TOKEN RECEIPT — MULTI-AGENT SESSIONS")
        click.echo("Every token has a receipt.\n")
        click.echo(f"Found {len(discovered)} session(s):")
        click.echo("-" * 78)
        for idx, (_, s) in enumerate(discovered, start=1):
            title = s.title or "Untitled Session"
            last_act = _format_dt(s.last_active_time)
            steps_str = f"{s.turn_count} turns" if s.turn_count is not None else "Metadata only"
            click.echo(f"[{idx}] [{s.agent}] {title}")
            click.echo(f"    Session ID:  {s.session_id}")
            click.echo(f"    Activity:    {steps_str} (Last active: {last_act})")
            if s.workspace_path:
                click.echo(f"    Workspace:   {s.workspace_path}")
            click.echo("")
        click.echo("-" * 78)
        click.echo("Run 'agent-token-receipt generate --workspace . --all-agents --non-interactive' for a unified workspace receipt.\n")
        return

    collector = AntigravityUsageCollector()

    if not collector.is_available():
        click.echo("[-] Antigravity local environment not detected.")
        click.echo("    Ensure Google Antigravity is installed and local records exist at ~/.gemini/antigravity.")
        return

    try:
        sessions = _discover_sessions_with_fallback(
            collector, workspace=workspace, all_workspaces=all_workspaces
        )
    except OSError as e:
        click.echo(f"[-] Error reading Antigravity session records: {e}")
        raise SystemExit(1)

    if not sessions:
        click.echo("[-] No Antigravity sessions found in local records.")
        return

    click.echo("\nAGENT TOKEN RECEIPT — SESSIONS")
    click.echo("Every token has a receipt.\n")
    click.echo(f"Found {len(sessions)} session(s):")
    click.echo("-" * 78)

    for idx, s in enumerate(sessions, start=1):
        title = s.title or "Untitled Session"
        last_act = _format_dt(s.last_active_time)
        steps_str = f"{s.turn_count} recorded steps" if s.turn_count is not None else "Steps unrecorded"

        click.echo(f"[{idx}] {title}")
        click.echo(f"    Session ID:  {s.session_id}")
        click.echo(f"    Activity:    {steps_str} (Last active: {last_act})")
        if s.workspace_path:
            click.echo(f"    Workspace:   {s.workspace_path}")
        click.echo("")

    click.echo("-" * 78)
    click.echo("Run 'agent-token-receipt generate' to create a receipt.\n")


def _print_receipt_banner(pdf_path: Path, receipt) -> None:
    """Display consistent receipt generation summary for single or multi-agent output."""
    cost_str = (
        f"${receipt.estimated_api_cost_usd:.4f} USD"
        if receipt.estimated_api_cost_usd is not None
        else "UNAVAILABLE"
    )
    cache_str = (
        f"{receipt.total_cache_read_tokens:,}"
        if receipt.total_cache_read_tokens is not None
        else "UNAVAILABLE"
    )
    active_agents = sorted(
        {s.agent for s in receipt.model_summaries if s.agent}
        | {u.get("agent") for u in (getattr(receipt, "unavailable_agents", []) or []) if u.get("agent")}
    )
    agents_str = ", ".join(active_agents) if active_agents else "Google Antigravity"

    click.echo("\n" + "=" * 62)
    click.echo("SUCCESS!")
    click.echo("Your thermal receipt has been generated:")
    click.echo(f"  File: {pdf_path.name}")
    click.echo(f"  Path: {pdf_path.resolve()}")
    click.echo("-" * 62)
    click.echo(f"  Session Title:         {receipt.metadata.session_title}")
    click.echo(f"  Active Agents:         {agents_str}")
    click.echo(f"  Total Turns:           {receipt.total_turns:,}")
    click.echo(f"  Input + Output Tokens: {receipt.total_tokens:,}")
    click.echo(f"  Total Cache-Read:      {cache_str}")
    click.echo(f"  Estimated API Total:   {cost_str} ({receipt.pricing_status.upper()})")
    click.echo("  Actual Billed Amount:  None (Unbilled locally)")
    for s in receipt.model_summaries:
        sub_cost = f"${s.estimated_api_cost_usd:.4f}" if s.estimated_api_cost_usd is not None else "UNAVAILABLE"
        click.echo(
            f"    - [{s.agent}] {s.model_display_name}: "
            f"in={s.input_tokens:,}, out={s.output_tokens:,}, est={sub_cost} ({s.pricing_status})"
        )
    for u in getattr(receipt, "unavailable_agents", []) or []:
        click.echo(
            f"    - [{u.get('agent', 'Unknown')}] Model={u.get('model', 'Unavailable')}, "
            f"Input={u.get('input_tokens', 'Unavailable')}, "
            f"Output={u.get('output_tokens', 'Unavailable')} ({u.get('reason', 'Unavailable')})"
        )
    click.echo("=" * 62 + "\n")


@cli.command("generate")
@click.option("--session", "-s", default=None, help="Session ID or ID prefix to generate receipt for.")
@click.option("--output", "-o", default="./receipts", help="Output directory for generated PDF receipts.")
@click.option("--workspace", "-w", default=None, help="Workspace path to collect usage for across supported agents.")
@click.option("--agent", "agents", multiple=True, help="Target specific agent(s) (antigravity, claude_code, codex, gemini_cli, cursor, windsurf).")
@click.option("--all-agents", is_flag=True, default=False, help="Collect and merge usage across all detected local agents.")
@click.option("--interactive/--non-interactive", default=True, help="Prompt interactively if --session is omitted.")
def generate_cmd(
    session: Optional[str],
    output: str,
    workspace: Optional[str],
    agents: Tuple[str, ...],
    all_agents: bool,
    interactive: bool,
):
    """Generate a thermal PDF receipt for one session or a multi-agent workspace."""
    if session is not None and not _is_safe_session_arg(session):
        click.echo(f"[-] Error: Invalid session identifier '{session}'.")
        raise SystemExit(1)

    if agents or all_agents or workspace is not None:
        ws_path = str(Path(workspace).resolve()) if workspace is not None else str(Path.cwd().resolve())
        agent_list = list(agents) if agents else None
        try:
            registry = CollectorRegistry()
            coll_res = registry.collect_workspace_usage(
                workspace_path=ws_path if (workspace is not None or (all_agents and session is None)) else None,
                agents=agent_list,
                session_id=session,
            )
        except (OSError, ValueError) as exc:
            click.echo(f"[-] Error collecting agent usage: {exc}")
            raise SystemExit(1)

        # Ensure explicitly requested unavailable agents report cleanly even if their config dir is absent
        if agent_list:
            for req in agent_list:
                c = registry.get(req)
                if c is not None and not getattr(c, "supports_token_telemetry", True):
                    already = {u.get("agent") for u in coll_res.unavailable_agents}
                    if c.agent_name not in already:
                        coll_res.unavailable_agents.append(
                            {
                                "agent": c.agent_name,
                                "model": "Unavailable",
                                "input_tokens": "Unavailable",
                                "output_tokens": "Unavailable",
                                "reason": getattr(
                                    c,
                                    "telemetry_unavailable_reason",
                                    "Local token telemetry unavailable.",
                                ),
                            }
                        )

        if not coll_res.records and not coll_res.unavailable_agents:
            click.echo(
                f"[-] No local agent usage records found for workspace '{ws_path}'."
            )
            click.echo(
                "    Run 'agent-token-receipt sessions --all-agents --all-workspaces' to list available sessions."
            )
            raise SystemExit(1)

        ws_label = Path(ws_path).name or "workspace"
        target_sid = session or f"workspace-{ws_label}"
        target_title = (
            f"Session {session[:12]}"
            if session
            else f"Workspace Billing ({ws_label})"
        )

        aggregator = UsageAggregator(CostCalculator())
        receipt = aggregator.build_receipt(
            records=coll_res.records,
            session_id=target_sid,
            session_title=target_title,
            unavailable_agents=coll_res.unavailable_agents,
        )
        generator = ReceiptPDFGenerator(output_dir=Path(output))
        try:
            pdf_path = generator.generate(receipt)
        except Exception as exc:
            click.echo(f"[-] Error: Failed to generate PDF receipt: {exc}")
            raise SystemExit(1)

        _print_receipt_banner(pdf_path, receipt)
        return

    if not session and not interactive:
        click.echo("[-] Error: --session is required when running in non-interactive mode.")
        raise SystemExit(1)

    collector = AntigravityUsageCollector()

    if not collector.is_available():
        click.echo("[-] Error: Antigravity local environment not detected.")
        click.echo("    Ensure Google Antigravity has been run on this machine.")
        raise SystemExit(1)

    target_session_id: Optional[str] = None
    target_title: Optional[str] = None

    if session:
        # Direct session resolution: prefer exact ID match, then unambiguous prefix match
        try:
            cand_sessions = collector.discover_sessions()
        except OSError as e:
            click.echo(f"[-] Error: Failed to read Antigravity sessions: {e}")
            raise SystemExit(1)

        exact = [s for s in cand_sessions if s.session_id.lower() == session.lower()]
        if exact:
            target_session_id = exact[0].session_id
            target_title = exact[0].title
        else:
            matched = [s for s in cand_sessions if s.session_id.lower().startswith(session.lower())]
            if len(matched) > 1:
                click.echo(f"[-] Error: Ambiguous session prefix '{session}' matches {len(matched)} sessions:")
                for m in matched[:5]:
                    click.echo(f"    - {m.session_id} ({m.title or 'Untitled Session'})")
                raise SystemExit(1)
            if len(matched) == 1:
                target_session_id = matched[0].session_id
                target_title = matched[0].title
            else:
                # Check if brain transcript folder exists directly on disk
                transcript_file = collector.brain_dir / session / ".system_generated" / "logs" / "transcript.jsonl"
                if transcript_file.exists():
                    target_session_id = session
                    target_title = "Antigravity Session"
                else:
                    # Check for prefix match in brain folders
                    prefix_matches = [
                        d.name for d in collector.brain_dir.iterdir()
                        if d.is_dir() and d.name.lower().startswith(session.lower())
                    ] if collector.brain_dir.exists() else []

                    if len(prefix_matches) > 1:
                        click.echo(
                            f"[-] Error: Ambiguous session prefix '{session}' matches {len(prefix_matches)} folders:"
                        )
                        for m in prefix_matches[:5]:
                            click.echo(f"    - {m}")
                        raise SystemExit(1)
                    if len(prefix_matches) == 1:
                        target_session_id = prefix_matches[0]
                        target_title = "Antigravity Session"
                    else:
                        click.echo(f"[-] Error: Session '{session}' was not found in Antigravity records.")
                        raise SystemExit(1)
    else:
        # Interactive selection
        click.echo("\nAGENT TOKEN RECEIPT")
        click.echo("Every token has a receipt.\n")
        click.echo("Discovering Antigravity sessions...")

        try:
            sessions = _discover_sessions_with_fallback(collector)
        except OSError as e:
            click.echo(f"[-] Error: Failed to read Antigravity sessions: {e}")
            raise SystemExit(1)

        if not sessions:
            click.echo("[-] Error: No Antigravity sessions found.")
            raise SystemExit(1)

        # Present available candidates
        click.echo(f"\nFound {len(sessions)} session(s):\n")
        for idx, s in enumerate(sessions, start=1):
            title = s.title or "Untitled Session"
            last_act = _format_dt(s.last_active_time)
            steps = f"{s.turn_count} steps" if s.turn_count is not None else "Recorded"
            click.echo(f"[{idx}] {title}")
            click.echo(f"    ID:          {s.session_id}")
            click.echo(f"    Activity:    {steps} | Last active: {last_act}\n")

        # Prompt user
        choice = click.prompt(f"Select a session [1-{len(sessions)}]", type=str).strip()
        try:
            choice_num = int(choice)
            if choice_num < 1 or choice_num > len(sessions):
                raise ValueError()
        except ValueError:
            click.echo(f"[-] Error: Invalid selection '{choice}'. Please select a number between 1 and {len(sessions)}.")
            raise SystemExit(1)

        selected = sessions[choice_num - 1]
        target_session_id = selected.session_id
        target_title = selected.title
        click.echo(f"\nSelected: {target_title or target_session_id}")

    # Collect usage records
    click.echo("Collecting session usage records...")
    try:
        records = collector.collect_records(target_session_id)
    except OSError as e:
        click.echo(f"[-] Error: Failed to read transcript for session '{target_session_id}': {e}")
        raise SystemExit(1)

    if not records:
        click.echo(f"[-] Error: Session '{target_session_id}' contains no generative turns or readable usage records.")
        raise SystemExit(1)

    # Build and price the canonical Receipt
    click.echo(f"Aggregating {len(records)} generative turns...")
    aggregator = UsageAggregator(CostCalculator())
    receipt = aggregator.build_receipt(
        records=records,
        session_id=target_session_id,
        session_title=target_title or "Antigravity Session",
    )

    # Output generation
    click.echo("Generating your receipt...")
    output_dir = Path(output)
    generator = ReceiptPDFGenerator(output_dir=output_dir)

    try:
        pdf_path = generator.generate(receipt)
    except Exception as e:
        click.echo(f"[-] Error: Failed to generate PDF receipt: {e}")
        raise SystemExit(1)

    # Success Banner
    _print_receipt_banner(pdf_path, receipt)


@cli.command("install")
@click.option(
    "--scope",
    type=click.Choice(["auto", "global", "project", "both"], case_sensitive=False),
    default="auto",
    help="Target configuration scope (default: auto).",
)
@click.option("--workspace", "-w", default=".", help="Workspace directory for project-scoped installation.")
@click.option("--agent", "agents", multiple=True, help="Restrict installation to specific agent(s).")
@click.option("--yes", "-y", is_flag=True, default=False, help="Approve planned modifications without prompting.")
@click.option("--dry-run", is_flag=True, default=False, help="Preview detected agents and file paths without modifying anything.")
@click.option("--force", is_flag=True, default=False, help="Back up and overwrite non-managed conflicting files.")
def install_cmd(
    scope: str,
    workspace: str,
    agents: Tuple[str, ...],
    yes: bool,
    dry_run: bool,
    force: bool,
):
    """Detect coding agents and safely install /agent-billing commands or skills."""
    installer = UniversalInstaller()
    ws_path = Path(workspace).resolve()
    try:
        plan = installer.plan_install(
            scope=scope.lower(),
            workspace=ws_path,
            agents=list(agents) if agents else None,
        )
    except ValueError as exc:
        click.echo(f"[-] Error: {exc}")
        raise SystemExit(1)

    click.echo("\nAGENT TOKEN RECEIPT — UNIVERSAL INSTALLER")
    click.echo("Every token has a receipt.\n")

    if not plan.artifacts:
        click.echo("[-] No matching installed coding-agent environments detected.")
        click.echo("    Tip: Pass --agent claude_code (or codex/cursor/windsurf/antigravity/gemini_cli) to target explicitly.")
        return

    click.echo(f"Detected environments ({len(plan.detected_agents)}):")
    for det in plan.detected_agents:
        click.echo(f"  + {det.display_name} [{det.scope}]: {det.reason}")

    click.echo(f"\nPlanned files ({len(plan.artifacts)}):")
    for art in plan.artifacts:
        click.echo(f"  -> [{art.agent_key} / {art.scope}] {art.target_path}")

    for warn in plan.warnings:
        click.echo(f"  ! Note: {warn}")

    def _ask_confirmation(_: InstallPlan) -> bool:
        return click.confirm("\nProceed with writing these billing integration files?", default=False)

    summary = installer.execute_install(
        plan=plan,
        yes=yes,
        dry_run=dry_run,
        force=force,
        confirm_callback=_ask_confirmation,
    )

    if summary.aborted:
        click.echo("\n[-] Installation cancelled by user. No files were modified.")
        return

    click.echo("\nInstallation Results:")
    for act in summary.actions:
        extra = f" (backup: {act.backup_path})" if act.backup_path else ""
        click.echo(f"  [{act.status.upper()}] {act.target_path}: {act.message}{extra}")

    if not dry_run:
        click.echo("\nInvoke '/agent-billing' (or '$agent-billing' in Codex) inside your agent!")


@cli.command("uninstall")
@click.option(
    "--scope",
    type=click.Choice(["all", "global", "project"], case_sensitive=False),
    default="all",
    help="Scope of installed artifacts to remove.",
)
@click.option("--workspace", "-w", default=".", help="Workspace directory for project-scoped removal.")
@click.option("--agent", "agents", multiple=True, help="Restrict removal to specific agent(s).")
@click.option("--yes", "-y", is_flag=True, default=False, help="Proceed without interactive confirmation prompt.")
def uninstall_cmd(
    scope: str,
    workspace: str,
    agents: Tuple[str, ...],
    yes: bool,
):
    """Remove installed Agent Token Receipt commands/skills and restore any backups."""
    installer = UniversalInstaller()
    ws_path = Path(workspace).resolve()

    def _confirm_paths(paths: List[Path]) -> bool:
        click.echo("\nManaged integration files selected for removal/restoration:")
        for p in paths:
            click.echo(f"  - {p}")
        return click.confirm("\nProceed with uninstalling these files?", default=False)

    summary = installer.uninstall(
        scope=scope.lower(),
        workspace=ws_path,
        agents=list(agents) if agents else None,
        yes=yes,
        confirm_callback=_confirm_paths,
    )

    if summary.aborted:
        click.echo("[-] Uninstall cancelled by user.")
        return
    if not summary.actions:
        click.echo("[-] No installed Agent Token Receipt integration files found for the selected scope.")
        return

    click.echo("\nUninstall Results:")
    for act in summary.actions:
        click.echo(f"  [{act.status.upper()}] {act.target_path}: {act.message}")


@cli.command("agents")
@click.option("--workspace", "-w", default=".", help="Workspace directory to check for project configs.")
def agents_cmd(workspace: str):
    """List supported coding agents, detection status, command format, and telemetry support."""
    installer = UniversalInstaller()
    collector_registry = CollectorRegistry()
    ws_path = Path(workspace).resolve()
    statuses = installer.detector.detect_all(workspace=ws_path)

    click.echo("\nAGENT TOKEN RECEIPT — SUPPORTED ENVIRONMENTS")
    click.echo("=" * 72)
    for st in statuses:
        integ = st.integration
        coll = collector_registry.get(integ.agent_key)
        detected_scopes = []
        if st.global_detection.detected:
            detected_scopes.append("global")
        if st.project_detection and st.project_detection.detected:
            detected_scopes.append("project")
        detect_label = ", ".join(detected_scopes) if detected_scopes else "not detected"

        if integ.telemetry_supported:
            sess_count = len(coll.discover_sessions()) if coll and coll.is_available() else 0
            telem_label = f"Full local telemetry ({sess_count} session(s) found)"
        else:
            telem_label = "Unavailable locally (server-side metering)"

        slash_note = integ.invocation_syntax
        click.echo(f"{integ.display_name} [{integ.agent_key}]")
        click.echo(f"  Detected:    {detect_label}")
        click.echo(f"  Invoke:      {slash_note}")
        click.echo(f"  Mechanism:   {integ.integration_mechanism}")
        click.echo(f"  Telemetry:   {telem_label}")
        click.echo("")


@cli.command("doctor")
@click.option("--workspace", "-w", default=".", help="Workspace directory to inspect.")
def doctor_cmd(workspace: str):
    """Verify installation health, pricing catalogue, agent commands, and telemetry availability."""
    installer = UniversalInstaller()
    report = installer.doctor(workspace=Path(workspace).resolve())

    click.echo("\nAGENT TOKEN RECEIPT — DOCTOR")
    click.echo("=" * 72)
    click.echo(f"  CLI on PATH:        {report.cli_on_path or 'NO (use python -m agent_token_receipt)'}")
    click.echo(f"  Pricing Catalogue:  {'OK' if report.catalogue_loaded else 'ERROR'} ({report.catalogue_model_count} models)")
    click.echo(f"  Install Manifest:   {report.manifest_path}")

    for issue in report.issues:
        click.echo(f"  [!] Warning: {issue}")

    click.echo("\nAgent Integrations:")
    for ag in report.agents:
        installed_count = len(ag.installed_artifacts)
        missing_count = len(ag.missing_artifacts)
        detect_str = "detected" if (ag.detected_global or ag.detected_project) else "not installed"
        slash_str = ag.invocation_syntax
        if installed_count and missing_count == 0:
            cmd_status = f"installed ({installed_count} file(s), {slash_str})"
        elif installed_count and missing_count:
            cmd_status = f"partial ({installed_count} present, {missing_count} missing)"
        elif ag.detected_global or ag.detected_project:
            cmd_status = f"not installed (run 'agent-token-receipt install --agent {ag.agent_key}')"
        else:
            cmd_status = f"skipped (agent not present; supports {slash_str})"

        click.echo(f"  * {ag.display_name} [{ag.agent_key}] ({detect_str})")
        click.echo(f"      Command:   {cmd_status}")
        click.echo(f"      Telemetry: {ag.telemetry_note}")

    if not report.catalogue_loaded:
        raise SystemExit(1)


@cli.command("mcp")
def mcp_cmd():
    """Start optional stdio JSON-RPC 2.0 MCP server (no external dependencies)."""
    LocalMCPServer().serve_streams()


def main():
    """Main entrypoint for console scripts."""
    cli()


if __name__ == "__main__":
    main()

