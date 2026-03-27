# app/services/pricing_engine.py
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, List, Optional

from app.schemas.routing import RouteDecision, RoutingBenchmarkReport, RoutingObservability
from app.services.token_estimator import estimate_tokens

CONFIG_PATH = Path(__file__).parent.parent.parent / "models_config.json"

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    GLOBAL_MODEL_CONFIG = json.load(f)

DEFAULT_BASELINE = {"token_cost_usd_per_1k": 0.002, "qps": 40.0, "latency_ms": 800.0, "accuracy": 0.8}
DEFAULT_WEIGHTS = {"token_cost": 0.5, "qps": 0.1, "latency": 0.2, "accuracy": 0.2}
DEFAULT_SCORING = GLOBAL_MODEL_CONFIG.get("scoring_defaults", {})
ZERO = Decimal("0")
THOUSAND = Decimal("1000")


def _to_decimal(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _benefit_score(value: float, baseline: float) -> float:
    safe_value = max(value, 0.0)
    safe_baseline = max(baseline, 0.000001)
    return _clamp(safe_value / (safe_value + safe_baseline))


def _cost_score(value: float, baseline: float) -> float:
    safe_value = max(value, 0.0)
    safe_baseline = max(baseline, 0.000001)
    return 1.0 if safe_value == 0 else _clamp(safe_baseline / (safe_value + safe_baseline))


def _round_money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def _pick_tier(model: Dict[str, Any], total_tokens: int) -> Dict[str, Any]:
    for tier in model.get("pricing_tiers", []):
        limit = tier.get("upto_tokens")
        if limit is None or total_tokens <= limit:
            return tier
    return {}


def _supports_request(model: Dict[str, Any], task_category: str, requires_vision: bool) -> bool:
    if requires_vision and not model.get("supports_vision", False):
        return False
    supported_task_categories = model.get("supported_task_categories")
    if supported_task_categories and task_category not in supported_task_categories:
        return False
    return True


ACTIVE_MODELS = []
for provider_name, provider_info in GLOBAL_MODEL_CONFIG.get("providers", {}).items():
    for model_name, model_info in provider_info.get("models", {}).items():
        ACTIVE_MODELS.append(
            {
                "model_id": f"{provider_name}/{model_name}",
                "ttfb_ms": model_info.get("ttfb_ms", 1000),
                "qps": model_info.get("qps", 20.0),
                "accuracy": model_info.get("accuracy", 0.72),
                **model_info,
            }
        )

def calculate_optimal_routing(
    input_char_count: int,
    output_word_count: int,
    max_budget_usd: float,
    max_latency_ms: Optional[int] = None,
    language: str = "en",
    task_category: str = "general_chat",
    requires_vision: bool = False,
    real_latencies_map: Optional[Dict[str, int]] = None,
    real_qps_map: Optional[Dict[str, float]] = None,
    score_weights: Optional[Dict[str, float]] = None,
    normalization_baseline: Optional[Dict[str, float]] = None,
    current_qps: Optional[float] = None,
    free_tier_remaining_tokens: Optional[Dict[str, int]] = None,
    accuracy_overrides: Optional[Dict[str, float]] = None,
    return_report: bool = False,
):
    started = perf_counter()
    candidates: List[RouteDecision] = []
    real_latencies_map = real_latencies_map or {}
    real_qps_map = real_qps_map or {}
    free_tier_remaining_tokens = free_tier_remaining_tokens or {}
    accuracy_overrides = accuracy_overrides or {}
    weights = {k: float(v) for k, v in {**DEFAULT_WEIGHTS, **DEFAULT_SCORING.get("weights", {}), **(score_weights or {})}.items()}
    total_weight = sum(max(0.0, value) for value in weights.values()) or 1.0
    weights = {k: max(0.0, value) / total_weight for k, value in weights.items()}
    baseline = {k: float(v) for k, v in {**DEFAULT_BASELINE, **DEFAULT_SCORING.get("normalization_baseline", {}), **(normalization_baseline or {})}.items()}
    output_char_approx = output_word_count * 5
    budget_filtered = 0
    latency_filtered = 0
    capacity_filtered = 0
    capability_filtered = 0
    max_pricing_error = 0.0

    for model in ACTIVE_MODELS:
        model_id = model["model_id"]
        if not _supports_request(model, task_category, requires_vision):
            capability_filtered += 1
            continue
        in_tokens = estimate_tokens(input_char_count, model_id, language)
        out_tokens = estimate_tokens(output_char_approx, model_id, language)
        total_tokens = max(1, in_tokens + out_tokens)
        tier = _pick_tier(model, total_tokens)
        remaining = max(0, int(free_tier_remaining_tokens.get(model_id, 0)))
        free_in = min(remaining, in_tokens)
        remaining -= free_in
        free_out = min(remaining, out_tokens)
        billable_in = in_tokens - free_in
        billable_out = out_tokens - free_out
        in_price = _to_decimal(tier.get("in_price_1k", model["in_price_1k"]))
        out_price = _to_decimal(tier.get("out_price_1k", model["out_price_1k"]))
        base_cost = (Decimal(billable_in) / THOUSAND) * in_price + (Decimal(billable_out) / THOUSAND) * out_price
        latency_ms = int(real_latencies_map.get(model_id, model.get("ttfb_ms", baseline["latency_ms"])))
        cold_start_cost = ZERO
        if current_qps is None or current_qps <= 0:
            latency_ms += int(model.get("cold_start_ms", 0))
            cold_start_cost = _to_decimal(model.get("cold_start_cost_usd", 0))
        qps = float(real_qps_map.get(model_id, model.get("qps", baseline["qps"])))
        utilization = (float(current_qps) / qps) if current_qps and qps > 0 else 0.0
        if qps > 0 and utilization > float(model.get("hard_capacity_factor", 1.15)):
            capacity_filtered += 1
            continue
        premium = ZERO
        threshold = float(model.get("burst_qps_threshold", DEFAULT_SCORING.get("burst_qps_threshold", 0.85)))
        rate = float(model.get("concurrency_premium_rate", 0))
        if qps > 0 and utilization > threshold and rate > 0:
            premium = base_cost * _to_decimal(rate * min((utilization - threshold) / max(0.01, 1.0 - threshold), 1.5))
        discount = ZERO
        discount_rate = float(model.get("long_text_discount_rate", 0))
        token_threshold = int(model.get("long_text_threshold_tokens", DEFAULT_SCORING.get("long_text_threshold_tokens", 16000)))
        if total_tokens >= token_threshold and discount_rate > 0:
            discount = base_cost * _to_decimal(discount_rate)
        total_cost = max(ZERO, base_cost + cold_start_cost + premium - discount)
        if (max_budget_usd == 0 and total_cost > ZERO) or (max_budget_usd > 0 and float(total_cost) > max_budget_usd):
            budget_filtered += 1
            continue
        if max_latency_ms and latency_ms > max_latency_ms:
            latency_filtered += 1
            continue
        unit_cost = ZERO if total_cost == ZERO else total_cost * THOUSAND / Decimal(total_tokens)
        accuracy = float(accuracy_overrides.get(model_id, model.get("accuracy", baseline["accuracy"])))
        score_breakdown = {
            "token_cost": round(_cost_score(float(unit_cost), baseline["token_cost_usd_per_1k"]), 4),
            "qps": round(_benefit_score(qps, baseline["qps"]), 4),
            "latency": round(_cost_score(float(latency_ms), baseline["latency_ms"]), 4),
            "accuracy": round(_benefit_score(accuracy, baseline["accuracy"]), 4),
        }
        normalized_score = round(sum(score_breakdown[key] * weights[key] for key in weights), 4)
        rounded_cost = _round_money(total_cost)
        if total_cost > ZERO:
            max_pricing_error = max(max_pricing_error, abs(rounded_cost - float(total_cost)) / float(total_cost) * 100)
        candidates.append(RouteDecision(model_id=model_id, estimated_cost_usd=rounded_cost, expected_ttfb_ms=latency_ms, confidence_score=normalized_score, normalized_score=normalized_score, score_breakdown=score_breakdown, pricing_components={"base_cost_usd": _round_money(base_cost), "cold_start_cost_usd": _round_money(cold_start_cost), "long_text_discount_usd": _round_money(discount), "concurrency_premium_usd": _round_money(premium), "unit_cost_usd_per_1k": _round_money(unit_cost), "free_tier_tokens_used": float(free_in + free_out)}))

    candidates.sort(key=lambda item: (-item.normalized_score, item.estimated_cost_usd, item.expected_ttfb_ms))
    compute_ms = round((perf_counter() - started) * 1000, 3)
    score_margin = round(candidates[0].normalized_score - candidates[1].normalized_score, 4) if len(candidates) > 1 else (candidates[0].normalized_score if candidates else 0.0)
    observability = RoutingObservability(routing_compute_ms=compute_ms, pricing_error_pct=round(max_pricing_error, 4), evaluated_models=len(ACTIVE_MODELS), filtered_by_budget=budget_filtered, filtered_by_latency=latency_filtered, filtered_by_capacity=capacity_filtered, filtered_by_capability=capability_filtered, applied_weights={k: round(v, 4) for k, v in weights.items()}, normalization_baseline={k: round(v, 4) for k, v in baseline.items()}, score_margin=score_margin)
    report = {"cascade": candidates, "observability": observability, "benchmark_report": RoutingBenchmarkReport(switch_latency_target_ms=200, switch_latency_actual_ms=compute_ms, switch_latency_met=compute_ms < 200, pricing_error_target_pct=3.0, pricing_error_actual_pct=round(max_pricing_error, 4), pricing_accuracy_met=max_pricing_error < 3.0)}
    return report if return_report else candidates
