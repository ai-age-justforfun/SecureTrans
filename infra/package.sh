#!/bin/bash
# ============================================================
# SecureTrans 一键打包脚本（发布用）
# 用途：将源代码+测试+部署脚本+文档+离线依赖打包为生产环境部署包
# 用法：bash infra/package.sh [版本号]
# 输出：securetrans-<版本>.tar.gz（含内置 offline-deps 离线 wheel）
# 依赖：packages/securetrans-offline-deps.tar.gz（离线依赖包）
# ============================================================
set -euo pipefail

VERSION="${1:-1.5.0}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="/tmp/securetrans-build"
PACKAGE_NAME="securetrans-${VERSION}"
OFFLINE_DEPS="$PROJECT_ROOT/packages/securetrans-offline-deps.tar.gz"

echo "============================================================"
echo "  SecureTrans 一键打包（发布 v${VERSION}）"
echo "  项目根目录: ${PROJECT_ROOT}"
echo "============================================================"
echo ""

# 0. 检查离线依赖包
if [ ! -f "$OFFLINE_DEPS" ]; then
    echo "[错误] 未找到离线依赖包: ${OFFLINE_DEPS}"
    echo "  请先在 WSL/Linux 环境生成:"
    echo "  pip download --only-binary=:all: --platform manylinux2014_x86_64 \\"
    echo "      --python-version 312 --implementation cp --abi cp312 \\"
    echo "      flask==3.0.0 flask-login==0.6.3 bcrypt==4.1.2 apscheduler==3.10.4 \\"
    echo "      ldap3==2.9.1 gunicorn==21.2.0 waitress==3.0.0 -d <dir>"
    exit 1
fi

# 1. 清理构建目录
echo "[1/7] 清理构建目录..."
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR/$PACKAGE_NAME"

# 2. 复制源代码
echo "[2/7] 复制源代码..."
cp -r "$PROJECT_ROOT/src" "$BUILD_DIR/$PACKAGE_NAME/"

# 3. 复制测试脚本
echo "[3/7] 复制测试脚本..."
cp -r "$PROJECT_ROOT/tests" "$BUILD_DIR/$PACKAGE_NAME/"

# 4. 复制部署脚本和配置
echo "[4/7] 复制部署脚本和配置..."
cp -r "$PROJECT_ROOT/infra" "$BUILD_DIR/$PACKAGE_NAME/"

# 5. 复制文档（全部 docs）与根文档
echo "[5/7] 复制文档..."
cp -r "$PROJECT_ROOT/docs" "$BUILD_DIR/$PACKAGE_NAME/docs"
cp "$PROJECT_ROOT/README.md" "$BUILD_DIR/$PACKAGE_NAME/"
cp "$PROJECT_ROOT/LICENSE" "$BUILD_DIR/$PACKAGE_NAME/"
cp "$PROJECT_ROOT/AGENTS.md" "$BUILD_DIR/$PACKAGE_NAME/" 2>/dev/null || true

# 5.5 内置离线 Python（可选，get-offline-python.sh 生成；服务器一键部署自动安装）
if [ -d "$PROJECT_ROOT/offline-python" ] && ls "$PROJECT_ROOT"/offline-python/*.rpm &>/dev/null 2>&1; then
    cp -r "$PROJECT_ROOT/offline-python" "$BUILD_DIR/$PACKAGE_NAME/offline-python"
    echo "  已内置离线 Python RPM ($(ls "$PROJECT_ROOT"/offline-python/*.rpm | wc -l) 个)"
else
    echo "  [提示] 未找到 offline-python/（联网 Rocky8 运行 infra/get-offline-python.sh 生成，随包离线携带）"
fi
if [ -d "$PROJECT_ROOT/offline-python-win" ] && ls "$PROJECT_ROOT"/offline-python-win/*.exe &>/dev/null 2>&1; then
    cp -r "$PROJECT_ROOT/offline-python-win" "$BUILD_DIR/$PACKAGE_NAME/offline-python-win"
    echo "  已内置 Windows 离线 Python 安装器"
fi

# 6. 内置离线依赖 wheel
echo "[6/7] 内置离线依赖 (offline-deps)..."
mkdir -p "$BUILD_DIR/$PACKAGE_NAME/offline-deps"
tar xzf "$OFFLINE_DEPS" -C "$BUILD_DIR/$PACKAGE_NAME/offline-deps" --strip-components=1
WHEEL_COUNT=$(ls "$BUILD_DIR/$PACKAGE_NAME/offline-deps"/*.whl 2>/dev/null | wc -l) || true
echo "  已内置 ${WHEEL_COUNT} 个 wheel"

# Windows 离线依赖（双平台部署支持，可选）
OFFLINE_DEPS_WIN="$PROJECT_ROOT/packages/offline-deps-win.tar.gz"
if [ -f "$OFFLINE_DEPS_WIN" ]; then
    mkdir -p "$BUILD_DIR/$PACKAGE_NAME/offline-deps-win"
    tar xzf "$OFFLINE_DEPS_WIN" -C "$BUILD_DIR/$PACKAGE_NAME/offline-deps-win" --strip-components=1
    WHEEL_COUNT_WIN=$(ls "$BUILD_DIR/$PACKAGE_NAME/offline-deps-win"/wheelhouse/*.whl 2>/dev/null | wc -l) || true
    echo "  已内置 Windows 离线依赖 ${WHEEL_COUNT_WIN} 个 wheel"
else
    echo "  [提示] 未找到 Windows 离线依赖包，跳过（Windows 部署将在线安装）"
fi

# 7. 清理并打包
echo "[7/7] 清理并打包..."
cd "$BUILD_DIR"

# 清理 venv、数据、日志、临时文件、git
find "$PACKAGE_NAME" -type d -name "venv" -exec rm -rf {} + 2>/dev/null || true
find "$PACKAGE_NAME" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$PACKAGE_NAME" -type d -name "data" -exec rm -rf {} + 2>/dev/null || true
find "$PACKAGE_NAME" -type d -name "nas" -exec rm -rf {} + 2>/dev/null || true
find "$PACKAGE_NAME" -name ".env" -type f -delete 2>/dev/null || true
find "$PACKAGE_NAME" -name "*.pyc" -delete 2>/dev/null || true
find "$PACKAGE_NAME" -name "*.log" -delete 2>/dev/null || true
find "$PACKAGE_NAME" -name ".git" -type d -exec rm -rf {} + 2>/dev/null || true

# 确保 shell 脚本 LF 换行（Windows 编辑过的 CRLF 会破坏 Linux 脚本）
find "$PACKAGE_NAME" -name "*.sh" -exec sed -i 's/\r$//' {} \;

# 打包
tar czf "${PACKAGE_NAME}.tar.gz" "$PACKAGE_NAME"

# 计算校验和
SIZE=$(du -h "${PACKAGE_NAME}.tar.gz" | cut -f1)
MD5=$(md5sum "${PACKAGE_NAME}.tar.gz" | cut -d' ' -f1)
SHA256=$(sha256sum "${PACKAGE_NAME}.tar.gz" | cut -d' ' -f1)

# 复制到项目根目录 packages/
mkdir -p "$PROJECT_ROOT/packages"
cp "${PACKAGE_NAME}.tar.gz" "$PROJECT_ROOT/packages/"
echo "${MD5}" > "$PROJECT_ROOT/packages/${PACKAGE_NAME}.tar.gz.md5"
echo "${SHA256}" > "$PROJECT_ROOT/packages/${PACKAGE_NAME}.tar.gz.sha256"

echo ""
echo "============================================================"
echo "  打包完成（发布 v${VERSION}）！"
echo "============================================================"
echo "  文件名: ${PACKAGE_NAME}.tar.gz"
echo "  大小:   ${SIZE}"
echo "  MD5:    ${MD5}"
echo "  SHA256: ${SHA256}"
echo "  位置:   ${PROJECT_ROOT}/packages/"
echo ""
echo "  部署包内容:"
echo "    src/          源代码 (Flask + 前端)"
echo "    tests/        自动化测试 (250项)"
echo "    infra/        部署脚本 (deploy.sh/verify.sh/nginx/systemd)"
echo "    docs/         全部文档（含唯一部署指南 DEPLOY.md）"
echo "    offline-deps/ 离线 wheel 依赖 (${WHEEL_COUNT}个, Linux x86_64 / py3.12)"
echo "    offline-deps-win/ Windows 离线 wheel 依赖 (cp312 win_amd64)"
echo "    offline-python/ 离线 Python 3.12 RPM (可选, get-offline-python.sh 生成)"
echo "    README/LICENSE/AGENTS.md"
echo ""
echo "  部署方法（Rocky 8.10, 见 docs/DEPLOY.md 分阶段执行手册）:"
echo "    1. 上传 ${PACKAGE_NAME}.tar.gz 到服务器"
echo "    2. tar xzf ${PACKAGE_NAME}.tar.gz -C /opt/securetrans --strip-components=1"
echo "    3. 离线装依赖: pip install --no-index --find-links=offline-deps -r requirements.txt"
echo "    4. 分阶段验证: testing → production → NAS → 双网卡 → 手工验收"
echo "============================================================"
