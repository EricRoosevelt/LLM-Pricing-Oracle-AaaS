import asyncio
import logging
from typing import Any

import redis.asyncio as redis

from app.core.config import settings
from app.services.control_plane import CatalogRegistry, RedisEventPublisher
from app.services.latency_tracker import RedisSignalStore, build_probe_payload, probe_loop_once


def build_probe_targets(catalog_snapshot) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for provider in catalog_snapshot.providers:
        api_key = getattr(settings, provider.env_key_name or "", None) if provider.env_key_name else None
        if not api_key:
            continue
        for model in provider.models:
            targets.append(
                {
                    "provider": provider.provider,
                    "model_id": model.model_id,
                    "target": build_probe_payload(
                        provider_base_url=model.probe_endpoint or provider.base_url,
                        model_name=model.model_name,
                        api_key=api_key,
                    ),
                }
            )
    return targets


async def run_probe_worker() -> None:  # pragma: no cover - long-running worker glue
    logging.info("starting probe worker")
    redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    signal_store = RedisSignalStore(redis_client)
    event_publisher = RedisEventPublisher(redis_client)
    registry = CatalogRegistry(settings.catalog_path)

    while True:
        try:
            snapshot = registry.get_snapshot()
            targets = build_probe_targets(snapshot)
            if not targets:
                logging.warning("probe worker skipped because no provider probe credentials are configured")
            else:
                results = await probe_loop_once(targets, signal_store)
                for payload in results:
                    await event_publisher.publish_probe(payload)
        except Exception as exc:  # pragma: no cover - long-running worker glue
            logging.exception("probe worker iteration failed: %s", exc)
        await asyncio.sleep(settings.PROBE_INTERVAL_SECONDS)


def main() -> None:  # pragma: no cover - CLI entrypoint
    asyncio.run(run_probe_worker())


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    main()
