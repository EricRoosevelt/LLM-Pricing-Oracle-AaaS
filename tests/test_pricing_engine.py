from copy import deepcopy

import pytest

from app.services import pricing_engine


TEST_MODELS = [
    {"model_id": "lab/value", "in_price_1k": 0.001, "out_price_1k": 0.0012, "ttfb_ms": 620, "qps": 55.0, "accuracy": 0.84, "cold_start_ms": 20, "long_text_discount_rate": 0.15, "long_text_threshold_tokens": 2400, "concurrency_premium_rate": 0.3, "supports_vision": False, "supported_task_categories": ["code_generation", "summarization", "general_chat"]},
    {"model_id": "lab/fast", "in_price_1k": 0.002, "out_price_1k": 0.0022, "ttfb_ms": 240, "qps": 85.0, "accuracy": 0.86, "cold_start_ms": 10, "concurrency_premium_rate": 0.25, "supports_vision": False, "supported_task_categories": ["code_generation", "summarization", "general_chat"]},
    {"model_id": "lab/free", "in_price_1k": 0.0008, "out_price_1k": 0.001, "ttfb_ms": 900, "qps": 20.0, "accuracy": 0.7, "free_tier_tokens": 2000, "supports_vision": False, "supported_task_categories": ["code_generation", "summarization", "general_chat"]},
    {"model_id": "lab/tiered", "in_price_1k": 0.0015, "out_price_1k": 0.002, "ttfb_ms": 500, "qps": 45.0, "accuracy": 0.81, "pricing_tiers": [{"upto_tokens": 2500, "in_price_1k": 0.001, "out_price_1k": 0.0015}, {"upto_tokens": None, "in_price_1k": 0.002, "out_price_1k": 0.003}], "supports_vision": False, "supported_task_categories": ["code_generation", "summarization", "general_chat"]},
]


def _patch_models(monkeypatch, models=None):
    monkeypatch.setattr(pricing_engine, "ACTIVE_MODELS", deepcopy(models or TEST_MODELS))


def test_routing_prefers_best_value_model(monkeypatch):
    _patch_models(monkeypatch)
    cascade = pricing_engine.calculate_optimal_routing(2400, 200, 0.02, current_qps=10)
    assert cascade[0].model_id == "lab/value"
    assert cascade[0].confidence_score >= cascade[-1].confidence_score


def test_dynamic_weights_can_flip_preference(monkeypatch):
    _patch_models(monkeypatch)
    cascade = pricing_engine.calculate_optimal_routing(2400, 200, 0.02, current_qps=10, score_weights={"token_cost": 0.1, "qps": 0.25, "latency": 0.45, "accuracy": 0.2})
    assert cascade[0].model_id == "lab/fast"


def test_zero_budget_and_free_tier_exhaustion(monkeypatch):
    _patch_models(monkeypatch)
    free_only = pricing_engine.calculate_optimal_routing(1000, 100, 0.0, free_tier_remaining_tokens={"lab/free": 2000})
    assert [item.model_id for item in free_only] == ["lab/free"]
    assert free_only[0].estimated_cost_usd == 0.0
    exhausted = pricing_engine.calculate_optimal_routing(1000, 100, 0.0, free_tier_remaining_tokens={"lab/free": 0})
    assert exhausted == []


def test_default_route_does_not_assume_free_balance(monkeypatch):
    _patch_models(monkeypatch)
    cascade = pricing_engine.calculate_optimal_routing(2400, 200, 0.02, current_qps=10)
    assert cascade[0].model_id != "lab/free"


def test_tiered_pricing_uses_overflow_tier(monkeypatch):
    _patch_models(monkeypatch, [TEST_MODELS[3]])
    cascade = pricing_engine.calculate_optimal_routing(5000, 500, 1.0, current_qps=5)
    assert cascade[0].estimated_cost_usd == pytest.approx(0.007, abs=1e-6)


def test_burst_traffic_filters_over_capacity(monkeypatch):
    models = deepcopy(TEST_MODELS[:2])
    models[0]["qps"] = 30.0
    models[0]["hard_capacity_factor"] = 1.1
    _patch_models(monkeypatch, models)
    report = pricing_engine.calculate_optimal_routing(2400, 200, 0.05, current_qps=40, return_report=True)
    assert [item.model_id for item in report["cascade"]] == ["lab/fast"]
    assert report["observability"].filtered_by_capacity == 1


def test_long_text_discount_is_applied(monkeypatch):
    _patch_models(monkeypatch, [TEST_MODELS[0]])
    cascade = pricing_engine.calculate_optimal_routing(5000, 500, 1.0, current_qps=5)
    assert cascade[0].pricing_components["long_text_discount_usd"] > 0
    assert cascade[0].pricing_components["base_cost_usd"] > cascade[0].estimated_cost_usd


def test_observability_and_benchmark_targets(monkeypatch):
    _patch_models(monkeypatch)
    report = pricing_engine.calculate_optimal_routing(2400, 200, 0.05, current_qps=10, return_report=True)
    assert report["observability"].pricing_error_pct < 3
    assert report["benchmark_report"].pricing_accuracy_met is True
    assert report["benchmark_report"].switch_latency_met is True
    assert sum(report["observability"].applied_weights.values()) == pytest.approx(1.0, abs=1e-6)
    assert report["observability"].filtered_by_capability == 0


def test_cold_start_penalty_changes_latency(monkeypatch):
    _patch_models(monkeypatch, [{"model_id": "lab/cold", "in_price_1k": 0.001, "out_price_1k": 0.001, "ttfb_ms": 200, "qps": 20.0, "accuracy": 0.8, "cold_start_ms": 120, "cold_start_cost_usd": 0.0003}])
    warm = pricing_engine.calculate_optimal_routing(1000, 100, 1.0, current_qps=5)
    cold = pricing_engine.calculate_optimal_routing(1000, 100, 1.0, current_qps=0)
    assert cold[0].expected_ttfb_ms == warm[0].expected_ttfb_ms + 120
    assert cold[0].estimated_cost_usd > warm[0].estimated_cost_usd


def test_capability_filters_close_the_loop(monkeypatch):
    models = deepcopy(TEST_MODELS[:2])
    models[1]["supports_vision"] = True
    models[1]["supported_task_categories"] = ["general_chat"]
    _patch_models(monkeypatch, models)
    report = pricing_engine.calculate_optimal_routing(1200, 100, 0.05, current_qps=5, task_category="general_chat", requires_vision=True, return_report=True)
    assert [item.model_id for item in report["cascade"]] == ["lab/fast"]
    assert report["observability"].filtered_by_capability == 1
