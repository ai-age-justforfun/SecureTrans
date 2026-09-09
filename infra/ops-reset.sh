#!/bin/bash
# ============================================================
# SecureTrans 出厂重置脚本（ADR-011 数据生命周期）
# 备份+清理：自动备份当前数据 → 清空业务库与 NAS → init_db 重建出厂状态
# admin 密码重置为 .env RESET_PASSWORD（与部署/verify 同源，ADR-009）
# 用法: sudo bash infra/ops-reset.sh   （先自动备份，安全可回退）
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

if [ -x "$INSTALL_DIR/venv/bin/python" ]; then
    PY="$INSTALL_DIR/venv/bin/python"
else
    PY="$(command -v python3 || command -v python || true)"
fi
if [ -z "$PY" ]; then
    echo "[错误] 未找到 python3/python" >&2
    exit 1
fi

ENV_RESET_PWD="$(grep -E '^RESET_PASSWORD=' "$INSTALL_DIR/.env" 2>/dev/null | cut -d= -f2 | tr -d '\r' | head -1 || true)"
ENV_RESET_PWD="${ENV_RESET_PWD:-Init@123456}"

echo "[1/2] 自动备份当前数据（可回退）..."
bash "$SCRIPT_DIR/ops-backup.sh"

echo "[2/2] 出厂重置（重建数据库 + 清空业务目录 + admin 密码重置）..."
(cd "$INSTALL_DIR/src" && RESET_PASSWORD="$ENV_RESET_PWD" "$PY" app.py --reset-factory)

echo "[OK] 出厂重置完成"
echo "     admin 密码 = $ENV_RESET_PWD（.env RESET_PASSWORD），首次登录强制修改"
echo "     重启服务: systemctl restart securetrans（若服务已停止则直接启动）"
