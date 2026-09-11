#!/bin/bash
set -e
echo "=== 1. 正确解压 offline-deps（在 /opt/ci-build 解出 wheelhouse/）==="
rm -rf /opt/ci-build/wheelhouse
cd /opt/ci-build
tar xzf /tmp/od.tar.gz
echo "wheelhouse whl 数: $(ls /opt/ci-build/wheelhouse/*.whl 2>/dev/null | wc -l)"
echo "requirements.txt: $(ls /opt/ci-build/wheelhouse/requirements.txt 2>/dev/null || echo '缺失(将从仓库复制)')"
if [ ! -f /opt/ci-build/wheelhouse/requirements.txt ]; then
  cp /opt/ci-build/requirements.txt /opt/ci-build/wheelhouse/requirements.txt
  echo "已复制仓库 requirements.txt"
fi
echo "=== 2. docker build ==="
cd /opt/ci-build
docker build -t securetrans-ci:3.12 /opt/ci-build/ 2>&1 | tail -3
echo "=== 3. 验证 ==="
docker images securetrans-ci:3.12 --format "{{.Repository}}:{{.Tag}} {{.Size}}"
docker run --rm securetrans-ci:3.12 bash -c "
  python -c 'import flask,bcrypt,ldap3; print(\"flask\", flask.__version__)'
  echo 'req lines:'; wc -l < /wheelhouse/requirements.txt
  echo 'whl count:'; ls /wheelhouse/*.whl 2>/dev/null | wc -l
"
echo "=== IMAGE-REBUILD-OK ==="
