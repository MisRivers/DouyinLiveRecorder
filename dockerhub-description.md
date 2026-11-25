<!-- 短描述（填到 Docker Hub 的 Description 简短描述字段，UTF-8 不超过 100 字节）：
自托管直播录制管理端：多平台、Web/手机管理，多架构 Docker 镜像。
-->

# LiveRecorder Web UI

GitHub 仓库：<https://github.com/MisRivers/DouyinLiveRecorder>

Docker 镜像：`misrivers/dlr-webui:latest`

一个面向自托管场景的直播录制管理端，基于 [ihmily/DouyinLiveRecorder](https://github.com/ihmily/DouyinLiveRecorder) 改造而来。镜像内置 Web 管理端、FastAPI 后端、FFmpeg、Node.js 运行时与前端静态文件，拉取后即可在浏览器或手机端管理直播录制。

> **重要声明**：本项目仅用于个人学习、技术交流与自托管实验，不提供商业化录制、代录、内容分发或绕过平台限制的能力。直播内容版权归主播、平台或权利人所有，录制行为本身不代表获得授权。使用前请完整阅读[合规使用与法律风险](#合规使用与法律风险)，并自行确保行为符合平台服务条款与当地法律法规。

## 镜像信息

| 项目 | 说明 |
| --- | --- |
| 镜像 | `misrivers/dlr-webui:latest` |
| 架构 | `linux/amd64`、`linux/arm64` |
| 容器端口 | `8642` |
| 健康检查 | `GET /api/system/health` |
| 内置组件 | FFmpeg、ffprobe、Node.js、前端静态文件 |
| 数据目录 | `/app/data`、`/app/config`、`/app/downloads`、`/app/logs` |
| 运行用户 | 通过 `PUID` / `PGID` 映射，默认 `1000:1000` |

镜像不包含本地 `config/`，首次启动由应用生成默认配置，避免把本机 Cookie、Token 打入镜像。

## 主要功能

- 桌面端与手机端自适应的 Web 管理端；
- 录制状态、正在录制、等待开播与异常提示；
- 直播间增删改查、快速添加、导入导出、排序与分页；
- 房间级每周录制计划，支持多时段与跨天时段；
- 录制文件按主播分组浏览、排序、批量删除与批量转码；
- 内置播放器支持 MP4、M4A、MP3、FLV、TS；
- 开播、关播、开始录制、录制结束、转码完成、录制异常六类通知模板；
- 微信、钉钉、邮箱、Telegram、BARK、NTFY、PushPlus 推送渠道；
- 平台类型启用/禁用管理；
- WebSocket 实时刷新，断线自动回退轮询；
- 录制中断后 30 秒内自动重连；
- 登录失败锁定、CSRF 校验、scrypt 口令、审计日志与敏感信息脱敏。

## 界面预览

| 录制状态 | 直播间管理 |
| --- | --- |
| ![录制状态](https://raw.githubusercontent.com/MisRivers/DouyinLiveRecorder/feature/web-ui/.screenshots/02-live-status.png) | ![直播间管理](https://raw.githubusercontent.com/MisRivers/DouyinLiveRecorder/feature/web-ui/.screenshots/05-rooms.png) |

| 录制文件播放 | 系统配置 |
| --- | --- |
| ![录制文件播放](https://raw.githubusercontent.com/MisRivers/DouyinLiveRecorder/feature/web-ui/.screenshots/06-player.png) | ![系统配置](https://raw.githubusercontent.com/MisRivers/DouyinLiveRecorder/feature/web-ui/.screenshots/07-settings.png) |

更多截图与完整说明见 [GitHub README](https://github.com/MisRivers/DouyinLiveRecorder/blob/feature/web-ui/README.md)。

## 快速开始

### 方式一：docker run

```bash
docker run -d \
  --name dlr-webui \
  --init \
  -p 8642:8642 \
  -e TZ=Asia/Shanghai \
  -e PUID=1000 \
  -e PGID=1000 \
  -v "$PWD/config:/app/config" \
  -v "$PWD/downloads:/app/downloads" \
  -v "$PWD/data:/app/data" \
  -v "$PWD/logs:/app/logs" \
  --restart unless-stopped \
  misrivers/dlr-webui:latest
```

### 方式二：Docker Compose

```yaml
services:
  dlr-webui:
    image: misrivers/dlr-webui:latest
    container_name: dlr-webui
    init: true
    ports:
      - "${DLR_PORT:-8642}:8642"
    environment:
      TZ: "Asia/Shanghai"
      DLR_PORT: "8642"
      PUID: "1000"
      PGID: "1000"
    volumes:
      - ./config:/app/config
      - ./downloads:/app/downloads
      - ./data:/app/data
      - ./logs:/app/logs
    restart: unless-stopped
    stop_grace_period: 60s
```

```bash
docker compose pull
docker compose up -d
```

### 首次访问

```text
http://<服务器或 NAS 的 IP>:8642
```

首次打开会进入“创建管理员”页面：

- 用户名至少 3 位；
- 密码至少 10 位，且必须同时包含字母与数字；
- 创建完成后自动登录；
- 登录失败 5 次会锁定 15 分钟。

如需修改宿主机端口：

```bash
DLR_PORT=9000 docker compose up -d
```

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DLR_PORT` | `8642` | Web 服务端口，容器内建议保持 8642 |
| `DLR_HOST` | `0.0.0.0` | 监听地址 |
| `DLR_DATA_DIR` | `/app/data` | SQLite、密钥、备份目录 |
| `DLR_CONFIG_DIR` | `/app/config` | `config.ini` / `URL_config.ini` 目录 |
| `DLR_DOWNLOAD_DIR` | `/app/downloads` | 录制文件目录 |
| `DLR_LOG_DIR` | `/app/logs` | 日志目录 |
| `DLR_SECRET_KEY` | 自动生成 | 会话密钥；未设置时写入 `data/secret.key` |
| `DLR_LOG_LEVEL` | `info` | 日志级别 |
| `DLR_TRUST_PROXY` | 未设置 | 仅在可信反向代理后设为 `1` |
| `DLR_DISABLE_WORKERS` | 未设置 | 设为 `1` 时只启动 Web，不启动录制/转码 Worker |
| `PUID` / `PGID` | `1000` | 容器运行用户与挂载目录属主 |
| `TZ` | `Asia/Shanghai` | 容器时区 |

## 数据卷

| 容器路径 | 用途 | 建议 |
| --- | --- | --- |
| `/app/data` | SQLite、密钥、备份 | 必须持久化 |
| `/app/config` | 生成的 ini 与备份 | 建议持久化 |
| `/app/downloads` | 录制文件 | 必须持久化 |
| `/app/logs` | 运行日志 | 建议持久化 |

未挂载这些目录时，重建容器会丢失数据库、配置、录制文件与日志。

## 端口、健康检查与停止

- 容器内固定监听 `8642`，宿主机端口可自行调整；
- 健康检查每 30 秒访问 `/api/system/health`，首次启动有 20 秒宽限期；
- `stop_grace_period: 60s` 用于等待录制收尾与 TS 转 MP4；
- 停止容器时会先请求录制引擎优雅停止，再终止 Worker；
- 强制删除容器可能导致当前录制文件未完成收尾。

## 录制与通知

### 运行模式

| 模式 | 行为 | 发送的事件 |
| --- | --- | --- |
| `只推送通知不录制 = 否` | 检测到开播后启动 FFmpeg 录制 | 开始录制、录制结束、转码完成、录制异常 |
| `只推送通知不录制 = 是` | 只检测开播/关播，不启动 FFmpeg | 开播、关播、拉流异常 |

### 录制计划

- 每个直播间可设置多个每周时间段；
- 支持跨天时段，例如 23:00 至次日 02:00；
- 时段外不检测、不录制，状态显示“计划外”；
- 留空表示全天检测。

### 通知模板

- 六类事件可独立开关；
- 标题与正文支持 `{主播}`、`{平台}`、`{标题}`、`{时间}`、`{时长}`、`{文件大小}`、`{错误原因}` 等变量；
- 推送渠道在“系统配置 → 推送配置”中选择；
- 发送失败会记录脱敏摘要，不保存完整 Webhook 或 Token。

## 升级、备份与迁移

### 升级

```bash
docker compose pull
docker compose up -d
```

数据库结构会在启动时自动迁移。跨大版本升级前，建议先停止容器并完整备份。

### 备份

需要备份：

- `data/`：SQLite、密钥、备份；
- `config/`：生成的配置与导出备份；
- `downloads/`：录制文件与字幕（按需）。

### 迁移

把上述目录复制到新机器，保持目录属主与 `PUID` / `PGID` 一致，再启动同一镜像即可。

## 安全部署建议

- 首次部署后立即修改管理员密码；
- 尽量只监听局域网或 VPN，不要直接暴露到公网；
- 公网访问必须使用 HTTPS 反向代理、访问控制与登录保护；
- 仅在使用可信反向代理时设置 `DLR_TRUST_PROXY=1`；
- 使用独立用户运行，避免 root；
- 限制 `data/`、`config/`、`downloads/`、`logs/` 的目录权限；
- 定期轮换平台 Cookie、Token 与推送 Webhook；
- 定期更新镜像与依赖；
- 定期检查日志、登录失败记录与磁盘剩余空间；
- 不要在截图、Issue、日志中暴露 Cookie、Token、密码或内网地址。

## 合规使用与法律风险

以下内容为风险提示，不构成法律意见。涉及具体权利义务时，请咨询专业律师。

### 项目定位

- 本项目是开源技术项目，仅用于个人学习、技术研究、自托管实验与自有内容归档；
- 本项目不是直播平台、录播平台、内容分发平台或商业代录服务；
- 本项目未获得任何直播平台的授权或背书；
- 本项目不提供平台账号、Cookie、付费内容、破解工具、去水印、DRM 绕过或地域限制绕过能力。

### 允许的使用场景

- 录制自己拥有著作权的直播内容；
- 已取得主播或权利人明确授权的录制与归档；
- 在遵守平台服务条款的前提下，进行个人离线留存、技术研究与功能测试；
- 在本地或受控网络环境中学习 Web、FFmpeg、FastAPI、Vue 等技术。

### 明确禁止的用途

- 盗录、传播或售卖他人付费直播、会员内容、课程、演唱会、赛事等受保护内容；
- 绕过 DRM、加密、付费墙、地域限制、反爬或平台访问控制；
- 未经同意录制他人隐私场景，或公开他人肖像、住址、联系方式等个人信息；
- 批量抓取、自动化骚扰、跟踪、偷拍偷录或其他侵犯隐私权的行为；
- 将录制内容二次剪辑、公开传播、商业使用，或用于诽谤、敲诈、色情及其他违法用途；
- 将本镜像包装为代录服务、内容站、下载站，或去除版权标识后对外分发；
- 任何违反平台服务条款、著作权法、个人信息保护法、网络安全法及当地法律的行为。

### 使用前合规清单

1. 确认你对目标直播拥有录制权，或已取得主播/权利人的明确授权；
2. 阅读并遵守目标平台的服务条款、robots 协议、API 规则与反爬政策；
3. 仅收集与录制目的直接相关的最少信息，不采集无关个人信息；
4. 为录制文件设置合理的保留期限，到期删除；
5. 不公开分享录制内容，不上传到公开网盘、视频站或社交平台；
6. 妥善保护 Cookie、Token、账号密码等敏感凭据；
7. 如需对外提供服务，先完成法律与合规评估；
8. 如当地法律要求告知或取得同意，请先履行相应程序。

### 责任边界

- 使用者应自行判断并承担使用本镜像产生的一切法律与合规责任；
- 项目作者与贡献者不对任何录制内容、数据泄露、账号封禁、法律责任或间接损失负责；
- 本项目不托管、不代理、不分发任何直播或录制内容；
- 权利人如认为仓库或镜像描述中的示例、文档、截图侵犯其权利，可通过 GitHub Issue 联系处理；
- 本镜像按“现状”提供，不提供任何明示或暗示担保，也不承诺持续维护或技术支持。

## 常见问题

### 端口被占用或页面打不开

- 检查宿主机端口映射与防火墙；
- 确认容器处于 `running` 状态；
- 查看 `docker logs dlr-webui` 与 `logs/webui.log`。

### 提示未找到 ffmpeg

镜像已内置 FFmpeg 与 ffprobe，通常不需要额外安装。若使用源码运行，请自行安装或把二进制放入 `ffmpeg/`。

### 录制文件没有出现

- 检查设置中的保存路径；
- 在录制文件页点击“重新扫描目录”；
- 确认录制 Worker 正在运行；
- 检查磁盘剩余空间与目录权限。

### 没有收到通知

- 先在“推送配置”中发送测试消息；
- 确认对应事件的通知模板已开启；
- 开播/关播通知只在“只推送通知不录制 = 是”时发送；
- 自建 Webhook 需使用受信任的 HTTPS 证书。

### WebSocket 显示轮询

反向代理需要转发 `/api/ws/events` 的 WebSocket 连接；页面会自动回退轮询，不影响基本使用。

### 容器权限问题

设置 `PUID` / `PGID` 与宿主机目录属主一致，并确认四个挂载目录可写。初次启动会修正属主，大目录可能耗时。

### 可以录制他人的直播吗？

不能仅凭“公开可见”就认为可以录制。公开直播同样可能受著作权、肖像权、隐私权与平台条款保护。请仅在取得授权、属于合理使用范围或法律明确允许的情况下录制。

### 镜像会把数据上传到云端吗？

不会。数据保存在本地 SQLite、配置文件和录制目录中。只有你主动配置的推送渠道会接收通知内容。

### 如何彻底删除数据？

停止并删除容器后，删除 `data/`、`config/`、`downloads/`、`logs/` 即可。删除前请确认已完成备份。

## 维护与支持

- 本项目由个人维护，按“尽力而为”原则处理 Issue，不提供 SLA、商业支持或法律咨询；
- 提交问题前请先搜索历史 Issue，并提供可复现步骤、运行环境与脱敏后的日志；
- 安全漏洞请通过私下渠道联系维护者，不要在公开 Issue 中披露敏感细节；
- 不接受任何绕过平台限制、破解、盗录或侵犯隐私的功能请求；
- 项目可能因上游接口变化、平台风控或法律要求而调整功能或停止维护。

## 上游与许可

本项目基于 [ihmily/DouyinLiveRecorder](https://github.com/ihmily/DouyinLiveRecorder) 改造，保留其平台解析、录制与 FFmpeg 相关能力。上游项目采用 MIT License，Copyright (c) 2025 Hmily。

本仓库新增的 Web UI、后端管理、Docker 与文档代码同样遵循 MIT License，详见 [LICENSE](https://github.com/MisRivers/DouyinLiveRecorder/blob/feature/web-ui/LICENSE)。

使用、修改或分发本项目时，请保留原始版权声明与许可文本，并自行承担合规责任。

## 免责声明

本镜像及文档仅用于技术学习、研究与自托管实验，不构成任何形式的授权、许可或法律意见。项目作者与贡献者不拥有直播内容的相关权利，也不对使用者的录制、存储、传播或商业使用行为负责。

使用者应自行确保：

- 已获得录制、存储与使用相关内容所需的全部授权；
- 行为符合目标平台的服务条款、API 规则与反爬政策；
- 行为符合著作权法、个人信息保护法、隐私权、肖像权及当地其他法律法规；
- 录制内容仅用于合法目的，并采取必要的访问控制与保留期限管理。

因使用或无法使用本镜像而产生的任何直接或间接损失、法律责任、账号封禁、数据泄露或第三方索赔，项目作者与贡献者均不承担责任。本镜像按“现状”提供，不提供任何明示或暗示担保。

如权利人认为本镜像描述或相关文档、截图侵犯其合法权益，请通过 GitHub Issue 联系，本项目会配合处理。
