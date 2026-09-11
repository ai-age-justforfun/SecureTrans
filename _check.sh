#!/bin/bash
echo "--- act_runner 日志尾部 ---"
sudo tail -8 /var/log/act_runner.log
echo "--- systemd-watch（重启记录）---"
tail -5 /opt/securetrans/systemd-watch.log 2>/dev/null || echo "(无记录 = systemd 稳定)"
echo "--- 当前状态 ---"
date '+%F %T'
echo "uptime: $(awk '{print int($1)}' /proc/uptime)s"
echo "runner PID: $(pgrep -f 'act_runner daemon' | head -1)"
