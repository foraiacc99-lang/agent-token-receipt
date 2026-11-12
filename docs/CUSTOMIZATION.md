# Customization & Extension Guide

Agent Token Receipt is modular so you can add new collectors, integrate additional coding environments, update pricing rates, or tweak local commands while keeping a single canonical accounting engine.

For core principles and PR rules, read [../CONTRIBUTING.md](../CONTRIBUTING.md).

---

## Architecture Pipeline

```text
  [Session Logs / Read-Only SQLite]
                 |
                 v
     collector/ (BaseUsageCollector)   --> CanonicalUsageRecord[]
                 |
                 v
     core/ (UsageAggregator)           --> ModelUsageSummary[] + Receipt
                 |
                 v
     pricing/ (CostCalculator + catalogue.json) --> Decimal USD estimates
                 |
                 v
     generator/ (ReceiptPDFGenerator)  --> 80mm monochrome thermal PDF
```

---

## 1. Create a Custom Collector (`collector/`)

1. Subclass `BaseUsageCollector` from `collector/base.py`:
   - Properties: `agent_name`, `provider_name`
   - Methods: `is_available()`, `discover_sessions(workspace_path=None) -> List[SessionDescriptor]`, `collect_records(session_id) -> List[CanonicalUsageRecord]`
2. Enforce read-only rules:
   - Never modify upstream logs or databases (`sqlite3` URI `?mode=ro`).
   - Accept optional root paths in `__init__` so tests can point to `tempfile.TemporaryDirectory()`.
   - Deduplicate streaming chunks / cumulative snapshots carefully and ensure `input_tokens` does **not** double-count cached tokens.
   - Set `supports_token_telemetry = False` if your target tool meters server-side (see `collector/cursor.py` and `collector/windsurf.py`).
3. Register the collector key and aliases in `CollectorRegistry` and `AGENT_ALIASES` inside `collector/registry.py`.
4. Add unit tests under `tests/`.

---

## 2. Create a Custom Agent Installer Integration (`agent_token_receipt/installer/`)

1. Subclass `BaseAgentIntegration` from `agent_token_receipt/installer/base.py`.
2. Define metadata fields (`agent_key`, `display_name`, `command_name`, `invocation_syntax`, `native_slash_supported`, `integration_mechanism`, `telemetry_supported`, `telemetry_status_note`).
3. Implement `detect_global()`, `detect_project(workspace: Path)`, and `get_artifacts(scope: str, workspace: Optional[Path] = None)`.
4. Render instruction files via `agent_token_receipt/installer/templates.py` so wrappers invoke the pinned Python interpreter (`sys.executable` with `python3`/`python` fallback) rather than re-implementing billing calculations.
5. Register the class inside `IntegrationRegistry` (`agent_token_receipt/installer/registry.py`) and add tests in `tests/test_installer.py`.

---

## 3. Customize Skills, Commands, and Workflows Locally

To customize billing behavior for a single project (such as always exporting receipts to `-o ./billing_pdfs`):

1. Install project-scoped files:
   ```bash
   agent-token-receipt install --scope project --workspace .
   ```
2. Edit the generated instruction file in your repository (e.g. `.claude/skills/agent-billing/SKILL.md`, `.codex/skills/agent-billing/SKILL.md`, `.gemini/commands/agent-billing.toml`, `.cursor/commands/agent-billing.md`, or `.windsurf/workflows/agent-billing.md`) to adjust CLI flags.
3. Do not duplicate pricing or aggregation logic inside prompts—always call `agent-token-receipt generate` (or `agent-token-receipt mcp`).
4. Subsequent `agent-token-receipt install` runs preserve your edited files (`SKIPPED`) unless `--force` is passed (which creates `.atr.bak.<timestamp>` backups).

---

## 4. Update or Add Model Pricing (`pricing/catalogue.json`)

Each entry under `"models"` in `pricing/catalogue.json` uses decimal strings in USD or `null` when unavailable:

```json
"example-model-id": {
  "provider": "ProviderName",
  "model_display_name": "Example Model",
  "canonical_model_id": "example-model-id",
  "verification_status": "verified",
  "pricing_type": "flat",
  "input_price_per_million": "1.00",
  "output_price_per_million": "5.00",
  "cache_read_price_per_million": "0.10",
  "cache_write_price_per_million": null,
  "currency": "USD",
  "source_url": "https://example.com/pricing",
  "retrieval_date": "2026-11-12",
  "notes": "Source pricing note."
}
```

Rules:
- Use `"verified"` for published GA rates, `"preview_estimate"` for documented preview/introductory rates, or `"unverified"` with `null` rates when unavailable.
- Never replace unknown prices with `"0"`.
- Verify changes against `tests/test_pricing.py`.

---

## 5. Customize Thermal PDF Receipt Layout (`generator/pdf.py`)

`ReceiptPDFGenerator` formats an 80mm thermal PDF (`Courier` monospace, 42-column alignment, auto-pagination). Keep `UNAVAILABLE` / `Unavailable` / `None (Unbilled locally)` markers intact and verify text rendering with `extract_pdf_texts()` in `tests/test_generator.py`.

