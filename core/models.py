"""Canonical data models for Agent Token Receipt.

Built with Pydantic v2 to enforce strict typing, validation, and zero-fabrication rules.
Adheres strictly to Phase 1 & Phase 3 specifications:
- Null/None for unavailable metrics (never default to zero).
- Non-negative integer validation for all token categories.
- Timezone-aware datetime validation for all timestamps.
- Decimal precision for financial values.
- Explicit prevention of double-counting cached tokens in total_tokens.
- Separation of provider and agent fields.
- Separation of model display names and canonical model IDs.
"""

from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


def _check_timezone_aware(dt: Optional[datetime], field_name: str) -> Optional[datetime]:
    """Ensures a datetime is timezone-aware (tzinfo is not None)."""
    if dt is not None and (dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None):
        raise ValueError(f"{field_name} must be timezone-aware (include tzinfo).")
    return dt


class CanonicalUsageRecord(BaseModel):
    """Normalized usage record for a single model interaction or turn."""
    provider: str = Field(..., min_length=1, description="Model provider, e.g. 'Google'")
    agent: str = Field(..., min_length=1, description="Coding agent, e.g. 'Google Antigravity'")
    session_id: str = Field(..., min_length=1, description="Unique session identifier")
    turn_index: int = Field(..., ge=0, description="Zero-based turn or request index")
    model_display_name: str = Field(..., min_length=1, description="Exact display name from log")
    model_id: Optional[str] = Field(default=None, description="Canonical API model ID, or null if unmapped")
    timestamp: datetime = Field(..., description="Timezone-aware timestamp of the request")
    
    # Token categories (mandatory reported counts must be non-negative)
    input_tokens: int = Field(..., ge=0, description="Reported input/prompt tokens")
    output_tokens: int = Field(..., ge=0, description="Reported output/completion tokens")
    
    # Optional / conditionally available token categories (null when unavailable)
    cache_read_tokens: Optional[int] = Field(default=None, ge=0, description="Tokens read from cache")
    cache_write_tokens: Optional[int] = Field(default=None, ge=0, description="Tokens written to cache")
    reasoning_tokens: Optional[int] = Field(default=None, ge=0, description="Tokens used for reasoning/thinking")
    
    source: str = Field(default="transcript.jsonl", description="Provenance of the usage record")

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp_tz(cls, v: datetime) -> datetime:
        return _check_timezone_aware(v, "timestamp")


class ModelUsageSummary(BaseModel):
    """Aggregated usage metrics for one distinct model within a session."""
    provider: str = Field(..., min_length=1, description="Model provider")
    agent: str = Field(..., min_length=1, description="Coding agent")
    model_display_name: str = Field(..., min_length=1, description="Model display name")
    model_id: Optional[str] = Field(default=None, description="Canonical API model ID")
    
    input_tokens: int = Field(..., ge=0, description="Total input tokens for this model")
    output_tokens: int = Field(..., ge=0, description="Total output tokens for this model")
    
    cache_read_tokens: Optional[int] = Field(default=None, ge=0, description="Total cache read tokens")
    cache_write_tokens: Optional[int] = Field(default=None, ge=0, description="Total cache write tokens")
    reasoning_tokens: Optional[int] = Field(default=None, ge=0, description="Total reasoning tokens")
    
    total_tokens: int = Field(default=0, ge=0, description="Valid combined total (input + output)")
    turn_count: int = Field(default=0, ge=0, description="Total generation turns recorded for this model")

    # Financial fields (exact Decimal math, Optional with None default)
    input_cost_usd: Optional[Decimal] = Field(default=None, ge=Decimal("0.0"), description="Estimated input token cost")
    output_cost_usd: Optional[Decimal] = Field(default=None, ge=Decimal("0.0"), description="Estimated output token cost")
    cache_read_cost_usd: Optional[Decimal] = Field(default=None, ge=Decimal("0.0"), description="Estimated cache read cost")
    cache_write_cost_usd: Optional[Decimal] = Field(default=None, ge=Decimal("0.0"), description="Estimated cache write cost")
    cache_storage_cost_usd: Optional[Decimal] = Field(default=None, ge=Decimal("0.0"), description="Estimated cache storage cost (None if unmeasured/unrecorded)")
    estimated_api_cost_usd: Optional[Decimal] = Field(default=None, ge=Decimal("0.0"), description="Total estimated API-equivalent cost")
    pricing_status: str = Field(default="unavailable", description="'verified', 'partially_priced', 'unknown_model', 'unknown_price', 'unavailable'")
    pricing_notes: Optional[str] = Field(default=None, description="Explanatory notes regarding missing or partial pricing")

    @model_validator(mode="before")
    @classmethod
    def compute_or_validate_total_tokens(cls, data: any) -> any:
        if isinstance(data, dict):
            inp = data.get("input_tokens", 0)
            out = data.get("output_tokens", 0)
            expected_total = inp + out
            
            # If total_tokens is provided by caller, ensure it does not double-count cache tokens
            if "total_tokens" in data and data["total_tokens"] is not None:
                provided_total = data["total_tokens"]
                cache_read = data.get("cache_read_tokens") or 0
                if provided_total == (inp + out + cache_read) and cache_read > 0:
                    raise ValueError(
                        f"total_tokens ({provided_total}) appears to double-count cache_read_tokens ({cache_read}). "
                        f"total_tokens must equal input_tokens + output_tokens ({expected_total})."
                    )
                if provided_total != expected_total:
                    raise ValueError(
                        f"total_tokens ({provided_total}) does not match input_tokens ({inp}) + output_tokens ({out}) = {expected_total}."
                    )
            else:
                data["total_tokens"] = expected_total
        return data


class ReceiptMetadata(BaseModel):
    """Metadata detailing the session context and receipt creation time."""
    receipt_id: str = Field(..., min_length=1, description="Unique receipt identifier")
    generated_at: datetime = Field(..., description="Timezone-aware timestamp when receipt was generated")
    timezone: str = Field(default="UTC", description="Timezone string, e.g. 'UTC' or 'Asia/Kolkata'")
    session_id: str = Field(..., min_length=1, description="Session UUID or identifier")
    session_title: Optional[str] = Field(default=None, description="Session title from agent index")
    first_turn_at: Optional[datetime] = Field(default=None, description="Timestamp of first recorded turn")
    last_turn_at: Optional[datetime] = Field(default=None, description="Timestamp of last recorded turn")
    elapsed_time_seconds: Optional[float] = Field(default=None, ge=0.0, description="Elapsed seconds between first and last turn")

    @field_validator("generated_at", "first_turn_at", "last_turn_at")
    @classmethod
    def validate_timestamps_tz(cls, v: Optional[datetime], info) -> Optional[datetime]:
        return _check_timezone_aware(v, info.field_name)


class Receipt(BaseModel):
    """Top-level receipt containing complete session breakdown and financial estimates."""
    metadata: ReceiptMetadata
    usage_records: List[CanonicalUsageRecord] = Field(default_factory=list)
    model_summaries: List[ModelUsageSummary] = Field(default_factory=list)
    
    # Granular token totals
    total_input_tokens: int = Field(default=0, ge=0, description="Sum of input tokens across models")
    total_output_tokens: int = Field(default=0, ge=0, description="Sum of output tokens across models")
    total_cache_read_tokens: Optional[int] = Field(default=None, ge=0, description="Sum of cache read tokens across models")
    total_tokens: int = Field(default=0, ge=0, description="Grand total tokens across all models (input + output)")
    total_turns: int = Field(default=0, ge=0, description="Grand total generation turns across all models")
    
    # Financial estimates
    estimated_api_cost_usd: Optional[Decimal] = Field(default=None, ge=Decimal("0.0"), description="Estimated API-equivalent cost in USD")
    actual_billed_amount_usd: Optional[Decimal] = Field(default=None, ge=Decimal("0.0"), description="Actual billed amount if reported by bill source")
    cache_storage_cost_usd: Optional[Decimal] = Field(default=None, ge=Decimal("0.0"), description="Total cache storage cost across models")
    pricing_status: str = Field(default="estimated", description="Pricing status: 'verified', 'partially_priced', 'unknown_model', 'unknown_price', 'unavailable'")
    pricing_notes: Optional[str] = Field(default=None, description="Explanatory notes regarding missing or partial pricing")
    unavailable_agents: List[Dict[str, str]] = Field(default_factory=list, description="Detected agents whose local token telemetry is unavailable")

    @model_validator(mode="before")
    @classmethod
    def compute_or_validate_receipt_totals(cls, data: any) -> any:
        if isinstance(data, dict):
            summaries = data.get("model_summaries", [])
            expected_total = sum(s.get("total_tokens", s.get("input_tokens", 0) + s.get("output_tokens", 0)) if isinstance(s, dict) else s.total_tokens for s in summaries)
            
            if "total_tokens" in data and data["total_tokens"] is not None:
                if summaries and data["total_tokens"] != expected_total:
                    raise ValueError(
                        f"Receipt total_tokens ({data['total_tokens']}) does not match sum of model summaries ({expected_total})."
                    )
            else:
                data["total_tokens"] = expected_total
        return data
