# LLM Agent Routing Control Plane

[English](./README.md) | [中文说明](./README_zh.md)

面向 AI Agent 的路由控制平面。它会在任务真正发起前，根据预算、任务形态、时延、并发、能力要求和探活新鲜度生成一份 durable `decision`，并返回有序 fallback 梯队，让 Agent 用自己的厂商密钥执行，再把 outcome 回写给控制面。

## 项目定位

- **控制面职责**：接收 Agent 路由请求，结合 catalog、policy 和 probe signal 产出 durable `decision_id`、候选梯队和拒绝原因
- **Agent 端职责**：拿到 `decision` 后，使用自己的厂商 API Key 发起真实模型调用；若首选模型失败则回退到下一候选，并把 outcome 回写给控制面
- **部署目标**：把“选路、降级、配额、结果回流、探活治理、观测”统一收敛为一个内部 Agent Routing Control Plane

## 创新点

- **路由与调用解耦**：服务端只负责选路，不直接代用户持有和转发厂商密钥，降低密钥集中暴露风险
- **多维度统一评分**：价格、QPS、延迟、准确率被映射到同一归一化空间，并支持请求级动态权重
- **面向真实负载的修正因子**：冷启动成本、长文本折扣、并发溢价、阶梯定价、免费额度都会进入最终决策
- **能力闭环过滤**：模型是否支持视觉、是否适配任务类别都会在候选集阶段被过滤，避免选到“能算但不能用”的模型
- **Agent 友好的失败恢复**：控制面返回稳定的有序候选名单和 `decision_id`，Agent 可以确定性回退并安全重试

## 核心技术

- **FastAPI**：对外暴露 Agent-first 控制面 API
- **Pydantic v2**：定义 decision、outcome、catalog、policy 契约
- **SQLAlchemy + Alembic**：持久化控制面记录与数据库迁移
- **Redis + Redis Streams**：承载配额、signal cache 和异步事件流
- **HTTPX**：用于 probe-worker 和 Agent 端示例调用
- **Pytest + pytest-cov**：验证决策逻辑、配额和观测原语

## 架构特点与优势

### 1. Agent 原生

- 控制面只负责决策和记录，不代理真实模型流量
- Agent 仍然自由控制 vendor SDK、重试、工具调用和编排逻辑

### 2. Durable Decision

- 每次请求都会得到一个 durable `decision_id`
- 幂等键和 outcome 回写让 Agent 可以安全重试，不会重复记账

### 3. 控制面可观测

- 每个 decision 都包含候选梯队、拒绝原因和 policy trace
- 指标覆盖 decision latency、probe freshness、候选数、拒绝原因和 outcome 成功率

### 4. 可运行治理

- 探活由独立 `probe-worker` 运行
- 事件消费由独立 `event-consumer` 负责，为后续聚合与回放做准备

## 默认策略

- `balanced`
- `cheap-first`
- `latency-first`
- `reasoning-first`
- `safe-fallback`

Agent 通过 `policy_id` 选择策略，而不是直接传一组散装权重。

## 核心流程

1. Agent 准备任务形态、预算、上下文、时延 SLO 和能力要求
2. Agent 调用 `POST /v1/routing/decisions`
3. 控制面读取 `models_config.json`、routing policy 和 Redis 中的新鲜 probe signal
4. 决策引擎生成 durable decision、候选梯队和拒绝原因
5. Agent 用自己的厂商 API Key 按顺序执行候选模型
6. 如首选模型失败，Agent 自动回退到下一候选
7. Agent 调用 `POST /v1/routing/outcomes` 回写真实 outcome

## 目录结构

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

## 快速开始

### 1. 准备环境变量

复制模板并填写配置：

```bash
cp .env.example .env
```

关键变量：

- `REDIS_URL`
- `DATABASE_URL`
- `BOOTSTRAP_AGENT_CREDENTIALS`
- `KIMI_API_KEY`
- `DEEPSEEK_API_KEY`

示例：

```env
PROJECT_NAME="LLM Agent Routing Control Plane"
REDIS_URL="redis://localhost:6379/0"
DATABASE_URL="postgresql+asyncpg://oracle_user:oracle_password@localhost:5432/oracle_db"
BOOTSTRAP_AGENT_CREDENTIALS='[{"api_key":"replace-with-a-long-random-agent-key","agent_id":"Primary-Agent","environment":"internal","status":"active","scopes":["routing:decide","routing:outcome","control:read"],"rate_limit_rpm":120,"concurrent_limit":25,"daily_budget_usd":250,"default_policy_id":"balanced"}]'
PROBE_PROXY=""
KIMI_API_KEY=""
DEEPSEEK_API_KEY=""
```

提交或推送前先运行仓库密钥检查：

```bash
bash scripts/secret_scan.sh
```

### 2. 本地运行

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
docker compose up -d postgres redis
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Docker 运行

```bash
docker compose up --build -d
```

### 4. 健康检查

```bash
curl http://127.0.0.1:8000/v1/control/health/live
```

## API 示例

### 创建路由决策

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

返回结果会包含：
- `decision_id`
- `recommended`
- `candidates`
- `rejections`
- `observability`

## Agent 集成

仓库内提供最小 Agent 客户端示例：

- [examples/agent_client.py](file:///home/ericdongz2042/projects/llm-pricing-oracle/examples/agent_client.py)
- [examples/README.md](file:///home/ericdongz2042/projects/llm-pricing-oracle/examples/README.md)

它展示了：

- 如何先向控制面请求 durable decision
- 如何使用厂商 API Key 发起真实调用
- 如何在模型超时、限流、5xx 时回退到下一名
- 如何把最终 outcome 回写给控制面

## 测试

```bash
pytest -q
```

或显式使用开发依赖：

```bash
pip install -r requirements-dev.txt
pytest -q
```

手工联调与验收 runbook：
- [docs/manual-test-runbook.md](./docs/manual-test-runbook.md)

## CI/CD

GitHub Actions 工作流位于：

- [ci.yml](file:///home/ericdongz2042/projects/llm-pricing-oracle/.github/workflows/ci.yml)

当前会在 `push` 和 `pull_request` 时自动安装依赖并运行测试。

## 安全与发布建议

- 不要提交真实 `.env`
- 不要把生产 Agent Key 写进代码默认值
- 发布前轮换任何在本地终端、截图或历史记录中暴露过的厂商 API Key
- 使用 `.gitignore` 与 `.dockerignore` 防止缓存、私密配置、虚拟环境和日志被打包或上传

## 已知边界

- outcome 回写已经持久化并可观测，但尚未用于自动准确率校准、再训练或权重调整
- 审计主要用于复盘与观测，尚未形成自动优化闭环
- 本仓库默认的数据库与 Redis 配置偏向本地开发，生产环境应改为托管服务与独立凭据
