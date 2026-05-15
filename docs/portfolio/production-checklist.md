# Notion 制作清单

## 内容准备

- [x] Notion 主文案：[notion-case-study.md](./notion-case-study.md)
- [x] 架构图 Mermaid：[architecture.mmd](./architecture.mmd)
- [x] 架构图 PNG：[assets/architecture.png](./assets/architecture.png)
- [x] 架构图可编辑源文件：[assets/architecture.svg](./assets/architecture.svg)
- [x] API Demo：[api-demo.md](./api-demo.md)
- [x] 测试与验收摘要：[validation-summary.md](./validation-summary.md)
- [x] 产品说明卡片：[assets/product-cards.png](./assets/product-cards.png)
- [x] 技术亮点卡片：[assets/technical-highlights-card.png](./assets/technical-highlights-card.png)
- [x] 测试结果卡片：[assets/test-results-card.png](./assets/test-results-card.png)
- [x] 验收摘要卡片：[assets/validation-summary-card.png](./assets/validation-summary-card.png)

## Notion 页面组装顺序

1. 粘贴标题、项目定位和关键结果。
2. 放入产品问题和核心用户旅程。
3. 上传 `assets/architecture.png`，并在下方放 `architecture.svg` 和 `architecture.mmd` 链接或源码。
4. 粘贴 API Demo 摘要，保留完整 Demo 文档链接。
5. 上传测试结果卡片和验收摘要卡片。
6. 放入产品判断、MVP 复盘和路线图。
7. 最后添加 GitHub 仓库链接、运行命令和测试命令。

## 脱敏检查

- [ ] 不展示真实 provider API key。
- [ ] 不展示真实 `.env`。
- [ ] 不展示生产数据库连接串。
- [ ] 不展示个人私密路径或账号信息。
- [ ] Notion 截图只保留脱敏请求和关键响应字段。

## 面试验收标准

- HR 能在 1 分钟内理解：这是一个为 AI Agent 降低成本和稳定性风险的基础设施产品。
- 产品面试官能看到：用户、痛点、MVP 边界、产品取舍、指标和路线图。
- 技术面试官能看到：架构、API、测试、持久化、worker、observability。
- 页面不依赖读者打开代码仓库，也能讲清楚项目闭环。
