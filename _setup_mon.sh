#!/bin/bash
# 取证监控部署（root）：抓 runner 中断根因
set -e
echo "=== 1. 安装 auditd（记录 kill/tgkill 调用）==="
dnf install -y audit 2>&1 | tail -2 || yum install -y audit 2>&1 | tail -2
systemctl start auditd 2>/dev/null || service auditd start 2>/dev/null || echo "auditd 启动失败"
echo "=== 2. 添加 kill 审计规则 ==="
auditctl -D 2>/dev/null || true
auditctl -a always,exit -F arch=b64 -S kill,tgkill 2>/dev/null && echo "kill 规则 OK" || echo "kill 规则失败"
echo "=== 3. journal 持久化（下次关闭原因可回溯）==="
mkdir -p /var/log/journal
systemd-tmpfiles --create --prefix /var/log/journal 2>/dev/null || true
systemctl restart systemd-journald 2>/dev/null || true
echo "journal Storage 设置："
grep -r "Storage" /etc/systemd/journald.conf | head -2 || echo "(默认 auto)"
echo "=== 4. 监控脚本（后台）：记录发行版重启时间 + act_runner PID 变化 ==="
cat > /opt/securetrans/watch.sh <<'EOF'
#!/bin/bash
# 每 2 秒记录：uptime（发行版重启检测）、act_runner PID、内存
LOG=/opt/securetrans/watch.log
: > $LOG
LAST_UP=""
LAST_PID=""
while true; do
  UP=$(awk '{print int($1)}' /proc/uptime)
  PID=$(pgrep -f 'act_runner daemon' | head -1)
  MEM=$(free -m | awk '/Mem:/{print $3"MB/"$2"MB"}')
  NOW=$(date '+%F %T')
  if [ "$UP" != "$LAST_UP" ]; then
    echo "$NOW UPTIME-RESET $UP (发行版重启!) last=$LAST_UP" >> $LOG
    LAST_UP="$UP"
  fi
  if [ "$PID" != "$LAST_PID" ]; then
    echo "$NOW RUNNER-PID $PID (变化) last=$LAST_PID" >> $LOG
    LAST_PID="$PID"
  fi
  echo "$NOW up=$UP pid=$PID mem=$MEM" >> $LOG
  sleep 2
done
EOF
chmod +x /opt/securetrans/watch.sh
pkill -f watch.sh 2>/dev/null || true
nohup /opt/securetrans/watch.sh >/dev/null 2>&1 &
echo "watch.sh 已后台启动（/opt/securetrans/watch.log）"
echo "=== 5. 确认 ==="
sleep 3
cat /opt/securetrans/watch.log
echo "=== 部署完成 ==="
