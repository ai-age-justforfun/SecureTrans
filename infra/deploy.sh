#!/bin/bash
# ============================================================
# SecureTrans 一键部署脚本 (Linux) — v2.2.0
# 适用：Rocky 8/9/10、RHEL 8+、CentOS 7+、Ubuntu 20.04+、Debian 11+
# 用法：sudo bash infra/deploy.sh
# 一键完成：Python 3.12 自动获取 → venv → 依赖(离线/在线) → .env → systemd → 启动验证
#
# Python 3.12 获取优先级：
#   1. 系统已有 Python 3.10+（python3 / python3.12 / ...）→ 直接使用
#   2. 部署包根目录 offline-python/*.rpm（get-offline-python.sh 生成）→ dnf 离线安装
#   3. 在线 dnf module 安装（需网络，防火墙临时放行 80/443 访问镜像源）
# 离线依赖：部署包内置 offline-deps/（cp312 wheel），自动离线优先安装
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
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SRC_DIR="$PROJECT_ROOT/src"
OFFLINE_PYTHON_DIR="$PROJECT_ROOT/offline-python"   # 离线 Python RPM（可选，get-offline-python.sh 生成）
OFFLINE_DEPS_DIR="$PROJECT_ROOT/offline-deps"       # 离线 wheel（部署包内置）

echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}  SecureTrans 一键部署脚本${NC}"
echo -e "${GREEN}  安装目录: ${INSTALL_DIR}${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""

# ============================================================
# 0. 前置检查 + Python 3.10+ 自动获取
# ============================================================
echo -e "${YELLOW}[0/9] 前置环境检查 + Python 自动获取...${NC}"

# 检查 root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}错误: 请使用 root 或 sudo 运行此脚本${NC}"
    exit 1
fi

# 找 >=3.10 的系统 Python（3.12 优先，离线 wheel 按 cp312 打包）
find_python() {
    local cmd ver maj min
    for cmd in python3.12 python3.11 python3.10 python3; do
        if command -v "$cmd" &>/dev/null; then
            ver=$("$cmd" -c 'import sys;print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "0.0")
            maj=${ver%%.*}
            min=${ver#*.}; min=${min%%.*}
            if [ "$maj" -gt 3 ] || { [ "$maj" -eq 3 ] && [ "$min" -ge 10 ]; }; then
                echo "$cmd"; return 0
            fi
        fi
    done
    return 1
}
PY_CMD="$(find_python || true)"

if [ -z "$PY_CMD" ]; then
    echo -e "${YELLOW}  系统无 Python 3.10+，尝试获取 Python 3.12...${NC}"
    if ls "$OFFLINE_PYTHON_DIR"/*.rpm &>/dev/null 2>&1; then
        echo -e "${YELLOW}  [离线] 使用 offline-python/ 本地 RPM 安装 Python 3.12...${NC}"
        dnf localinstall -y "$OFFLINE_PYTHON_DIR"/*.rpm
    else
        echo -e "${YELLOW}  [在线] dnf 安装 Python 3.12（需网络；如未放行镜像请先在防火墙临时放行 80/443）...${NC}"
        echo -e "${YELLOW}        镜像参考: repo.huaweicloud.com / mirrors.aliyun.com / mirrors.rockylinux.org${NC}"
        # Rocky 8: AppStream 直接提供 python3.12 包套件（无需 module enable、无需源码编译）
        # 若 AppStream 缺失（老版本/精简源），兜底启用 EPEL 8
        dnf install -y python3.12 python3.12-pip python3.12-devel 2>/dev/null \
            || { dnf install -y epel-release && dnf install -y python3.12 python3.12-pip python3.12-devel; }
    fi
    if command -v python3.12 &>/dev/null; then
        alternatives --set python3 /usr/bin/python3.12 2>/dev/null || true
        PY_CMD="python3.12"
    fi
fi
PY_CMD="${PY_CMD:-python3}"
PY_VERSION=$("$PY_CMD" -c 'import sys;print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo -e "  Python: ${PY_CMD} (${PY_VERSION}) ${GREEN}OK${NC}"

# 版本匹配强化：离线 wheel 按 cp312 打包，若当前 Python 非 3.12 且部署包内有离线 3.12 RPM，
# 优先切换安装 3.12（保证与离线依赖一致），而不是降级用非 3.12
if [ "$PY_VERSION" != "3.12" ] && ls "$OFFLINE_PYTHON_DIR"/*.rpm &>/dev/null 2>&1; then
    echo -e "${YELLOW}  当前 Python 为 ${PY_VERSION}，检测到离线 Python 3.12 RPM，切换安装 3.12 以匹配离线 wheel (cp312)...${NC}"
    dnf localinstall -y "$OFFLINE_PYTHON_DIR"/*.rpm
    if command -v python3.12 &>/dev/null; then
        alternatives --set python3 /usr/bin/python3.12 2>/dev/null || true
        PY_CMD="python3.12"
        PY_VERSION=$("$PY_CMD" -c 'import sys;print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        echo -e "  Python 已切换: ${PY_CMD} (${PY_VERSION}) ${GREEN}OK${NC}"
    fi
fi

# 兼容性提示：内置离线 wheel 按 cp312 打包，若 Python 非 3.12 且离线安装失败请改用 3.12
if [ -d "$OFFLINE_DEPS_DIR" ] && [ "$PY_VERSION" != "3.12" ]; then
    echo -e "${YELLOW}  提示: 内置离线 wheel 按 Python 3.12 (cp312) 打包，当前为 ${PY_VERSION}${NC}"
    echo -e "${YELLOW}        如离线安装失败，请将 offline-python/ 的 Python 3.12 RPM 放入部署包或联网安装${NC}"
fi

# 检查 venv 模块
if ! "$PY_CMD" -m venv --help &>/dev/null 2>&1; then
    echo -e "${YELLOW}  venv 模块不可用，尝试安装...${NC}"
    if command -v dnf &>/dev/null; then
        dnf install -y python3.12-pip 2>/dev/null || true
    elif command -v apt &>/dev/null; then
        apt update -qq && apt install -y python3-venv
    fi
fi

# AD 手工验证依赖（openldap-clients 提供 ldapsearch；离线环境需提前准备 RPM，未装不影响系统运行）
if command -v dnf &>/dev/null && ! command -v ldapsearch &>/dev/null; then
    echo -e "${YELLOW}  ldapsearch 未安装（AD 手工验证用），尝试安装 openldap-clients ...${NC}"
    dnf install -y openldap-clients 2>/dev/null || echo -e "${YELLOW}  openldap-clients 安装失败（离线？），可在 AD 配置页使用「测试连接」替代手工 ldapsearch${NC}"
elif command -v apt &>/dev/null && ! command -v ldapsearch &>/dev/null; then
    apt install -y ldap-utils 2>/dev/null || echo -e "${YELLOW}  ldap-utils 安装失败（离线？），可在 AD 配置页使用「测试连接」替代手工 ldapsearch${NC}"
fi

# 检查源码目录
if [ ! -d "$SRC_DIR" ]; then
    echo -e "${RED}错误: 未找到源码目录 ${SRC_DIR}（请在项目根目录运行: sudo bash infra/deploy.sh）${NC}"
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
# 3.5 保护生产 .env 不被本地开发配置覆盖（src/.env 为 testing 配置）
if [ -f "$INSTALL_DIR/.env" ]; then
    cp -a "$INSTALL_DIR/.env" "$INSTALL_DIR/.env.deploybak"
fi
# 用 tar 排除本地开发产物（.env/data/nas/venv 等），避免覆盖生产配置/数据库/venv
tar --exclude='./.env' --exclude='./.env.*' --exclude='./data' --exclude='./nas' \
    --exclude='./venv' --exclude='./server_err.log' --exclude='./start.bat' \
    -C "$SRC_DIR" -cf - . | tar -C "$INSTALL_DIR" -xf -
if [ -f "$INSTALL_DIR/.env.deploybak" ]; then
    mv "$INSTALL_DIR/.env.deploybak" "$INSTALL_DIR/.env"
fi
mkdir -p "$INSTALL_DIR/data"
echo -e "  程序文件已复制 ${GREEN}OK${NC}"

# ============================================================
# 4. 配置 .env
# ============================================================
echo -e "${YELLOW}[4/9] 配置环境变量...${NC}"
if [ ! -f "$INSTALL_DIR/.env" ]; then
    cp "$SRC_DIR/.env.production" "$INSTALL_DIR/.env"
    RANDOM_KEY=$("$PY_CMD" -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s/^SECRET_KEY=.*/SECRET_KEY=${RANDOM_KEY}/" "$INSTALL_DIR/.env"
    echo -e "  .env 已创建，SECRET_KEY 已随机生成 ${GREEN}OK${NC}"
    echo -e "  ${YELLOW}请编辑 ${INSTALL_DIR}/.env 修改 NAS_ROOT、INTERNAL_CIDRS 等配置${NC}"
else
    echo -e "  .env 已存在，保留原有配置 ${GREEN}OK${NC}"
fi

# ============================================================
# 4.6 确保 .env 含 RESET_PASSWORD 行（缺失时追加，值默认 Init@123456；与 app.py 默认一致，
#     保证 verify.sh 凭据与部署重置后的 admin 密码同源）
if ! grep -qE '^RESET_PASSWORD=' "$INSTALL_DIR/.env" 2>/dev/null; then
    echo "RESET_PASSWORD=Init@123456" >> "$INSTALL_DIR/.env"
    echo -e "  .env 缺失 RESET_PASSWORD，已追加默认值 Init@123456 ${YELLOW}(可编辑修改)${NC}"
fi

# 4.5 解析 NAS_ROOT（环境变量可覆盖，并写回 .env 保持 app/service 一致）
# ============================================================
# .env 统一转 LF：Windows 编辑/CRLF 模板会导致 NAS_ROOT 值带 \r，
# 创建"异形目录"(securetrans$'\r')，且 systemd 239 ReadWritePaths 含 \r 路径报 226/NAMESPACE
sed -i 's/\r$//' "$INSTALL_DIR/.env"
if [ -n "${NAS_ROOT:-}" ]; then
    NAS_ROOT=$(printf '%s' "$NAS_ROOT" | tr -d '\r')
    echo -e "${YELLOW}[4.5/9] NAS_ROOT 环境变量覆盖: ${NAS_ROOT}（写回 .env）...${NC}"
    sed -i "s|^NAS_ROOT=.*|NAS_ROOT=${NAS_ROOT}|" "$INSTALL_DIR/.env"
fi
NAS_ROOT=$(grep -E '^NAS_ROOT=' "$INSTALL_DIR/.env" | cut -d= -f2 | tr -d '\r')
NAS_ROOT="${NAS_ROOT:-/mnt/nas/securetrans}"

# ============================================================
# 5. 创建 Python 虚拟环境并安装依赖（离线优先）
# ============================================================
echo -e "${YELLOW}[5/9] 创建虚拟环境并安装依赖...${NC}"
cd "$INSTALL_DIR"
if [ ! -d "venv" ]; then
    echo -e "  创建 venv（Python ${PY_VERSION}，--copies 与系统完全隔离）..."
    "$PY_CMD" -m venv --copies venv
    echo -e "  虚拟环境已创建 ${GREEN}OK${NC}"
else
    echo -e "  虚拟环境已存在，跳过创建 ${GREEN}OK${NC}"
fi

# 校验 venv 内 Python 版本（离线 wheel 按 cp312 打包，须为 3.12）
VVER=$(venv/bin/python -c 'import sys;print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if [ "$VVER" != "3.12" ]; then
    echo -e "${YELLOW}  提示: venv Python 为 ${VVER}，与离线 wheel (cp312) 不一致；如离线安装失败请用 Python 3.12 重建 venv（删除 venv/ 后重跑）${NC}"
else
    echo -e "  venv Python: ${VVER}（匹配 cp312） ${GREEN}OK${NC}"
fi

source venv/bin/activate
if [ -d "$OFFLINE_DEPS_DIR" ]; then
    echo -e "  [离线] 使用内置离线 wheel (offline-deps/) 安装..."
    pip install --no-index --find-links="$OFFLINE_DEPS_DIR" -r requirements.txt -q
    pip install --no-index --find-links="$OFFLINE_DEPS_DIR" gunicorn==21.2.0 -q
else
    echo -e "  [在线] 联网安装依赖（需网络）..."
    pip install --upgrade pip -q
    pip install -r requirements.txt -q
    pip install gunicorn -q
fi
deactivate
echo -e "  依赖安装完成（含 gunicorn） ${GREEN}OK${NC}"

# ============================================================
# 6. NAS 存储目录准备
# ============================================================
echo -e "${YELLOW}[6/9] 存储目录准备...${NC}"
mkdir -p "$NAS_ROOT/staging" "$NAS_ROOT/external" "$NAS_ROOT/archive"
echo -e "  存储目录: ${NAS_ROOT}"

STAGING_FS=$(df -P "$NAS_ROOT/staging" | tail -1 | awk '{print $1}')
EXTERNAL_FS=$(df -P "$NAS_ROOT/external" | tail -1 | awk '{print $1}')
ARCHIVE_FS=$(df -P "$NAS_ROOT/archive" | tail -1 | awk '{print $1}')
if [ "$STAGING_FS" = "$EXTERNAL_FS" ] && [ "$EXTERNAL_FS" = "$ARCHIVE_FS" ]; then
    echo -e "  同文件系统 (${STAGING_FS})，os.rename 0拷贝可用 ${GREEN}OK${NC}"
else
    echo -e "  ${RED}警告: 三目录不在同一文件系统！os.rename 将退化为复制+删除${NC}"
fi

# ============================================================
# 7. 设置权限
# ============================================================
echo -e "${YELLOW}[7/9] 设置文件权限...${NC}"
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
chown -R "$SERVICE_USER:$SERVICE_USER" "$NAS_ROOT" 2>/dev/null || true
chmod 750 "$INSTALL_DIR"
chmod 640 "$INSTALL_DIR/.env"
echo -e "  权限设置完成 ${GREEN}OK${NC}"

# ============================================================
# 8. 安装 systemd 服务
# ============================================================
echo -e "${YELLOW}[8/9] 安装 systemd 服务...${NC}"
cp "$SCRIPT_DIR/securetrans.service" /etc/systemd/system/securetrans.service
# ReadWritePaths 只保留存在的路径：systemd 239（RHEL8/Rocky8）对不存在的路径报 226/NAMESPACE
# （如 NAS 未挂载时 /mnt/nas/securetrans 不存在）；NAS 挂载后重跑部署自动补全
RW_PATHS="/opt/securetrans"
if [ -n "$NAS_ROOT" ] && [ -d "$NAS_ROOT" ]; then
    RW_PATHS="$RW_PATHS $NAS_ROOT"
else
    echo -e "  NAS_ROOT ($NAS_ROOT) 不存在或未挂载，ReadWritePaths 仅保留 /opt/securetrans（挂载后重跑部署更新）"
fi
sed -i "s|__RW_PATHS__|${RW_PATHS}|" /etc/systemd/system/securetrans.service
# gunicorn 绑定地址由 systemd 变量展开（ExecStart 中 ${HOST}:${PORT}，读 EnvironmentFile .env），
# 改 .env 的 HOST/PORT 后 systemctl restart securetrans 即生效，无需重跑部署
systemctl daemon-reload
systemctl enable securetrans
echo -e "  systemd 服务已安装并设为开机自启（ReadWritePaths=${NAS_ROOT}） ${GREEN}OK${NC}"

# ============================================================
# 9. 启动服务并验证
# ============================================================
echo -e "${YELLOW}[9/9] 启动服务并验证...${NC}"
systemctl restart securetrans
sleep 3

if systemctl is-active --quiet securetrans; then
    echo -e "  服务运行中 ${GREEN}OK${NC}"
else
    echo -e "  ${RED}服务启动失败！查看日志: journalctl -u securetrans -n 50${NC}"
    systemctl status securetrans --no-pager -l
    exit 1
fi

sleep 2
# 健康检查目标从 .env HOST/PORT 自适应（HOST=具体IP 时 loopback 不可达）
ENV_HOST=$(grep -E '^HOST=' "$INSTALL_DIR/.env" 2>/dev/null | cut -d= -f2 | tr -d '\r' | head -1 || true)
ENV_PORT=$(grep -E '^PORT=' "$INSTALL_DIR/.env" 2>/dev/null | cut -d= -f2 | tr -d '\r' | head -1 || true)
ENV_PORT="${ENV_PORT:-8000}"
case "$ENV_HOST" in
    ""|0.0.0.0|127.0.0.1|localhost) HEALTH_URL="http://127.0.0.1:${ENV_PORT}" ;;
    *) HEALTH_URL="http://${ENV_HOST}:${ENV_PORT}" ;;
esac
HEALTH=$(curl -s "${HEALTH_URL}/api/health" 2>/dev/null || echo "FAILED")
if echo "$HEALTH" | tr -d "\n" | grep -q '"status":"ok"'; then
    echo -e "  健康检查通过: ${HEALTH} ${GREEN}OK${NC}"
else
    echo -e "  ${YELLOW}健康检查未通过（可能启动较慢）: ${HEALTH}${NC}"

# ============================================================
# 9.5 preflight 自检（模拟 systemd 239 严格行为：ReadWritePaths 路径必须全部存在且无 CR）
# 在 WSL/本地测试环境跑通后，服务器生产环境行为一致
# ============================================================
echo -e "${YELLOW}[9.5/9] preflight 自检（ReadWritePaths 路径存在性 + 无 CR）...${NC}"
PRE_FAIL=0
# 1) .env 无 CR（CRLF 行尾会污染 NAS_ROOT 值，创建异形目录）
if grep -q $'\r' "$INSTALL_DIR/.env"; then
    echo -e "  ${RED}[FAIL] .env 含 CR 字符（CRLF 行尾）${NC}"
    PRE_FAIL=1
fi
# 2) service 最终产物无 CR 且每个路径存在（257 会忽略不存在路径，239 严格报 226——WSL 不能复现，此检查兜底）
RWP=$(grep '^ReadWritePaths=' /etc/systemd/system/securetrans.service | cut -d= -f2)
if echo "$RWP" | grep -q $'\r'; then
    echo -e "  ${RED}[FAIL] ReadWritePaths 含 CR 字符${NC}"
    PRE_FAIL=1
fi
for p in $RWP; do
    if [ ! -d "$p" ]; then
        echo -e "  ${RED}[FAIL] ReadWritePaths 路径不存在: $p（systemd 239 将报 226/NAMESPACE）${NC}"
        echo -e "  ${YELLOW}  解决: 挂载 NAS / 创建目录后重跑 deploy.sh${NC}"
        PRE_FAIL=1
    fi
done
if [ "$PRE_FAIL" -eq 0 ]; then
    echo -e "  ReadWritePaths: $RWP ${GREEN}全部存在且无 CR OK${NC}"
else
    echo -e "  ${RED}preflight 未通过，请修复后重跑部署（切勿直接上服务器生产环境）${NC}"
    exit 1
fi
fi

echo ""
# ============================================================
# 9.6 防火墙放行 ${ENV_PORT}/tcp（内网 + 办公外网 Alpha 访问）
# ============================================================
echo -e "${YELLOW}[9.6/9] 防火墙放行 ${ENV_PORT}/tcp...${NC}"
if command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld 2>/dev/null; then
    firewall-cmd --permanent --add-port=${ENV_PORT}/tcp >/dev/null 2>&1
    firewall-cmd --reload >/dev/null 2>&1
    if firewall-cmd --list-ports 2>/dev/null | grep -q "${ENV_PORT}/tcp"; then
        echo -e "  已放行 ${ENV_PORT}/tcp ${GREEN}OK${NC}"
    else
        echo -e "  ${YELLOW}放行命令已执行但列表未确认，请检查: firewall-cmd --list-all${NC}"
    fi
else
    echo -e "  ${YELLOW}未检测到 firewalld（或未启用），跳过防火墙配置；如需放行请按 DEPLOY.md 阶段7 手工执行${NC}"
fi

# 9.7 重置 admin 密码为 .env RESET_PASSWORD（每次部署重置，保证 verify 与首次登录凭据一致；
#     界面"重置密码"显示值与 .env RESET_PASSWORD 同源，登录后请立即修改）
#     fix(v2.2.21)：显式把 .env RESET_PASSWORD 传入 CLI 环境——app.py 不自动读 .env，
#     此前用代码默认 Init@123456 重置，若 .env 配了其他值会与 verify.sh 凭据(grep .env)不一致导致 401
echo -e "${YELLOW}[9.7/9] 重置 admin 密码为 RESET_PASSWORD（.env）...${NC}"
ENV_RESET_PWD=$(grep -E '^RESET_PASSWORD=' "$INSTALL_DIR/.env" 2>/dev/null | cut -d= -f2 | tr -d '\r' | head -1 || true)
ENV_RESET_PWD="${ENV_RESET_PWD:-Init@123456}"
if [ -x "$INSTALL_DIR/venv/bin/python" ]; then
    RESET_PY="$INSTALL_DIR/venv/bin/python"
else
    RESET_PY="$PY_CMD"
fi
(cd "$INSTALL_DIR/src" && RESET_PASSWORD="$ENV_RESET_PWD" "$RESET_PY" app.py --reset-admin-password 2>/dev/null | grep "admin 密码已重置" || echo "  (admin 用户不存在，跳过)")
echo -e "  admin 密码 = ${ENV_RESET_PWD}（.env RESET_PASSWORD），登录后建议尽快修改（不强制） ${GREEN}OK${NC}"

# 9.8 可选出厂重置（ADR-011）：测试环境部署时清空老库恢复出厂状态
#     触发方式：RESET_DB=1 bash deploy.sh（生产环境默认不触发；按需重置用 infra/ops-reset.sh 或系统工具页）
if [ "${RESET_DB:-0}" = "1" ]; then
    echo -e "${YELLOW}[9.8/9] 出厂重置（RESET_DB=1：清空业务数据恢复出厂，原数据自动备份）...${NC}"
    if (cd "$INSTALL_DIR/src" && RESET_PASSWORD="$ENV_RESET_PWD" "$RESET_PY" app.py --reset-factory 2>/dev/null | grep -q "已重置出厂"); then
        echo -e "  出厂重置完成：业务数据已清空（原数据在 data/backups/），admin 密码 = ${ENV_RESET_PWD} ${GREEN}OK${NC}"
    else
        echo -e "  ${YELLOW}(出厂重置未执行/失败，请检查日志；不影响服务启动)${NC}"
    fi
fi

echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}  部署完成！${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
echo "  安装目录:   ${INSTALL_DIR}"
echo "  配置文件:   ${INSTALL_DIR}/.env"
echo "  存储目录:   ${NAS_ROOT}"
echo "  访问地址:   http://<服务器IP>:${ENV_PORT}  (或通过 nginx 代理)"
echo "  初始账号:   admin / ${ENV_RESET_PWD}  (每次部署重置为 .env RESET_PASSWORD，登录后建议尽快修改（不强制）)"
echo ""
echo -e "${YELLOW}  后续步骤:${NC}"
echo "  1. 编辑 .env 确认 NAS_ROOT / INTERNAL_CIDRS（单网卡按网段隔离时）"
echo "  2. 配置 nginx 反向代理（单/双网卡模板见 infra/nginx-securetrans-*.conf）"
echo "  3. 全量验证: sudo bash infra/verify.sh  (193项，自动使用 RESET_PASSWORD 凭据)"
echo "  4. 登录系统修改 admin 初始密码（修改后 verify 需 VERIFY_ADMIN_PASS 显式传参，见 DEPLOY.md）"
echo ""
