#!/bin/bash
echo "=== A. uptime / 启动时间 ==="
uptime
echo "boot 时间:"
who -b 2>/dev/null
echo "systemd 启动:"
systemctl show -p SystemdTimestamp --value 2>/dev/null
echo
echo "=== B. sdg 磁盘信息 ==="
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINT 2>/dev/null | grep -E "sdg|NAME" 
echo
echo "=== C. /etc/resolv.conf（网关线索）==="
cat /etc/resolv.conf 2>/dev/null | grep nameserver
echo
echo "=== D. 默认网关（Windows 主机 IP）==="
ip route | head -3
echo
echo "=== E. 当前内存与 cgroup 限制 ==="
free -h | head -2
cat /sys/fs/cgroup/memory.max 2>/dev/null || cat /sys/fs/cgroup/memory/memory.limit_in_bytes 2>/dev/null
echo
echo "=== F. docker 容器当前状态 ==="
sudo docker ps -a --format "{{.Names}} {{.Status}}" 2>/dev/null | head -8
echo
echo "=== G. 最近一次 docker/runner 启动与现在的时间差 ==="
systemctl show docker -p ExecMainStartTimestamp --value
systemctl show act_runner -p ExecMainStartTimestamp --value
date '+%F %T'
