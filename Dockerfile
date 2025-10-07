# syntax=docker/dockerfile:1
FROM --platform=$BUILDPLATFORM python:3.12-slim

WORKDIR /app

# 合并安装依赖，清理缓存，减少镜像层数
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    pip install --upgrade pip && \
    pip install uv && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./

RUN uv pip install --system ".[perf]" --no-cache-dir && \
    uv pip install --system bilichat-request --no-cache-dir && \
    apt-get purge -y build-essential && \
    apt-get autoremove -y && \
    rm -rf /root/.cache/pip

COPY . .

CMD ["nb", "run"]
