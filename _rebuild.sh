#!/bin/bash
# 重建 securetrans-ci:3.12（ADR-020：保留 /wheelhouse 构建工具链，镜像自包含）
# WSL 内 Linux 原生路径执行（不依赖 /mnt/c 大目录）
set -e
echo "=== 1. 准备构建目录 ==="
rm -rf /opt/ci-build && mkdir -p /opt/ci-build
cp /workspace/infra/docker/Dockerfile /opt/ci-build/
echo "Dockerfile 就位"
echo "=== 2. wheelhouse（从 Gitea Release 拉 offline-deps 解压）==="
GW=$(ip route | awk '/default/{print $3; exit}')
echo "网关: ${GW}"
curl -sL --max-time 60 "http://${GW}:3000/openwrtadmin/SecureTrans/releases/download/v2.3.3/securetrans-offline-deps.tar.gz" -o /tmp/od.tar.gz
ls -la /tmp/od.tar.gz
cd /opt/ci-build
tar xzf /tmp/od.tar.gz
echo "wheelhouse 内容（前 8 项）:"
ls wheelhouse/ | head -8
wc -l wheelhouse/requirements.txt
echo "=== 3. docker build ==="
cd /opt/ci-build
docker build -t securetrans-ci:3.12 /opt/ci-build/ 2>&1 | tail -5
echo "=== 4. 确认 ==="
docker images securetrans-ci:3.12
docker run --rm securetrans-ci:3.12 python -c "import flask,sqlalchemy,bcrypt; print('依赖 OK:', flask.__version__)"
echo "=== IMAGE-REBUILD-OK ==="
