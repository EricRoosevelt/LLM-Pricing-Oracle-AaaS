# LLM Agent Routing Control Plane

[English](./README.md) | [中文说明](./README_zh.md)

An agent-first routing control plane for LLM workloads. It evaluates budget, task shape, latency, concurrency, capability requirements, and probe freshness *before* execution to return a durable routing `decision` plus an ordered fallback ladder that Agents can execute with their own vendor keys.

## Architecture & Responsibilities

- **Control Plane**: Accepts Agent routing requests, combines catalog metadata, routing policies, and probe signals, then returns a durable `decision_id` with ranked candidates and rejection reasons.
- **Agent Runtime**: Executes the actual model invocation using its own vendor API keys and reports the outcome back to the control plane.
- **Deployment Target**: Run as an internal control plane for multiple Agents and workflows without proxying real model traffic.

## Key Innovations

- **Decoupled Routing & Invocation**: The server exclusively handles routing decisions. It does not proxy real chat traffic or hold user vendor keys, significantly reducing the risk of centralized key exposure.
- **Unified Multi-Dimensional Scoring**: Normalizes pricing, QPS, latency, and accuracy into a single dimensional space, supporting dynamic, per-request weight adjustments.
- **Real-World Load Correction Factors**: Integrates cold start penalties, long-context discounts, concurrency premiums, tiered pricing, and free-tier allowances into the final decision matrix.
- **Closed-Loop Capability Filtering**: Candidates are pre-filtered based on vision support and task category compatibility, avoiding the "technically capable but practically unusable" trap.
- **Agent-Friendly Failure Recovery**: The control plane returns ranked candidates and a durable `decision_id`; Agents can retry and fall back deterministically, then report what actually happened.

## Tech Stack

- **FastAPI**: Exposes the Agent-first control plane API.
- **Pydantic v2**: Defines decision, outcome, catalog, and policy contracts.
- **SQLAlchemy + Alembic**: Persists control-plane records and schema migrations.
- **Redis + Redis Streams**: Drives quotas, signal cache, and async event fanout.
- **HTTPX**: Powers probe-worker checks and the example Agent client.
- **Pytest + pytest-cov**: Validates decision logic, quotas, and observability primitives.

## Architectural Highlights & Advantages

### 1. Agent-native
- The control plane only decides and records. It never proxies model traffic.
- Agents remain free to implement retries, vendor SDK logic, tool execution, and orchestration.

### 2. Decision durability
- Every request produces a durable `decision_id`.
- Idempotency and outcome reporting let Agents retry safely without duplicating records.

### 3. Control-plane observability
- Decisions carry ranked candidates, rejections, and policy trace data.
- Metrics cover decision latency, probe freshness, candidate count, rejection reasons, and outcome success.

### 4. Operable at runtime
- Probe collection is split into a dedicated worker.
- Event consumption is split into a separate worker for probe snapshot persistence and future aggregate processing.

## Default Policies

- `balanced`
- `cheap-first`
- `latency-first`
- `reasoning-first`
- `safe-fallback`

Each policy is centrally managed by the control plane and selected by `policy_id`.

## Core Workflow

1. Agent prepares task shape, budget, context, latency SLO, and capability requirements.
2. Agent calls `POST /v1/routing/decisions`.
3. The control plane loads the model catalog, routing policy, and fresh probe signals.
4. The decision engine returns a durable `decision_id`, ranked candidates, and explicit rejections.
5. The Agent executes the ranked candidates with its own vendor API keys.
6. The Agent reports the execution result through `POST /v1/routing/outcomes`.
7. Probe snapshots and outcome events are available to workers for persistence and future aggregate scoring.

## Directory Structure

```text
app/
  api/
  core/
  models/
  schemas/
  services/
alembic/
examples/
.github/workflows/
models_config.json
docker-compose.yml
requirements.txt
requirements-dev.txt
```

## Quick Start

### 1. Environment Setup

Copy the template and fill in your configurations:

```bash
cp .env.example .env
```

Key Variables:
- `REDIS_URL`
- `DATABASE_URL`
- `BOOTSTRAP_AGENT_CREDENTIALS`
- `KIMI_API_KEY`
- `DEEPSEEK_API_KEY`

Example:
```env
PROJECT_NAME="LLM Agent Routing Control Plane"
REDIS_URL="redis://localhost:6379/0"
DATABASE_URL="postgresql+asyncpg://oracle_user:oracle_password@localhost:5432/oracle_db"
BOOTSTRAP_AGENT_CREDENTIALS='[{"api_key":"replace-with-a-long-random-agent-key","agent_id":"Primary-Agent","environment":"internal","status":"active","scopes":["routing:decide","routing:outcome","control:read"],"rate_limit_rpm":120,"concurrent_limit":25,"daily_budget_usd":250,"default_policy_id":"balanced"}]'
PROBE_PROXY=""
KIMI_API_KEY=""
DEEPSEEK_API_KEY=""
```

Before committing or pushing, run the repository secret check:

```bash
bash scripts/secret_scan.sh
```

### 2. Local Development

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
docker compose up -d postgres redis
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Docker Deployment

```bash
docker compose up --build -d
```

### 4. Health Check

```bash
curl http://127.0.0.1:8000/v1/control/health/live
```

## API Example

### Creating a Routing Decision

```bash
curl -X POST http://127.0.0.1:8000/v1/routing/decisions \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: replace-with-a-long-random-agent-key' \
  -H 'Idempotency-Key: demo-request-001' \
  -d '{
    "agent_id": "Primary-Agent",
    "workflow_id": "chat-demo",
    "session_id": "session-001",
    "request_id": "demo-request-001",
    "task_type": "general_chat",
    "modalities": ["text"],
    "language": "zh",
    "input_chars": 2400,
    "expected_output_tokens": 300,
    "context_window_tokens": 4096,
    "budget_limit_usd": 0.02,
    "latency_slo_ms": 1500,
    "throughput_hint_qps": 1,
    "policy_id": "balanced",
    "capability_requirements": {"json_mode": true}
  }'
```

The response payload will include:
- `decision_id`
- `recommended`
- `candidates`
- `rejections`
- `observability`

## Agent Integration

The repository provides a minimal Agent client implementation:
- `examples/agent_client.py`
- `examples/README.md`

It demonstrates:
- How to create a durable routing decision.
- How to invoke the real model using your own vendor API keys.
- How to gracefully fall back to the next ranked candidate.
- How to report final execution outcomes back to the control plane.

## Testing

```bash
pytest -q
```

Or run explicitly with development dependencies:
```bash
pip install -r requirements-dev.txt
pytest -q
```

Manual validation runbook:
- [docs/manual-test-runbook.md](./docs/manual-test-runbook.md)

## CI/CD

GitHub Actions workflows are located at:
- `.github/workflows/ci.yml`

Currently, dependencies are automatically installed and tests are executed on `push` and `pull_request` events.

## Security & Release Guidelines

- **Never** commit your real `.env` file.
- Do not hardcode production Agent Keys into code defaults.
- Rotate any vendor API keys that have been exposed in local terminals, screenshots, or commit histories prior to public release.
- Ensure `.gitignore` and `.dockerignore` are properly configured to prevent cache files, private configs, virtual environments, and logs from being packaged or uploaded.

## Known Limitations

- Outcome reports are persisted and observable, but they are not yet used for automated accuracy calibration, retraining, or weight adjustment.
- Auditing is primarily utilized for post-mortem review and observability. It does not yet form an automated optimization loop.
- The default database and Redis configurations in this repository are geared towards local development. Production environments should transition to managed services with isolated credentials.
