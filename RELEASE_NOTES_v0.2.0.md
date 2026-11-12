# Agent Token Receipt v0.2.0 — Public Beta

> **Release Status:** **PUBLIC BETA (`v0.2.0`)** — Tested end-to-end on Windows 11 (`Python 3.11` & `3.13`). Not yet a production `v1.0.0` release; community beta testing is actively open for Linux, macOS, and additional coding-agent setups.

**Tagline:** *Every token has a receipt.*  
**Release Date:** November 12, 2026  
**License:** MIT (`Copyright (c) 2026 Swaraj Talekar`)  
**Python Requirement:** Python 3.10+

---

## Highlights

**v0.2.0** is the first public beta release of **Agent Token Receipt**, expanding read-only local token auditing and monochrome 80mm thermal PDF receipts from Google Antigravity into a multi-agent CLI, safe command installer, and optional local stdio MCP server.

### What's New in `v0.2.0`
- **Universal Multi-Agent Installer (`install` / `uninstall` / `agents` / `doctor`):**
  - Probes global and workspace configs, previews exact planned file writes (`--dry-run`), requires explicit confirmation (`--yes` for scripts), creates `.atr.bak.<timestamp>` backups on `--force`, ref-counts shared `.agents/skills` files in `install_manifest.json`, and pins the install-time `sys.executable` interpreter with a `python3`/`python` fallback.
- **Multi-Agent Local Collectors (`collector/`):**
  - **Google Antigravity** (`~/.gemini/antigravity`) — *Live-verified on Windows 11*
  - **OpenAI Codex CLI** (`~/.codex/sessions`) — *Live-verified on Windows 11 via `$agent-billing`; uncached input computed as `input_tokens - cached_input_tokens`*
  - **Claude Code** (`~/.claude/projects`) — *Collector, deduplication (`message.id` + subagents), CLI, & installer verified on Windows 11; live interactive LLM run unverified locally due to expired OAuth*
  - **Gemini CLI** (`~/.gemini/tmp/*/chats`) — *Verified via isolated unit tests & synthetic fixtures only (`gemini` binary absent on test host)*
  - **Cursor & Windsurf:** Installs native `/agent-billing` commands/workflows and discloses local token metrics honestly as `Unavailable` *(Cursor CLI/installer & PDF disclosure verified on Windows 11; interactive Cursor IDE UI and Windsurf live host testing remain unverified)*
- **Precision Pricing Catalogue (`15` Models):**
  - Exact Python `Decimal` math and per-turn context tiering across 15 documented/verified models (including `claude-sonnet-4-6`, `claude-haiku-4-5`, `gpt-5.4`, `gpt-5`, `gpt-4.1`, and `o3`), plus multi-agent same-model deduplication so shared models never double-count turns or costs.
- **Optional Local Stdio MCP Server (`agent-token-receipt mcp`):**
  - Zero-dependency JSON-RPC 2.0 server exposing `list_agent_sessions`, `get_agent_usage`, and `generate_agent_receipt`.

---

## Installation Instructions

> [!NOTE]
> Cloning the repository or installing the Python package does **not** automatically register `/agent-billing` inside your IDE or CLI. You must run `agent-token-receipt install` afterwards (and restart an IDE or terminal if it caches slash commands/skills on startup).

### Option A: From Source in a Virtual Environment (Recommended)

```bash
git clone https://github.com/foraiacc99-lang/agent-token-receipt.git
cd agent-token-receipt
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# Windows CMD:        .venv\Scripts\activate.bat
# macOS / Linux:      source .venv/bin/activate

python -m pip install .
```

### Option B: From GitHub Release Assets (`.whl` or `.tar.gz`)

```bash
python -m venv .venv
# Activate .venv, then install the downloaded wheel:
python -m pip install agent_token_receipt-0.2.0-py3-none-any.whl
```

### Option C: Global User or `pipx` Install

```bash
pipx install agent_token_receipt-0.2.0-py3-none-any.whl
# Or: python -m pip install --user .
```

### Register Commands & Verify

```bash
agent-token-receipt --version
agent-token-receipt install --dry-run
agent-token-receipt install
agent-token-receipt doctor
```

Invoke inside your coding agent via `/agent-billing` (**Google Antigravity**, **Claude Code**, **Gemini CLI**, **Cursor**, **Windsurf**) or **`$agent-billing`** / `/skills` (**OpenAI Codex CLI**), or generate a unified workspace receipt directly from the terminal:

```bash
agent-token-receipt sessions --all-agents --all-workspaces
agent-token-receipt generate --workspace . --all-agents --non-interactive
```

---

## Known Limitations in Public Beta

- **Cross-Platform Verification:** Tested end-to-end on **Windows 11** (`Python 3.11` & `3.13`). Native **Linux** and **macOS** runtime testing are not yet verified and rely on POSIX unit-test mocks until community beta reports arrive. *(Ubuntu/Debian users may need `sudo apt install python3-venv python3-pip` before creating a `.venv`.)*
- **Cursor & Windsurf Telemetry:** Token counts are metered server-side and are not recorded locally; receipts render those platforms under `[ UNAVAILABLE TELEMETRY ]`.
- **OpenAI Codex Syntax:** Uses `$agent-billing` or `/skills` because Codex deprecated custom `/prompts:*` slash commands.
- **Anthropic Cache-Write TTL Split:** Unsplit cache writes on models like `claude-opus-4-6` remain unpriced (`PARTIALLY_PRICED`) rather than guessing `1.25x` vs `2x` TTL tiers.
- **Estimated API Cost vs. Actual Billing:** Receipts estimate API-equivalent token value alongside `Actual Billed Amount: None (Unbilled locally)`.

---

## Beta Testing & Feedback

Want to help test `v0.2.0` on Linux, macOS, Gemini CLI, Cursor, Windsurf, or Claude Code?
1. Follow [`BETA_TESTING_GUIDE.md`](BETA_TESTING_GUIDE.md) and [`BETA_TEST_CHECKLIST.md`](BETA_TEST_CHECKLIST.md).
2. Submit results using [`BETA_FEEDBACK_TEMPLATE.md`](BETA_FEEDBACK_TEMPLATE.md).
3. **Never share** private prompts, source code, thinking content, API keys, or raw session logs.

---

## Release Assets

- `agent_token_receipt-0.2.0-py3-none-any.whl` — Built Python wheel
- `agent_token_receipt-0.2.0.tar.gz` — Source distribution including offline test suite, user docs (`docs/`), community guidelines, and beta feedback guides

See [`docs/INSTALLATION.md`](docs/INSTALLATION.md), [`docs/USAGE.md`](docs/USAGE.md), and [`docs/SUPPORTED_AGENTS.md`](docs/SUPPORTED_AGENTS.md) for complete documentation.
