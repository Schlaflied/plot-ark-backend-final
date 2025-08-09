# 使用官方的 Python 基础镜像
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 复制依赖清单并安装
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 复制你所有的后端代码
COPY . .

# 暴露端口
EXPOSE 8080

# 运行应用的命令 (使用 gunicorn，这是生产环境推荐的方式)
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]