# app/services/latency_tracker.py
import asyncio
import json
import logging
from pathlib import Path
import time

import httpx
import redis.asyncio as redis

from app.core.config import settings

# 获取当前 Python 文件所在的目录，然后向上推两层回到根目录，再找到 JSON 文件
# 路径推导: app/services/pricing_engine.py -> app/services -> app -> root -> models_config.json
CONFIG_PATH = Path(__file__).parent.parent.parent / "models_config.json"

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    GLOBAL_MODEL_CONFIG = json.load(f)

redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)

def build_probe_targets():
    targets = []
    
    for provider_name, provider_info in GLOBAL_MODEL_CONFIG["providers"].items():
        # 🚀 动态从 settings 中获取对应的 API KEY (利用 getattr 魔法)
        # 例如：getattr(settings, "DEEPSEEK_API_KEY")
        api_key = getattr(settings, provider_info["env_key_name"], None)
        
        if not api_key:
            continue 

        # 🚀 动态遍历 JSON 里配置的模型
        for model_name in provider_info["models"].keys():
            targets.append({
                "model_id": f"{provider_name}/{model_name}",
                "url": provider_info["base_url"],
                "headers": {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                "payload": {
                    "model": model_name,
                    "messages": [{"role": "user", "content": "Hi"}],
                    "max_tokens": 5,
                    "stream": True
                }
            })
            
    return targets

async def probe_stream_latency(target: dict) -> dict:
    """保留你的神级流式计算逻辑，只优化参数传入方式"""
    model_id = target["model_id"]
    proxies = settings.PROBE_PROXY if settings.PROBE_PROXY else None

    try:
        # 连接 5 秒必须通（不通说明排队太长或挂了），但允许它花 30 秒慢慢把字吐完
        timeout = httpx.Timeout(5.0, read=30.0)
        async with httpx.AsyncClient(timeout=timeout, proxy=proxies) as client:
            start_time = time.perf_counter()
            ttfb_ms = 0
            chunk_count = 0
            
            async with client.stream("POST", target["url"], json=target["payload"], headers=target["headers"]) as response:
                response.raise_for_status()
                
                async for chunk in response.aiter_lines():
                    if chunk:
                        chunk_count += 1
                        if ttfb_ms == 0:
                            ttfb_ms = int((time.perf_counter() - start_time) * 1000)
            
            total_time_s = time.perf_counter() - start_time
            tps = int(chunk_count / total_time_s) if total_time_s > 0 else 0
            return {"model_id": model_id, "ttfb_ms": ttfb_ms, "tps": tps}

    except Exception as e:
        logging.warning(f"⚠️ {model_id} 流式探活失败: {e}")
        return {"model_id": model_id, "ttfb_ms": 9999, "tps": 0}


async def update_latencies_to_redis():
    """加入了 EMA (指数移动平均) 的高端入库逻辑"""
    targets = build_probe_targets()
    if not targets:
        logging.warning("尚未配置任何大模型 API Key，探活引擎跳过执行。")
        return
        
    tasks = [probe_stream_latency(target) for target in targets]
    results = await asyncio.gather(*tasks)
    
    # 🚀 1. 循环前：一次性拿到所有模型当前的旧 TTFB
    model_ids = [res["model_id"] for res in results]
    old_keys = [f"model_latency:{m_id}" for m_id in model_ids]
    old_ttfbs = await redis_client.mget(old_keys)  # 一次 I/O，全部带回！
    
    # 将旧数据转为字典方便查询 {"openai/gpt-4o-mini": "250", ...}
    old_ttfb_map = dict(zip(model_ids, old_ttfbs))

    # 🚀 2. 纯内存计算 + Pipeline 纯打包写入
    async with redis_client.pipeline(transaction=True) as pipe:
        for res in results:
            model_id = res["model_id"]
            new_ttfb = res["ttfb_ms"]
            new_tps = res["tps"]
            
            old_ttfb = old_ttfb_map.get(model_id)
            
            if old_ttfb and new_ttfb != 9999: 
                smoothed_ttfb = int(int(old_ttfb) * 0.7 + new_ttfb * 0.3)
            else:
                smoothed_ttfb = new_ttfb
                
            pipe.set(f"model_latency:{model_id}", smoothed_ttfb, ex=120)
            pipe.set(f"model_tps:{model_id}", new_tps, ex=120)

            # 👇 看着控制台心跳，是一种享受
            logging.info(f"📡 [探活] {model_id} | 原始TTFB: {new_ttfb}ms -> 平滑TTFB: {smoothed_ttfb}ms | TPS: {new_tps}")
            
        # 一次性把所有的 SET 命令发给 Redis
        await pipe.execute()

async def latency_tracker_loop():
    logging.info("🚀 启动全局流式神谕探活守护进程 (带 EMA 平滑防抖)...")
    while True:
        try:
            await update_latencies_to_redis()
        except Exception as e:
            logging.error(f"🔴 探活循环严重崩溃: {e}")
        await asyncio.sleep(60)
