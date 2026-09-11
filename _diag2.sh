#!/bin/bash
echo "=== A. 当前时间 ==="
date '+%F %T'
echo
echo "=== B. act_runner 最新 15 行 ==="
tail -15 /var/log/act_runner.log 2>/dev/null
echo
echo "=== C. act_runner 进程信号相关状态 ==="
PID=$(pgrep -f act_runner | head -1)
echo "PID=$PID"
if [ -n "$PID" ]; then
  cat /proc/$PID/status | grep -E "State|SigBlk|SigIgn|SigCgt|SigPnd|ShdPnd"
  echo "--- 父进程 ---"
  ps -o pid,ppid,comm,args -p $PID
fi
echo
echo "=== D. WSL 内核日志（最近 30 行，OOM/oom/kill/panic）==="
dmesg --time-format iso 2>/dev/null | tail -30 | grep -iE "oom|kill|panic|crash|docker|overlay|memory" || dmesg 2>/dev/null | tail -20
echo
echo "=== E. docker daemon 状态与重启历史 ==="
systemctl show docker -p ActiveState -p SubState -p NRestarts -p ExecMainStartTimestamp
echo
echo "=== F. docker 内核事件（最近 30 条）==="
sudo docker events --since 1h --until 0s 2>/dev/null | head -30 || echo "(无事件或权限)"
echo
echo "=== G. 是否有 cron / 定时任务杀 runner ==="
ls -la /etc/cron.d/ 2>/dev/null
crontab -l 2>/dev/null | head -5
echo
echo "=== H. 最近 3 小时 journal 全量 act_runner 条目数 ==="
journalctl -u act_runner --since "3 hours ago" --no-pager 2>/dev/null | wc -l
echo
echo "=== I. WSL 发行版启动时间（检查 WSL 是否被重启）==="
uptime
