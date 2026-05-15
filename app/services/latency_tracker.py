import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional

import httpx
import redis.asyncio as redis
from redis.exceptions import RedisError

from app.core.config import settings


SIGNAL_KEY_PREFIX = "routing-signal"


class InMemorySignalStore:
    def __init__(self) -> None:
        self.signals: Dict[str, Dict[str, Any]] = {}

    async def get_signals(self, model_ids: list[str]) -> Dict[str, Dict[str, Any]]:
        return {model_id: self.signals.get(model_id, {}) for model_id in model_ids}

    async def set_signal(self, model_id: str, signal: Dict[str, Any]) -> None:
        self.signals[model_id] = signal

    async def has_fresh_signals(self, max_age_seconds: int) -> bool:
        now = datetime.now(timezone.utc)
        for signal in self.signals.values():
            try:
                observed_at = datetime.fromisoformat(signal["last_probe_at"].replace("Z", "+00:00"))
            except (KeyError, TypeError, ValueError):
                continue
            if int((now - observed_at).total_seconds()) <= max_age_seconds:
                return True
        return False


class RedisSignalStore:
    def __init__(self, client: redis.Redis) -> None:
        self.client = client

    async def get_signals(self, model_ids: list[str]) -> Dict[str, Dict[str, Any]]:  # pragma: no cover - integration glue
        if not model_ids:
            return {}
        raw_values = await self.client.mget([f"{SIGNAL_KEY_PREFIX}:{model_id}" for model_id in model_ids])
        signals: Dict[str, Dict[str, Any]] = {}
        for model_id, payload in zip(model_ids, raw_values):
            if payload:
                try:
                    signals[model_id] = json.loads(payload)
                except json.JSONDecodeError:
                    logging.warning("invalid routing signal payload for %s", model_id)
        return signals

    async def set_signal(self, model_id: str, signal: Dict[str, Any], ttl_seconds: int = 600) -> None:  # pragma: no cover - integration glue
        await self.client.set(f"{SIGNAL_KEY_PREFIX}:{model_id}", json.dumps(signal), ex=ttl_seconds)

    async def has_fresh_signals(self, max_age_seconds: int) -> bool:  # pragma: no cover - integration glue
        try:
            keys = await self.client.keys(f"{SIGNAL_KEY_PREFIX}:*")
            if not keys:
                return False
            values = await self.client.mget(keys)
        except RedisError:
            return False
        now = datetime.now(timezone.utc)
        for payload in values:
            if not payload:
                continue
            try:
                signal = json.loads(payload)
                observed_at = datetime.fromisoformat(signal["last_probe_at"].replace("Z", "+00:00"))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
            if int((now - observed_at).total_seconds()) <= max_age_seconds:
                return True
        return False


def build_probe_payload(provider_base_url: str, model_name: str, api_key: str) -> Dict[str, Any]:
    return {
        "url": provider_base_url,
        "headers": {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        "payload": {
            "model": model_name,
            "messages": [{"role": "user", "content": "health probe"}],
            "max_tokens": 4,
            "stream": True,
        },
    }


async def probe_model(model_id: str, provider: str, target: Mapping[str, Any]) -> Dict[str, Any]:  # pragma: no cover - integration glue
    proxies = settings.PROBE_PROXY or None
    timeout = httpx.Timeout(5.0, read=30.0)
    start = time.perf_counter()
    chunk_count = 0
    ttfb_ms = 9999
    degraded_reason: Optional[str] = None
    status = "success"
    try:
        async with httpx.AsyncClient(timeout=timeout, proxy=proxies) as client:
            async with client.stream(
                "POST",
                target["url"],
                json=target["payload"],
                headers=target["headers"],
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_lines():
                    if chunk:
                        chunk_count += 1
                        if ttfb_ms == 9999:
                            ttfb_ms = int((time.perf_counter() - start) * 1000)
    except Exception as exc:  # pragma: no cover - exercised indirectly in worker environments
        status = "degraded"
        degraded_reason = exc.__class__.__name__
        logging.warning("probe failure for %s: %s", model_id, exc)

    total_time = max(time.perf_counter() - start, 0.001)
    throughput_hint_qps = round(chunk_count / total_time, 3)
    success_rate = 1.0 if status == "success" else 0.0
    observed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "provider": provider,
        "model_id": model_id,
        "status": status,
        "ttfb_ms": ttfb_ms,
        "ttfb_p50_ms": ttfb_ms,
        "ttfb_p95_ms": int(ttfb_ms * 1.15) if ttfb_ms < 9999 else 9999,
        "throughput_hint_qps": throughput_hint_qps,
        "success_rate": success_rate,
        "last_probe_at": observed_at,
        "degraded_reason": degraded_reason,
    }


async def smooth_and_store_signal(
    store: InMemorySignalStore | RedisSignalStore,
    result: Mapping[str, Any],
    previous: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    previous = previous or {}
    prev_p50 = float(previous.get("ttfb_p50_ms", result["ttfb_p50_ms"]))
    prev_p95 = float(previous.get("ttfb_p95_ms", result["ttfb_p95_ms"]))
    prev_success = float(previous.get("success_rate", result["success_rate"]))
    prev_qps = float(previous.get("throughput_hint_qps", result["throughput_hint_qps"]))

    signal = {
        "provider": result["provider"],
        "model_id": result["model_id"],
        "ttfb_p50_ms": int(prev_p50 * 0.7 + float(result["ttfb_p50_ms"]) * 0.3),
        "ttfb_p95_ms": int(max(prev_p95 * 0.6, float(result["ttfb_p95_ms"]) * 0.4)),
        "throughput_hint_qps": round(prev_qps * 0.5 + float(result["throughput_hint_qps"]) * 0.5, 3),
        "success_rate": round(prev_success * 0.7 + float(result["success_rate"]) * 0.3, 4),
        "last_probe_at": result["last_probe_at"],
        "degraded_reason": result.get("degraded_reason"),
    }
    await store.set_signal(result["model_id"], signal)
    return signal


async def build_redis_signal_store() -> RedisSignalStore:  # pragma: no cover - integration glue
    return RedisSignalStore(redis.from_url(settings.REDIS_URL, decode_responses=True))


async def probe_loop_once(
    targets: list[dict[str, Any]],
    store: InMemorySignalStore | RedisSignalStore,
) -> list[Dict[str, Any]]:
    existing = await store.get_signals([target["model_id"] for target in targets])
    tasks = [
        probe_model(target["model_id"], target["provider"], target["target"])
        for target in targets
    ]
    results = await asyncio.gather(*tasks)
    for result in results:
        await smooth_and_store_signal(store, result, previous=existing.get(result["model_id"]))
    return list(results)
