# LLM Pricing Oracle AaaS

[English](./README.md) | [中文说明](./README_zh.md)

面向 AI Agent 的路由与定价神谕服务。它负责在任务真正发起前，根据预算、任务规模、时延、并发与能力约束，生成一份可执行的 `routing_cascade`，让 Agent 按梯队逐个尝试模型并在失败时自动回退。

## 项目定位

- **服务端职责**：接收 Agent 的路由请求，结合价格配置、实时探活数据和评分引擎产出模型梯队
- **Agent 端职责**：拿到 `routing_cascade` 后，使用自己的厂商 API Key 发起真实模型调用；若首选模型失败则回退到下一候选
- **部署目标**：把“比价、切换、降级、审计、观测”统一收敛为一个独立的 AaaS 网关

## 创新点

- **路由与调用解耦**：服务端只负责选路，不直接代用户持有和转发厂商密钥，降低密钥集中暴露风险
- **多维度统一评分**：价格、QPS、延迟、准确率被映射到同一归一化空间，并支持请求级动态权重
- **面向真实负载的修正因子**：冷启动成本、长文本折扣、并发溢价、阶梯定价、免费额度都会进入最终决策
- **能力闭环过滤**：模型是否支持视觉、是否适配任务类别都会在候选集阶段被过滤，避免选到“能算但不能用”的模型
- **Agent 友好的失败恢复**：服务端返回排序好的模型梯队，Agent 端按名单逐个回退即可形成稳定的容灾链路

## 核心技术

- **FastAPI**：对外暴露路由网关与健康检查
- **Pydantic v2**：请求契约、响应契约、评分权重和基线建模
- **SQLAlchemy + Alembic**：审计日志持久化与数据库迁移
- **Redis**：限流、实时延迟和吞吐探活缓存
- **HTTPX**：对模型厂商进行流式探活和 Agent 端示例调用
- **Pytest + pytest-cov**：评分引擎与回归场景验证

## 架构特点与优势

### 1. 低耦合

- 网关只输出决策，不代理真实聊天流量
- Agent 可以自由选择重试、回退、超时和厂商 SDK 实现方式

### 2. 可扩展

- 新增 provider 主要通过 `models_config.json` 扩展
- 评分引擎支持请求级覆盖 `score_weights` 和 `normalization_baseline`

### 3. 可观测

- 每次路由都会返回 `observability` 和 `benchmark_report`
- 审计链路会记录候选梯队、观测指标和请求上下文，便于复盘

### 4. 可控

- 默认黄金权重偏向“成本优先但兼顾性能”
- 支持预算、延迟、能力、容量等多层过滤

## 当前默认黄金权重

- `token_cost`: `0.5`
- `qps`: `0.1`
- `latency`: `0.2`
- `accuracy`: `0.2`

这组权重更适合开发者与企业的共同场景：默认优先性价比，同时保留足够的性能与质量约束。

## 核心流程

1. Agent 估算任务字符量、预算、场景、延迟要求
2. Agent 调用 `/api/v1/route/optimize`
3. 网关读取 `models_config.json` 与 Redis 中的实时探活数据
4. 评分引擎生成 `routing_cascade`
5. Agent 拿着梯队名单和自己的厂商 API Key 逐个尝试调用
6. 如首选模型失败，Agent 自动回退到下一候选
7. 网关异步保存审计快照，支持后续复盘

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
- `AGENT_API_KEYS`
- `KIMI_API_KEY`
- `DEEPSEEK_API_KEY`

示例：

```env
PROJECT_NAME="LLM Pricing Oracle AaaS"
REDIS_URL="redis://localhost:6379/0"
DATABASE_URL="postgresql+asyncpg://oracle_user:oracle_password@localhost:5432/oracle_db"
AGENT_API_KEYS='{"replace-with-a-long-random-key":"Primary-Agent"}'
PROBE_PROXY=""
KIMI_API_KEY=""
DEEPSEEK_API_KEY=""
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
curl http://127.0.0.1:8000/health
```

## API 示例

### 获取路由梯队

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

返回结果会包含：

- `routing_cascade`
- `observability`
- `benchmark_report`

## Agent 集成

仓库内提供最小 Agent 客户端示例：

- [examples/agent_client.py](file:///home/ericdongz2042/projects/llm-pricing-oracle/examples/agent_client.py)
- [examples/README.md](file:///home/ericdongz2042/projects/llm-pricing-oracle/examples/README.md)

它展示了：

- 如何先向网关请求 `routing_cascade`
- 如何使用厂商 API Key 发起真实调用
- 如何在模型超时、限流、5xx 时回退到下一名

## 测试

```bash
pytest -q
```

或显式使用开发依赖：

```bash
pip install -r requirements-dev.txt
pytest -q
```

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

- 当前准确率维度仍以静态配置和调用方覆盖为主，尚未接入真实线上结果回写
- 审计主要用于复盘与观测，尚未形成自动再训练或自动调权闭环
- 本仓库默认的数据库与 Redis 配置偏向本地开发，生产环境应改为托管服务与独立凭据
