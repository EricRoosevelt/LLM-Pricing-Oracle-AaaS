import logging
from contextlib import asynccontextmanager # ✅ 新增导入
import asyncio # ✅ 新增导入
from fastapi import FastAPI
from pydantic import BaseModel, Field
from app.core.config import settings
from app.api.v1 import router_endpoints
from app.services.latency_tracker import latency_tracker_loop # ✅ 引入我们的探活器

# 🚀 极其关键：配置全局日志格式与最低输出级别
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(module)s:%(funcName)s:%(lineno)d - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# ✅ 定义生命周期管理器
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时执行：将探活任务扔到后台独立运行
    tracker_task = asyncio.create_task(latency_tracker_loop())
    yield
    # 关闭时执行：取消后台任务
    tracker_task.cancel()

# ✅ 将 lifespan 挂载到 FastAPI 实例上
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="去中心化智能体的高频路由基础与定价神谕",
    version="1.0.0",
    docs_url="/docs",
    lifespan=lifespan # 👈 这里是关键
)

# 将 v1 版本的路由挂载到 FastAPI 实例上
app.include_router(router_endpoints.router, prefix=settings.API_V1_STR, tags=["Oracle Routing"])

# 定义严格的响应契约
class HealthCheckResponse(BaseModel):
    status: str = Field(..., description="API 当前运行状态")
    project: str = Field(..., description="项目名称")
    message: str = Field(..., description="附加状态信息")

# 在装饰器中强制绑定 response_model
@app.get("/health", tags=["System"], response_model=HealthCheckResponse)
async def health_check():
    return HealthCheckResponse(
        status="online",
        project=settings.PROJECT_NAME,
        message="Pricing Oracle is ready for requests."
    )