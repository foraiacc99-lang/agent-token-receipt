"""Thermal-printer-style PDF receipt generator for Agent Token Receipt.

Adheres strictly to Phase 4 specifications:
- Minimalist, monochrome, authentic 80mm thermal receipt appearance.
- Monospace Courier typography with exact character and column alignment.
- Zero-fabrication data integrity:
  * Strict Decimal precision for all financial values.
  * Preserves None / unavailable states (displays 'UNAVAILABLE' or 'N/A', never '$0.00').
  * Clear distinction between estimated API-equivalent costs and actual billing.
- Supports multi-agent and multi-model sessions.
- Automatic pagination with continuation headers and page numbers when multiple pages are generated.
- Section-aware spacing (`ensure_space`) preventing awkward element splitting.
- Unique receipt filename generation preventing accidental overwrites.
"""

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import List, Optional, Union
import re

from fpdf import FPDF
from core.models import ModelUsageSummary, Receipt


class ThermalReceiptPDF(FPDF):
    """Custom FPDF document tailored for authentic 80mm thermal receipts."""

    def __init__(
        self,
        show_page_numbers: bool = False,
        width_mm: float = 80.0,
        page_height_mm: float = 250.0,
        margin_mm: float = 4.0,
        *args,
        **kwargs,
    ):
        super().__init__(unit="mm", format=(width_mm, page_height_mm), *args, **kwargs)
        self.show_page_numbers = show_page_numbers
        self.width_mm = width_mm
        self.page_height_mm = page_height_mm
        self.margin_mm = margin_mm
        self.printable_width = width_mm - (2 * margin_mm)

        self.alias_nb_pages()
        self.set_margins(margin_mm, margin_mm, margin_mm)
        self.set_auto_page_break(auto=True, margin=8.0)
        self.set_text_color(0, 0, 0)
        self.set_draw_color(0, 0, 0)

    def header(self):
        """Prints a thermal continuation header on pages 2 and later."""
        if self.page_no() > 1:
            self.set_font("Courier", "B", 7.5)
            self.cell(0, 3.2, "=" * 42, align="C", new_x="LMARGIN", new_y="NEXT")
            self.cell(0, 3.5, "AGENT TOKEN RECEIPT (CONT.)", align="C", new_x="LMARGIN", new_y="NEXT")
            if self.show_page_numbers:
                self.set_font("Courier", "", 7.0)
                self.cell(0, 3.2, f"Page {self.page_no()} of {{nb}}", align="C", new_x="LMARGIN", new_y="NEXT")
            self.set_font("Courier", "B", 7.5)
            self.cell(0, 3.2, "=" * 42, align="C", new_x="LMARGIN", new_y="NEXT")
            self.ln(1.5)

    def footer(self):
        """Prints bottom page indicator on multi-page receipts."""
        if self.show_page_numbers:
            self.set_y(-6.0)
            self.set_font("Courier", "", 6.5)
            self.cell(0, 3.0, f"- Page {self.page_no()} of {{nb}} -", align="C")

    # --- Thermal Layout Helper Methods ---

    def ensure_space(self, min_space_mm: float):
        """Adds a page break if remaining vertical space on current page is less than min_space_mm."""
        # 8mm is bottom margin
        if self.get_y() > (self.page_height_mm - 8.0 - min_space_mm):
            self.add_page()

    def print_centered(self, text: str, bold: bool = False, size: float = 7.5, h: float = 3.5):
        """Prints a centered line of monospace text."""
        self.set_font("Courier", "B" if bold else "", size)
        self.cell(0, h, text, align="C", new_x="LMARGIN", new_y="NEXT")

    def print_separator(self, char: str = "=", length: int = 42, h: float = 3.0, size: float = 7.5):
        """Prints a full-width monospace separator line."""
        self.set_font("Courier", "", size)
        self.cell(0, h, char * length, align="C", new_x="LMARGIN", new_y="NEXT")

    def print_row(
        self,
        label: str,
        value: str,
        bold_val: bool = False,
        bold_label: bool = False,
        size: float = 7.5,
        h: float = 3.4,
        label_w: float = 40.0,
        val_w: float = 32.0,
    ):
        """Prints a two-column key-value row with right-aligned value.
        
        If label or value exceeds column bounds, prints label on line 1 and indented value on line 2.
        """
        self.set_font("Courier", "B" if bold_label else "", size)
        lbl_w = self.get_string_width(label)
        
        self.set_font("Courier", "B" if bold_val else "", size)
        val_w_actual = self.get_string_width(value)

        # Check if row fits side-by-side cleanly within column allocations
        if lbl_w > (label_w - 1.0) or val_w_actual > (val_w - 0.5):
            # Print label on first line
            self.set_font("Courier", "B" if bold_label else "", size)
            self.cell(0, h, label, new_x="LMARGIN", new_y="NEXT")
            # Print value on second line indented
            self.set_font("Courier", "B" if bold_val else "", size)
            self.cell(0, h, f"  {value}", new_x="LMARGIN", new_y="NEXT")
        else:
            # Print label in left cell
            self.set_font("Courier", "B" if bold_label else "", size)
            self.cell(label_w, h, label, align="L")
            # Print value in right cell
            self.set_font("Courier", "B" if bold_val else "", size)
            self.cell(val_w, h, value, align="R", new_x="LMARGIN", new_y="NEXT")

    def print_multiline(self, text: str, prefix: str = "", size: float = 7.0, h: float = 3.2):
        """Prints wrapped text within the printable area."""
        self.set_font("Courier", "", size)
        full_text = f"{prefix}{text}" if prefix else text
        self.multi_cell(0, h, full_text, new_x="LMARGIN", new_y="NEXT")


class ReceiptPDFGenerator:
    """Generates thermal-style PDF receipts from canonical Receipt objects."""

    def __init__(
        self,
        output_dir: Optional[Union[str, Path]] = None,
        width_mm: float = 80.0,
        page_height_mm: float = 250.0,
        margin_mm: float = 4.0,
    ):
        self.output_dir = Path(output_dir) if output_dir else (Path.cwd() / "receipts")
        self.width_mm = width_mm
        self.page_height_mm = page_height_mm
        self.margin_mm = margin_mm

    @staticmethod
    def extract_thinking_config(display_name: str, reasoning_tokens: Optional[int]) -> str:
        """Extracts readable thinking configuration from model display name or reasoning tokens."""
        dn_lower = display_name.lower()
        if "(high)" in dn_lower:
            return "Thinking: HIGH"
        elif "(medium)" in dn_lower:
            return "Thinking: MEDIUM"
        elif "(low)" in dn_lower:
            return "Thinking: LOW"
        elif "(thinking)" in dn_lower or "thinking" in dn_lower:
            return "Thinking: ON"
        elif reasoning_tokens is not None and reasoning_tokens > 0:
            return f"Thinking: {reasoning_tokens:,} tokens"
        return "N/A"

    @staticmethod
    def format_tokens(val: Optional[int]) -> str:
        """Formats integer token count with commas, or 'UNAVAILABLE' if None."""
        if val is None:
            return "UNAVAILABLE"
        return f"{val:,}"

    @staticmethod
    def format_cost(val: Optional[Decimal], currency: str = "USD") -> str:
        """Formats Decimal monetary value to 4 decimal places, or 'UNAVAILABLE' if None."""
        if val is None:
            return "UNAVAILABLE"
        return f"${val:.4f} {currency}"

    @staticmethod
    def format_duration(seconds: Optional[float]) -> str:
        """Formats elapsed duration into a human-readable string, or 'UNAVAILABLE' if None."""
        if seconds is None:
            return "UNAVAILABLE"
        if seconds < 60.0:
            return f"{seconds:.1f}s"
        mins = int(seconds // 60)
        secs = seconds % 60
        return f"{seconds:.1f}s ({mins}m {secs:04.1f}s)"

    def _render_receipt_content(self, pdf: ThermalReceiptPDF, receipt: Receipt):
        """Constructs and draws the full receipt sections into the given ThermalReceiptPDF document."""
        pdf.add_page()

        # ---------------------------------------------------------
        # 1. HEADER
        # ---------------------------------------------------------
        pdf.print_centered("AGENT TOKEN RECEIPT", bold=True, size=10.0, h=4.2)
        pdf.print_centered("Every token has a receipt.", bold=False, size=7.5, h=3.4)
        if pdf.show_page_numbers:
            pdf.print_centered(f"Page {pdf.page_no()} of {{nb}}", bold=False, size=7.0, h=3.0)
        pdf.print_separator(char="=", length=42, h=3.0)

        # ---------------------------------------------------------
        # 2. RECEIPT INFORMATION
        # ---------------------------------------------------------
        pdf.print_centered("RECEIPT INFORMATION", bold=True, size=8.0, h=3.8)
        pdf.print_row("Receipt ID:", receipt.metadata.receipt_id)
        
        # Generated timestamp
        gen_dt = receipt.metadata.generated_at
        gen_str = gen_dt.strftime("%Y-%m-%d %H:%M:%S")
        pdf.print_row("Generated At:", gen_str)
        pdf.print_row("Timezone:", receipt.metadata.timezone)
        
        # Duration
        dur_str = self.format_duration(receipt.metadata.elapsed_time_seconds)
        pdf.print_row("Session Duration:", dur_str)
        
        # Session & Project Identifiers
        pdf.print_row("Session ID:", receipt.metadata.session_id)
        if receipt.metadata.session_title:
            pdf.print_row("Session Title:", receipt.metadata.session_title)
        else:
            pdf.print_row("Session Title:", "N/A")

        # Agents count (include unavailable active platforms cleanly without defaulting wrongly)
        active_agents = {s.agent for s in receipt.model_summaries if s.agent}
        unavailable_list = getattr(receipt, "unavailable_agents", []) or []
        unavail_agents = {u.get("agent") for u in unavailable_list if u.get("agent")}
        agents = sorted(active_agents | unavail_agents)
        agent_count = len(agents) if agents else 1
        agent_names = ", ".join(agents) if agents else "Google Antigravity"
        pdf.print_row("Active Agents:", f"{agent_count} ({agent_names})")
        pdf.print_row("Total Turns:", f"{receipt.total_turns:,}")
        pdf.print_separator(char="-", length=42, h=3.0)

        # ---------------------------------------------------------
        # 3. AGENT AND MODEL BREAKDOWN
        # ---------------------------------------------------------
        pdf.print_centered("MODEL & AGENT BREAKDOWN", bold=True, size=8.0, h=3.8)
        
        num_models = len(receipt.model_summaries)
        for idx, s in enumerate(receipt.model_summaries, start=1):
            # Ensure sufficient vertical space for model header and basic rows
            pdf.ensure_space(38.0)
            pdf.print_centered(f"[ MODEL {idx} OF {num_models} ]", bold=True, size=7.5, h=3.4)
            pdf.print_row("Model Name:", s.model_display_name, bold_label=True)
            pdf.print_row("Provider:", s.provider)
            pdf.print_row("Agent:", s.agent)
            pdf.print_row("Canonical ID:", s.model_id or "N/A")
            
            thinking_str = self.extract_thinking_config(s.model_display_name, s.reasoning_tokens)
            pdf.print_row("Thinking Config:", thinking_str)
            pdf.print_row("Generation Turns:", f"{s.turn_count:,}")

            # Token Breakdown
            pdf.print_separator(char="- ", length=21, h=2.5)
            pdf.print_row("Input Tokens:", f"{s.input_tokens:,}")
            pdf.print_row("Output Tokens:", f"{s.output_tokens:,}")
            pdf.print_row("Cache-Read Tokens:", self.format_tokens(s.cache_read_tokens))
            pdf.print_row("Cache-Write Tokens:", self.format_tokens(s.cache_write_tokens))
            if s.reasoning_tokens is not None and s.reasoning_tokens > 0:
                pdf.print_row("Reasoning Tokens:", f"{s.reasoning_tokens:,}")
            pdf.print_row("Input + Output Tokens:", f"{s.total_tokens:,}")

            # Cost Breakdown for this model
            pdf.print_separator(char="- ", length=21, h=2.5)
            pdf.print_row("Input Token Cost:", self.format_cost(s.input_cost_usd))
            pdf.print_row("Output Token Cost:", self.format_cost(s.output_cost_usd))
            pdf.print_row("Cache-Read Cost:", self.format_cost(s.cache_read_cost_usd))
            pdf.print_row("Cache-Write Cost:", self.format_cost(s.cache_write_cost_usd))
            pdf.print_row("Cache-Storage Cost:", self.format_cost(s.cache_storage_cost_usd))
            pdf.print_row("Model Subtotal:", self.format_cost(s.estimated_api_cost_usd), bold_val=True)
            pdf.print_row("Pricing Status:", s.pricing_status.upper())

            if s.pricing_notes:
                pdf.print_multiline(f"* Note: {s.pricing_notes}", size=6.5, h=3.0)

            if idx < num_models:
                pdf.print_separator(char="-", length=42, h=3.0)

        for u_idx, unavail in enumerate(unavailable_list):
            if num_models > 0 or u_idx > 0:
                pdf.print_separator(char="-", length=42, h=3.0)
            pdf.ensure_space(28.0)
            pdf.print_centered("[ UNAVAILABLE TELEMETRY ]", bold=True, size=7.5, h=3.4)
            pdf.print_row("Agent:", unavail.get("agent", "Unknown Agent"), bold_label=True)
            pdf.print_row("Model:", unavail.get("model", "Unavailable"))
            pdf.print_row("Input Tokens:", unavail.get("input_tokens", "Unavailable"))
            pdf.print_row("Output Tokens:", unavail.get("output_tokens", "Unavailable"))
            reason = unavail.get("reason")
            if reason:
                pdf.print_multiline(f"* Note: {reason}", size=6.5, h=3.0)

        # ---------------------------------------------------------
        # 4. OVERALL USAGE & COST BREAKDOWN
        # ---------------------------------------------------------
        pdf.ensure_space(42.0)
        pdf.print_separator(char="=", length=42, h=3.0)
        pdf.print_centered("TOTAL USAGE & COST BREAKDOWN", bold=True, size=8.0, h=3.8)
        
        pdf.print_row("Total Turns:", f"{receipt.total_turns:,}")
        pdf.print_row("Total Input Tokens:", f"{receipt.total_input_tokens:,}")
        pdf.print_row("Total Output Tokens:", f"{receipt.total_output_tokens:,}")
        pdf.print_row("Total Cache-Read:", self.format_tokens(receipt.total_cache_read_tokens))
        pdf.print_row("Input + Output Tokens:", f"{receipt.total_tokens:,}", bold_val=True)
        pdf.print_separator(char="-", length=42, h=3.0)

        # Sum component costs
        in_costs = [s.input_cost_usd for s in receipt.model_summaries if s.input_cost_usd is not None]
        out_costs = [s.output_cost_usd for s in receipt.model_summaries if s.output_cost_usd is not None]
        read_costs = [s.cache_read_cost_usd for s in receipt.model_summaries if s.cache_read_cost_usd is not None]
        write_costs = [s.cache_write_cost_usd for s in receipt.model_summaries if s.cache_write_cost_usd is not None]

        tot_in_cost = sum(in_costs) if in_costs else None
        tot_out_cost = sum(out_costs) if out_costs else None
        tot_read_cost = sum(read_costs) if read_costs else None
        tot_write_cost = sum(write_costs) if write_costs else None

        pdf.print_row("Input Token Cost:", self.format_cost(tot_in_cost))
        pdf.print_row("Output Token Cost:", self.format_cost(tot_out_cost))
        pdf.print_row("Cache-Read Cost:", self.format_cost(tot_read_cost))
        pdf.print_row("Cache-Write Cost:", self.format_cost(tot_write_cost))
        pdf.print_row("Cache-Storage Cost:", "UNAVAILABLE")

        pdf.print_separator(char="=", length=42, h=3.0)
        pdf.print_row("ESTIMATED API TOTAL:", self.format_cost(receipt.estimated_api_cost_usd), bold_val=True, bold_label=True, size=8.0)
        pdf.print_row("Pricing Status:", receipt.pricing_status.upper(), bold_val=True)
        
        billed_str = self.format_cost(receipt.actual_billed_amount_usd) if receipt.actual_billed_amount_usd is not None else "None (Unbilled locally)"
        pdf.print_row("Actual Billed Amount:", billed_str)
        pdf.print_separator(char="-", length=42, h=3.0)

        # Footnote distinguishing estimate vs billed
        if agents and set(agents) != {"Google Antigravity"}:
            footnote_text = (
                "* Estimated API-equivalent cost based on published rates. Not an actual bill. "
                "Local coding-agent sessions may use API keys, subscriptions, or preview credits."
            )
        else:
            footnote_text = (
                "* Estimated API-equivalent cost based on published rates. Not an actual charge. "
                "Antigravity local sessions run on preview/subscription credits and are not billed per-token."
            )
        pdf.print_multiline(
            footnote_text,
            size=6.5,
            h=2.8,
        )
        pdf.print_separator(char="=", length=42, h=3.0)

        # ---------------------------------------------------------
        # 5. FOOTER
        # ---------------------------------------------------------
        pdf.ensure_space(25.0)
        pdf.print_centered("THANK YOU FOR BUILDING!", bold=True, size=8.0, h=3.6)
        pdf.print_centered("KEEP BUILDING. KEEP SHIPPING.", bold=False, size=7.5, h=3.2)
        pdf.ln(1.0)
        pdf.print_centered("Generated by Agent Token Receipt.", bold=False, size=7.0, h=3.0)
        pdf.print_centered("github.com/agent-token-receipt/agent-token-receipt", bold=False, size=6.5, h=2.8)
        pdf.ln(1.0)
        pdf.print_centered("END OF RECEIPT", bold=True, size=7.5, h=3.2)
        pdf.print_separator(char="=", length=42, h=3.0)

    def generate(self, receipt: Receipt, filename: Optional[str] = None) -> Path:
        """Generates and writes a thermal PDF receipt to disk with a guaranteed unique filename."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        if not filename:
            clean_rec_id = re.sub(r"[^a-zA-Z0-9_\-]", "", receipt.metadata.receipt_id)[:8]
            clean_session = re.sub(r"[^a-zA-Z0-9_\-]", "", receipt.metadata.session_id)[:8]
            ts_str = receipt.metadata.generated_at.strftime("%Y%m%d_%H%M%S")
            base_name = f"receipt_{clean_session}_{clean_rec_id}_{ts_str}.pdf"
        else:
            base_name = filename if filename.endswith(".pdf") else f"{filename}.pdf"

        # Determine non-colliding file destination
        dest_path = self.output_dir / base_name
        counter = 1
        stem = dest_path.stem
        while dest_path.exists():
            dest_path = self.output_dir / f"{stem}_{counter}.pdf"
            counter += 1

        pdf_bytes = self.generate_bytes(receipt)
        with open(dest_path, "wb") as f:
            f.write(pdf_bytes)

        return dest_path

    def generate_bytes(self, receipt: Receipt) -> bytes:
        """Generates thermal PDF receipt and returns raw PDF bytes (two-pass pagination aware)."""
        # Pass 1: Render with show_page_numbers=False to detect multi-page overflow
        pdf = ThermalReceiptPDF(
            show_page_numbers=False,
            width_mm=self.width_mm,
            page_height_mm=self.page_height_mm,
            margin_mm=self.margin_mm,
        )
        self._render_receipt_content(pdf, receipt)

        # Pass 2: If multi-page detected, re-render with show_page_numbers=True to display page indicators
        if pdf.pages_count > 1:
            pdf = ThermalReceiptPDF(
                show_page_numbers=True,
                width_mm=self.width_mm,
                page_height_mm=self.page_height_mm,
                margin_mm=self.margin_mm,
            )
            self._render_receipt_content(pdf, receipt)

        return bytes(pdf.output())
