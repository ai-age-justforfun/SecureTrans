#!/usr/bin/env bash
# SecureTrans 飞书通知网关 —— 安装/升级脚本（在 feishu-sdk-server-securetrans 上执行）
#
# 用法（在网关机上）：
#   FEISHU_APP_ID=cli_xxx FEISHU_APP_SECRET=yyy bash deploy-gateway.sh
#
# 约定：
#   - 只安装「单向通知服务」，与 CICD 的 feishu-api:8080 完全分离
#   - App Secret 只落在本机 /opt/securetrans-notify/.env（600），不入库、不外传
#   - 地址/端口一律来自环境变量或本机探测，不硬编码（ADR-005）
set -euo pipefail

ROOT="${NOTIFY_ROOT:-/opt/securetrans-notify}"
SRC="${NOTIFY_SRC:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
APP_ID="${FEISHU_APP_ID:?请设置 FEISHU_APP_ID}"
APP_SECRET="${FEISHU_APP_SECRET:?请设置 FEISHU_APP_SECRET}"
PORT="${NOTIFY_PORT:-8090}"
BIND="${NOTIFY_BIND:-$(hostname -I | awk '{print $1}')}"
DATA_DIR="${NOTIFY_DATA_DIR:-/var/lib/securetrans-notify}"
APP_URL="${SECURETRANS_APP_URL:-}"
ALLOW_CIDRS="${NOTIFY_ALLOW_CIDRS:-}"
VENV_SRC="${FEISHU_SDK_VENV_SRC:-/opt/feishu-cicd/venv}"
TOKEN="${FEISHU_NOTIFY_TOKEN:-}"

# 源 IP 白名单为强制项（ADR-052）：服务端 fail-closed，未配置时所有 /notify 请求 403
if [ -z "$ALLOW_CIDRS" ]; then
  echo "[WARN] NOTIFY_ALLOW_CIDRS 为空 —— 服务端将拒绝所有 /notify 请求（请设置如 10.10.30.8/32）"
fi

echo "==> 安装到 $ROOT（bind=$BIND port=$PORT）"
mkdir -p "$ROOT/srv" "$DATA_DIR" /var/log

# 1) 复用网关既有 venv（出网只放行 open.feishu.cn:443，pip 无法在线装包）
if [ ! -x "$ROOT/venv/bin/python" ]; then
  echo "==> 复制 venv: $VENV_SRC -> $ROOT/venv"
  cp -a "$VENV_SRC" "$ROOT/venv"
fi
"$ROOT/venv/bin/python" -c "import lark_oapi, fastapi, uvicorn; print('deps ok', lark_oapi.__version__ if hasattr(lark_oapi,'__version__') else 'lark-oapi')"

# 2) 代码
install -m 0644 "$SRC/notify_app.py" "$ROOT/srv/notify_app.py"

# 3) .env（保留既有 token；首次生成）
if [ -f "$ROOT/.env" ]; then
  if [ -z "$TOKEN" ]; then
    TOKEN="$(grep -E '^FEISHU_NOTIFY_TOKEN=' "$ROOT/.env" | head -1 | cut -d= -f2-)"
  fi
fi
if [ -z "$TOKEN" ]; then
  TOKEN="$(head -c 32 /dev/urandom | base64 | tr -d '=+/' | cut -c1-43)"
  echo "==> 已生成新的 FEISHU_NOTIFY_TOKEN（请记录到开发机 server_credential.md）"
fi
umask 077
cat > "$ROOT/.env" <<EOF
FEISHU_APP_ID=$APP_ID
FEISHU_APP_SECRET=$APP_SECRET
FEISHU_NOTIFY_TOKEN=$TOKEN
NOTIFY_BIND=$BIND
NOTIFY_PORT=$PORT
NOTIFY_DATA_DIR=$DATA_DIR
NOTIFY_MAX_RECIPIENTS=20
NOTIFY_ALLOW_CIDRS=$ALLOW_CIDRS
SECURETRANS_APP_URL=$APP_URL
EOF
chmod 600 "$ROOT/.env"

# 4) systemd
install -m 0644 "$SRC/securetrans-notify.service" /etc/systemd/system/securetrans-notify.service
systemctl daemon-reload
systemctl enable securetrans-notify >/dev/null 2>&1 || true
systemctl restart securetrans-notify
sleep 2

# 5) 自检
if curl -fsS "http://$BIND:$PORT/health" >/dev/null; then
  echo "==> health OK: http://$BIND:$PORT/health"
  curl -fsS "http://$BIND:$PORT/health"; echo
else
  echo "!! health FAIL，查看日志: journalctl -u securetrans-notify -n 50 --no-pager"
  exit 1
fi

echo "==> 完成。token 已写入 $ROOT/.env（600），不同步、不入库。"
