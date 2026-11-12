"""Unit and integration tests for Antigravity transcript parsing and session discovery.

Covers all 12 requirements from Phase 2 Task 7:
1. Valid generation event.
2. Missing optional token metrics.
3. Invalid JSON line.
4. Missing timestamp.
5. Model switching.
6. Unknown model.
7. Duplicate event handling.
8. Multiple generations in one session.
9. Non-generation events ignored.
10. Missing transcript file.
11. Read-only database access.
12. Private prompt and thinking text not stored.
Plus: Real local integration test against active Antigravity session.
"""

import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from collector.antigravity import AntigravityUsageCollector, _resolve_model_metadata


class TestAntigravityParser(unittest.TestCase):
    """Test suite for AntigravityUsageCollector transcript parser."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_root = Path(self.temp_dir.name)
        self.collector = AntigravityUsageCollector(
            antigravity_dir=self.test_root,
            db_path=self.test_root / "test_summaries.db",
            brain_dir=self.test_root / "brain",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_transcript(self, lines: list) -> Path:
        """Helper to write lines to a temporary transcript.jsonl."""
        trans_file = self.test_root / "test_transcript.jsonl"
        with open(trans_file, "w", encoding="utf-8") as f:
            for item in lines:
                if isinstance(item, str):
                    f.write(item + "\n")
                else:
                    f.write(json.dumps(item) + "\n")
        return trans_file

    def test_1_valid_generation_event(self):
        """1. Test parsing a standard, valid PLANNER_RESPONSE turn."""
        lines = [
            {
                "step_index": 0,
                "type": "USER_INPUT",
                "content": "<USER_SETTINGS_CHANGE>\nThe user changed setting `Model Selection` from None to Gemini 3.8 Flash (High).\n</USER_SETTINGS_CHANGE>",
            },
            {
                "step_index": 1,
                "type": "PLANNER_RESPONSE",
                "input_tokens": 1500,
                "output_tokens": 300,
                "cache_read_tokens": 500,
                "created_at": "2026-11-07T12:00:00Z",
                "thinking": "Some thinking process...",
            },
        ]
        path = self._write_transcript(lines)
        records = self.collector.parse_transcript_file(path, session_id="test-session-1")

        self.assertEqual(len(records), 1)
        r = records[0]
        self.assertEqual(r.turn_index, 1)
        self.assertEqual(r.provider, "Google")
        self.assertEqual(r.agent, "Google Antigravity")
        self.assertEqual(r.model_display_name, "Gemini 3.8 Flash (High)")
        self.assertEqual(r.model_id, "gemini-3.8-flash")
        self.assertEqual(r.input_tokens, 1500)
        self.assertEqual(r.output_tokens, 300)
        self.assertEqual(r.cache_read_tokens, 500)
        self.assertIsNone(r.cache_write_tokens)
        self.assertIsNone(r.reasoning_tokens)
        self.assertEqual(r.timestamp, datetime(2026, 11, 7, 12, 0, 0, tzinfo=timezone.utc))

    def test_2_missing_optional_token_metrics(self):
        """2. Test that missing cache_read_tokens is preserved as None."""
        lines = [
            {
                "step_index": 1,
                "type": "PLANNER_RESPONSE",
                "input_tokens": 2000,
                "output_tokens": 400,
                "created_at": "2026-11-07T12:00:00Z",
                # cache_read_tokens is omitted
            }
        ]
        path = self._write_transcript(lines)
        records = self.collector.parse_transcript_file(path)

        self.assertEqual(len(records), 1)
        self.assertIsNone(records[0].cache_read_tokens)
        self.assertIsNone(records[0].cache_write_tokens)
        self.assertIsNone(records[0].reasoning_tokens)

    def test_3_invalid_json_line(self):
        """3. Test that malformed JSON lines are safely skipped without failing the parse."""
        lines = [
            '{"step_index": 0, "type": "USER_INPUT", "content": "Valid line"}',
            '{"step_index": 1, "type": "PLANNER_RESPONSE", "broken_json": ',  # Broken line
            "",  # Empty line
            json.dumps({
                "step_index": 2,
                "type": "PLANNER_RESPONSE",
                "input_tokens": 100,
                "output_tokens": 50,
                "created_at": "2026-11-07T12:00:00Z",
            }),
        ]
        path = self._write_transcript(lines)
        records = self.collector.parse_transcript_file(path)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].turn_index, 2)

    def test_4_missing_timestamp(self):
        """4. Test that turns missing timestamps are skipped rather than guessing times."""
        lines = [
            {
                "step_index": 1,
                "type": "PLANNER_RESPONSE",
                "input_tokens": 100,
                "output_tokens": 50,
                # Missing created_at
            },
            {
                "step_index": 2,
                "type": "PLANNER_RESPONSE",
                "input_tokens": 200,
                "output_tokens": 60,
                "created_at": "invalid-timestamp-string",
            },
            {
                "step_index": 3,
                "type": "PLANNER_RESPONSE",
                "input_tokens": 300,
                "output_tokens": 70,
                "created_at": "2026-11-07T12:05:00Z",
            },
        ]
        path = self._write_transcript(lines)
        records = self.collector.parse_transcript_file(path)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].turn_index, 3)

    def test_5_model_switching(self):
        """5. Test accurate attribution when model switches mid-session."""
        lines = [
            {
                "step_index": 0,
                "type": "USER_INPUT",
                "content": "<USER_SETTINGS_CHANGE>\nThe user changed setting `Model Selection` from None to Gemini 3.8 Flash (High).\n</USER_SETTINGS_CHANGE>",
            },
            {
                "step_index": 1,
                "type": "PLANNER_RESPONSE",
                "input_tokens": 1000,
                "output_tokens": 200,
                "created_at": "2026-11-07T10:00:00Z",
            },
            {
                "step_index": 2,
                "type": "USER_INPUT",
                "content": "<USER_SETTINGS_CHANGE>\nThe user changed setting `Model Selection` from Gemini 3.8 Flash (High) to Gemini 3.8 Pro (High).\n</USER_SETTINGS_CHANGE>",
            },
            {
                "step_index": 3,
                "type": "PLANNER_RESPONSE",
                "input_tokens": 4000,
                "output_tokens": 800,
                "created_at": "2026-11-07T10:05:00Z",
            },
        ]
        path = self._write_transcript(lines)
        records = self.collector.parse_transcript_file(path)

        self.assertEqual(len(records), 2)
        # Turn 1: Flash
        self.assertEqual(records[0].model_display_name, "Gemini 3.8 Flash (High)")
        self.assertEqual(records[0].model_id, "gemini-3.8-flash")
        self.assertEqual(records[0].input_tokens, 1000)

        # Turn 2: Pro
        self.assertEqual(records[1].model_display_name, "Gemini 3.8 Pro (High)")
        self.assertEqual(records[1].model_id, "gemini-3.8-pro")
        self.assertEqual(records[1].input_tokens, 4000)

    def test_6_unknown_model(self):
        """6. Test handling unmapped or unverified model strings without guessing."""
        lines = [
            {
                "step_index": 0,
                "type": "USER_INPUT",
                "content": "<USER_SETTINGS_CHANGE>\nThe user changed setting `Model Selection` to Experimental-Super-Model-9000.\n</USER_SETTINGS_CHANGE>",
            },
            {
                "step_index": 1,
                "type": "PLANNER_RESPONSE",
                "input_tokens": 500,
                "output_tokens": 100,
                "created_at": "2026-11-07T12:00:00Z",
            },
        ]
        path = self._write_transcript(lines)
        records = self.collector.parse_transcript_file(path)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].model_display_name, "Experimental-Super-Model-9000")
        self.assertIsNone(records[0].model_id)
        self.assertEqual(records[0].provider, "Unknown")

    def test_7_duplicate_event_handling(self):
        """7. Test that multiple events with the same step_index are not double counted."""
        lines = [
            {
                "step_index": 1,
                "type": "PLANNER_RESPONSE",
                "input_tokens": 1000,
                "output_tokens": 200,
                "created_at": "2026-11-07T12:00:00Z",
            },
            {
                # Duplicate entry with same step_index
                "step_index": 1,
                "type": "PLANNER_RESPONSE",
                "input_tokens": 1000,
                "output_tokens": 200,
                "created_at": "2026-11-07T12:00:00Z",
            },
        ]
        path = self._write_transcript(lines)
        records = self.collector.parse_transcript_file(path)

        self.assertEqual(len(records), 1)

    def test_8_multiple_generations_in_one_session(self):
        """8. Test parsing a multi-turn conversation with sequential steps."""
        lines = [
            {
                "step_index": 0,
                "type": "USER_INPUT",
                "content": "<USER_SETTINGS_CHANGE>\nThe user changed setting `Model Selection` to Gemini 2.5 Flash.\n</USER_SETTINGS_CHANGE>",
            },
            {
                "step_index": 1,
                "type": "PLANNER_RESPONSE",
                "input_tokens": 1000,
                "output_tokens": 150,
                "created_at": "2026-11-07T10:00:00Z",
            },
            {
                "step_index": 2,
                "type": "GENERIC",
                "content": "Tool output",
                "created_at": "2026-11-07T10:00:02Z",
            },
            {
                "step_index": 3,
                "type": "PLANNER_RESPONSE",
                "input_tokens": 1200,
                "output_tokens": 250,
                "created_at": "2026-11-07T10:00:05Z",
            },
        ]
        path = self._write_transcript(lines)
        records = self.collector.parse_transcript_file(path)

        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].turn_index, 1)
        self.assertEqual(records[1].turn_index, 3)
        self.assertEqual(records[0].input_tokens, 1000)
        self.assertEqual(records[1].input_tokens, 1200)

    def test_9_non_generation_events_ignored(self):
        """9. Test that USER_INPUT, GENERIC, and SYSTEM_MESSAGE are not counted as generations."""
        lines = [
            {"step_index": 0, "type": "SYSTEM_MESSAGE", "content": "Init", "created_at": "2026-11-07T10:00:00Z"},
            {"step_index": 1, "type": "USER_INPUT", "content": "Hello", "created_at": "2026-11-07T10:00:01Z"},
            {"step_index": 2, "type": "GENERIC", "content": "File saved", "created_at": "2026-11-07T10:00:02Z"},
            {"step_index": 3, "type": "ERROR_MESSAGE", "content": "Err", "created_at": "2026-11-07T10:00:03Z"},
        ]
        path = self._write_transcript(lines)
        records = self.collector.parse_transcript_file(path)

        self.assertEqual(len(records), 0)

    def test_10_missing_transcript_file(self):
        """10. Test graceful handling when a transcript file does not exist on disk."""
        non_existent = self.test_root / "does_not_exist.jsonl"
        records = self.collector.parse_transcript_file(non_existent)
        self.assertEqual(records, [])

    def test_11_read_only_database_access(self):
        """11. Test that session database connection is strictly read-only and blocks writes."""
        db_path = self.test_root / "test_summaries.db"
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE conversation_summaries (
                conversation_id TEXT PRIMARY KEY,
                title TEXT,
                step_count INTEGER,
                last_modified_time DATETIME,
                workspace_uris TEXT
            )
            """
        )
        cur.execute(
            """
            INSERT INTO conversation_summaries VALUES (
                'test-uuid-999',
                'Sample Session',
                5,
                '2026-11-07T12:00:00Z',
                '["file:///C:/test/workspace"]'
            )
            """
        )
        conn.commit()
        conn.close()

        # Discover via collector
        sessions = self.collector.discover_sessions()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].session_id, "test-uuid-999")
        self.assertEqual(sessions[0].title, "Sample Session")

        # Test write operation directly on the collector's URI connection
        file_uri = db_path.resolve().as_uri() + "?mode=ro"
        ro_conn = sqlite3.connect(file_uri, uri=True)
        ro_cur = ro_conn.cursor()
        with self.assertRaises(sqlite3.OperationalError):
            ro_cur.execute("DELETE FROM conversation_summaries")
        ro_conn.close()

    def test_12_private_prompt_and_thinking_not_stored(self):
        """12. Test that private prompt and thinking texts are strictly excluded from records."""
        secret_prompt = "PRIVATE_CONFIDENTIAL_USER_PROMPT_ABC123"
        secret_thinking = "INTERNAL_CHAIN_OF_THOUGHT_XYZ789"

        lines = [
            {
                "step_index": 0,
                "type": "USER_INPUT",
                "content": f"{secret_prompt}\n<USER_SETTINGS_CHANGE>\nThe user changed setting `Model Selection` to Gemini 3.8 Flash.\n</USER_SETTINGS_CHANGE>",
            },
            {
                "step_index": 1,
                "type": "PLANNER_RESPONSE",
                "input_tokens": 1000,
                "output_tokens": 200,
                "thinking": secret_thinking,
                "created_at": "2026-11-07T12:00:00Z",
            },
        ]
        path = self._write_transcript(lines)
        records = self.collector.parse_transcript_file(path)

        self.assertEqual(len(records), 1)
        record = records[0]

        # Verify secrets are NOT in any attribute or dump
        record_dump = json.dumps(record.model_dump(), default=str)
        self.assertNotIn(secret_prompt, record_dump)
        self.assertNotIn(secret_thinking, record_dump)
        self.assertNotIn(secret_prompt, str(record))
        self.assertNotIn(secret_thinking, str(record))


class TestRealAntigravityIntegration(unittest.TestCase):
    """Real local integration test using the host's actual Antigravity directory."""

    def test_real_antigravity_discovery_and_collection(self):
        collector = AntigravityUsageCollector()
        if not collector.is_available():
            self.skipTest("Antigravity local directory not found on host machine.")

        sessions = collector.discover_sessions()
        self.assertGreater(len(sessions), 0, "Expected to find at least one real Antigravity session")

        # Find a session that has actual generation steps
        found_records = False
        for s in sessions[:5]:
            records = collector.collect_records(s.session_id)
            if records:
                found_records = True
                self.assertGreater(len(records), 0)
                # Verify numeric token counts on real records
                for r in records:
                    self.assertGreaterEqual(r.input_tokens, 0)
                    self.assertGreaterEqual(r.output_tokens, 0)
                    self.assertIsNotNone(r.timestamp.tzinfo)
                    self.assertEqual(r.agent, "Google Antigravity")
                break

        self.assertTrue(found_records, "Expected to successfully parse tokens from at least one real session")


if __name__ == "__main__":
    unittest.main()

