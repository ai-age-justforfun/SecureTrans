#!/bin/bash
# ============================================================
# SecureTrans 容器内 TDD 全量测试入口（ADR-019 CI 隔离）
# 供：Gitea Actions 容器 job（docker://securetrans-ci:3.12）与本地容器验证
#     docker run --rm -v <项目>:/workspace -w /workspace securetrans-ci:3.12 bash infra/ci_test.sh
# 特点（相对宿主 verify.sh）：
#   - 无 systemd：直接后台 gunicorn（loopback），trap 清理
#   - 干净数据：/data（每次容器销毁即清，无版本/数据残留）
#   - 零工作区污染：配置全部经环境变量注入（app.py 12-Factor：env 优先于 .env），
#     不写 src/.env；仅 /data（容器内）与 gunicorn 日志（/data）产生文件
# ============================================================
set -euo pipefail

# act_runner 容器 job 通过 GITHUB_WORKSPACE 指向工作区（本地 docker run 验证用 /workspace）
# host 网络模式下需显式 clone（act_runner 容器模式不做自动 checkout）
WS="${GITHUB_WORKSPACE:-/workspace}"
cd "$WS"
if [ ! -f src/app.py ]; then
    echo "工作区无代码，显式 clone（host 网络 → localhost:3000 = Gitea）..."
    rm -rf "$WS" && mkdir -p "$WS"
    git clone --depth 1 http://localhost:3000/openwrtadmin/SecureTrans.git "$WS"
    cd "$WS"
fi
[ -f src/app.py ] || { echo "工作区缺少 src/app.py，当前目录: $(pwd)"; ls -la; exit 1; }
DATA_ROOT="${CI_DATA_ROOT:-/data}"
mkdir -p "$DATA_ROOT"

echo "[1/4] 注入干净配置（环境变量，不写 .env）..."
export SECURETRANS_DATA="$DATA_ROOT"
export NAS_ROOT="$DATA_ROOT"
export ENV_ROLE="test"                # test=允许全量写测试；prod=写测试被 fail-safe 拒绝
export APP_STAGE="${CI_APP_STAGE:-beta}"
export RESET_PASSWORD="${CI_RESET_PASSWORD:-Init@123456}"
export SECRET_KEY="securetrans-ci-container-secret"
export MAX_FILE_SIZE_MB="800"
export HOST="127.0.0.1"
export PORT="${CI_PORT:-18000}"          # host 网络下避开宿主 securetrans:8000
echo "  DATA_ROOT=$DATA_ROOT | ENV_ROLE=$ENV_ROLE | APP_STAGE=$APP_STAGE | PORT=$PORT"

echo "[2/4] 启动服务（容器内 gunicorn，loopback）..."
(cd src && /venv/bin/gunicorn -b 127.0.0.1:${PORT} -w 1 --threads 4 app:app >"$DATA_ROOT/gunicorn.log" 2>&1) &
GUNI_PID=$!
trap 'kill $GUNI_PID 2>/dev/null || true' EXIT
for i in $(seq 1 30); do
    curl -sf http://127.0.0.1:${PORT}/api/health >/dev/null 2>&1 && break
    sleep 1
done
curl -sf http://127.0.0.1:${PORT}/api/health || { echo "服务未就绪"; tail -20 "$DATA_ROOT/gunicorn.log"; exit 1; }

echo "[3/4] 全量 TDD（test_api.py，含 ADR-017 门控 + ADR-018 计数门禁）..."
BASE_URL="http://127.0.0.1:${PORT}" NAS_ROOT="$DATA_ROOT" \
RESET_PASSWORD="$RESET_PASSWORD" ENV_ROLE="test" \
/venv/bin/python tests/test_api.py

echo "[4/4] 容器内测试完成（/data 随容器销毁，工作区零残留）"
