#!/bin/bash
echo "=== /var/nas/securetrans 旧数据 ==="
find /var/nas/securetrans -maxdepth 2 | head -20
du -sh /var/nas/securetrans 2>/dev/null
echo ""
echo "=== 当前服务健康 ==="
curl -s --max-time 5 http://127.0.0.1:8000/api/health | head -c 200
echo ""
echo "=== 当前 .env 关键行 ==="
grep -E "^(NAS_ROOT|DEPLOY_MODE)=" /opt/securetrans/.env
