#!/usr/bin/env bash
# Publish one target/channel by dispatching .github/workflows/release.yml.
#
# Four everyday commands:
#   ./scripts/release.sh beta docker
#   ./scripts/release.sh beta windows
#   ./scripts/release.sh release docker
#   ./scripts/release.sh release windows
#
# Options:
#   --ref <branch>        branch/tag to build from (default: current branch)
#   --bump patch|minor|major  stable version bump (default: patch)
#   --version <x.y.z>     explicit version; skips auto numbering
#   --no-wait             dispatch and print the run URL without waiting
#   --allow-dirty         allow uncommitted changes (not recommended)
set -euo pipefail

CHANNEL="${1:-}"
TARGET="${2:-}"
if [[ "$CHANNEL" != "beta" && "$CHANNEL" != "release" ]]; then
  echo "usage: $0 <beta|release> <docker|windows|both> [options]" >&2
  exit 2
fi
if [[ "$TARGET" != "docker" && "$TARGET" != "windows" && "$TARGET" != "both" ]]; then
  echo "usage: $0 <beta|release> <docker|windows|both> [options]" >&2
  exit 2
fi
shift 2

REF=""
BUMP="patch"
VERSION=""
WAIT=1
ALLOW_DIRTY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --ref) REF="$2"; shift 2 ;;
    --bump) BUMP="$2"; shift 2 ;;
    --version) VERSION="$2"; shift 2 ;;
    --no-wait) WAIT=0; shift ;;
    --allow-dirty) ALLOW_DIRTY=1; shift ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI (gh) is required: https://cli.github.com/" >&2
  exit 1
fi
if ! gh auth status >/dev/null 2>&1; then
  echo "gh is not authenticated. Run: gh auth login" >&2
  exit 1
fi

if [[ -z "$REF" ]]; then
  REF="$(git rev-parse --abbrev-ref HEAD)"
fi
if [[ "$REF" == "HEAD" ]]; then
  REF="main"
fi

if [[ -n "$(git status --porcelain)" ]]; then
  if [[ "$CHANNEL" == "release" && "$ALLOW_DIRTY" -ne 1 ]]; then
    echo "working tree is dirty; commit or stash before a stable release (or pass --allow-dirty)" >&2
    exit 1
  fi
  echo "warning: working tree is dirty; CI builds the committed ref, not local files" >&2
fi

echo "dispatching: channel=$CHANNEL target=$TARGET ref=$REF bump=$BUMP"
ARGS=(-f "channel=$CHANNEL" -f "target=$TARGET" -f "bump=$BUMP")
if [[ -n "$VERSION" ]]; then
  ARGS+=(-f "version=$VERSION")
fi
gh workflow run release.yml --ref "$REF" "${ARGS[@]}"

if [[ "$WAIT" -eq 0 ]]; then
  echo "dispatched; open: https://github.com/MisRivers/DouyinLiveRecorder/actions/workflows/release.yml"
  exit 0
fi

RUN_ID=""
for _ in $(seq 1 15); do
  sleep 3
  RUN_ID="$(gh run list --workflow release.yml --branch "$REF" --event workflow_dispatch \
    --limit 1 --json databaseId --jq '.[0].databaseId // empty' 2>/dev/null || true)"
  if [[ -n "$RUN_ID" ]]; then
    break
  fi
done
if [[ -z "$RUN_ID" ]]; then
  echo "could not find the dispatched run; open the Actions page:"
  echo "https://github.com/MisRivers/DouyinLiveRecorder/actions/workflows/release.yml"
  exit 1
fi

RUN_URL="$(gh run view "$RUN_ID" --json url --jq '.url')"
echo "run: $RUN_URL"
if ! gh run watch "$RUN_ID" --exit-status --interval 10 >/dev/null; then
  echo "release failed: $RUN_URL" >&2
  gh run view "$RUN_ID" --json conclusion --jq '.conclusion' >&2 || true
  exit 1
fi

echo "release succeeded: $RUN_URL"
if [[ "$CHANNEL" == "release" || "$TARGET" != "docker" ]]; then
  echo "recent releases:"
  gh release list --limit 5 || true
fi
if [[ "$TARGET" != "windows" ]]; then
  echo "docker image: https://hub.docker.com/r/misrivers/dlr-webui/tags"
fi
