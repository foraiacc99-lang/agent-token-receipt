"""Unit tests for Phase 3 aggregation engine (core/aggregator.py).

Covers:
1. Single-model aggregation.
2. Multiple-model aggregation (mid-session switches).
3. Multiple-agent aggregation.
4. Multiple-session aggregation.
5. Unknown model handling.
6. Missing token metrics.
7. Cache-read accounting.
8. Prevention of double-counting.
15. Empty session handling.
"""

import unittest
from datetime import datetime, timezone
from decimal import Decimal

from core.models import CanonicalUsageRecord
from core.aggregator import UsageAggregator


class TestUsageAggregator(unittest.TestCase):
    """Test suite for UsageAggregator."""

    def setUp(self):
        self.aggregator = UsageAggregator()
        self.t1 = datetime(2026, 11, 9, 10, 0, 0, tzinfo=timezone.utc)
        self.t2 = datetime(2026, 11, 9, 10, 5, 0, tzinfo=timezone.utc)
        self.t3 = datetime(2026, 11, 9, 10, 10, 0, tzinfo=timezone.utc)

    def test_1_single_model_aggregation(self):
        """1. Test aggregating multiple turns of a single model."""
        records = [
            CanonicalUsageRecord(
                provider="Google",
                agent="Google Antigravity",
                session_id="session-1",
                turn_index=0,
                model_display_name="Gemini 3.8 Flash (High)",
                model_id="gemini-3.8-flash",
                timestamp=self.t1,
                input_tokens=1000,
                output_tokens=200,
                cache_read_tokens=500,
            ),
            CanonicalUsageRecord(
                provider="Google",
                agent="Google Antigravity",
                session_id="session-1",
                turn_index=1,
                model_display_name="Gemini 3.8 Flash (High)",
                model_id="gemini-3.8-flash",
                timestamp=self.t2,
                input_tokens=2000,
                output_tokens=300,
                cache_read_tokens=1500,
            ),
        ]

        summaries = self.aggregator.aggregate_by_model(records)
        self.assertEqual(len(summaries), 1)
        s = summaries[0]
        self.assertEqual(s.model_display_name, "Gemini 3.8 Flash (High)")
        self.assertEqual(s.input_tokens, 3000)
        self.assertEqual(s.output_tokens, 500)
        self.assertEqual(s.cache_read_tokens, 2000)
        # Total tokens must equal input + output (3500)
        self.assertEqual(s.total_tokens, 3500)

    def test_2_multiple_model_aggregation(self):
        """2. Test aggregating across multiple distinct models (model switching)."""
        records = [
            CanonicalUsageRecord(
                provider="Google",
                agent="Google Antigravity",
                session_id="session-1",
                turn_index=0,
                model_display_name="Gemini 3.8 Flash (High)",
                model_id="gemini-3.8-flash",
                timestamp=self.t1,
                input_tokens=1000,
                output_tokens=150,
            ),
            CanonicalUsageRecord(
                provider="Google",
                agent="Google Antigravity",
                session_id="session-1",
                turn_index=1,
                model_display_name="Gemini 3.8 Pro (High)",
                model_id="gemini-3.8-pro",
                timestamp=self.t2,
                input_tokens=3000,
                output_tokens=400,
            ),
        ]

        summaries = self.aggregator.aggregate_by_model(records)
        self.assertEqual(len(summaries), 2)
        model_names = {s.model_display_name for s in summaries}
        self.assertEqual(model_names, {"Gemini 3.8 Flash (High)", "Gemini 3.8 Pro (High)"})

    def test_3_multiple_agent_aggregation(self):
        """3. Test grouping usage across multiple coding agents."""
        records = [
            CanonicalUsageRecord(
                provider="Google",
                agent="Google Antigravity",
                session_id="session-1",
                turn_index=0,
                model_display_name="Gemini 3.8 Flash",
                model_id="gemini-3.8-flash",
                timestamp=self.t1,
                input_tokens=1000,
                output_tokens=200,
            ),
            CanonicalUsageRecord(
                provider="Anthropic",
                agent="Claude Code",
                session_id="session-1",
                turn_index=1,
                model_display_name="Claude 3.5 Sonnet",
                model_id="claude-3-5-sonnet",
                timestamp=self.t2,
                input_tokens=1500,
                output_tokens=300,
            ),
        ]

        agent_rollup = self.aggregator.aggregate_by_agent(records)
        self.assertIn("Google Antigravity", agent_rollup)
        self.assertIn("Claude Code", agent_rollup)
        self.assertEqual(agent_rollup["Google Antigravity"]["total_tokens"], 1200)
        self.assertEqual(agent_rollup["Claude Code"]["total_tokens"], 1800)

    def test_4_multiple_session_aggregation(self):
        """4. Test grouping usage across multiple distinct session IDs."""
        records = [
            CanonicalUsageRecord(
                provider="Google",
                agent="Google Antigravity",
                session_id="session-A",
                turn_index=0,
                model_display_name="Gemini 3.8 Flash",
                timestamp=self.t1,
                input_tokens=500,
                output_tokens=100,
            ),
            CanonicalUsageRecord(
                provider="Google",
                agent="Google Antigravity",
                session_id="session-B",
                turn_index=0,
                model_display_name="Gemini 3.8 Flash",
                timestamp=self.t2,
                input_tokens=800,
                output_tokens=200,
            ),
        ]

        by_session = self.aggregator.aggregate_by_session(records)
        self.assertIn("session-A", by_session)
        self.assertIn("session-B", by_session)
        self.assertEqual(by_session["session-A"][0].total_tokens, 600)
        self.assertEqual(by_session["session-B"][0].total_tokens, 1000)

    def test_5_unknown_model_handling(self):
        """5. Test that unknown models remain unmerged and preserve display name."""
        records = [
            CanonicalUsageRecord(
                provider="Unknown",
                agent="Google Antigravity",
                session_id="session-1",
                turn_index=0,
                model_display_name="Experimental-Custom-X",
                model_id=None,
                timestamp=self.t1,
                input_tokens=400,
                output_tokens=100,
            )
        ]

        summaries = self.aggregator.aggregate_by_model(records)
        self.assertEqual(len(summaries), 1)
        self.assertIsNone(summaries[0].model_id)
        self.assertEqual(summaries[0].model_display_name, "Experimental-Custom-X")

    def test_6_missing_token_metrics(self):
        """6. Test that missing optional metrics remain None when none are reported."""
        records = [
            CanonicalUsageRecord(
                provider="Google",
                agent="Google Antigravity",
                session_id="session-1",
                turn_index=0,
                model_display_name="Gemini 3.8 Flash",
                timestamp=self.t1,
                input_tokens=100,
                output_tokens=50,
                cache_read_tokens=None,
                cache_write_tokens=None,
                reasoning_tokens=None,
            )
        ]

        summaries = self.aggregator.aggregate_by_model(records)
        self.assertIsNone(summaries[0].cache_read_tokens)
        self.assertIsNone(summaries[0].cache_write_tokens)
        self.assertIsNone(summaries[0].reasoning_tokens)

    def test_7_cache_read_accounting(self):
        """7. Test accurate summing of cache_read_tokens when present."""
        records = [
            CanonicalUsageRecord(
                provider="Google",
                agent="Google Antigravity",
                session_id="session-1",
                turn_index=0,
                model_display_name="Gemini 3.8 Flash",
                model_id="gemini-3.8-flash",
                timestamp=self.t1,
                input_tokens=2000,
                output_tokens=100,
                cache_read_tokens=10000,
            ),
            CanonicalUsageRecord(
                provider="Google",
                agent="Google Antigravity",
                session_id="session-1",
                turn_index=1,
                model_display_name="Gemini 3.8 Flash",
                model_id="gemini-3.8-flash",
                timestamp=self.t2,
                input_tokens=3000,
                output_tokens=200,
                cache_read_tokens=25000,
            ),
        ]

        summaries = self.aggregator.aggregate_by_model(records)
        self.assertEqual(summaries[0].cache_read_tokens, 35000)

    def test_8_prevention_of_double_counting(self):
        """8. Test that total_tokens strictly equals input_tokens + output_tokens."""
        records = [
            CanonicalUsageRecord(
                provider="Google",
                agent="Google Antigravity",
                session_id="session-1",
                turn_index=0,
                model_display_name="Gemini 3.8 Flash",
                model_id="gemini-3.8-flash",
                timestamp=self.t1,
                input_tokens=1000,
                output_tokens=200,
                cache_read_tokens=50000,  # Large cache read
            )
        ]

        summaries = self.aggregator.aggregate_by_model(records)
        # total_tokens MUST be 1200 (1000 + 200). It must NOT be 51200!
        self.assertEqual(summaries[0].total_tokens, 1200)

    def test_15_empty_session_handling(self):
        """15. Test building a receipt when a session has zero generation records."""
        receipt = self.aggregator.build_receipt([], session_id="empty-sess-100")
        self.assertEqual(receipt.total_tokens, 0)
        self.assertEqual(receipt.total_input_tokens, 0)
        self.assertEqual(receipt.total_output_tokens, 0)
        self.assertIsNone(receipt.total_cache_read_tokens)
        self.assertIsNone(receipt.estimated_api_cost_usd)
        self.assertIsNone(receipt.actual_billed_amount_usd)
        self.assertEqual(receipt.pricing_status, "unavailable")

    def test_16_accounting_semantics_formula(self):
        """16. Test verified accounting semantics using real Turn 3 metrics from local session."""
        # Empirical Turn 3 data: input_tokens=9790, cache_read=22852, output_tokens=684
        record = CanonicalUsageRecord(
            provider="Google",
            agent="Google Antigravity",
            session_id="session-turn-3",
            turn_index=3,
            model_display_name="Gemini 3.8 Flash",
            model_id="gemini-3.8-flash",
            timestamp=self.t1,
            input_tokens=9790,
            output_tokens=684,
            cache_read_tokens=22852,
        )

        summaries = self.aggregator.aggregate_by_model([record])
        s = summaries[0]
        # input_tokens is uncached input tokens
        self.assertEqual(s.input_tokens, 9790)
        # cache_read_tokens is cached context
        self.assertEqual(s.cache_read_tokens, 22852)
        # total_tokens is STRICTLY input + output (10,474), NEVER 10,474 + 22,852!
        self.assertEqual(s.total_tokens, 10474)
        self.assertNotEqual(s.total_tokens, 9790 + 684 + 22852)

    def test_17_preview_status_propagation_to_receipt(self):
        """17. Test that preview models propagate 'preview_estimate' status to receipt."""
        records = [
            CanonicalUsageRecord(
                provider="Google",
                agent="Google Antigravity",
                session_id="session-preview-1",
                turn_index=0,
                model_display_name="Gemini 3.8 Flash",
                model_id="gemini-3.8-flash",
                timestamp=self.t1,
                input_tokens=10000,
                output_tokens=500,
                cache_read_tokens=20000,
            )
        ]
        receipt = self.aggregator.build_receipt(records, session_id="session-preview-1")
        self.assertEqual(receipt.pricing_status, "preview_estimate")
        self.assertIsNotNone(receipt.estimated_api_cost_usd)
        self.assertIsNone(receipt.actual_billed_amount_usd)

    def test_18_mixed_model_session_build_receipt(self):
        """18. Test full receipt aggregation and pricing for a mixed-model session."""
        records = [
            # Turn 0: Gemini 3.8 Flash
            CanonicalUsageRecord(
                provider="Google",
                agent="Google Antigravity",
                session_id="session-mixed-1",
                turn_index=0,
                model_display_name="Gemini 3.8 Flash",
                model_id="gemini-3.8-flash",
                timestamp=self.t1,
                input_tokens=10000,
                output_tokens=500,
                cache_read_tokens=25000,
            ),
            # Turn 1: Claude Opus 4.6 (unpriced)
            CanonicalUsageRecord(
                provider="Anthropic",
                agent="Google Antigravity",
                session_id="session-mixed-1",
                turn_index=1,
                model_display_name="Claude Opus 4.6",
                model_id="claude-opus-4-6",
                timestamp=self.t2,
                input_tokens=8000,
                output_tokens=400,
                cache_read_tokens=30000,
            ),
            # Turn 2: Gemini 2.5 Flash (verified)
            CanonicalUsageRecord(
                provider="Google",
                agent="Google Antigravity",
                session_id="session-mixed-1",
                turn_index=2,
                model_display_name="Gemini 2.5 Flash",
                model_id="gemini-2.5-flash",
                timestamp=self.t3,
                input_tokens=5000,
                output_tokens=300,
                cache_read_tokens=40000,
            ),
        ]
        receipt = self.aggregator.build_receipt(records, session_id="session-mixed-1")

        # 3 model summaries created
        self.assertEqual(len(receipt.model_summaries), 3)

        by_model = {s.model_id: s for s in receipt.model_summaries}
        self.assertIn("gemini-3.8-flash", by_model)
        self.assertIn("claude-opus-4-6", by_model)
        self.assertIn("gemini-2.5-flash", by_model)

        # Gemini 3.8 Flash: preview_estimate
        self.assertEqual(by_model["gemini-3.8-flash"].pricing_status, "preview_estimate")
        self.assertIsNotNone(by_model["gemini-3.8-flash"].estimated_api_cost_usd)

        # Claude Opus 4.6: partially_priced (input & output priced, cache read unverified/None)
        self.assertEqual(by_model["claude-opus-4-6"].pricing_status, "partially_priced")
        self.assertIsNotNone(by_model["claude-opus-4-6"].estimated_api_cost_usd)
        self.assertEqual(by_model["claude-opus-4-6"].input_cost_usd, Decimal("0.040"))
        self.assertEqual(by_model["claude-opus-4-6"].output_cost_usd, Decimal("0.010"))
        self.assertIsNone(by_model["claude-opus-4-6"].cache_read_cost_usd)

        # Gemini 2.5 Flash: verified
        self.assertEqual(by_model["gemini-2.5-flash"].pricing_status, "verified")
        self.assertIsNotNone(by_model["gemini-2.5-flash"].estimated_api_cost_usd)

        # Overall receipt has partially_priced status (due to partially priced Claude Opus component)
        self.assertEqual(receipt.pricing_status, "partially_priced")
        self.assertIsNotNone(receipt.estimated_api_cost_usd)
        self.assertIsNone(receipt.actual_billed_amount_usd)
        self.assertIsNone(receipt.cache_storage_cost_usd)
        self.assertEqual(receipt.total_turns, 3)
        self.assertEqual(by_model["gemini-3.8-flash"].turn_count, 1)
        self.assertEqual(by_model["claude-opus-4-6"].turn_count, 1)
        self.assertEqual(by_model["gemini-2.5-flash"].turn_count, 1)

    def test_19_model_turn_counts_reconciliation(self):
        """19. Verify authentic per-model turn counts for multi-model session 99d16623."""
        # 10 turns of Claude Opus
        opus_recs = [
            CanonicalUsageRecord(
                provider="Anthropic",
                agent="Google Antigravity",
                session_id="session-99d",
                turn_index=i,
                model_display_name="Claude Opus 4.6 (Thinking)",
                model_id="claude-opus-4-6",
                timestamp=self.t1,
                input_tokens=18521,
                output_tokens=2644,
                cache_read_tokens=60126,
            )
            for i in range(10)
        ]
        # 29 turns of Gemini 3.8 Flash (Medium)
        med_recs = [
            CanonicalUsageRecord(
                provider="Google",
                agent="Google Antigravity",
                session_id="session-99d",
                turn_index=10 + i,
                model_display_name="Gemini 3.8 Flash (Medium)",
                model_id="gemini-3.8-flash",
                timestamp=self.t2,
                input_tokens=10104,
                output_tokens=649,
                cache_read_tokens=110465,
            )
            for i in range(29)
        ]
        # 46 turns of Gemini 3.8 Flash (High)
        hi_recs = [
            CanonicalUsageRecord(
                provider="Google",
                agent="Google Antigravity",
                session_id="session-99d",
                turn_index=39 + i,
                model_display_name="Gemini 3.8 Flash (High)",
                model_id="gemini-3.8-flash",
                timestamp=self.t3,
                input_tokens=2796,
                output_tokens=1018,
                cache_read_tokens=162683,
            )
            for i in range(46)
        ]

        all_recs = opus_recs + med_recs + hi_recs
        self.assertEqual(len(all_recs), 85)

        receipt = self.aggregator.build_receipt(all_recs, session_id="session-99d")
        self.assertEqual(receipt.total_turns, 85)

        by_display = {s.model_display_name: s for s in receipt.model_summaries}
        self.assertEqual(by_display["Claude Opus 4.6 (Thinking)"].turn_count, 10)
        self.assertEqual(by_display["Gemini 3.8 Flash (Medium)"].turn_count, 29)
        self.assertEqual(by_display["Gemini 3.8 Flash (High)"].turn_count, 46)


if __name__ == "__main__":
    unittest.main()

