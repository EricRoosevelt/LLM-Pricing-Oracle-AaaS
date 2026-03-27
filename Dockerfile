# 使用官方极其精简的 Python 3.12 镜像
FROM python:3.12-slim

# 设置容器内的工作目录
WORKDIR /app

# 先拷贝依赖文件，利用 Docker 缓存机制加速构建
COPY requirements.txt .

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝所有项目代码到容器中
COPY . .

# 暴露 FastAPI 运行的 8000 端口
EXPOSE 8000

# 容器启动时执行的命令 (先跑数据库迁移，再启动 Uvicorn)
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]