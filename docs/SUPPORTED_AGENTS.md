# Supported Coding Agents

Agent Token Receipt (`v0.2.0 Public Beta`) supports command/skill installation across **six** AI coding environments and honest local usage collection across each platform's verifiable trace format.

---

## Summary Matrix

| Coding Agent | Trigger | Telemetry Support | `v0.2.0` Verification Status |
| :--- | :--- | :--- | :--- |
| **Google Antigravity** | `/agent-billing` | **Full local** (`~/.gemini/antigravity`) | **Live-verified** (Windows 11) |
| **OpenAI Codex CLI** | `$agent-billing` / `/skills` | **Full local** (`~/.codex/sessions`) | **Live-verified** (Windows 11) |
| **Claude Code** | `/agent-billing` | **Full local** (`~/.claude/projects`) | **Partially verified** (collector, installer, CLI, & PDF generation verified on Windows 11; live interactive LLM run blocked locally by expired OAuth) |
| **Cursor** | `/agent-billing` | **Unavailable locally** *(server-side metering)* | **Partially verified** (CLI, installer, uninstaller, & `Unavailable` disclosure verified on Windows 11; interactive IDE UI not driven live) |
| **Gemini CLI** | `/agent-billing` | **Full local** (`~/.gemini/tmp/*/chats`) | **Fixture/unit-verified only** (`gemini` binary absent on test host) |
| **Windsurf** | `/agent-billing` | **Unavailable locally** *(server-side credits)* | **Fixture/unit-verified only** (Windsurf absent on test host) |

---

## Per-Integration Details & Target Paths

### 1. Google Antigravity (`antigravity`)
- **Invocation:** `/agent-billing`
- **Mechanism:** Agent Skill (`SKILL.md`)
- **Global install path:** `~/.gemini/config/skills/agent-billing/SKILL.md`
- **Project install path:** `.agents/skills/agent-billing/SKILL.md`
- **Local telemetry source:** `~/.gemini/antigravity/conversation_summaries.db` (read-only SQLite) and `~/.gemini/antigravity/brain/<session-id>/.system_generated/logs/transcript.jsonl`
- **Notes:** Deduplicates repeated `step_index` entries; preserves missing `input_tokens` or `cache_write_tokens` as `None` / `UNAVAILABLE`.

### 2. Claude Code (`claude_code`)
- **Invocation:** `/agent-billing`
- **Mechanism:** Agent Skill (`SKILL.md`)
- **Global install path:** `~/.claude/skills/agent-billing/SKILL.md`
- **Project install path:** `.claude/skills/agent-billing/SKILL.md`
- **Local telemetry source:** `~/.claude/projects/<project>/*.jsonl` and `<session>/subagents/agent-*.jsonl`
- **Notes:** Deduplicates streamed chunks by `message.id` across root and subagent transcripts and captures `cache_creation_input_tokens` and `cache_read_input_tokens`. Unsplit Anthropic cache-write TTLs on `claude-opus-4-6` keep unverified categories marked `PARTIALLY_PRICED`.

### 3. OpenAI Codex CLI (`codex`)
- **Invocation:** **`$agent-billing`** or choose `agent-billing` from **`/skills`**
- **Mechanism:** Agent Skill (`SKILL.md`) — *Codex deprecated custom `/prompts:*` slash commands*
- **Global install path:** `~/.codex/skills/agent-billing/SKILL.md`
- **Project install path:** `.agents/skills/agent-billing/SKILL.md`
- **Local telemetry source:** `~/.codex/sessions/**/rollout-*.jsonl`
- **Notes:** Subtracts `cached_input_tokens` from `input_tokens` (`max(0, input_tokens - cached_input_tokens)`) so cached reads are never double-counted into uncached input tokens, and filters duplicate cumulative `token_count` snapshots.

### 4. Gemini CLI (`gemini_cli`)
- **Invocation:** `/agent-billing`
- **Mechanism:** Custom TOML Slash Command + Agent Skill
- **Global install paths:**
  - `~/.gemini/commands/agent-billing.toml`
  - `~/.gemini/skills/agent-billing/SKILL.md`
- **Project install paths:**
  - `.gemini/commands/agent-billing.toml`
  - `.agents/skills/agent-billing/SKILL.md`
- **Local telemetry source:** `~/.gemini/tmp/<project_hash>/chats/session-*.jsonl` and legacy `session-*.json`
- **Notes:** Disambiguates `tokens.input`, `tokens.cached`, and `tokens.total` invariants safely.

### 5. Cursor (`cursor`)
- **Invocation:** `/agent-billing`
- **Mechanism:** Custom Slash Command + Agent Skill
- **Global install paths:**
  - `~/.cursor/commands/agent-billing.md`
  - `~/.cursor/skills/agent-billing/SKILL.md`
- **Project install paths:**
  - `.cursor/commands/agent-billing.md`
  - `.cursor/skills/agent-billing/SKILL.md`
- **Local telemetry:** **Unavailable (`supports_token_telemetry = False`)**. Cursor meters token usage server-side and does not write verifiable per-turn token counts locally. Receipts render Cursor transparently under `[ UNAVAILABLE TELEMETRY ]`.

### 6. Windsurf (`windsurf`)
- **Invocation:** `/agent-billing`
- **Mechanism:** Workflow + Agent Skill
- **Global install paths:**
  - `~/.codeium/windsurf/global_workflows/agent-billing.md`
  - `~/.codeium/windsurf/skills/agent-billing/SKILL.md`
- **Project install paths:**
  - `.windsurf/workflows/agent-billing.md`
  - `.windsurf/skills/agent-billing/SKILL.md`
- **Local telemetry:** **Unavailable (`supports_token_telemetry = False`)**. Windsurf meters Cascade prompt credits server-side and does not expose verifiable local token logs. Receipts disclose Windsurf under `[ UNAVAILABLE TELEMETRY ]`.

---

## Shared `.agents/skills` Manifest Tracking

Notice that **Google Antigravity**, **OpenAI Codex CLI**, and **Gemini CLI** share `.agents/skills/agent-billing/SKILL.md` during `--scope project` installation. `agent-token-receipt` tracks owners in `~/.agent-token-receipt/install_manifest.json` using reference counting so uninstalling one agent never deletes shared skills still needed by another.

