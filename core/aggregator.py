"""Aggregation engine for Agent Token Receipt.

Groups canonical usage records by model, agent, provider, session, and entire receipt.
Enforces strict accounting rules:
- Total tokens = input_tokens + output_tokens (never double-counts cache tokens).
- Missing optional token categories remain None unless non-None values exist.
- Preserves model distinctions across model switches.
- Keeps token summation and cost calculation cleanly separated.
"""

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
import uuid

from core.models import CanonicalUsageRecord, ModelUsageSummary, Receipt, ReceiptMetadata
from pricing.calculator import CostCalculator


class UsageAggregator:
    """Aggregates canonical usage records into model summaries and full receipts."""

    def __init__(self, cost_calculator: Optional[CostCalculator] = None):
        self.calculator = cost_calculator or CostCalculator()

    @staticmethod
    def aggregate_by_model(records: List[CanonicalUsageRecord]) -> List[ModelUsageSummary]:
        """Groups records by (agent, provider, model_display_name, model_id) and sums tokens."""
        if not records:
            return []

        # Key: (agent, provider, model_display_name, model_id)
        grouped: Dict[tuple, List[CanonicalUsageRecord]] = defaultdict(list)
        for r in records:
            key = (r.agent, r.provider, r.model_display_name, r.model_id)
            grouped[key].append(r)

        summaries: List[ModelUsageSummary] = []

        for (agent, provider, display_name, model_id), recs in grouped.items():
            input_sum = sum(r.input_tokens for r in recs)
            output_sum = sum(r.output_tokens for r in recs)

            # Cache Read: if all None -> None, else sum of non-None
            cache_read_vals = [r.cache_read_tokens for r in recs if r.cache_read_tokens is not None]
            cache_read_sum = sum(cache_read_vals) if cache_read_vals else None

            # Cache Write: if all None -> None, else sum of non-None
            cache_write_vals = [r.cache_write_tokens for r in recs if r.cache_write_tokens is not None]
            cache_write_sum = sum(cache_write_vals) if cache_write_vals else None

            # Reasoning: if all None -> None, else sum of non-None
            reasoning_vals = [r.reasoning_tokens for r in recs if r.reasoning_tokens is not None]
            reasoning_sum = sum(reasoning_vals) if reasoning_vals else None

            # Total tokens = input + output (do NOT double-count cache tokens)
            total_sum = input_sum + output_sum

            summary = ModelUsageSummary(
                provider=provider,
                agent=agent,
                model_display_name=display_name,
                model_id=model_id,
                input_tokens=input_sum,
                output_tokens=output_sum,
                cache_read_tokens=cache_read_sum,
                cache_write_tokens=cache_write_sum,
                reasoning_tokens=reasoning_sum,
                total_tokens=total_sum,
                turn_count=len(recs),
            )
            summaries.append(summary)

        return summaries

    @staticmethod
    def aggregate_by_agent(records: List[CanonicalUsageRecord]) -> Dict[str, Dict[str, Any]]:
        """Rolls up usage metrics grouped by agent name."""
        res: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "turns": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": None,
            "total_tokens": 0,
            "models": set(),
        })

        for r in records:
            g = res[r.agent]
            g["turns"] += 1
            g["input_tokens"] += r.input_tokens
            g["output_tokens"] += r.output_tokens
            g["total_tokens"] += (r.input_tokens + r.output_tokens)
            g["models"].add(r.model_display_name)

            if r.cache_read_tokens is not None:
                if g["cache_read_tokens"] is None:
                    g["cache_read_tokens"] = 0
                g["cache_read_tokens"] += r.cache_read_tokens

        return {k: {**v, "models": sorted(list(v["models"]))} for k, v in res.items()}

    @staticmethod
    def aggregate_by_provider(records: List[CanonicalUsageRecord]) -> Dict[str, Dict[str, Any]]:
        """Rolls up usage metrics grouped by provider name."""
        res: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "turns": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": None,
            "total_tokens": 0,
            "agents": set(),
        })

        for r in records:
            g = res[r.provider]
            g["turns"] += 1
            g["input_tokens"] += r.input_tokens
            g["output_tokens"] += r.output_tokens
            g["total_tokens"] += (r.input_tokens + r.output_tokens)
            g["agents"].add(r.agent)

            if r.cache_read_tokens is not None:
                if g["cache_read_tokens"] is None:
                    g["cache_read_tokens"] = 0
                g["cache_read_tokens"] += r.cache_read_tokens

        return {k: {**v, "agents": sorted(list(v["agents"]))} for k, v in res.items()}

    @staticmethod
    def aggregate_by_session(records: List[CanonicalUsageRecord]) -> Dict[str, List[ModelUsageSummary]]:
        """Groups records by session_id and produces model usage summaries per session."""
        session_groups: Dict[str, List[CanonicalUsageRecord]] = defaultdict(list)
        for r in records:
            session_groups[r.session_id].append(r)

        return {s_id: UsageAggregator.aggregate_by_model(recs) for s_id, recs in session_groups.items()}

    def build_receipt(
        self,
        records: List[CanonicalUsageRecord],
        receipt_id: Optional[str] = None,
        session_id: Optional[str] = None,
        session_title: Optional[str] = None,
        timezone_name: str = "UTC",
        unavailable_agents: Optional[List[Dict[str, str]]] = None,
    ) -> Receipt:
        """Compiles canonical usage records into a complete, priced Receipt object."""
        now = datetime.now(timezone.utc)
        rec_id = receipt_id or f"rec-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}"
        unavail_list = list(unavailable_agents) if unavailable_agents else []

        if not records:
            unavail_notes = (
                "; ".join(
                    f"{u.get('agent', 'Unknown')}: {u.get('reason', 'Token telemetry unavailable')}"
                    for u in unavail_list
                )
                if unavail_list
                else "No usage records in session"
            )
            metadata = ReceiptMetadata(
                receipt_id=rec_id,
                generated_at=now,
                timezone=timezone_name,
                session_id=session_id or "empty-session",
                session_title=session_title,
                first_turn_at=None,
                last_turn_at=None,
                elapsed_time_seconds=0.0,
            )
            return Receipt(
                metadata=metadata,
                usage_records=[],
                model_summaries=[],
                total_input_tokens=0,
                total_output_tokens=0,
                total_cache_read_tokens=None,
                total_tokens=0,
                estimated_api_cost_usd=None,
                actual_billed_amount_usd=None,
                pricing_status="unavailable",
                pricing_notes=unavail_notes,
                unavailable_agents=unavail_list,
            )

        # 1. Determine session bounds and metadata
        first_turn = min(r.timestamp for r in records)
        last_turn = max(r.timestamp for r in records)
        elapsed_sec = max(0.0, (last_turn - first_turn).total_seconds())
        active_session_id = session_id or records[0].session_id

        metadata = ReceiptMetadata(
            receipt_id=rec_id,
            generated_at=now,
            timezone=timezone_name,
            session_id=active_session_id,
            session_title=session_title,
            first_turn_at=first_turn,
            last_turn_at=last_turn,
            elapsed_time_seconds=elapsed_sec,
        )

        # 2. Model aggregation
        summaries = self.aggregate_by_model(records)

        # 3. Calculate costs on model summaries
        priced_summaries: List[ModelUsageSummary] = []
        for s in summaries:
            priced = self.calculator.calculate_model_cost(s)
            priced_summaries.append(priced)

        # 4. Token Rollups
        total_in = sum(s.input_tokens for s in priced_summaries)
        total_out = sum(s.output_tokens for s in priced_summaries)
        
        cache_vals = [s.cache_read_tokens for s in priced_summaries if s.cache_read_tokens is not None]
        total_cache = sum(cache_vals) if cache_vals else None

        grand_tokens = total_in + total_out

        # 5. Receipt Cost & Status Rollup
        preliminary_receipt = Receipt(
            metadata=metadata,
            usage_records=records,
            model_summaries=priced_summaries,
            total_input_tokens=total_in,
            total_output_tokens=total_out,
            total_cache_read_tokens=total_cache,
            total_tokens=grand_tokens,
            total_turns=len(records),
            estimated_api_cost_usd=None,
            actual_billed_amount_usd=None,
            pricing_status="unavailable",
            unavailable_agents=unavail_list,
        )

        return self.calculator.calculate_receipt_cost(preliminary_receipt)

