# Agent 集成示例

这个目录展示一个最小可运行的 Agent 端接入方式：

1. Agent 先向路由网关请求 `routing_cascade`
2. Agent 拿着返回的模型梯队，自己用厂商 API Key 直接调用大模型
3. 如果第一名模型宕机、超时或限流，自动切到下一名继续请求

## 文件说明

- `agent_client.py`：完整的串联示例
- `requirements.txt`：示例脚本依赖

## 环境变量

先准备一个独立的示例环境文件，例如：

```env
ORACLE_BASE_URL=http://127.0.0.1:8000
ORACLE_API_KEY=replace-with-your-gateway-key
DEEPSEEK_API_KEY=sk-your-deepseek-key
KIMI_API_KEY=sk-your-kimi-key
```

## 安装

```bash
cd examples
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 运行

```bash
python agent_client.py
```

## 适配说明

- 当前示例内置了 `deepseek` 和 `moonshot` 两个 provider 的调用方式
- 如果你在 `models_config.json` 中新增了 provider，只需要在 `PROVIDER_CONFIGS` 中补上 `base_url` 和对应环境变量名
- 如果你的 Agent 框架支持工具调用，可以把 `fetch_routing_cascade` 和 `invoke_with_fallback` 直接封装成工具函数
