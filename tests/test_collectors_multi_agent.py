"""Synthetic unit & integration tests for Phase 7 multi-agent usage collectors and combined receipts."""

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from collector.antigravity import AntigravityUsageCollector
from collector.claude_code import ClaudeCodeUsageCollector
from collector.codex import CodexUsageCollector
from collector.cursor import CursorUsageCollector, _encode_cursor_workspace_slug
from collector.gemini_cli import GeminiCLIUsageCollector
from collector.registry import CollectorRegistry
from collector.windsurf import WindsurfUsageCollector
from core.aggregator import UsageAggregator
from generator.pdf import ReceiptPDFGenerator
from pricing.calculator import CostCalculator
from tests.test_generator import extract_pdf_texts


class TestMultiAgentCollectors(unittest.TestCase):
    """Verify read-only collection, deduplication, non-overlap, and unavailable platform honesty."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.workspace = self.root / "my-project"
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.other_workspace = self.root / "other-project"
        self.other_workspace.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_claude_code_deduplication_subagents_and_pricing(self):
        """Claude Code keeps latest snapshot per message.id, includes subagents, skips <synthetic>, and filters cwd."""
        claude_dir = self.root / ".claude"
        proj_dir = claude_dir / "projects" / "my-proj"
        sub_dir = proj_dir / "sess-cc-001" / "subagents"
        sub_dir.mkdir(parents=True, exist_ok=True)

        # Streaming duplicate msg_01 + final msg_01 + synthetic error + non-matching workspace
        root_events = [
            {"type": "ai-title", "sessionId": "sess-cc-001", "aiTitle": "Audit Claude Billing"},
            {
                "type": "assistant",
                "sessionId": "sess-cc-001",
                "cwd": str(self.workspace),
                "timestamp": "2026-11-11T10:00:01Z",
                "message": {
                    "id": "msg_01",
                    "model": "claude-sonnet-4-6",
                    "stop_reason": None,
                    "content": [{"type": "text", "text": "SECRET PROMPT NEVER READ"}],
                    "usage": {
                        "input_tokens": 1000,
                        "output_tokens": 10,
                        "cache_read_input_tokens": 5000,
                    },
                },
            },
            {
                "type": "assistant",
                "sessionId": "sess-cc-001",
                "cwd": str(self.workspace),
                "timestamp": "2026-11-11T10:00:05Z",
                "message": {
                    "id": "msg_01",
                    "model": "claude-sonnet-4-6",
                    "stop_reason": "end_turn",
                    "usage": {
                        "input_tokens": 1000,
                        "output_tokens": 200,
                        "cache_read_input_tokens": 5000,
                    },
                },
            },
            {
                "type": "assistant",
                "sessionId": "sess-cc-001",
                "cwd": str(self.workspace),
                "timestamp": "2026-11-11T10:00:06Z",
                "message": {
                    "id": "msg_syn",
                    "model": "<synthetic>",
                    "usage": {"input_tokens": 0, "output_tokens": 0},
                },
            },
        ]
        (proj_dir / "sess-cc-001.jsonl").write_text(
            "\n".join(json.dumps(e) for e in root_events) + "\n", encoding="utf-8"
        )

        # Subagent turn on claude-haiku-4-5-20251001
        sub_events = [
            {
                "type": "assistant",
                "sessionId": "sess-cc-001",
                "cwd": str(self.workspace),
                "timestamp": "2026-11-11T10:00:10Z",
                "message": {
                    "id": "msg_sub_01",
                    "model": "claude-haiku-4-5-20251001",
                    "usage": {
                        "input_tokens": 2000,
                        "output_tokens": 500,
                        "cache_read_input_tokens": 10000,
                    },
                },
            }
        ]
        (sub_dir / "agent-a1.jsonl").write_text(
            json.dumps(sub_events[0]) + "\n", encoding="utf-8"
        )

        # Unrelated workspace session
        (proj_dir / "sess-other.jsonl").write_text(
            json.dumps(
                {
                    "type": "assistant",
                    "sessionId": "sess-other",
                    "cwd": str(self.other_workspace),
                    "timestamp": "2026-11-11T11:00:00Z",
                    "message": {
                        "id": "msg_x",
                        "model": "claude-sonnet-4-6",
                        "usage": {"input_tokens": 999, "output_tokens": 99},
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )

        collector = ClaudeCodeUsageCollector(claude_dir=claude_dir)
        self.assertTrue(collector.is_available())
        sessions = collector.discover_sessions(workspace_path=str(self.workspace))
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].session_id, "sess-cc-001")
        self.assertEqual(sessions[0].title, "Audit Claude Billing")
        self.assertEqual(sessions[0].turn_count, 2)

        records = collector.collect_records("sess-cc-001")
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].model_id, "claude-sonnet-4-6")
        self.assertEqual(records[0].input_tokens, 1000)
        self.assertEqual(records[0].output_tokens, 200)
        self.assertEqual(records[0].cache_read_tokens, 5000)
        self.assertEqual(records[1].model_id, "claude-haiku-4-5")
        self.assertEqual(records[1].model_display_name, "Claude Haiku 4.5")

        receipt = UsageAggregator(CostCalculator()).build_receipt(records, session_id="sess-cc-001")
        self.assertEqual(receipt.pricing_status, "verified")
        # Sonnet: 1000*3/1M + 200*15/1M + 5000*0.3/1M = 0.003 + 0.003 + 0.0015 = 0.0075
        # Haiku:  2000*1/1M + 500*5/1M  + 10000*0.1/1M = 0.002 + 0.0025 + 0.001 = 0.0055
        self.assertEqual(receipt.estimated_api_cost_usd, Decimal("0.0130"))

    def test_codex_subtract_cached_dedup_and_unknown_model(self):
        """Codex subtracts cached_input_tokens from input_tokens, deduplicates snapshots, and leaves gpt-6-luna unpriced."""
        codex_dir = self.root / ".codex"
        rollout_dir = codex_dir / "sessions" / "2026" / "11" / "11"
        rollout_dir.mkdir(parents=True, exist_ok=True)

        (codex_dir / "session_index.jsonl").write_text(
            json.dumps({"id": "codex-001", "thread_name": "Codex Test Task"}) + "\n",
            encoding="utf-8",
        )

        events = [
            {
                "timestamp": "2026-11-11T12:00:00Z",
                "type": "session_meta",
                "payload": {"id": "codex-001", "timestamp": "2026-11-11T12:00:00Z", "cwd": str(self.workspace)},
            },
            {
                "timestamp": "2026-11-11T12:00:01Z",
                "type": "turn_context",
                "payload": {"cwd": str(self.workspace), "model": "gpt-5.4"},
            },
            {
                "timestamp": "2026-11-11T12:00:02Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "total_token_usage": {
                            "input_tokens": 14718,
                            "cached_input_tokens": 11008,
                            "output_tokens": 37,
                            "reasoning_output_tokens": 0,
                            "total_tokens": 14755,
                        },
                        "last_token_usage": {
                            "input_tokens": 14718,
                            "cached_input_tokens": 11008,
                            "cache_write_input_tokens": 0,
                            "output_tokens": 37,
                            "reasoning_output_tokens": 0,
                            "total_tokens": 14755,
                        },
                    },
                },
            },
            # Exact duplicate status snapshot (must NOT double count)
            {
                "timestamp": "2026-11-11T12:00:03Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "total_token_usage": {
                            "input_tokens": 14718,
                            "cached_input_tokens": 11008,
                            "output_tokens": 37,
                            "reasoning_output_tokens": 0,
                            "total_tokens": 14755,
                        },
                        "last_token_usage": {
                            "input_tokens": 14718,
                            "cached_input_tokens": 11008,
                            "output_tokens": 37,
                            "total_tokens": 14755,
                        },
                    },
                },
            },
            # Duplicate mirror event type (ignored)
            {
                "timestamp": "2026-11-11T12:00:03Z",
                "type": "token_usage_record",
                "payload": {"input_tokens": 14718, "output_tokens": 37},
            },
            {
                "timestamp": "2026-11-11T12:00:04Z",
                "type": "turn_context",
                "payload": {"cwd": str(self.workspace), "model": "gpt-6-luna"},
            },
            {
                "timestamp": "2026-11-11T12:00:05Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "total_token_usage": {
                            "input_tokens": 16718,
                            "cached_input_tokens": 12008,
                            "output_tokens": 137,
                            "reasoning_output_tokens": 20,
                            "total_tokens": 16855,
                        },
                        "last_token_usage": {
                            "input_tokens": 2000,
                            "cached_input_tokens": 1000,
                            "output_tokens": 100,
                            "reasoning_output_tokens": 20,
                            "total_tokens": 2100,
                        },
                    },
                },
            },
        ]
        (rollout_dir / "rollout-2026-11-11T12-00-00-codex-001.jsonl").write_text(
            "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
        )

        collector = CodexUsageCollector(codex_dir=codex_dir)
        sessions = collector.discover_sessions(workspace_path=str(self.workspace))
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].title, "Codex Test Task")
        self.assertEqual(sessions[0].turn_count, 2)

        records = collector.collect_records("codex-001")
        self.assertEqual(len(records), 2)
        # First turn: 14718 - 11008 = 3710 uncached input + 11008 cached
        self.assertEqual(records[0].input_tokens, 3710)
        self.assertEqual(records[0].cache_read_tokens, 11008)
        self.assertEqual(records[0].output_tokens, 37)
        self.assertEqual(records[0].model_id, "gpt-5.4")

        # Second turn: unknown model gpt-6-luna, 2000 - 1000 = 1000 uncached input, 20 reasoning
        self.assertEqual(records[1].input_tokens, 1000)
        self.assertEqual(records[1].cache_read_tokens, 1000)
        self.assertEqual(records[1].reasoning_tokens, 20)
        self.assertEqual(records[1].model_id, "gpt-6-luna")

        receipt = UsageAggregator(CostCalculator()).build_receipt(records, session_id="codex-001")
        by_model = {s.model_id: s for s in receipt.model_summaries}
        self.assertEqual(by_model["gpt-5.4"].pricing_status, "preview_estimate")
        self.assertIsNotNone(by_model["gpt-5.4"].estimated_api_cost_usd)
        self.assertEqual(by_model["gpt-6-luna"].pricing_status, "unavailable")
        self.assertIn("gpt-6-luna", by_model["gpt-6-luna"].pricing_notes or "")
        self.assertIsNone(by_model["gpt-6-luna"].estimated_api_cost_usd)

    def test_gemini_cli_jsonl_and_total_disambiguation(self):
        """Gemini CLI handles delta JSONL updates and disambiguates raw vs uncached input via total invariant."""
        gemini_dir = self.root / ".gemini"
        ws_hash = hashlib.sha256(str(self.workspace.resolve()).encode("utf-8")).hexdigest()
        chats_dir = gemini_dir / "tmp" / ws_hash / "chats"
        chats_dir.mkdir(parents=True, exist_ok=True)

        jsonl_lines = [
            {
                "sessionId": "gem-sess-1",
                "projectHash": ws_hash,
                "startTime": "2026-11-11T09:00:00Z",
            },
            # Case A: input=1000 ALREADY uncached (total = 1000 + 50 + 400 + 25 = 1475)
            {
                "id": "gmsg-1",
                "type": "gemini",
                "model": "gemini-2.5-flash",
                "timestamp": "2026-11-11T09:00:05Z",
                "tokens": {"input": 1000, "output": 50, "cached": 400, "thoughts": 25, "total": 1475},
            },
            # Case B: delta update with inclusive promptTokenCount (input=1400 includes cached=400; total = 1400 + 60 = 1460)
            {
                "id": "gmsg-2",
                "type": "gemini",
                "model": "gemini-2.5-flash",
                "timestamp": "2026-11-11T09:00:10Z",
                "tokens": {"input": 100, "output": 10, "cached": 0, "total": 110},
            },
            {
                "id": "gmsg-2",
                "type": "message_update",
                "timestamp": "2026-11-11T09:00:12Z",
                "tokens": {"input": 1400, "output": 60, "cached": 400, "thoughts": 0, "total": 1460},
            },
        ]
        (chats_dir / "session-gem-1.jsonl").write_text(
            "\n".join(json.dumps(x) for x in jsonl_lines) + "\n", encoding="utf-8"
        )

        collector = GeminiCLIUsageCollector(gemini_dir=gemini_dir)
        sessions = collector.discover_sessions(workspace_path=str(self.workspace))
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].turn_count, 2)

        records = collector.collect_records("gem-sess-1")
        self.assertEqual(records[0].input_tokens, 1000)
        self.assertEqual(records[0].cache_read_tokens, 400)
        self.assertEqual(records[0].reasoning_tokens, 25)
        self.assertEqual(records[1].input_tokens, 1000)  # 1400 - 400
        self.assertEqual(records[1].output_tokens, 60)

    def test_cursor_and_windsurf_report_unavailable_honestly(self):
        """Cursor discovers transcript metadata without inventing tokens; Windsurf stays unavailable."""
        cursor_dir = self.root / ".cursor"
        slug = _encode_cursor_workspace_slug(str(self.workspace))
        t_dir = cursor_dir / "projects" / slug / "agent-transcripts"
        t_dir.mkdir(parents=True, exist_ok=True)
        (t_dir / "cursor-tx-1234.jsonl").write_text(
            json.dumps({"role": "user", "message": {"content": "hello"}}) + "\n",
            encoding="utf-8",
        )

        cursor = CursorUsageCollector(cursor_dir=cursor_dir)
        self.assertTrue(cursor.is_available())
        self.assertFalse(cursor.supports_token_telemetry)
        sessions = cursor.discover_sessions(workspace_path=str(self.workspace))
        self.assertEqual(len(sessions), 1)
        self.assertEqual(cursor.collect_records("cursor-tx-1234"), [])

        windsurf_dir = self.root / ".codeium" / "windsurf"
        windsurf_dir.mkdir(parents=True, exist_ok=True)
        windsurf = WindsurfUsageCollector(codeium_windsurf_dir=windsurf_dir, dot_windsurf_dir=self.root / ".windsurf")
        self.assertTrue(windsurf.is_available())
        self.assertFalse(windsurf.supports_token_telemetry)
        self.assertEqual(windsurf.collect_records("any"), [])

    def test_combined_multi_agent_receipt_and_pdf_with_unavailable_cursor(self):
        """Combining Claude Code + Codex + unavailable Cursor produces one valid 80mm PDF receipt."""
        # Claude Code
        claude_dir = self.root / ".claude"
        cproj = claude_dir / "projects" / "ws"
        cproj.mkdir(parents=True, exist_ok=True)
        (cproj / "cc1.jsonl").write_text(
            json.dumps(
                {
                    "type": "assistant",
                    "sessionId": "cc1",
                    "cwd": str(self.workspace),
                    "timestamp": "2026-11-11T10:00:00Z",
                    "message": {
                        "id": "m1",
                        "model": "claude-sonnet-4-6",
                        "usage": {"input_tokens": 5000, "output_tokens": 1000, "cache_read_input_tokens": 20000},
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )

        # Codex
        codex_dir = self.root / ".codex"
        cdx_dir = codex_dir / "sessions" / "2026" / "11" / "11"
        cdx_dir.mkdir(parents=True, exist_ok=True)
        (cdx_dir / "rollout-1.jsonl").write_text(
            "\n".join(
                json.dumps(e)
                for e in [
                    {
                        "timestamp": "2026-11-11T10:05:00Z",
                        "type": "session_meta",
                        "payload": {"id": "cdx1", "cwd": str(self.workspace)},
                    },
                    {
                        "timestamp": "2026-11-11T10:05:01Z",
                        "type": "turn_context",
                        "payload": {"cwd": str(self.workspace), "model": "gpt-5"},
                    },
                    {
                        "timestamp": "2026-11-11T10:05:02Z",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {
                                "last_token_usage": {
                                    "input_tokens": 10000,
                                    "cached_input_tokens": 4000,
                                    "output_tokens": 500,
                                }
                            },
                        },
                    },
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        # Cursor active transcript marker (server-side tokens unavailable)
        cursor_dir = self.root / ".cursor"
        slug = _encode_cursor_workspace_slug(str(self.workspace))
        ct_dir = cursor_dir / "projects" / slug / "agent-transcripts"
        ct_dir.mkdir(parents=True, exist_ok=True)
        (ct_dir / "cur1.jsonl").write_text('{"role":"user"}\n', encoding="utf-8")

        registry = CollectorRegistry(
            {
                "antigravity": AntigravityUsageCollector(antigravity_dir=self.root / "missing-ag"),
                "claude_code": ClaudeCodeUsageCollector(claude_dir=claude_dir),
                "codex": CodexUsageCollector(codex_dir=codex_dir),
                "gemini_cli": GeminiCLIUsageCollector(gemini_dir=self.root / "missing-gem"),
                "cursor": CursorUsageCollector(cursor_dir=cursor_dir),
                "windsurf": WindsurfUsageCollector(
                    codeium_windsurf_dir=self.root / "missing-ws",
                    dot_windsurf_dir=self.root / "missing-dotws",
                ),
            }
        )

        res = registry.collect_workspace_usage(workspace_path=str(self.workspace))
        self.assertEqual(len(res.records), 2)
        self.assertEqual(len(res.unavailable_agents), 1)
        self.assertEqual(res.unavailable_agents[0]["agent"], "Cursor")

        receipt = UsageAggregator(CostCalculator()).build_receipt(
            records=res.records,
            session_id="ws-multi",
            session_title="Multi-Agent Workspace",
            unavailable_agents=res.unavailable_agents,
        )
        pdf_path = ReceiptPDFGenerator(output_dir=self.root / "out").generate(receipt)
        self.assertTrue(pdf_path.is_file())
        pdf_texts = "\n".join(extract_pdf_texts(pdf_path.read_bytes()))
        self.assertIn("3 (Claude Code, Cursor, OpenAI Codex)", pdf_texts)
        self.assertIn("UNAVAILABLE TELEMETRY", pdf_texts)
        self.assertIn("Claude Sonnet 4.6", pdf_texts)
        self.assertIn("GPT-5", pdf_texts)

    def test_antigravity_file_uri_normalization_preserves_posix_and_windows_roots(self):
        """Antigravity URI normalization preserves drive letters on Windows and leading '/' on POSIX."""
        from unittest.mock import patch
        from collector.antigravity import _normalize_path

        win_resolved = _normalize_path("file:///c%3A/Users/Test/my%20project")
        self.assertTrue("users" in win_resolved and "my project" in win_resolved)

        with patch("collector.antigravity.Path") as mock_path:
            mock_path.side_effect = lambda p: Path(p)
            # Directly verify parsed POSIX string passed to Path lacks dropped leading slash
            _normalize_path("file:///home/alice/my%20app")
            called_arg = mock_path.call_args[0][0]
            self.assertTrue(called_arg.startswith("/home/alice/my app"))

    def test_antigravity_collect_records_missing_session_no_warning(self):
        """Missing Antigravity session IDs return [] quietly without spurious transcript warnings."""
        ag_dir = self.root / ".gemini" / "antigravity"
        (ag_dir / "brain").mkdir(parents=True, exist_ok=True)
        collector = AntigravityUsageCollector(antigravity_dir=ag_dir)
        with self.assertNoLogs("collector.antigravity", level="WARNING"):
            records = collector.collect_records("claude-session-id-not-in-antigravity")
        self.assertEqual(records, [])


if __name__ == "__main__":
    unittest.main()
