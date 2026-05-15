import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Optional
from uuid import uuid4

import redis.asyncio as redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.metrics import MetricsStore, metrics_store
from app.schemas.routing import (
    AgentPrincipal,
    CatalogModel,
    CatalogProvider,
    CatalogResponse,
    CatalogSnapshot,
    HealthResponse,
    ModelCapabilities,
    PolicyListResponse,
    PolicyWeights,
    RoutingDecisionRequest,
    RoutingDecisionResponse,
    RoutingOutcomeRequest,
    RoutingOutcomeResponse,
    RoutingPolicy,
)
from app.services.latency_tracker import InMemorySignalStore, RedisSignalStore
from app.services.pricing_engine import calculate_routing_decision


class AuthenticationError(RuntimeError):
    pass


class AuthorizationError(RuntimeError):
    pass


class NotFoundError(RuntimeError):
    pass


class QuotaExceededError(RuntimeError):
    pass


class CatalogRegistry:
    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self._snapshot: Optional[CatalogSnapshot] = None
        self._checksum: Optional[str] = None

    def get_snapshot(self) -> CatalogSnapshot:
        raw_text = self.config_path.read_text(encoding="utf-8")
        checksum = sha256(raw_text.encode("utf-8")).hexdigest()
        if self._snapshot and self._checksum == checksum:
            return self._snapshot

        raw = json.loads(raw_text)
        providers: list[CatalogProvider] = []
        models: list[CatalogModel] = []
        for provider_name, provider_info in raw.get("providers", {}).items():
            provider_models: list[CatalogModel] = []
            for model_name, model_info in provider_info.get("models", {}).items():
                capability_info = model_info.get("capabilities", {})
                model = CatalogModel(
                    provider=provider_name,
                    model_name=model_name,
                    model_id=f"{provider_name}/{model_name}",
                    display_name=model_info.get("display_name", model_name),
                    in_price_1k=model_info["in_price_1k"],
                    out_price_1k=model_info["out_price_1k"],
                    pricing_tiers=model_info.get("pricing_tiers", []),
                    context_window_tokens=model_info.get("context_window_tokens", 8192),
                    default_ttfb_ms=model_info.get("ttfb_ms", 900),
                    throughput_hint_qps=model_info.get("qps", 20.0),
                    accuracy=model_info.get("accuracy", 0.72),
                    hard_capacity_factor=model_info.get("hard_capacity_factor", 1.15),
                    capabilities=ModelCapabilities(
                        vision=capability_info.get("vision", model_info.get("supports_vision", False)),
                        reasoning=capability_info.get(
                            "reasoning", "reasoner" in model_name or model_info.get("reasoning", False)
                        ),
                        tool_calling=capability_info.get("tool_calling", model_info.get("tool_calling", False)),
                        json_mode=capability_info.get("json_mode", model_info.get("json_mode", False)),
                        supported_task_types=capability_info.get(
                            "supported_task_types",
                            model_info.get(
                                "supported_task_types",
                                model_info.get("supported_task_categories", ["general_chat"]),
                            ),
                        ),
                    ),
                    cold_start_ms=model_info.get("cold_start_ms", 0),
                    cold_start_cost_usd=model_info.get("cold_start_cost_usd", 0.0),
                    long_text_discount_rate=model_info.get("long_text_discount_rate", 0.0),
                    long_text_threshold_tokens=model_info.get("long_text_threshold_tokens", 16000),
                    concurrency_premium_rate=model_info.get("concurrency_premium_rate", 0.0),
                    burst_qps_threshold=model_info.get("burst_qps_threshold", 0.85),
                    probe_endpoint=model_info.get("probe_endpoint", provider_info.get("base_url")),
                )
                provider_models.append(model)
                models.append(model)
            providers.append(
                CatalogProvider(
                    provider=provider_name,
                    display_name=provider_info.get("display_name", provider_name),
                    base_url=provider_info["base_url"],
                    env_key_name=provider_info.get("env_key_name"),
                    models=provider_models,
                )
            )

        scoring_defaults = raw.get("scoring_defaults", {})
        version = raw.get("catalog_version", checksum[:12])
        self._snapshot = CatalogSnapshot(
            version=version,
            checksum=checksum,
            source=str(self.config_path),
            providers=providers,
            models=models,
            normalization_baseline=scoring_defaults.get("normalization_baseline", {}),
        )
        self._checksum = checksum
        return self._snapshot


def build_default_policies() -> dict[str, RoutingPolicy]:
    version = "2026.04.v1"
    return {
        "balanced": RoutingPolicy(
            policy_id="balanced",
            version=version,
            description="Balanced default for mixed agent workloads.",
            weights=PolicyWeights(token_cost=0.35, qps=0.15, latency=0.25, accuracy=0.25),
            max_candidates=4,
            freshness_penalty=0.12,
            degraded_penalty=0.18,
            fallback_bonus=0.05,
        ),
        "cheap-first": RoutingPolicy(
            policy_id="cheap-first",
            version=version,
            description="Bias toward lower spend while keeping viable fallbacks.",
            weights=PolicyWeights(token_cost=0.55, qps=0.1, latency=0.15, accuracy=0.2),
            max_candidates=4,
            freshness_penalty=0.12,
            degraded_penalty=0.18,
            fallback_bonus=0.04,
        ),
        "latency-first": RoutingPolicy(
            policy_id="latency-first",
            version=version,
            description="Bias toward fast first-token response for interactive agents.",
            weights=PolicyWeights(token_cost=0.15, qps=0.15, latency=0.45, accuracy=0.25),
            max_candidates=3,
            freshness_penalty=0.1,
            degraded_penalty=0.2,
            fallback_bonus=0.04,
        ),
        "reasoning-first": RoutingPolicy(
            policy_id="reasoning-first",
            version=version,
            description="Bias toward higher quality/reasoning capacity even if it costs more.",
            weights=PolicyWeights(token_cost=0.1, qps=0.1, latency=0.2, accuracy=0.6),
            max_candidates=3,
            freshness_penalty=0.12,
            degraded_penalty=0.16,
            fallback_bonus=0.03,
        ),
        "safe-fallback": RoutingPolicy(
            policy_id="safe-fallback",
            version=version,
            description="Prefer routes with healthier fallback ladders under uncertain signals.",
            weights=PolicyWeights(token_cost=0.2, qps=0.2, latency=0.2, accuracy=0.4),
            max_candidates=5,
            freshness_penalty=0.08,
            degraded_penalty=0.14,
            fallback_bonus=0.08,
        ),
    }


class InMemoryEventPublisher:
    def __init__(self) -> None:
        self.outcome_events: list[dict[str, Any]] = []
        self.probe_events: list[dict[str, Any]] = []

    async def publish_outcome(self, payload: dict[str, Any]) -> None:
        self.outcome_events.append(payload)

    async def publish_probe(self, payload: dict[str, Any]) -> None:
        self.probe_events.append(payload)

    async def ping(self) -> bool:
        return True


class RedisEventPublisher:
    def __init__(self, client: redis.Redis) -> None:
        self.client = client

    async def publish_outcome(self, payload: dict[str, Any]) -> None:  # pragma: no cover - integration glue
        await self.client.xadd(settings.OUTCOME_STREAM_NAME, {"payload": json.dumps(payload)})

    async def publish_probe(self, payload: dict[str, Any]) -> None:  # pragma: no cover - integration glue
        await self.client.xadd(settings.PROBE_STREAM_NAME, {"payload": json.dumps(payload)})

    async def ping(self) -> bool:  # pragma: no cover - integration glue
        try:
            await self.client.ping()
            return True
        except RedisError:
            return False


class InMemoryQuotaManager:
    def __init__(self) -> None:
        self.rpm: dict[tuple[str, str, int], int] = defaultdict(int)
        self.concurrent: dict[tuple[str, str], set[str]] = defaultdict(set)
        self.daily_budget: dict[tuple[str, str, str], float] = defaultdict(float)

    async def enforce_rpm(self, principal: AgentPrincipal) -> None:
        minute_key = int(__import__("time").time() // 60)
        key = (principal.environment, principal.agent_id, minute_key)
        self.rpm[key] += 1
        if self.rpm[key] > principal.rate_limit_rpm:
            raise QuotaExceededError("agent RPM exceeded")

    async def reserve_concurrency(self, principal: AgentPrincipal, decision_id: str) -> None:
        key = (principal.environment, principal.agent_id)
        current = self.concurrent[key]
        current.add(decision_id)
        if len(current) > principal.concurrent_limit:
            current.discard(decision_id)
            raise QuotaExceededError("agent concurrent limit exceeded")

    async def release_concurrency(self, principal: AgentPrincipal, decision_id: str) -> None:
        self.concurrent[(principal.environment, principal.agent_id)].discard(decision_id)

    async def current_daily_spend(self, principal: AgentPrincipal) -> float:
        return self.daily_budget[(principal.environment, principal.agent_id, date.today().isoformat())]

    async def record_spend(self, principal: AgentPrincipal, amount: float) -> None:
        self.daily_budget[(principal.environment, principal.agent_id, date.today().isoformat())] += amount

    async def ping(self) -> bool:
        return True


class RedisQuotaManager:
    def __init__(self, client: redis.Redis) -> None:
        self.client = client

    async def enforce_rpm(self, principal: AgentPrincipal) -> None:  # pragma: no cover - integration glue
        minute_key = int(__import__("time").time() // 60)
        key = f"quota:rpm:{principal.environment}:{principal.agent_id}:{minute_key}"
        count = await self.client.incr(key)
        if count == 1:
            await self.client.expire(key, 60)
        if count > principal.rate_limit_rpm:
            raise QuotaExceededError("agent RPM exceeded")

    async def reserve_concurrency(self, principal: AgentPrincipal, decision_id: str) -> None:  # pragma: no cover - integration glue
        key = f"quota:concurrency:{principal.environment}:{principal.agent_id}"
        await self.client.sadd(key, decision_id)
        await self.client.expire(key, settings.DECISION_TTL_SECONDS * 6)
        count = await self.client.scard(key)
        if count > principal.concurrent_limit:
            await self.client.srem(key, decision_id)
            raise QuotaExceededError("agent concurrent limit exceeded")

    async def release_concurrency(self, principal: AgentPrincipal, decision_id: str) -> None:  # pragma: no cover - integration glue
        key = f"quota:concurrency:{principal.environment}:{principal.agent_id}"
        await self.client.srem(key, decision_id)

    async def current_daily_spend(self, principal: AgentPrincipal) -> float:  # pragma: no cover - integration glue
        key = f"quota:budget:{principal.environment}:{principal.agent_id}:{date.today().isoformat()}"
        raw = await self.client.get(key)
        return float(raw or 0.0)

    async def record_spend(self, principal: AgentPrincipal, amount: float) -> None:  # pragma: no cover - integration glue
        key = f"quota:budget:{principal.environment}:{principal.agent_id}:{date.today().isoformat()}"
        await self.client.incrbyfloat(key, amount)
        await self.client.expire(key, 86400 * 7)

    async def ping(self) -> bool:  # pragma: no cover - integration glue
        try:
            await self.client.ping()
            return True
        except RedisError:
            return False


@dataclass
class ControlPlaneDependencies:
    credential_store: Any
    metadata_store: Any
    decision_store: Any
    signal_store: Any
    quota_manager: Any
    event_publisher: Any
    catalog_registry: CatalogRegistry
    metrics: MetricsStore
    policies: dict[str, RoutingPolicy]


class ControlPlaneService:
    def __init__(self, deps: ControlPlaneDependencies) -> None:
        self.deps = deps

    async def authenticate(self, api_key: Optional[str], required_scopes: Iterable[str]) -> AgentPrincipal:
        if not api_key:
            raise AuthenticationError("Missing X-API-Key header.")
        principal = await self.deps.credential_store.authenticate(api_key)
        if not principal:
            raise AuthenticationError("Invalid API key.")
        if principal.status != "active":
            raise AuthorizationError("Agent credential is blocked.")
        required = set(required_scopes)
        if not required.issubset(set(principal.scopes)):
            raise AuthorizationError("Required scope is missing for this credential.")
        return principal

    async def create_decision(
        self,
        principal: AgentPrincipal,
        request: RoutingDecisionRequest,
        idempotency_key: Optional[str],
    ) -> RoutingDecisionResponse:
        if principal.agent_id != request.agent_id:
            raise AuthorizationError("request agent_id does not match authenticated credential.")
        existing = await self.deps.decision_store.get_by_idempotency(principal.agent_id, idempotency_key)
        if existing:
            return existing

        await self.deps.quota_manager.enforce_rpm(principal)
        current_spend = await self.deps.quota_manager.current_daily_spend(principal)
        if current_spend + request.budget_limit_usd > principal.daily_budget_usd:
            raise QuotaExceededError("daily budget would be exceeded by this decision request.")

        catalog = self.deps.catalog_registry.get_snapshot()
        policy_id = request.policy_id or principal.default_policy_id or settings.DEFAULT_POLICY_ID
        policy = self.deps.policies.get(policy_id)
        if not policy or policy.status != "active":
            raise NotFoundError(f"Unknown or inactive policy '{policy_id}'.")

        try:
            await self.deps.metadata_store.ensure_catalog_version(catalog)
            await self.deps.metadata_store.ensure_policies(self.deps.policies.values())
        except Exception as exc:  # pragma: no cover - best effort persistence
            logging.warning("metadata persistence skipped: %s", exc)

        decision_id = uuid4().hex
        await self.deps.quota_manager.reserve_concurrency(principal, decision_id)
        try:
            signals = await self.deps.signal_store.get_signals([model.model_id for model in catalog.models])
            response = calculate_routing_decision(
                request=request,
                catalog=catalog,
                policy=policy,
                signals=signals,
                signal_freshness_seconds=settings.SIGNAL_FRESHNESS_SECONDS,
                ttl_seconds=settings.DECISION_TTL_SECONDS,
            ).model_copy(update={"decision_id": decision_id})
            await self.deps.decision_store.create_decision(
                principal=principal,
                request=request,
                response=response,
                idempotency_key=idempotency_key,
            )
        except Exception:
            await self.deps.quota_manager.release_concurrency(principal, decision_id)
            raise

        self.deps.metrics.incr(
            "routing_decisions_total",
            labels={"policy_id": response.policy_id, "agent_id": principal.agent_id},
        )
        self.deps.metrics.observe(
            "routing_decision_latency_ms",
            response.observability.decision_compute_ms,
            labels={"policy_id": response.policy_id},
        )
        self.deps.metrics.observe(
            "routing_candidate_count",
            len(response.candidates),
            labels={"policy_id": response.policy_id},
        )
        for rejection in response.rejections:
            self.deps.metrics.incr(
                "routing_rejections_total",
                labels={"reason": rejection.reason, "provider": rejection.provider},
            )
        self.deps.metrics.incr(
            "routing_policy_hits_total",
            labels={"policy_id": response.policy_id},
        )
        self.deps.metrics.set_gauge(
            "routing_probe_freshness_seconds",
            float(response.observability.signal_freshness_min_seconds or 0),
            labels={"policy_id": response.policy_id},
        )
        return response

    async def record_outcome(
        self,
        principal: AgentPrincipal,
        outcome: RoutingOutcomeRequest,
        idempotency_key: Optional[str],
    ) -> RoutingOutcomeResponse:
        if principal.agent_id != outcome.agent_id:
            raise AuthorizationError("outcome agent_id does not match authenticated credential.")

        await self.deps.quota_manager.enforce_rpm(principal)
        record = await self.deps.decision_store.get_decision_context(outcome.decision_id)
        if not record:
            raise NotFoundError(f"Unknown decision_id '{outcome.decision_id}'.")
        if record.agent_id != principal.agent_id:
            raise AuthorizationError("decision ownership mismatch.")
        if record.request_id != outcome.request_id:
            raise AuthorizationError("outcome request_id does not match the original decision request.")

        response = await self.deps.decision_store.record_outcome(record, outcome, idempotency_key)
        if response.outcome_status == "recorded":
            await self.deps.quota_manager.release_concurrency(principal, outcome.decision_id)
            await self.deps.quota_manager.record_spend(principal, outcome.final_cost_usd)
            await self.deps.event_publisher.publish_outcome(
                {
                    "decision_id": outcome.decision_id,
                    "agent_id": principal.agent_id,
                    "request_id": outcome.request_id,
                    "final_status": outcome.final_status,
                    "final_model_id": outcome.final_model_id,
                    "fallback_depth": outcome.fallback_depth,
                    "final_cost_usd": outcome.final_cost_usd,
                    "end_to_end_latency_ms": outcome.end_to_end_latency_ms,
                }
            )
            self.deps.metrics.incr(
                "routing_outcomes_total",
                labels={"final_status": outcome.final_status, "agent_id": principal.agent_id},
            )
            self.deps.metrics.observe(
                "routing_fallback_depth",
                outcome.fallback_depth,
                labels={"final_status": outcome.final_status},
            )
        return response

    async def get_catalog(self) -> CatalogResponse:
        snapshot = self.deps.catalog_registry.get_snapshot()
        return CatalogResponse(
            catalog_version=snapshot.version,
            checksum=snapshot.checksum,
            providers=snapshot.providers,
            models=snapshot.models,
        )

    async def get_policies(self) -> PolicyListResponse:
        return PolicyListResponse(policies=list(self.deps.policies.values()))

    async def live_health(self) -> HealthResponse:
        return HealthResponse(
            status="online",
            project=settings.PROJECT_NAME,
            details={"mode": "agent-routing-control-plane"},
        )

    async def ready_health(self) -> HealthResponse:
        catalog = self.deps.catalog_registry.get_snapshot()
        redis_ready = await self.deps.quota_manager.ping() and await self.deps.event_publisher.ping()
        db_ready = await self.deps.decision_store.db_ready()
        fresh_signals = await self.deps.signal_store.has_fresh_signals(settings.SIGNAL_FRESHNESS_SECONDS)
        details = {
            "database": db_ready,
            "redis": redis_ready,
            "catalog_loaded": bool(catalog.models),
            "fresh_signals": fresh_signals,
        }
        status = "online" if all(details.values()) else "degraded"
        return HealthResponse(status=status, project=settings.PROJECT_NAME, details=details)


def build_runtime_dependencies(
    credential_store,
    metadata_store,
    decision_store,
    signal_store,
    quota_manager,
    event_publisher,
    metrics: MetricsStore | None = None,
) -> ControlPlaneDependencies:
    return ControlPlaneDependencies(
        credential_store=credential_store,
        metadata_store=metadata_store,
        decision_store=decision_store,
        signal_store=signal_store,
        quota_manager=quota_manager,
        event_publisher=event_publisher,
        catalog_registry=CatalogRegistry(settings.catalog_path),
        metrics=metrics or metrics_store,
        policies=build_default_policies(),
    )


def build_redis_runtime(credential_store, metadata_store, decision_store) -> ControlPlaneService:  # pragma: no cover - integration glue
    redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    deps = build_runtime_dependencies(
        credential_store=credential_store,
        metadata_store=metadata_store,
        decision_store=decision_store,
        signal_store=RedisSignalStore(redis_client),
        quota_manager=RedisQuotaManager(redis_client),
        event_publisher=RedisEventPublisher(redis_client),
    )
    return ControlPlaneService(deps)


def build_in_memory_runtime(
    credential_store,
    decision_store,
    metadata_store,
) -> ControlPlaneService:
    deps = build_runtime_dependencies(
        credential_store=credential_store,
        metadata_store=metadata_store,
        decision_store=decision_store,
        signal_store=InMemorySignalStore(),
        quota_manager=InMemoryQuotaManager(),
        event_publisher=InMemoryEventPublisher(),
    )
    return ControlPlaneService(deps)
