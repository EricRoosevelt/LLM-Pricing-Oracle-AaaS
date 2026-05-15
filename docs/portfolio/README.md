# Portfolio Material Pack

这个目录是 `LLM Agent Routing Control Plane` 的作品集物料包，定位为面向产品相关岗位的 Notion 一页式深度案例。

## 文件说明

| 文件 | 用途 |
| --- | --- |
| [notion-case-study.md](./notion-case-study.md) | 可直接粘贴到 Notion 的主页面文案 |
| [architecture.mmd](./architecture.mmd) | 架构图 Mermaid 源文件 |
| [assets/architecture.svg](./assets/architecture.svg) | 现代架构图可编辑 SVG 源文件 |
| [api-demo.md](./api-demo.md) | API Demo 请求、响应和讲解词 |
| [validation-summary.md](./validation-summary.md) | 自动化测试与手工验收摘要 |
| [production-checklist.md](./production-checklist.md) | Notion 制作与脱敏检查清单 |
| [scripts/render_portfolio_assets.py](./scripts/render_portfolio_assets.py) | PNG/SVG 资产生成脚本，使用 Pillow 渲染现代字体 |

## PNG 资产

| 图片 | 用途 |
| --- | --- |
| [assets/portfolio-cover.png](./assets/portfolio-cover.png) | Notion 封面或项目头图 |
| [assets/architecture.png](./assets/architecture.png) | 架构图 PNG |
| [assets/architecture.svg](./assets/architecture.svg) | 架构图 SVG，可在 Figma、Canva 或浏览器中继续编辑/导出 |
| [assets/api-demo-card.png](./assets/api-demo-card.png) | API Demo 流程卡片 |
| [assets/test-results-card.png](./assets/test-results-card.png) | 测试结果卡片 |
| [assets/validation-summary-card.png](./assets/validation-summary-card.png) | 验收摘要卡片 |
| [assets/product-cards.png](./assets/product-cards.png) | 产品说明卡片 |
| [assets/technical-highlights-card.png](./assets/technical-highlights-card.png) | 技术亮点卡片 |

## 重新生成图片

```bash
./venv/bin/python docs/portfolio/scripts/render_portfolio_assets.py
```

如果本地环境缺少 Pillow，先安装开发依赖：

```bash
./venv/bin/python -m pip install -r requirements-dev.txt
```

## 当前实测结论

- 自动化测试：`17 passed`
- 覆盖率：`88.08%`
- 手工验收：Docker 三进程联动、Redis Streams、Postgres 落库、worker integration、Example Agent E2E 均通过
