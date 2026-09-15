# SecureTrans CI 隔离镜像（ADR-019）
# 用途：Gitea Actions 容器 job（act_runner docker:// 模式）与本地容器化 TDD 验证。
#       每次 job 拉起全新容器 + 全新 /data 数据目录，实现"干净环境 + 新配置 + 新数据"。
# 构建（Windows 侧联网 Docker Desktop 或 WSL docker）：
#   docker build -f infra/docker/Dockerfile -t securetrans-ci:3.12 .
# 依赖：infra/docker/wheelhouse/（由 packages/securetrans-offline-deps.tar.gz 解压而来）
# 注意：构建上下文 = 仓库根（COPY requirements.txt / COPY wheelhouse/ 均相对根）。

# kaniko executor（ADR-038-2 无特权镜像构建）：从官方镜像固化静态二进制到 CI 镜像，
#   release job 直接调用 /usr/local/bin/executor（无需下载、无需 docker daemon、无特权）。
#   gcr.io 拉取需构建机联网；固化后 CI 每次运行零外部下载。
FROM gcr.io/kaniko-project/executor:v1.24.0 AS kaniko

FROM python:3.12-slim

# openssh-client/rsync/jq：CD 部署（ADR-024，经 SSH 推送生产服务器，容器直连内网 22 端口）
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl git ca-certificates procps openssh-client rsync jq \
    && rm -rf /var/lib/apt/lists/*

# kaniko executor（静态二进制，COPY 自官方镜像；版本由镜像 tag v1.24.0 固定）
COPY --from=kaniko /kaniko/executor /usr/local/bin/executor
RUN chmod +x /usr/local/bin/executor

WORKDIR /workspace

# 离线 wheelhouse（与生产离线包同一来源，保证依赖一致性）
# ADR-020 归一化：wheelhouse 保留在镜像内作为 CI 构建工具链——
#   package job 直接从 /wheelhouse 生成 offline-deps 发布包（无需宿主共享目录），
#   实现"镜像自包含 + 每次 CI 干净环境"（旧镜像 fallback：从 Gitea Release 下载 offline-deps）
# 构建上下文准备（wheelhouse 被 gitignore，由 packages/securetrans-offline-deps.tar.gz 解压生成）：
#   mkdir -p infra/docker/wheelhouse && tar xzf packages/securetrans-offline-deps.tar.gz -C infra/docker/
# requirements.txt 由仓库跟踪（依赖清单单一来源，与 src/requirements.txt 一致）
COPY requirements.txt /wheelhouse/requirements.txt
COPY wheelhouse/ /wheelhouse/
RUN python -m venv /venv \
    && /venv/bin/pip install --no-index --find-links /wheelhouse -r /wheelhouse/requirements.txt \
    && rm -rf /root/.cache/pip

ENV PATH="/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
