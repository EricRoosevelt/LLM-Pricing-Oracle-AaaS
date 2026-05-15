import os
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx
from dotenv import load_dotenv


load_dotenv()

ORACLE_BASE_URL = os.getenv("ORACLE_BASE_URL", "http://127.0.0.1:8000")
ORACLE_API_KEY = os.getenv("ORACLE_API_KEY")
AGENT_ID = os.getenv("AGENT_ID", "Primary-Agent")

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


def build_decision_request(prompt: str, budget_usd: float) -> Dict[str, Any]:
    request_id = uuid4().hex
    return {
        "agent_id": AGENT_ID,
        "workflow_id": "example-workflow",
        "session_id": "demo-session",
        "request_id": request_id,
        "task_type": "general_chat",
        "modalities": ["text"],
        "language": "zh",
        "input_chars": len(prompt),
        "expected_output_tokens": 400,
        "context_window_tokens": max(len(prompt), 4096),
        "budget_limit_usd": budget_usd,
        "latency_slo_ms": 1500,
        "throughput_hint_qps": 1,
        "policy_id": "balanced",
        "capability_requirements": {
            "vision": False,
            "reasoning": False,
            "tool_calling": False,
            "json_mode": True,
        },
        "metadata": {
            "source": "examples/agent_client.py",
        },
    }


def create_decision(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not ORACLE_API_KEY:
        raise RuntimeError("missing control plane api key: ORACLE_API_KEY")

    response = httpx.post(
        f"{ORACLE_BASE_URL}/v1/routing/decisions",
        headers={
            "X-API-Key": ORACLE_API_KEY,
            "Idempotency-Key": payload["request_id"],
        },
        json=payload,
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


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


def report_outcome(
    decision: Dict[str, Any],
    request_payload: Dict[str, Any],
    attempts: List[Dict[str, Any]],
    final_status: str,
    final_model_id: Optional[str],
    final_cost_usd: float,
    end_to_end_latency_ms: int,
) -> Dict[str, Any]:
    response = httpx.post(
        f"{ORACLE_BASE_URL}/v1/routing/outcomes",
        headers={
            "X-API-Key": ORACLE_API_KEY,
            "Idempotency-Key": decision["decision_id"],
        },
        json={
            "decision_id": decision["decision_id"],
            "agent_id": request_payload["agent_id"],
            "request_id": request_payload["request_id"],
            "final_status": final_status,
            "attempts": attempts,
            "final_model_id": final_model_id,
            "fallback_depth": max(0, len(attempts) - 1),
            "end_to_end_latency_ms": end_to_end_latency_ms,
            "final_cost_usd": final_cost_usd,
            "user_feedback": final_status,
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def invoke_with_fallback(prompt: str, budget_usd: float) -> Dict[str, Any]:
    messages = [{"role": "user", "content": prompt}]
    request_payload = build_decision_request(prompt, budget_usd)
    decision = create_decision(request_payload)
    attempts: List[Dict[str, Any]] = []
    last_error: Optional[Exception] = None

    for candidate in decision["candidates"]:
        model_id = candidate["model_id"]
        provider, _ = model_id.split("/", 1)
        try:
            result = call_model(model_id, messages)
            attempts.append(
                {
                    "model_id": model_id,
                    "provider": provider,
                    "rank": candidate["rank"],
                    "status": "success",
                    "error_class": None,
                    "latency_ms": candidate["expected_ttfb_ms"],
                    "input_tokens": max(1, request_payload["input_chars"] // 2),
                    "output_tokens": request_payload["expected_output_tokens"],
                    "cost_usd": candidate["estimated_cost_usd"],
                }
            )
            report_outcome(
                decision=decision,
                request_payload=request_payload,
                attempts=attempts,
                final_status="success",
                final_model_id=model_id,
                final_cost_usd=candidate["estimated_cost_usd"],
                end_to_end_latency_ms=sum(attempt["latency_ms"] for attempt in attempts),
            )
            return {
                "decision_id": decision["decision_id"],
                "selected_model": model_id,
                "response": result,
            }
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError, RuntimeError) as exc:
            last_error = exc
            attempts.append(
                {
                    "model_id": model_id,
                    "provider": provider,
                    "rank": candidate["rank"],
                    "status": "upstream_error",
                    "error_class": exc.__class__.__name__,
                    "latency_ms": candidate["expected_ttfb_ms"],
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost_usd": 0.0,
                }
            )
            print(f"model failed, falling back: {model_id} -> {exc}")

    report_outcome(
        decision=decision,
        request_payload=request_payload,
        attempts=attempts,
        final_status="failed",
        final_model_id=None,
        final_cost_usd=0.0,
        end_to_end_latency_ms=sum(attempt["latency_ms"] for attempt in attempts),
    )
    raise RuntimeError("all models in decision candidates failed") from last_error


if __name__ == "__main__":
    result = invoke_with_fallback("请总结一下为什么需要做灰度发布。", budget_usd=0.02)
    print(result["decision_id"])
    print(result["selected_model"])
