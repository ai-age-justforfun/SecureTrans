#!/bin/bash
set -e
echo "=== 0. 旧镜像 pytest 检查 ==="
docker run --rm securetrans-ci:3.12 bash -c "pip list 2>/dev/null | grep -iE 'pytest|flask|bcrypt' || echo '(旧镜像无这些包?)'" || true
echo "=== 1. 补齐 wheelhouse/requirements.txt ==="
ls /opt/securetrans-repo/infra/docker/wheelhouse/requirements.txt
cp /opt/securetrans-repo/infra/docker/wheelhouse/requirements.txt /opt/ci-build/wheelhouse/
echo "--- requirements.txt 内容 ---"
cat /opt/ci-build/wheelhouse/requirements.txt
echo "=== 2. docker build（保留 /wheelhouse）==="
cd /opt/ci-build
docker build -t securetrans-ci:3.12 /opt/ci-build/ 2>&1 | tail -4
echo "=== 3. 验证镜像 ==="
docker images securetrans-ci:3.12 --format "{{.Repository}}:{{.Tag}} {{.Size}}"
docker run --rm securetrans-ci:3.12 bash -c "
  python -c 'import flask,bcrypt; print(\"flask\", flask.__version__)'
  echo 'wheelhouse whl 数:'; ls /wheelhouse/*.whl 2>/dev/null | wc -l
  echo 'requirements.txt:'; cat /wheelhouse/requirements.txt | wc -l
  echo 'pytest:'; pip list 2>/dev/null | grep -i pytest || echo '(无 pytest)'
"
echo "=== IMAGE-REBUILD-OK ==="
