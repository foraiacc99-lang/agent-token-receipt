# Security Policy

## Supported Versions

| Version | Status | Security Updates |
| :--- | :--- | :--- |
| `0.2.0` (Public Beta) | Current Beta Release | Best-effort fixes |
| `< 0.2.0` | Unsupported | None |

## Security & Privacy Model

Agent Token Receipt is designed for **100% local, read-only execution**:
- Collectors never write to upstream session logs or SQLite state files (`?mode=ro`).
- Zero outbound runtime network calls, analytics, or telemetry SDKs exist in the codebase.
- User prompts, source code, chain-of-thought prose, and API keys are never extracted or written to PDFs or stdout.

## Reporting a Vulnerability

If you discover a security or privacy issue (for example, unintended path traversal, unintended file overwrite during installation/uninstall, or accidental secret leakage):

1. **Do not** open a public issue with exploitable details or paste private session logs, API keys, or transcripts.
2. Report the vulnerability privately through **GitHub Security Advisories** (if enabled on the repository) or contact the project maintainer directly.
3. Include OS, Python version, affected command (`generate`, `install`, `uninstall`, `mcp`), and minimal sanitized reproduction steps.

