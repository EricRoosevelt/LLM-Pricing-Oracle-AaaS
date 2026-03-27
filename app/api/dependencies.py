# app/api/dependencies.py
import time
import logging
from fastapi import Request, HTTPException, Depends
import redis.asyncio as redis
from redis.exceptions import RedisError
from app.core.config import settings
from app.core.security import verify_api_key # 引入鉴权函数

# 注意：别忘了在文件开头初始化 redis_client
redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)

# 🚀 把 verify_api_key 作为限流器的前置依赖！
async def rate_limiter(request: Request, agent_name: str = Depends(verify_api_key)):
    """
    工业级限流器：基于 Agent 身份限流，而不是容易被 NAT 误杀的 IP
    """
    # 以 Agent Name 和 当前分钟 构建 Redis Key
    current_minute = int(time.time() // 60)
    redis_key = f"rate_limit:agent:{agent_name}:{current_minute}"
    MAX_REQUESTS_PER_MINUTE = 5

    try:
        async with redis_client.pipeline(transaction=True) as pipe:
            pipe.incr(redis_key)
            results = await pipe.execute()

        result = results[0]
        if result == 1:
            await redis_client.expire(redis_key, 60)

        if result > MAX_REQUESTS_PER_MINUTE:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded for agent '{agent_name}'. Please try again later.",
                headers={"Retry-After": "60"}
            )
    except RedisError as e:
        logging.error(f"🔴 Redis is down! Rate limiter bypassed. Error: {e}")

    # 限流通过，返回 agent_name 给下游
    return agent_name

'''
之前的代码-
# 初始化 Redis 异步连接池
redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)

async def rate_limiter(request: Request):
    """
    带极速优化与 Fail-Open 容错机制的工业级限流器
    """
    client_ip = request.client.host
    current_minute = int(time.time() // 60)
    redis_key = f"rate_limit:{client_ip}:{current_minute}"
    MAX_REQUESTS_PER_MINUTE = 5

    try:
        # 使用 Pipeline 保证查询和自增操作的原子性
        async with redis_client.pipeline(transaction=True) as pipe:
            pipe.incr(redis_key)
            results = await pipe.execute()

        result = results[0]
        
        # 🚀 性能优化：只在每分钟的第 1 次请求时发送 EXPIRE 指令，节省 50% 的 I/O
        if result == 1:
            await redis_client.expire(redis_key, 60)

        if result > MAX_REQUESTS_PER_MINUTE:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please try again later.",
                headers={"Retry-After": "60"}
            )
            
    except RedisError as e:
        # 🛡️ 容错降级：如果 Redis 宕机，绝不阻塞核心业务，直接 Fail-Open 放行！
        logging.error(f"🔴 Redis is down! Rate limiter bypassed. Error: {e}")

    return client_ip
'''