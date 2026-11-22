#!/bin/sh
set -eu

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

mkdir -p /app/data /app/config /app/downloads /app/logs

# 挂载空配置目录时，用镜像内置模板初始化
if [ -f /opt/dlr-defaults/config/config.ini ] && [ ! -f /app/config/config.ini ]; then
    cp -a /opt/dlr-defaults/config/config.ini /app/config/config.ini
fi
if [ ! -f /app/config/URL_config.ini ]; then
    : > /app/config/URL_config.ini
fi

if [ "$(id -u)" = "0" ]; then
    if getent group dlr >/dev/null 2>&1; then
        groupmod -o -g "$PGID" dlr
    else
        groupadd -o -g "$PGID" dlr
    fi
    if id -u dlr >/dev/null 2>&1; then
        usermod -o -u "$PUID" -g "$PGID" dlr
    else
        useradd -o -u "$PUID" -g "$PGID" -M -s /usr/sbin/nologin dlr
    fi
    # 让挂载目录可写；目录属主已正确时跳过，避免大录像库反复递归
    for dir in /app/data /app/config /app/downloads /app/logs; do
        if [ "$(stat -c '%u:%g' "$dir" 2>/dev/null)" != "$PUID:$PGID" ]; then
            chown -R "$PUID:$PGID" "$dir"
        fi
    done
    exec gosu "$PUID:$PGID" "$@"
fi

exec "$@"
