#!/bin/bash
# 容器内模拟 act_runner job：空 workspace + clone + ci_test.sh
set -e
echo "=== 容器内开始: $(date '+%F %T') ==="
cd /tmp
rm -rf ws_act && mkdir -p ws_act && cd ws_act
GW=$(ip route | awk '/default/{print $3; exit}')
echo "网关: ${GW}"
echo "=== clone 开始: $(date '+%F %T') ==="
timeout 120 git clone --depth 1 "http://${GW}:3000/openwrtadmin/SecureTrans.git" . || { echo "CLONE-FAIL"; exit 1; }
echo "=== clone 完成: $(date '+%F %T') ==="
ls src/app.py >/dev/null && echo "代码就位"
echo "=== ci_test.sh 开始: $(date '+%F %T') ==="
timeout 600 bash infra/ci_test.sh 2>&1 | tail -8
echo "=== 全部完成: $(date '+%F %T') ==="
