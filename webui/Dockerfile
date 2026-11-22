ARG NODE_IMAGE=node:22-slim
ARG PYTHON_IMAGE=python:3.11-slim

FROM ${NODE_IMAGE} AS frontend
WORKDIR /src/webui/frontend
COPY webui/frontend/package.json webui/frontend/package-lock.json* ./
RUN npm ci
COPY webui/frontend .
RUN npm run build -- --outDir /out

FROM ${PYTHON_IMAGE}
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    TZ=Asia/Shanghai \
    DLR_PORT=8642 \
    DLR_DATA_DIR=/app/data \
    DLR_CONFIG_DIR=/app/config \
    DLR_DOWNLOAD_DIR=/app/downloads \
    DLR_LOG_DIR=/app/logs
WORKDIR /app

# ffmpeg 随镜像内置；Node.js 供上游签名脚本使用
# 可通过 DEBIAN_MIRROR 切换 Debian 软件源，避免跨架构构建时访问官方源超时
ARG DEBIAN_MIRROR=http://deb.debian.org/debian
ARG DEBIAN_SECURITY_MIRROR=http://deb.debian.org/debian-security
RUN if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
      sed -i "s|http://deb.debian.org/debian-security|${DEBIAN_SECURITY_MIRROR}|g; s|http://deb.debian.org/debian|${DEBIAN_MIRROR}|g" /etc/apt/sources.list.d/debian.sources; \
    fi && \
    apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg ca-certificates gosu nodejs && \
    rm -rf /var/lib/apt/lists/*

ARG PIP_INDEX_URL=https://pypi.org/simple
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
COPY requirements.txt ./requirements.txt
COPY webui/requirements.txt ./webui-requirements.txt
RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" \
    -r requirements.txt -r webui-requirements.txt

COPY . /app
COPY --from=frontend /out /app/webui/backend/static

# 不把本地 config 打入镜像，避免 Cookie、Token 等敏感配置泄露；
# 首次启动由应用按默认设置生成 config.ini
RUN mkdir -p /opt/dlr-defaults/config /app/data /app/config /app/downloads /app/logs && \
    useradd -m -u 10001 -s /usr/sbin/nologin dlr

COPY webui/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8642
VOLUME ["/app/data", "/app/config", "/app/downloads", "/app/logs"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8642/api/system/health', timeout=3)" || exit 1

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["python", "run_webui.py", "--no-browser"]
