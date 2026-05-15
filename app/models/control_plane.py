from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AgentCredential(Base):
    __tablename__ = "agent_credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, default="internal")
    agent_id: Mapped[str] = mapped_column(String(128), index=True)
    environment: Mapped[str] = mapped_column(String(64), index=True)
    api_key_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    rate_limit_rpm: Mapped[int] = mapped_column(Integer, default=120)
    concurrent_limit: Mapped[int] = mapped_column(Integer, default=25)
    daily_budget_usd: Mapped[float] = mapped_column(Float, default=250.0)
    default_policy_id: Mapped[str] = mapped_column(String(64), default="balanced")
    budget_profile_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


class ModelCatalogVersion(Base):
    __tablename__ = "model_catalog_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    checksum: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    source: Mapped[str] = mapped_column(String(256))
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


class RoutingPolicyRecord(Base):
    __tablename__ = "routing_policies"

    policy_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    description: Mapped[str] = mapped_column(Text)
    config: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


class RoutingDecisionRecord(Base):
    __tablename__ = "routing_decisions"
    __table_args__ = (
        UniqueConstraint("agent_id", "idempotency_key", name="uq_routing_decisions_agent_idempotency"),
        Index("ix_routing_decisions_request_id", "request_id"),
    )

    decision_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, default="internal")
    agent_id: Mapped[str] = mapped_column(String(128), index=True)
    environment: Mapped[str] = mapped_column(String(64), index=True)
    workflow_id: Mapped[str] = mapped_column(String(128))
    session_id: Mapped[str] = mapped_column(String(128))
    request_id: Mapped[str] = mapped_column(String(128))
    catalog_version: Mapped[str] = mapped_column(String(64))
    policy_id: Mapped[str] = mapped_column(String(64))
    policy_version: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    outcome_idempotency_key: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="open")
    recommended_model_id: Mapped[str] = mapped_column(String(256))
    request_payload: Mapped[dict] = mapped_column(JSON)
    response_payload: Mapped[dict] = mapped_column(JSON)
    outcome_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    final_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    final_model_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    fallback_depth: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


class RoutingAttemptRecord(Base):
    __tablename__ = "routing_attempts"
    __table_args__ = (Index("ix_routing_attempts_decision_rank", "decision_id", "rank"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    decision_id: Mapped[str] = mapped_column(ForeignKey("routing_decisions.decision_id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(128))
    model_id: Mapped[str] = mapped_column(String(256))
    rank: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(64))
    error_class: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer)
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    cost_usd: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


class ProbeSnapshotRecord(Base):
    __tablename__ = "probe_snapshots"
    __table_args__ = (Index("ix_probe_snapshots_model_captured", "model_id", "captured_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(128), index=True)
    model_id: Mapped[str] = mapped_column(String(256), index=True)
    status: Mapped[str] = mapped_column(String(32))
    ttfb_ms: Mapped[int] = mapped_column(Integer)
    throughput_hint_qps: Mapped[float] = mapped_column(Float)
    success_rate: Mapped[float] = mapped_column(Float)
    degraded_reason: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    signal_payload: Mapped[dict] = mapped_column(JSON)
    captured_at: Mapped[datetime] = mapped_column(default=_utcnow)
