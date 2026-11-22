#!/usr/bin/env bash
# 清理本项目的历史 Docker 构建记录、悬空镜像，并限制构建缓存大小。
# 只保留最新一条构建记录与当前镜像标签，避免 Builds/Images 持续堆积。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
KEEP_BUILD_CACHE="${KEEP_BUILD_CACHE:-1GB}"

# 删除除最新一条之外的本仓库构建记录
OLD_IDS="$(
  docker buildx history ls --local --format json 2>/dev/null \
    | python3 -c 'import json,sys; rows=[json.loads(line) for line in sys.stdin if line.strip()]; print("\n".join(row["ref"].rsplit("/", 1)[-1] for row in rows[1:]))'
)"
if [ -n "$OLD_IDS" ]; then
  while IFS= read -r build_id; do
    [ -n "$build_id" ] || continue
    docker buildx history rm "$build_id" >/dev/null
  done <<< "$OLD_IDS"
fi

# 删除旧构建留下的 <none> 镜像，保留当前标签
docker image prune -f >/dev/null

# 构建缓存设置上限，避免无限增长；保留最近使用的一部分以加速下一次构建
docker buildx prune -f --max-used-space "$KEEP_BUILD_CACHE" >/dev/null

echo "已保留最新构建记录与当前镜像："
docker images 'dlr-webui' --format '  {{.Repository}}:{{.Tag}}  {{.ID}}  {{.Size}}'
docker system df
