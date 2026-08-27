#!/bin/bash
# SecureTrans 生产环境启动脚本 (gunicorn)
# 用途：封闭数据中心正式部署，用 gunicorn WSGI 服务器
# 前置：已配置 .env（DEPLOY_MODE=production），NAS 已挂载
# 推荐：用 systemd 管理服务，此脚本用于手动启动验证
set -e

cd "$(dirname "$0")"

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "[错误] 未找到 venv，请先运行 start.sh 创建虚拟环境"
    exit 1
fi
source venv/bin/activate

# 检查 gunicorn
if ! command -v gunicorn &> /dev/null; then
    echo "[信息] 安装 gunicorn..."
    pip install gunicorn
fi

# 加载环境变量
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
fi

DEPLOY_MODE=${DEPLOY_MODE:-production}
PORT=${PORT:-8000}
WORKERS=${WORKERS:-4}

echo ""
echo "========================================"
echo "  SecureTrans 生产环境启动 (gunicorn)"
echo "  部署模式: $DEPLOY_MODE"
echo "  监听: 127.0.0.1:${PORT}"
echo "  Worker 进程数: $WORKERS"
echo "========================================"
echo ""

# gunicorn 启动
# -b: 绑定地址（生产环境只监听 127.0.0.1，由 nginx 反向代理）
# -w: worker 进程数（建议 CPU核数*2+1）
# --timeout: 超时时间（大文件上传需要较长时间）
# --access-logfile: 访问日志
# --error-logfile: 错误日志
exec gunicorn \
    -b 127.0.0.1:${PORT} \
    -w ${WORKERS} \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    app:app
