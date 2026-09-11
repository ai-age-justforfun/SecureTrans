#!/bin/bash
# 重建 securetrans-ci:3.12（ADR-020 镜像自包含）
# 方案：WSL 内 Linux 原生路径 /opt/securetrans-repo（git clone，摆脱 /mnt/c 大目录）
set -e
GW=$(ip route | awk '/default/{print $3; exit}')
echo "=== 1. WSL 侧仓库副本（Linux 原生路径）==="
if [ ! -d /opt/securetrans-repo/.git ]; then
  rm -rf /opt/securetrans-repo
  git clone --depth 1 "http://${GW}:3000/openwrtadmin/SecureTrans.git" /opt/securetrans-repo
  echo "clone 完成"
else
  cd /opt/securetrans-repo && git pull --ff-only origin main 2>&1 | tail -1
  echo "已更新"
fi
ls /opt/securetrans-repo/infra/docker/Dockerfile
echo "=== 2. 准备构建目录 ==="
rm -rf /opt/ci-build && mkdir -p /opt/ci-build
cp /opt/securetrans-repo/infra/docker/Dockerfile /opt/ci-build/
echo "=== 3. wheelhouse（Release offline-deps 解压）==="
curl -sL --max-time 60 "http://${GW}:3000/openwrtadmin/SecureTrans/releases/download/v2.3.3/securetrans-offline-deps.tar.gz" -o /tmp/od.tar.gz
ls -la /tmp/od.tar.gz
cd /opt/ci-build
tar xzf /tmp/od.tar.gz
echo "wheelhouse 前 8 项:"
ls wheelhouse/ | head -8
echo "requirements: $(wc -l < wheelhouse/requirements.txt) 行"
echo "=== 4. docker build（保留 /wheelhouse）==="
docker build -t securetrans-ci:3.12 /opt/ci-build/ 2>&1 | tail -6
echo "=== 5. 验证 ==="
docker images securetrans-ci:3.12
docker run --rm securetrans-ci:3.12 bash -c "python -c 'import flask,bcrypt; print(\"flask\", flask.__version__)' && ls /wheelhouse/*.whl | wc -l && echo WHEELHOUSE-PRESENT"
echo "=== IMAGE-REBUILD-OK ==="
