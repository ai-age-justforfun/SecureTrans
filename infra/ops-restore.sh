#!/bin/bash
# ============================================================
# SecureTrans 数据恢复脚本（ADR-011 数据生命周期）
# 离线文件级操作：从 data/backups/<name> 恢复 DB + NAS 业务目录
# 用法: sudo bash infra/ops-restore.sh backup-20260909_120000
# 注意: 恢复会替换当前全部业务数据；回退 = 再恢复之前的备份；
#       建议在服务停止时执行（systemctl stop securetrans）
# ============================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

NAME="${1:-}"
if [ -z "$NAME" ]; then
    echo "用法: sudo bash infra/ops-restore.sh <备份名称>" >&2
    echo "     备份列表: ls $INSTALL_DIR/data/backups/" >&2
    exit 1
fi
if [ ! -f "$INSTALL_DIR/.env" ]; then
    echo "[错误] 未找到 $INSTALL_DIR/.env" >&2
    exit 1
fi
set -a
# shellcheck disable=SC1091
. "$INSTALL_DIR/.env"
set +a

DATA_DIR="${SECURETRANS_DATA:-$INSTALL_DIR/data}"
NAS_ROOT="${NAS_ROOT:-$INSTALL_DIR/nas}"
DB_PATH="$DATA_DIR/securetrans.db"
SRC="$DATA_DIR/backups/$NAME"

if [ ! -f "$SRC/db/securetrans.db" ]; then
    echo "[错误] 备份不存在或缺少数据库: $SRC" >&2
    exit 1
fi

# 服务运行检查（提示，不强制）
if systemctl is-active --quiet securetrans 2>/dev/null; then
    echo "[警告] securetrans 服务正在运行，建议先: systemctl stop securetrans" >&2
fi

# 1. 替换数据库（清理 WAL/SHM 残留）
for suffix in "" "-wal" "-shm"; do
    [ -e "${DB_PATH}${suffix}" ] && rm -f "${DB_PATH}${suffix}"
done
cp -a "$SRC/db/securetrans.db" "$DB_PATH"

# 2. 替换 NAS 业务目录
for sub in staging external archive; do
    [ -d "$NAS_ROOT/$sub" ] && rm -rf "$NAS_ROOT/$sub"
done
for sub in staging external archive; do
    if [ -d "$SRC/nas/$sub" ]; then
        cp -a "$SRC/nas/$sub" "$NAS_ROOT/$sub"
    else
        mkdir -p "$NAS_ROOT/$sub"
    fi
done

echo "[OK] 恢复完成: $NAME"
echo "     数据已回滚至备份时点（${NAME#backup-}），请重启服务: systemctl restart securetrans"
