#!/bin/bash
# WSL 验证 v2.2.9 绑定机制：systemd ${HOST}:${PORT} 变量展开
set -e
cd /mnt/c/Users/jinta/.doubao/lark-chats/2026-08-25/new-chat

# 1. 重跑部署（新模板：-b ${HOST}:${PORT}）
NAS_ROOT=/mnt/nas/securetrans bash infra/deploy.sh > /tmp/deploy.log 2>&1
echo "部署完成: $?"
sleep 2
echo "--- 部署后 service 实际 ExecStart ---"
grep -E "\-b |ExecStart" /etc/systemd/system/securetrans.service | grep -v "^#" | head -3
echo "--- 监听 ---"
ss -tln | grep 8000

# 2. 改 .env HOST 为 WSL 内网 IP，restart，验证绑定变化
WSLIP=$(ip -4 addr show eth0 | grep -oP 'inet \K[\d.]+' | head -1)
echo "WSL IP: $WSLIP"
sed -i "s|^HOST=.*|HOST=${WSLIP}|" /opt/securetrans/.env
systemctl restart securetrans
sleep 3
echo "--- 改 HOST=${WSLIP} + restart 后监听 ---"
ss -tln | grep 8000 || echo "FAIL: 未监听 ${WSLIP}"

# 3. 改回 0.0.0.0，restart，验证
sed -i "s|^HOST=.*|HOST=0.0.0.0|" /opt/securetrans/.env
systemctl restart securetrans
sleep 3
echo "--- 改回 0.0.0.0 + restart 后监听 ---"
ss -tln | grep 8000

# 4. health + 回归
curl -s http://127.0.0.1:8000/api/health
echo ""
cd /opt/securetrans/tests && unset NAS_ROOT && python3 test_api.py 2>&1 | tail -3
