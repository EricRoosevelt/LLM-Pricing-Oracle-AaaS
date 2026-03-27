import os
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv


load_dotenv()

ORACLE_BASE_URL = os.getenv("ORACLE_BASE_URL", "http://127.0.0.1:8000")
ORACLE_API_KEY = os.getenv("ORACLE_API_KEY")

PROVIDER_CONFIGS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/chat/completions",
        "api_key_env": "DEEPSEEK_API_KEY",
    },
    "moonshot": {
        "base_url": "https://api.moonshot.cn/v1/chat/completions",
        "api_key_env": "KIMI_API_KEY",
    },
}


def build_route_request(prompt: str, budget_usd: float) -> Dict[str, Any]:
    return {
        "task_category": "general_chat",
        "language": "zh",
        "payload_char_count": len(prompt),
        "expected_output_words": 400,
        "max_budget_usd": budget_usd,
        "max_latency_ms": 1500,
        "requires_vision": False,
        "current_qps": 1,
    }


def fetch_routing_cascade(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not ORACLE_API_KEY:
        raise RuntimeError("missing gateway api key: ORACLE_API_KEY")

    response = httpx.post(
        f"{ORACLE_BASE_URL}/api/v1/route/optimize",
        headers={"X-API-Key": ORACLE_API_KEY},
        json=payload,
        timeout=15,
    )
    response.raise_for_status()
    return response.json()["routing_cascade"]


def call_model(model_id: str, messages: List[Dict[str, str]], max_tokens: int = 800) -> Dict[str, Any]:
    provider, model_name = model_id.split("/", 1)
    provider_config = PROVIDER_CONFIGS[provider]
    api_key = os.getenv(provider_config["api_key_env"])
    if not api_key:
        raise RuntimeError(f"missing provider api key: {provider_config['api_key_env']}")

    response = httpx.post(
        provider_config["base_url"],
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model_name,
            "messages": messages,
            "max_tokens": max_tokens,
        },
        timeout=60,
    )
    if response.status_code in {408, 409, 429} or response.status_code >= 500:
        raise httpx.HTTPStatusError(
            f"retryable upstream error: {response.status_code}",
            request=response.request,
            response=response,
        )
    response.raise_for_status()
    return response.json()


def invoke_with_fallback(prompt: str, budget_usd: float) -> Dict[str, Any]:
    messages = [{"role": "user", "content": prompt}]
    cascade = fetch_routing_cascade(build_route_request(prompt, budget_usd))
    last_error: Optional[Exception] = None

    for candidate in cascade:
        model_id = candidate["model_id"]
        try:
            result = call_model(model_id, messages)
            return {
                "selected_model": model_id,
                "estimated_cost_usd": candidate["estimated_cost_usd"],
                "response": result,
            }
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError, RuntimeError) as exc:
            last_error = exc
            print(f"model failed, falling back: {model_id} -> {exc}")

    raise RuntimeError("all models in routing_cascade failed") from last_error


if __name__ == "__main__":
    result = invoke_with_fallback("请总结一下为什么需要做灰度发布。", budget_usd=0.02)
    print(result["selected_model"])
    print(result["response"])
