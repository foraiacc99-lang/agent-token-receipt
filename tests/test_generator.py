"""Unit tests for the Thermal Receipt PDF Generator.

Verifies all 10 required test cases for Phase 4:
1. Basic single-model receipt.
2. Multiple-model receipt.
3. Multiple-agent receipt.
4. Partially priced model.
5. Unavailable cache-read cost.
6. Unavailable cache-write cost.
7. Missing metadata.
8. Long receipt with pagination.
9. Decimal cost formatting.
10. Correct total turn counts.
Additional tests:
11. Unique filename generation preventing accidental overwrites.
12. Single-page receipts omit multi-page pagination indicators.
"""

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import re
import tempfile
import unittest
import zlib

from core.models import ModelUsageSummary, Receipt, ReceiptMetadata
from generator.pdf import ReceiptPDFGenerator, ThermalReceiptPDF


def extract_pdf_texts(pdf_bytes: bytes) -> list[str]:
    """Decompresses all content streams in a PDF and returns extracted text tokens."""
    streams = []
    for m in re.finditer(rb"/Length\s+(\d+)[\s\S]{0,80}?stream\r?\n", pdf_bytes):
        length = int(m.group(1))
        start = m.end()
        streams.append(pdf_bytes[start : start + length])
    if not streams:
        streams = re.findall(rb"stream\r?\n(.*?)\r?\nendstream", pdf_bytes, re.DOTALL)

    texts = []
    for s in streams:
        try:
            decomp = zlib.decompress(s).decode("latin1", errors="ignore")
            matches = re.findall(r"\((.*?)\)\s*Tj", decomp)
            for m in matches:
                # Unescape PDF literal string parentheses
                clean = re.sub(r"\\([()])", r"\1", m)
                texts.append(clean)
        except Exception:
            pass
    return texts


class TestReceiptPDFGenerator(unittest.TestCase):
    """Test suite for thermal receipt PDF generation."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.temp_dir.name)
        self.generator = ReceiptPDFGenerator(output_dir=self.output_dir)
        self.now = datetime(2026, 11, 10, 1, 0, 0, tzinfo=timezone.utc)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_01_basic_single_model_receipt(self):
        """Test generating a receipt with a single verified model."""
        summary = ModelUsageSummary(
            provider="Google",
            agent="Google Antigravity",
            model_display_name="Gemini 3.8 Flash (High)",
            model_id="gemini-3.8-flash",
            input_tokens=100000,
            output_tokens=20000,
            cache_read_tokens=500000,
            cache_write_tokens=None,
            reasoning_tokens=None,
            total_tokens=120000,
            turn_count=25,
            input_cost_usd=Decimal("0.0750"),
            output_cost_usd=Decimal("0.0750"),
            cache_read_cost_usd=Decimal("0.0375"),
            cache_write_cost_usd=None,
            cache_storage_cost_usd=None,
            estimated_api_cost_usd=Decimal("0.1875"),
            pricing_status="verified",
            pricing_notes=None,
        )

        metadata = ReceiptMetadata(
            receipt_id="rec-test-01",
            generated_at=self.now,
            timezone="UTC",
            session_id="session-single-model-01",
            session_title="Single Model Workflow",
            elapsed_time_seconds=120.5,
        )

        receipt = Receipt(
            metadata=metadata,
            model_summaries=[summary],
            total_input_tokens=100000,
            total_output_tokens=20000,
            total_cache_read_tokens=500000,
            total_tokens=120000,
            total_turns=25,
            estimated_api_cost_usd=Decimal("0.1875"),
            pricing_status="verified",
        )

        pdf_path = self.generator.generate(receipt)
        self.assertTrue(pdf_path.exists())
        self.assertGreater(pdf_path.stat().st_size, 1000)

        pdf_bytes = pdf_path.read_bytes()
        texts = extract_pdf_texts(pdf_bytes)

        # Assert key text presence
        self.assertIn("AGENT TOKEN RECEIPT", texts)
        self.assertIn("Every token has a receipt.", texts)
        self.assertTrue(any("Gemini 3.8 Flash (High)" in t for t in texts))
        self.assertIn("100,000", texts)
        self.assertIn("20,000", texts)
        self.assertIn("500,000", texts)
        self.assertTrue(any("$0.1875 USD" in t for t in texts))
        self.assertIn("VERIFIED", texts)
        self.assertIn("Input + Output Tokens:", texts)
        self.assertFalse(any("Grand Total Tokens" in t for t in texts))
        self.assertIn("THANK YOU FOR BUILDING!", texts)
        self.assertIn("END OF RECEIPT", texts)

    def test_02_multiple_model_receipt(self):
        """Test receipt with multiple models across distinct configurations."""
        model_1 = ModelUsageSummary(
            provider="Anthropic",
            agent="Google Antigravity",
            model_display_name="Claude Opus 4.6 (Thinking)",
            model_id="claude-opus-4-6",
            input_tokens=185212,
            output_tokens=26445,
            cache_read_tokens=601260,
            total_tokens=211657,
            turn_count=10,
            input_cost_usd=Decimal("0.9261"),
            output_cost_usd=Decimal("0.6611"),
            cache_read_cost_usd=None,
            estimated_api_cost_usd=Decimal("1.5872"),
            pricing_status="partially_priced",
            pricing_notes="Unpriced components: cache-read tokens",
        )

        model_2 = ModelUsageSummary(
            provider="Google",
            agent="Google Antigravity",
            model_display_name="Gemini 3.8 Flash (Medium)",
            model_id="gemini-3.8-flash",
            input_tokens=293022,
            output_tokens=18839,
            cache_read_tokens=3203508,
            total_tokens=311861,
            turn_count=29,
            input_cost_usd=Decimal("0.2198"),
            output_cost_usd=Decimal("0.0706"),
            cache_read_cost_usd=Decimal("0.2403"),
            estimated_api_cost_usd=Decimal("0.5307"),
            pricing_status="preview_estimate",
        )

        metadata = ReceiptMetadata(
            receipt_id="rec-test-02",
            generated_at=self.now,
            timezone="UTC",
            session_id="session-multi-model-02",
            session_title="Mixed Model Session",
            elapsed_time_seconds=642.0,
        )

        receipt = Receipt(
            metadata=metadata,
            model_summaries=[model_1, model_2],
            total_input_tokens=478234,
            total_output_tokens=45284,
            total_cache_read_tokens=3804768,
            total_tokens=523518,
            total_turns=39,
            estimated_api_cost_usd=Decimal("2.1179"),
            pricing_status="partially_priced",
        )

        pdf_bytes = self.generator.generate_bytes(receipt)
        texts = extract_pdf_texts(pdf_bytes)

        self.assertTrue(any("Claude Opus 4.6 (Thinking)" in t for t in texts))
        self.assertTrue(any("Gemini 3.8 Flash (Medium)" in t for t in texts))
        self.assertIn("39", texts)
        self.assertTrue(any("$1.5872 USD" in t for t in texts))
        self.assertTrue(any("$0.5307 USD" in t for t in texts))
        self.assertTrue(any("$2.1179 USD" in t for t in texts))

    def test_03_multiple_agent_receipt(self):
        """Test receipt with multiple collaborating coding agents."""
        agent_1 = ModelUsageSummary(
            provider="Google",
            agent="Google Antigravity",
            model_display_name="Gemini 3.8 Flash (High)",
            model_id="gemini-3.8-flash",
            input_tokens=50000,
            output_tokens=10000,
            total_tokens=60000,
            turn_count=12,
            estimated_api_cost_usd=Decimal("0.0750"),
            pricing_status="verified",
        )

        agent_2 = ModelUsageSummary(
            provider="Anthropic",
            agent="Claude Code",
            model_display_name="Claude Sonnet 3.7",
            model_id="claude-sonnet-3-7",
            input_tokens=70000,
            output_tokens=15000,
            total_tokens=85000,
            turn_count=18,
            estimated_api_cost_usd=Decimal("0.4350"),
            pricing_status="verified",
        )

        metadata = ReceiptMetadata(
            receipt_id="rec-test-03",
            generated_at=self.now,
            timezone="UTC",
            session_id="session-multi-agent-03",
            session_title="Collaborative Agents Run",
        )

        receipt = Receipt(
            metadata=metadata,
            model_summaries=[agent_1, agent_2],
            total_input_tokens=120000,
            total_output_tokens=25000,
            total_tokens=145000,
            total_turns=30,
            estimated_api_cost_usd=Decimal("0.5100"),
            pricing_status="verified",
        )

        pdf_bytes = self.generator.generate_bytes(receipt)
        texts = extract_pdf_texts(pdf_bytes)

        # Both agents must be identified
        self.assertTrue(any("2 (Claude Code, Google Antigravity)" in t for t in texts))
        self.assertIn("Claude Code", texts)
        self.assertIn("Google Antigravity", texts)

    def test_04_partially_priced_model(self):
        """Test that partially priced models are clearly identified and unpriced items flagged."""
        summary = ModelUsageSummary(
            provider="Anthropic",
            agent="Google Antigravity",
            model_display_name="Claude Opus 4.6 (Thinking)",
            model_id="claude-opus-4-6",
            input_tokens=100000,
            output_tokens=10000,
            cache_read_tokens=50000,
            total_tokens=110000,
            turn_count=5,
            input_cost_usd=Decimal("0.5000"),
            output_cost_usd=Decimal("0.2500"),
            cache_read_cost_usd=None,  # Unverified equivalence
            estimated_api_cost_usd=Decimal("0.7500"),
            pricing_status="partially_priced",
            pricing_notes="Unpriced components: cache-read tokens",
        )

        metadata = ReceiptMetadata(
            receipt_id="rec-test-04",
            generated_at=self.now,
            timezone="UTC",
            session_id="session-partial-04",
        )

        receipt = Receipt(
            metadata=metadata,
            model_summaries=[summary],
            total_input_tokens=100000,
            total_output_tokens=10000,
            total_tokens=110000,
            total_turns=5,
            estimated_api_cost_usd=Decimal("0.7500"),
            pricing_status="partially_priced",
        )

        pdf_bytes = self.generator.generate_bytes(receipt)
        texts = extract_pdf_texts(pdf_bytes)

        self.assertIn("PARTIALLY_PRICED", texts)
        self.assertTrue(any("Unpriced components: cache-read tokens" in t for t in texts))

    def test_05_unavailable_cache_read_cost(self):
        """Test that missing cache-read cost is displayed as UNAVAILABLE, never $0.00."""
        summary = ModelUsageSummary(
            provider="Anthropic",
            agent="Google Antigravity",
            model_display_name="Claude Opus 4.6",
            model_id="claude-opus-4-6",
            input_tokens=50000,
            output_tokens=5000,
            cache_read_tokens=250000,
            total_tokens=55000,
            turn_count=3,
            input_cost_usd=Decimal("0.2500"),
            output_cost_usd=Decimal("0.1250"),
            cache_read_cost_usd=None,
            estimated_api_cost_usd=Decimal("0.3750"),
            pricing_status="partially_priced",
        )

        metadata = ReceiptMetadata(
            receipt_id="rec-test-05",
            generated_at=self.now,
            timezone="UTC",
            session_id="session-no-read-cost",
        )

        receipt = Receipt(
            metadata=metadata,
            model_summaries=[summary],
            total_input_tokens=50000,
            total_output_tokens=5000,
            total_cache_read_tokens=250000,
            total_tokens=55000,
            total_turns=3,
            estimated_api_cost_usd=Decimal("0.3750"),
            pricing_status="partially_priced",
        )

        pdf_bytes = self.generator.generate_bytes(receipt)
        texts = extract_pdf_texts(pdf_bytes)

        # UNAVAILABLE must be present; no $0.00 or $0.0000 should appear
        self.assertIn("UNAVAILABLE", texts)
        self.assertFalse(any("$0.0000" in t for t in texts))
        self.assertFalse(any("$0.00 USD" in t for t in texts))

    def test_06_unavailable_cache_write_cost(self):
        """Test that missing cache-write data is explicitly rendered as UNAVAILABLE."""
        summary = ModelUsageSummary(
            provider="Google",
            agent="Google Antigravity",
            model_display_name="Gemini 3.8 Flash",
            model_id="gemini-3.8-flash",
            input_tokens=20000,
            output_tokens=4000,
            cache_read_tokens=10000,
            cache_write_tokens=None,
            total_tokens=24000,
            turn_count=2,
            input_cost_usd=Decimal("0.0150"),
            output_cost_usd=Decimal("0.0150"),
            cache_read_cost_usd=Decimal("0.0008"),
            cache_write_cost_usd=None,
            estimated_api_cost_usd=Decimal("0.0308"),
            pricing_status="preview_estimate",
        )

        metadata = ReceiptMetadata(
            receipt_id="rec-test-06",
            generated_at=self.now,
            timezone="UTC",
            session_id="session-no-write",
        )

        receipt = Receipt(
            metadata=metadata,
            model_summaries=[summary],
            total_input_tokens=20000,
            total_output_tokens=4000,
            total_cache_read_tokens=10000,
            total_tokens=24000,
            total_turns=2,
            estimated_api_cost_usd=Decimal("0.0308"),
            pricing_status="preview_estimate",
        )

        pdf_bytes = self.generator.generate_bytes(receipt)
        texts = extract_pdf_texts(pdf_bytes)

        self.assertIn("UNAVAILABLE", texts)
        self.assertFalse(any("$0.0000" in t for t in texts))

    def test_07_missing_metadata(self):
        """Test graceful handling when optional metadata fields are None."""
        summary = ModelUsageSummary(
            provider="Google",
            agent="Google Antigravity",
            model_display_name="Gemini 3.8 Flash",
            model_id="gemini-3.8-flash",
            input_tokens=1000,
            output_tokens=200,
            total_tokens=1200,
            turn_count=1,
            estimated_api_cost_usd=Decimal("0.0015"),
            pricing_status="preview_estimate",
        )

        metadata = ReceiptMetadata(
            receipt_id="rec-test-07",
            generated_at=self.now,
            timezone="UTC",
            session_id="session-missing-metadata",
            session_title=None,
            elapsed_time_seconds=None,
        )

        receipt = Receipt(
            metadata=metadata,
            model_summaries=[summary],
            total_input_tokens=1000,
            total_output_tokens=200,
            total_tokens=1200,
            total_turns=1,
            estimated_api_cost_usd=Decimal("0.0015"),
            pricing_status="preview_estimate",
        )

        # Must not raise an exception
        pdf_bytes = self.generator.generate_bytes(receipt)
        texts = extract_pdf_texts(pdf_bytes)

        self.assertIn("UNAVAILABLE", texts)
        self.assertIn("N/A", texts)

    def test_08_long_receipt_with_pagination(self):
        """Test that long multi-model receipts trigger automatic multi-page pagination."""
        summaries = []
        for i in range(1, 6):
            summaries.append(
                ModelUsageSummary(
                    provider="Google",
                    agent="Google Antigravity",
                    model_display_name=f"Gemini Sub-Agent Model {i}",
                    model_id="gemini-3.8-flash",
                    input_tokens=50000 * i,
                    output_tokens=10000 * i,
                    cache_read_tokens=200000 * i,
                    total_tokens=60000 * i,
                    turn_count=10 * i,
                    input_cost_usd=Decimal(f"{0.0375 * i:.4f}"),
                    output_cost_usd=Decimal(f"{0.0375 * i:.4f}"),
                    cache_read_cost_usd=Decimal(f"{0.0150 * i:.4f}"),
                    estimated_api_cost_usd=Decimal(f"{0.0900 * i:.4f}"),
                    pricing_status="preview_estimate",
                    pricing_notes="Introductory preview pricing tier",
                )
            )

        metadata = ReceiptMetadata(
            receipt_id="rec-test-08-pagination",
            generated_at=self.now,
            timezone="UTC",
            session_id="session-long-multi-page",
            session_title="Extensive Agent Swarm Session",
            elapsed_time_seconds=3600.0,
        )

        total_in = sum(s.input_tokens for s in summaries)
        total_out = sum(s.output_tokens for s in summaries)
        total_read = sum(s.cache_read_tokens for s in summaries)
        total_tok = sum(s.total_tokens for s in summaries)
        total_trn = sum(s.turn_count for s in summaries)
        total_cost = sum(s.estimated_api_cost_usd for s in summaries)

        receipt = Receipt(
            metadata=metadata,
            model_summaries=summaries,
            total_input_tokens=total_in,
            total_output_tokens=total_out,
            total_cache_read_tokens=total_read,
            total_tokens=total_tok,
            total_turns=total_trn,
            estimated_api_cost_usd=total_cost,
            pricing_status="preview_estimate",
        )

        pdf_bytes = self.generator.generate_bytes(receipt)
        page_matches = re.findall(rb"/Type\s*/Page\b", pdf_bytes)
        self.assertGreater(len(page_matches), 1, "Long receipt should paginate to at least 2 pages")

        texts = extract_pdf_texts(pdf_bytes)
        # Continuation header and page indicators must be present
        self.assertTrue(any("AGENT TOKEN RECEIPT (CONT.)" in t for t in texts))
        self.assertTrue(any("Page 2 of" in t for t in texts))

    def test_09_decimal_cost_formatting(self):
        """Test exact Decimal cost formatting and currency presentation."""
        summary = ModelUsageSummary(
            provider="Google",
            agent="Google Antigravity",
            model_display_name="Gemini 3.8 Flash",
            model_id="gemini-3.8-flash",
            input_tokens=123456,
            output_tokens=78910,
            total_tokens=202366,
            turn_count=10,
            input_cost_usd=Decimal("0.092592"),
            output_cost_usd=Decimal("0.295912"),
            estimated_api_cost_usd=Decimal("0.388504"),
            pricing_status="verified",
        )

        metadata = ReceiptMetadata(
            receipt_id="rec-test-09",
            generated_at=self.now,
            timezone="UTC",
            session_id="session-decimal-format",
        )

        receipt = Receipt(
            metadata=metadata,
            model_summaries=[summary],
            total_input_tokens=123456,
            total_output_tokens=78910,
            total_tokens=202366,
            total_turns=10,
            estimated_api_cost_usd=Decimal("0.388504"),
            pricing_status="verified",
        )

        pdf_bytes = self.generator.generate_bytes(receipt)
        texts = extract_pdf_texts(pdf_bytes)

        # 4-decimal place financial rounding
        self.assertTrue(any("$0.0926 USD" in t for t in texts))
        self.assertTrue(any("$0.2959 USD" in t for t in texts))
        self.assertTrue(any("$0.3885 USD" in t for t in texts))

    def test_10_correct_total_turn_counts(self):
        """Test that turn counts per model and overall match accurately."""
        m1 = ModelUsageSummary(
            provider="Anthropic",
            agent="Google Antigravity",
            model_display_name="Claude Opus 4.6",
            model_id="claude-opus-4-6",
            input_tokens=1000,
            output_tokens=200,
            total_tokens=1200,
            turn_count=10,
            estimated_api_cost_usd=Decimal("0.0100"),
            pricing_status="partially_priced",
        )
        m2 = ModelUsageSummary(
            provider="Google",
            agent="Google Antigravity",
            model_display_name="Gemini 3.8 Flash (Medium)",
            model_id="gemini-3.8-flash",
            input_tokens=2000,
            output_tokens=400,
            total_tokens=2400,
            turn_count=29,
            estimated_api_cost_usd=Decimal("0.0030"),
            pricing_status="preview_estimate",
        )
        m3 = ModelUsageSummary(
            provider="Google",
            agent="Google Antigravity",
            model_display_name="Gemini 3.8 Flash (High)",
            model_id="gemini-3.8-flash",
            input_tokens=3000,
            output_tokens=600,
            total_tokens=3600,
            turn_count=46,
            estimated_api_cost_usd=Decimal("0.0045"),
            pricing_status="preview_estimate",
        )

        metadata = ReceiptMetadata(
            receipt_id="rec-test-10",
            generated_at=self.now,
            timezone="UTC",
            session_id="session-turns-audit",
        )

        receipt = Receipt(
            metadata=metadata,
            model_summaries=[m1, m2, m3],
            total_input_tokens=6000,
            total_output_tokens=1200,
            total_tokens=7200,
            total_turns=85,
            estimated_api_cost_usd=Decimal("0.0175"),
            pricing_status="partially_priced",
        )

        pdf_bytes = self.generator.generate_bytes(receipt)
        texts = extract_pdf_texts(pdf_bytes)

        # Per model turns
        self.assertIn("10", texts)
        self.assertIn("29", texts)
        self.assertIn("46", texts)
        # Total turns
        self.assertIn("85", texts)

    def test_11_filename_unique_and_no_overwrite(self):
        """Test that generate() creates unique filenames and never overwrites existing receipts."""
        summary = ModelUsageSummary(
            provider="Google",
            agent="Google Antigravity",
            model_display_name="Gemini 3.8 Flash",
            model_id="gemini-3.8-flash",
            input_tokens=1000,
            output_tokens=200,
            total_tokens=1200,
            turn_count=1,
            estimated_api_cost_usd=Decimal("0.0015"),
            pricing_status="preview_estimate",
        )

        metadata = ReceiptMetadata(
            receipt_id="rec-unique-test",
            generated_at=self.now,
            timezone="UTC",
            session_id="session-unique-test",
        )

        receipt = Receipt(
            metadata=metadata,
            model_summaries=[summary],
            total_input_tokens=1000,
            total_output_tokens=200,
            total_tokens=1200,
            total_turns=1,
            estimated_api_cost_usd=Decimal("0.0015"),
            pricing_status="preview_estimate",
        )

        path_1 = self.generator.generate(receipt, filename="receipt_test.pdf")
        self.assertTrue(path_1.exists())

        # Attempt to write with the exact same filename
        path_2 = self.generator.generate(receipt, filename="receipt_test.pdf")
        self.assertTrue(path_2.exists())
        self.assertNotEqual(path_1, path_2)
        self.assertEqual(path_2.name, "receipt_test_1.pdf")

    def test_12_single_page_omits_pagination_indicators(self):
        """Test that single-page receipts do not show redundant 'Page 1 of 1' headers."""
        summary = ModelUsageSummary(
            provider="Google",
            agent="Google Antigravity",
            model_display_name="Gemini 3.8 Flash",
            model_id="gemini-3.8-flash",
            input_tokens=1000,
            output_tokens=200,
            total_tokens=1200,
            turn_count=1,
            estimated_api_cost_usd=Decimal("0.0015"),
            pricing_status="preview_estimate",
        )

        metadata = ReceiptMetadata(
            receipt_id="rec-single-page",
            generated_at=self.now,
            timezone="UTC",
            session_id="session-single-page",
        )

        receipt = Receipt(
            metadata=metadata,
            model_summaries=[summary],
            total_input_tokens=1000,
            total_output_tokens=200,
            total_tokens=1200,
            total_turns=1,
            estimated_api_cost_usd=Decimal("0.0015"),
            pricing_status="preview_estimate",
        )

        pdf_bytes = self.generator.generate_bytes(receipt)
        page_matches = re.findall(rb"/Type\s*/Page\b", pdf_bytes)
        self.assertEqual(len(page_matches), 1)

        texts = extract_pdf_texts(pdf_bytes)
        self.assertFalse(any("AGENT TOKEN RECEIPT (CONT.)" in t for t in texts))
        self.assertFalse(any("Page 1 of" in t for t in texts))

    def test_13_input_output_tokens_label_presentation(self):
        """Test that combined tokens are strictly labeled 'Input + Output Tokens:' and 'Grand Total Tokens:' is not used."""
        summary = ModelUsageSummary(
            provider="Google",
            agent="Google Antigravity",
            model_display_name="Gemini 3.8 Flash (High)",
            model_id="gemini-3.8-flash",
            input_tokens=100000,
            output_tokens=20000,
            cache_read_tokens=500000,
            total_tokens=120000,
            turn_count=10,
            estimated_api_cost_usd=Decimal("0.1875"),
            pricing_status="verified",
        )
        metadata = ReceiptMetadata(
            receipt_id="rec-test-13",
            generated_at=self.now,
            timezone="UTC",
            session_id="session-tokens-label",
        )
        receipt = Receipt(
            metadata=metadata,
            model_summaries=[summary],
            total_input_tokens=100000,
            total_output_tokens=20000,
            total_cache_read_tokens=500000,
            total_tokens=120000,
            total_turns=10,
            estimated_api_cost_usd=Decimal("0.1875"),
            pricing_status="verified",
        )

        pdf_bytes = self.generator.generate_bytes(receipt)
        texts = extract_pdf_texts(pdf_bytes)

        # Label must be 'Input + Output Tokens:'
        self.assertIn("Input + Output Tokens:", texts)
        # Old labels must NOT be present
        self.assertFalse(any("Grand Total Tokens" in t for t in texts))
        self.assertFalse(any("Combined Tokens" in t for t in texts))
        # Cache-read tokens must remain displayed separately
        self.assertIn("Cache-Read Tokens:", texts)
        self.assertIn("500,000", texts)
        # Combined value must be 120,000 (100,000 + 20,000), excluding cache_read_tokens
        self.assertIn("120,000", texts)


if __name__ == "__main__":
    unittest.main()
