# LLM Pricing Oracle AaaS

[English](./README.md) | [中文说明](./README_zh.md)

A routing and pricing oracle service designed for AI Agents. It evaluates budget, task scale, latency, concurrency, and capability constraints *prior* to task execution to generate an actionable `routing_cascade`. This empowers Agents to attempt model calls in a prioritized sequence and automatically fall back upon failure.

## Architecture & Responsibilities

- **Server-Side**: Receives routing requests from Agents, synthesizes pricing configs, real-time health probe data, and scoring engine metrics to output a prioritized model cascade.
- **Agent-Side**: Consumes the `routing_cascade` and executes the actual model invocation using its own vendor API keys. If the primary model fails, it seamlessly falls back to the next candidate.
- **Deployment Target**: Consolidate "price comparison, switching, degradation, auditing, and observability" into a standalone AaaS (Agent-as-a-Service) gateway.

## Key Innovations

- **Decoupled Routing & Invocation**: The server exclusively handles routing decisions. It does not proxy real chat traffic or hold user vendor keys, significantly reducing the risk of centralized key exposure.
- **Unified Multi-Dimensional Scoring**: Normalizes pricing, QPS, latency, and accuracy into a single dimensional space, supporting dynamic, per-request weight adjustments.
- **Real-World Load Correction Factors**: Integrates cold start penalties, long-context discounts, concurrency premiums, tiered pricing, and free-tier allowances into the final decision matrix.
- **Closed-Loop Capability Filtering**: Candidates are pre-filtered based on vision support and task category compatibility, avoiding the "technically capable but practically unusable" trap.
- **Agent-Friendly Failure Recovery**: The server returns a pre-sorted model cascade. Agents simply iterate through this list on failure, forming a robust and stable disaster recovery pipeline.

## Tech Stack

- **FastAPI**: Exposes the routing gateway and health checks.
- **Pydantic v2**: Defines request/response contracts, scoring weights, and baseline modeling.
- **SQLAlchemy + Alembic**: Handles audit log persistence and database migrations.
- **Redis**: Manages rate limiting, caching, and real-time latency/throughput probe data.
- **HTTPX**: Executes streaming health probes against model vendors and provides Agent-side invocation examples.
- **Pytest + pytest-cov**: Validates scoring engines and regression scenarios.

## Architectural Highlights & Advantages

### 1. Loose Coupling
- The gateway outputs decisions; it does not proxy traffic.
- Agents are free to implement their own retry, fallback, timeout, and vendor SDK logic.

### 2. Highly Extensible
- New providers can be easily added via `models_config.json`.
- The scoring engine supports request-level overrides for `score_weights` and `normalization_baseline`.

### 3. Observable
- Every routing request returns `observability` and `benchmark_report` metrics.
- The audit trail logs candidate cascades, metrics, and request context for comprehensive post-mortem analysis.

### 4. Controllable
- The default golden weights represent a "cost-first, performance-aware" strategy.
- Supports multi-layer filtering across budget, latency, capabilities, and capacity constraints.

## Current Default Golden Weights

- `token_cost`: `0.5`
- `qps`: `0.1`
- `latency`: `0.2`
- `accuracy`: `0.2`

This distribution represents a sweet spot for developers and enterprise scenarios: prioritizing cost-efficiency while maintaining strict performance and quality constraints.

## Core Workflow

1. Agent estimates the task character count, budget, context, and latency requirements.
2. Agent calls `/api/v1/route/optimize`.
3. Gateway reads `models_config.json` and real-time probe data from Redis.
4. Scoring engine generates the `routing_cascade`.
5. Agent attempts actual invocations using the cascade list and its own vendor API keys.
6. If the primary model fails, the Agent automatically falls back to the next candidate.
7. Gateway asynchronously persists an audit snapshot for future review.

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
- `AGENT_API_KEYS`
- `KIMI_API_KEY`
- `DEEPSEEK_API_KEY`

Example:
```env
PROJECT_NAME="LLM Pricing Oracle AaaS"
REDIS_URL="redis://localhost:6379/0"
DATABASE_URL="postgresql+asyncpg://oracle_user:oracle_password@localhost:5432/oracle_db"
AGENT_API_KEYS='{"replace-with-a-long-random-key":"Primary-Agent"}'
PROBE_PROXY=""
KIMI_API_KEY=""
DEEPSEEK_API_KEY=""
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
curl http://127.0.0.1:8000/health
```

## API Example

### Fetching the Routing Cascade

```bash
curl -X POST http://127.0.0.1:8000/api/v1/route/optimize \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: replace-with-a-long-random-key' \
  -d '{
    "task_category": "general_chat",
    "language": "zh",
    "payload_char_count": 2400,
    "expected_output_words": 300,
    "max_budget_usd": 0.02,
    "max_latency_ms": 1500,
    "requires_vision": false,
    "current_qps": 1
  }'
```

The response payload will include:
- `routing_cascade`
- `observability`
- `benchmark_report`

## Agent Integration

The repository provides a minimal Agent client implementation:
- `examples/agent_client.py`
- `examples/README.md`

It demonstrates:
- How to initially request the `routing_cascade` from the gateway.
- How to invoke the real model using your own vendor API keys.
- How to gracefully fall back to the next rank upon timeouts, rate limits, or 5xx errors.

## Testing

```bash
pytest -q
```

Or run explicitly with development dependencies:
```bash
pip install -r requirements-dev.txt
pytest -q
```

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

- The `accuracy` metric currently relies on static configurations and caller overrides; a real-world outcome feedback loop is not yet integrated.
- Auditing is primarily utilized for post-mortem review and observability. It does not yet form an automated re-training or weight-adjustment loop.
- The default database and Redis configurations in this repository are geared towards local development. Production environments should transition to managed services with isolated credentials.
