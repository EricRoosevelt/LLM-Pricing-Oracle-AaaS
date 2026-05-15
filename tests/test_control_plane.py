import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from app.core.metrics import MetricsStore
from app.schemas.routing import AgentPrincipal, RoutingDecisionRequest, RoutingOutcomeRequest
from app.services.control_plane import (
    CatalogRegistry,
    ControlPlaneDependencies,
    ControlPlaneService,
    InMemoryEventPublisher,
    InMemoryQuotaManager,
    NotFoundError,
    build_default_policies,
)
from app.services.latency_tracker import InMemorySignalStore
from app.services.persistence import duplicate_outcome_payload, normalize_probe_snapshot_payload
from app.services.pricing_engine import calculate_routing_decision


CATALOG_PAYLOAD = {
    "catalog_version": "test-catalog",
    "providers": {
        "lab": {
            "display_name": "Lab",
            "base_url": "https://example.invalid/v1/chat/completions",
            "models": {
                "budget": {
                    "display_name": "Budget",
                    "in_price_1k": 0.001,
                    "out_price_1k": 0.0012,
                    "qps": 90.0,
                    "ttfb_ms": 280,
                    "accuracy": 0.8,
                    "context_window_tokens": 32000,
                    "capabilities": {
                        "vision": False,
                        "reasoning": False,
                        "tool_calling": True,
                        "json_mode": True,
                        "supported_task_types": ["general_chat", "tool_execution"],
                    },
                },
                "reasoner": {
                    "display_name": "Reasoner",
                    "in_price_1k": 0.004,
                    "out_price_1k": 0.005,
                    "qps": 30.0,
                    "ttfb_ms": 720,
                    "accuracy": 0.93,
                    "context_window_tokens": 64000,
                    "capabilities": {
                        "vision": False,
                        "reasoning": True,
                        "tool_calling": False,
                        "json_mode": True,
                        "supported_task_types": ["general_chat", "reasoning"],
                    },
                },
                "vision": {
                    "display_name": "Vision",
                    "in_price_1k": 0.003,
                    "out_price_1k": 0.003,
                    "qps": 50.0,
                    "ttfb_ms": 500,
                    "accuracy": 0.85,
                    "context_window_tokens": 32000,
                    "capabilities": {
                        "vision": True,
                        "reasoning": False,
                        "tool_calling": False,
                        "json_mode": True,
                        "supported_task_types": ["general_chat", "summarization"],
                    },
                },
            },
        }
    },
}


class FakeCredentialStore:
    def __init__(self, principal: AgentPrincipal) -> None:
        self.principal = principal

    async def authenticate(self, api_key: str):
        return self.principal if api_key == "valid-key" else None


class FakeMetadataStore:
    async def ensure_catalog_version(self, catalog):
        return None

    async def ensure_policies(self, policies):
        return None


@dataclass
class FakeDecisionRecord:
    decision_id: str
    agent_id: str
    request_id: str
    outcome_payload: dict | None = None
    outcome_idempotency_key: str | None = None


class FakeDecisionStore:
    def __init__(self) -> None:
        self.by_idempotency = {}
        self.by_id = {}
        self.created = 0

    async def get_by_idempotency(self, agent_id, idempotency_key):
        return self.by_idempotency.get((agent_id, idempotency_key))

    async def create_decision(self, principal, request, response, idempotency_key):
        self.created += 1
        self.by_idempotency[(principal.agent_id, idempotency_key)] = response
        self.by_id[response.decision_id] = FakeDecisionRecord(
            decision_id=response.decision_id,
            agent_id=principal.agent_id,
            request_id=request.request_id,
        )

    async def get_decision_context(self, decision_id):
        return self.by_id.get(decision_id)

    async def record_outcome(self, record, outcome, idempotency_key):
        if record.outcome_payload:
            payload = dict(record.outcome_payload)
            payload["outcome_status"] = "duplicate"
            from app.schemas.routing import RoutingOutcomeResponse

            return RoutingOutcomeResponse.model_validate(payload)
        from app.schemas.routing import RoutingOutcomeResponse

        response = RoutingOutcomeResponse(
            decision_id=record.decision_id,
            outcome_status="recorded",
            final_status=outcome.final_status,
            attempts_recorded=len(outcome.attempts),
            fallback_depth=outcome.fallback_depth,
        )
        record.outcome_payload = response.model_dump(mode="json")
        record.outcome_idempotency_key = idempotency_key
        return response

    async def db_ready(self):
        return True


def _fresh_signal(provider: str, model_id: str, ttfb_ms: int, qps: float, success_rate: float = 1.0, degraded_reason=None):
    return {
        "provider": provider,
        "model_id": model_id,
        "ttfb_p50_ms": ttfb_ms,
        "ttfb_p95_ms": int(ttfb_ms * 1.2),
        "throughput_hint_qps": qps,
        "success_rate": success_rate,
        "last_probe_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "degraded_reason": degraded_reason,
    }


def build_service(tmp_path, daily_budget_usd: float = 50.0):
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(CATALOG_PAYLOAD), encoding="utf-8")
    principal = AgentPrincipal(
        agent_id="agent-1",
        environment="internal",
        tenant_id="internal",
        status="active",
        scopes=["routing:decide", "routing:outcome", "control:read"],
        rate_limit_rpm=50,
        concurrent_limit=5,
        daily_budget_usd=daily_budget_usd,
        default_policy_id="balanced",
    )
    signal_store = InMemorySignalStore()
    asyncio.run(signal_store.set_signal("lab/budget", _fresh_signal("lab", "lab/budget", 250, 100.0)))
    asyncio.run(signal_store.set_signal("lab/reasoner", _fresh_signal("lab", "lab/reasoner", 700, 30.0)))
    asyncio.run(signal_store.set_signal("lab/vision", _fresh_signal("lab", "lab/vision", 480, 60.0)))
    deps = ControlPlaneDependencies(
        credential_store=FakeCredentialStore(principal),
        metadata_store=FakeMetadataStore(),
        decision_store=FakeDecisionStore(),
        signal_store=signal_store,
        quota_manager=InMemoryQuotaManager(),
        event_publisher=InMemoryEventPublisher(),
        catalog_registry=CatalogRegistry(catalog_path),
        metrics=MetricsStore(),
        policies=build_default_policies(),
    )
    return ControlPlaneService(deps), principal


def test_pricing_engine_prefers_budget_candidate_for_balanced_policy(tmp_path):
    service, principal = build_service(tmp_path)
    catalog = service.deps.catalog_registry.get_snapshot()
    request = RoutingDecisionRequest(
        agent_id=principal.agent_id,
        workflow_id="wf-1",
        session_id="session-1",
        request_id="req-1",
        task_type="general_chat",
        modalities=["text"],
        language="zh",
        input_chars=2000,
        expected_output_tokens=300,
        context_window_tokens=8192,
        budget_limit_usd=0.02,
        latency_slo_ms=1500,
        throughput_hint_qps=3,
        policy_id="balanced",
        capability_requirements={"json_mode": True},
    )
    signals = asyncio.run(service.deps.signal_store.get_signals([model.model_id for model in catalog.models]))
    response = calculate_routing_decision(
        request=request,
        catalog=catalog,
        policy=service.deps.policies["balanced"],
        signals=signals,
        signal_freshness_seconds=90,
        ttl_seconds=300,
    )
    assert response.recommended.model_id == "lab/budget"
    assert response.observability.filtered_by_capability == 0
    assert response.candidates[0].confidence_score >= response.candidates[-1].confidence_score


def test_pricing_engine_records_capability_rejections(tmp_path):
    service, principal = build_service(tmp_path)
    catalog = service.deps.catalog_registry.get_snapshot()
    request = RoutingDecisionRequest(
        agent_id=principal.agent_id,
        workflow_id="wf-vision",
        session_id="session-vision",
        request_id="req-vision",
        task_type="summarization",
        modalities=["vision"],
        language="en",
        input_chars=800,
        expected_output_tokens=120,
        context_window_tokens=4096,
        budget_limit_usd=0.1,
        latency_slo_ms=2000,
        throughput_hint_qps=1,
        policy_id="balanced",
        capability_requirements={"vision": True},
    )
    signals = asyncio.run(service.deps.signal_store.get_signals([model.model_id for model in catalog.models]))
    response = calculate_routing_decision(
        request=request,
        catalog=catalog,
        policy=service.deps.policies["balanced"],
        signals=signals,
        signal_freshness_seconds=90,
        ttl_seconds=300,
    )
    assert response.recommended.model_id == "lab/vision"
    assert any(rejection.reason == "capability_filtered" for rejection in response.rejections)
    assert response.observability.filtered_by_capability >= 1


def test_control_plane_service_supports_decision_idempotency(tmp_path):
    service, principal = build_service(tmp_path)
    request = RoutingDecisionRequest(
        agent_id=principal.agent_id,
        workflow_id="wf-1",
        session_id="session-1",
        request_id="req-idem",
        task_type="general_chat",
        modalities=["text"],
        language="en",
        input_chars=1600,
        expected_output_tokens=220,
        context_window_tokens=4096,
        budget_limit_usd=0.05,
        latency_slo_ms=1200,
        throughput_hint_qps=2,
        policy_id="balanced",
    )
    first = asyncio.run(service.create_decision(principal, request, "idem-1"))
    second = asyncio.run(service.create_decision(principal, request, "idem-1"))
    assert first.decision_id == second.decision_id
    assert service.deps.decision_store.created == 1


def test_control_plane_records_outcomes_and_duplicates(tmp_path):
    service, principal = build_service(tmp_path)
    request = RoutingDecisionRequest(
        agent_id=principal.agent_id,
        workflow_id="wf-2",
        session_id="session-2",
        request_id="req-outcome",
        task_type="general_chat",
        modalities=["text"],
        language="en",
        input_chars=1200,
        expected_output_tokens=200,
        context_window_tokens=4096,
        budget_limit_usd=0.05,
        latency_slo_ms=1500,
        throughput_hint_qps=1,
        policy_id="balanced",
    )
    decision = asyncio.run(service.create_decision(principal, request, "idem-outcome"))
    outcome = RoutingOutcomeRequest(
        decision_id=decision.decision_id,
        agent_id=principal.agent_id,
        request_id=request.request_id,
        final_status="success",
        attempts=[
            {
                "model_id": decision.recommended.model_id,
                "provider": decision.recommended.provider,
                "rank": 1,
                "status": "success",
                "error_class": None,
                "latency_ms": decision.recommended.expected_ttfb_ms,
                "input_tokens": 500,
                "output_tokens": 200,
                "cost_usd": decision.recommended.estimated_cost_usd,
            }
        ],
        final_model_id=decision.recommended.model_id,
        fallback_depth=0,
        end_to_end_latency_ms=decision.recommended.expected_ttfb_ms,
        final_cost_usd=decision.recommended.estimated_cost_usd,
        user_feedback="success",
    )
    recorded = asyncio.run(service.record_outcome(principal, outcome, "outcome-idem"))
    duplicate = asyncio.run(service.record_outcome(principal, outcome, "outcome-idem"))
    assert recorded.outcome_status == "recorded"
    assert duplicate.outcome_status == "duplicate"
    assert len(service.deps.event_publisher.outcome_events) == 1
    assert asyncio.run(service.deps.quota_manager.current_daily_spend(principal)) == pytest.approx(
        decision.recommended.estimated_cost_usd
    )


def test_persistence_duplicate_outcome_payload_never_replays_recorded_status():
    payload = {
        "decision_id": "decision-1",
        "outcome_status": "recorded",
        "final_status": "success",
        "attempts_recorded": 1,
        "fallback_depth": 0,
    }

    duplicate = duplicate_outcome_payload(payload)

    assert duplicate["outcome_status"] == "duplicate"
    assert payload["outcome_status"] == "recorded"


def test_persistence_normalizes_legacy_probe_signal_payloads():
    legacy_signal_payload = {
        "provider": "lab",
        "model_id": "lab/demo",
        "ttfb_p50_ms": 321,
        "ttfb_p95_ms": 500,
        "throughput_hint_qps": 12.5,
        "success_rate": 1.0,
        "last_probe_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "degraded_reason": None,
    }

    normalized = normalize_probe_snapshot_payload(legacy_signal_payload)

    assert normalized["status"] == "success"
    assert normalized["ttfb_ms"] == 321


def test_control_plane_budget_guard_raises_when_daily_budget_would_be_exceeded(tmp_path):
    service, principal = build_service(tmp_path, daily_budget_usd=0.01)
    asyncio.run(service.deps.quota_manager.record_spend(principal, 0.009))
    request = RoutingDecisionRequest(
        agent_id=principal.agent_id,
        workflow_id="wf-budget",
        session_id="session-budget",
        request_id="req-budget",
        task_type="general_chat",
        modalities=["text"],
        language="en",
        input_chars=1000,
        expected_output_tokens=100,
        context_window_tokens=4096,
        budget_limit_usd=0.005,
        latency_slo_ms=1500,
        throughput_hint_qps=1,
        policy_id="balanced",
    )
    with pytest.raises(Exception) as exc_info:
        asyncio.run(service.create_decision(principal, request, "idem-budget"))
    assert "daily budget" in str(exc_info.value)


def test_ready_health_requires_fresh_signals(tmp_path):
    service, _principal = build_service(tmp_path)
    ready = asyncio.run(service.ready_health())
    assert ready.status == "online"

    service.deps.signal_store.signals.clear()
    degraded = asyncio.run(service.ready_health())
    assert degraded.status == "degraded"
    assert degraded.details["fresh_signals"] is False
