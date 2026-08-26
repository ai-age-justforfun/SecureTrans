#!/bin/bash
# SecureTrans 启动脚本 (Linux)
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

# 加载环境变量
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
fi

PORT=${PORT:-8000}
NAS_ROOT=${NAS_ROOT:-./nas}
echo "[信息] 存储目录: $NAS_ROOT"
echo "[信息] 启动 SecureTrans 服务..."
echo "[信息] 访问地址: http://0.0.0.0:${PORT}"
echo "[信息] 初始管理员: admin / Admin@123"
echo "[信息] 按 Ctrl+C 停止服务"
echo ""

python app.py
