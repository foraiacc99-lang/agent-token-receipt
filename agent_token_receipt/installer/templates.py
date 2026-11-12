"""Versioned command, workflow, and SKILL.md templates for agent integrations.

Templates invoke the local ``agent-token-receipt`` CLI strictly and never
duplicate token accounting or pricing calculations inside prompt markdown.
"""

from pathlib import Path
import sys
from typing import Optional

MANAGED_MARKER_MD = "<!-- managed-by: agent-token-receipt -->"
MANAGED_MARKER_TOML = "# managed-by: agent-token-receipt"


def _resolve_python_posix(python_executable: Optional[str] = None) -> str:
    """Return a forward-slash Python interpreter path safe across bash and PowerShell."""
    raw = python_executable if python_executable else sys.executable
    return Path(raw).as_posix()


def render_billing_skill_md(python_executable: Optional[str] = None) -> str:
    """Render portable SKILL.md compatible with Claude Code, Antigravity, Codex, Cursor, Windsurf, and Gemini CLI."""
    py_posix = _resolve_python_posix(python_executable)
    return f"""---
name: agent-billing
description: Generates verified local AI token usage and estimated API cost receipts via agent-token-receipt when the user invokes /agent-billing, asks for token usage, or requests session billing.
---

{MANAGED_MARKER_MD}

# Agent Token Receipt - Billing Command

When the user asks for usage billing, token counts, cost estimates, or a PDF receipt:

1. Run the local billing CLI against the active project workspace (read-only over local agent logs; never inspect raw user credentials):

```bash
agent-token-receipt generate --workspace . --all-agents --non-interactive
```

If `agent-token-receipt` is not yet on `PATH`, run:

```bash
python -m agent_token_receipt generate --workspace . --all-agents --non-interactive
```

If neither is available in the current shell (for example, when installed inside a dedicated virtual environment), invoke the installed Python environment directly:

- POSIX / bash / zsh: `"{py_posix}" -m agent_token_receipt generate --workspace . --all-agents --non-interactive`
- Windows PowerShell: `& "{py_posix}" -m agent_token_receipt generate --workspace . --all-agents --non-interactive`

2. Report strictly what the CLI prints:
   - Active coding agents and models detected
   - Input tokens, output tokens, cache-read/cache-write tokens (if reported)
   - Estimated API-equivalent cost breakdown and exact pricing status (`verified`, `preview_estimate`, `partially_priced`, or `unknown_price`)
   - Explicitly note any detected agents whose local token metrics are unavailable (for example, Cursor or Windsurf server-side metering) without guessing numbers
   - The generated 80mm thermal PDF receipt path under `./receipts/`

3. Never compute token prices manually in chat and never fabricate missing token metrics or pricing rates.
"""


def render_command_markdown(
    agent_display_name: str,
    mechanism_label: str,
    python_executable: Optional[str] = None,
) -> str:
    """Render slash command / workflow markdown for Cursor Commands and Windsurf Workflows."""
    py_posix = _resolve_python_posix(python_executable)
    return f"""---
description: Generate a verified Agent Token Receipt usage and cost breakdown for the current workspace.
---

{MANAGED_MARKER_MD}

# /agent-billing ({agent_display_name} {mechanism_label})

Generate an accurate, local-only token usage and API-equivalent cost receipt for this project using `agent-token-receipt`.

## Instructions

1. Execute the following command in the workspace root:

```bash
agent-token-receipt generate --workspace . --all-agents --non-interactive
```

Fallback if scripts directory is not on `PATH`:

```bash
python -m agent_token_receipt generate --workspace . --all-agents --non-interactive
```

Virtualenv / multi-Python fallback if both commands above fail:

- POSIX / bash / zsh: `"{py_posix}" -m agent_token_receipt generate --workspace . --all-agents --non-interactive`
- Windows PowerShell: `& "{py_posix}" -m agent_token_receipt generate --workspace . --all-agents --non-interactive`

2. Summarize only the verified output returned by `agent-token-receipt`:
   - Discovered agents and models
   - Exact input, output, cache-read, and cache-write token totals
   - Estimated API cost breakdown with pricing verification status
   - Any unavailable platforms or unpriced models reported by the engine
   - Saved PDF receipt file path

Do not recalculate or estimate token rates manually; rely solely on the Python billing engine.
"""


def render_gemini_cli_toml(python_executable: Optional[str] = None) -> str:
    """Render native ~/.gemini/commands/agent-billing.toml custom command for Gemini CLI."""
    py_posix = _resolve_python_posix(python_executable)
    return f"""{MANAGED_MARKER_TOML}
description = "Generate a verified local token usage and estimated API cost receipt via agent-token-receipt."
prompt = \"\"\"
Run the local Agent Token Receipt CLI in the current workspace to generate a verified billing summary and 80mm thermal PDF receipt:

```bash
agent-token-receipt generate --workspace . --all-agents --non-interactive
```

If `agent-token-receipt` is not on PATH, try `python -m agent_token_receipt generate --workspace . --all-agents --non-interactive`, or invoke the installed environment Python directly (`"{py_posix}" -m agent_token_receipt generate --workspace . --all-agents --non-interactive`, or `& "{py_posix}" ...` in PowerShell).

Optional user arguments passed to `/agent-billing`: {{{{args}}}}

Present only the verified token counts, pricing status, unavailable agent disclosures, and generated PDF receipt path reported by the CLI. Never invent token numbers or recalculate prices manually.
\"\"\"
"""

