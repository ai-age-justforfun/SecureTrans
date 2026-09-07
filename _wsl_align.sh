#!/bin/bash
# WSL 测试环境对齐服务器生产路径：NAS_ROOT=/mnt/nas/securetrans
set -x
# 1. 迁移旧测试数据（保持 external/archive 证据连续）
mkdir -p /mnt/nas
if [ -d /mnt/nas/securetrans ]; then
    echo "目标已存在，跳过迁移"
else
    mv /var/nas/securetrans /mnt/nas/securetrans
    echo "已迁移 /var/nas/securetrans -> /mnt/nas/securetrans"
fi
ls -la /mnt/nas/ | cat -A

# 2. 用环境变量覆盖 NAS_ROOT 重跑部署（deploy.sh 会写回 .env 并同步代码）
cd /mnt/c/Users/jinta/.doubao/lark-chats/2026-08-25/new-chat
NAS_ROOT=/mnt/nas/securetrans bash infra/deploy.sh
echo "DEPLOY_EXIT=$?"
