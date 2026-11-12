"""Pricing catalogue and Decimal cost calculator for Agent Token Receipt.

Adheres strictly to Phase 3 & Phase 3.1 requirements:
- Exact Python Decimal precision for all financial operations.
- Separates actual billed amount (strictly None for local sessions) from estimated API-equivalent costs.
- Supports pricing statuses:
  * 'verified': Official published API rates verified from primary documentation.
  * 'preview_estimate': Estimated rates for preview or introductory models.
  * 'partially_priced': Some token categories priced, others missing/unpriced.
  * 'unknown_model': Unmapped or unrecognized model ID.
  * 'unknown_price': Recognized model but no published pricing.
  * 'unavailable': No pricing rate catalogued.
- Context window tiered pricing (e.g. <= 128k vs > 128k or <= 200k vs > 200k).
- Never defaults unknown costs to $0.
- Guarantees that uncached input tokens and cached tokens are accounted for separately.
"""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from core.models import CanonicalUsageRecord, ModelUsageSummary, Receipt


class PricingCatalogue:
    """Manages the versioned pricing catalogue."""

    def __init__(self, catalogue_data: Optional[Dict[str, Any]] = None, catalogue_path: Optional[Union[str, Path]] = None):
        if catalogue_data is not None:
            self._data = catalogue_data
        else:
            path = Path(catalogue_path) if catalogue_path else (Path(__file__).parent / "catalogue.json")
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            else:
                self._data = {"models": {}, "default_currency": "USD", "version": "unknown"}

        self.models: Dict[str, Dict[str, Any]] = self._data.get("models", {})
        self.version: str = self._data.get("version", "unknown")
        self.default_currency: str = self._data.get("default_currency", "USD")

    def get_model_entry(self, model_id: Optional[str]) -> Optional[Dict[str, Any]]:
        """Looks up a model's pricing definition by canonical ID."""
        if not model_id:
            return None
        return self.models.get(model_id.lower().strip())


class CostCalculator:
    """Calculates estimated API-equivalent costs with exact Decimal precision."""

    def __init__(self, catalogue: Optional[PricingCatalogue] = None):
        self.catalogue = catalogue or PricingCatalogue()

    def get_effective_rates(
        self,
        entry: Dict[str, Any],
        context_tokens: Optional[int] = None,
    ) -> Tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal], Optional[Decimal]]:
        """Resolves (input_rate, output_rate, cache_read_rate, cache_write_rate) as Decimals.
        
        Evaluates context window tiers if defined and context_tokens is provided.
        Falls back to base rates otherwise.
        """
        raw_in = entry.get("input_price_per_million")
        raw_out = entry.get("output_price_per_million")
        raw_read = entry.get("cache_read_price_per_million")
        raw_write = entry.get("cache_write_price_per_million")

        tiers = entry.get("tiers")
        if tiers and context_tokens is not None:
            for tier in tiers:
                thresh = tier.get("threshold_tokens", 128000)
                cond = tier.get("condition", "<=")
                if cond == "<=" and context_tokens <= thresh:
                    raw_in = tier.get("input_price_per_million", raw_in)
                    raw_out = tier.get("output_price_per_million", raw_out)
                    raw_read = tier.get("cache_read_price_per_million", raw_read)
                    raw_write = tier.get("cache_write_price_per_million", raw_write)
                    break
                elif cond == ">" and context_tokens > thresh:
                    raw_in = tier.get("input_price_per_million", raw_in)
                    raw_out = tier.get("output_price_per_million", raw_out)
                    raw_read = tier.get("cache_read_price_per_million", raw_read)
                    raw_write = tier.get("cache_write_price_per_million", raw_write)
                    break

        dec_in = Decimal(str(raw_in)) if raw_in is not None else None
        dec_out = Decimal(str(raw_out)) if raw_out is not None else None
        dec_read = Decimal(str(raw_read)) if raw_read is not None else None
        dec_write = Decimal(str(raw_write)) if raw_write is not None else None

        return dec_in, dec_out, dec_read, dec_write

    def calculate_turn_cost(
        self,
        record: CanonicalUsageRecord,
    ) -> Dict[str, Optional[Decimal]]:
        """Calculates exact costs for a single turn or request using tiered rates."""
        entry = self.catalogue.get_model_entry(record.model_id)
        if not entry:
            return {
                "input_cost": None,
                "output_cost": None,
                "cache_read_cost": None,
                "cache_write_cost": None,
                "total_cost": None,
            }

        # Effective prompt context length on this turn = uncached input + cached context
        turn_context = record.input_tokens + (record.cache_read_tokens or 0)
        in_rate, out_rate, read_rate, write_rate = self.get_effective_rates(entry, context_tokens=turn_context)

        one_million = Decimal("1000000")
        in_cost = (Decimal(record.input_tokens) * in_rate / one_million) if in_rate is not None else None
        out_cost = (Decimal(record.output_tokens) * out_rate / one_million) if out_rate is not None else None
        read_cost = (Decimal(record.cache_read_tokens) * read_rate / one_million) if (read_rate is not None and record.cache_read_tokens) else None
        write_cost = (Decimal(record.cache_write_tokens) * write_rate / one_million) if (write_rate is not None and record.cache_write_tokens) else None

        priced = [c for c in (in_cost, out_cost, read_cost, write_cost) if c is not None]
        total_cost = sum(priced) if priced else None

        return {
            "input_cost": in_cost,
            "output_cost": out_cost,
            "cache_read_cost": read_cost,
            "cache_write_cost": write_cost,
            "total_cost": total_cost,
        }

    def calculate_model_cost_from_records(
        self,
        records: List[CanonicalUsageRecord],
        summary: ModelUsageSummary,
    ) -> ModelUsageSummary:
        """Calculates model cost by summing turn-by-turn costs across individual records.
        
        This accurately captures context window tiering on turns that exceed threshold limits.
        Falls back to summary-level calculation if records are empty.
        """
        if not records:
            return self.calculate_model_cost(summary)

        model_id = summary.model_id
        if not model_id or model_id.strip().lower() == "unknown":
            summary.pricing_status = "unknown_model"
            summary.pricing_notes = f"Model ID unmapped for display name '{summary.model_display_name}'"
            summary.input_cost_usd = None
            summary.output_cost_usd = None
            summary.cache_read_cost_usd = None
            summary.cache_write_cost_usd = None
            summary.estimated_api_cost_usd = None
            return summary

        entry = self.catalogue.get_model_entry(model_id)
        if not entry:
            summary.pricing_status = "unavailable"
            summary.pricing_notes = f"No pricing rate catalogued for model ID '{model_id}'"
            summary.input_cost_usd = None
            summary.output_cost_usd = None
            summary.cache_read_cost_usd = None
            summary.cache_write_cost_usd = None
            summary.estimated_api_cost_usd = None
            return summary

        # Check for unpriced model entries
        raw_in_price = entry.get("input_price_per_million")
        raw_out_price = entry.get("output_price_per_million")
        if raw_in_price is None and raw_out_price is None:
            summary.pricing_status = "unknown_price"
            summary.pricing_notes = f"Model '{model_id}' is recognized but has no published API rates"
            summary.input_cost_usd = None
            summary.output_cost_usd = None
            summary.cache_read_cost_usd = None
            summary.cache_write_cost_usd = None
            summary.estimated_api_cost_usd = None
            return summary

        # Sum turn-by-turn calculations
        in_costs: List[Decimal] = []
        out_costs: List[Decimal] = []
        read_costs: List[Decimal] = []
        write_costs: List[Decimal] = []

        is_partial = False
        missing_components = set()

        for r in records:
            costs = self.calculate_turn_cost(r)
            if costs["input_cost"] is not None:
                in_costs.append(costs["input_cost"])
            elif r.input_tokens > 0:
                is_partial = True
                missing_components.add("input tokens")

            if costs["output_cost"] is not None:
                out_costs.append(costs["output_cost"])
            elif r.output_tokens > 0:
                is_partial = True
                missing_components.add("output tokens")

            if costs["cache_read_cost"] is not None:
                read_costs.append(costs["cache_read_cost"])
            elif r.cache_read_tokens is not None and r.cache_read_tokens > 0:
                is_partial = True
                missing_components.add("cache-read tokens")

            if costs["cache_write_cost"] is not None:
                write_costs.append(costs["cache_write_cost"])
            elif r.cache_write_tokens is not None and r.cache_write_tokens > 0:
                is_partial = True
                missing_components.add("cache-write tokens")

        summary.input_cost_usd = sum(in_costs) if in_costs or summary.input_tokens == 0 else None
        summary.output_cost_usd = sum(out_costs) if out_costs or summary.output_tokens == 0 else None
        summary.cache_read_cost_usd = sum(read_costs) if read_costs else (Decimal("0.0") if summary.cache_read_tokens == 0 else None)
        summary.cache_write_cost_usd = sum(write_costs) if write_costs else (Decimal("0.0") if summary.cache_write_tokens == 0 else None)
        summary.cache_storage_cost_usd = None  # Storage duration unmeasured in local traces
        summary.turn_count = len(records)

        priced_components = [
            c for c in (summary.input_cost_usd, summary.output_cost_usd, summary.cache_read_cost_usd, summary.cache_write_cost_usd)
            if c is not None
        ]
        summary.estimated_api_cost_usd = sum(priced_components) if priced_components else None

        # Determine pricing status
        verification_status = entry.get("verification_status", "verified")
        if is_partial:
            summary.pricing_status = "partially_priced"
            summary.pricing_notes = f"Unpriced components: {', '.join(sorted(missing_components))}"
        elif verification_status == "preview_estimate":
            summary.pricing_status = "preview_estimate"
            summary.pricing_notes = entry.get("notes") or "Preview model rate estimated from introductory API pricing"
        else:
            summary.pricing_status = "verified"
            summary.pricing_notes = None

        return summary

    def calculate_model_cost(
        self,
        summary: ModelUsageSummary,
        context_tokens: Optional[int] = None,
    ) -> ModelUsageSummary:
        """Calculates input, output, cache, and total estimated API costs for a ModelUsageSummary.
        
        Returns an updated ModelUsageSummary with exact Decimal costs and pricing status.
        Never replaces unknown or unpriced costs with $0.
        """
        model_id = summary.model_id
        
        # 1. Check if model ID is missing or unknown
        if not model_id or model_id.strip().lower() == "unknown":
            summary.pricing_status = "unknown_model"
            summary.pricing_notes = f"Model ID unmapped for display name '{summary.model_display_name}'"
            summary.input_cost_usd = None
            summary.output_cost_usd = None
            summary.cache_read_cost_usd = None
            summary.cache_write_cost_usd = None
            summary.estimated_api_cost_usd = None
            return summary

        # 2. Check if model exists in catalogue
        entry = self.catalogue.get_model_entry(model_id)
        if not entry:
            summary.pricing_status = "unavailable"
            summary.pricing_notes = f"No pricing rate catalogued for model ID '{model_id}'"
            summary.input_cost_usd = None
            summary.output_cost_usd = None
            summary.cache_read_cost_usd = None
            summary.cache_write_cost_usd = None
            summary.estimated_api_cost_usd = None
            return summary

        # Check for unpriced model entries (all rates null)
        raw_in_price = entry.get("input_price_per_million")
        raw_out_price = entry.get("output_price_per_million")
        if raw_in_price is None and raw_out_price is None:
            summary.pricing_status = "unknown_price"
            summary.pricing_notes = f"Model '{model_id}' is recognized but has no published API rates"
            summary.input_cost_usd = None
            summary.output_cost_usd = None
            summary.cache_read_cost_usd = None
            summary.cache_write_cost_usd = None
            summary.estimated_api_cost_usd = None
            return summary

        # 3. Resolve effective rates (evaluating context window tiers if context_tokens given)
        in_rate, out_rate, cache_rate, write_rate = self.get_effective_rates(entry, context_tokens=context_tokens)

        one_million = Decimal("1000000")
        is_partial = False
        missing_components = []

        # Input cost
        if in_rate is not None:
            summary.input_cost_usd = (Decimal(summary.input_tokens) * in_rate) / one_million
        else:
            summary.input_cost_usd = None
            if summary.input_tokens > 0:
                is_partial = True
                missing_components.append("input tokens")

        # Output cost
        if out_rate is not None:
            summary.output_cost_usd = (Decimal(summary.output_tokens) * out_rate) / one_million
        else:
            summary.output_cost_usd = None
            if summary.output_tokens > 0:
                is_partial = True
                missing_components.append("output tokens")

        # Cache Read cost
        if cache_rate is not None and summary.cache_read_tokens is not None and summary.cache_read_tokens > 0:
            summary.cache_read_cost_usd = (Decimal(summary.cache_read_tokens) * cache_rate) / one_million
        elif summary.cache_read_tokens is not None and summary.cache_read_tokens > 0:
            summary.cache_read_cost_usd = None
            is_partial = True
            missing_components.append("cache-read tokens")
        else:
            summary.cache_read_cost_usd = None

        # Cache Write cost
        if write_rate is not None and summary.cache_write_tokens is not None and summary.cache_write_tokens > 0:
            summary.cache_write_cost_usd = (Decimal(summary.cache_write_tokens) * write_rate) / one_million
        elif summary.cache_write_tokens is not None and summary.cache_write_tokens > 0:
            summary.cache_write_cost_usd = None
            is_partial = True
            missing_components.append("cache-write tokens")
        else:
            summary.cache_write_cost_usd = None

        summary.cache_storage_cost_usd = None  # Storage duration unmeasured in local traces

        # Total Estimated Cost Rollup
        priced_components = [
            c for c in (summary.input_cost_usd, summary.output_cost_usd, summary.cache_read_cost_usd, summary.cache_write_cost_usd)
            if c is not None
        ]

        if priced_components:
            summary.estimated_api_cost_usd = sum(priced_components)
        else:
            summary.estimated_api_cost_usd = None

        # Status assignment
        verification_status = entry.get("verification_status", "verified")
        if is_partial:
            summary.pricing_status = "partially_priced"
            summary.pricing_notes = f"Unpriced components: {', '.join(missing_components)}"
        elif verification_status == "preview_estimate":
            summary.pricing_status = "preview_estimate"
            summary.pricing_notes = entry.get("notes") or "Preview model rate estimated from introductory API pricing"
        else:
            summary.pricing_status = "verified"
            summary.pricing_notes = None

        return summary

    def calculate_receipt_cost(self, receipt: Receipt) -> Receipt:
        """Calculates and aggregates costs for an entire Receipt.
        
        Evaluates per-model summaries, computes overall estimated API cost,
        and determines the overall receipt pricing status.
        Actual billed amount strictly remains None.
        """
        updated_summaries = []
        statuses = set()
        total_estimated = Decimal("0.0")
        has_any_estimate = False
        all_notes = []

        for summary in receipt.model_summaries:
            # Check if matching usage records are present in the receipt
            matching_recs = [
                r for r in receipt.usage_records
                if (
                    r.model_display_name == summary.model_display_name
                    and r.model_id == summary.model_id
                    and r.agent == summary.agent
                    and r.provider == summary.provider
                )
            ]
            if matching_recs:
                updated = self.calculate_model_cost_from_records(matching_recs, summary)
            else:
                updated = self.calculate_model_cost(summary)

            updated_summaries.append(updated)
            statuses.add(updated.pricing_status)
            if updated.estimated_api_cost_usd is not None:
                total_estimated += updated.estimated_api_cost_usd
                has_any_estimate = True
            if updated.pricing_notes:
                all_notes.append(f"{updated.model_display_name}: {updated.pricing_notes}")

        receipt.model_summaries = updated_summaries
        receipt.actual_billed_amount_usd = None  # Strictly unbilled locally
        receipt.cache_storage_cost_usd = None    # Storage duration unmeasured in local traces
        if receipt.total_turns == 0:
            receipt.total_turns = len(receipt.usage_records) if receipt.usage_records else sum(s.turn_count for s in receipt.model_summaries)

        if has_any_estimate:
            receipt.estimated_api_cost_usd = total_estimated
        else:
            receipt.estimated_api_cost_usd = None

        # Determine overall receipt pricing status
        if statuses == {"verified"}:
            receipt.pricing_status = "verified"
        elif "partially_priced" in statuses:
            receipt.pricing_status = "partially_priced"
        elif "preview_estimate" in statuses:
            receipt.pricing_status = "preview_estimate"
        elif statuses == {"unknown_model"}:
            receipt.pricing_status = "unknown_model"
        elif statuses == {"unknown_price"}:
            receipt.pricing_status = "unknown_price"
        else:
            receipt.pricing_status = "unavailable"

        if all_notes:
            receipt.pricing_notes = "; ".join(all_notes)
        else:
            receipt.pricing_notes = None

        return receipt
