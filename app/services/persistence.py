import logging
from typing import Iterable, Optional

from sqlalchemy import delete, select, text

from app.core.security import hash_api_key
from app.models.control_plane import (
    AgentCredential,
    ModelCatalogVersion,
    ProbeSnapshotRecord,
    RoutingAttemptRecord,
    RoutingDecisionRecord,
    RoutingPolicyRecord,
)
from app.schemas.routing import (
    AgentPrincipal,
    CatalogSnapshot,
    OutcomeAttempt,
    RoutingDecisionRequest,
    RoutingDecisionResponse,
    RoutingOutcomeRequest,
    RoutingOutcomeResponse,
    RoutingPolicy,
)


def duplicate_outcome_payload(payload: dict) -> dict:
    return {
        **payload,
        "outcome_status": "duplicate",
    }


def normalize_probe_snapshot_payload(payload: dict) -> dict:
    status = payload.get("status")
    if status is None:
        status = "degraded" if payload.get("degraded_reason") else "success"
    ttfb_ms = payload.get("ttfb_ms", payload.get("ttfb_p50_ms"))
    if ttfb_ms is None:
        raise ValueError("probe payload missing ttfb_ms/ttfb_p50_ms")
    return {
        **payload,
        "status": status,
        "ttfb_ms": int(ttfb_ms),
    }


class SqlAlchemyCredentialStore:
    def __init__(self, session_factory, bootstrap_credentials) -> None:
        self.session_factory = session_factory
        self.bootstrap_credentials = list(bootstrap_credentials)
        self._bootstrapped = False

    async def _ensure_bootstrap_credentials(self) -> None:  # pragma: no cover - integration glue
        if self._bootstrapped or not self.bootstrap_credentials:
            return
        async with self.session_factory() as session:
            async with session.begin():
                for bootstrap in self.bootstrap_credentials:
                    api_key_hash = hash_api_key(bootstrap.api_key)
                    existing = await session.scalar(
                        select(AgentCredential).where(AgentCredential.api_key_hash == api_key_hash)
                    )
                    if existing:
                        continue
                    session.add(
                        AgentCredential(
                            tenant_id=bootstrap.tenant_id,
                            agent_id=bootstrap.agent_id,
                            environment=bootstrap.environment,
                            api_key_hash=api_key_hash,
                            status=bootstrap.status,
                            scopes=bootstrap.scopes,
                            rate_limit_rpm=bootstrap.rate_limit_rpm,
                            concurrent_limit=bootstrap.concurrent_limit,
                            daily_budget_usd=bootstrap.daily_budget_usd,
                            default_policy_id=bootstrap.default_policy_id,
                            budget_profile_id=bootstrap.budget_profile_id,
                        )
                    )
        self._bootstrapped = True

    async def authenticate(self, api_key: str) -> Optional[AgentPrincipal]:  # pragma: no cover - integration glue
        await self._ensure_bootstrap_credentials()
        async with self.session_factory() as session:
            record = await session.scalar(
                select(AgentCredential).where(AgentCredential.api_key_hash == hash_api_key(api_key))
            )
            if not record:
                return None
            return AgentPrincipal(
                agent_id=record.agent_id,
                environment=record.environment,
                tenant_id=record.tenant_id,
                status=record.status,
                scopes=list(record.scopes or []),
                rate_limit_rpm=record.rate_limit_rpm,
                concurrent_limit=record.concurrent_limit,
                daily_budget_usd=record.daily_budget_usd,
                default_policy_id=record.default_policy_id,
                budget_profile_id=record.budget_profile_id,
            )


class SqlAlchemyMetadataStore:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    async def ensure_catalog_version(self, catalog: CatalogSnapshot) -> None:  # pragma: no cover - integration glue
        async with self.session_factory() as session:
            async with session.begin():
                existing = await session.scalar(
                    select(ModelCatalogVersion).where(ModelCatalogVersion.version == catalog.version)
                )
                if not existing:
                    session.add(
                        ModelCatalogVersion(
                            version=catalog.version,
                            checksum=catalog.checksum,
                            status="active",
                            source=catalog.source,
                            snapshot=catalog.model_dump(mode="json"),
                        )
                    )

    async def ensure_policies(self, policies: Iterable[RoutingPolicy]) -> None:  # pragma: no cover - integration glue
        async with self.session_factory() as session:
            async with session.begin():
                for policy in policies:
                    existing = await session.get(RoutingPolicyRecord, policy.policy_id)
                    if existing:
                        existing.version = policy.version
                        existing.status = policy.status
                        existing.description = policy.description
                        existing.config = policy.model_dump(mode="json")
                    else:
                        session.add(
                            RoutingPolicyRecord(
                                policy_id=policy.policy_id,
                                version=policy.version,
                                status=policy.status,
                                description=policy.description,
                                config=policy.model_dump(mode="json"),
                            )
                        )


class SqlAlchemyDecisionStore:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    async def get_by_idempotency(  # pragma: no cover - integration glue
        self,
        agent_id: str,
        idempotency_key: Optional[str],
    ) -> Optional[RoutingDecisionResponse]:
        if not idempotency_key:
            return None
        async with self.session_factory() as session:
            record = await session.scalar(
                select(RoutingDecisionRecord).where(
                    RoutingDecisionRecord.agent_id == agent_id,
                    RoutingDecisionRecord.idempotency_key == idempotency_key,
                )
            )
            if not record:
                return None
            return RoutingDecisionResponse.model_validate(record.response_payload)

    async def create_decision(  # pragma: no cover - integration glue
        self,
        principal: AgentPrincipal,
        request: RoutingDecisionRequest,
        response: RoutingDecisionResponse,
        idempotency_key: Optional[str],
    ) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                session.add(
                    RoutingDecisionRecord(
                        decision_id=response.decision_id,
                        tenant_id=principal.tenant_id,
                        agent_id=principal.agent_id,
                        environment=principal.environment,
                        workflow_id=request.workflow_id,
                        session_id=request.session_id,
                        request_id=request.request_id,
                        catalog_version=response.catalog_version,
                        policy_id=response.policy_id,
                        policy_version=response.policy_version,
                        idempotency_key=idempotency_key,
                        recommended_model_id=response.recommended.model_id,
                        request_payload=request.model_dump(mode="json"),
                        response_payload=response.model_dump(mode="json"),
                    )
                )

    async def get_decision_context(self, decision_id: str) -> Optional[RoutingDecisionRecord]:  # pragma: no cover - integration glue
        async with self.session_factory() as session:
            return await session.get(RoutingDecisionRecord, decision_id)

    async def record_outcome(  # pragma: no cover - integration glue
        self,
        record: RoutingDecisionRecord,
        outcome: RoutingOutcomeRequest,
        idempotency_key: Optional[str],
    ) -> RoutingOutcomeResponse:
        async with self.session_factory() as session:
            async with session.begin():
                decision = await session.get(RoutingDecisionRecord, record.decision_id)
                if decision is None:
                    raise LookupError(record.decision_id)
                if decision.outcome_payload:
                    payload = duplicate_outcome_payload(decision.outcome_payload)
                    if idempotency_key and decision.outcome_idempotency_key == idempotency_key:
                        return RoutingOutcomeResponse.model_validate(payload)
                    return RoutingOutcomeResponse.model_validate(payload)

                await session.execute(
                    delete(RoutingAttemptRecord).where(RoutingAttemptRecord.decision_id == decision.decision_id)
                )
                for attempt in outcome.attempts:
                    session.add(self._attempt_record(decision.decision_id, attempt))

                response = RoutingOutcomeResponse(
                    decision_id=decision.decision_id,
                    outcome_status="recorded",
                    final_status=outcome.final_status,
                    attempts_recorded=len(outcome.attempts),
                    fallback_depth=outcome.fallback_depth,
                )
                decision.outcome_idempotency_key = idempotency_key
                decision.status = "completed"
                decision.final_status = outcome.final_status
                decision.final_model_id = outcome.final_model_id
                decision.fallback_depth = outcome.fallback_depth
                decision.outcome_payload = response.model_dump(mode="json")
                return response

    @staticmethod
    def _attempt_record(decision_id: str, attempt: OutcomeAttempt) -> RoutingAttemptRecord:
        return RoutingAttemptRecord(
            decision_id=decision_id,
            provider=attempt.provider,
            model_id=attempt.model_id,
            rank=attempt.rank,
            status=attempt.status,
            error_class=attempt.error_class,
            latency_ms=attempt.latency_ms,
            input_tokens=attempt.input_tokens,
            output_tokens=attempt.output_tokens,
            cost_usd=attempt.cost_usd,
        )

    async def record_probe_snapshot(self, payload: dict) -> None:  # pragma: no cover - integration glue
        normalized = normalize_probe_snapshot_payload(payload)

        async with self.session_factory() as session:
            async with session.begin():
                session.add(
                    ProbeSnapshotRecord(
                        provider=normalized["provider"],
                        model_id=normalized["model_id"],
                        status=normalized["status"],
                        ttfb_ms=normalized["ttfb_ms"],
                        throughput_hint_qps=normalized["throughput_hint_qps"],
                        success_rate=normalized["success_rate"],
                        degraded_reason=normalized.get("degraded_reason"),
                        signal_payload=normalized,
                    )
                )

    async def db_ready(self) -> bool:  # pragma: no cover - integration glue
        try:
            async with self.session_factory() as session:
                await session.execute(text("SELECT 1"))
            return True
        except Exception as exc:  # pragma: no cover - depends on external database
            logging.warning("database readiness failed: %s", exc)
            return False
