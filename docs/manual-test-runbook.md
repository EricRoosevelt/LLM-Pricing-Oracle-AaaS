# LLM Agent Routing Control Plane Manual Test Runbook

## 1. 目的

这份 runbook 用来做两件事：

1. 记录当前仓库里我已经替你完成的自动化验证
2. 给你一套可以亲手照着执行的人工测试步骤，覆盖真实 HTTP、真实依赖、worker 联动、signal freshness、Redis Streams、数据库落库和示例 Agent 端到端链路

它默认面向当前的 **Agent-first control plane** 实现：

- `POST /v1/routing/decisions`
- `POST /v1/routing/outcomes`
- `GET /v1/control/health/live`
- `GET /v1/control/health/ready`
- `GET /v1/control/catalog`
- `GET /v1/control/policies`

## 2. 我已经替你完成的验证

### 2.1 自动化测试

我已在当前仓库执行：

```bash
./venv/bin/pytest -q
```

结果：

- `15 passed`
- 覆盖率 `88.18%`

已覆盖的能力：

- 决策排序与能力过滤
- decision 幂等
- outcome 回写与 duplicate 处理
- 日预算守卫
- readiness 对 fresh signal 的判断
- metrics 渲染
- signal store 与 probe smoothing
- token estimator 基线

### 2.2 当前环境限制

我已确认当前 Codex 运行环境里：

- `docker` 在这个 WSL 环境中不可用
- 因此我**无法继续替你执行** `docker compose` 级别的三进程联调

这意味着以下部分必须由你手工完成：

- Postgres/Redis/Redis Streams 的真实联通
- `decision-api / probe-worker / event-consumer` 联动
- 真实 provider key 驱动的 probe 和 `ready` 变更
- 示例 Agent 的真实端到端调用

## 3. 测试前准备

### 3.1 环境变量

先复制模板：

```bash
cp .env.example .env
```

至少确认这些字段：

- `REDIS_URL`
- `DATABASE_URL`
- `CATALOG_PATH`
- `BOOTSTRAP_AGENT_CREDENTIALS`
- `KIMI_API_KEY`
- `DEEPSEEK_API_KEY`

关键检查：

- `BOOTSTRAP_AGENT_CREDENTIALS` 至少有一条可用 credential
- 这条 credential 的 `agent_id` 与你要发请求时的 `agent_id` 一致
- `scopes` 至少包含：
  - `routing:decide`
  - `routing:outcome`
  - `control:read`

### 3.2 最低配置

当前默认文档里的最低本地开发凭证是：

- API key: `replace-with-a-long-random-agent-key`
- agent\_id: `Primary-Agent`

如果你保持模板不改，下面的 curl 可以直接照抄。

## 4. 启动方式

### 4.1 只测 API

如果你先只想验证 API 契约和数据库/Redis 基础连通性：

```bash
./venv/bin/alembic upgrade head
./venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 4.2 测完整三进程

如果你的机器有 Docker：

```bash
docker compose up -d postgres redis
docker compose up --build -d
```

这会启动：

- `decision-api`
- `probe-worker`
- `event-consumer`

## 5. 基础健康检查

### 5.1 Live

```bash
curl http://127.0.0.1:8000/v1/control/health/live
```

期望：

- HTTP `200`
- `status = "online"`

### 5.2 Ready

```bash
curl http://127.0.0.1:8000/v1/control/health/ready
```

重点看 `details`：

- `database`
- `redis`
- `catalog_loaded`
- `fresh_signals`

期望分两种：

1. **未配置 provider key 或 probe 还没写出 signal**
   - `status` 很可能是 `degraded`
   - `fresh_signals = false`
2. **probe-worker 已运行且成功写入 signal**
   - `status = online`
   - `fresh_signals = true`

## 6. 控制面只读接口

### 6.1 未认证访问 catalog

```bash
curl http://127.0.0.1:8000/v1/control/catalog
```

期望：

- HTTP `401`

### 6.2 已认证访问 catalog

```bash
curl http://127.0.0.1:8000/v1/control/catalog \
  -H 'X-API-Key: replace-with-a-long-random-agent-key'
```

期望：

- HTTP `200`
- 返回 `catalog_version`
- 返回 `providers`
- 返回 `models`

### 6.3 已认证访问 policies

```bash
curl http://127.0.0.1:8000/v1/control/policies \
  -H 'X-API-Key: replace-with-a-long-random-agent-key'
```

期望至少包含这些策略：

- `balanced`
- `cheap-first`
- `latency-first`
- `reasoning-first`
- `safe-fallback`

## 7. Decision API 主链路

### 7.1 创建 decision

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

期望：

- HTTP `200`
- 存在：
  - `decision_id`
  - `catalog_version`
  - `policy_id`
  - `policy_version`
  - `recommended`
  - `candidates`
  - `rejections`
  - `decision_explanation`
  - `observability`

人工核对：

- `recommended.model_id == candidates[0].model_id`
- `candidates[].rank` 从 `1` 开始连续递增
- `expires_at` 存在
- `observability.candidate_count >= 1`

### 7.2 decision 幂等

把**同一个**请求体再发一次，并保持：

- `Idempotency-Key` 不变

期望：

- HTTP `200`
- 返回的 `decision_id` 与第一次**完全一致**

## 8. Decision 失败路径

### 8.1 agent\_id 不匹配

把请求体里的 `agent_id` 改成别的值，继续使用同一个 API key。

期望：

- HTTP `403`

### 8.2 policy\_id 不存在

把 `policy_id` 改成不存在值，例如：

```json
"policy_id": "not-exists-policy"
```

期望：

- HTTP `404`

### 8.3 能力过滤导致无候选

当前 catalog 里大概率无法在所有环境下返回满足 `vision=true` 的可用候选，可以用这个方式测失败路径：

```json
"capability_requirements": {"vision": true}
```

期望：

- HTTP `400`
- 错误信息类似“没有模型通过过滤”

### 8.4 provider allow/deny

两组都测：

```json
"provider_allowlist": ["deepseek"]
```

```json
"provider_denylist": ["deepseek"]
```

期望：

- allowlist 时只看到允许 provider 的候选
- denylist 时，被排除的 provider 会出现在 `rejections`

## 9. Outcome API 主链路

### 9.1 成功 outcome

先拿到上一步的 `decision_id` 和 `recommended` 候选，再回写：

```bash
curl -X POST http://127.0.0.1:8000/v1/routing/outcomes \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: replace-with-a-long-random-agent-key' \
  -H 'Idempotency-Key: outcome-demo-001' \
  -d '{
    "decision_id": "替换成真实 decision_id",
    "agent_id": "Primary-Agent",
    "request_id": "demo-request-001",
    "final_status": "success",
    "attempts": [
      {
        "model_id": "替换成真实 model_id",
        "provider": "替换成真实 provider",
        "rank": 1,
        "status": "success",
        "error_class": null,
        "latency_ms": 500,
        "input_tokens": 800,
        "output_tokens": 300,
        "cost_usd": 0.01
      }
    ],
    "final_model_id": "替换成真实 model_id",
    "fallback_depth": 0,
    "end_to_end_latency_ms": 500,
    "final_cost_usd": 0.01,
    "user_feedback": "success"
  }'
```

期望：

- HTTP `200`
- 返回：
  - `decision_id`
  - `outcome_status = "recorded"`
  - `final_status = "success"`
  - `attempts_recorded = 1`

### 9.2 outcome 幂等

保持同一个 `Idempotency-Key` 再发一次。

期望：

- HTTP `200`
- `outcome_status = "duplicate"`

### 9.3 outcome 异常路径

分别验证：

1. `decision_id` 乱填
   - 期望 `404`
2. `request_id` 与原始 decision 的 `request_id` 不一致
   - 期望 `403`
3. `agent_id` 与当前 credential 不一致
   - 期望 `403`

## 10. Metrics 检查

在 decision/outcome 跑完后拉一次：

```bash
curl http://127.0.0.1:8000/metrics
```

至少检查这些指标存在并增长：

- `http_requests_total`
- `routing_decisions_total`
- `routing_decision_latency_ms_count`
- `routing_candidate_count_count`
- `routing_policy_hits_total`
- `routing_outcomes_total`
- `routing_fallback_depth_count`
- `routing_probe_freshness_seconds`

## 11. Redis 与数据库落地检查

这部分非常重要，它能验证控制面不是只“返回对了”，而是真的把状态保存了。

### 11.1 Redis Streams

如果本机有 `redis-cli`，执行：

```bash
redis-cli XRANGE routing-outcomes - + COUNT 5
redis-cli XRANGE routing-probes - + COUNT 5
```

期望：

- outcome 回写后，`routing-outcomes` 有事件
- probe-worker 跑起来后，`routing-probes` 有事件

### 11.2 Postgres

如果本机有 `psql`，执行：

```bash
psql "$DATABASE_URL" -c "select decision_id, agent_id, status, final_status, created_at from routing_decisions order by created_at desc limit 10;"
psql "$DATABASE_URL" -c "select decision_id, model_id, rank, status, created_at from routing_attempts order by created_at desc limit 10;"
psql "$DATABASE_URL" -c "select model_id, status, captured_at from probe_snapshots order by captured_at desc limit 10;"
```

期望：

- `routing_decisions` 能看到刚才创建的 `decision_id`
- `routing_attempts` 能看到 outcome 回写后的 attempt
- `probe_snapshots` 在 probe-worker 跑起来后有记录

## 12. Worker 联动检查

### 12.1 不配置 provider key

直接起全套服务，但不填：

- `KIMI_API_KEY`
- `DEEPSEEK_API_KEY`

期望：

- `probe-worker` 会打印 warning 或 skip 信息
- `ready` 可能持续 `degraded`
- `fresh_signals = false`

这是**正常行为**

### 12.2 配置 provider key

填至少一个 provider key 后再起：

```bash
docker compose up -d decision-api probe-worker event-consumer
```

然后观察：

```bash
docker logs -f oracle_probe_worker
docker logs -f oracle_event_consumer
```

期望：

- probe-worker 周期性跑探活
- Redis 中出现 probe signal
- `ready` 从 `degraded` 变成 `online`
- event-consumer 能消费 probe stream

## 13. Example Agent 端到端链路

这是最接近真实 Agent 的验收，但会触发真实 provider 调用，可能产生费用。

先准备：

- `ORACLE_BASE_URL`
- `ORACLE_API_KEY`
- `AGENT_ID`
- `DEEPSEEK_API_KEY`
- `KIMI_API_KEY`

然后运行：

```bash
cd examples
../venv/bin/python agent_client.py
```

期望：

- 输出 `decision_id`
- 输出 `selected_model`
- 能完整走通：
  - `decision`
  - provider invoke
  - `outcome` 回写

如果 provider 失败：

- 应看到 fallback 日志
- 最终仍应有 outcome 回写

## 14. 测试记录模板

建议每个场景都记录：

- 测试时间
- 请求命令
- HTTP status code
- 关键响应字段
- `/metrics` 是否增长
- `decision-api` 日志
- `probe-worker` 日志
- `event-consumer` 日志
- Redis stream 是否有事件
- Postgres 是否有新记录

你可以直接用下面这个模板：

```text
[Case]
时间:
命令:
期望:
实际 HTTP:
关键字段:
metrics:
redis:
postgres:
日志:
结论:
```

## 15. 快速判障

如果失败，优先按下面归类：

- `401/403/404`
  - 看 credential、scope、agent\_id、request\_id、policy\_id 是否匹配
- `400`
  - 看请求体 schema、budget、latency、capability 过滤后是否无候选
- `ready = degraded`
  - 先看 `details`
  - 大多数情况是 `fresh_signals = false`
  - 优先排查 `probe-worker`
- outcome 没落库
  - 先看 `routing-outcomes` stream
  - 再看 `event-consumer` 日志
- probe 不生效
  - 先看 provider key 是否真的注入
  - 再看 `routing-probes` stream 和 `probe_snapshots`

## 16. 建议执行顺序

为了最快定位问题，建议你按这个顺序走：

1. `pytest -q`
2. `live` / `ready`
3. `catalog` / `policies`
4. `decision`
5. decision 幂等
6. outcome
7. outcome 幂等
8. metrics
9. Redis/Postgres 落地检查
10. probe-worker 联动
11. 示例 Agent 端到端

## 17. 假设

- 这份 runbook 基于当前仓库实现，不依赖 UI 或额外 CLI。
- 默认使用 `.env.example` 中的占位控制面 key / `Primary-Agent`。
- 如果你不提供真实 provider key，probe 和端到端 invoke 场景只验证负路径或 degraded 状态，这是预期行为。
- 旧的 `/api/v1/route/optimize` 不再属于测试范围，本 runbook 全部基于新的 `/v1/*` 控制面接口。
