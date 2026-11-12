# Changelog

All notable changes to **Agent Token Receipt** are documented in this file.

## [0.2.0] - 2026-11-12 (Public Beta)

### Added
- **Universal Multi-Agent Installer (`agent_token_receipt/installer/`)**:
  - Environment detection and safe command/skill installation across **Google Antigravity**, **Claude Code**, **OpenAI Codex CLI**, **Gemini CLI**, **Cursor**, and **Windsurf** (global and project scopes).
  - Explicit interactive confirmation before modifying config directories (`--yes` for non-interactive runs, `--dry-run` preview).
  - Automatic `.atr.bak.<timestamp>` backups under `--force`, conflict preservation by default, shared `.agents/skills` reference counting in `install_manifest.json`, and safe `uninstall`.
  - `agent-token-receipt doctor` now warns if installed wrapper files reference a different Python interpreter than the active CLI environment.
- **Multi-Agent Usage Collectors (`collector/`)**:
  - Added read-only [`ClaudeCodeUsageCollector`](collector/claude_code.py) with `message.id` streaming deduplication and subagent aggregation.
  - Added read-only [`CodexUsageCollector`](collector/codex.py) with cached-input subtraction (`input_tokens - cached_input_tokens`) and duplicate snapshot filtering.
  - Added read-only [`GeminiCLIUsageCollector`](collector/gemini_cli.py) with delta JSONL/legacy JSON parsing and `tokens.total` invariant disambiguation.
  - Added honest server-side capability detectors [`CursorUsageCollector`](collector/cursor.py) and [`WindsurfUsageCollector`](collector/windsurf.py).
  - Added [`CollectorRegistry`](collector/registry.py) for workspace-scoped unified multi-agent billing.
- **CLI Commands & Options (`cli/main.py`)**:
  - Added `install`, `uninstall`, `agents`, `doctor`, and optional `mcp`.
  - Extended `sessions` and `generate` with `--workspace`, `--agent`, and `--all-agents` while maintaining full backward compatibility.
- **Multi-Agent & Unavailable Platform Receipts**:
  - Extended `Receipt` (`core/models.py`) and `ReceiptPDFGenerator` (`generator/pdf.py`) to disclose unavailable server-side platforms cleanly under `[ UNAVAILABLE TELEMETRY ]`.
- **Pricing Catalogue (`pricing/catalogue.json`)**:
  - Expanded verified/documented entries to 15 models (`claude-sonnet-4-6`, `claude-haiku-4-5`, `gpt-5.4`, `gpt-5`, `gpt-4.1`, `o3`).
- **Optional Local MCP Server (`agent_token_receipt/mcp_server.py`)**:
  - Added zero-dependency stdio JSON-RPC 2.0 server exposing `list_agent_sessions`, `get_agent_usage`, and `generate_agent_receipt`.
- **Public Beta & Contributor Documentation**:
  - Added [`BETA_TESTING_GUIDE.md`](BETA_TESTING_GUIDE.md), [`BETA_TEST_CHECKLIST.md`](BETA_TEST_CHECKLIST.md), [`BETA_FEEDBACK_TEMPLATE.md`](BETA_FEEDBACK_TEMPLATE.md), [`RELEASE_NOTES_v0.2.0.md`](RELEASE_NOTES_v0.2.0.md), platform support caveats in [`README.md`](README.md), and extension guides in [`CONTRIBUTING.md`](CONTRIBUTING.md).

### Fixed
- **Virtual Environment Wrapper Fallback (`agent_token_receipt/installer/templates.py`)**: Generated `/agent-billing` and `$agent-billing` wrappers invoke the exact `sys.executable` captured at install time before falling back to `python3` / `python`.
- **Same-Model Multi-Agent Cost Accounting (`pricing/calculator.py`)**: `CostCalculator.calculate_receipt_cost` filters usage records by `agent` and `provider` in addition to `model_display_name` and `model_id`, preventing turn-count and cost duplication across collaborating agents.
- **Cross-Workspace `--session` Prefix Resolution (`cli/main.py`)**: `--all-agents --session <prefix>` without `--workspace` no longer restricts discovery to `Path.cwd()`.
- **Quiet Missing-Session Handling (`collector/antigravity.py`)**: Missing local Antigravity transcript paths no longer emit noisy `WARNING` output on `collect_records`.
- **POSIX URI Normalization (`collector/antigravity.py`)**: `_normalize_path()` preserves leading slashes for POSIX `file:///` workspace URIs.

## [0.1.0] - 2026-11-11

### Added
- Canonical Pydantic v2 token usage & receipt models (`core/models.py`, `core/normalizer.py`, `core/aggregator.py`).
- Read-only Google Antigravity SQLite & JSONL collector (`collector/antigravity.py`).
- Decimal-precision pricing engine & versioned catalogue (`pricing/calculator.py`, `pricing/catalogue.json`).
- 80mm monochrome thermal receipt PDF generator with auto-pagination and collision-safe filenames (`generator/pdf.py`).
- Click CLI (`sessions`, `generate`), `pyproject.toml`, `MANIFEST.in`, and isolated unit test suite.
