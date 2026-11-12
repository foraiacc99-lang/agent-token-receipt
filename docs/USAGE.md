# Usage Guide

Agent Token Receipt can be invoked from inside supported AI coding agents or directly from the command line.

---

## 1. Invoking Inside AI Coding Agents

After running `agent-token-receipt install` (and restarting your IDE or CLI session if needed):

| Coding Agent | Command / Skill Invocation |
| :--- | :--- |
| **Google Antigravity** | `/agent-billing` |
| **Claude Code** | `/agent-billing` |
| **OpenAI Codex CLI** | `$agent-billing` (or select from `/skills`) |
| **Gemini CLI** | `/agent-billing` |
| **Cursor** | `/agent-billing` *(reports `Unavailable` local token telemetry)* |
| **Windsurf** | `/agent-billing` *(reports `Unavailable` local token telemetry)* |

> **Important:** In OpenAI Codex CLI, custom `/prompts:*` slash commands were deprecated in favor of Agent Skills. Use **`$agent-billing`** or `/skills`.

---

## 2. Terminal CLI Reference

You can run commands via `agent-token-receipt` (or alias `agent-receipt`, or `python -m agent_token_receipt`).

### Global Options

- `--version`: Print version (`agent-token-receipt, version 0.2.0`).
- `--help`: Show command summary and examples.

### `agents` — Inspect Supported Environments

```bash
agent-token-receipt agents [--workspace .]
```

Lists each supported coding agent, global/project detection status, invocation syntax, integration mechanism, and whether local token telemetry is supported.

### `doctor` — Verify Installation & Telemetry Readiness

```bash
agent-token-receipt doctor [--workspace .]
```

Verifies:
- CLI entrypoint availability and active Python executable.
- `pricing/catalogue.json` integrity and model count (`15`).
- Default receipt output writability (`./receipts`).
- Per-agent command installation status, wrapper Python path alignment, and local telemetry availability.

### `install` — Register Agent Integrations

```bash
agent-token-receipt install [OPTIONS]
```

Options:
- `--scope <auto|global|project|both>` (default: `auto` — uses global paths for detected agents and project fallback otherwise)
- `--workspace`, `-w <path>` (default: `.`)
- `--agent <name>` (repeatable; e.g., `--agent claude_code --agent codex`)
- `--dry-run`: Preview detected agents, planned target file paths, and status without writing files.
- `--yes`, `-y`: Skip the interactive confirmation prompt.
- `--force`: Overwrite existing modified files after backing them up to `<file>.atr.bak.<timestamp>`.

### `uninstall` — Remove Managed Integrations

```bash
agent-token-receipt uninstall [OPTIONS]
```

Options:
- `--scope <all|global|project>` (default: `all`)
- `--workspace`, `-w <path>` (default: `.`)
- `--agent <name>` (repeatable)
- `--yes`, `-y`: Skip confirmation prompt.

Deletes only manifest-tracked artifacts, decrements reference counts on shared `.agents/skills` files, and restores `.atr.bak.*` backups when present.

### `sessions` — List Discovered Sessions

```bash
agent-token-receipt sessions [OPTIONS]
```

Options:
- `--workspace`, `-w <path>`: Filter sessions to a specific project directory.
- `--all-workspaces`, `-a`: List sessions across all local workspaces.
- `--agent <name>`: Filter to specific agents (repeatable).
- `--all-agents`: Discover sessions across all available telemetry-capable agents.

Examples:

```bash
# List Antigravity sessions for the current workspace (or all if workspace matches none)
agent-token-receipt sessions

# List sessions across all local agents and all workspaces
agent-token-receipt sessions --all-agents --all-workspaces
```

### `generate` — Create a Thermal PDF Receipt

```bash
agent-token-receipt generate [OPTIONS]
```

Options:
- `--session`, `-s <id_or_prefix>`: Full session ID or unique ID prefix.
- `--output`, `-o <dir>` (default: `./receipts`): Output folder for the PDF file.
- `--workspace`, `-w <path>`: Generate a unified receipt for sessions matching a workspace directory.
- `--agent <name>`: Include specific coding agents (repeatable).
- `--all-agents`: Include all available coding agents.
- `--interactive / --non-interactive` (default: `--interactive`): Fail instead of prompting if interactive selection would be required.

Examples:

```bash
# Interactive session picker (Antigravity default)
agent-token-receipt generate

# Unified multi-agent receipt for the current project workspace
agent-token-receipt generate --workspace . --all-agents --non-interactive

# Single session by ID prefix into a custom folder
agent-token-receipt generate --all-agents --session 99d16623 -o ./my_receipts
```

### `mcp` — Optional Local Stdio MCP Server

```bash
agent-token-receipt mcp
```

Starts a local JSON-RPC 2.0 MCP server over `stdin`/`stdout` with zero extra runtime dependencies, exposing:
- `list_agent_sessions`
- `get_agent_usage`
- `generate_agent_receipt`

---

## 3. Understanding Receipt Fields & Export Locations

### Export Locations

- Default output folder: `./receipts` in your current working directory (override with `-o <path>`).
- Collision-safe filenames: `receipt_<session_prefix>_<receipt_id>_<timestamp>.pdf`, automatically appending `_1.pdf`, `_2.pdf`, etc. if an identically named file already exists.

### Key Receipt Fields

- **Input Tokens**: Uncached prompt/context tokens sent to the model.
- **Output Tokens**: Generated assistant tokens.
- **Cache-Read Tokens**: Tokens served from prompt cache without inflating `input_tokens`.
- **Cache-Write Tokens**: Prompt cache creation tokens when separately reported by the agent.
- **Input + Output Tokens**: Strictly `input_tokens + output_tokens` (never double-counts cached tokens).
- **Pricing Status**:
  - `VERIFIED`: Every non-zero reported token category uses published standard API rates.
  - `PREVIEW_ESTIMATE`: Uses documented introductory/preview API rates.
  - `PARTIALLY_PRICED`: At least one category has a published rate and at least one non-zero category lacks a verified rate (displayed as `UNAVAILABLE`).
  - `UNAVAILABLE` / `unknown_model` / `unknown_price`: No published rate exists in `pricing/catalogue.json`.
- **Estimated API Total**: Hypothetical pay-as-you-go API value in USD computed with Python `Decimal`.
- **Actual Billed Amount**: Strictly `None (Unbilled locally)` whenever local logs do not contain vendor invoice amounts.
- **`[ UNAVAILABLE TELEMETRY ]`**: Lists explicitly queried or workspace-present tools (Cursor, Windsurf) that do not store local token counts.

