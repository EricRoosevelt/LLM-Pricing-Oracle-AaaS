# 升级版
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

# 创建异步引擎 (echo=False 在生产环境关闭 SQL 打印)
# 🚀 增加高并发连接池配置
engine = create_async_engine(
    settings.DATABASE_URL, 
    echo=False,
    pool_size=20,          # 核心连接池大小，保持常驻连接
    max_overflow=10,       # 当请求激增时，最多允许额外创建 10 个临时连接
    pool_timeout=30,       # 如果池子空了，协程最多等待 30 秒，超时才报错
    pool_recycle=1800      # 每半小时回收一次连接，防止数据库主动断开闲置连接 (MySQL常见，PG也建议加上)
)

# 创建异步 Session 工厂
AsyncSessionLocal = async_sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

# ORM 模型基类
class Base(DeclarativeBase):
    pass