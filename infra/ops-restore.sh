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
SCOPE="${2:-all}"   # all=系统+业务(默认) / system=仅系统DB / business=仅业务文件（与界面系统工具一致，ADR-011 拆分）
if [ -z "$NAME" ]; then
    echo "用法: sudo bash infra/ops-restore.sh <备份名称> [all|system|business]" >&2
    echo "     备份列表: ls $INSTALL_DIR/data/backups/" >&2
    exit 1
fi
case "$SCOPE" in
  all|system|business) ;;
  *) echo "[错误] SCOPE 仅支持 all/system/business" >&2; exit 1 ;;
esac
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

if [ "$SCOPE" = "system" ] || [ "$SCOPE" = "all" ]; then
    if [ ! -f "$SRC/db/securetrans.db" ]; then
        echo "[错误] 备份不存在或缺少数据库: $SRC" >&2
        exit 1
    fi
fi
if [ "$SCOPE" = "business" ] || [ "$SCOPE" = "all" ]; then
    if [ ! -d "$SRC/nas" ]; then
        echo "[错误] 备份缺少业务数据目录(nas): $SRC" >&2
        exit 1
    fi
fi

# 服务运行检查（提示，不强制）
if systemctl is-active --quiet securetrans 2>/dev/null; then
    echo "[警告] securetrans 服务正在运行，建议先: systemctl stop securetrans" >&2
fi

# 1. 替换数据库（清理 WAL/SHM 残留）—— system/all
if [ "$SCOPE" = "system" ] || [ "$SCOPE" = "all" ]; then
for suffix in "" "-wal" "-shm"; do
    [ -e "${DB_PATH}${suffix}" ] && rm -f "${DB_PATH}${suffix}"
done
cp -a "$SRC/db/securetrans.db" "$DB_PATH"
fi

# 2. 替换 NAS 业务目录 —— business/all
if [ "$SCOPE" = "business" ] || [ "$SCOPE" = "all" ]; then
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
fi

SCOPE_ZH="all:系统+业务|system:系统|business:业务数据"
SCOPE_TXT="${SCOPE_ZH#*$SCOPE:}"; SCOPE_TXT="${SCOPE_TXT%%|*}"
echo "[OK] 恢复完成: $NAME（$SCOPE_TXT）"
echo "     数据已回滚至备份时点（${NAME#backup-}），请重启服务: systemctl restart securetrans"
