#!/bin/bash
# WSL 测试环境重置 + 同步最新 tests + 全量测试
set -x
# 1. 同步工作区 tests（deploy.sh 不复制 tests，手动同步）
cp -a /mnt/c/Users/jinta/.doubao/lark-chats/2026-08-25/new-chat/tests/. /opt/securetrans/tests/
# 2. 重置干净基线（测试假设 admin/Admin@123 初始状态）
systemctl stop securetrans
rm -f /opt/securetrans/data/securetrans.db /opt/securetrans/data/securetrans.log
rm -rf /mnt/nas/securetrans/staging/* /mnt/nas/securetrans/external/* /mnt/nas/securetrans/archive/* 2>/dev/null
chown -R securetrans:securetrans /opt/securetrans/data /mnt/nas/securetrans
systemctl start securetrans
sleep 3
curl -s http://127.0.0.1:8000/api/health
echo ""
# 3. 全量测试
cd /opt/securetrans/tests
NAS_ROOT=/mnt/nas/securetrans python3 test_api.py 2>&1 | tail -8
