from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class ScoreWeights(BaseModel):
    token_cost: float = Field(default=0.4, ge=0)
    qps: float = Field(default=0.15, ge=0)
    latency: float = Field(default=0.25, ge=0)
    accuracy: float = Field(default=0.2, ge=0)

    @model_validator(mode="after")
    def validate_total_weight(self):
        if (self.token_cost + self.qps + self.latency + self.accuracy) <= 0:
            raise ValueError("At least one score weight must be positive.")
        return self


class NormalizationBaseline(BaseModel):
    token_cost_usd_per_1k: float = Field(default=0.002, gt=0)
    qps: float = Field(default=40.0, gt=0)
    latency_ms: float = Field(default=800.0, gt=0)
    accuracy: float = Field(default=0.8, gt=0, le=1.0)


class OptimizeRouteRequest(BaseModel):
    task_category: Literal["code_generation", "summarization", "realtime_voice", "general_chat"]
    language: Literal["en", "zh"] = Field(default="en")
    payload_char_count: int = Field(..., ge=1)
    expected_output_words: int = Field(..., ge=1)
    max_budget_usd: float = Field(..., ge=0)
    max_latency_ms: Optional[int] = Field(None, ge=50)
    requires_vision: bool = Field(default=False)
    current_qps: Optional[float] = Field(default=None, ge=0)
    score_weights: Optional[ScoreWeights] = None
    normalization_baseline: Optional[NormalizationBaseline] = None
    free_tier_remaining_tokens: Optional[Dict[str, int]] = None


class RouteDecision(BaseModel):
    model_id: str
    estimated_cost_usd: float = Field(..., ge=0)
    expected_ttfb_ms: int = Field(..., ge=0)
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    normalized_score: float = Field(..., ge=0.0, le=1.0)
    score_breakdown: Dict[str, float] = Field(default_factory=dict)
    pricing_components: Dict[str, float] = Field(default_factory=dict)


class RoutingObservability(BaseModel):
    routing_compute_ms: float = Field(..., ge=0)
    pricing_error_pct: float = Field(..., ge=0)
    evaluated_models: int = Field(..., ge=0)
    filtered_by_budget: int = Field(..., ge=0)
    filtered_by_latency: int = Field(..., ge=0)
    filtered_by_capacity: int = Field(..., ge=0)
    filtered_by_capability: int = Field(..., ge=0)
    applied_weights: Dict[str, float] = Field(default_factory=dict)
    normalization_baseline: Dict[str, float] = Field(default_factory=dict)
    score_margin: float = Field(..., ge=0)


class RoutingBenchmarkReport(BaseModel):
    switch_latency_target_ms: int = Field(default=200, ge=1)
    switch_latency_actual_ms: float = Field(..., ge=0)
    switch_latency_met: bool
    pricing_error_target_pct: float = Field(default=3.0, ge=0)
    pricing_error_actual_pct: float = Field(..., ge=0)
    pricing_accuracy_met: bool


class OptimizeRouteResponse(BaseModel):
    status: str = Field(default="success")
    routing_cascade: List[RouteDecision] = Field(..., min_length=1)
    ttl_seconds: int = Field(default=300, ge=1)
    observability: RoutingObservability
    benchmark_report: RoutingBenchmarkReport
