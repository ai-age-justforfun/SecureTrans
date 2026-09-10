#!/usr/bin/env bash
# ============================================================
# env-refresh.sh — 刷新 .env 到最新模板格式（安全：只增不覆盖）
#
# 背景：发布包不含 .env（gitignore + 打包排除）；deploy.sh 首次部署从
#   env/prod.env.template 生成 .env，升级时自动保留现有 .env（不覆盖）。
#   但当新版本模板新增/改名配置键（如 v2.2.24 起 MAX_CONTENT_LENGTH →
#   MAX_FILE_SIZE_MB）时，老 .env 缺少新键，需要"刷新格式"。
#
# 用法:
#   bash infra/env-refresh.sh                          # 默认 INSTALL_DIR=/opt/securetrans
#   INSTALL_DIR=/path/to/app bash infra/env-refresh.sh # 指定部署目录
#
# 行为（安全三原则）:
#   1. 先备份现有 .env → .env.bak-<时间戳>（可回退）
#   2. 以 env/prod.env.template 为模板对比键：
#       模板有、现有缺失 → 追加模板默认值（已有键绝不覆盖原值）
#       SECRET_KEY 缺失   → 随机生成（不从模板占位符复制）
#       AD_BIND_PASSWORD 缺失 → 留空并提示手工填写
#   3. 输出报告：新增 N / 保留 M / 模板已删除的键（提示手工清理）
#   4. chmod 640 + 统一 LF（防 Windows 编辑 CRLF 污染）
#
# 与 deploy.sh 关系：deploy.sh 默认不刷新（纯保留）；需要刷新格式时
#   显式运行本脚本，避免升级静默改动生产配置。
# ============================================================
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/securetrans}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE="$SCRIPT_DIR/../env/prod.env.template"
ENV_FILE="$INSTALL_DIR/.env"

if [ ! -f "$ENV_FILE" ]; then
  echo "[错误] $ENV_FILE 不存在。首次部署请运行 deploy.sh（自动从模板生成 .env），无需刷新。"
  exit 1
fi
if [ ! -f "$TEMPLATE" ]; then
  echo "[错误] 模板不存在: $TEMPLATE"
  exit 1
fi

TS=$(date +%Y%m%d%H%M%S)
BAK="$ENV_FILE.bak-$TS"
cp -a "$ENV_FILE" "$BAK"
echo "== 已备份: $BAK"

# 提取键（KEY= 行，忽略注释/空行/行尾 CR）
tmpl_keys=$(grep -E '^[A-Z_]+=' "$TEMPLATE" | sed 's/\r$//' | cut -d= -f1 | sort -u)
cur_keys=$(grep -E '^[A-Z_]+=' "$ENV_FILE" | sed 's/\r$//' | cut -d= -f1 | sort -u)

# 新增键 = 模板 - 现有（保留现有键的原值）
added=0
for k in $tmpl_keys; do
  if ! echo "$cur_keys" | grep -qx "$k"; then
    # 敏感键特殊处理：不从模板占位符复制
    if [ "$k" = "SECRET_KEY" ]; then
      new_val=$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null \
                || openssl rand -hex 32)
      printf '%s=%s\n' "$k" "$new_val" >> "$ENV_FILE"
      echo "  + $k = <随机生成>"
    elif [ "$k" = "AD_BIND_PASSWORD" ]; then
      printf '%s=\n' "$k" >> "$ENV_FILE"
      echo "  + $k = (留空，请手工填写 AD 绑定密码)"
    else
      val=$(grep -E "^$k=" "$TEMPLATE" | sed 's/\r$//' | head -1 | cut -d= -f2-)
      printf '%s=%s\n' "$k" "$val" >> "$ENV_FILE"
      echo "  + $k = $val"
    fi
    added=$((added + 1))
  fi
done

# 模板已删除的键（现有有、模板无）→ 提示，不自动删（防误删）
echo "== 模板中已不存在的键（手工确认后自行清理，默认保留）:"
removed=0
for k in $cur_keys; do
  if ! echo "$tmpl_keys" | grep -qx "$k"; then
    val=$(grep -E "^$k=" "$ENV_FILE" | sed 's/\r$//' | head -1 | cut -d= -f2-)
    echo "  - $k=${val:0:12}...（模板已移除；如 MAX_CONTENT_LENGTH 请删除，上限改由 MAX_FILE_SIZE_MB 控制）"
    removed=$((removed + 1))
  fi
done
[ "$removed" -eq 0 ] && echo "  （无）"

# 统一 LF + 权限
sed -i 's/\r$//' "$ENV_FILE"
chmod 640 "$ENV_FILE"

echo "== 刷新完成: 新增 $added 个键，保留原有 $(echo "$cur_keys" | wc -l) 个键的值，提示清理 $removed 个旧键"
echo "== 刷新后请执行: sudo systemctl restart securetrans（.env 改动经 systemd EnvironmentFile 即时生效）"
