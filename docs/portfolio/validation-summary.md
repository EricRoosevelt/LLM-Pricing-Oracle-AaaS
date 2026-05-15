# 测试与验收摘要

数据来源：

- 自动化测试：本地执行 `./venv/bin/pytest -q`
- 手工验收：[2026-05-15-agent-routing-control-plane-manual-runbook.json](../test-reports/2026-05-15-agent-routing-control-plane-manual-runbook.json)

## 自动化测试

| 项目 | 结果 |
| --- | --- |
| 命令 | `./venv/bin/pytest -q` |
| 测试结果 | `17 passed` |
| 覆盖率 | `88.08%` |
| 覆盖率门槛 | `85%` |
| 结论 | 通过 |

覆盖能力：

- 决策排序与能力过滤
- decision 幂等
- outcome 回写与 duplicate 处理
- 日预算守卫
- readiness 对 fresh signal 的判断
- metrics 渲染
- signal store 与 probe smoothing
- token estimator 基线

## 手工验收

| 模块 | 结果 | 说明 |
| --- | --- | --- |
| Health checks | 通过 | live/ready 均 online，database、redis、catalog、fresh signals 正常 |
| Catalog / Policies | 通过 | 2 个 provider、4 个 model、5 个 active policies |
| Decision API | 通过 | 返回 `recommended`、`candidates`、`rejections`、`observability` |
| Decision 幂等 | 通过 | 同一 Idempotency-Key 返回同一 `decision_id` |
| Outcome API | 通过 | 首次 `recorded`，重复回写 `duplicate` |
| Metrics | 通过 | Prometheus 指标包含 routing decisions、outcomes、rejections |
| Redis Streams | 通过 | `routing-outcomes`、`routing-probes` 有事件 |
| Postgres | 通过 | decision、attempt、probe snapshot 成功落库 |
| Worker 联动 | 通过 | decision-api / probe-worker / event-consumer 三进程联动正常 |
| Example Agent E2E | 通过 | 选中 `deepseek/deepseek-chat` 完成端到端调用 |

## 可放入 Notion 的可信度结论

这个项目已经完成从单元测试到手工联调的闭环验证：自动化测试 `17 passed`，覆盖率 `88.08%`，并通过真实 Docker 三进程联动、Redis Streams、Postgres 落库、Prometheus metrics 和 Example Agent E2E 验收。因此它不是静态概念页，而是一个可运行、可验证、可复盘的 AI Agent 路由控制面 MVP。
