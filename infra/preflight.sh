#!/bin/bash
# ============================================================
# SecureTrans 环境前置检查 preflight（ADR-035 · 2026-09-15）
# 用途：任何 CI / WSL 测试 / 部署运行之前，先验证环境条件满足并清理历史残留，
#       减少"依赖缺失 / 残留数据 / 端口占用 / 版本不一致 / 文件缺失"类反复诊断
#       （用户 2026-09-15 反馈：Windows dev / WSL test / CI 三环境频繁出现上述问题）。
# 用法：
#   bash infra/preflight.sh                 # 默认检查端口 18000，不自动清理
#   PORT=18000 CLEAN_DIR=/tmp/st-data bash infra/preflight.sh
#     PORT      待检测端口（CI 用 18000，本地 dev 用 8000）
#     CLEAN_DIR 显式传入才清理该残留数据目录（防止误删生产/开发数据）
# 退出码：0=PASS（环境就绪），1=FAIL（输出缺失项，由 CI 直接失败）
# ============================================================
set -euo pipefail
PORT="${PORT:-18000}"
CLEAN_DIR="${CLEAN_DIR:-}"
WS="$(cd "$(dirname "$0")/.." && pwd)"
cd "$WS"
FAIL=0
pass(){ echo "  [PASS] $1"; }
fail(){ echo "  [FAIL] $1"; FAIL=1; }

echo "=== SecureTrans preflight (workspace=$WS, port=$PORT) ==="

# 1. 工作区完整性（核心代码 / 测试 / env 模板 / 关键脚本）
[ -f src/app.py ] && pass "src/app.py" || fail "缺少 src/app.py"
[ -f tests/test_api.py ] && pass "tests/test_api.py" || fail "缺少 tests/test_api.py"
for f in env/dev.env env/test.env env/prod.env.template; do
  [ -f "$f" ] && pass "$f" || fail "缺少 $f"
done
for f in infra/deploy.sh infra/verify.sh infra/smoke.sh infra/ci_test.sh; do
  [ -f "$f" ] && pass "$f" || fail "缺少 $f"
done

# 2. Python 3.12（CI 容器 / WSL 为 venv 或系统 python3.12；裸 3.12 优先）
PY=python3
if command -v python3.12 >/dev/null 2>&1; then PY=python3.12; fi
if [ -x .venv/bin/python ] && .venv/bin/python -c 'import sys; sys.exit(0 if sys.version_info[:2]==(3,12) else 1)' 2>/dev/null; then
  PY=.venv/bin/python
fi
if $PY -c 'import sys; sys.exit(0 if sys.version_info[:2]==(3,12) else 1)' 2>/dev/null; then
  pass "Python 3.12 ($($PY -V 2>&1))"
else
  fail "需要 Python 3.12（当前 $($PY -V 2>&1)），请安装或激活 venv"
fi

# 3. 核心依赖可导入（与 infra/docker/requirements.txt 同源）
if $PY -c 'import flask, gunicorn, apscheduler, ldap3' 2>/dev/null; then
  pass "核心依赖可导入 (flask/gunicorn/apscheduler/ldap3)"
else
  fail "核心依赖缺失：pip install -r infra/docker/requirements.txt（离线：用 wheelhouse）"
fi

# 4. 版本双源一致性（app.py -> index.html，ADR-030 唯一版本源）
V_BE=$(grep -m1 '^APP_VERSION = "v' src/app.py 2>/dev/null | sed -E 's/.*"v([^"]+)".*/\1/' || true)
V_FE=$(grep -m1 "const APP_VERSION = 'v" src/static/index.html 2>/dev/null | sed -E "s/.*'v([^']+)'.*/\1/" || true)
if [ -n "$V_BE" ] && [ "$V_BE" = "$V_FE" ]; then
  pass "版本双源一致 (v$V_BE)"
else
  fail "版本不一致: backend=$V_BE frontend=$V_FE"
fi

# 5. 端口占用检测（残留进程会导致服务起不来/地址占用）
if command -v ss >/dev/null 2>&1 && ss -tln 2>/dev/null | grep -qE "[:.]$PORT[[:space:]]"; then
  fail "端口 $PORT 已被占用（残留服务进程？请先停止再运行）"
else
  pass "端口 $PORT 空闲"
fi

# 6. 清理历史残留数据目录（仅显式传入时执行，防误删）
if [ -n "$CLEAN_DIR" ]; then
  if [ -d "$CLEAN_DIR" ]; then
    rm -rf "$CLEAN_DIR"
    pass "已清理残留数据目录 $CLEAN_DIR"
  else
    pass "无残留数据目录 $CLEAN_DIR"
  fi
fi

if [ "$FAIL" = "1" ]; then
  echo "=== preflight FAILED（请按上方 [FAIL] 项修复后重试）==="
  exit 1
fi
echo "=== preflight PASS（环境就绪）==="
