#!/bin/bash
# WSL 恢复 production 配置 + 重跑修复后 deploy.sh
set -x
# 1. 恢复 DEPLOY_MODE=production（上轮被 src/.env 覆盖为 testing）
sed -i 's/^DEPLOY_MODE=testing/DEPLOY_MODE=production/' /opt/securetrans/.env
grep -E "^(DEPLOY_MODE|NAS_ROOT)=" /opt/securetrans/.env

# 2. 重跑部署（新逻辑：tar 排除本地产物 + .env 保护 + __RW_PATHS__ 渲染）
cd /mnt/c/Users/jinta/.doubao/lark-chats/2026-08-25/new-chat
NAS_ROOT=/mnt/nas/securetrans bash infra/deploy.sh
echo "DEPLOY_EXIT=$?"
