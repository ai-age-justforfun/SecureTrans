#!/bin/bash
# 取证部署 II：strace act_runner 信号 + journal 持久化 + systemd 崩溃检测
set -e
echo "=== 1. 安装 strace ==="
dnf install -y strace 2>&1 | tail -1
echo "=== 2. journald.conf 位置 ==="
ls -la /etc/systemd/journald.conf 2>/dev/null || ls -la /usr/lib/systemd/journald.conf 2>/dev/null
echo "=== 3. journal 持久化 ==="
mkdir -p /var/log/journal
chown root:systemd-journal /var/log/journal 2>/dev/null || chown root:root /var/log/journal
chmod 2755 /var/log/journal
if [ -f /etc/systemd/journald.conf ]; then
  grep -q "^Storage=persistent" /etc/systemd/journald.conf || echo "Storage=persistent" >> /etc/systemd/journald.conf
fi
systemctl kill -s SIGUSR1 systemd-journald 2>/dev/null || true
sleep 1
echo "journal 目录（应为 persistent）："
ls -ld /var/log/journal 2>/dev/null
echo "=== 4. strace attach 循环（后台）==="
cat > /opt/securetrans/strace-attach.sh <<'EOF'
#!/bin/bash
# 持续 attach 到 act_runner，捕获信号（SIGTERM 等）
while true; do
  PID=$(pgrep -f 'act_runner daemon' | head -1)
  if [ -n "$PID" ] && [ ! -f "/tmp/st_${PID}.log" ]; then
    echo "$(date '+%F %T') ATTACH $PID" >> /opt/securetrans/watch.log
    strace -f -e trace=signal -p "$PID" -o "/tmp/st_${PID}.log" 2>/dev/null &
  fi
  sleep 3
done
EOF
chmod +x /opt/securetrans/strace-attach.sh
pkill -f strace-attach.sh 2>/dev/null || true
nohup /opt/securetrans/strace-attach.sh >/dev/null 2>&1 &
echo "strace-attach 已启动"
sleep 2
pgrep -f act_runner | head -1 | while read p; do ls -la /tmp/st_$p.log 2>/dev/null || echo "(attach 等待中)"; done
echo "=== 5. systemd 崩溃检测（后台）：记录 systemd 启动时间变化 ==="
cat > /opt/securetrans/systemd-watch.sh <<'EOF'
#!/bin/bash
LOG=/opt/securetrans/systemd-watch.log
: > $LOG
LAST=""
while true; do
  S=$(systemctl show --property=SystemdTimestamp --value 2>/dev/null)
  if [ -n "$S" ] && [ "$S" != "$LAST" ]; then
    echo "$(date '+%F %T') SYSTEMD-START=$S last=$LAST" >> $LOG
    LAST="$S"
  fi
  sleep 2
done
EOF
chmod +x /opt/securetrans/systemd-watch.sh
pkill -f systemd-watch.sh 2>/dev/null || true
nohup /opt/securetrans/systemd-watch.sh >/dev/null 2>&1 &
echo "systemd-watch 已启动（/opt/securetrans/systemd-watch.log）"
echo "=== 部署完成 ==="
