#!/bin/bash
# 查证 WSL 测试环境实例状态
echo "=== systemd 版本 ==="
systemd --version | head -1
systemd-detect-virt

echo ""
echo "=== /opt/securetrans/.env 行尾与 NAS_ROOT ==="
python3 -c "
b=open('/opt/securetrans/.env','rb').read()
print('CRLF:', b'\r\n' in b)
import re
for line in b.decode('utf-8','replace').splitlines():
    if line.startswith('NAS_ROOT'):
        print(repr(line))
"

echo ""
echo "=== /etc/systemd/system/securetrans.service 关键行 ==="
grep -E "ReadWritePaths|PrivateTmp|ProtectSystem" /etc/systemd/system/securetrans.service

echo ""
echo "=== NAS 目录实况 ==="
ls -la /var/nas/ 2>/dev/null | cat -A
ls -la /mnt/nas/ 2>/dev/null | cat -A
echo "NAS_ROOT 目录存在性:"
[ -d /var/nas/securetrans ] && echo "/var/nas/securetrans 存在" || echo "/var/nas/securetrans 不存在"
[ -d /mnt/nas/securetrans ] && echo "/mnt/nas/securetrans 存在" || echo "/mnt/nas/securetrans 不存在"

echo ""
echo "=== 服务状态 ==="
systemctl is-active securetrans 2>/dev/null
curl -s --max-time 5 http://127.0.0.1:8000/api/health | head -c 200
echo ""
