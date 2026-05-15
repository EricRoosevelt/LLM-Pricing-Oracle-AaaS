from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class CapabilityRequirements(BaseModel):
    vision: bool = False
    reasoning: bool = False
    tool_calling: bool = False
    json_mode: bool = False


class ModelCapabilities(CapabilityRequirements):
    supported_task_types: List[str] = Field(default_factory=lambda: ["general_chat"])


class PricingTier(BaseModel):
    upto_tokens: Optional[int] = Field(default=None, ge=1)
    in_price_1k: float = Field(..., ge=0)
    out_price_1k: float = Field(..., ge=0)


class CatalogModel(BaseModel):
    provider: str
    model_name: str
    model_id: str
    display_name: str
    in_price_1k: float = Field(..., ge=0)
    out_price_1k: float = Field(..., ge=0)
    pricing_tiers: List[PricingTier] = Field(default_factory=list)
    context_window_tokens: int = Field(default=8192, ge=1)
    default_ttfb_ms: int = Field(default=900, ge=1)
    throughput_hint_qps: float = Field(default=20.0, gt=0)
    accuracy: float = Field(default=0.72, ge=0, le=1.0)
    hard_capacity_factor: float = Field(default=1.15, ge=1.0)
    capabilities: ModelCapabilities = Field(default_factory=ModelCapabilities)
    cold_start_ms: int = Field(default=0, ge=0)
    cold_start_cost_usd: float = Field(default=0.0, ge=0)
    long_text_discount_rate: float = Field(default=0.0, ge=0, le=1)
    long_text_threshold_tokens: int = Field(default=16000, ge=1)
    concurrency_premium_rate: float = Field(default=0.0, ge=0)
    burst_qps_threshold: float = Field(default=0.85, gt=0, le=1.5)
    probe_endpoint: Optional[str] = None


class CatalogProvider(BaseModel):
    provider: str
    display_name: str
    base_url: str
    env_key_name: Optional[str] = None
    models: List[CatalogModel]


class CatalogSnapshot(BaseModel):
    version: str
    checksum: str
    source: str
    providers: List[CatalogProvider]
    models: List[CatalogModel]
    normalization_baseline: Dict[str, float] = Field(default_factory=dict)


class PolicyWeights(BaseModel):
    token_cost: float = Field(default=0.35, ge=0)
    qps: float = Field(default=0.15, ge=0)
    latency: float = Field(default=0.25, ge=0)
    accuracy: float = Field(default=0.25, ge=0)

    @model_validator(mode="after")
    def validate_total_weight(self) -> "PolicyWeights":
        total = self.token_cost + self.qps + self.latency + self.accuracy
        if total <= 0:
            raise ValueError("At least one policy weight must be positive.")
        return self


class RoutingPolicy(BaseModel):
    policy_id: str
    version: str
    description: str
    status: Literal["active", "disabled"] = "active"
    weights: PolicyWeights
    max_candidates: int = Field(default=4, ge=1, le=10)
    freshness_penalty: float = Field(default=0.12, ge=0, le=1)
    degraded_penalty: float = Field(default=0.18, ge=0, le=1)
    fallback_bonus: float = Field(default=0.05, ge=0, le=1)


class AgentPrincipal(BaseModel):
    agent_id: str
    environment: str
    tenant_id: str
    status: Literal["active", "blocked"]
    scopes: List[str]
    rate_limit_rpm: int
    concurrent_limit: int
    daily_budget_usd: float
    default_policy_id: str
    budget_profile_id: Optional[str] = None


class RoutingDecisionRequest(BaseModel):
    agent_id: str
    workflow_id: str
    session_id: str
    request_id: str
    task_type: str
    modalities: List[str] = Field(default_factory=lambda: ["text"], min_length=1)
    language: str = Field(default="en", min_length=2)
    input_chars: int = Field(..., ge=1)
    expected_output_tokens: int = Field(..., ge=1)
    context_window_tokens: int = Field(..., ge=1)
    budget_limit_usd: float = Field(..., ge=0)
    latency_slo_ms: Optional[int] = Field(default=None, ge=1)
    throughput_hint_qps: Optional[float] = Field(default=None, ge=0)
    policy_id: Optional[str] = None
    provider_allowlist: Optional[List[str]] = None
    provider_denylist: Optional[List[str]] = None
    capability_requirements: CapabilityRequirements = Field(default_factory=CapabilityRequirements)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ScoreBreakdown(BaseModel):
    token_cost: float = Field(..., ge=0, le=1)
    qps: float = Field(..., ge=0, le=1)
    latency: float = Field(..., ge=0, le=1)
    accuracy: float = Field(..., ge=0, le=1)
    freshness_penalty: float = Field(default=0, ge=0, le=1)
    degraded_penalty: float = Field(default=0, ge=0, le=1)
    fallback_bonus: float = Field(default=0, ge=0, le=1)


class DecisionCandidate(BaseModel):
    rank: int = Field(..., ge=1)
    model_id: str
    provider: str
    estimated_cost_usd: float = Field(..., ge=0)
    expected_ttfb_ms: int = Field(..., ge=0)
    confidence_score: float = Field(..., ge=0, le=1)
    signal_freshness_seconds: Optional[int] = Field(default=None, ge=0)
    degraded_reason: Optional[str] = None
    score_breakdown: ScoreBreakdown


class DecisionRejection(BaseModel):
    model_id: str
    provider: str
    reason: str
    detail: str


class DecisionObservability(BaseModel):
    decision_compute_ms: float = Field(..., ge=0)
    evaluated_models: int = Field(..., ge=0)
    candidate_count: int = Field(..., ge=0)
    filtered_by_budget: int = Field(..., ge=0)
    filtered_by_latency: int = Field(..., ge=0)
    filtered_by_capacity: int = Field(..., ge=0)
    filtered_by_capability: int = Field(..., ge=0)
    filtered_by_provider: int = Field(..., ge=0)
    signal_freshness_min_seconds: Optional[int] = Field(default=None, ge=0)
    fallback_safety_score: float = Field(..., ge=0, le=1)
    policy_trace: List[str] = Field(default_factory=list)


class RoutingDecisionResponse(BaseModel):
    decision_id: str
    catalog_version: str
    policy_id: str
    policy_version: str
    expires_at: datetime
    recommended: DecisionCandidate
    candidates: List[DecisionCandidate] = Field(..., min_length=1)
    rejections: List[DecisionRejection] = Field(default_factory=list)
    decision_explanation: str
    observability: DecisionObservability


class OutcomeAttempt(BaseModel):
    model_id: str
    provider: str
    rank: int = Field(..., ge=1)
    status: Literal["success", "timeout", "rate_limited", "upstream_error", "validation_error", "cancelled"]
    error_class: Optional[str] = None
    latency_ms: int = Field(..., ge=0)
    input_tokens: int = Field(..., ge=0)
    output_tokens: int = Field(..., ge=0)
    cost_usd: float = Field(..., ge=0)


class RoutingOutcomeRequest(BaseModel):
    decision_id: str
    agent_id: str
    request_id: str
    final_status: Literal["success", "partial", "failed"]
    attempts: List[OutcomeAttempt] = Field(..., min_length=1)
    final_model_id: Optional[str] = None
    fallback_depth: int = Field(..., ge=0)
    end_to_end_latency_ms: int = Field(..., ge=0)
    final_cost_usd: float = Field(..., ge=0)
    user_feedback: Optional[Literal["success", "partial", "failed"]] = None


class RoutingOutcomeResponse(BaseModel):
    decision_id: str
    outcome_status: Literal["recorded", "duplicate"]
    final_status: Literal["success", "partial", "failed"]
    attempts_recorded: int = Field(..., ge=0)
    fallback_depth: int = Field(..., ge=0)


class HealthResponse(BaseModel):
    status: Literal["online", "degraded"]
    project: str
    details: Dict[str, Any] = Field(default_factory=dict)


class PolicyListResponse(BaseModel):
    policies: List[RoutingPolicy]


class CatalogResponse(BaseModel):
    catalog_version: str
    checksum: str
    providers: List[CatalogProvider]
    models: List[CatalogModel]
