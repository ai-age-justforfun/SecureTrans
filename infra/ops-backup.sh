#!/bin/bash
# ============================================================
# SecureTrans 数据备份脚本（ADR-011 数据生命周期）
# 离线文件级操作：不依赖服务运行，服务停止时最安全
# 用法: sudo bash infra/ops-backup.sh
# 输出: <SECURETRANS_DATA>/backups/backup-<时间戳>/（db + nas）
# ============================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ ! -f "$INSTALL_DIR/.env" ]; then
    echo "[错误] 未找到 $INSTALL_DIR/.env（请先部署）" >&2
    exit 1
fi
# 加载部署级配置（SECURETRANS_DATA / NAS_ROOT）
set -a
# shellcheck disable=SC1091
. "$INSTALL_DIR/.env"
set +a

DATA_DIR="${SECURETRANS_DATA:-$INSTALL_DIR/data}"
NAS_ROOT="${NAS_ROOT:-$INSTALL_DIR/nas}"
DB_PATH="$DATA_DIR/securetrans.db"
BACKUP_ROOT="$DATA_DIR/backups"

if [ ! -f "$DB_PATH" ]; then
    echo "[错误] 数据库不存在: $DB_PATH" >&2
    exit 1
fi

# Python 探测：venv → 系统 python3
if [ -x "$INSTALL_DIR/venv/bin/python" ]; then
    PY="$INSTALL_DIR/venv/bin/python"
else
    PY="$(command -v python3 || command -v python || true)"
fi
if [ -z "$PY" ]; then
    echo "[错误] 未找到 python3/python" >&2
    exit 1
fi

TS="$(date +%Y%m%d_%H%M%S)"
DEST="$BACKUP_ROOT/backup-$TS"
mkdir -p "$DEST/db" "$DEST/nas"

# 1. 数据库一致性快照（sqlite backup API，WAL 安全）
"$PY" - "$DB_PATH" "$DEST/db/securetrans.db" <<'PYEOF'
import sqlite3, sys
src = sqlite3.connect(sys.argv[1])
dst = sqlite3.connect(sys.argv[2])
try:
    src.backup(dst)
finally:
    dst.close(); src.close()
PYEOF

# 2. NAS 业务目录（staging/external/archive）
for sub in staging external archive; do
    if [ -d "$NAS_ROOT/$sub" ]; then
        cp -a "$NAS_ROOT/$sub" "$DEST/nas/$sub"
    fi
done

SIZE="$(du -sh "$DEST" 2>/dev/null | cut -f1)"
echo "[OK] 备份完成: $DEST（$SIZE）"
echo "     恢复: sudo bash infra/ops-restore.sh backup-$TS"
