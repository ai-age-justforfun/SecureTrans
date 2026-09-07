#!/bin/bash
echo "=== 当前 service 文件 ==="
cat -A /etc/systemd/system/securetrans.service | grep -vE "^#|^$"
echo ""
echo "=== 服务进程环境 ==="
pid=$(systemctl show -p MainPID --value securetrans)
echo "MainPID=$pid"
tr '\0' '\n' < /proc/$pid/environ | grep -E "^(NAS_ROOT|DEPLOY_MODE)=" | cat -A
echo ""
echo "=== 备份的 v2.2.0 service（对比 EnvironmentFile）==="
ls -d /opt/securetrans_backup_*/ 2>/dev/null | tail -2
for d in /opt/securetrans_backup_*/; do
    echo "--- $d ---"
    grep -E "EnvironmentFile|ReadWritePaths" $d/etc/systemd/system/securetrans.service 2>/dev/null || \
    find $d -name "securetrans.service" 2>/dev/null | head -2 | while read f; do grep -E "EnvironmentFile|ReadWritePaths" "$f"; done
    break
done
echo ""
echo "=== 工作区模板 EnvironmentFile ==="
grep -n "EnvironmentFile" /mnt/c/Users/jinta/.doubao/lark-chats/2026-08-25/new-chat/infra/securetrans.service || echo "工作区模板无 EnvironmentFile!"
