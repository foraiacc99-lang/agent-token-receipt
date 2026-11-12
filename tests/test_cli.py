"""Automated unit and integration tests for Agent Token Receipt CLI.

Verifies all required scenarios cleanly using an isolated temporary Antigravity
environment fixture so tests pass identically on any machine without local logs:
1. CLI help (--help)
2. Version command (--version)
3. Session listing (sessions)
4. Empty session list
5. Valid interactive session selection
6. Invalid interactive session selection
7. Direct session ID selection (--session)
8. Custom output directory (--output)
9. Missing Antigravity environment handling
10. PDF generation through CLI
11. Existing receipt collision avoidance
12. Friendly error handling for non-existent session
13. Non-interactive mode requirement
14. Ambiguous session prefix rejection
15. Path-traversal session identifier rejection
16. Non-interactive flag precedence when Antigravity is absent
17. Graceful error handling when reading transcript fails (OSError)
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from cli.main import __version__, cli
from collector.antigravity import AntigravityUsageCollector
from collector.base import SessionDescriptor


def _build_temp_antigravity_env(root: Path, workspace_path: Path) -> Path:
    """Create a realistic, isolated read-only Antigravity database + transcript fixture."""
    ag_dir = root / "antigravity"
    brain_dir = ag_dir / "brain"
    ag_dir.mkdir(parents=True, exist_ok=True)
    brain_dir.mkdir(parents=True, exist_ok=True)

    db_path = ag_dir / "conversation_summaries.db"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE conversation_summaries (
            conversation_id TEXT PRIMARY KEY,
            title TEXT,
            step_count INTEGER,
            last_modified_time TEXT,
            workspace_uris TEXT
        )
        """
    )

    ws_uri = workspace_path.resolve().as_uri()
    sessions = [
        (
            "demo-session-99d16623",
            "Convert Demo Layout to App",
            4,
            "2026-11-10T18:50:37Z",
            json.dumps([ws_uri]),
        ),
        (
            "prefix-dup-0001",
            "Ambiguous Candidate One",
            1,
            "2026-11-10T17:00:00Z",
            json.dumps([ws_uri]),
        ),
        (
            "prefix-dup-0002",
            "Ambiguous Candidate Two",
            1,
            "2026-11-10T16:00:00Z",
            json.dumps([ws_uri]),
        ),
    ]
    cur.executemany(
        "INSERT INTO conversation_summaries VALUES (?, ?, ?, ?, ?)",
        sessions,
    )
    conn.commit()
    conn.close()

    # Populate synthetic multi-model JSONL transcript for primary test session
    logs_dir = brain_dir / "demo-session-99d16623" / ".system_generated" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    events = [
        {
            "step_index": 0,
            "type": "USER_INPUT",
            "created_at": "2026-11-10T18:45:00Z",
            "content": "<USER_SETTINGS_CHANGE> Changed Model Selection from None to Gemini 3.8 Flash (High) </USER_SETTINGS_CHANGE>",
        },
        {
            "step_index": 1,
            "type": "PLANNER_RESPONSE",
            "created_at": "2026-11-10T18:46:10Z",
            "input_tokens": 10000,
            "output_tokens": 1000,
            "cache_read_tokens": 50000,
        },
        {
            "step_index": 2,
            "type": "USER_INPUT",
            "created_at": "2026-11-10T18:47:00Z",
            "content": "<USER_SETTINGS_CHANGE> Changed Model Selection from Gemini 3.8 Flash (High) to Claude Opus 4.6 </USER_SETTINGS_CHANGE>",
        },
        {
            "step_index": 3,
            "type": "PLANNER_RESPONSE",
            "created_at": "2026-11-10T18:48:30Z",
            "input_tokens": 5000,
            "output_tokens": 500,
            "cache_read_tokens": 20000,
        },
    ]
    with open(logs_dir / "transcript.jsonl", "w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")

    return ag_dir


class TestAgentTokenReceiptCLI(unittest.TestCase):
    """Test suite covering the complete CLI surface."""

    def setUp(self):
        self.runner = CliRunner()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_temp = Path(self.temp_dir.name)
        self.output_path = self.base_temp / "receipts"
        self.output_path.mkdir(parents=True, exist_ok=True)
        self.mock_ag_dir = _build_temp_antigravity_env(
            self.base_temp / "mock_home", Path.cwd()
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def _collector_factory(self, *args, **kwargs):
        return AntigravityUsageCollector(antigravity_dir=self.mock_ag_dir)

    def test_01_cli_help(self):
        """Test that --help displays app name, tagline, commands, and examples."""
        result = self.runner.invoke(cli, ["--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("AGENT TOKEN RECEIPT", result.output)
        self.assertIn("Every token has a receipt.", result.output)
        self.assertIn("sessions", result.output)
        self.assertIn("generate", result.output)
        self.assertIn("Examples:", result.output)
        self.assertIn("agent-token-receipt generate", result.output)

    def test_02_version_command(self):
        """Test that --version displays the exact version."""
        result = self.runner.invoke(cli, ["--version"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn(f"agent-token-receipt, version {__version__}", result.output)

    def test_03_session_listing(self):
        """Test listing discovered sessions."""
        mock_descriptor = SessionDescriptor(
            session_id="mock-session-01",
            agent="Google Antigravity",
            provider="Google",
            title="Authentication System Audit",
            last_active_time=datetime(2026, 11, 10, 12, 0, 0, tzinfo=timezone.utc),
            turn_count=42,
            workspace_path="/path/to/project",
        )

        with patch("cli.main.AntigravityUsageCollector") as mock_col_cls:
            mock_inst = MagicMock()
            mock_col_cls.return_value = mock_inst
            mock_inst.is_available.return_value = True
            mock_inst.discover_sessions.return_value = [mock_descriptor]

            result = self.runner.invoke(cli, ["sessions", "--all-workspaces"])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("AGENT TOKEN RECEIPT — SESSIONS", result.output)
            self.assertIn("Authentication System Audit", result.output)
            self.assertIn("mock-session-01", result.output)
            self.assertIn("42 recorded steps", result.output)

    def test_04_empty_session_list(self):
        """Test friendly messaging when no sessions exist."""
        with patch("cli.main.AntigravityUsageCollector") as mock_col_cls:
            mock_inst = MagicMock()
            mock_col_cls.return_value = mock_inst
            mock_inst.is_available.return_value = True
            mock_inst.discover_sessions.return_value = []

            result = self.runner.invoke(cli, ["sessions", "--all-workspaces"])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("No Antigravity sessions found in local records.", result.output)

    def test_05_valid_interactive_selection(self):
        """Test interactive session selection by choosing number 1."""
        with patch("cli.main.AntigravityUsageCollector", side_effect=self._collector_factory):
            result = self.runner.invoke(
                cli,
                ["generate", "-o", str(self.output_path)],
                input="1\n",
            )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Discovering Antigravity sessions...", result.output)
        self.assertIn("Selected:", result.output)
        self.assertIn("SUCCESS!", result.output)
        self.assertIn("Your thermal receipt has been generated:", result.output)

        generated_pdfs = list(self.output_path.glob("*.pdf"))
        self.assertEqual(len(generated_pdfs), 1)

    def test_06_invalid_interactive_selection(self):
        """Test user entering an out-of-bounds choice interactively."""
        with patch("cli.main.AntigravityUsageCollector", side_effect=self._collector_factory):
            result = self.runner.invoke(
                cli,
                ["generate", "-o", str(self.output_path)],
                input="999\n",
            )
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Error: Invalid selection '999'", result.output)

    def test_07_direct_session_selection(self):
        """Test passing session ID directly via -s option."""
        with patch("cli.main.AntigravityUsageCollector", side_effect=self._collector_factory):
            result = self.runner.invoke(
                cli,
                ["generate", "-s", "demo-session-99d16623", "-o", str(self.output_path)],
            )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("SUCCESS!", result.output)
        self.assertIn("Convert Demo Layout to App", result.output)
        self.assertIn("Total Turns:           2", result.output)
        self.assertIn("Input + Output Tokens: 16,500", result.output)
        self.assertIn("Total Cache-Read:      70,000", result.output)

    def test_08_custom_output_directory(self):
        """Test that custom directory is created and receipt is written inside it."""
        custom_sub = self.output_path / "deep" / "nested" / "receipts"
        self.assertFalse(custom_sub.exists())

        with patch("cli.main.AntigravityUsageCollector", side_effect=self._collector_factory):
            result = self.runner.invoke(
                cli,
                ["generate", "-s", "demo-session", "-o", str(custom_sub)],
            )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertTrue(custom_sub.exists())
        pdfs = list(custom_sub.glob("*.pdf"))
        self.assertEqual(len(pdfs), 1)

    def test_09_missing_antigravity_data(self):
        """Test friendly error message when Antigravity environment is absent."""
        missing_dir = self.base_temp / "does_not_exist"
        with patch(
            "cli.main.AntigravityUsageCollector",
            side_effect=lambda *a, **kw: AntigravityUsageCollector(antigravity_dir=missing_dir),
        ):
            res_sess = self.runner.invoke(cli, ["sessions"])
            self.assertEqual(res_sess.exit_code, 0)
            self.assertIn("Antigravity local environment not detected.", res_sess.output)

            res_gen = self.runner.invoke(cli, ["generate"])
            self.assertEqual(res_gen.exit_code, 1)
            self.assertIn("Error: Antigravity local environment not detected.", res_gen.output)

    def test_10_pdf_generation_through_cli(self):
        """Test generated PDF file integrity through CLI."""
        with patch("cli.main.AntigravityUsageCollector", side_effect=self._collector_factory):
            result = self.runner.invoke(
                cli,
                ["generate", "-s", "demo-session", "-o", str(self.output_path)],
            )
        self.assertEqual(result.exit_code, 0, result.output)
        pdf_file = list(self.output_path.glob("*.pdf"))[0]
        data = pdf_file.read_bytes()
        self.assertTrue(data.startswith(b"%PDF-"), "Generated file must be a valid PDF")
        self.assertGreater(len(data), 1000)

    def test_11_filename_collision_avoidance(self):
        """Test that generating multiple receipts does not overwrite existing files."""
        with patch("cli.main.AntigravityUsageCollector", side_effect=self._collector_factory):
            res1 = self.runner.invoke(
                cli,
                ["generate", "-s", "demo-session", "-o", str(self.output_path)],
            )
            self.assertEqual(res1.exit_code, 0, res1.output)

            res2 = self.runner.invoke(
                cli,
                ["generate", "-s", "demo-session", "-o", str(self.output_path)],
            )
            self.assertEqual(res2.exit_code, 0, res2.output)

        pdfs = sorted(list(self.output_path.glob("*.pdf")))
        self.assertGreaterEqual(len(pdfs), 2)
        self.assertNotEqual(pdfs[0].name, pdfs[1].name)

    def test_12_friendly_error_nonexistent_session(self):
        """Test clean error when session ID does not exist."""
        with patch("cli.main.AntigravityUsageCollector", side_effect=self._collector_factory):
            result = self.runner.invoke(
                cli,
                ["generate", "-s", "completely_fake_uuid_12345", "-o", str(self.output_path)],
            )
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Session 'completely_fake_uuid_12345' was not found in Antigravity records.", result.output)
        self.assertNotIn("Traceback (most recent call last):", result.output)

    def test_13_non_interactive_without_session(self):
        """Test non-interactive mode requirement."""
        with patch("cli.main.AntigravityUsageCollector", side_effect=self._collector_factory):
            result = self.runner.invoke(
                cli,
                ["generate", "--non-interactive"],
            )
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Error: --session is required when running in non-interactive mode.", result.output)

    def test_14_ambiguous_session_prefix(self):
        """Test clean error when --session prefix matches multiple sessions."""
        with patch("cli.main.AntigravityUsageCollector", side_effect=self._collector_factory):
            result = self.runner.invoke(
                cli,
                ["generate", "-s", "prefix-dup", "-o", str(self.output_path)],
            )
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Ambiguous session prefix 'prefix-dup'", result.output)
        self.assertIn("prefix-dup-0001", result.output)
        self.assertIn("prefix-dup-0002", result.output)

    def test_15_invalid_session_path_traversal(self):
        """Test rejection of path traversal sequences in --session."""
        with patch("cli.main.AntigravityUsageCollector", side_effect=self._collector_factory):
            result = self.runner.invoke(
                cli,
                ["generate", "-s", "../outside", "-o", str(self.output_path)],
            )
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Invalid session identifier '../outside'", result.output)

    def test_16_non_interactive_without_session_missing_env(self):
        """Test option validation happens cleanly even if Antigravity directory is absent."""
        missing_dir = self.base_temp / "absent"
        with patch(
            "cli.main.AntigravityUsageCollector",
            side_effect=lambda *a, **kw: AntigravityUsageCollector(antigravity_dir=missing_dir),
        ):
            result = self.runner.invoke(cli, ["generate", "--non-interactive"])
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Error: --session is required when running in non-interactive mode.", result.output)

    def test_17_unreadable_transcript_oserror(self):
        """Test graceful handling when transcript opening raises OSError."""
        import builtins
        real_open = builtins.open

        def fail_on_transcript(file, *args, **kwargs):
            if "transcript.jsonl" in str(file):
                raise PermissionError("Access denied")
            return real_open(file, *args, **kwargs)

        with patch("cli.main.AntigravityUsageCollector", side_effect=self._collector_factory):
            with patch("builtins.open", side_effect=fail_on_transcript):
                result = self.runner.invoke(
                    cli,
                    ["generate", "-s", "demo-session-99d16623", "-o", str(self.output_path)],
                )
        self.assertEqual(result.exit_code, 1)
        self.assertIn("contains no generative turns or readable usage records", result.output)
        self.assertNotIn("Traceback (most recent call last):", result.output)


if __name__ == "__main__":
    unittest.main()
