# LiveRecorder Web UI v1.1.0

自托管直播录制管理端，支持 40+ 平台、Web 管理界面、Docker 多架构镜像与 Windows 桌面端。

## 本次更新

- 桌面端新增“重置账号”：可同时重置管理员用户名与密码，重置后自动撤销全部网页登录会话。
- 桌面端关闭窗口可选择后台继续运行，并驻留 Windows 系统托盘；托盘菜单支持显示窗口、打开管理页面、重置账号与退出。
- 关闭确认框按钮改为高对比度实心按钮，后台运行与退出操作更清晰。
- Docker 镜像新增 `reset_account.py`，可在容器内重置管理员账号，不依赖网页登录。
- Docker 标签策略调整：不再发布 `sha-*` 标签；beta 与 stable 版本各保留最新 5 个；正式版发布后清理 1.1.0-beta 镜像。
- beta 版本号改为按 Docker Hub 最新 beta 与 Git 标签递增，每次构建唯一。

## Docker

```bash
docker pull misrivers/dlr-webui:1.1.0
docker pull misrivers/dlr-webui:latest
```

多架构镜像支持 `linux/amd64` 与 `linux/arm64`。升级时保留 `config/`、`data/`、`downloads/`、`logs/` 挂载目录。

重置账号：

```bash
docker exec -it -u dlr dlr-webui python reset_account.py
```

## Windows

下载 `DouyinLiveRecorderUI-1.1.0-windows-x64.zip`，解压后运行 `DouyinLiveRecorderUI.exe`。首次启动缺少 FFmpeg 时可自动下载。数据保存在程序目录的 `config/`、`data/`、`downloads/`、`logs/`。

## 升级说明

- 从 1.1.0-beta 升级时，用新镜像或新 EXE 替换即可，数据库会在启动时自动迁移。
- 升级前建议备份 `config/` 与 `data/`。
- 账号重置会撤销所有登录会话，请在重置后重新登录。

## 校验

Windows 压缩包与 Docker 镜像信息见本 Release 资产中的 `sha256sums.txt`、`docker-info.json` 与 `windows-info.json`。
