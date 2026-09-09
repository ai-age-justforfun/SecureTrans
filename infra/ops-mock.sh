#!/bin/bash
# ============================================================
# SecureTrans 模拟数据生成脚本（ADR-011，测试/开发环境闭环）
# 生成测试用户/审批人/合作方/各状态提交单，配合 verify.sh 自动化验证
# 生产/预生产模式拒绝（DEPLOY_MODE=production 时退出）
# 用法: sudo bash infra/ops-mock.sh   （测试环境；幂等，可重复执行）
# ============================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ ! -f "$INSTALL_DIR/.env" ]; then
    echo "[错误] 未找到 $INSTALL_DIR/.env" >&2
    exit 1
fi
set -a
# shellcheck disable=SC1091
. "$INSTALL_DIR/.env"
set +a

DEPLOY_MODE="${DEPLOY_MODE:-testing}"
if [ "$DEPLOY_MODE" != "testing" ]; then
    echo "[错误] 当前 DEPLOY_MODE=$DEPLOY_MODE：生产/预生产环境禁止生成模拟数据（ADR-011）" >&2
    exit 1
fi

if [ -x "$INSTALL_DIR/venv/bin/python" ]; then
    PY="$INSTALL_DIR/venv/bin/python"
else
    PY="$(command -v python3 || command -v python || true)"
fi
if [ -z "$PY" ]; then
    echo "[错误] 未找到 python3/python" >&2
    exit 1
fi

(cd "$INSTALL_DIR/src" && DEPLOY_MODE=testing "$PY" app.py --mock-data)
echo "[OK] 模拟数据生成完成（幂等）；可运行 bash infra/verify.sh 做全量自动化验证"
