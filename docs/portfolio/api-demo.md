# API Demo 素材

这份文档用于 Notion 中的 Demo 模块。所有请求均已脱敏，示例 key 使用占位控制面 key。

## 1. 创建 Routing Decision

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

## 2. Decision Response 摘要

```json
{
  "decision_id": "768aebe7db6348238284c175e79c9bc9",
  "catalog_version": "2026-04-23-v1",
  "policy_id": "balanced",
  "policy_version": "2026.04.v1",
  "recommended": {
    "rank": 1,
    "model_id": "deepseek/deepseek-chat",
    "provider": "deepseek",
    "estimated_cost_usd": 0.000319,
    "expected_ttfb_ms": 639,
    "confidence_score": 0.6602
  },
  "candidates": [
    {"rank": 1, "model_id": "deepseek/deepseek-chat"},
    {"rank": 2, "model_id": "deepseek/deepseek-reasoner"}
  ],
  "rejections": [
    {
      "model_id": "moonshot/moonshot-v1-8k",
      "reason": "latency_filtered",
      "detail": "expected_ttfb_ms=4236 exceeds latency_slo_ms=1500"
    },
    {
      "model_id": "moonshot/moonshot-v1-32k",
      "reason": "latency_filtered",
      "detail": "expected_ttfb_ms=5034 exceeds latency_slo_ms=1500"
    }
  ],
  "observability": {
    "decision_compute_ms": 0.226,
    "evaluated_models": 4,
    "candidate_count": 2,
    "filtered_by_latency": 2,
    "fallback_safety_score": 0.6272,
    "policy_trace": [
      "catalog=2026-04-23-v1 checksum=e42d479166e5",
      "policy=balanced@2026.04.v1",
      "top_candidate=deepseek/deepseek-chat",
      "fallback_depth=1"
    ]
  }
}
```

适合在 Notion 中强调的字段：

- `recommended.model_id`：本次推荐的首选模型。
- `candidates`：如果首选失败，Agent 可以按 rank 继续 fallback。
- `rejections`：被过滤模型不是黑盒消失，而是有可解释原因。
- `observability.policy_trace`：方便排查一次 decision 是基于什么 catalog 和 policy 产生的。

## 3. 回写 Outcome

```bash
curl -X POST http://127.0.0.1:8000/v1/routing/outcomes \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: replace-with-a-long-random-agent-key' \
  -H 'Idempotency-Key: outcome-demo-001' \
  -d '{
    "decision_id": "768aebe7db6348238284c175e79c9bc9",
    "agent_id": "Primary-Agent",
    "request_id": "demo-request-001",
    "final_status": "success",
    "attempts": [
      {
        "model_id": "deepseek/deepseek-chat",
        "provider": "deepseek",
        "rank": 1,
        "status": "success",
        "error_class": null,
        "latency_ms": 639,
        "input_tokens": 1200,
        "output_tokens": 300,
        "cost_usd": 0.000319
      }
    ],
    "final_model_id": "deepseek/deepseek-chat",
    "fallback_depth": 0,
    "end_to_end_latency_ms": 639,
    "final_cost_usd": 0.000319,
    "user_feedback": "success"
  }'
```

首次回写：

```json
{
  "decision_id": "768aebe7db6348238284c175e79c9bc9",
  "outcome_status": "recorded",
  "final_status": "success",
  "attempts_recorded": 1,
  "fallback_depth": 0
}
```

重复回写：

```json
{
  "decision_id": "97ad9c0c49974e409c175ba8e8cd9c86",
  "outcome_status": "duplicate",
  "final_status": "success",
  "attempts_recorded": 1,
  "fallback_depth": 0
}
```

## 4. Example Agent E2E

```bash
set -a
source .env
set +a
export ORACLE_BASE_URL=http://127.0.0.1:8000
export ORACLE_API_KEY=replace-with-your-control-plane-key
export AGENT_ID=Primary-Agent
./venv/bin/python examples/agent_client.py
```

实际验收结果：

```text
decision_id: 07a0b9527aa5459d84e95cb73c8221d7
selected_model: deepseek/deepseek-chat
```

## 5. Demo 讲解词

这段 Demo 展示的是一次完整的 Agent 调用前决策。Agent 先把任务约束交给控制面，控制面根据模型目录、策略权重和实时 signal 返回一个可追踪的 `decision_id`，同时给出首选模型和 fallback 梯队。Agent 不需要把厂商 key 交给控制面，而是自己调用模型。调用结束后，Agent 把 outcome 回写给控制面，系统就能记录这次推荐是否真正成功，并为后续预算统计、稳定性分析和策略调优提供数据。
