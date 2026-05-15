"""add control plane tables

Revision ID: b7b5b6c7d8e9
Revises: 49704d1de009
Create Date: 2026-04-23 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7b5b6c7d8e9"
down_revision: Union[str, Sequence[str], None] = "49704d1de009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_credentials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("api_key_hash", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("rate_limit_rpm", sa.Integer(), nullable=False),
        sa.Column("concurrent_limit", sa.Integer(), nullable=False),
        sa.Column("daily_budget_usd", sa.Float(), nullable=False),
        sa.Column("default_policy_id", sa.String(length=64), nullable=False),
        sa.Column("budget_profile_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_agent_credentials_agent_id", "agent_credentials", ["agent_id"])
    op.create_index("ix_agent_credentials_environment", "agent_credentials", ["environment"])
    op.create_index("ix_agent_credentials_tenant_id", "agent_credentials", ["tenant_id"])
    op.create_index("ix_agent_credentials_api_key_hash", "agent_credentials", ["api_key_hash"], unique=True)

    op.create_table(
        "model_catalog_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=256), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_model_catalog_versions_version", "model_catalog_versions", ["version"], unique=True)
    op.create_index("ix_model_catalog_versions_checksum", "model_catalog_versions", ["checksum"])

    op.create_table(
        "routing_policies",
        sa.Column("policy_id", sa.String(length=64), primary_key=True),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_routing_policies_version", "routing_policies", ["version"])

    op.create_table(
        "routing_decisions",
        sa.Column("decision_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("workflow_id", sa.String(length=128), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("catalog_version", sa.String(length=64), nullable=False),
        sa.Column("policy_id", sa.String(length=64), nullable=False),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=True),
        sa.Column("outcome_idempotency_key", sa.String(length=256), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("recommended_model_id", sa.String(length=256), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("response_payload", sa.JSON(), nullable=False),
        sa.Column("outcome_payload", sa.JSON(), nullable=True),
        sa.Column("final_status", sa.String(length=32), nullable=True),
        sa.Column("final_model_id", sa.String(length=256), nullable=True),
        sa.Column("fallback_depth", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("agent_id", "idempotency_key", name="uq_routing_decisions_agent_idempotency"),
    )
    op.create_index("ix_routing_decisions_agent_id", "routing_decisions", ["agent_id"])
    op.create_index("ix_routing_decisions_environment", "routing_decisions", ["environment"])
    op.create_index("ix_routing_decisions_tenant_id", "routing_decisions", ["tenant_id"])
    op.create_index("ix_routing_decisions_created_at", "routing_decisions", ["created_at"])
    op.create_index("ix_routing_decisions_request_id", "routing_decisions", ["request_id"])

    op.create_table(
        "routing_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("decision_id", sa.String(length=64), sa.ForeignKey("routing_decisions.decision_id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(length=128), nullable=False),
        sa.Column("model_id", sa.String(length=256), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("error_class", sa.String(length=128), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_routing_attempts_decision_id", "routing_attempts", ["decision_id"])
    op.create_index("ix_routing_attempts_decision_rank", "routing_attempts", ["decision_id", "rank"])

    op.create_table(
        "probe_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(length=128), nullable=False),
        sa.Column("model_id", sa.String(length=256), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("ttfb_ms", sa.Integer(), nullable=False),
        sa.Column("throughput_hint_qps", sa.Float(), nullable=False),
        sa.Column("success_rate", sa.Float(), nullable=False),
        sa.Column("degraded_reason", sa.String(length=256), nullable=True),
        sa.Column("signal_payload", sa.JSON(), nullable=False),
        sa.Column("captured_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_probe_snapshots_provider", "probe_snapshots", ["provider"])
    op.create_index("ix_probe_snapshots_model_id", "probe_snapshots", ["model_id"])
    op.create_index("ix_probe_snapshots_model_captured", "probe_snapshots", ["model_id", "captured_at"])


def downgrade() -> None:
    op.drop_index("ix_probe_snapshots_model_captured", table_name="probe_snapshots")
    op.drop_index("ix_probe_snapshots_model_id", table_name="probe_snapshots")
    op.drop_index("ix_probe_snapshots_provider", table_name="probe_snapshots")
    op.drop_table("probe_snapshots")

    op.drop_index("ix_routing_attempts_decision_rank", table_name="routing_attempts")
    op.drop_index("ix_routing_attempts_decision_id", table_name="routing_attempts")
    op.drop_table("routing_attempts")

    op.drop_index("ix_routing_decisions_request_id", table_name="routing_decisions")
    op.drop_index("ix_routing_decisions_created_at", table_name="routing_decisions")
    op.drop_index("ix_routing_decisions_tenant_id", table_name="routing_decisions")
    op.drop_index("ix_routing_decisions_environment", table_name="routing_decisions")
    op.drop_index("ix_routing_decisions_agent_id", table_name="routing_decisions")
    op.drop_table("routing_decisions")

    op.drop_index("ix_routing_policies_version", table_name="routing_policies")
    op.drop_table("routing_policies")

    op.drop_index("ix_model_catalog_versions_checksum", table_name="model_catalog_versions")
    op.drop_index("ix_model_catalog_versions_version", table_name="model_catalog_versions")
    op.drop_table("model_catalog_versions")

    op.drop_index("ix_agent_credentials_api_key_hash", table_name="agent_credentials")
    op.drop_index("ix_agent_credentials_tenant_id", table_name="agent_credentials")
    op.drop_index("ix_agent_credentials_environment", table_name="agent_credentials")
    op.drop_index("ix_agent_credentials_agent_id", table_name="agent_credentials")
    op.drop_table("agent_credentials")
