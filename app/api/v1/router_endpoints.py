# app/api/v1/router_endpoints.py
import logging

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Request
import redis.asyncio as redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.schemas.routing import OptimizeRouteRequest, OptimizeRouteResponse
from app.services.pricing_engine import calculate_optimal_routing, ACTIVE_MODELS
from app.api.dependencies import rate_limiter
from app.services.auditor import async_record_audit_log

router = APIRouter()
redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)

@router.post("/route/optimize", response_model=OptimizeRouteResponse)
async def optimize_route(
    request_body: OptimizeRouteRequest,     # ✅ 接收请求 JSON
    request_meta: Request,                  # ✅ 获取底层的 HTTP 请求元数据
    background_tasks: BackgroundTasks,      # ✅ 获取后台任务句柄
    agent_name: str = Depends(rate_limiter) # ✅ 触发：鉴权 -> 限流 -> 返回 Agent 名字
):
    # 🚀 优雅地从底层 Request 提取 IP
    client_ip = request_meta.client.host

    # 🛡️ 拦截器安防位置：Fail Fast！如果配置没加载进来，直接熔断报错
    if not ACTIVE_MODELS:
        raise HTTPException(
            status_code=500, 
            detail="Oracle configuration error: No active models loaded."
        )
    
    # 1. 网关层负责去 Redis 捞实时探活数据
    latency_keys = [f"model_latency:{model['model_id']}" for model in ACTIVE_MODELS]
    qps_keys = [f"model_tps:{model['model_id']}" for model in ACTIVE_MODELS]
    try:
        latencies_raw = await redis_client.mget(latency_keys)
        qps_raw = await redis_client.mget(qps_keys)
    except RedisError as exc:
        logging.warning("routing metrics fallback triggered: %s", exc)
        latencies_raw = [None] * len(ACTIVE_MODELS)
        qps_raw = [None] * len(ACTIVE_MODELS)

    real_latencies_map = {}
    real_qps_map = {}
    for i, model in enumerate(ACTIVE_MODELS):
        model_id = model["model_id"]
        if latencies_raw[i] is not None:
            real_latencies_map[model_id] = int(latencies_raw[i])
        if qps_raw[i] is not None:
            real_qps_map[model_id] = float(qps_raw[i])

    report = calculate_optimal_routing(
        input_char_count=request_body.payload_char_count,
        output_word_count=request_body.expected_output_words,
        max_budget_usd=request_body.max_budget_usd,
        max_latency_ms=request_body.max_latency_ms,
        language=request_body.language,
        task_category=request_body.task_category,
        requires_vision=request_body.requires_vision,
        real_latencies_map=real_latencies_map,
        real_qps_map=real_qps_map,
        score_weights=request_body.score_weights.model_dump() if request_body.score_weights else None,
        normalization_baseline=request_body.normalization_baseline.model_dump() if request_body.normalization_baseline else None,
        current_qps=request_body.current_qps,
        free_tier_remaining_tokens=request_body.free_tier_remaining_tokens,
        return_report=True,
    )
    cascade = report["cascade"]

    if not cascade:
        raise HTTPException(
            status_code=400, 
            detail="No models meet your budget and latency constraints."
        )

    logging.info(
        "[ROUTING SUCCESS] agent=%s ip=%s best=%s latency_ms=%s price_error_pct=%s",
        agent_name,
        client_ip,
        cascade[0].model_id,
        report["observability"].routing_compute_ms,
        report["observability"].pricing_error_pct,
    )

    # 4. 后台异步记账：所有的信息都完美凑齐了！
    background_tasks.add_task(
        async_record_audit_log,
        agent_name=agent_name,
        request_ip=client_ip,
        task_category=request_body.task_category,
        budget_usd=request_body.max_budget_usd,
        best_model_id=cascade[0].model_id,
        routing_cascade=cascade,
        observability=report["observability"],
        benchmark_report=report["benchmark_report"],
        request_context={
            "language": request_body.language,
            "requires_vision": request_body.requires_vision,
            "current_qps": request_body.current_qps,
            "score_weights": request_body.score_weights.model_dump() if request_body.score_weights else None,
            "normalization_baseline": request_body.normalization_baseline.model_dump() if request_body.normalization_baseline else None,
        },
    )

    # 5. 秒回给智能体
    return OptimizeRouteResponse(
        status="success",
        routing_cascade=cascade,
        ttl_seconds=300,
        observability=report["observability"],
        benchmark_report=report["benchmark_report"],
    )
