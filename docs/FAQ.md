# Frequently Asked Questions (FAQ)

### Is Agent Token Receipt free?
Yes. Agent Token Receipt is free, open-source software licensed under the **MIT License**.

### Does it require an API key?
No. Agent Token Receipt reads local session files already on your computer and uses its bundled local pricing catalogue (`pricing/catalogue.json`). No OpenAI, Anthropic, Google, or vendor API key is needed.

### Does it work with multiple coding agents?
Yes. It supports command/skill installation for **Google Antigravity**, **Claude Code**, **OpenAI Codex CLI**, **Gemini CLI**, **Cursor**, and **Windsurf**, and can combine sessions across multiple agents in the same workspace into a single receipt via `agent-token-receipt generate --workspace . --all-agents`.

### Does it track usage automatically in the background?
No. There is no background daemon or telemetry hook. Agent Token Receipt reads existing local session logs on demand only when you run a CLI command (`sessions`, `generate`), invoke `/agent-billing` (or `$agent-billing` in Codex), or call its optional local `mcp` stdio server.

### Where are receipts saved?
By default, receipts are saved to `./receipts/` in your current working directory. You can specify another folder with `-o <directory>`. Existing files are never overwritten; numeric suffixes (`_1.pdf`) are appended if needed.

### Does it upload my conversations or prompts?
No. Collectors read files offline in read-only mode, ignore prompts/code/thinking text, and never make outbound network requests. Note that if you invoke `/agent-billing` *inside* an active coding agent chat, that IDE/CLI sends your command turn to its own AI provider as part of running the assistant—use `agent-token-receipt generate` in your terminal for zero-LLM execution.

### Why are some token counts unavailable?
Not every coding tool records every metric locally. **Cursor** and **Windsurf** meter token usage server-side, so their local token counts remain `Unavailable`. Even in telemetry-enabled tools, fields like split `cache_write_tokens` or separate `reasoning_tokens` are reported as `UNAVAILABLE` whenever the upstream log does not record them.

### Why is actual subscription billing unavailable (`None (Unbilled locally)`)?
Local IDE and CLI logs record token quantities, not your vendor invoice or subscription plan balance. Showing `Estimated API Total` alongside `Actual Billed Amount: None (Unbilled locally)` avoids misrepresenting a hypothetical API-rate estimate as an actual charge.

### Can I create my own integration or pricing entry?
Yes. See [CUSTOMIZATION.md](CUSTOMIZATION.md) and [../CONTRIBUTING.md](../CONTRIBUTING.md) for step-by-step instructions on adding collectors (`collector/base.py`), installer integrations (`agent_token_receipt/installer/base.py`), project-local skills/commands, and model rates in `pricing/catalogue.json`.

