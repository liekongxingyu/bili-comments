# 1. 指定基础镜像：使用 slim 版本可以显著减小镜像体积
FROM python:3.11-slim

# 2. 设置环境变量：防止 Python 产生 pyc 文件，并强制日志实时输出（不缓存）
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 3. 设置容器内的工作目录
WORKDIR /app

# 4. 先复制依赖文件：利用 Docker 的层缓存机制
# 只要 requirements.txt 不变，再次构建时会跳过 pip install 阶段
COPY requirements.txt .

# 5. 安装依赖：使用国内镜像源（如阿里云）可以大幅提升速度
RUN pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# 6. 复制项目所有内容到容器中
COPY . .

# 7. 声明容器监听的端口（仅作说明，实际映射需在运行命令中指定）
EXPOSE 8080

# 8. 启动命令：运行你的监控主程序
CMD ["python", "main.py"]