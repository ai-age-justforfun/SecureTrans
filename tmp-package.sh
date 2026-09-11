#!/bin/bash
set -e
cd /opt/securetrans-repo
echo "=== 1. 强制对齐 main ==="
git fetch origin 2>&1 | tail -2
git reset --hard origin/main 2>&1 | tail -2
git clean -fdx -- packages/ offline-python/ 2>/dev/null || true
git reset --hard origin/main 2>&1 | tail -1
echo "=== 2. 版本确认 ==="
grep -m1 'APP_VERSION = ' src/app.py
grep -m1 'const APP_VERSION' src/static/index.html
echo "=== 3. RPM 数量 ==="
ls offline-python/*.rpm 2>/dev/null | wc -l
echo "=== 4. 构建发布包 ==="
bash infra/package.sh 2>&1 | tail -6
echo "=== 5. 产物 ==="
ls -la packages/*.tar.gz 2>/dev/null
echo "DONE"
