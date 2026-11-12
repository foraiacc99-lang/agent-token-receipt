"""Isolated tests for Phase 7 CLI commands and optional local stdio MCP server."""

import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from click.testing import CliRunner

from agent_token_receipt.installer import UniversalInstaller
from agent_token_receipt.mcp_server import LocalMCPServer
from cli.main import cli
from collector.antigravity import AntigravityUsageCollector
from collector.claude_code import ClaudeCodeUsageCollector
from collector.codex import CodexUsageCollector
from collector.cursor import CursorUsageCollector
from collector.gemini_cli import GeminiCLIUsageCollector
from collector.registry import CollectorRegistry
from collector.windsurf import WindsurfUsageCollector
from tests.test_generator import extract_pdf_texts


def _build_temp_registry(home: Path) -> CollectorRegistry:
    return CollectorRegistry(
        {
            "antigravity": AntigravityUsageCollector(antigravity_dir=home / ".gemini" / "antigravity"),
            "claude_code": ClaudeCodeUsageCollector(claude_dir=home / ".claude"),
            "codex": CodexUsageCollector(codex_dir=home / ".codex"),
            "gemini_cli": GeminiCLIUsageCollector(gemini_dir=home / ".gemini"),
            "cursor": CursorUsageCollector(cursor_dir=home / ".cursor"),
            "windsurf": WindsurfUsageCollector(
                codeium_windsurf_dir=home / ".codeium" / "windsurf",
                dot_windsurf_dir=home / ".windsurf",
            ),
        }
    )


class TestMCPAndCLIPhase7(unittest.TestCase):
    """Test local MCP JSON-RPC protocol and Phase 7 universal CLI commands."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.ws = self.root / "workspace"
        self.out_dir = self.root / "receipts"
        self.home.mkdir(parents=True, exist_ok=True)
        self.ws.mkdir(parents=True, exist_ok=True)
        self.runner = CliRunner()

        # Seed isolated Claude Code + Codex fixtures
        cproj = self.home / ".claude" / "projects" / "ws"
        cproj.mkdir(parents=True, exist_ok=True)
        (cproj / "cc-demo.jsonl").write_text(
            json.dumps(
                {
                    "type": "assistant",
                    "sessionId": "cc-demo",
                    "cwd": str(self.ws),
                    "timestamp": "2026-11-11T14:00:00Z",
                    "message": {
                        "id": "msg_cc_1",
                        "model": "claude-sonnet-4-6",
                        "usage": {"input_tokens": 2500, "output_tokens": 500, "cache_read_input_tokens": 10000},
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )

        cdx_dir = self.home / ".codex" / "sessions" / "2026" / "11" / "11"
        cdx_dir.mkdir(parents=True, exist_ok=True)
        (cdx_dir / "rollout-demo.jsonl").write_text(
            "\n".join(
                json.dumps(x)
                for x in [
                    {
                        "timestamp": "2026-11-11T14:05:00Z",
                        "type": "session_meta",
                        "payload": {"id": "cdx-demo", "cwd": str(self.ws)},
                    },
                    {
                        "timestamp": "2026-11-11T14:05:01Z",
                        "type": "turn_context",
                        "payload": {"cwd": str(self.ws), "model": "gpt-4.1"},
                    },
                    {
                        "timestamp": "2026-11-11T14:05:02Z",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {
                                "last_token_usage": {
                                    "input_tokens": 4000,
                                    "cached_input_tokens": 1000,
                                    "output_tokens": 250,
                                }
                            },
                        },
                    },
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_mcp_stdio_protocol_and_tools(self):
        """MCP server responds cleanly to initialize, tools/list, and all 3 billing tools."""
        registry = _build_temp_registry(self.home)
        server = LocalMCPServer(collector_registry=registry)

        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "list_agent_sessions", "arguments": {"workspace_path": str(self.ws)}},
            },
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "generate_agent_receipt",
                    "arguments": {"workspace_path": str(self.ws), "output_dir": str(self.out_dir)},
                },
            },
        ]
        stdin_buf = io.StringIO("\n".join(json.dumps(r) for r in requests) + "\n")
        stdout_buf = io.StringIO()
        server.serve_streams(stdin=stdin_buf, stdout=stdout_buf)

        responses = [json.loads(line) for line in stdout_buf.getvalue().strip().splitlines()]
        self.assertEqual(len(responses), 4)  # notification intentionally produces no response
        self.assertEqual(responses[0]["result"]["serverInfo"]["name"], "agent-token-receipt")

        tool_names = [t["name"] for t in responses[1]["result"]["tools"]]
        self.assertEqual(
            tool_names,
            ["list_agent_sessions", "get_agent_usage", "generate_agent_receipt"],
        )

        list_payload = json.loads(responses[2]["result"]["content"][0]["text"])
        self.assertEqual(list_payload["count"], 2)

        gen_payload = json.loads(responses[3]["result"]["content"][0]["text"])
        self.assertTrue(gen_payload["generated"])
        self.assertTrue(Path(gen_payload["pdf_path"]).is_file())
        self.assertEqual(gen_payload["input_plus_output_tokens"], 2500 + 500 + 3000 + 250)

    def test_cli_install_confirmation_uninstall_agents_doctor(self):
        """CLI install asks permission, installs cleanly with --yes, verifies via doctor, and uninstalls."""
        installer_factory = lambda *a, **kw: UniversalInstaller(
            home_dir=self.home, probe_path_binaries=False
        )
        registry_factory = lambda *a, **kw: _build_temp_registry(self.home)

        with patch("cli.main.UniversalInstaller", side_effect=installer_factory), patch(
            "cli.main.CollectorRegistry", side_effect=registry_factory
        ):
            # Agents listing
            res_agents = self.runner.invoke(cli, ["agents", "--workspace", str(self.ws)])
            self.assertEqual(res_agents.exit_code, 0)
            self.assertIn("Claude Code [claude_code]", res_agents.output)
            self.assertIn("OpenAI Codex [codex]", res_agents.output)
            self.assertIn("$agent-billing", res_agents.output)

            # Interactive install declined ('n') leaves filesystem untouched
            res_decline = self.runner.invoke(
                cli,
                ["install", "--scope", "global", "--workspace", str(self.ws)],
                input="n\n",
            )
            self.assertEqual(res_decline.exit_code, 0)
            self.assertIn("Installation cancelled by user", res_decline.output)
            self.assertFalse((self.home / ".claude" / "skills" / "agent-billing" / "SKILL.md").exists())

            # Install with --yes installs Claude Code and Codex skills
            res_yes = self.runner.invoke(
                cli,
                ["install", "--scope", "global", "--workspace", str(self.ws), "--yes"],
            )
            self.assertEqual(res_yes.exit_code, 0)
            self.assertIn("[INSTALLED]", res_yes.output)
            self.assertTrue((self.home / ".claude" / "skills" / "agent-billing" / "SKILL.md").is_file())
            self.assertTrue((self.home / ".codex" / "skills" / "agent-billing" / "SKILL.md").is_file())

            # Doctor passes and reports installed commands
            res_doc = self.runner.invoke(cli, ["doctor", "--workspace", str(self.ws)])
            self.assertEqual(res_doc.exit_code, 0)
            self.assertIn("Pricing Catalogue:  OK", res_doc.output)
            self.assertIn("installed", res_doc.output)

            # Uninstall with --yes removes installed files
            res_un = self.runner.invoke(
                cli,
                ["uninstall", "--scope", "global", "--workspace", str(self.ws), "--yes"],
            )
            self.assertEqual(res_un.exit_code, 0)
            self.assertIn("[REMOVED]", res_un.output)
            self.assertFalse((self.home / ".claude" / "skills" / "agent-billing" / "SKILL.md").exists())

    def test_cli_multi_agent_generate_and_cursor_unavailable_receipt(self):
        """CLI generate --workspace --all-agents merges logs and handles Cursor-only unavailability cleanly."""
        registry_factory = lambda *a, **kw: _build_temp_registry(self.home)

        with patch("cli.main.CollectorRegistry", side_effect=registry_factory):
            res_sess = self.runner.invoke(
                cli, ["sessions", "--all-agents", "--workspace", str(self.ws)]
            )
            self.assertEqual(res_sess.exit_code, 0)
            self.assertIn("Claude Code", res_sess.output)
            self.assertIn("OpenAI Codex", res_sess.output)

            res_gen = self.runner.invoke(
                cli,
                [
                    "generate",
                    "--workspace",
                    str(self.ws),
                    "--all-agents",
                    "--non-interactive",
                    "-o",
                    str(self.out_dir),
                ],
            )
            self.assertEqual(res_gen.exit_code, 0)
            self.assertIn("Claude Code", res_gen.output)
            self.assertIn("OpenAI Codex", res_gen.output)
            pdfs = list(self.out_dir.glob("*.pdf"))
            self.assertEqual(len(pdfs), 1)

            # Explicit Cursor-only receipt produces honest Unavailable telemetry PDF without fake numbers
            res_cur = self.runner.invoke(
                cli,
                [
                    "generate",
                    "--workspace",
                    str(self.ws),
                    "--agent",
                    "cursor",
                    "--non-interactive",
                    "-o",
                    str(self.out_dir),
                ],
            )
            self.assertEqual(res_cur.exit_code, 0)
            self.assertIn("Cursor", res_cur.output)
            self.assertIn("Unavailable", res_cur.output)
            latest_pdf = sorted(self.out_dir.glob("*.pdf"), key=lambda p: p.stat().st_mtime)[-1]
            cur_texts = "\n".join(extract_pdf_texts(latest_pdf.read_bytes()))
            self.assertIn("UNAVAILABLE TELEMETRY", cur_texts)
            self.assertIn("Cursor", cur_texts)

    def test_cli_all_agents_session_prefix_works_outside_session_workspace(self):
        """Regression test: --all-agents --session <prefix> works even when CWD differs from session workspace."""
        other_cwd = self.root / "unrelated_cwd"
        other_cwd.mkdir(parents=True, exist_ok=True)
        runner = CliRunner()
        with patch("cli.main.CollectorRegistry", return_value=_build_temp_registry(self.home)), patch(
            "cli.main.Path.cwd", return_value=other_cwd
        ):
            res = runner.invoke(
                cli,
                [
                    "generate",
                    "--all-agents",
                    "--session",
                    "cc-d",
                    "--non-interactive",
                    "-o",
                    str(self.out_dir),
                ],
            )
            self.assertEqual(res.exit_code, 0, msg=res.output)
            self.assertIn("Claude Code", res.output)
            self.assertIn("Claude Sonnet 4.6", res.output)
            self.assertIn("3,000", res.output)
            self.assertIn("$0.0180 USD", res.output)
            pdfs = list(self.out_dir.glob("*.pdf"))
            self.assertGreaterEqual(len(pdfs), 1)


if __name__ == "__main__":
    unittest.main()

