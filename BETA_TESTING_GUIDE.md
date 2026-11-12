# Agent Token Receipt — Public Beta Testing Guide (`v0.2.0`)

> **Every token has a receipt.**

Thank you for helping test **Agent Token Receipt** during controlled public beta! This guide walks you through installing, configuring, testing, and uninstalling the tool safely on your machine.

---

## 1. What Agent Token Receipt Does

**Agent Token Receipt** is a 100% local-first, read-only Python CLI that audits local AI coding-agent session logs and generates authentic 80mm thermal-printer-style PDF receipts showing genuine token counts and estimated pay-as-you-go API-equivalent costs.

- **Privacy-First & Read-Only:** Never modifies agent logs, never reads prompts, code snippets, or thinking text, requires zero API keys, and makes zero network calls.
- **Zero Data Fabrication:** Missing metrics, unpriced preview models, and server-side-metered platforms (Cursor, Windsurf) are reported honestly as `UNAVAILABLE` / `Unavailable`—never guessed or defaulted to `$0.00`.

---

## 2. Prerequisites

- **Python 3.10 or newer** (`3.10`, `3.11`, `3.12`, or `3.13`)
- **Git**
- One or more supported AI coding agents:
  - Google Antigravity
  - Claude Code
  - OpenAI Codex CLI
  - Gemini CLI
  - Cursor
  - Windsurf

> [!NOTE]
> **Ubuntu / Debian Linux users:** If `python3 -m venv` reports that `ensurepip` is missing, install `python3-venv` and `python3-pip` first (e.g., `sudo apt update && sudo apt install -y python3-venv python3-pip`).

---

## 3. Clone the Repository

```bash
git clone https://github.com/foraiacc99-lang/agent-token-receipt.git
cd agent-token-receipt
```

---

## 4. Install Agent Token Receipt

### Option A: Virtual Environment (Recommended for Isolated Beta Testing)

Create and activate a virtual environment:

```bash
python -m venv .venv
```

Activate it for your shell:
- **Windows (PowerShell):** `.venv\Scripts\Activate.ps1`
- **Windows (CMD):** `.venv\Scripts\activate.bat`
- **macOS / Linux (bash/zsh):** `source .venv/bin/activate`

Install from the repository source (or from a release `.whl` file):

```bash
# From cloned source:
python -m pip install .

# Or from a downloaded wheel:
python -m pip install dist/agent_token_receipt-0.2.0-py3-none-any.whl
```

### Option B: Global User / `pipx` Install (Always on `PATH`)

If you want `agent-token-receipt` on your global `PATH` across all terminal windows and workspaces:

```bash
# Using pipx (recommended if installed):
pipx install .

# Or user-level pip install:
python -m pip install --user .
```

### Verify the Installation

```bash
agent-token-receipt --version
agent-token-receipt doctor
```

Expected version output:

```text
agent-token-receipt, version 0.2.0
```

*(If `agent-token-receipt` is not on your `PATH`, you can always run `python -m agent_token_receipt --version`.)*

---

## 5. Install Agent Integrations (`/agent-billing` & `$agent-billing`)

1. **Preview detected environments without modifying any files:**

   ```bash
   agent-token-receipt install --dry-run
   ```

2. **Install integrations (prompts for explicit confirmation before writing):**

   ```bash
   agent-token-receipt install
   ```

   Useful options:
   - `--scope global` (default behavior when global agent config exists), `--scope project`, or `--scope both`
   - `--agent claude_code` (or `codex`, `antigravity`, `gemini_cli`, `cursor`, `windsurf`) to target specific agents
   - `--force` to back up (`.atr.bak.<timestamp>`) and replace any existing conflicting file
   - `--yes` to skip the interactive confirmation prompt

3. **Confirm integration status:**

   ```bash
   agent-token-receipt agents
   agent-token-receipt doctor
   ```

4. **Invoke billing inside your coding agent:**
   - **Google Antigravity, Claude Code, Gemini CLI, Cursor, Windsurf:** Type `/agent-billing`
   - **OpenAI Codex CLI:** Type `$agent-billing` (or choose `agent-billing` from `/skills`)

> [!IMPORTANT]
> **Cursor & Windsurf:** Both receive working `/agent-billing` integrations, but because Cursor and Windsurf meter token usage server-side rather than storing per-turn token counts locally, receipts will report their local token metrics as `Unavailable`. This is expected behavior, not a bug.

---

## 6. Generate a Receipt

You can generate receipts either from inside your coding agent (`/agent-billing` or `$agent-billing`) or directly from the terminal:

```bash
# 1. List discovered sessions across all local agents and workspaces
agent-token-receipt sessions --all-agents --all-workspaces

# 2. Generate a combined multi-agent receipt for the current project workspace
agent-token-receipt generate --workspace . --all-agents --non-interactive

# 3. Generate interactively (Antigravity session picker)
agent-token-receipt generate

# 4. Generate for a specific session ID or prefix into a custom folder
agent-token-receipt generate --all-agents --session <SESSION_ID_PREFIX> -o ./my_receipts
```

Generated PDFs are saved to `./receipts/` (or your `-o` directory) with collision-safe filenames so existing PDFs are never overwritten.

---

## 7. Uninstall Cleanly

1. **Remove all installed agent commands/skills (and restore any `.atr.bak.*` backups):**

   ```bash
   agent-token-receipt uninstall
   ```

2. **Verify removal:**

   ```bash
   agent-token-receipt doctor
   ```

3. **Remove the Python package (or delete `.venv`):**

   ```bash
   python -m pip uninstall agent-token-receipt
   ```

---

## 8. How to Report Bugs & Share Feedback

Please fill out [`BETA_FEEDBACK_TEMPLATE.md`](BETA_FEEDBACK_TEMPLATE.md) and review [`BETA_TEST_CHECKLIST.md`](BETA_TEST_CHECKLIST.md) to separate expected unsupported telemetry from real bugs.

> [!CAUTION]
> **Privacy Rule for Bug Reports:** Never attach or paste private prompts, repository source code, model thinking content, API keys, `.env` files, or raw personal session transcripts into a bug report or GitHub issue. Share only OS/Python details, sanitized CLI error messages, model names, and numeric token discrepancies.

