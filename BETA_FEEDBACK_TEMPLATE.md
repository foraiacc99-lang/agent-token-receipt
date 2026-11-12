# Agent Token Receipt — Beta Feedback Template (`v0.2.0`)

Please copy and complete the sections below when submitting beta feedback.

> **Privacy Reminder:** **NEVER** include private prompts, source code snippets, model thinking content, API keys, credentials, or raw session transcript files in your feedback.

---

## 1. Environment Details

- **Operating System & Version:** *(e.g., Windows 11 24H2, macOS 15.1 Apple Silicon, Ubuntu 24.04 x86_64)*
- **Python Version:** *(output of `python --version`)*
- **Install Method:** *(venv from source / venv from `.whl` / `pip install --user` / `pipx` / existing Python env)*
- **Coding Agent(s) Tested:** *(Google Antigravity / Claude Code / OpenAI Codex CLI / Gemini CLI / Cursor / Windsurf)*

---

## 2. Installation & Setup Results

- **Package Installation (`pip install`):** `[ ] Success` / `[ ] Failure` / `[ ] Not Tested`
- **Universal Installer (`agent-token-receipt install --dry-run` & `install`):** `[ ] Success` / `[ ] Failure` / `[ ] Not Tested`
- **`agent-token-receipt doctor` Output Summary:** *(paste sanitized doctor status here)*

---

## 3. Command & Receipt Generation Results

- **Native Agent Command Invocation (`/agent-billing` or `$agent-billing`):** `[ ] Success` / `[ ] Failure` / `[ ] Not Tested`
- **Terminal Receipt Generation (`agent-token-receipt generate ...`):** `[ ] Success` / `[ ] Failure` / `[ ] Not Tested`
- **Uninstallation (`agent-token-receipt uninstall`):** `[ ] Success` / `[ ] Failure` / `[ ] Not Tested`

---

## 4. Accuracy & PDF Checks

- **Incorrect Token Counts?** `[ ] No` / `[ ] Yes`
  - *If yes, provide only numeric details (agent, model, CLI-reported input/output/cache-read vs. expected count):*
- **Incorrect Pricing?** `[ ] No` / `[ ] Yes`
  - *If yes, provide model ID, pricing status (`verified`, `preview_estimate`, `partially_priced`, `unavailable`), and rate discrepancy:*
- **PDF Problems?** `[ ] No` / `[ ] Yes`
  - *If yes, describe layout, wrapping, truncation, pagination, or viewer issues:*

---

## 5. Error Messages (Sanitized)

Paste any sanitized CLI traceback or command error message here (redact usernames or workspace paths if sensitive):

```text
<paste sanitized error output here>
```

---

## 6. Suggestions & General Feedback

- What worked smoothly?
- What felt confusing during setup, invocation, or uninstall?
- Any edge cases or compatibility quirks you noticed?

