"""Unit tests for Phase 1 canonical data models and validation rules.

Tests cover:
1. Valid usage records.
2. Missing optional metrics (None/null preservation, distinct from 0).
3. Negative token rejection.
4. Missing / nullable model IDs.
5. Timezone-aware timestamp validation.
6. Decimal cost handling and precision.
7. Correct total-token calculation without double-counting cache tokens.
"""

import unittest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pydantic import ValidationError

from core.models import (
    CanonicalUsageRecord,
    ModelUsageSummary,
    ReceiptMetadata,
    Receipt,
)


class TestCanonicalUsageRecord(unittest.TestCase):
    """Test suite for CanonicalUsageRecord validation."""

    def test_valid_usage_record(self):
        """Test creating a completely valid CanonicalUsageRecord."""
        record = CanonicalUsageRecord(
            provider="Google",
            agent="Google Antigravity",
            session_id="session-uuid-101",
            turn_index=1,
            model_display_name="Gemini 3.8 Flash (High)",
            model_id="gemini-3.8-flash",
            timestamp=datetime(2026, 11, 7, 12, 0, 0, tzinfo=timezone.utc),
            input_tokens=1500,
            output_tokens=350,
            cache_read_tokens=400,
            cache_write_tokens=None,
            reasoning_tokens=None,
            source="transcript.jsonl",
        )
        self.assertEqual(record.provider, "Google")
        self.assertEqual(record.agent, "Google Antigravity")
        self.assertEqual(record.session_id, "session-uuid-101")
        self.assertEqual(record.turn_index, 1)
        self.assertEqual(record.model_display_name, "Gemini 3.8 Flash (High)")
        self.assertEqual(record.model_id, "gemini-3.8-flash")
        self.assertEqual(record.input_tokens, 1500)
        self.assertEqual(record.output_tokens, 350)
        self.assertEqual(record.cache_read_tokens, 400)
        self.assertIsNone(record.cache_write_tokens)
        self.assertIsNone(record.reasoning_tokens)

    def test_missing_optional_metrics_preserved_as_none(self):
        """Test that missing optional metrics remain None and are not converted to 0."""
        record = CanonicalUsageRecord(
            provider="Google",
            agent="Google Antigravity",
            session_id="session-uuid-102",
            turn_index=0,
            model_display_name="Gemini 3.8 Flash",
            timestamp=datetime.now(timezone.utc),
            input_tokens=100,
            output_tokens=50,
            cache_read_tokens=None,
            cache_write_tokens=None,
            reasoning_tokens=None,
        )
        self.assertIsNone(record.cache_read_tokens)
        self.assertIsNone(record.cache_write_tokens)
        self.assertIsNone(record.reasoning_tokens)
        self.assertIsNone(record.model_id)

        # Distinguish explicit 0 from None
        record_with_zeros = CanonicalUsageRecord(
            provider="Google",
            agent="Google Antigravity",
            session_id="session-uuid-102",
            turn_index=0,
            model_display_name="Gemini 3.8 Flash",
            timestamp=datetime.now(timezone.utc),
            input_tokens=100,
            output_tokens=50,
            cache_read_tokens=0,
            cache_write_tokens=0,
            reasoning_tokens=0,
        )
        self.assertEqual(record_with_zeros.cache_read_tokens, 0)
        self.assertEqual(record_with_zeros.cache_write_tokens, 0)
        self.assertEqual(record_with_zeros.reasoning_tokens, 0)

    def test_negative_token_rejection(self):
        """Test that negative token values are strictly rejected."""
        base_args = {
            "provider": "Google",
            "agent": "Google Antigravity",
            "session_id": "session-103",
            "turn_index": 0,
            "model_display_name": "Gemini 3.8 Flash",
            "timestamp": datetime.now(timezone.utc),
        }

        with self.assertRaises(ValidationError):
            CanonicalUsageRecord(**base_args, input_tokens=-1, output_tokens=10)

        with self.assertRaises(ValidationError):
            CanonicalUsageRecord(**base_args, input_tokens=10, output_tokens=-5)

        with self.assertRaises(ValidationError):
            CanonicalUsageRecord(**base_args, input_tokens=10, output_tokens=10, cache_read_tokens=-1)

        with self.assertRaises(ValidationError):
            CanonicalUsageRecord(**base_args, input_tokens=10, output_tokens=10, cache_write_tokens=-1)

        with self.assertRaises(ValidationError):
            CanonicalUsageRecord(**base_args, input_tokens=10, output_tokens=10, reasoning_tokens=-1)

    def test_missing_model_ids(self):
        """Test that unmapped or unknown models can have model_id as None."""
        record = CanonicalUsageRecord(
            provider="Google",
            agent="Google Antigravity",
            session_id="session-104",
            turn_index=0,
            model_display_name="Custom Experimental Model",
            model_id=None,
            timestamp=datetime.now(timezone.utc),
            input_tokens=500,
            output_tokens=100,
        )
        self.assertIsNone(record.model_id)
        self.assertEqual(record.model_display_name, "Custom Experimental Model")

    def test_timezone_aware_timestamps(self):
        """Test that naive datetimes without tzinfo are strictly rejected."""
        naive_dt = datetime(2026, 11, 7, 10, 30, 0)  # No tzinfo

        with self.assertRaises(ValidationError):
            CanonicalUsageRecord(
                provider="Google",
                agent="Google Antigravity",
                session_id="session-105",
                turn_index=0,
                model_display_name="Gemini 3.8 Flash",
                timestamp=naive_dt,
                input_tokens=100,
                output_tokens=50,
            )

        # Timezone-aware datetimes with non-UTC offset must succeed
        ist = timezone(timedelta(hours=5, minutes=30))
        aware_dt = datetime(2026, 11, 7, 10, 30, 0, tzinfo=ist)
        record = CanonicalUsageRecord(
            provider="Google",
            agent="Google Antigravity",
            session_id="session-105",
            turn_index=0,
            model_display_name="Gemini 3.8 Flash",
            timestamp=aware_dt,
            input_tokens=100,
            output_tokens=50,
        )
        self.assertIsNotNone(record.timestamp.tzinfo)


class TestModelUsageSummary(unittest.TestCase):
    """Test suite for ModelUsageSummary and token double-counting prevention."""

    def test_total_tokens_auto_calculation(self):
        """Test that total_tokens defaults correctly to input_tokens + output_tokens."""
        summary = ModelUsageSummary(
            provider="Google",
            agent="Google Antigravity",
            model_display_name="Gemini 3.8 Flash",
            model_id="gemini-3.8-flash",
            input_tokens=1000,
            output_tokens=300,
            cache_read_tokens=250,
        )
        # total_tokens must be input (1000) + output (300) = 1300
        # cache_read_tokens (250) must NOT be added again!
        self.assertEqual(summary.total_tokens, 1300)

    def test_double_counting_cache_tokens_rejection(self):
        """Test that explicitly passing a total that double-counts cache tokens is rejected."""
        # input=1000, output=300, cache_read=250 -> passing 1550 (1000+300+250) must fail
        with self.assertRaises(ValidationError):
            ModelUsageSummary(
                provider="Google",
                agent="Google Antigravity",
                model_display_name="Gemini 3.8 Flash",
                model_id="gemini-3.8-flash",
                input_tokens=1000,
                output_tokens=300,
                cache_read_tokens=250,
                total_tokens=1550,
            )

    def test_negative_summary_tokens_rejection(self):
        """Test rejection of negative values in summary."""
        with self.assertRaises(ValidationError):
            ModelUsageSummary(
                provider="Google",
                agent="Google Antigravity",
                model_display_name="Gemini 3.8 Flash",
                input_tokens=-10,
                output_tokens=50,
            )


class TestReceiptAndMetadata(unittest.TestCase):
    """Test suite for ReceiptMetadata and Receipt."""

    def test_metadata_timezone_validation(self):
        """Test that ReceiptMetadata validates timezone awareness on all timestamp fields."""
        naive_dt = datetime(2026, 11, 7, 10, 0, 0)
        aware_dt = datetime(2026, 11, 7, 10, 0, 0, tzinfo=timezone.utc)

        # Naive generated_at must fail
        with self.assertRaises(ValidationError):
            ReceiptMetadata(
                receipt_id="rec-001",
                generated_at=naive_dt,
                session_id="session-001",
            )

        # Naive first_turn_at must fail
        with self.assertRaises(ValidationError):
            ReceiptMetadata(
                receipt_id="rec-001",
                generated_at=aware_dt,
                first_turn_at=naive_dt,
                session_id="session-001",
            )

        # Fully aware metadata must succeed
        meta = ReceiptMetadata(
            receipt_id="rec-001",
            generated_at=aware_dt,
            first_turn_at=aware_dt,
            last_turn_at=aware_dt + timedelta(minutes=15),
            elapsed_time_seconds=900.0,
            session_id="session-001",
        )
        self.assertEqual(meta.elapsed_time_seconds, 900.0)

    def test_decimal_cost_handling(self):
        """Test that financial fields strictly preserve Decimal precision and reject negatives."""
        meta = ReceiptMetadata(
            receipt_id="rec-002",
            generated_at=datetime.now(timezone.utc),
            session_id="session-002",
        )
        summary = ModelUsageSummary(
            provider="Google",
            agent="Google Antigravity",
            model_display_name="Gemini 3.8 Flash",
            model_id="gemini-3.8-flash",
            input_tokens=100000,
            output_tokens=20000,
        )

        receipt = Receipt(
            metadata=meta,
            model_summaries=[summary],
            estimated_api_cost_usd=Decimal("0.013500"),
            actual_billed_amount_usd=Decimal("0.00"),
            pricing_status="estimated",
        )

        self.assertIsInstance(receipt.estimated_api_cost_usd, Decimal)
        self.assertEqual(receipt.estimated_api_cost_usd, Decimal("0.013500"))
        self.assertEqual(receipt.actual_billed_amount_usd, Decimal("0.00"))
        self.assertEqual(receipt.total_tokens, 120000)

        # Reject negative cost
        with self.assertRaises(ValidationError):
            Receipt(
                metadata=meta,
                model_summaries=[summary],
                estimated_api_cost_usd=Decimal("-0.05"),
                pricing_status="estimated",
            )


if __name__ == "__main__":
    unittest.main()

