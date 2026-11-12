```text
========================================================================
                         AGENT TOKEN RECEIPT
                      Every token has a receipt.
------------------------------------------------------------------------
   Version: v0.2.0 Public Beta   |   License: MIT   |   Python: 3.10+
========================================================================
```

**Agent Token Receipt** is a free, open-source, local-first CLI tool that audits local AI coding-agent sessions and renders monochrome 80mm thermal-style PDF receipts showing genuine token counts and estimated API-equivalent costs.

---

## Documentation

- [Installation Guide](docs/INSTALLATION.md) — Windows, Linux, macOS, and troubleshooting setup
- [Usage Guide](docs/USAGE.md) — IDE commands, terminal CLI flags, receipt fields, and export paths
- [Supported Agents](docs/SUPPORTED_AGENTS.md) — All six integrations, install targets, and verification status
- [Privacy & Security](docs/PRIVACY.md) — Read-only collectors, local storage, and data never collected
- [Customization Guide](docs/CUSTOMIZATION.md) — Collectors, integrations, skills, pricing catalogue, and PDF layout
- [Troubleshooting](docs/TROUBLESHOOTING.md) | [FAQ](docs/FAQ.md) | [Beta Testing Guide](BETA_TESTING_GUIDE.md)

---

## The Problem

Developers switch across multiple AI coding agents—IDE assistants, terminal CLIs, and agentic editors—while token metrics, cached reads, and model pricing remain scattered across incompatible local formats. Agent Token Receipt brings verifiable local usage across collaborating tools together into one auditable receipt.

It reports, strictly from local traces without guessing:
- Coding agent(s) and model identifier(s)
- Uncached input tokens, output tokens, cache-read tokens, and cache-write tokens (when reported)
- Generation turn counts
- Estimated pay-as-you-go API-equivalent cost (`pricing/catalogue.json`) and pricing status
- Actual billed amount (strictly `None (Unbilled locally)` unless a local log genuinely contains billing data)

---

## Key Features

- **Universal Multi-Agent Reporting**: Collects and aggregates workspace sessions across **Google Antigravity**, **Claude Code**, **OpenAI Codex CLI**, and **Gemini CLI**, while detecting **Cursor** and **Windsurf**.
- **Combined 80mm Thermal PDF Receipts**: Renders monochrome Courier monospace receipts with auto-pagination (`Page X of Y`) and collision-safe filenames.
- **Local-First Architecture**: Runs offline with zero cloud accounts, zero mandatory API keys, and zero background daemons.
- **Verified Model Pricing**: Uses Python `Decimal` math, turn-level context tiering, and a versioned 15-model catalogue (`pricing/catalogue.json`). Unpriced or unverified categories remain `UNAVAILABLE`.
- **Cache-Token Accounting**: Keeps `cache_read_tokens` and `cache_write_tokens` separate from `input_tokens` and enforces `total_tokens == input_tokens + output_tokens`.
- **Developer Customization**: Extend cleanly with custom `BaseUsageCollector` parsers, `BaseAgentIntegration` wrappers, project-local skills, and catalogue rates ([docs/CUSTOMIZATION.md](docs/CUSTOMIZATION.md)).
- **Complete CLI & Safe Installer**: Includes `install` (`--dry-run`, `--scope`, `--force`), `uninstall`, `agents`, `doctor`, `sessions`, and `generate`.
- **Optional Stdio MCP Server**: Built-in zero-dependency JSON-RPC 2.0 server (`agent-token-receipt mcp`).
- **Privacy-Focused Collection**: Opens SQLite databases with `?mode=ro` read-only URIs and ignores prompts, source code, thinking text, and credentials.

---

## Supported Agents

| Coding Agent | Invocation | Telemetry Availability | `v0.2.0` Verification Status | Known Limitations |
| :--- | :--- | :--- | :--- | :--- |
| **Google Antigravity** | `/agent-billing` | Full local (`~/.gemini/antigravity`) | **Live-verified** (Windows 11) | Split cache-write tokens not separated in upstream logs (`UNAVAILABLE`). |
| **OpenAI Codex CLI** | `$agent-billing` / `/skills` | Full local (`~/.codex/sessions`) | **Live-verified** (Windows 11) | Custom `/prompts:*` slash prompts deprecated by Codex; use `$agent-billing`. |
| **Claude Code** | `/agent-billing` | Full local (`~/.claude/projects`) | **Partially verified** (collector, installer, & CLI verified on Windows 11; live LLM run blocked by expired local OAuth) | Unsplit Anthropic cache-write TTLs on `claude-opus-4-6` keep cache categories `PARTIALLY_PRICED`. |
| **Cursor** | `/agent-billing` | Unavailable locally (server-side) | **Partially verified** (CLI, installer/uninstaller, & disclosure verified on Windows 11; interactive IDE UI not driven live) | Cursor meters usage server-side; receipts report Cursor under `[ UNAVAILABLE TELEMETRY ]`. |
| **Gemini CLI** | `/agent-billing` | Full local (`~/.gemini/tmp/*/chats`) | **Fixture/unit-verified only** (`gemini` binary absent on test host) | Awaiting live community host testing across OS platforms. |
| **Windsurf** | `/agent-billing` | Unavailable locally (server-side) | **Fixture/unit-verified only** (Windsurf absent on test host) | Windsurf meters Cascade credits server-side; receipts report metrics as `Unavailable`. |

Full installation target paths are listed in [docs/SUPPORTED_AGENTS.md](docs/SUPPORTED_AGENTS.md).

---

## Installation

> **Important:** Cloning the repository or installing the Python package does **not** register `/agent-billing` or `$agent-billing` in your coding tools. You must run `agent-token-receipt install`.
>
> **OS Support Note (`v0.2.0 Public Beta`):** Tested end-to-end on **Windows 11** (`Python 3.11` & `3.13`). **Linux** and **macOS** native runtime testing is **not yet verified**; POSIX paths and wrapper templates are tested via isolated unit tests and open for community beta verification.

### Windows (PowerShell — Verified on Windows 11)

```powershell
# 1. Prerequisites: Python 3.10+ and Git
git clone https://github.com/foraiacc99-lang/agent-token-receipt.git
cd agent-token-receipt

# 2. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# 3. Install package, preview installer plan, and register agent commands
python -m pip install .
agent-token-receipt install --dry-run
agent-token-receipt install

# 4. Restart your IDE or terminal if needed, then verify and generate a receipt
agent-token-receipt doctor
agent-token-receipt generate --workspace . --all-agents --non-interactive
```

### Linux / macOS *(POSIX Venv Workflow — Native Runtime Unverified in v0.2.0)*

> On Ubuntu/Debian, install `python3-venv` and `python3-pip` first if `python3 -m venv` reports missing `ensurepip` (`sudo apt update && sudo apt install -y python3-venv python3-pip`).

```bash
# 1. Prerequisites: Python 3.10+ and Git
git clone https://github.com/foraiacc99-lang/agent-token-receipt.git
cd agent-token-receipt

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install package, preview installer plan, and register agent commands
python -m pip install .
agent-token-receipt install --dry-run
agent-token-receipt install

# 4. Restart your IDE or terminal if needed, then verify and generate a receipt
agent-token-receipt doctor
agent-token-receipt generate --workspace . --all-agents --non-interactive
```

*(Replace the clone URL above with your fork URL if contributing from a fork.)* For wheel (`pip install agent_token_receipt-0.2.0-py3-none-any.whl`), `pipx`, and uninstall steps, see [docs/INSTALLATION.md](docs/INSTALLATION.md).

---

## How to Use

### Inside AI Coding Agents

Run `agent-token-receipt install`, restart your IDE or agent CLI if it caches skill/command discovery on startup, and invoke:

- **Google Antigravity:** `/agent-billing`
- **Claude Code:** `/agent-billing`
- **OpenAI Codex CLI:** `$agent-billing` (or select from `/skills`)
- **Gemini CLI:** `/agent-billing`
- **Cursor:** `/agent-billing` *(discloses unavailable local token telemetry)*
- **Windsurf:** `/agent-billing` *(discloses unavailable local token telemetry)*

### From the Terminal

```bash
agent-token-receipt agents
agent-token-receipt doctor
agent-token-receipt sessions --all-agents --all-workspaces
agent-token-receipt generate --workspace . --all-agents --non-interactive
agent-token-receipt generate --all-agents --session <ID_OR_PREFIX> -o ./my_receipts
agent-token-receipt uninstall
```

You can also run `agent-token-receipt mcp` for local stdio JSON-RPC 2.0 integration (`list_agent_sessions`, `get_agent_usage`, `generate_agent_receipt`). Full CLI documentation is in [docs/USAGE.md](docs/USAGE.md).

---

## Example Receipt

> **ILLUSTRATIVE EXAMPLE ONLY:** The numbers below illustrate thermal receipt layout and accounting fields rather than actual measured session usage.

```text
==========================================
           AGENT TOKEN RECEIPT
        Every token has a receipt.
                Page 1 of 1
==========================================
           RECEIPT INFORMATION
Receipt ID:        rec-example-0001
Generated At:      2026-11-12 10:00:00
Timezone:          UTC
Session Title:
  Example Unified Workspace
Active Agents:
  Claude Code, OpenAI Codex
Total Turns:       2
------------------------------------------
          MODEL & AGENT BREAKDOWN
             [ MODEL 1 OF 2 ]
Model Name:        Claude Sonnet 4.6
Provider:          Anthropic
Agent:             Claude Code
Canonical ID:      claude-sonnet-4-6
Generation Turns:  1
Input Tokens:                        1,000
Output Tokens:                         250
Cache-Read Tokens:                   2,000
Cache-Write Tokens:            UNAVAILABLE
Input + Output Tokens:               1,250
Model Subtotal:                $0.0074 USD
Pricing Status:                   VERIFIED
------------------------------------------
             [ MODEL 2 OF 2 ]
Model Name:        GPT-5
Provider:          OpenAI
Agent:             OpenAI Codex
Canonical ID:      gpt-5
Generation Turns:  1
Input Tokens:                        1,500
Output Tokens:                         300
Cache-Read Tokens:                     500
Cache-Write Tokens:            UNAVAILABLE
Input + Output Tokens:               1,800
Model Subtotal:                $0.0049 USD
Pricing Status:                   VERIFIED
==========================================
        TOTAL USAGE & COST BREAKDOWN
Total Turns:                             2
Total Input Tokens:                  2,500
Total Output Tokens:                   550
Total Cache-Read:                    2,500
Input + Output Tokens:               3,050
------------------------------------------
ESTIMATED API TOTAL:           $0.0123 USD
Pricing Status:                   VERIFIED
Actual Billed Amount:
  None (Unbilled locally)
==========================================
```

**Estimated API Total vs. Actual Billed Amount:** `Estimated API Total` reflects what recorded tokens would cost at published pay-as-you-go API rates in `pricing/catalogue.json`. `Actual Billed Amount` remains `None (Unbilled locally)` because local logs do not contain your vendor subscription invoice.

---

## Architecture & Privacy

```text
+-----------------------+     read-only     +-----------------------+
| Local Agent Logs / DB | ----------------> | collector/            |
| (~/.gemini, ~/.claude,|                   | (BaseUsageCollector)  |
|  ~/.codex, ...)       |                   +-----------+-----------+
+-----------------------+                               |
                                                        v  CanonicalUsageRecord[]
+-----------------------+                   +-----------+-----------+
| pricing/              | ----------------> | core/                 |
| (catalogue.json +     |   Decimal rates   | (UsageAggregator)     |
|  CostCalculator)      |                   +-----------+-----------+
+-----------------------+                               |
                                                        v  Receipt
                                            +-----------+-----------+
                                            | generator/            |
                                            | (ReceiptPDFGenerator) |
                                            +-----------------------+
```

- **Local-First & Offline**: Zero cloud accounts, zero mandatory API keys, zero analytics telemetry, and zero runtime HTTP requests (`37` runtime Python modules audited).
- **Read-Only Access**: Opens SQLite databases with `?mode=ro` URI mode and session logs read-only.
- **Zero Content Retention**: Discards prompts, assistant replies, chain-of-thought prose, repository source code, and credentials.

Read the full privacy model in [docs/PRIVACY.md](docs/PRIVACY.md) and security disclosure policy in [SECURITY.md](SECURITY.md).

---

## Customization

Agent Token Receipt is modular around one shared accounting engine:
- Add new read-only `BaseUsageCollector` implementations (`collector/base.py`, `collector/registry.py`)
- Add new `BaseAgentIntegration` wrappers (`agent_token_receipt/installer/base.py`, `registry.py`)
- Customize project-scoped `/agent-billing` instructions safely (`agent-token-receipt install --scope project --workspace .`)
- Add verified, preview, or unverified model rates in `pricing/catalogue.json`
- Adjust 80mm thermal PDF formatting in `generator/pdf.py`

See [docs/CUSTOMIZATION.md](docs/CUSTOMIZATION.md) and [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Known Limitations

- **OS Coverage (`v0.2.0 Public Beta`)**: End-to-end runtime behavior is verified on Windows 11 (`Python 3.11` & `3.13`); Linux and macOS native runtime testing await community verification.
- **Live Agent Coverage**: Live interactive invocations are verified on Google Antigravity and OpenAI Codex CLI on Windows 11; Gemini CLI, Windsurf, authenticated Claude Code live LLM runs, and Cursor GUI interactions remain unverified live.
- **Cursor & Windsurf Telemetry**: Metered server-side; local receipts honestly mark token counts `Unavailable`.
- **Anthropic Cache-Write TTL Split**: Unsplit ephemeral cache-write counts on `claude-opus-4-6` keep unverified categories marked `PARTIALLY_PRICED`.
- **Unknown / Preview Pricing**: Models without published rates remain `UNAVAILABLE` / `unknown_price` rather than `$0.00`.

---

## Community & Contribution

- **Report Bugs / Beta Testing**: Follow [BETA_TESTING_GUIDE.md](BETA_TESTING_GUIDE.md) and [BETA_TEST_CHECKLIST.md](BETA_TEST_CHECKLIST.md), then submit [BETA_FEEDBACK_TEMPLATE.md](BETA_FEEDBACK_TEMPLATE.md) or open a GitHub Issue (never attach prompts, source code, API keys, or transcripts).
- **Request Features or New Agents**: Use the `.github/ISSUE_TEMPLATE/` forms.
- **Test on Linux or macOS**: Native test reports on Ubuntu/Debian, Fedora, Arch, and macOS (Intel & Apple Silicon) are especially welcome before `v1.0.0`.
- **Submit Pull Requests**: Read [CONTRIBUTING.md](CONTRIBUTING.md) and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md), and run `python -m unittest discover -s tests -v`.
- **Need Help?** See [SUPPORT.md](SUPPORT.md) and [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

---

## License

Licensed under the **MIT License**. See [LICENSE](LICENSE).
