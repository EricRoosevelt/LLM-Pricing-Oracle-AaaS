from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from time import perf_counter
from typing import Any, Dict, Mapping, Optional

from app.schemas.routing import (
    CatalogModel,
    CatalogSnapshot,
    DecisionCandidate,
    DecisionObservability,
    DecisionRejection,
    RoutingDecisionRequest,
    RoutingDecisionResponse,
    RoutingPolicy,
    ScoreBreakdown,
)
from app.services.token_estimator import estimate_tokens


DEFAULT_BASELINE = {
    "token_cost_usd_per_1k": 0.002,
    "qps": 40.0,
    "latency_ms": 800.0,
    "accuracy": 0.8,
}
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


def _normalize_weights(policy: RoutingPolicy) -> Dict[str, float]:
    weights = policy.weights.model_dump()
    total = sum(max(0.0, float(value)) for value in weights.values()) or 1.0
    return {key: max(0.0, float(value)) / total for key, value in weights.items()}


def _pick_tier(model: CatalogModel, total_tokens: int) -> Dict[str, float]:
    for tier in model.pricing_tiers:
        if tier.upto_tokens is None or total_tokens <= tier.upto_tokens:
            return tier.model_dump()
    return {"in_price_1k": model.in_price_1k, "out_price_1k": model.out_price_1k}


def _signal_age_seconds(signal: Mapping[str, Any] | None) -> Optional[int]:
    if not signal or not signal.get("last_probe_at"):
        return None
    raw = signal["last_probe_at"]
    try:
        observed_at = datetime.fromisoformat(raw.replace("Z", "+00:00")) if isinstance(raw, str) else raw
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        return max(0, int((datetime.now(timezone.utc) - observed_at).total_seconds()))
    except (TypeError, ValueError):
        return None


def _matches_capabilities(model: CatalogModel, request: RoutingDecisionRequest) -> Optional[str]:
    capabilities = model.capabilities
    required = request.capability_requirements
    if required.vision and not capabilities.vision:
        return "vision"
    if required.reasoning and not capabilities.reasoning:
        return "reasoning"
    if required.tool_calling and not capabilities.tool_calling:
        return "tool_calling"
    if required.json_mode and not capabilities.json_mode:
        return "json_mode"
    if request.task_type not in capabilities.supported_task_types:
        return "task_type"
    if request.context_window_tokens > model.context_window_tokens:
        return "context_window"
    return None


def calculate_routing_decision(
    request: RoutingDecisionRequest,
    catalog: CatalogSnapshot,
    policy: RoutingPolicy,
    signals: Mapping[str, Mapping[str, Any]],
    signal_freshness_seconds: int,
    ttl_seconds: int,
) -> RoutingDecisionResponse:
    started = perf_counter()
    baseline = {**DEFAULT_BASELINE, **catalog.normalization_baseline}
    weights = _normalize_weights(policy)
    candidates: list[DecisionCandidate] = []
    rejections: list[DecisionRejection] = []
    filtered_by_budget = 0
    filtered_by_latency = 0
    filtered_by_capacity = 0
    filtered_by_capability = 0
    filtered_by_provider = 0
    freshness_values: list[int] = []
    policy_trace = [
        f"catalog={catalog.version} checksum={catalog.checksum[:12]}",
        f"policy={policy.policy_id}@{policy.version}",
    ]

    for model in catalog.models:
        if request.provider_allowlist and model.provider not in request.provider_allowlist:
            filtered_by_provider += 1
            rejections.append(
                DecisionRejection(
                    model_id=model.model_id,
                    provider=model.provider,
                    reason="provider_filtered",
                    detail=f"provider '{model.provider}' not present in allowlist",
                )
            )
            continue
        if request.provider_denylist and model.provider in request.provider_denylist:
            filtered_by_provider += 1
            rejections.append(
                DecisionRejection(
                    model_id=model.model_id,
                    provider=model.provider,
                    reason="provider_filtered",
                    detail=f"provider '{model.provider}' explicitly denied",
                )
            )
            continue

        capability_gap = _matches_capabilities(model, request)
        if capability_gap:
            filtered_by_capability += 1
            rejections.append(
                DecisionRejection(
                    model_id=model.model_id,
                    provider=model.provider,
                    reason="capability_filtered",
                    detail=f"missing or incompatible capability: {capability_gap}",
                )
            )
            continue

        signal = signals.get(model.model_id, {})
        age_seconds = _signal_age_seconds(signal)
        freshness_values.append(age_seconds if age_seconds is not None else signal_freshness_seconds * 2)
        degraded_reason = signal.get("degraded_reason")
        ttfb_ms = int(signal.get("ttfb_p50_ms", model.default_ttfb_ms))
        qps = float(signal.get("throughput_hint_qps", model.throughput_hint_qps))
        success_rate = float(signal.get("success_rate", 1.0))

        throughput_hint = request.throughput_hint_qps or 0.0
        if throughput_hint > 0 and qps > 0 and throughput_hint > qps * model.hard_capacity_factor:
            filtered_by_capacity += 1
            rejections.append(
                DecisionRejection(
                    model_id=model.model_id,
                    provider=model.provider,
                    reason="capacity_filtered",
                    detail=f"throughput_hint_qps={throughput_hint} exceeds effective capacity {round(qps * model.hard_capacity_factor, 2)}",
                )
            )
            continue

        input_tokens = estimate_tokens(request.input_chars, model.model_id, request.language)
        output_tokens = max(1, request.expected_output_tokens)
        total_tokens = max(1, input_tokens + output_tokens)
        tier = _pick_tier(model, total_tokens)
        base_cost = (Decimal(input_tokens) / THOUSAND) * _to_decimal(tier["in_price_1k"])
        base_cost += (Decimal(output_tokens) / THOUSAND) * _to_decimal(tier["out_price_1k"])

        if throughput_hint <= 0:
            ttfb_ms += model.cold_start_ms
            base_cost += _to_decimal(model.cold_start_cost_usd)

        if total_tokens >= model.long_text_threshold_tokens and model.long_text_discount_rate > 0:
            base_cost -= base_cost * _to_decimal(model.long_text_discount_rate)

        if throughput_hint > 0 and qps > 0 and throughput_hint / qps > model.burst_qps_threshold:
            overage = min((throughput_hint / qps) - model.burst_qps_threshold, 1.0)
            base_cost += base_cost * _to_decimal(model.concurrency_premium_rate * overage)

        total_cost = max(ZERO, base_cost)
        if request.budget_limit_usd == 0 and total_cost > ZERO:
            filtered_by_budget += 1
            rejections.append(
                DecisionRejection(
                    model_id=model.model_id,
                    provider=model.provider,
                    reason="budget_filtered",
                    detail="request requires a zero-cost route but model is billable",
                )
            )
            continue
        if request.budget_limit_usd > 0 and float(total_cost) > request.budget_limit_usd:
            filtered_by_budget += 1
            rejections.append(
                DecisionRejection(
                    model_id=model.model_id,
                    provider=model.provider,
                    reason="budget_filtered",
                    detail=f"estimated cost {round(float(total_cost), 6)} exceeds budget_limit_usd={request.budget_limit_usd}",
                )
            )
            continue
        if request.latency_slo_ms and ttfb_ms > request.latency_slo_ms:
            filtered_by_latency += 1
            rejections.append(
                DecisionRejection(
                    model_id=model.model_id,
                    provider=model.provider,
                    reason="latency_filtered",
                    detail=f"expected_ttfb_ms={ttfb_ms} exceeds latency_slo_ms={request.latency_slo_ms}",
                )
            )
            continue

        unit_cost = ZERO if total_cost == ZERO else total_cost * THOUSAND / Decimal(total_tokens)
        freshness_penalty = 0.0
        if age_seconds is None:
            freshness_penalty = round(policy.freshness_penalty, 4)
        elif age_seconds > signal_freshness_seconds:
            freshness_penalty = round(
                min(1.0, age_seconds / max(signal_freshness_seconds, 1)) * policy.freshness_penalty,
                4,
            )
        degraded_penalty = round(policy.degraded_penalty if degraded_reason else 0.0, 4)
        fallback_bonus = round(policy.fallback_bonus * success_rate, 4)

        score_breakdown = ScoreBreakdown(
            token_cost=round(_cost_score(float(unit_cost), baseline["token_cost_usd_per_1k"]), 4),
            qps=round(_benefit_score(qps, baseline["qps"]), 4),
            latency=round(_cost_score(float(ttfb_ms), baseline["latency_ms"]), 4),
            accuracy=round(_benefit_score(model.accuracy * success_rate, baseline["accuracy"]), 4),
            freshness_penalty=freshness_penalty,
            degraded_penalty=degraded_penalty,
            fallback_bonus=fallback_bonus,
        )
        confidence_score = round(
            _clamp(
                sum(getattr(score_breakdown, key) * weights[key] for key in weights)
                - freshness_penalty
                - degraded_penalty
                + fallback_bonus
            ),
            4,
        )
        candidates.append(
            DecisionCandidate(
                rank=len(candidates) + 1,
                model_id=model.model_id,
                provider=model.provider,
                estimated_cost_usd=_round_money(total_cost),
                expected_ttfb_ms=ttfb_ms,
                confidence_score=confidence_score,
                signal_freshness_seconds=age_seconds,
                degraded_reason=degraded_reason,
                score_breakdown=score_breakdown,
            )
        )

    candidates.sort(key=lambda item: (-item.confidence_score, item.estimated_cost_usd, item.expected_ttfb_ms))
    candidates = candidates[: policy.max_candidates]
    for index, candidate in enumerate(candidates, start=1):
        candidate.rank = index

    fallback_safety_score = 0.0
    if candidates:
        fallback_safety_score = round(
            _clamp(sum(candidate.confidence_score for candidate in candidates) / len(candidates)),
            4,
        )
        policy_trace.append(f"top_candidate={candidates[0].model_id}")
        policy_trace.append(f"fallback_depth={len(candidates) - 1}")
    policy_trace.append(f"rejections={len(rejections)}")
    policy_trace.append(f"freshness_budget_seconds={signal_freshness_seconds}")

    compute_ms = round((perf_counter() - started) * 1000, 3)
    observability = DecisionObservability(
        decision_compute_ms=compute_ms,
        evaluated_models=len(catalog.models),
        candidate_count=len(candidates),
        filtered_by_budget=filtered_by_budget,
        filtered_by_latency=filtered_by_latency,
        filtered_by_capacity=filtered_by_capacity,
        filtered_by_capability=filtered_by_capability,
        filtered_by_provider=filtered_by_provider,
        signal_freshness_min_seconds=min(freshness_values) if freshness_values else None,
        fallback_safety_score=fallback_safety_score,
        policy_trace=policy_trace,
    )

    if not candidates:
        raise ValueError("No models survived policy, budget, latency, and capability filtering.")

    top_candidate = candidates[0]
    decision_explanation = (
        f"Selected {top_candidate.model_id} for policy '{policy.policy_id}' because it offered the best "
        f"confidence/cost/latency balance for task_type='{request.task_type}' with "
        f"{len(candidates)} viable candidates after filtering."
    )
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    return RoutingDecisionResponse(
        decision_id="",
        catalog_version=catalog.version,
        policy_id=policy.policy_id,
        policy_version=policy.version,
        expires_at=expires_at,
        recommended=top_candidate,
        candidates=candidates,
        rejections=rejections,
        decision_explanation=decision_explanation,
        observability=observability,
    )
