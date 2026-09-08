#!/bin/bash
# ============================================================
# SecureTrans 离线 Python 获取脚本（Rocky 8 联网环境运行一次）
# 用法：sudo bash infra/get-offline-python.sh
# 产出：offline-python/*.rpm（python3.12 及其依赖）
# 用途：把生成的 offline-python/ 目录随部署包一同携带，
#       离线服务器上一键部署（deploy.sh）自动 dnf localinstall 安装 Python 3.12
# 前置：服务器可联网访问 Rocky 镜像源（repo.huaweicloud.com / mirrors.aliyun.com 等）
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUT_DIR="$PROJECT_ROOT/offline-python"

echo "============================================================"
echo "  SecureTrans 离线 Python 获取（python3.12 + 依赖 RPM）"
echo "  输出目录: ${OUT_DIR}"
echo "============================================================"

# 检查 root（dnf download 需要 root 缓存/权限）
if [ "$EUID" -ne 0 ]; then
    echo "提示: 需要 root 权限执行 dnf download（sudo 运行）"
    exit 1
fi

# 检查 dnf
if ! command -v dnf &>/dev/null; then
    echo "错误: 未找到 dnf（本脚本适用于 Rocky/RHEL 8+）"
    exit 1
fi

mkdir -p "$OUT_DIR"
cd "$OUT_DIR"

# 下载 python3.12 + pip + devel 及依赖 RPM（--resolve 自动拉全部依赖）
# Rocky 8 AppStream 直接提供 python3.12 包套件；若源缺失，先启用 EPEL 8:
#   dnf install -y epel-release
echo "[1/2] 下载 python3.12 + pip + devel 及依赖 RPM..."
dnf download --resolve --alldeps \
    python3.12 python3.12-pip python3.12-devel

echo "[2/2] 校验..."
COUNT=$(ls *.rpm 2>/dev/null | wc -l)
if [ "$COUNT" -eq 0 ]; then
    echo "错误: 未下载到任何 RPM，请检查网络/镜像源"
    exit 1
fi
ls -la *.rpm
echo ""
echo "============================================================"
echo "  完成！共 ${COUNT} 个 RPM"
echo "  将整个 offline-python/ 目录随部署包携带到离线服务器"
echo "  离线服务器执行: sudo bash infra/deploy.sh 即可自动安装"
echo "============================================================"
