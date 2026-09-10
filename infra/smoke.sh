#!/bin/bash
# ============================================================
# SecureTrans 生产环境只读冒烟验证脚本（ADR-017）
# 标准入口：生产部署验证 / 升级后冒烟 / CI 生产 job
# 特性：
#   1. 只执行 tests/test_api.py 的冒烟白名单组（SMOKE_MODE=1 → 仅组 24，allowlist 只读）
#   2. 不创建任何业务数据（health/登录/会话/查询/网络面模拟）
#   3. 即使误用 verify.sh 全量脚本，ENV_ROLE=prod 下写测试也会 fail-safe 拒绝
# 用法：bash smoke.sh [BASE_URL]
# 目录结构：infra/smoke.sh, tests/test_api.py
# ============================================================
set -euo pipefail

INSTALL_DIR="/opt/securetrans"
BASE_URL="${1:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_SCRIPT_PATH="$SCRIPT_DIR/../tests/test_api.py"

# 未显式指定 BASE_URL 时，从 .env HOST/PORT 自适应（与 verify.sh 同逻辑）
if [ -z "$BASE_URL" ]; then
    ENV_HOST=""
    ENV_PORT="8000"
    if [ -f "$INSTALL_DIR/.env" ]; then
        ENV_HOST=$(grep -E '^HOST=' "$INSTALL_DIR/.env" 2>/dev/null | cut -d= -f2 | tr -d '\r' | head -1 || true)
        ENV_PORT=$(grep -E '^PORT=' "$INSTALL_DIR/.env" 2>/dev/null | cut -d= -f2 | tr -d '\r' | head -1 || true)
        ENV_PORT="${ENV_PORT:-8000}"
    fi
    case "$ENV_HOST" in
        ""|0.0.0.0|127.0.0.1|localhost)
            BASE_URL="http://127.0.0.1:${ENV_PORT}" ;;
        *)
            BASE_URL="http://${ENV_HOST}:${ENV_PORT}" ;;
    esac
fi

echo "============================================================"
echo "  SecureTrans 生产只读冒烟验证（ADR-017 · allowlist）"
echo "  目标: ${BASE_URL}"
echo "============================================================"
echo ""

# 1. 服务健康检查
echo "[1/3] 服务健康检查..."
HEALTH=$(curl -sf "${BASE_URL}/api/health" || echo "FAILED")
if echo "$HEALTH" | grep -q '"status":"ok"'; then
    echo "  健康检查: PASS"
    echo "  返回: ${HEALTH}"
else
    echo "  健康检查: FAIL"
    echo "  返回: ${HEALTH}"
    echo "  排查: systemctl status securetrans / journalctl -u securetrans -n 100"
    exit 1
fi

# 2. 检查关键目录（staging/external/archive 存在 + 同文件系统）
echo ""
echo "[2/3] 存储目录检查..."
if [ -f "$INSTALL_DIR/.env" ]; then
    NAS_ROOT=$(grep -E '^NAS_ROOT=' "$INSTALL_DIR/.env" | cut -d= -f2)
else
    NAS_ROOT="./nas"
fi
echo "  NAS_ROOT: ${NAS_ROOT}"
for dir in staging external archive; do
    if [ -d "${NAS_ROOT}/${dir}" ]; then
        echo "  ${dir}/ 存在: PASS"
    else
        echo "  ${dir}/ 不存在: WARN (将由 app 自动创建)"
    fi
done

# 3. 只读冒烟测试（SMOKE_MODE=1 → test_api.py 仅执行组 24 冒烟白名单）
echo ""
echo "[3/3] 运行只读冒烟测试（组 24 · 白名单）..."
if [ ! -f "$TEST_SCRIPT_PATH" ]; then
    echo "  错误: 未找到测试脚本 ${TEST_SCRIPT_PATH}"
    exit 1
fi

# 优先用部署环境 venv python
if [ -x "/opt/securetrans/venv/bin/python" ]; then
    PY="/opt/securetrans/venv/bin/python"
elif command -v python3.12 &>/dev/null; then
    PY="python3.12"
else
    PY="python3"
fi

# 凭据自适应（与 verify.sh 同源：.env RESET_PASSWORD）
ENV_RESET_PWD=""
if [ -f "$INSTALL_DIR/.env" ]; then
    ENV_RESET_PWD=$(grep -E '^RESET_PASSWORD=' "$INSTALL_DIR/.env" 2>/dev/null | cut -d= -f2 | tr -d '\r' | head -1 || true)
fi
TEST_ADMIN_USER="${VERIFY_ADMIN_USER:-admin}"
TEST_ADMIN_PASS="${VERIFY_ADMIN_PASS:-${ENV_RESET_PWD:-Init@123456}}"

# ENV_ROLE：读取 .env；缺失时默认 prod（冒烟本身只读，安全）
ENV_ROLE_VAL="prod"
if [ -f "$INSTALL_DIR/.env" ]; then
    ENV_ROLE_VAL=$(grep -E '^ENV_ROLE=' "$INSTALL_DIR/.env" 2>/dev/null | cut -d= -f2 | tr -d '\r' | head -1 || true)
    ENV_ROLE_VAL="${ENV_ROLE_VAL:-prod}"
fi
echo "  环境角色: ${ENV_ROLE_VAL}（冒烟组只读，不创建业务数据）"

BASE_URL="$BASE_URL" NAS_ROOT="$NAS_ROOT" SMOKE_MODE=1 \
  TEST_ADMIN_USER="$TEST_ADMIN_USER" TEST_ADMIN_PASS="$TEST_ADMIN_PASS" ENV_ROLE="$ENV_ROLE_VAL" \
  "$PY" "$TEST_SCRIPT_PATH"
TEST_EXIT=$?

# 4. 防火墙提示（生产远程访问需要）
echo ""
if command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld 2>/dev/null; then
    if firewall-cmd --list-ports 2>/dev/null | grep -q "${ENV_PORT}/tcp"; then
        echo "  端口 ${ENV_PORT}/tcp 已放行: PASS"
    else
        echo "  端口 ${ENV_PORT}/tcp 未放行: WARN —— 内网/办公外网无法远程访问（见 DEPLOY.md 阶段7）"
    fi
else
    echo "  未启用 firewalld，跳过"
fi

if [ $TEST_EXIT -ne 0 ]; then
    echo "  冒烟测试异常 (exit code: ${TEST_EXIT})"
    exit 1
fi

echo ""
echo "============================================================"
echo "  只读冒烟验证完成（ADR-017）"
echo "  说明：写数据（上传/审批/用户/备份等）不在此脚本，需人工验收"
echo "============================================================"
