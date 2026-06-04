# LLM Agent Routing Control Plane｜面向 AI Agent 的模型路由控制面

> 一句话说明：这个产品面向构建 AI Agent、workflow 和企业内部 AI 工具的开发者团队，在真实调用大模型前返回可解释的模型推荐、fallback 梯队和结果回写闭环，降低硬编码模型带来的成本、延迟、稳定性和治理风险。

## 1. 30 秒摘要

| 维度 | 内容 |
| --- | --- |
| 项目类型 | AI 基础设施产品 / Developer Tool |
| 目标用户 | 构建 AI Agent、workflow、企业内部 AI 工具的开发者、平台团队和 AI 应用产品团队 |
| 我的角色 | 产品定义、用户场景拆解、API 契约设计、系统方案设计、后端实现、测试验收、Demo 打磨、作品集整理 |
| 核心价值 | 把“选哪个模型、失败怎么降级、结果怎么回流”从业务代码中抽象成可解释、可追踪、可验证的 routing control plane |
| 当前阶段 | 可运行 MVP / 作品集终稿整理阶段 |
| 关键结果 | `17 passed`、`88.08% coverage`、5 个 active routing policies、4 个模型、Docker 三进程联动、Redis Streams、Postgres 落库、Example Agent E2E 均已验证 |

## 2. 为什么值得做

当前 Agent 开发者通常会把模型选择直接写在业务代码或配置文件里：某个任务默认用一个模型，失败时临时写重试逻辑，价格、延迟、能力和 provider 健康状态分散在不同地方判断。

问题 1：成本和延迟不可治理。不同模型的输入/输出价格、上下文窗口、延迟和并发能力不同，如果每个 Agent 自己做选择，团队很难统一预算和 SLO。

问题 2：失败恢复不稳定。Provider 可能限流、超时或返回 5xx；没有稳定 fallback ladder 时，Agent 只能依赖临时重试或人工修配置。

问题 3：能力边界不透明。模型是否支持 JSON mode、reasoning、tool calling、视觉或特定任务类型，需要在调用前过滤，否则可能选到“便宜但不能用”的模型。

问题 4：缺少结果回流。没有 outcome report，就无法知道推荐模型是否真的成功、省钱、低延迟，也无法复盘策略是否需要调整。

产品机会：把模型选择做成一个 Agent-first control plane。控制面不接管真实模型调用，而是在调用前给出可解释 decision；Agent 仍使用自己的 vendor key 执行；调用完成后回写 outcome，形成决策、执行、观测和复盘闭环。

## 3. 目标用户与核心场景

### 目标用户

- Agent 应用开发者：需要在不同任务、预算和延迟约束下选择合适模型。
- AI 平台 / Infra 团队：需要统一治理多个 Agent 的模型目录、策略、配额和观测字段。
- 内部 AI 工具产品团队：需要把模型选择从“写死配置”升级为可解释、可审计、可复盘的产品能力。

### 核心场景

1. 调用前决策：Agent 提交任务类型、预算、上下文长度、延迟 SLO 和能力要求，控制面返回推荐模型与候选梯队。
2. 失败降级：首选 provider 失败时，Agent 按控制面返回的 candidates 顺序 fallback。
3. 策略解释：团队可以看到 rejected models 和 rejection reasons，知道为什么某些模型被过滤。
4. Outcome 回写：Agent 把最终模型、延迟、token、成本、状态和 fallback 深度回写，供审计、metrics 和后续策略优化使用。

### 用户成功标准

- Agent 能在真实模型调用前拿到可解释 decision。
- Agent 不需要把 vendor key 交给控制面。
- 失败时有稳定 fallback 路径，而不是临时重试。
- 每次推荐和执行结果都能被追踪、审计和复盘。

## 4. 产品方案

核心闭环：

```text
任务约束 -> 路由决策 -> Agent 自主调用 -> fallback 执行 -> outcome 回写 -> 审计/指标/策略复盘
```

关键模块：

| 模块 | 解决的问题 | 用户可见价值 |
| --- | --- | --- |
| Decision API | Agent 调用前不知道该选哪个模型 | 返回推荐模型、候选梯队、过滤原因和 observability 字段 |
| Model Catalog | 模型价格、能力、上下文窗口和 provider 元数据分散 | 统一模型目录，支持可追溯 catalog version |
| Routing Policies | 裸权重难理解、难运营 | 用 `balanced`、`cheap-first`、`latency-first` 等命名策略承载产品意图 |
| Scoring Engine | 成本、延迟、能力、健康信号无法统一比较 | 将多维度约束转成可排序候选集 |
| Redis Signals / Probe Worker | Provider 健康状态会随时间变化 | 路由决策可以读取 fresh signals，而不是只依赖静态配置 |
| Durable Decision / Outcome | 推荐和执行结果断裂 | 通过 `decision_id` 连接决策、执行、fallback 和结果回写 |
| Metrics / Persistence | 面试或团队评估时缺少可信证据 | 可以展示测试、落库、事件流和 E2E 验收结果 |

架构图备份：

- 产品闭环 Mermaid：[product-flow.mmd](./product-flow.mmd)
- 控制面架构 Mermaid：[product-architecture.mmd](./product-architecture.mmd)
- 静态架构 SVG：[assets/architecture.svg](./assets/architecture.svg)
- FigJam 可编辑图：https://www.figma.com/board/1rKE9qZT13SDmzwoBudhxf

## 5. 关键产品取舍

| 取舍 | 决策 | 理由 |
| --- | --- | --- |
| 范围取舍 | 先做路由控制面，不做完整 dashboard | 目标用户是开发者和 Agent 团队，API 是最短集成路径；dashboard 可在策略治理和报表阶段再做 |
| 架构取舍 | 做“导航系统”，不做代理网关 | 控制面只给推荐和 fallback，不集中持有 vendor key，降低密钥暴露和调用链耦合风险 |
| 用户体验取舍 | API 返回 candidates、rejections、observability，而不是只返回一个 model_id | 让开发者能调试、解释和复盘一次 decision，降低黑盒感 |
| 隐私/权限取舍 | Agent 使用自己的 vendor key 调用 provider | 保留 Agent 对 SDK、工具调用、重试和业务编排的控制权 |
| 验证取舍 | 先验证核心链路、幂等、事件流、落库和 E2E，不编造业务增长指标 | 作品集可以证明 MVP 可运行、可追踪、可复盘；真实用户和业务结果放入待补采样 |

## 6. Demo / 交付形态

| 能力 | 交付物 | 面试官可观察点 |
| --- | --- | --- |
| 创建 routing decision | `POST /v1/routing/decisions`，详见 [api-demo.md](./api-demo.md) | Agent 在调用前拿到 `decision_id`、`recommended`、`candidates`、`rejections`、`observability` |
| 结果回写与幂等 | `POST /v1/routing/outcomes` | 首次 outcome 返回 `recorded`，重复回写返回 `duplicate` |
| Example Agent E2E | [examples/agent_client.py](../../examples/agent_client.py) | 完成 decision -> provider invoke -> outcome report，选中 `deepseek/deepseek-chat` |
| 控制面可观测 | Prometheus metrics、Redis Streams、Postgres | decision、outcome、rejection、worker event 都可被检查 |
| 作品集图像 | FigJam 可编辑图 + Mermaid / SVG 备份 | 架构可重排，静态图可用于 Notion 展示 |

## 7. 验证与证据

| 验证项 | 结果 | 证据 |
| --- | --- | --- |
| 自动化测试 | `17 passed` | [validation-summary.md](./validation-summary.md) |
| 覆盖率 | `88.08%`，超过 `85%` 门槛 | [validation-summary.md](./validation-summary.md) |
| Control Plane API | health、catalog、policies、decision、outcome 通过 | [manual test report](../../docs/test-reports/2026-05-15-agent-routing-control-plane-manual-runbook.json) |
| 模型与策略 | 2 个 provider、4 个 model、5 个 active policy | [manual test report](../../docs/test-reports/2026-05-15-agent-routing-control-plane-manual-runbook.json) |
| Outcome 幂等 | 初次 `recorded`，重复 `duplicate`，修复后复测通过 | [manual test report](../../docs/test-reports/2026-05-15-agent-routing-control-plane-manual-runbook.json) |
| Worker 联动 | decision-api / probe-worker / event-consumer 三进程联动通过 | [manual test report](../../docs/test-reports/2026-05-15-agent-routing-control-plane-manual-runbook.json) |
| Redis / Postgres | Redis Streams 有事件，Postgres decision/outcome 成功落库 | [manual test report](../../docs/test-reports/2026-05-15-agent-routing-control-plane-manual-runbook.json) |
| Example Agent E2E | 成功选中 `deepseek/deepseek-chat` 并完成端到端调用 | [manual test report](../../docs/test-reports/2026-05-15-agent-routing-control-plane-manual-runbook.json) |

这些证据验证的是产品风险，而不只是工程指标：Agent 能否拿到可解释 decision，fallback 是否可执行，结果是否可追踪，控制面是否能在真实 Redis / Postgres / worker 环境中形成闭环。

## 8. 复盘与下一步

### 做对的事

- 把产品边界定义为 Agent-first control plane，避免一开始陷入代理网关和密钥托管。
- 把 fallback、rejections、policy trace 和 observability 放进 API 契约，让开发者能解释和调试。
- 用 outcome 回写把“推荐模型”与“真实执行结果”连接起来。
- 用自动化测试、手工 runbook、Redis / Postgres / worker 联动和 Example Agent E2E 做可信证据。

### 当前边界

- 还没有完整 dashboard，策略配置主要通过 API / 配置理解。
- outcome 已能回写和持久化，但尚未用于自动调权或策略学习。
- 缺少 shadow mode、route replay 和策略对比实验。
- 缺少真实用户访谈、可用性测试、竞品实机截图和真实业务使用数据。

### 下一步路线图

| 阶段 | 目标 |
| --- | --- |
| v1.1 | 模型 registry 热更新、策略配置治理、route outcome 聚合、生产化 readiness |
| v1.2 | shadow mode、route replay、策略对比实验、provider adapter 抽象 |
| v1.3 | 成本报表、团队/租户视图、管理 dashboard、商业化配额与权限 |

## 9. 面试讲述版本

### 30 秒版

我把这个项目定位成面向 AI Agent 的模型路由控制面。Agent 在调用大模型前提交任务约束，控制面根据预算、延迟、能力、健康信号和策略返回可解释的推荐模型与 fallback 梯队；Agent 用自己的 vendor key 调用模型，完成后把 outcome 回写。这样既避免硬编码模型带来的成本和稳定性风险，也不会让控制面集中持有用户密钥。

### 2 分钟版

这个项目解决的是 Agent 团队在多模型环境下的路由治理问题。现实里不同模型价格、延迟、能力和可用性不同，如果每个 Agent 都把模型写死在代码里，成本、失败降级和复盘都会很难治理。

我的方案不是做一个代理网关，而是做 Agent-first control plane：控制面只负责调用前决策和结果记录，不代理真实模型流量。Agent 先提交任务类型、预算、上下文、延迟 SLO 和能力要求，控制面读取 model catalog、routing policy 和 Redis probe signals，返回 durable `decision_id`、首选模型、候选梯队、过滤原因和观测字段。Agent 自己调用 provider，失败时按候选梯队 fallback，最后回写 outcome。

这个 MVP 已经通过自动化测试和手工联调验证：`17 passed`、`88.08% coverage`，Docker 三进程、Redis Streams、Postgres 落库和 Example Agent E2E 都跑通。下一步我会把它推进到策略治理、route replay、shadow mode 和成本报表，让它从可运行 MVP 变成更可运营的 routing product。

### 面试官可追问点

| 追问方向 | 可展开内容 |
| --- | --- |
| 产品能力 | 用户是谁、为什么模型硬编码值得产品化、MVP 边界为什么先做 API |
| 技术沟通 | Agent-first 架构、durable decision、fallback ladder、幂等、Redis signal、Postgres 落库 |
| 取舍判断 | 为什么不做代理网关、为什么不先做 dashboard、为什么 outcome 回写是闭环关键 |
| 验证方式 | 自动化测试、覆盖率、手工 runbook、worker 联动、Example Agent E2E |
| 路线图 | registry 热更新、策略治理、shadow mode、route replay、成本报表 |

## 10. 外部链接 / 附录

- GitHub 仓库：https://github.com/EricRoosevelt/LLM-Pricing-Oracle-AaaS
- FigJam 可编辑架构图：https://www.figma.com/board/1rKE9qZT13SDmzwoBudhxf
- Notion 终稿页：https://app.notion.com/p/3751cb002005813b8b86fe11cf67983b
- 证据索引：[evidence-index.md](./evidence-index.md)
- 待补采样清单：[sampling-checklist.md](./sampling-checklist.md)
- API Demo 详情：[api-demo.md](./api-demo.md)
- 测试与验收摘要：[validation-summary.md](./validation-summary.md)
- 手工验收报告：[2026-05-15-agent-routing-control-plane-manual-runbook.json](../../docs/test-reports/2026-05-15-agent-routing-control-plane-manual-runbook.json)
- 旧 Notion 短页：https://app.notion.com/p/3611cb002005811fa96cf1fbf982c603
- 旧 Notion 长页：https://app.notion.com/p/3611cb002005817fb022e64899e51605

## 待补采样清单

完整清单见 [sampling-checklist.md](./sampling-checklist.md)。当前最重要的待补证据是目标开发者访谈、竞品截图、Demo 录屏、可用性测试和真实使用数据。在这些证据补齐前，作品页不写下载量、活跃用户、收入、留存率、转化率、用户满意度或“已上线”等未验证结论。
