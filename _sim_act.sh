#!/bin/bash
# 模拟 act_runner 容器 job 全链路（空 workspace + clone + ci_test.sh）测速
set -e
echo "=== 开始: $(date '+%F %T') ==="
GW=$(ip route | awk '/default/{print $3; exit}')
echo "网关: ${GW}"
cd /tmp
rm -rf ws_act
mkdir -p ws_act
cd ws_act
echo "=== clone 开始: $(date '+%F %T') ==="
timeout 300 git clone --depth 1 "http://${GW}:3000/openwrtadmin/SecureTrans.git" repo
echo "=== clone 完成: $(date '+%F %T') ==="
cd repo
echo "=== ci_test.sh 开始: $(date '+%F %T') ==="
timeout 600 bash infra/ci_test.sh 2>&1 | tail -6
echo "=== 全部完成: $(date '+%F %T') ==="
