import asyncio
from datetime import datetime, timedelta, timezone

from app.core.metrics import MetricsStore
from app.services.latency_tracker import (
    InMemorySignalStore,
    build_probe_payload,
    probe_loop_once,
    smooth_and_store_signal,
)


def test_metrics_store_renders_counters_gauges_and_summaries():
    store = MetricsStore()
    store.incr("routing_decisions_total", labels={"policy_id": "balanced"})
    store.set_gauge("routing_probe_freshness_seconds", 12, labels={"policy_id": "balanced"})
    store.observe("routing_decision_latency_ms", 42.5, labels={"policy_id": "balanced"})

    rendered = store.render_prometheus()

    assert 'routing_decisions_total{policy_id="balanced"} 1.0' in rendered
    assert 'routing_probe_freshness_seconds{policy_id="balanced"} 12' in rendered
    assert 'routing_decision_latency_ms_count{policy_id="balanced"} 1.0' in rendered
    assert 'routing_decision_latency_ms_sum{policy_id="balanced"} 42.5' in rendered


def test_inmemory_signal_store_detects_fresh_signals():
    store = InMemorySignalStore()
    stale_time = (datetime.now(timezone.utc) - timedelta(seconds=300)).isoformat().replace("+00:00", "Z")
    fresh_time = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    asyncio.run(store.set_signal("lab/stale", {"last_probe_at": stale_time}))
    assert asyncio.run(store.has_fresh_signals(90)) is False

    asyncio.run(store.set_signal("lab/fresh", {"last_probe_at": fresh_time}))
    assert asyncio.run(store.has_fresh_signals(90)) is True


def test_build_probe_payload_and_smoothing():
    payload = build_probe_payload("https://example.invalid", "demo-model", "secret-key")
    assert payload["url"] == "https://example.invalid"
    assert payload["headers"]["Authorization"] == "Bearer secret-key"
    assert payload["payload"]["model"] == "demo-model"

    store = InMemorySignalStore()
    result = {
        "provider": "lab",
        "model_id": "lab/demo",
        "status": "success",
        "ttfb_ms": 300,
        "ttfb_p50_ms": 300,
        "ttfb_p95_ms": 360,
        "throughput_hint_qps": 40.0,
        "success_rate": 1.0,
        "last_probe_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "degraded_reason": None,
    }
    previous = {
        "ttfb_p50_ms": 500,
        "ttfb_p95_ms": 600,
        "throughput_hint_qps": 20.0,
        "success_rate": 0.5,
    }
    signal = asyncio.run(smooth_and_store_signal(store, result, previous=previous))
    assert signal["ttfb_p50_ms"] < previous["ttfb_p50_ms"]
    assert signal["throughput_hint_qps"] > previous["throughput_hint_qps"]
    assert asyncio.run(store.get_signals(["lab/demo"]))["lab/demo"]["ttfb_p95_ms"] == signal["ttfb_p95_ms"]


def test_probe_loop_once_uses_probe_model_results(monkeypatch):
    async def fake_probe_model(model_id, provider, target):
        return {
            "provider": provider,
            "model_id": model_id,
            "status": "success",
            "ttfb_ms": 250,
            "ttfb_p50_ms": 250,
            "ttfb_p95_ms": 300,
            "throughput_hint_qps": 50.0,
            "success_rate": 1.0,
            "last_probe_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "degraded_reason": None,
        }

    monkeypatch.setattr("app.services.latency_tracker.probe_model", fake_probe_model)
    store = InMemorySignalStore()
    results = asyncio.run(
        probe_loop_once(
            targets=[
                {"model_id": "lab/a", "provider": "lab", "target": {"url": "https://example.invalid"}},
                {"model_id": "lab/b", "provider": "lab", "target": {"url": "https://example.invalid"}},
            ],
            store=store,
        )
    )

    assert len(results) == 2
    assert results[0]["status"] == "success"
    assert results[0]["ttfb_ms"] == 250
    signals = asyncio.run(store.get_signals(["lab/a", "lab/b"]))
    assert signals["lab/a"]["success_rate"] == 1.0
    assert signals["lab/b"]["ttfb_p50_ms"] == 250
    assert "status" not in signals["lab/a"]
