#!/bin/bash
# ============================================================
# SecureTrans 部署后验证脚本
# 运行全量 166 项 API 测试，确认服务器部署正确
# 用法：bash verify.sh [BASE_URL]
# 目录结构：infra/verify.sh, tests/test_api.py
# ============================================================
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8000}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_SCRIPT_PATH="$SCRIPT_DIR/../tests/test_api.py"

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
INSTALL_DIR="/opt/securetrans"
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
echo "[3/4] 运行全量 API 测试 (166项)..."
echo "  (测试脚本会创建测试用户和测试文件，完成后自动清理)"
echo ""

# 检查测试脚本是否存在
if [ ! -f "$TEST_SCRIPT_PATH" ]; then
    echo "  错误: 未找到测试脚本 ${TEST_SCRIPT_PATH}"
    echo "  请确保在项目根目录下运行: bash infra/verify.sh"
    exit 1
fi

# 修改 test_api.py 的 BASE_URL 并运行
TEST_SCRIPT=$(mktemp /tmp/securetrans_test_XXXXXX.py)
sed "s|BASE_URL = \"http://localhost:8000\"|BASE_URL = \"${BASE_URL}\"|" \
    "$TEST_SCRIPT_PATH" > "$TEST_SCRIPT"

python3 "$TEST_SCRIPT"
TEST_EXIT=$?
rm -f "$TEST_SCRIPT"

if [ $TEST_EXIT -ne 0 ]; then
    echo ""
    echo "  测试脚本执行异常 (exit code: ${TEST_EXIT})"
    exit 1
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
