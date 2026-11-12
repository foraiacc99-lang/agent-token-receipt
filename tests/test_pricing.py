"""Unit tests for Phase 3 & 3.1 pricing calculation engine (pricing/calculator.py).

Covers:
- Standard model calculations with exact Decimal precision.
- Context window tiered pricing (<= 128k vs > 128k).
- Preview vs verified status separation.
- Cache-write (prompt creation) and cache-read costs.
- Partial pricing and missing category handling.
- Unknown model and unpriced model handling.
- Actual billed amount strictly remaining None.
- Verification against the production catalogue.json.
"""

import unittest
from datetime import datetime, timezone
from decimal import Decimal

from core.models import CanonicalUsageRecord, ModelUsageSummary, Receipt, ReceiptMetadata
from pricing.calculator import CostCalculator, PricingCatalogue


class TestCostCalculator(unittest.TestCase):
    """Test suite for CostCalculator and PricingCatalogue."""

    def setUp(self):
        # Dedicated synthetic catalogue for isolated testing
        test_catalogue_data = {
            "version": "test-v2",
            "default_currency": "USD",
            "models": {
                "test-flash": {
                    "provider": "Google",
                    "model_display_name": "Test Flash",
                    "canonical_model_id": "test-flash",
                    "verification_status": "verified",
                    "input_price_per_million": "0.075",
                    "output_price_per_million": "0.30",
                    "cache_read_price_per_million": "0.01875",
                    "cache_write_price_per_million": None,
                },
                "test-pro": {
                    "provider": "Google",
                    "model_display_name": "Test Pro",
                    "canonical_model_id": "test-pro",
                    "verification_status": "verified",
                    "input_price_per_million": "1.25",
                    "output_price_per_million": "5.00",
                    "cache_read_price_per_million": "0.3125",
                    "cache_write_price_per_million": None,
                },
                "test-partial": {
                    "provider": "Google",
                    "model_display_name": "Test Partial",
                    "canonical_model_id": "test-partial",
                    "verification_status": "verified",
                    "input_price_per_million": "1.00",
                    "output_price_per_million": "2.00",
                    "cache_read_price_per_million": None,  # Missing cache read price
                    "cache_write_price_per_million": None,
                },
                "test-unpriced": {
                    "provider": "Anthropic",
                    "model_display_name": "Test Unpriced",
                    "canonical_model_id": "test-unpriced",
                    "verification_status": "unverified",
                    "input_price_per_million": None,
                    "output_price_per_million": None,
                    "cache_read_price_per_million": None,
                    "cache_write_price_per_million": None,
                },
                "test-tiered": {
                    "provider": "Google",
                    "model_display_name": "Test Tiered",
                    "canonical_model_id": "test-tiered",
                    "verification_status": "verified",
                    "input_price_per_million": "0.075",
                    "output_price_per_million": "0.30",
                    "cache_read_price_per_million": "0.01875",
                    "cache_write_price_per_million": None,
                    "tiers": [
                        {
                            "threshold_tokens": 128000,
                            "condition": "<=",
                            "input_price_per_million": "0.075",
                            "output_price_per_million": "0.30",
                            "cache_read_price_per_million": "0.01875",
                            "cache_write_price_per_million": None,
                        },
                        {
                            "threshold_tokens": 128000,
                            "condition": ">",
                            "input_price_per_million": "0.15",
                            "output_price_per_million": "0.60",
                            "cache_read_price_per_million": "0.0375",
                            "cache_write_price_per_million": None,
                        },
                    ],
                },
                "test-preview": {
                    "provider": "Google",
                    "model_display_name": "Test Preview",
                    "canonical_model_id": "test-preview",
                    "verification_status": "preview_estimate",
                    "input_price_per_million": "0.75",
                    "output_price_per_million": "3.75",
                    "cache_read_price_per_million": "0.075",
                    "cache_write_price_per_million": None,
                    "notes": "Introductory preview rate through Dec 31, 2026",
                },
                "test-claude": {
                    "provider": "Anthropic",
                    "model_display_name": "Test Claude",
                    "canonical_model_id": "test-claude",
                    "verification_status": "verified",
                    "input_price_per_million": "3.00",
                    "output_price_per_million": "15.00",
                    "cache_read_price_per_million": "0.30",
                    "cache_write_price_per_million": "3.75",
                },
            },
        }
        self.catalogue = PricingCatalogue(catalogue_data=test_catalogue_data)
        self.calculator = CostCalculator(catalogue=self.catalogue)

    def test_decimal_precision(self):
        """Test that calculations maintain exact Decimal precision without float inaccuracies."""
        summary = ModelUsageSummary(
            provider="Google",
            agent="Google Antigravity",
            model_display_name="Test Flash",
            model_id="test-flash",
            input_tokens=1000000,   # 1M tokens @ 0.075 = $0.075
            output_tokens=1000000,  # 1M tokens @ 0.30 = $0.30
            cache_read_tokens=1000000, # 1M tokens @ 0.01875 = $0.01875
        )
        calculated = self.calculator.calculate_model_cost(summary)

        self.assertIsInstance(calculated.input_cost_usd, Decimal)
        self.assertIsInstance(calculated.output_cost_usd, Decimal)
        self.assertIsInstance(calculated.cache_read_cost_usd, Decimal)
        self.assertIsInstance(calculated.estimated_api_cost_usd, Decimal)

        self.assertEqual(calculated.input_cost_usd, Decimal("0.075"))
        self.assertEqual(calculated.output_cost_usd, Decimal("0.30"))
        self.assertEqual(calculated.cache_read_cost_usd, Decimal("0.01875"))
        # 0.075 + 0.30 + 0.01875 = 0.39375
        self.assertEqual(calculated.estimated_api_cost_usd, Decimal("0.39375"))

    def test_correct_input_cost(self):
        """Test accurate calculation of input token cost."""
        summary = ModelUsageSummary(
            provider="Google",
            agent="Google Antigravity",
            model_display_name="Test Pro",
            model_id="test-pro",
            input_tokens=500000,  # 500k tokens @ $1.25 / 1M = $0.625
            output_tokens=0,
        )
        calculated = self.calculator.calculate_model_cost(summary)
        self.assertEqual(calculated.input_cost_usd, Decimal("0.625"))

    def test_correct_output_cost(self):
        """Test accurate calculation of output token cost."""
        summary = ModelUsageSummary(
            provider="Google",
            agent="Google Antigravity",
            model_display_name="Test Pro",
            model_id="test-pro",
            input_tokens=0,
            output_tokens=200000,  # 200k tokens @ $5.00 / 1M = $1.00
        )
        calculated = self.calculator.calculate_model_cost(summary)
        self.assertEqual(calculated.output_cost_usd, Decimal("1.00"))

    def test_unknown_pricing(self):
        """Test that unpriced models are marked unknown_price and not defaulted to $0."""
        summary = ModelUsageSummary(
            provider="Anthropic",
            agent="Claude Code",
            model_display_name="Test Unpriced",
            model_id="test-unpriced",
            input_tokens=50000,
            output_tokens=10000,
        )
        calculated = self.calculator.calculate_model_cost(summary)
        self.assertEqual(calculated.pricing_status, "unknown_price")
        # NEVER default unknown cost to $0!
        self.assertIsNone(calculated.estimated_api_cost_usd)
        self.assertIsNone(calculated.input_cost_usd)
        self.assertIsNone(calculated.output_cost_usd)

    def test_partially_priced_models(self):
        """Test that models missing a category rate (e.g. cache read) are marked partially_priced."""
        summary = ModelUsageSummary(
            provider="Google",
            agent="Google Antigravity",
            model_display_name="Test Partial",
            model_id="test-partial",
            input_tokens=100000,   # 100k @ $1.00 / 1M = $0.10
            output_tokens=50000,   # 50k @ $2.00 / 1M = $0.10
            cache_read_tokens=200000,  # Cache tokens exist, but rate is None in catalogue!
        )
        calculated = self.calculator.calculate_model_cost(summary)
        self.assertEqual(calculated.pricing_status, "partially_priced")
        self.assertIn("cache-read tokens", calculated.pricing_notes)
        self.assertEqual(calculated.input_cost_usd, Decimal("0.10"))
        self.assertEqual(calculated.output_cost_usd, Decimal("0.10"))
        self.assertIsNone(calculated.cache_read_cost_usd)
        self.assertEqual(calculated.estimated_api_cost_usd, Decimal("0.20"))

    def test_actual_billing_remains_unavailable(self):
        """Test that actual_billed_amount_usd strictly remains None on the receipt."""
        meta = ReceiptMetadata(
            receipt_id="rec-test-99",
            generated_at=datetime.now(timezone.utc),
            session_id="session-99",
        )
        summary = ModelUsageSummary(
            provider="Google",
            agent="Google Antigravity",
            model_display_name="Test Flash",
            model_id="test-flash",
            input_tokens=1000,
            output_tokens=200,
        )
        receipt = Receipt(
            metadata=meta,
            model_summaries=[summary],
            total_tokens=1200,
        )

        priced_receipt = self.calculator.calculate_receipt_cost(receipt)
        self.assertIsNone(priced_receipt.actual_billed_amount_usd)
        self.assertIsNotNone(priced_receipt.estimated_api_cost_usd)
        self.assertEqual(priced_receipt.pricing_status, "verified")

    def test_unknown_model_status(self):
        """Test that unmapped model IDs are flagged as unknown_model without guessing."""
        summary = ModelUsageSummary(
            provider="Unknown",
            agent="Google Antigravity",
            model_display_name="Nonexistent Experimental Model",
            model_id=None,
            input_tokens=1000,
            output_tokens=200,
        )
        calculated = self.calculator.calculate_model_cost(summary)
        self.assertEqual(calculated.pricing_status, "unknown_model")
        self.assertIsNone(calculated.estimated_api_cost_usd)

    def test_tiered_pricing_below_threshold(self):
        """Test tiered pricing when prompt context is <= 128k tokens."""
        summary = ModelUsageSummary(
            provider="Google",
            agent="Google Antigravity",
            model_display_name="Test Tiered",
            model_id="test-tiered",
            input_tokens=100000,  # 100k tokens
            output_tokens=10000,
            cache_read_tokens=20000,
        )
        # Context = 120,000 <= 128,000
        calculated = self.calculator.calculate_model_cost(summary, context_tokens=120000)
        self.assertEqual(calculated.input_cost_usd, Decimal("0.0075"))  # 100k @ 0.075/1M
        self.assertEqual(calculated.output_cost_usd, Decimal("0.003"))   # 10k @ 0.30/1M
        self.assertEqual(calculated.cache_read_cost_usd, Decimal("0.000375")) # 20k @ 0.01875/1M

    def test_tiered_pricing_above_threshold(self):
        """Test tiered pricing when prompt context is > 128k tokens."""
        summary = ModelUsageSummary(
            provider="Google",
            agent="Google Antigravity",
            model_display_name="Test Tiered",
            model_id="test-tiered",
            input_tokens=100000,  # 100k tokens
            output_tokens=10000,
            cache_read_tokens=50000,
        )
        # Context = 150,000 > 128,000 -> tier 2 rates (0.15 in, 0.60 out, 0.0375 cache)
        calculated = self.calculator.calculate_model_cost(summary, context_tokens=150000)
        self.assertEqual(calculated.input_cost_usd, Decimal("0.015"))  # 100k @ 0.15/1M
        self.assertEqual(calculated.output_cost_usd, Decimal("0.006"))  # 10k @ 0.60/1M
        self.assertEqual(calculated.cache_read_cost_usd, Decimal("0.001875")) # 50k @ 0.0375/1M

    def test_preview_estimate_status(self):
        """Test that preview models are marked preview_estimate and not verified."""
        summary = ModelUsageSummary(
            provider="Google",
            agent="Google Antigravity",
            model_display_name="Test Preview",
            model_id="test-preview",
            input_tokens=1000000,
            output_tokens=100000,
            cache_read_tokens=500000,
        )
        calculated = self.calculator.calculate_model_cost(summary)
        self.assertEqual(calculated.pricing_status, "preview_estimate")
        self.assertIn("Introductory preview rate", calculated.pricing_notes)
        self.assertEqual(calculated.input_cost_usd, Decimal("0.75"))
        self.assertEqual(calculated.output_cost_usd, Decimal("0.375"))
        self.assertEqual(calculated.cache_read_cost_usd, Decimal("0.0375"))

    def test_claude_cache_write_and_read(self):
        """Test Anthropic Claude 3.5 / 3.7 with cache write and cache read."""
        summary = ModelUsageSummary(
            provider="Anthropic",
            agent="Claude Code",
            model_display_name="Test Claude",
            model_id="test-claude",
            input_tokens=1000000,       # 1M @ $3.00 = $3.00
            output_tokens=100000,       # 100k @ $15.00 = $1.50
            cache_read_tokens=2000000,  # 2M @ $0.30 = $0.60
            cache_write_tokens=500000,  # 500k @ $3.75 = $1.875
        )
        calculated = self.calculator.calculate_model_cost(summary)
        self.assertEqual(calculated.pricing_status, "verified")
        self.assertEqual(calculated.input_cost_usd, Decimal("3.00"))
        self.assertEqual(calculated.output_cost_usd, Decimal("1.50"))
        self.assertEqual(calculated.cache_read_cost_usd, Decimal("0.60"))
        self.assertEqual(calculated.cache_write_cost_usd, Decimal("1.875"))
        # 3.00 + 1.50 + 0.60 + 1.875 = 6.975
        self.assertEqual(calculated.estimated_api_cost_usd, Decimal("6.975"))

    def test_turn_level_context_tiering_from_records(self):
        """Test that calculate_model_cost_from_records evaluates tiers on a per-turn basis."""
        t1 = datetime(2026, 11, 9, 10, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 11, 9, 10, 5, tzinfo=timezone.utc)

        # Turn 1: 50k input + 20k cache = 70k prompt (<= 128k tier)
        # Input: 50k @ 0.075/1M = $0.00375; Output: 1k @ 0.30/1M = $0.0003
        r1 = CanonicalUsageRecord(
            provider="Google",
            agent="Google Antigravity",
            session_id="s1",
            turn_index=0,
            model_display_name="Test Tiered",
            model_id="test-tiered",
            timestamp=t1,
            input_tokens=50000,
            output_tokens=1000,
            cache_read_tokens=20000,
        )

        # Turn 2: 100k input + 50k cache = 150k prompt (> 128k tier)
        # Input: 100k @ 0.15/1M = $0.015; Output: 2k @ 0.60/1M = $0.0012
        r2 = CanonicalUsageRecord(
            provider="Google",
            agent="Google Antigravity",
            session_id="s1",
            turn_index=1,
            model_display_name="Test Tiered",
            model_id="test-tiered",
            timestamp=t2,
            input_tokens=100000,
            output_tokens=2000,
            cache_read_tokens=50000,
        )

        summary = ModelUsageSummary(
            provider="Google",
            agent="Google Antigravity",
            model_display_name="Test Tiered",
            model_id="test-tiered",
            input_tokens=150000,
            output_tokens=3000,
            cache_read_tokens=70000,
        )

        calculated = self.calculator.calculate_model_cost_from_records([r1, r2], summary)
        # Input cost = $0.00375 + $0.015 = $0.01875
        self.assertEqual(calculated.input_cost_usd, Decimal("0.01875"))
        # Output cost = $0.0003 + $0.0012 = $0.0015
        self.assertEqual(calculated.output_cost_usd, Decimal("0.0015"))
        # Cache read cost = (20k @ 0.01875/1M = $0.000375) + (50k @ 0.0375/1M = $0.001875) = $0.00225
        self.assertEqual(calculated.cache_read_cost_usd, Decimal("0.00225"))

    def test_production_catalogue_gemini_38_flash(self):
        """Test production catalogue rates for Gemini 3.8 Flash."""
        prod_calc = CostCalculator()
        summary = ModelUsageSummary(
            provider="Google",
            agent="Google Antigravity",
            model_display_name="Gemini 3.8 Flash",
            model_id="gemini-3.8-flash",
            input_tokens=1000000,   # 1M @ 0.75 = $0.75
            output_tokens=100000,   # 100k @ 3.75 = $0.375
            cache_read_tokens=2000000, # 2M @ 0.075 = $0.15
        )
        calculated = prod_calc.calculate_model_cost(summary)
        self.assertEqual(calculated.pricing_status, "preview_estimate")
        self.assertEqual(calculated.input_cost_usd, Decimal("0.75"))
        self.assertEqual(calculated.output_cost_usd, Decimal("0.375"))
        self.assertEqual(calculated.cache_read_cost_usd, Decimal("0.15"))
        self.assertEqual(calculated.estimated_api_cost_usd, Decimal("1.275"))

    def test_cache_storage_cost_remains_none(self):
        """Test that cache_storage_cost_usd is strictly None (unavailable) and never substituted with 0."""
        summary = ModelUsageSummary(
            provider="Google",
            agent="Google Antigravity",
            model_display_name="Test Flash",
            model_id="test-flash",
            input_tokens=100000,
            output_tokens=20000,
            cache_read_tokens=500000,
        )
        calculated = self.calculator.calculate_model_cost(summary)
        self.assertIsNone(calculated.cache_storage_cost_usd)

        meta = ReceiptMetadata(
            receipt_id="rec-storage-test",
            generated_at=datetime.now(timezone.utc),
            session_id="session-storage",
        )
        receipt = Receipt(
            metadata=meta,
            model_summaries=[calculated],
            total_tokens=120000,
        )
        priced_receipt = self.calculator.calculate_receipt_cost(receipt)
        self.assertIsNone(priced_receipt.cache_storage_cost_usd)

    def test_mixed_model_distinct_pricing(self):
        """Test that in a mixed-model receipt, each model is strictly priced with its own catalogue entry."""
        # Model 1: Test Flash ($0.075 in, $0.30 out, $0.01875 cache read)
        s_flash = ModelUsageSummary(
            provider="Google",
            agent="Google Antigravity",
            model_display_name="Test Flash",
            model_id="test-flash",
            input_tokens=1000000,
            output_tokens=100000,
            cache_read_tokens=2000000,
        )
        # Model 2: Test Claude ($3.00 in, $15.00 out, $0.30 cache read, $3.75 cache write)
        s_claude = ModelUsageSummary(
            provider="Anthropic",
            agent="Claude Code",
            model_display_name="Test Claude",
            model_id="test-claude",
            input_tokens=1000000,
            output_tokens=100000,
            cache_read_tokens=2000000,
        )
        # Model 3: Test Unpriced
        s_unpriced = ModelUsageSummary(
            provider="Anthropic",
            agent="Claude Code",
            model_display_name="Test Unpriced",
            model_id="test-unpriced",
            input_tokens=500000,
            output_tokens=50000,
        )

        meta = ReceiptMetadata(
            receipt_id="rec-mixed",
            generated_at=datetime.now(timezone.utc),
            session_id="session-mixed",
        )
        receipt = Receipt(
            metadata=meta,
            model_summaries=[s_flash, s_claude, s_unpriced],
            total_tokens=2750000,
        )
        priced_receipt = self.calculator.calculate_receipt_cost(receipt)

        # Confirm Model 1 got Flash rates
        res_flash = priced_receipt.model_summaries[0]
        self.assertEqual(res_flash.input_cost_usd, Decimal("0.075"))
        self.assertEqual(res_flash.output_cost_usd, Decimal("0.030"))
        self.assertEqual(res_flash.cache_read_cost_usd, Decimal("0.0375"))
        self.assertEqual(res_flash.estimated_api_cost_usd, Decimal("0.1425"))

        # Confirm Model 2 got Claude rates (NOT Flash rates!)
        res_claude = priced_receipt.model_summaries[1]
        self.assertEqual(res_claude.input_cost_usd, Decimal("3.00"))
        self.assertEqual(res_claude.output_cost_usd, Decimal("1.50"))
        self.assertEqual(res_claude.cache_read_cost_usd, Decimal("0.60"))
        self.assertEqual(res_claude.estimated_api_cost_usd, Decimal("5.10"))

        # Confirm Model 3 remains unpriced (NOT defaulted to $0 or Flash rates!)
        res_unpriced = priced_receipt.model_summaries[2]
        self.assertEqual(res_unpriced.pricing_status, "unknown_price")
        self.assertIsNone(res_unpriced.input_cost_usd)
        self.assertIsNone(res_unpriced.output_cost_usd)
        self.assertIsNone(res_unpriced.estimated_api_cost_usd)

        # Receipt total is sum of priced models
        self.assertEqual(priced_receipt.estimated_api_cost_usd, Decimal("5.2425"))

    def test_exact_221_turn_cost_snapshot(self):
        """Test exact Decimal recalculation of the 221-turn snapshot ($3.7258)."""
        prod_calc = CostCalculator()
        summary = ModelUsageSummary(
            provider="Google",
            agent="Google Antigravity",
            model_display_name="Gemini 3.8 Flash (High)",
            model_id="gemini-3.8-flash",
            input_tokens=1489498,
            output_tokens=196636,
            cache_read_tokens=24950223,
        )
        calculated = prod_calc.calculate_model_cost(summary)
        self.assertEqual(calculated.input_cost_usd, Decimal("1.11712350"))
        self.assertEqual(calculated.output_cost_usd, Decimal("0.73738500"))
        self.assertEqual(calculated.cache_read_cost_usd, Decimal("1.871266725"))
        # Total = 1.11712350 + 0.73738500 + 1.871266725 = 3.725775225
        self.assertEqual(calculated.estimated_api_cost_usd, Decimal("3.725775225"))
        self.assertEqual(f"{calculated.estimated_api_cost_usd:.4f}", "3.7258")

    def test_claude_opus_4_6_pricing_production(self):
        """Test Claude Opus 4.6 pricing from production catalogue."""
        prod_calc = CostCalculator()
        summary = ModelUsageSummary(
            provider="Anthropic",
            agent="Google Antigravity",
            model_display_name="Claude Opus 4.6 (Thinking)",
            model_id="claude-opus-4-6",
            input_tokens=185212,
            output_tokens=26445,
            cache_read_tokens=601260,
        )
        calculated = prod_calc.calculate_model_cost(summary)
        # Input: 185,212 @ $5.00/1M = $0.926060
        self.assertEqual(calculated.input_cost_usd, Decimal("0.926060"))
        # Output: 26,445 @ $25.00/1M = $0.661125
        self.assertEqual(calculated.output_cost_usd, Decimal("0.661125"))
        # Cache Read: None (unavailable due to unverified cache-read semantics)
        self.assertIsNone(calculated.cache_read_cost_usd)
        self.assertIsNone(calculated.cache_write_cost_usd)
        self.assertIsNone(calculated.cache_storage_cost_usd)
        # Status: partially_priced
        self.assertEqual(calculated.pricing_status, "partially_priced")
        self.assertIn("cache-read tokens", calculated.pricing_notes)
        # Total sum of priced components = 0.926060 + 0.661125 = 1.587185
        self.assertEqual(calculated.estimated_api_cost_usd, Decimal("1.587185"))

    def test_claude_opus_with_custom_cache_hit_rate(self):
        """Test Claude Opus 4.6 when catalogue explicitly specifies cache hit rate ($0.50/1M)."""
        custom_data = {
            "version": "test-opus-cache",
            "models": {
                "claude-opus-4-6": {
                    "provider": "Anthropic",
                    "model_display_name": "Claude Opus 4.6",
                    "canonical_model_id": "claude-opus-4-6",
                    "verification_status": "verified",
                    "input_price_per_million": "5.00",
                    "output_price_per_million": "25.00",
                    "cache_read_price_per_million": "0.50",
                    "cache_write_price_per_million": "6.25",
                }
            }
        }
        calc = CostCalculator(PricingCatalogue(catalogue_data=custom_data))
        summary = ModelUsageSummary(
            provider="Anthropic",
            agent="Google Antigravity",
            model_display_name="Claude Opus 4.6",
            model_id="claude-opus-4-6",
            input_tokens=185212,
            output_tokens=26445,
            cache_read_tokens=601260,
        )
        calculated = calc.calculate_model_cost(summary)
        # Cache Read: 601,260 @ $0.50/1M = $0.300630
        self.assertEqual(calculated.cache_read_cost_usd, Decimal("0.300630"))
        # Total = 0.926060 + 0.661125 + 0.300630 = 1.887815
        self.assertEqual(calculated.estimated_api_cost_usd, Decimal("1.887815"))

    def test_missing_cache_write_data(self):
        """Test that missing cache_write_tokens in logs does not cause errors or invalid charges."""
        custom_data = {
            "version": "test-write",
            "models": {
                "test-claude-write": {
                    "provider": "Anthropic",
                    "canonical_model_id": "test-claude-write",
                    "model_display_name": "Test Claude",
                    "input_price_per_million": "3.00",
                    "output_price_per_million": "15.00",
                    "cache_read_price_per_million": "0.30",
                    "cache_write_price_per_million": "3.75",
                }
            }
        }
        calc = CostCalculator(PricingCatalogue(catalogue_data=custom_data))
        summary = ModelUsageSummary(
            provider="Anthropic",
            agent="Google Antigravity",
            model_display_name="Test Claude",
            model_id="test-claude-write",
            input_tokens=100000,
            output_tokens=20000,
            cache_write_tokens=None,  # Not recorded in Antigravity
        )
        calculated = calc.calculate_model_cost(summary)
        # Cache write cost must remain None
        self.assertIsNone(calculated.cache_write_cost_usd)
        self.assertEqual(calculated.estimated_api_cost_usd, Decimal("0.60"))  # 0.30 in + 0.30 out

    def test_mixed_model_session_99d16623_recalculation(self):
        """Test exact recalculation of real multi-model session 99d16623-30c3-4cc5-a071-6c3e3c47ac15."""
        prod_calc = CostCalculator()
        
        # Model 1: Claude Opus 4.6 (185,212 in, 26,445 out, 601,260 cache read)
        s_opus = ModelUsageSummary(
            provider="Anthropic",
            agent="Google Antigravity",
            model_display_name="Claude Opus 4.6 (Thinking)",
            model_id="claude-opus-4-6",
            input_tokens=185212,
            output_tokens=26445,
            cache_read_tokens=601260,
        )
        # Model 2: Gemini 3.8 Flash (Medium) (293,022 in, 18,839 out, 3,203,508 cache read)
        s_flash_med = ModelUsageSummary(
            provider="Google",
            agent="Google Antigravity",
            model_display_name="Gemini 3.8 Flash (Medium)",
            model_id="gemini-3.8-flash",
            input_tokens=293022,
            output_tokens=18839,
            cache_read_tokens=3203508,
        )
        # Model 3: Gemini 3.8 Flash (High) (128,618 in, 46,841 out, 7,483,433 cache read)
        s_flash_hi = ModelUsageSummary(
            provider="Google",
            agent="Google Antigravity",
            model_display_name="Gemini 3.8 Flash (High)",
            model_id="gemini-3.8-flash",
            input_tokens=128618,
            output_tokens=46841,
            cache_read_tokens=7483433,
        )

        meta = ReceiptMetadata(
            receipt_id="rec-real-mixed",
            generated_at=datetime.now(timezone.utc),
            session_id="99d16623-30c3-4cc5-a071-6c3e3c47ac15",
        )
        receipt = Receipt(
            metadata=meta,
            model_summaries=[s_opus, s_flash_med, s_flash_hi],
            total_tokens=698977,
        )

        priced = prod_calc.calculate_receipt_cost(receipt)

        # Opus cost = $0.926060 in + $0.661125 out = $1.587185
        self.assertEqual(priced.model_summaries[0].estimated_api_cost_usd, Decimal("1.587185"))
        # Flash Medium cost = $0.2197665 in + $0.07064625 out + $0.24026310 cache = $0.53067585
        self.assertEqual(priced.model_summaries[1].estimated_api_cost_usd, Decimal("0.53067585"))
        # Flash High cost = $0.0964635 in + $0.17565375 out + $0.561257475 cache = $0.833374725
        self.assertEqual(priced.model_summaries[2].estimated_api_cost_usd, Decimal("0.833374725"))

        # Combined Total = 1.587185 + 0.53067585 + 0.833374725 = 2.951235575
        self.assertEqual(priced.estimated_api_cost_usd, Decimal("2.951235575"))
        self.assertEqual(f"{priced.estimated_api_cost_usd:.4f}", "2.9512")
        self.assertEqual(priced.pricing_status, "partially_priced")

    def test_multi_agent_same_model_no_cost_or_turn_duplication(self):
        """Regression test: two agents sharing model_id/display_name must not duplicate costs or turns."""
        prod_calc = CostCalculator()
        t0 = datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)

        rec_claude = CanonicalUsageRecord(
            session_id="sess-cc",
            turn_index=0,
            agent="Claude Code",
            provider="Anthropic",
            model_id="claude-opus-4-6",
            model_display_name="Claude Opus 4.6 (Thinking)",
            input_tokens=1000,
            output_tokens=500,
            total_tokens=1500,
            timestamp=t0,
        )
        rec_ag_1 = CanonicalUsageRecord(
            session_id="sess-ag",
            turn_index=0,
            agent="Google Antigravity",
            provider="Anthropic",
            model_id="claude-opus-4-6",
            model_display_name="Claude Opus 4.6 (Thinking)",
            input_tokens=2000,
            output_tokens=1000,
            total_tokens=3000,
            timestamp=t0,
        )
        rec_ag_2 = CanonicalUsageRecord(
            session_id="sess-ag",
            turn_index=1,
            agent="Google Antigravity",
            provider="Anthropic",
            model_id="claude-opus-4-6",
            model_display_name="Claude Opus 4.6 (Thinking)",
            input_tokens=2000,
            output_tokens=1000,
            total_tokens=3000,
            timestamp=t0,
        )

        s_claude = ModelUsageSummary(
            provider="Anthropic",
            agent="Claude Code",
            model_display_name="Claude Opus 4.6 (Thinking)",
            model_id="claude-opus-4-6",
            input_tokens=1000,
            output_tokens=500,
            turn_count=1,
        )
        s_ag = ModelUsageSummary(
            provider="Anthropic",
            agent="Google Antigravity",
            model_display_name="Claude Opus 4.6 (Thinking)",
            model_id="claude-opus-4-6",
            input_tokens=4000,
            output_tokens=2000,
            turn_count=2,
        )

        receipt = Receipt(
            metadata=ReceiptMetadata(
                receipt_id="rec-multi-same-model",
                generated_at=t0,
                session_id="multi-sess",
                agent="Claude Code, Google Antigravity",
            ),
            model_summaries=[s_claude, s_ag],
            usage_records=[rec_claude, rec_ag_1, rec_ag_2],
            total_tokens=7500,
        )

        priced = prod_calc.calculate_receipt_cost(receipt)
        # claude-opus-4-6: $5.00/M input, $25.00/M output
        # Claude Code: 1000 * 5 / 1M + 500 * 25 / 1M = 0.005 + 0.0125 = 0.0175
        # Antigravity: 4000 * 5 / 1M + 2000 * 25 / 1M = 0.02 + 0.05 = 0.07
        self.assertEqual(priced.model_summaries[0].turn_count, 1)
        self.assertEqual(priced.model_summaries[0].estimated_api_cost_usd, Decimal("0.0175"))
        self.assertEqual(priced.model_summaries[1].turn_count, 2)
        self.assertEqual(priced.model_summaries[1].estimated_api_cost_usd, Decimal("0.07"))
        self.assertEqual(priced.estimated_api_cost_usd, Decimal("0.0875"))


if __name__ == "__main__":
    unittest.main()
