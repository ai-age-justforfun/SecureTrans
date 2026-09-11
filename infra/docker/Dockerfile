# SecureTrans CI 隔离镜像（ADR-019）
# 用途：Gitea Actions 容器 job（act_runner docker:// 模式）与本地容器化 TDD 验证。
#       每次 job 拉起全新容器 + 全新 /data 数据目录，实现"干净环境 + 新配置 + 新数据"。
# 构建（Windows 侧联网 Docker Desktop）：
#   docker build -f infra/docker/Dockerfile -t securetrans-ci:3.12 .
# 依赖：infra/docker/wheelhouse/（由 packages/securetrans-offline-deps.tar.gz 解压而来）
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl git ca-certificates procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# 离线 wheelhouse（与生产离线包同一来源，保证依赖一致性）
# ADR-020 归一化：wheelhouse 保留在镜像内作为 CI 构建工具链——
#   package job 直接从 /wheelhouse 生成 offline-deps 发布包（无需宿主共享目录），
#   实现"镜像自包含 + 每次 CI 干净环境"（旧镜像 fallback：从 Gitea Release 下载 offline-deps）
COPY wheelhouse/ /wheelhouse/
RUN python -m venv /venv \
    && /venv/bin/pip install --no-index --find-links /wheelhouse -r /wheelhouse/requirements.txt \
    && rm -rf /root/.cache/pip

ENV PATH="/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
