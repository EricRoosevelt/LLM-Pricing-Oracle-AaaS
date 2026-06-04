# Evidence Index

| Evidence | Source | Verifiable fact | Portfolio use |
| --- | --- | --- | --- |
| Product README | [README_zh.md](../../README_zh.md) | Agent-first routing control plane, control plane only decides and records, Agent uses its own vendor keys. | Product positioning, architecture boundary, target users. |
| API demo | [api-demo.md](./api-demo.md) | `POST /v1/routing/decisions`, `POST /v1/routing/outcomes`, ranked candidates, rejections, observability, duplicate outcome handling. | Demo / delivery shape and product loop. |
| Validation summary | [validation-summary.md](./validation-summary.md) | `17 passed`, `88.08%` coverage, Docker three-process integration, Redis Streams, Postgres persistence, Example Agent E2E. | Verification and credibility section. |
| Manual test report | [2026-05-15-agent-routing-control-plane-manual-runbook.json](../../docs/test-reports/2026-05-15-agent-routing-control-plane-manual-runbook.json) | Ready checks online, 2 providers, 4 models, 5 policies, outcome duplicate fix verified, worker integration verified, Example Agent selected `deepseek/deepseek-chat`. | Evidence details and appendix. |
| Architecture source | [product-architecture.mmd](./product-architecture.mmd) and [architecture.svg](./assets/architecture.svg) | Control plane API, decision service, scoring engine, probe worker, event consumer, Redis, Postgres, providers, metrics. | Architecture diagram backup. |
| Product flow source | [product-flow.mmd](./product-flow.mmd) | Decision request, explainable decision, Agent-owned provider invocation, outcome feedback, audit and metrics loop. | Product solution and FigJam redraw. |
| FigJam redraw | https://www.figma.com/board/1rKE9qZT13SDmzwoBudhxf | Editable product-loop and control-plane architecture diagrams generated from the local Mermaid sources. | Notion final page visual asset and manual rearrangement source. |
| Notion final page | https://app.notion.com/p/3751cb002005813b8b86fe11cf67983b | Final page created under the portfolio parent page using the unified framework. | Published Notion portfolio draft. |
| Existing Notion short page | https://app.notion.com/p/3611cb002005811fa96cf1fbf982c603 | Prior short portfolio page with product summary and proof points. | Source to consolidate, not final. |
| Existing Notion long page | https://app.notion.com/p/3611cb002005817fb022e64899e51605 | Prior detailed page with long API snippets and validation material. | Source to consolidate, not final. |
| GitHub repository | https://github.com/EricRoosevelt/LLM-Pricing-Oracle-AaaS | Public code and documentation home. | External link / appendix. |

## Claims Not Used

The final portfolio must not claim downloads, active users, revenue, retention, conversion, market share, enterprise usage, or user satisfaction until separate evidence is collected.
