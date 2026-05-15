import logging
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request, Response

from app.api.v1 import router_endpoints
from app.core.config import settings
from app.core.metrics import metrics_store


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(module)s:%(funcName)s:%(lineno)d - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Agent-first routing control plane that returns routing decisions, records outcomes, and manages provider signals.",
    version="1.1.0",
    docs_url="/docs",
)
app.include_router(router_endpoints.router, prefix=settings.API_V1_STR)


@app.middleware("http")
async def trace_and_metrics_middleware(request: Request, call_next):
    trace_id = request.headers.get("X-Trace-ID", uuid4().hex)
    started = perf_counter()
    request.state.trace_id = trace_id
    response: Response = await call_next(request)
    duration_ms = round((perf_counter() - started) * 1000, 3)
    response.headers["X-Trace-ID"] = trace_id
    metrics_store.observe(
        "http_request_latency_ms",
        duration_ms,
        labels={"method": request.method, "path": request.url.path, "status_code": str(response.status_code)},
    )
    metrics_store.incr(
        "http_requests_total",
        labels={"method": request.method, "path": request.url.path, "status_code": str(response.status_code)},
    )
    return response


@app.get("/metrics", tags=["Observability"])
async def metrics() -> Response:
    return Response(metrics_store.render_prometheus(), media_type="text/plain; version=0.0.4")
