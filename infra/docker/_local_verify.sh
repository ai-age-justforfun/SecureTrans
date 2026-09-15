#!/usr/bin/env bash
# 本地容器运行验证（WSL docker）：18000 端口 + mock AD + 临时数据
set -u
docker rm -f st-test >/dev/null 2>&1 || true
docker run -d --name st-test -p 18000:8000 \
  -e AD_MOCK_MODE=true -e RESET_PASSWORD=Init@123456 -e SECURETRANS_DATA=/data -e NAS_ROOT=/nas \
  securetrans:v2.7.0-dev
echo "--- 等待健康 ---"
for i in $(seq 1 15); do
  sleep 2
  H=$(curl -fsS http://127.0.0.1:18000/api/health 2>/dev/null || true)
  if [ -n "$H" ]; then echo "health: $H"; break; fi
done
echo "--- 登录冒烟 ---"
curl -sS -X POST http://127.0.0.1:18000/api/auth/login -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"Init@123456"}' | head -c 200
echo ""
echo "--- 容器内 AD 工具检查 ---"
docker exec st-test bash -c 'command -v ldapsearch && echo LDAP_TOOLS_OK'
echo "--- 进程/端口 ---"
docker exec st-test bash -c 'ps aux | grep gunicorn | grep -v grep | head -2'
echo "--- 镜像大小 ---"
docker images securetrans:v2.7.0-dev --format '{{.Size}}'
