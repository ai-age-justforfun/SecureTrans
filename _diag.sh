#!/bin/bash
echo "=== 1. act_runner / docker 状态 ==="
systemctl is-active act_runner docker 2>&1
echo
echo "=== 2. 内存 ==="
free -h | head -2
echo
echo "=== 3. act_runner 进程 ==="
ps aux | grep -i act_runner | grep -v grep | head -3
echo
echo "=== 4. config.yaml ==="
cat /opt/securetrans/config.yaml 2>/dev/null | head -40
echo
echo "=== 5. 最近日志 80 行 ==="
tail -80 /var/log/act_runner.log 2>/dev/null
echo
echo "=== 6. systemd 单元 ==="
cat /etc/systemd/system/act_runner.service 2>/dev/null
echo
echo "=== 7. journal 中 Stopping/Shutdown/OOM 相关 ==="
journalctl -u act_runner --no-pager 2>/dev/null | grep -iE "stopp|shutdown|kill|oom|signal|panic|fatal" | tail -20
echo
echo "=== 8. docker 最近容器事件 ==="
sudo docker events --since 2h --until 1h 2>/dev/null | tail -10 || echo "no docker events"
