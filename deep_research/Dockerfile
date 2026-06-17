# Deep Research - 一键 Docker 部署
# 用法: docker run -p 8765:8765 deep-research
FROM python:3.12-slim AS builder

WORKDIR /app

# 安装系统依赖（Playwright 需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl git build-essential \
    && rm -rf /var/lib/apt/lists/*

# 安装 Playwright 浏览器
RUN pip install playwright && playwright install --with-deps chromium

# 复制源码
COPY . /app

# 安装 Python 依赖
RUN pip install --no-cache-dir -e ".[web]"


# ---- 运行时镜像 ----
FROM python:3.12-slim

WORKDIR /app

# 安装 Playwright 运行时
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.12/site-packages/playwright /usr/local/lib/python3.12/site-packages/playwright
COPY --from=builder /usr/local/bin/playwright /usr/local/bin/playwright
COPY --from=builder /root/.cache/ms-playwright /root/.cache/ms-playwright

COPY --from=builder /app /app

ENV PYTHONPATH=/app/src
ENV DR_PLAYWRIGHT_HEADLESS=true

EXPOSE 8765

# 默认：Ollama 地址（可覆盖）
ENV DR_LOCAL_MODEL_URL=http://host.docker.internal:11434/v1
ENV DR_USE_LOCAL_MODEL=true

CMD ["python", "/app/run.py"]
