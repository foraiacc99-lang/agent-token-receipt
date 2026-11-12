# Contributing to Agent Token Receipt

Thank you for contributing to **Agent Token Receipt** (*Every token has a receipt*).

For step-by-step extension code examples, see [`docs/CUSTOMIZATION.md`](docs/CUSTOMIZATION.md). Participation is governed by [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

---

## Core Design Principles

1. **Zero Data Fabrication:** Never default missing metrics, cache costs, or unpriced models to `$0.00` or `0`. Unavailable values must stay `None` / `UNAVAILABLE`.
2. **Strict Privacy & Read-Only Collection:** Never extract, log, or export user prompts, code snippets, tool responses, or model thinking text. Open SQLite stores with `?mode=ro` read-only URIs (`uri=True`) and open JSON/JSONL logs strictly read-only.
3. **Offline & Local-First:** Runtime execution must never require internet access, cloud accounts, API keys, or analytics telemetry.
4. **No Double Counting:** Keep cached token counts strictly separated from uncached `input_tokens`, and enforce `total_tokens == input_tokens + output_tokens`.
5. **Single Canonical Accounting Engine:** Agent skills, slash commands, workflows, and custom wrappers must invoke `agent-token-receipt` rather than duplicating parsing, aggregation, or pricing logic.

---

## Architecture Overview

```text
collector/                 -> Read-only agent parsers (BaseUsageCollector -> CanonicalUsageRecord)
core/                      -> Pydantic v2 schemas, UsageNormalizer, and UsageAggregator
pricing/                   -> Versioned pricing catalogue (catalogue.json) & Decimal CostCalculator
generator/                 -> Monochrome 80mm thermal PDF renderer (ReceiptPDFGenerator)
cli/                       -> Click CLI commands (sessions, generate, install, uninstall, agents, doctor, mcp)
agent_token_receipt/
  installer/               -> Detection, dry-run planning, backup/manifest install/uninstall, doctor
  mcp_server.py            -> Optional zero-dependency stdio JSON-RPC 2.0 server
tests/                     -> Offline unit and integration tests using isolated temp directories
```

Data flows through one shared pipeline:
1. A collector (`BaseUsageCollector`) reads local session files and emits `CanonicalUsageRecord` objects.
2. `UsageAggregator` validates and groups records by `(provider, agent, model_display_name, model_id)`.
3. `CostCalculator` prices each model summary (and per-turn records when context tiering applies) using `pricing/catalogue.json` and Python `Decimal`.
4. `ReceiptPDFGenerator` renders the `Receipt` model to an 80mm PDF with explicit verification badges and `Actual Billed Amount: None (Unbilled locally)`.

---

## Local Development Setup

```bash
git clone https://github.com/foraiacc99-lang/agent-token-receipt.git
cd agent-token-receipt
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# Windows CMD:        .venv\Scripts\activate.bat
# macOS / Linux:      source .venv/bin/activate
python -m pip install -e .
```

If you want to contribute without replacing your global CLI binary, keep edits inside `.venv` and invoke `python -m agent_token_receipt ...` or activate `.venv` before running `agent-token-receipt`.

---

## How to Extend Agent Token Receipt

### 1. Add a New Usage Collector (`collector/`)

Collectors read local traces without mutating source files:

1. Create `collector/<agent>.py` subclassing `BaseUsageCollector` (`collector/base.py`):
   - Implement `agent_name`, `provider_name`, `is_available()`, `discover_sessions(workspace_path=None) -> List[SessionDescriptor]`, and `collect_records(session_id) -> List[CanonicalUsageRecord]`.
   - Accept injectable directory path arguments in `__init__` (defaulting to standard home paths) so tests run in isolated temp directories.
   - Deduplicate streamed assistant chunks / cumulative snapshots carefully and subtract cached tokens from `input_tokens` if the upstream format counts cached reads inside total input tokens.
   - Set `supports_token_telemetry = False` and `telemetry_unavailable_reason = "..."` if an environment meters usage strictly server-side (follow `collector/cursor.py` and `collector/windsurf.py`). Never fabricate token counts.
2. Register the collector in `CollectorRegistry` and `AGENT_ALIASES` inside `collector/registry.py`.
3. Add isolated fixture tests in `tests/` verifying session discovery, deduplication, workspace filtering, and error resilience.

### 2. Add a New Agent Installer Integration (`agent_token_receipt/installer/`)

To register `/agent-billing` (or platform-equivalent commands) automatically via `agent-token-receipt install`:

1. Create `agent_token_receipt/installer/integrations/<agent>.py` subclassing `BaseAgentIntegration` (`agent_token_receipt/installer/base.py`).
2. Define metadata attributes (`agent_key`, `display_name`, `invocation_syntax`, `native_slash_supported`, `integration_mechanism`, `telemetry_supported`, `telemetry_status_note`).
3. Implement `detect_global() -> DetectionResult`, `detect_project(workspace: Path) -> DetectionResult`, and `get_artifacts(scope: str, workspace: Optional[Path] = None) -> List[InstallArtifact]`.
4. Render instruction templates through helpers in `agent_token_receipt/installer/templates.py` so wrappers invoke the pinned `sys.executable` (with `python3`/`python` fallback) instead of duplicating accounting logic.
5. Register the integration class in `agent_token_receipt/installer/registry.py`.
6. Add installer/uninstaller round-trip tests in `tests/test_installer.py`.

### 3. Customize Skills, Commands, & Workflows Locally

You can customize prompt text, output folder defaults (e.g., adding `-o ./docs/receipts`), or workflow shortcuts without touching core accounting:

- **Project-level customization:** Install scoped files into a single repository via:
  ```bash
  agent-token-receipt install --scope project --workspace .
  ```
  Then edit the generated project-local file (such as `.claude/skills/agent-billing/SKILL.md`, `.codex/skills/agent-billing/SKILL.md`, `.gemini/commands/agent-billing.toml`, `.cursor/commands/agent-billing.md`, or `.windsurf/workflows/agent-billing.md`) so it still calls `python -m agent_token_receipt generate ...` (or `agent-token-receipt mcp`).
- **Protecting custom files:** By default, `agent-token-receipt install` skips existing modified files rather than overwriting them. Only `--force` overwrites customized files (creating `.atr.bak.<timestamp>` backups restored on `uninstall`).

### 4. Add or Update Model Pricing Entries (`pricing/catalogue.json`)

1. Open `pricing/catalogue.json` and add or update an entry under `"models"` keyed by canonical model ID:
   - `"provider"`, `"model_display_name"`, `"canonical_model_id"`
   - `"verification_status"`: use `"verified"` (published GA API rates), `"preview_estimate"` (documented introductory/preview rates), or `"unverified"` (`null` rates when no official rate exists)
   - `"pricing_type"`: `"flat"` (or `"tiered"` with threshold rules following existing entries)
   - `"input_price_per_million"`, `"output_price_per_million"`, `"cache_read_price_per_million"`, `"cache_write_price_per_million"`: decimal strings in USD, or `null` if unpublished/ambiguous (never substitute `"0"` for unknown rates)
   - `"currency": "USD"`, `"source_url"`, `"retrieval_date"`, and `"notes"`
2. Add or update unit tests in `tests/test_pricing.py` asserting exact `Decimal` totals and pricing statuses (`verified`, `preview_estimate`, `partially_priced`, or `unknown_price`).

### 5. Improve PDF Receipt Formatting (`generator/pdf.py`)

- Receipts target **80mm** thermal width using Courier monospace typography (~42 columns per line).
- Keep all unavailable values rendered honestly as `UNAVAILABLE`, `Unavailable`, or `None (Unbilled locally)`.
- Wrap text safely and verify multi-page pagination and text output using `extract_pdf_texts()` in `tests/test_generator.py`.

---

## Writing Tests & Pull Request Checklist

All unit and integration tests must run offline using isolated temporary fixtures (`tempfile.TemporaryDirectory`) and never rely on host session databases or network access:

```bash
python -m unittest discover -s tests -v
```

Before opening a pull request:
1. Run the full test suite (`python -m unittest discover -s tests -v`) and verify zero failures.
2. Add unit tests under `tests/` covering new collectors, installer targets, pricing entries, or formatting changes.
3. Verify no personal paths, API keys, test PDFs, or session logs are committed or packaged (check `.gitignore` and `MANIFEST.in`).
4. Keep changes focused on the existing local-first architecture—avoid adding cloud dependencies, external telemetry, or duplicate calculation logic.
