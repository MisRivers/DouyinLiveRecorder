# LiveRecorder Web UI v1.1.1

自托管直播录制管理端，支持 40+ 平台、Web 管理界面、Docker 多架构镜像与 Windows 桌面端。

## 本次更新

- 新增可选 `streamget` 解析后端，用于接入比 DLR 更新的平台取流实现。
- streamget 默认开启（Docker 与 Windows EXE 实例统一生效），对全部 streamget 支持平台优先解析；超时、网络、Cookie、Node、空流地址等异常自动回退 DLR，不会阻断录制。
- 新增 `scripts/diagnose_stream.py`，可对同一房间同时运行 DLR 与 streamget，比较开播状态、主播、流地址、耗时与错误码。
- 同一平台连续失败后进入冷却，避免反复请求失败平台。
- 保留 v1.1.0 的桌面端账号重置、系统托盘、Docker 标签清理与 beta 版本递增能力。

## Docker

```bash
docker pull misrivers/dlr-webui:1.1.1
docker pull misrivers/dlr-webui:latest
```

多架构镜像支持 `linux/amd64` 与 `linux/arm64`。升级时保留 `config/`、`data/`、`downloads/`、`logs/` 挂载目录。

## Windows

下载 `DouyinLiveRecorderUI-1.1.1-windows-x64.zip`，解压后运行 `DouyinLiveRecorderUI.exe`。首次启动缺少 FFmpeg 时可自动下载。数据保存在程序目录的 `config/`、`data/`、`downloads/`、`logs/`。

## 升级说明

- 从 1.1.0 升级时，用新镜像或新 EXE 替换即可，数据库会在启动时自动迁移。
- 升级前建议备份 `config/` 与 `data/`。
- streamget 默认已开启；如需排查，可在“系统配置 → 录制设置”中临时关闭。
- streamget 的部分平台依赖 Node.js；Docker 镜像已内置，Windows 需要自行安装。

## 校验

Windows 压缩包与 Docker 镜像信息见本 Release 资产中的 `sha256sums.txt`、`docker-info.json` 与 `windows-info.json`。
