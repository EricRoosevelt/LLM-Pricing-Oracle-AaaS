# app/services/auditor.py
import logging
from typing import Optional # 🚀
from app.core.database import AsyncSessionLocal
from app.models.audit import AuditLog

async def async_record_audit_log(
    request_ip: str,
    task_category: str,
    budget_usd: float,
    best_model_id: str,
    routing_cascade: list,
    observability=None,
    benchmark_report=None,
    request_context: Optional[dict] = None,
    agent_name: Optional[str] = None, # 🚀 新参，默认值为 None
):
    """
    后台异步记账任务：独立开启数据库 Session，写完即走，绝不阻塞主线程
    """
    try:
        # Pydantic 的对象需要先转成字典，才能存入 JSON 类型的字段
        cascade_data = [decision.model_dump() for decision in routing_cascade]
        routing_snapshot = {
            "cascade": cascade_data,
            "observability": observability.model_dump() if hasattr(observability, "model_dump") else observability,
            "benchmark_report": benchmark_report.model_dump() if hasattr(benchmark_report, "model_dump") else benchmark_report,
            "request_context": request_context or {},
        }

        # 每次写库都开启一个全新的异步 Session
        async with AsyncSessionLocal() as session:
            async with session.begin():  # 自动管理事务 (Commit / Rollback)
                new_log = AuditLog(
                    agent_name=agent_name, # 🚀 新增字段，记录调用的智能体名称
                    request_ip=request_ip,
                    task_category=task_category,
                    budget_usd=budget_usd,
                    best_model_id=best_model_id,
                    routing_cascade=routing_snapshot
                )
                session.add(new_log)
                
            # 离开 with 块时，数据已被安全 Commit 到 Postgres
            logging.info(f"📝 [AUDIT SUCCESS] 审计日志已异步写入 DB, 赢家模型: {best_model_id}")
            
    except Exception as e:
        # 记账失败绝对不能影响主业务，打印个错误日志就行了
        logging.error(f"🔴 [AUDIT FAILED] 审计日志写入失败: {e}")
