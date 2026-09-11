#!/bin/bash
set -e
echo "=== 0. 更新 WSL 仓库副本 ==="
cd /opt/securetrans-repo && git pull --ff-only origin main 2>&1 | tail -1
echo "=== 1. 准备构建上下文 ==="
rm -rf /opt/ci-build && mkdir -p /opt/ci-build/wheelhouse
cp /opt/securetrans-repo/infra/docker/Dockerfile /opt/ci-build/
cp /opt/securetrans-repo/infra/docker/requirements.txt /opt/ci-build/requirements.txt
tar xzf /tmp/od.tar.gz -C /opt/ci-build/wheelhouse 2>/dev/null || {
  GW=$(ip route | awk '/default/{print $3; exit}')
  curl -sL --max-time 60 "http://${GW}:3000/openwrtadmin/SecureTrans/releases/download/v2.3.3/securetrans-offline-deps.tar.gz" -o /tmp/od2.tar.gz
  tar xzf /tmp/od2.tar.gz -C /opt/ci-build/wheelhouse
}
echo "wheelhouse whl 数: $(ls /opt/ci-build/wheelhouse/*.whl 2>/dev/null | wc -l)"
echo "=== 2. docker build ==="
docker build -t securetrans-ci:3.12 /opt/ci-build/ 2>&1 | tail -4
echo "=== 3. 验证 ==="
docker images securetrans-ci:3.12 --format "{{.Repository}}:{{.Tag}} {{.Size}}"
docker run --rm securetrans-ci:3.12 bash -c "
  python -c 'import flask,bcrypt,ldap3; print(\"flask\", flask.__version__)'
  echo 'requirements.txt 行数:'; wc -l < /wheelhouse/requirements.txt
  echo 'whl 数:'; ls /wheelhouse/*.whl 2>/dev/null | wc -l
"
echo "=== IMAGE-REBUILD-OK ==="
