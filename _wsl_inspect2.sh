#!/bin/bash
echo "=== systemctl 版本 ==="
systemctl --version | head -1

echo ""
echo "=== .env 原始字节（cat -A）==="
cat -A /opt/securetrans/.env | grep NAS_ROOT

echo ""
echo "=== .env NAS_ROOT 行 repr（Python bytes）==="
python3 -c "
b=open('/opt/securetrans/.env','rb').read()
for line in b.split(b'\n'):
    if line.startswith(b'NAS_ROOT'):
        print(repr(line))
"

echo ""
echo "=== service ReadWritePaths 原始字节 ==="
grep ReadWritePaths /etc/systemd/system/securetrans.service | cat -A

echo ""
echo "=== /var/nas 目录原始字节 ==="
ls -la /var/nas/ | cat -A

echo ""
echo "=== systemd EnvironmentFile 加载后 NAS_ROOT（服务进程环境）==="
pid=$(systemctl show -p MainPID --value securetrans)
echo "MainPID=$pid"
tr '\0' '\n' < /proc/$pid/environ | grep NAS_ROOT | cat -A
