# Agent Token Receipt — Beta Test Checklist (`v0.2.0`)

Use this checklist to validate **Agent Token Receipt** across environments and distinguish expected unsupported telemetry from real defects.

---

## 1. Installation & Platform Matrix

- [ ] **Fresh installation:** Clean virtual environment (`python -m venv .venv`) from `.whl` and from source (`pip install .`)
- [ ] **Existing Python environment:** Upgrade or install into a pre-existing Python environment with other packages installed
- [ ] **Windows installation:** `agent-token-receipt --version`, `agent-receipt --version`, `python -m agent_token_receipt --version`
- [ ] **macOS installation:** Wheel/source install, `doctor`, and receipt generation on macOS
- [ ] **Linux installation:** Wheel/source install, `doctor`, and receipt generation on Linux

---

## 2. Agent Integrations

Verify both installer file placement **and** real command invocation inside each accessible environment:

- [ ] **Google Antigravity:** Global skill `~/.gemini/config/skills/agent-billing/SKILL.md` (or project `.agents/skills/agent-billing/SKILL.md`) installed; `/agent-billing` invokes CLI and reports verified totals
- [ ] **Claude Code:** Global skill `~/.claude/skills/agent-billing/SKILL.md` (or project `.claude/skills/agent-billing/SKILL.md`) installed; `/agent-billing` invokes CLI and reports verified totals
- [ ] **OpenAI Codex CLI:** Global skill `~/.codex/skills/agent-billing/SKILL.md` (or project `.agents/skills/agent-billing/SKILL.md`) installed; `$agent-billing` (or `/skills`) invokes CLI and reports verified totals
- [ ] **Gemini CLI:** Command `~/.gemini/commands/agent-billing.toml` and skill `~/.gemini/skills/agent-billing/SKILL.md` installed; `/agent-billing` invokes CLI and reports verified totals
- [ ] **Cursor:** Command `~/.cursor/commands/agent-billing.md` and skill `~/.cursor/skills/agent-billing/SKILL.md` installed; `/agent-billing` runs CLI and honestly reports local token telemetry as `Unavailable`
- [ ] **Windsurf:** Workflow `~/.codeium/windsurf/global_workflows/agent-billing.md` and skill `~/.codeium/windsurf/skills/agent-billing/SKILL.md` installed; `/agent-billing` runs CLI and honestly reports local token telemetry as `Unavailable`

---

## 3. Core Functionality

- [ ] **Agent detection:** `agent-token-receipt agents` and `doctor` accurately detect present agents and skip absent ones (e.g., `~/.gemini/antigravity` does not falsely detect Gemini CLI)
- [ ] **Session detection:** `sessions --all-agents --all-workspaces` lists sessions with accurate IDs, turn counts, timestamps, and workspaces
- [ ] **Model identification:** Canonical model IDs and display names map accurately; unknown/preview models preserve raw IDs without guessing
- [ ] **Input token collection:** Uncached `input_tokens` extracted accurately (Codex subtracts `cached_input_tokens`; Gemini CLI disambiguates via `tokens.total`; Claude Code deduplicates streaming `message.id` snapshots)
- [ ] **Output token collection:** `output_tokens` match recorded assistant usage without duplication
- [ ] **Cache-read token collection:** `cache_read_tokens` tracked separately and **never** added into `Input + Output Tokens`
- [ ] **Pricing calculation:** Exact `Decimal` calculation; correct pricing statuses (`verified`, `preview_estimate`, `partially_priced`, `unavailable`); `Actual Billed Amount: None (Unbilled locally)`
- [ ] **Multi-agent aggregation:** `generate --workspace . --all-agents --non-interactive` combines multiple agents/models into a single receipt without overwriting or duplicating turns
- [ ] **PDF receipt generation:** Valid 80mm thermal PDF created with clean alignment, pagination (`Page X of Y`), collision-safe filenames (`_1.pdf`), and `[ UNAVAILABLE TELEMETRY ]` section when applicable

---

## 4. Installation Management

- [ ] **Dry-run installation:** `agent-token-receipt install --dry-run` previews detected agents and target paths with zero filesystem writes
- [ ] **Normal installation:** `agent-token-receipt install` asks explicit confirmation before writing, creates artifacts, and updates `~/.agent-token-receipt/install_manifest.json`
- [ ] **Reinstallation:** Re-running `agent-token-receipt install --yes` is strictly idempotent (`[UNCHANGED]`)
- [ ] **Uninstallation:** `agent-token-receipt uninstall` removes managed files cleanly, removes empty `agent-billing/` directories, and leaves parent agent config folders intact
- [ ] **Existing configuration preservation:** Unmanaged user files are skipped by default (`[SKIPPED_CONFLICT]`), backed up to `.atr.bak.<timestamp>` only under `--force`, and restored cleanly on `uninstall`

---

## 5. Unsupported Telemetry vs. Actual Bugs

Before filing a bug, check this table to distinguish **intentional zero-fabrication behavior** from **real bugs**:

| Observation | Status | Explanation |
| :--- | :--- | :--- |
| **Cursor** or **Windsurf** shows `Unavailable` for model/input/output tokens | **Expected (Unsupported Telemetry)** | Both platforms meter usage server-side and do not persist verifiable per-turn token counts locally. |
| **Preview / internal models** (e.g., `gpt-6-luna`, `gemini-3.8-pro`) show `UNAVAILABLE` cost | **Expected (No Published Rate)** | No official public pay-as-you-go API rates exist for these model IDs. |
| **Anthropic `cache_write` cost** shows `UNAVAILABLE` (`PARTIALLY_PRICED`) | **Expected (TTL Ambiguity)** | Canonical `cache_write_tokens` does not separate 5-minute vs. 1-hour ephemeral write tiers. |
| **`Actual Billed Amount`** shows `None (Unbilled locally)` | **Expected (Accounting Integrity)** | Receipts estimate API-equivalent value; local IDE/CLI sessions often run on subscriptions or credits. |
| **`agent-token-receipt` fails inside `.venv`**, crashes on valid logs, miscounts tokens, duplicates turns, overwrites user configs without `--force`, or fails to uninstall | **Actual Bug** | Report using `BETA_FEEDBACK_TEMPLATE.md`. |

