# app/models/audit.py
from datetime import datetime, timezone
from typing import Optional # 🚀 引入 Optional
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class AuditLog(Base):
    __tablename__ = "audit_logs"

    # 🚀 拥抱 SQLAlchemy 2.0 的 Mapped 类型提示，告别裸写 Column
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    # 🚀 正确的 2.0 语法：允许为空必须写 Optional[str]
    agent_name: Mapped[Optional[str]] = mapped_column(index=True)
    request_ip: Mapped[str] = mapped_column(index=True)
    task_category: Mapped[str] = mapped_column()
    budget_usd: Mapped[float] = mapped_column()
    
    # ✅ 完美的 comment 运用
    best_model_id: Mapped[str] = mapped_column(comment="系统推荐的最优模型")
    # ⚠️ 注意 JSON 类型的特殊写法
    routing_cascade: Mapped[dict] = mapped_column(JSON, comment="完整的备选梯队完整快照")
    
    # 动态默认值：获取当前 UTC 时间，并抹除时区标签以适应数据库的 Naive Timestamp
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )