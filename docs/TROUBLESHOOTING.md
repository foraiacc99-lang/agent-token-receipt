# Troubleshooting Guide

Common setup and usage issues and how to resolve them cleanly.

---

## 1. `agent-token-receipt: command not found`

**Cause:** Your virtual environment is not activated, or your user scripts directory is not on `PATH`.

**Fix:**
- Activate `.venv` first:
  - PowerShell: `.venv\Scripts\Activate.ps1`
  - CMD: `.venv\Scripts\activate.bat`
  - macOS / Linux: `source .venv/bin/activate`
- Or invoke via module directly using your `.venv` Python binary:
  ```bash
  python -m agent_token_receipt --help
  ```
- Open a new terminal window after global `--user` or `pipx` installs so `PATH` refreshes.

---

## 2. `doctor` Warns That Installed Wrappers Point to Another Python Interpreter

**Cause:** You installed `/agent-billing` from one Python environment (or global install) and later reinstalled into a `.venv` (or vice versa).

**Fix:** Run `install --force` from the active Python environment you want to keep using:

```bash
agent-token-receipt install --force
agent-token-receipt doctor
```

Existing files are automatically backed up with a `.atr.bak.<timestamp>` suffix.

---

## 3. `/agent-billing` or `$agent-billing` Does Not Appear Inside My IDE / CLI

1. Confirm files were actually installed (cloning alone does not install them):
   ```bash
   agent-token-receipt doctor
   ```
2. **Restart or reload your IDE / CLI session.** Most tools index skills, commands, and workflows at startup.
3. **OpenAI Codex CLI:** Codex deprecated custom slash prompts. Type **`$agent-billing`** or pick `agent-billing` from **`/skills`**, not `/agent-billing`.

---

## 4. `python3 -m venv .venv` Fails on Ubuntu / Debian (`ensurepip` Missing)

**Fix:**

```bash
sudo apt update && sudo apt install -y python3-venv python3-pip
```

---

## 5. Cursor or Windsurf Shows `Unavailable` Token Counts

**Expected Behavior:** Cursor and Windsurf meter usage server-side and do not write verifiable per-turn token counts to disk. Receipts report `[ UNAVAILABLE TELEMETRY ]` rather than guessing numbers. See [SUPPORTED_AGENTS.md](SUPPORTED_AGENTS.md).

---

## 6. No Sessions Found in Current Workspace

`agent-token-receipt sessions` filters to the current folder by default. To inspect sessions across all workspaces and all installed agents:

```bash
agent-token-receipt sessions --all-agents --all-workspaces
```

Then generate a receipt using the desired `--workspace <path>` or `--session <id_prefix>`.

---

## 7. `Estimated API Total` Differs from My Subscription Bill

Receipts estimate what your token counts would cost at published pay-as-you-go developer API rates (`pricing/catalogue.json`), whereas IDEs and CLIs often run under flat monthly subscriptions or preview credits (`Actual Billed Amount: None (Unbilled locally)`). If a model shows `UNAVAILABLE` or `PARTIALLY_PRICED`, no published rate exists for that model or cache category yet.

---

## 8. Reporting a Bug

Run `agent-token-receipt doctor`, review [../BETA_TEST_CHECKLIST.md](../BETA_TEST_CHECKLIST.md), and submit [../BETA_FEEDBACK_TEMPLATE.md](../BETA_FEEDBACK_TEMPLATE.md) on GitHub Issues—**without** pasting prompts, code, API keys, or raw session logs.

