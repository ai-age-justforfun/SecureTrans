#!/bin/bash
# 容器内模拟 act_runner job：空 workspace + clone + ci_test.sh（与 ci_test.sh 同源网关解析）
set -e
hex_ip() { local h=$1; echo "$((16#${h:6:2})).$((16#${h:4:2})).$((16#${h:2:2})).$((16#${h:0:2}))"; }
GW="$(hex_ip "$(awk '$2=="00000000" {print $3; exit}' /proc/net/route 2>/dev/null)")"
echo "=== 容器内开始: $(date '+%F %T') | 网关: ${GW} ==="
cd /tmp
rm -rf ws_act && mkdir -p ws_act && cd ws_act
echo "=== clone 开始: $(date '+%F %T') ==="
timeout 120 git clone --depth 1 "http://${GW}:3000/openwrtadmin/SecureTrans.git" . || { echo "CLONE-FAIL(网关 ${GW})"; exit 1; }
echo "=== clone 完成: $(date '+%F %T') ==="
ls src/app.py >/dev/null && echo "代码就位"
echo "=== ci_test.sh 开始: $(date '+%F %T') ==="
timeout 600 bash infra/ci_test.sh 2>&1 | tail -8
echo "=== 全部完成: $(date '+%F %T') ==="
