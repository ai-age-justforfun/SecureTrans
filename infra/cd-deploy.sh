#!/bin/bash
# ============================================================
# SecureTrans CD 部署脚本（服务器侧执行，ADR-024 / ADR-043）
# 用途：Gitea Release 发布后，由 CD job（WSL act_runner 容器）经 SSH 调用本脚本，
#       完成生产服务器的轻量升级。部署形态自动检测（ADR-043）：
#       - Docker 形态（securetrans-docker 容器存在 或 原生 systemd 未运行）：加载镜像 → 起容器 → 内网只读冒烟
#       - 原生形态（回退）：systemd 轻量升级 → 重启 → 只读冒烟
# 用法：bash cd-deploy.sh <版本号>   （发布包 + 镜像包须已上传到 /opt/securetrans-release/）
# 前置：securetrans-<版本>.tar.gz 与 securetrans-<版本>-image.tar.gz 已 scp 到 /opt/securetrans-release/
# 安全：不重置 admin 密码、不重建 venv、不覆盖生产数据；生产只跑只读冒烟（ADR-017/024）
# ============================================================
set -euo pipefail

VER="${1:?用法: bash cd-deploy.sh <版本号>}"
VNO="${VER#v}"
REL_DIR="/opt/securetrans-release"
PKG="${REL_DIR}/securetrans-${VNO}.tar.gz"
IMG="${REL_DIR}/securetrans-${VNO}-image.tar.gz"
SRC_DIR="${REL_DIR}/securetrans-${VNO}"
INSTALL_DIR="/opt/securetrans"
SERVICE="securetrans"

echo "============================================================"
echo "  SecureTrans CD 部署 | 版本: ${VER}"
echo "============================================================"

# 0. 发布包存在性
[ -f "$PKG" ] || { echo "[错误] 发布包不存在: ${PKG}"; exit 1; }

# 1. 解压（幂等：已解压则跳过）
if [ ! -f "${SRC_DIR}/src/app.py" ]; then
  mkdir -p "${SRC_DIR}"
  echo "[1/6] 解压发布包..."
  tar xzf "${PKG}" -C "${REL_DIR}" --strip-components=1 --one-top-level="${SRC_DIR}" 2>/dev/null \
    || { mkdir -p "${SRC_DIR}/src"; tar xzf "${PKG}" -C "${SRC_DIR}/src" --strip-components=1; }
fi
[ -f "${SRC_DIR}/src/app.py" ] || { echo "[错误] 解压后未找到 src/app.py"; exit 1; }

# 2. 版本一致性校验（包内版本 == 部署版本）
PKG_VER=$(grep -m1 '^APP_VERSION = "v' "${SRC_DIR}/src/app.py" | sed -E 's/.*"v([^"]+)".*/\1/')
echo "[2/6] 版本校验: 包内 v${PKG_VER} == 部署 ${VER}"
[ "${PKG_VER}" = "${VNO}" ] || { echo "[错误] 版本不一致，中止"; exit 1; }

# 2.5 部署形态检测（ADR-043：docker 为默认形态，原生为回退）
DOCKER_MODE=0
if command -v podman >/dev/null 2>&1 && podman ps -a --format '{{.Names}}' 2>/dev/null | grep -qx 'securetrans-docker'; then
  DOCKER_MODE=1
elif ! systemctl is-active --quiet "${SERVICE}" 2>/dev/null; then
  DOCKER_MODE=1
fi
echo "[形态] $([ "$DOCKER_MODE" = "1" ] && echo 'docker 容器（ADR-043 默认形态）' || echo '原生 systemd（回退）')"

# 3. 备份当前部署（.env + data + nas 结构整体快照，防止误操作）
BACKUP_DIR="/opt/securetrans_backup_$(date +%Y%m%d_%H%M%S)"
if [ -d "${INSTALL_DIR}" ]; then
  echo "[3/6] 备份当前部署 → ${BACKUP_DIR}"
  cp -a "${INSTALL_DIR}" "${BACKUP_DIR}"
  # 保留最近 5 份备份，防止磁盘膨胀
  ls -dt /opt/securetrans_backup_* 2>/dev/null | tail -n +6 | xargs -r rm -rf
fi

# 4. 更新程序文件与 infra/tests（保留 .env/data/nas/venv/__pycache__）
echo "[4/6] 复制程序文件与 infra/tests（保留 .env/data/nas/venv）..."
mkdir -p "${INSTALL_DIR}"
if [ -f "${INSTALL_DIR}/.env" ]; then cp -a "${INSTALL_DIR}/.env" "${INSTALL_DIR}/.env.deploybak"; fi
tar --exclude='./.env' --exclude='./.env.*' --exclude='./data' --exclude='./nas' \
    --exclude='./venv' --exclude='./__pycache__' \
    -C "${SRC_DIR}/src" -cf - . | tar -C "${INSTALL_DIR}" -xf -
if [ -d "${SRC_DIR}/infra" ]; then
  tar -C "${SRC_DIR}" -cf - infra tests 2>/dev/null | tar -C "${INSTALL_DIR}" -xf - || true
fi
if [ -f "${INSTALL_DIR}/.env.deploybak" ]; then mv "${INSTALL_DIR}/.env.deploybak" "${INSTALL_DIR}/.env"; fi
chown -R securetrans:securetrans "${INSTALL_DIR}" 2>/dev/null || true

PORT=$(grep -oP '(?<=^PORT=).*' "${INSTALL_DIR}/.env" 2>/dev/null | head -1)
PORT="${PORT:-8000}"

if [ "$DOCKER_MODE" = "1" ]; then
  # ============ Docker 通道（ADR-043 默认形态） ============
  echo "============================================"
  echo "  Docker 部署通道 | ${VER} | 端口 ${PORT}"
  echo "============================================"
  [ -f "$IMG" ] || { echo "[错误] 镜像包不存在: ${IMG}"; exit 1; }
  # 切换顺序纪律（ADR-043）：严禁双实例同时运行；docker-deploy.sh 内部先 rm 旧容器再起新容器
  cd "${INSTALL_DIR}" && bash infra/docker-deploy.sh "$IMG" "${PORT}"
  # 完整只读冒烟（从内网 IP 访问；127.0.0.1 不在 INTERNAL_CIDRS → 判外网面，管理接口 403 是正确行为）
  HOST_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
  echo "[冒烟] 目标 http://${HOST_IP}:${PORT}（内网面）"
  if [ -f "${INSTALL_DIR}/infra/smoke.sh" ] && [ -n "${HOST_IP}" ]; then
    cd "${INSTALL_DIR}" && bash infra/smoke.sh "http://${HOST_IP}:${PORT}" && echo "  SMOKE-OK" \
      || { echo "  [错误] 生产冒烟未通过（只读冒烟全量通过是部署门禁，见 ADR-017/053）"; exit 1; }
  else
    echo "  冒烟脚本/HOST_IP 不可用，以健康检查为准（docker-deploy.sh 已做 health + 登录探测）"
  fi
else
  # ============ 原生通道（回退，旧 deploy 形态） ============
  echo "[5/6] 重启服务 ${SERVICE}..."
  UNIT="/etc/systemd/system/${SERVICE}.service"
  if [ -f "$UNIT" ] && grep -q "WorkingDirectory=.*/src" "$UNIT"; then
    echo "  [修正] WorkingDirectory 残留指向 src/，统一为 ${INSTALL_DIR}"
    sed -i "s|^WorkingDirectory=.*|WorkingDirectory=${INSTALL_DIR}|" "$UNIT"
    systemctl daemon-reload
  fi
  systemctl restart "${SERVICE}"
  sleep 3
  systemctl is-active --quiet "${SERVICE}" || {
    echo "[错误] 服务启动失败，最近日志："
    journalctl -u "${SERVICE}" -n 30 --no-pager 2>/dev/null || true
    exit 1
  }
  HOST=$(grep -oP '(?<=^HOST=).*' "${INSTALL_DIR}/.env" 2>/dev/null | head -1)
  HOST="${HOST:-127.0.0.1}"
  HEALTH="http://${HOST}:${PORT}/healthz"
  for i in 1 2 3 4 5; do
    if curl -sf "${HEALTH}" -o /dev/null; then echo "  健康检查通过: ${HEALTH}"; break; fi
    [ "$i" = 5 ] && { echo "[错误] 健康检查失败: ${HEALTH}"; journalctl -u "${SERVICE}" -n 30 --no-pager 2>/dev/null || true; exit 1; }
    sleep 2
  done
  PID=$(pgrep -f "gunicorn.*app:app" 2>/dev/null | head -1)
  CWD=$(readlink "/proc/${PID}/cwd" 2>/dev/null || echo unknown)
  echo "  服务加载目录: ${CWD}"
  [ "${CWD}" = "${INSTALL_DIR}" ] || {
    echo "[错误] 服务加载目录异常: ${CWD}（应为 ${INSTALL_DIR}），请检查 systemd WorkingDirectory"
    exit 1
  }
  echo "[6/6] 只读冒烟..."
  if [ -f "${INSTALL_DIR}/infra/smoke.sh" ]; then
    cd "${INSTALL_DIR}" && bash infra/smoke.sh && echo "  SMOKE-OK" \
      || { echo "  [错误] 生产冒烟未通过（只读冒烟全量通过是部署门禁，见 ADR-017/053）"; exit 1; }
  else
    echo "  冒烟脚本缺失，健康检查已通过（服务可用）"
  fi
fi

echo "============================================================"
echo "  CD-DEPLOY-COMPLETE ${VER} | 备份: ${BACKUP_DIR} | 形态: $([ "$DOCKER_MODE" = "1" ] && echo docker || echo native)"
echo "============================================================"
