# SecureTrans CI 隔离镜像（ADR-019）
# 用途：Gitea Actions 容器 job（act_runner docker:// 模式）与本地容器化 TDD 验证。
#       每次 job 拉起全新容器 + 全新 /data 数据目录，实现"干净环境 + 新配置 + 新数据"。
# 构建（Windows 侧联网 Docker Desktop 或 WSL docker）：
#   docker build -f Dockerfile -t securetrans-ci:3.12 .   ← 构建上下文 = 本目录（infra/docker）
# 依赖：requirements.txt + wheelhouse/（由 packages/securetrans-offline-deps.tar.gz 解压而来，
#       即 `tar xzf packages/securetrans-offline-deps.tar.gz -C infra/docker/` 生成 wheelhouse/）。
# 注意：本 Dockerfile（CI 镜像）与 Dockerfile.run（运行镜像）构建上下文不同——
#       Dockerfile.run COPY src/、packages/ 相对仓库根；本文件 COPY requirements.txt、wheelhouse/ 相对本目录。

# kaniko 方案已废弃（ADR-038-2 修订 2026-09-15）：kaniko v1.23.2/v1.24.0 在本地 Debian bookworm 宿主
#   (glibc 2.36，工具链被升级污染至要求 GLIBC_2.38) 上构建 Debian apt postinst 镜像失败
#   （ca-certificates/procps postinst 报 GLIBC_2.38 not found）。改为：release job 容器内 docker CLI
#   + 宿主 docker.sock（act_runner container.options 挂载），直接调用本地 WSL docker daemon 构建，
#   runc 完整隔离，无 kaniko 快照/glibc 缺陷；docker.sock 逃逸风险按"可信代码模型"接受（ADR-038-2）。
FROM python:3.12-slim

# openssh-client/rsync/jq：CD 部署（ADR-024，经 SSH 推送生产服务器，容器直连内网 22 端口）
# docker-ce-cli：release job 经宿主 docker.sock 构建运行镜像（ADR-038-2 修订，官方静态 CLI 轻量）
# 非交互 + conffile force：与 Dockerfile.run 同策略（docker/kaniko 双构建稳定，防 dpkg 交互卡死）
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl git ca-certificates procps openssh-client rsync jq gnupg \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/docker.gpg] https://download.docker.com/linux/debian bookworm stable" > /etc/apt/sources.list.d/docker.list \
    && DEBIAN_FRONTEND=noninteractive apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" \
        docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

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
