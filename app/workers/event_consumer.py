import asyncio
import json
import logging

import redis.asyncio as redis

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.services.persistence import SqlAlchemyDecisionStore


async def run_event_consumer() -> None:  # pragma: no cover - long-running worker glue
    logging.info("starting event consumer")
    redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    decision_store = SqlAlchemyDecisionStore(AsyncSessionLocal)
    offsets = {
        settings.OUTCOME_STREAM_NAME: "0-0",
        settings.PROBE_STREAM_NAME: "0-0",
    }

    while True:
        try:
            events = await redis_client.xread(offsets, count=50, block=1000)
            for stream_name, entries in events:
                for entry_id, fields in entries:
                    offsets[stream_name] = entry_id
                    payload = json.loads(fields["payload"])
                    if stream_name == settings.PROBE_STREAM_NAME:
                        await decision_store.record_probe_snapshot(payload)
                    else:
                        logging.info(
                            "outcome event consumed decision_id=%s final_status=%s",
                            payload.get("decision_id"),
                            payload.get("final_status"),
                        )
        except Exception as exc:  # pragma: no cover - long-running worker glue
            logging.exception("event consumer iteration failed: %s", exc)
            await asyncio.sleep(1)


def main() -> None:  # pragma: no cover - CLI entrypoint
    asyncio.run(run_event_consumer())


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    main()
