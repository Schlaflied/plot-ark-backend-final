# -----------------------------------------------------------------------------
# 「灵感方舟」后端施工图纸 (Plot Ark Backend Dockerfile)
# 版本: 3.0 - Cache Busting & Production Ready
# 描述: 为Google Cloud Run优化的最终版Dockerfile。
#       这个版本能确保依赖被正确安装，并以最高效的方式启动服务。
# -----------------------------------------------------------------------------

# 1. 使用官方的、轻量级的Python 3.9镜像作为基础
FROM python:3.9-slim

# 2. 设置环境变量，让Python运行更稳定
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# 3. 在容器内创建一个工作目录
WORKDIR /app

# 4. 复制依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. 复制你项目的所有其他文件到工作目录
COPY . .

# 6. 设置启动命令
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 app:app

