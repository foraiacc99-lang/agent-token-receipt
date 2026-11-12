# Installation Guide

> **Current Status (`v0.2.0 Public Beta`):** Tested end-to-end on **Windows 11** (`Python 3.11` & `3.13`). Native **Linux** and **macOS** runtime testing has not yet been verified; POSIX paths and wrapper templates are covered via unit tests and await community beta verification.

Cloning the repository or installing the Python package does **not** automatically register `/agent-billing` or `$agent-billing` inside your AI coding tools. You must also run `agent-token-receipt install`.

---

## 1. Prerequisites

- **Python 3.10 or newer** (`3.10`, `3.11`, `3.12`, or `3.13`) with `pip` and `venv`
- **Git** (if installing from a cloned repository)
- At least one supported AI coding environment (Google Antigravity, Claude Code, OpenAI Codex CLI, Gemini CLI, Cursor, or Windsurf)

---

## 2. Windows Installation (Verified on Windows 11)

Open **PowerShell** (or Windows Terminal):

```powershell
# 1. Clone the repository and enter the project folder
git clone https://github.com/foraiacc99-lang/agent-token-receipt.git
cd agent-token-receipt

# 2. Create and activate an isolated virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# 3. Install Agent Token Receipt
python -m pip install .

# 4. Preview and register IDE / CLI integrations
agent-token-receipt install --dry-run
agent-token-receipt install

# 5. Restart open terminals/IDEs if needed, then verify
agent-token-receipt doctor
```

If PowerShell blocks `.venv\Scripts\Activate.ps1` due to execution policy, either use CMD (`.venv\Scripts\activate.bat`) or run via `.venv\Scripts\python.exe -m pip install .` and `.venv\Scripts\python.exe -m agent_token_receipt ...`.

---

## 3. Linux Installation *(Runtime Verification Pending Beta)*

> [!NOTE]
> Native Linux runtime installation has not yet been verified in CI or on a live Linux desktop/container with `pip`/`venv`. Debian and Ubuntu systems often omit `pip` and `ensurepip` by default—install `python3-venv` and `python3-pip` before creating a virtual environment.

```bash
# Debian / Ubuntu prerequisite (if python3 -m venv fails):
sudo apt update && sudo apt install -y python3-venv python3-pip

# 1. Clone and enter the repository
git clone https://github.com/foraiacc99-lang/agent-token-receipt.git
cd agent-token-receipt

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install Agent Token Receipt
python -m pip install .

# 4. Preview and register integrations
agent-token-receipt install --dry-run
agent-token-receipt install

# 5. Verify installation
agent-token-receipt doctor
```

---

## 4. macOS Installation *(Not Yet Tested)*

> [!NOTE]
> Native macOS runtime execution has not yet been tested. Standard macOS/POSIX paths (`~/.claude`, `~/.codex`, `~/.gemini`, `~/.codeium/windsurf`, and `~/Library/Application Support/Cursor`) are implemented in code and unit-tested via mocks.

```bash
# 1. Clone and enter the repository
git clone https://github.com/foraiacc99-lang/agent-token-receipt.git
cd agent-token-receipt

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install Agent Token Receipt
python -m pip install .

# 4. Preview and register integrations
agent-token-receipt install --dry-run
agent-token-receipt install

# 5. Verify installation
agent-token-receipt doctor
```

---

## 5. Alternative Install Options

### Install from a Built Wheel

```bash
python -m pip install agent_token_receipt-0.2.0-py3-none-any.whl
```

### Global Isolated Install with `pipx`

```bash
pipx install .
```

### Editable Development Install

```bash
python -m pip install -e .
```

---

## 6. Post-Install Checklist & Restart Behavior

1. **Restart Terminal:** If you installed globally (`pipx` or `--user`) and `agent-token-receipt` is not recognized, open a new terminal window so updated `PATH` entries load.
2. **Restart Coding Agents / IDEs:** Many IDEs and CLIs cache Skills and custom commands only at startup. Restart or reload your coding tool after running `agent-token-receipt install` so `/agent-billing` (or `$agent-billing` in Codex) appears.
3. **Run Diagnostics:**
   ```bash
   agent-token-receipt --version
   agent-token-receipt agents
   agent-token-receipt doctor
   ```
   `doctor` checks CLI execution readiness, `pricing/catalogue.json` load status, detected agents, wrapper alignment with the active Python interpreter, and local session availability.
4. **Generate Your First Receipt:**
   ```bash
   agent-token-receipt sessions --all-agents --all-workspaces
   agent-token-receipt generate --workspace . --all-agents --non-interactive
   ```

---

## 7. Clean Uninstallation

```bash
# Remove installed /agent-billing commands & skills cleanly and restore backups
agent-token-receipt uninstall

# Optional: remove the Python package
python -m pip uninstall agent-token-receipt
```

For common setup errors, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

