#!/bin/bash
# SecureTrans 启动脚本 (Linux)
# 测试环境: bash start.sh  (Flask自带服务器 + 本地文件系统)
# 生产环境: 用 gunicorn，见 start-production.sh 或 systemd 服务
set -e

cd "$(dirname "$0")"

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "[错误] 未找到 python3，请先安装 Python 3.10+"
    exit 1
fi

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "[信息] 首次启动，创建虚拟环境..."
    python3 -m venv venv
    source venv/bin/activate
    echo "[信息] 安装依赖..."
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# 加载环境变量（优先 .env，其次 ../env/test.env）
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
elif [ -f "../env/test.env" ]; then
    echo "[信息] 未找到 .env，使用 ../env/test.env 配置"
    set -a
    source ../env/test.env
    set +a
fi

DEPLOY_MODE=${DEPLOY_MODE:-testing}
PORT=${PORT:-8000}
NAS_ROOT=${NAS_ROOT:-./nas}

echo ""
echo "========================================"
echo "  SecureTrans 启动"
echo "  部署模式: $DEPLOY_MODE"
echo "  存储目录: $NAS_ROOT"
echo "  访问地址: http://0.0.0.0:${PORT}"
echo "  初始管理员: admin / Admin@123"
if [ "$DEPLOY_MODE" = "testing" ]; then
    echo "  [测试模式] Flask自带服务器，适合开发和测试验证"
else
    echo "  [生产模式] 建议用 gunicorn 启动，不要用此脚本"
fi
echo "========================================"
echo ""
echo "按 Ctrl+C 停止服务"
echo ""

python app.py
