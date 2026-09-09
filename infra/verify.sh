#!/bin/bash
# ============================================================
# SecureTrans 部署后验证脚本
# 运行全量 193项 API 测试，确认服务器部署正确
# 用法：bash verify.sh [BASE_URL]
# 目录结构：infra/verify.sh, tests/test_api.py
# ============================================================
set -euo pipefail

INSTALL_DIR="/opt/securetrans"
BASE_URL="${1:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_SCRIPT_PATH="$SCRIPT_DIR/../tests/test_api.py"

# 未显式指定 BASE_URL 时，从 .env HOST/PORT 自适应：
#   HOST=0.0.0.0 / 127.0.0.1 / 空 -> 127.0.0.1:PORT（loopback 可达）
#   HOST=<具体IP>               -> http://<IP>:PORT（gunicorn 仅监听该 IP，127.0.0.1 不可达）
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
echo "  SecureTrans 部署验证"
echo "  目标: ${BASE_URL}"
echo "============================================================"
echo ""

# 1. 服务健康检查
echo "[1/4] 服务健康检查..."
HEALTH=$(curl -sf "${BASE_URL}/api/health" || echo "FAILED")
if echo "$HEALTH" | grep -q '"status":"ok"'; then
    echo "  健康检查: PASS"
    echo "  返回: ${HEALTH}"
else
    echo "  健康检查: FAIL"
    echo "  返回: ${HEALTH}"
    echo ""
    echo "  排查命令:"
    echo "    systemctl status securetrans"
    echo "    journalctl -u securetrans -n 100"
    echo "    curl -v ${BASE_URL}/api/health"
    exit 1
fi

# 2. 检查关键目录
echo ""
echo "[2/4] 存储目录与文件系统检查..."
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
        echo "  ${dir}/ 不存在: FAIL (将由 app 自动创建)"
    fi
done

# 检查同文件系统
if [ -d "${NAS_ROOT}/staging" ] && [ -d "${NAS_ROOT}/external" ]; then
    FS1=$(df -P "${NAS_ROOT}/staging" | tail -1 | awk '{print $1}')
    FS2=$(df -P "${NAS_ROOT}/external" | tail -1 | awk '{print $1}')
    if [ "$FS1" = "$FS2" ]; then
        echo "  同文件系统验证: PASS (${FS1})"
    else
        echo "  同文件系统验证: FAIL (staging=${FS1}, external=${FS2})"
        echo "  警告: os.rename 将退化为复制+删除，大文件摆渡会变慢"
    fi
fi

# 3. 运行全量 API 测试
echo ""
echo "[3/4] 运行全量 API 测试 (193项)..."
echo "  (测试脚本会创建测试用户和测试文件，完成后自动清理)"
echo ""

# 检查测试脚本是否存在
if [ ! -f "$TEST_SCRIPT_PATH" ]; then
    echo "  错误: 未找到测试脚本 ${TEST_SCRIPT_PATH}"
    echo "  请确保在项目根目录下运行: bash infra/verify.sh"
    exit 1
fi

# 优先用部署环境的 venv python，其次系统 python3
if [ -x "/opt/securetrans/venv/bin/python" ]; then
    PY="/opt/securetrans/venv/bin/python"
elif command -v python3.12 &>/dev/null; then
    PY="python3.12"
else
    PY="python3"
fi

# 管理凭据自适应（非硬编码，ADR-005）：
#   部署时 admin 密码会被 deploy.sh 重置为 .env RESET_PASSWORD，因此验证凭据自动取 .env RESET_PASSWORD；
#   也可用环境变量 VERIFY_ADMIN_USER / VERIFY_ADMIN_PASS 显式覆盖（例如 admin 密码已手工修改、临时验证时）
ENV_RESET_PWD=""
if [ -f "$INSTALL_DIR/.env" ]; then
    ENV_RESET_PWD=$(grep -E '^RESET_PASSWORD=' "$INSTALL_DIR/.env" 2>/dev/null | cut -d= -f2 | tr -d '\r' | head -1 || true)
fi
TEST_ADMIN_USER="${VERIFY_ADMIN_USER:-admin}"
# 兜底与 app.py RESET_PASSWORD 默认一致（Init@123456），不用 Admin@123（部署后 admin 已重置）
TEST_ADMIN_PASS="${VERIFY_ADMIN_PASS:-${ENV_RESET_PWD:-Init@123456}}"
echo "  验证账号: ${TEST_ADMIN_USER} (凭据: .env RESET_PASSWORD 或 VERIFY_ADMIN_PASS)"

# 原地运行 test_api.py（保留 tests/ 相对路径依赖），BASE_URL / NAS_ROOT / 凭据用环境变量传入
BASE_URL="$BASE_URL" NAS_ROOT="$NAS_ROOT" TEST_ADMIN_USER="$TEST_ADMIN_USER" TEST_ADMIN_PASS="$TEST_ADMIN_PASS" "$PY" "$TEST_SCRIPT_PATH"
TEST_EXIT=$?

if [ $TEST_EXIT -ne 0 ]; then
    echo ""
    echo "  测试脚本执行异常 (exit code: ${TEST_EXIT})"
    exit 1
fi

# 3.5 防火墙放行检查（提示项，不阻塞验证）
echo ""
echo "[3.5/4] 防火墙放行检查...（提示项）"
if command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld 2>/dev/null; then
    if firewall-cmd --list-ports 2>/dev/null | grep -q "${ENV_PORT}/tcp"; then
        echo "  端口 ${ENV_PORT}/tcp 已放行: PASS"
    else
        echo "  端口 ${ENV_PORT}/tcp 未放行: WARN —— 内网/办公外网无法远程访问，放行命令见 DEPLOY.md 阶段7"
    fi
else
    echo "  未启用 firewalld，跳过（本机访问不受影响，远程访问需自行放行）"
fi

# 4. 总结
echo ""
echo "[4/4] 验证总结..."
echo "  服务健康:   PASS"
echo "  目录结构:   已检查"
echo "  API 测试:   见上方结果"
echo ""
echo "============================================================"
echo "  验证完成"
echo "============================================================"
echo ""
echo "  如全部通过，部署验证成功。"
echo "  如有失败项，请查看上方日志并排查。"
echo ""
echo "  常用排查命令:"
echo "    systemctl status securetrans"
echo "    journalctl -u securetrans -n 100 --no-pager"
echo "    tail -f /opt/securetrans/data/securetrans.log"
echo "    tail -f /opt/securetrans/data/gunicorn-error.log"
