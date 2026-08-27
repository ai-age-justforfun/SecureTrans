#!/bin/bash
# ============================================================
# SecureTrans 一键部署脚本 (Linux)
# 适用：Ubuntu 20.04+ / Debian 11+ / CentOS 7+ / RHEL 8+ / Rocky 8+
# 用法：sudo bash deploy.sh
# 目录结构：infra/deploy.sh, src/ (源码), tests/ (测试)
# ============================================================
set -euo pipefail

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

INSTALL_DIR="/opt/securetrans"
SERVICE_USER="securetrans"
BACKUP_DIR="/opt/securetrans_backup_$(date +%Y%m%d_%H%M%S)"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$SCRIPT_DIR/../src"

echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}  SecureTrans 一键部署脚本${NC}"
echo -e "${GREEN}  安装目录: ${INSTALL_DIR}${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""

# ============================================================
# 0. 前置检查
# ============================================================
echo -e "${YELLOW}[0/9] 前置环境检查...${NC}"

# 检查 root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}错误: 请使用 root 或 sudo 运行此脚本${NC}"
    exit 1
fi

# 检查 Python 3.10+
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}错误: 未找到 python3，请先安装 Python 3.10+${NC}"
    echo "  Ubuntu/Debian: apt install python3 python3-venv python3-pip"
    echo "  CentOS/RHEL:   yum install python3"
    exit 1
fi

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    echo -e "${RED}错误: Python 版本过低 (${PY_VERSION})，需要 3.10+${NC}"
    exit 1
fi
echo -e "  Python 版本: ${PY_VERSION} ${GREEN}OK${NC}"

# 检查 python3-venv
if ! python3 -m venv --help &> /dev/null; then
    echo -e "${YELLOW}  警告: python3-venv 模块不可用，尝试安装...${NC}"
    if command -v apt &> /dev/null; then
        apt update -qq && apt install -y python3-venv
    elif command -v yum &> /dev/null; then
        yum install -y python3-virtualenv
    fi
fi

# 检查源码目录
if [ ! -d "$SRC_DIR" ]; then
    echo -e "${RED}错误: 未找到源码目录 ${SRC_DIR}${NC}"
    echo "  请确保在项目根目录下运行: bash infra/deploy.sh"
    exit 1
fi

# ============================================================
# 1. 创建服务用户
# ============================================================
echo -e "${YELLOW}[1/9] 创建服务用户 ${SERVICE_USER}...${NC}"
if ! id "$SERVICE_USER" &> /dev/null; then
    useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
    echo -e "  用户 ${SERVICE_USER} 已创建 ${GREEN}OK${NC}"
else
    echo -e "  用户 ${SERVICE_USER} 已存在，跳过 ${GREEN}OK${NC}"
fi

# ============================================================
# 2. 备份旧版本（如果存在）
# ============================================================
if [ -d "$INSTALL_DIR" ]; then
    echo -e "${YELLOW}[2/9] 检测到旧版本，备份到 ${BACKUP_DIR}...${NC}"
    mkdir -p "$(dirname "$BACKUP_DIR")"
    cp -a "$INSTALL_DIR" "$BACKUP_DIR"
    echo -e "  备份完成 ${GREEN}OK${NC}"
else
    echo -e "${YELLOW}[2/9] 无旧版本，跳过备份${NC}"
fi

# ============================================================
# 3. 复制程序文件
# ============================================================
echo -e "${YELLOW}[3/9] 复制程序文件到 ${INSTALL_DIR}...${NC}"
mkdir -p "$INSTALL_DIR"
cp -a "$SRC_DIR/." "$INSTALL_DIR/"

# 创建必要目录
mkdir -p "$INSTALL_DIR/data"
mkdir -p "$INSTALL_DIR/static"

echo -e "  程序文件已复制 ${GREEN}OK${NC}"

# ============================================================
# 4. 配置 .env
# ============================================================
echo -e "${YELLOW}[4/9] 配置环境变量...${NC}"
if [ ! -f "$INSTALL_DIR/.env" ]; then
    cp "$SRC_DIR/.env.production" "$INSTALL_DIR/.env"
    # 生成随机 SECRET_KEY
    RANDOM_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s/^SECRET_KEY=.*/SECRET_KEY=${RANDOM_KEY}/" "$INSTALL_DIR/.env"
    echo -e "  .env 已创建，SECRET_KEY 已随机生成 ${GREEN}OK${NC}"
    echo -e "  ${YELLOW}请编辑 ${INSTALL_DIR}/.env 修改 NAS_ROOT 等配置${NC}"
else
    echo -e "  .env 已存在，保留原有配置 ${GREEN}OK${NC}"
fi

# ============================================================
# 5. 创建 Python 虚拟环境并安装依赖
# ============================================================
echo -e "${YELLOW}[5/9] 创建虚拟环境并安装依赖...${NC}"
cd "$INSTALL_DIR"

if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "  虚拟环境已创建 ${GREEN}OK${NC}"
else
    echo -e "  虚拟环境已存在，跳过创建 ${GREEN}OK${NC}"
fi

source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
pip install gunicorn -q
deactivate
echo -e "  依赖安装完成（含 gunicorn） ${GREEN}OK${NC}"

# ============================================================
# 6. NAS 存储目录准备
# ============================================================
echo -e "${YELLOW}[6/9] 存储目录准备...${NC}"
# 从 .env 读取 NAS_ROOT
NAS_ROOT=$(grep -E '^NAS_ROOT=' "$INSTALL_DIR/.env" | cut -d= -f2)
NAS_ROOT="${NAS_ROOT:-/mnt/nas/securetrans}"

mkdir -p "$NAS_ROOT/staging" "$NAS_ROOT/external" "$NAS_ROOT/archive"
echo -e "  存储目录: ${NAS_ROOT}"
echo -e "  staging/external/archive 已创建 ${GREEN}OK${NC}"

# 验证同文件系统（os.rename 0拷贝前提）
STAGING_FS=$(df -P "$NAS_ROOT/staging" | tail -1 | awk '{print $1}')
EXTERNAL_FS=$(df -P "$NAS_ROOT/external" | tail -1 | awk '{print $1}')
ARCHIVE_FS=$(df -P "$NAS_ROOT/archive" | tail -1 | awk '{print $1}')
if [ "$STAGING_FS" = "$EXTERNAL_FS" ] && [ "$EXTERNAL_FS" = "$ARCHIVE_FS" ]; then
    echo -e "  三个目录在同一文件系统 (${STAGING_FS})，os.rename 0拷贝可用 ${GREEN}OK${NC}"
else
    echo -e "  ${RED}警告: 三个目录不在同一文件系统！os.rename 将退化为复制+删除${NC}"
    echo -e "  staging: ${STAGING_FS}, external: ${EXTERNAL_FS}, archive: ${ARCHIVE_FS}"
fi

# ============================================================
# 7. 设置权限
# ============================================================
echo -e "${YELLOW}[7/9] 设置文件权限...${NC}"
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
chown -R "$SERVICE_USER:$SERVICE_USER" "$NAS_ROOT"
chmod 750 "$INSTALL_DIR"
chmod 640 "$INSTALL_DIR/.env"
chmod 600 "$INSTALL_DIR/data/"*.db 2>/dev/null || true
echo -e "  权限设置完成 ${GREEN}OK${NC}"

# ============================================================
# 8. 安装 systemd 服务
# ============================================================
echo -e "${YELLOW}[8/9] 安装 systemd 服务...${NC}"
cp "$SCRIPT_DIR/securetrans.service" /etc/systemd/system/securetrans.service
systemctl daemon-reload
systemctl enable securetrans
echo -e "  systemd 服务已安装并设为开机自启 ${GREEN}OK${NC}"

# ============================================================
# 9. 启动服务并验证
# ============================================================
echo -e "${YELLOW}[9/9] 启动服务并验证...${NC}"
systemctl restart securetrans
sleep 3

# 检查服务状态
if systemctl is-active --quiet securetrans; then
    echo -e "  服务运行中 ${GREEN}OK${NC}"
else
    echo -e "  ${RED}服务启动失败！查看日志: journalctl -u securetrans -n 50${NC}"
    systemctl status securetrans --no-pager -l
    exit 1
fi

# 健康检查
sleep 2
HEALTH=$(curl -s http://127.0.0.1:8000/api/health 2>/dev/null || echo "FAILED")
if echo "$HEALTH" | grep -q '"status":"ok"'; then
    echo -e "  健康检查通过: ${HEALTH} ${GREEN}OK${NC}"
else
    echo -e "  ${YELLOW}健康检查未通过（可能启动较慢），返回: ${HEALTH}${NC}"
    echo -e "  ${YELLOW}请稍后手动检查: curl http://127.0.0.1:8000/api/health${NC}"
fi

echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}  部署完成！${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
echo "  安装目录:   ${INSTALL_DIR}"
echo "  配置文件:   ${INSTALL_DIR}/.env"
echo "  数据目录:   ${INSTALL_DIR}/data"
echo "  存储目录:   ${NAS_ROOT}"
echo "  服务状态:   systemctl status securetrans"
echo "  服务日志:   journalctl -u securetrans -f"
echo "  访问地址:   http://<服务器IP>:8000  (或通过 nginx 代理)"
echo "  初始账号:   admin / Admin@123  (首次登录强制修改密码)"
echo ""
echo -e "${YELLOW}  后续步骤:${NC}"
echo "  1. 编辑 .env 确认 NAS_ROOT 指向真实 NAS 挂载"
echo "  2. 配置 nginx 反向代理 (参考 infra/nginx-securetrans.conf)"
echo "  3. 运行全量测试: bash infra/verify.sh"
echo "  4. 登录系统修改 admin 初始密码"
echo ""
