#!/bin/bash
# 停 strace（精确匹配 strace 进程）
for pid in $(pgrep -x strace); do
  cmdline=$(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null)
  if echo "$cmdline" | grep -q "act_runner"; then
    kill $pid 2>/dev/null
    echo "stopped strace $pid"
  fi
done
pkill -f strace-attach 2>/dev/null
echo "=== act_runner 日志尾部 ==="
tail -4 /var/log/act_runner.log
echo "=== systemd-watch ==="
tail -3 /opt/securetrans/systemd-watch.log 2>/dev/null || echo "(空)"
echo "=== 当前 runner PID ==="
pgrep -f 'act_runner daemon' | head -1
