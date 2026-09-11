#!/bin/bash
echo "=== docker ps（act_runner 的 job 容器？）==="
sudo docker ps -a --format "{{.Names}} | {{.Image}} | {{.Status}} | {{.Label \"com.docker.compose.project\"}}" 2>/dev/null | head -8
echo ""
echo "=== act_runner workspace 卷 ==="
ls -la /opt/securetrans/workspace/ 2>/dev/null | head -10
echo ""
echo "=== workspace 下 job 目录 ==="
find /opt/securetrans/workspace -maxdepth 2 -type d 2>/dev/null | head -10
echo ""
echo "=== act_runner 进程 CPU/状态 ==="
ps -o pid,pcpu,pmem,etime,stat,cmd -p $(pgrep -f 'act_runner daemon' | head -1) 2>/dev/null
echo ""
echo "=== runner 日志最新 5 行 ==="
sudo tail -5 /var/log/act_runner.log
