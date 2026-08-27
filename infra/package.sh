#!/bin/bash
# ============================================================
# SecureTrans 一键打包脚本
# 用途：将源代码+测试+部署脚本打包为生产环境部署包
# 用法：bash package.sh [版本号]
# 输出：securetrans-<版本>.tar.gz
# ============================================================
set -euo pipefail

VERSION="${1:-1.5.0}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="/tmp/securetrans-build"
PACKAGE_NAME="securetrans-${VERSION}"

echo "============================================================"
echo "  SecureTrans 一键打包"
echo "  版本: ${VERSION}"
echo "  项目根目录: ${PROJECT_ROOT}"
echo "============================================================"
echo ""

# 1. 清理构建目录
echo "[1/6] 清理构建目录..."
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR/$PACKAGE_NAME"

# 2. 复制源代码
echo "[2/6] 复制源代码..."
cp -r "$PROJECT_ROOT/src" "$BUILD_DIR/$PACKAGE_NAME/"

# 3. 复制测试脚本
echo "[3/6] 复制测试脚本..."
cp -r "$PROJECT_ROOT/tests" "$BUILD_DIR/$PACKAGE_NAME/"

# 4. 复制部署脚本和配置
echo "[4/6] 复制部署脚本和配置..."
cp -r "$PROJECT_ROOT/infra" "$BUILD_DIR/$PACKAGE_NAME/"

# 5. 复制文档
echo "[5/6] 复制文档..."
mkdir -p "$BUILD_DIR/$PACKAGE_NAME/docs"
cp "$PROJECT_ROOT/docs/DEPLOY.md" "$BUILD_DIR/$PACKAGE_NAME/docs/"
cp "$PROJECT_ROOT/docs/06-test-report.md" "$BUILD_DIR/$PACKAGE_NAME/docs/" 2>/dev/null || true
cp "$PROJECT_ROOT/README.md" "$BUILD_DIR/$PACKAGE_NAME/"
cp "$PROJECT_ROOT/LICENSE" "$BUILD_DIR/$PACKAGE_NAME/"

# 6. 清理不需要的文件并打包
echo "[6/6] 清理并打包..."
cd "$BUILD_DIR"

# 清理 venv、数据、日志、临时文件
find "$PACKAGE_NAME" -type d -name "venv" -exec rm -rf {} + 2>/dev/null || true
find "$PACKAGE_NAME" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$PACKAGE_NAME" -type d -name "data" -exec rm -rf {} + 2>/dev/null || true
find "$PACKAGE_NAME" -type d -name "nas" -exec rm -rf {} + 2>/dev/null || true
find "$PACKAGE_NAME" -name ".env" -type f -delete 2>/dev/null || true
find "$PACKAGE_NAME" -name "*.pyc" -delete 2>/dev/null || true
find "$PACKAGE_NAME" -name "*.log" -delete 2>/dev/null || true
find "$PACKAGE_NAME" -name ".git" -type d -exec rm -rf {} + 2>/dev/null || true

# 确保 shell 脚本 LF 换行
find "$PACKAGE_NAME" -name "*.sh" -exec sed -i 's/\r$//' {} \;

# 打包
tar czf "${PACKAGE_NAME}.tar.gz" "$PACKAGE_NAME"

# 计算大小和 MD5
SIZE=$(du -h "${PACKAGE_NAME}.tar.gz" | cut -f1)
MD5=$(md5sum "${PACKAGE_NAME}.tar.gz" | cut -d' ' -f1)

# 复制到项目根目录
cp "${PACKAGE_NAME}.tar.gz" "$PROJECT_ROOT/"

echo ""
echo "============================================================"
echo "  打包完成！"
echo "============================================================"
echo "  文件名: ${PACKAGE_NAME}.tar.gz"
echo "  大小:   ${SIZE}"
echo "  MD5:    ${MD5}"
echo "  位置:   ${PROJECT_ROOT}/${PACKAGE_NAME}.tar.gz"
echo ""
echo "  部署包内容:"
echo "    src/          源代码 (Flask + 前端)"
echo "    tests/        自动化测试 (51项)"
echo "    infra/        部署脚本 (deploy.sh/verify.sh/nginx/systemd)"
echo "    docs/         部署指南 + 测试报告"
echo "    README.md     项目说明"
echo "    LICENSE       MIT许可证"
echo ""
echo "  部署方法:"
echo "    1. 上传 ${PACKAGE_NAME}.tar.gz 到服务器"
echo "    2. tar xzf ${PACKAGE_NAME}.tar.gz"
echo "    3. cd ${PACKAGE_NAME}"
echo "    4. sudo bash infra/deploy.sh"
echo "    5. bash infra/verify.sh"
echo "============================================================"
