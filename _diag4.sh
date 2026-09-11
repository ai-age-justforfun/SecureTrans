#!/bin/bash
echo "=== 1. WSL 版本 ==="
cat /proc/version | head -1
echo
echo "=== 2. /etc/wsl.conf ==="
cat /etc/wsl.conf 2>/dev/null || echo "(无)"
echo
echo "=== 3. journal 持久化情况 ==="
ls -la /var/log/journal/ 2>/dev/null && du -sh /var/log/journal 2>/dev/null || echo "journal 未持久化（/run 易失）"
echo
echo "=== 4. 上一次 boot 的最后 40 行（若可读）==="
journalctl -b -1 -n 40 --no-pager 2>/dev/null || echo "(上一次 boot 日志不可读)"
echo
echo "=== 5. systemd 本次启动日志（确认启动顺序）==="
journalctl -b 0 -n 25 --no-pager 2>/dev/null | head -25
echo
echo "=== 6. 当前系统时间 ==="
date '+%F %T'
echo "=== 7. 启动后 uptime（秒）==="
awk '{print int($1)"s"}' /proc/uptime
