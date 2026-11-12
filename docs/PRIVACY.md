# Privacy & Local-First Architecture

Agent Token Receipt is built to audit your local AI coding-agent usage **without sending data off your machine** or extracting private conversation content.

---

## 1. What Data Is Collected Locally

Collectors read only structural metadata and numeric token counters required for receipts:

- Session ID (`session_id`) and display title (`session_title`)
- Workspace folder path (`workspace_path`)
- Turn index (`turn_index`) and UTC timestamps (`timestamp`)
- Coding agent name (`agent`), model provider (`provider`), and model ID/display name
- Whether thinking mode was enabled (`thinking_enabled` boolean flag, when recorded)
- Numeric token counters (`input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, `thought_tokens`)

---

## 2. Information Never Collected or Retained

Collectors discard or ignore all sensitive content in session traces:

- User prompts or chat messages
- Assistant responses or explanations
- Chain-of-thought / reasoning (`thinking`) prose
- Repository source code, file paths inside edits, or diffs
- Tool call arguments, shell commands, or stdout/stderr logs
- API keys, OAuth tokens, passwords, or `.env` values

---

## 3. Read-Only Access Behavior

- **SQLite databases:** Antigravity's `conversation_summaries.db` is opened strictly using SQLite read-only URI mode (`file:...?mode=ro`, `uri=True`), falling back to reading an isolated temporary copy if locked rather than writing to the original file.
- **Session logs:** JSON and JSONL files are opened strictly with `"r"` read-only mode (`collector/` never opens any agent trace file for writing).
- **Receipts output:** Generated PDFs are written only to the local output folder you choose (`./receipts` by default or `-o <dir>`).
- **Installer manifest:** Only `install` / `uninstall` write integration files (after explicit confirmation unless `--yes` is passed) and record managed paths in `~/.agent-token-receipt/install_manifest.json`.

---

## 4. Network & Telemetry Behavior

- **Zero Runtime Network Requests:** An AST import audit across all `37` runtime Python files (`agent_token_receipt/`, `cli/`, `collector/`, `core/`, `generator/`, `pricing/`) confirmed zero imports of `requests`, `httpx`, `aiohttp`, `urllib.request`, `urllib3`, `socket`, `http`, or any telemetry/analytics SDK.
- Only Python's `urllib.parse` is imported in `collector/antigravity.py` to decode local `file:///` workspace URIs on disk.
- **No Cloud Account / No API Keys:** Generating receipts works 100% offline. `pricing/catalogue.json` ships locally with the package.
- **Important Distinction About Coding Agents Themselves:** Agent Token Receipt runs offline locally; however, your underlying coding IDEs/CLIs still communicate with their own AI providers according to their own privacy policies, and invoking `/agent-billing` *inside* an active LLM chat causes that agent to execute the Skill/Command prompt. For completely non-LLM local generation, run `agent-token-receipt generate` directly in your terminal.

