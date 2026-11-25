# 发布流程

本仓库只保留一个发布工作流：[release.yml](.github/workflows/release.yml)。日常发布通过 4 条命令完成，Docker 与 Windows 使用同一套版本号规则和构建内容标准。

## 四条命令

```bash
bash scripts/release.sh beta docker      # Docker 测试版
bash scripts/release.sh beta windows     # Windows 测试版
bash scripts/release.sh release docker   # Docker 正式版
bash scripts/release.sh release windows  # Windows 正式版
```

需要一次同时构建两个端时：

```bash
bash scripts/release.sh beta both
bash scripts/release.sh release both
```

常用参数：

```bash
--ref <branch>            指定构建分支，默认当前分支
--bump patch|minor|major  正式版版本递增方式，默认 patch
--version 1.2.3           指定版本，跳过自动编号
--no-wait                 只触发，不等待执行结果
--allow-dirty             允许工作区有未提交修改（不推荐）
```

命令会触发 GitHub Actions、等待运行结束，并在失败时返回非零退出码。正式版建议使用 `both`，或先执行 `release docker`、再执行 `release windows`，两条命令会自动共享同一个版本号。

### beta 分支自动构建

推送到 `beta` 分支会自动运行 `release.yml`，固定使用 `channel=beta`、`target=both`，同时构建 Docker 与 Windows 测试版：

```bash
git push github feature/web-ui:beta
```

每次推送都会生成新的 `1.1.0-beta.N` 版本：Docker 推送 `beta` 标签，Windows 更新滚动预发布 `webui-v1.1.0-beta`。适合连续调试，不需要执行 `release.sh`。

## 版本规则

`VERSION` 文件保存下一个测试版基线，例如 `1.1.0`。

| 通道 | 版本示例 | 自动规则 |
| --- | --- | --- |
| beta | `1.1.0-beta.1` | 读取 `VERSION`，N 从已有 `webui-v1.1.0-beta.N` 标签与 Docker Hub 最新 beta 版本中取较大值递增，每次构建唯一 |
| stable | `1.1.0` | 有正式标签时按 patch/minor/major 递增；没有正式标签时使用 `VERSION` |

WebUI 的 Release 标签统一使用 `webui-v` 前缀（例如 `webui-v1.1.0`），避免与上游项目的 `v4.x` 标签冲突。GitHub Release 标题仍显示为 `v1.1.0`。

正式版跨命令闭环：

1. `release docker` 创建草稿 Release `webui-v1.1.0`，上传 `docker-info.json`；
2. 此时不会发布，因为还缺 Windows 资产；
3. `release windows` 自动识别该草稿版本，构建后上传 Windows zip 与 `windows-info.json`；
4. 检查到两个标记资产都存在后，自动把 Release 从草稿转为正式版并设为 latest。

先执行 `release windows` 再执行 `release docker` 同样成立。若只执行其中一个端，Release 会保持草稿，避免发布不完整版本。

## 产物与标签

### Docker

镜像：`misrivers/dlr-webui`

| 通道 | 标签 |
| --- | --- |
| beta | `beta`、`1.1.0-beta.N` |
| stable | `latest`、`1.1.0` |

标签保留策略：

- `latest` 与 `beta` 永久保留；
- beta 版本标签只保留最新 5 个（`1.1.0-beta.N`）；
- stable 版本标签只保留最新 5 个（`1.1.0`）；
- 不再生成 `sha-<commit>` 标签，历史 `sha-*`、`feature-web-ui`、`amd64`、`arm64` 由发布任务自动删除；
- 自动清理需要 Docker Hub Token 具备 Delete 权限；权限不足时只输出警告，不影响发布。

镜像内写入 `/app/VERSION`，应用启动后显示对应版本。CI 会拉取 amd64 镜像启动容器并检查 `/api/system/health`。

### Windows

Windows 产物为 one-folder zip：

- stable：`DouyinLiveRecorderUI-1.1.0-windows-x64.zip`
- beta：Release 中固定资产名 `DouyinLiveRecorderUI-windows-x64-beta.zip`，每次覆盖，避免测试版资产无限累积

每个正式版 Release 还包含：

- `windows-info.json`
- `docker-info.json`
- `sha256sums.txt`

测试版使用滚动预发布 Release：`webui-v1.1.0-beta`，标题为 `v1.1.0 Beta`，每次构建更新说明和资产。

## 构建内容标准

统一原则：**只包含运行时代码和版本信息，绝不包含本机配置、账号凭据、录制数据、日志和开发产物。**

| 内容 | Docker | Windows | 说明 |
| --- | --- | --- | --- |
| `run_webui.py`、`webui/backend` | 包含 | 包含 | 服务端与桌面入口 |
| `src` | 包含 | 包含 | 上游取流逻辑 |
| `msg_push.py`、`pyproject.toml` | 包含 | 包含 | 通知与上游版本信息 |
| 前端构建产物 | 构建阶段生成 | 构建阶段生成 | 不提交、不复用本地 dist |
| `VERSION` | 构建参数写入镜像 | 构建后写入 dist | 版本唯一来源 |
| `config/`、`config.ini` | 排除 | 排除 | 首次运行自动生成，可能含 Cookie/Token |
| `data/`、`downloads/`、`logs/` | 排除 | 排除 | 运行时数据，通过卷挂载 |
| `.env`、`*.key`、`*.pem`、`cookies*` | 排除 | 排除 | 凭据 |
| `docs/`、`.aoci*`、`.git`、`.github` | 排除 | 排除 | 开发资料 |
| `node_modules`、`frontend/dist`、`build/`、`dist/` | 排除 | 排除 | 构建缓存与产物 |
| `ffmpeg.exe`、`ffprobe.exe` | 系统包安装 | 不打包 | Windows 首次运行下载或手动放置 |
| `webui/tests`、`.screenshots` | 排除 | 排除 | 测试与截图 |

执行检查：

```bash
python scripts/check_build_files.py
```

检查内容包括：

- Dockerfile 不允许 `COPY . /app`，必须显式复制运行时文件；
- `.dockerignore` 和 `.gitignore` 必须覆盖运行时目录与凭据；
- PyInstaller spec 不允许打包 `config/data/downloads/logs`；
- `VERSION` 必须同时被 Docker 和 Windows 构建读取；
- git 不得跟踪 `config/data/downloads/logs`。

CI 和 Windows 发布任务都会先执行该检查，不通过则拒绝构建。

## 前置条件

- 仓库 Secrets 已配置 `DOCKERHUB_USERNAME`、`DOCKERHUB_TOKEN`（或 `DOCKERHUB_PASSWORD`）；
- 本机已安装并登录 GitHub CLI：`gh auth login`；
- 触发分支包含 `.github/workflows/release.yml`；
- 正式版建议工作区干净；测试版也建议先提交，避免 CI 构建的不是本地最新代码。

## 回滚与清理

- 测试版 Docker 标签可单独删除，不影响 `latest`；
- 测试版 Release 为预发布，不会进入 `/releases/latest`；
- 正式版 Release 如发布错误，可在 GitHub 上删除 Release 与标签，再重新执行；
- Docker 正式版回滚可重新推送旧版本标签，或执行 `release docker --version <旧版本>`。
