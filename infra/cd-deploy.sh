#!/bin/bash
# ============================================================
# SecureTrans CD 部署脚本（服务器侧执行，ADR-024）
# 用途：Gitea Release 发布后，由 CD job（WSL act_runner 容器）经 SSH 调用本脚本，
#       完成生产服务器的【轻量升级】：代码更新（保留 .env/data/nas/venv）→ 重启 → 只读冒烟
# 用法：bash cd-deploy.sh <版本号>   （发布包须已上传到 /opt/securetrans-release/）
# 前置：发布包 securetrans-<版本>.tar.gz 已 scp 到 /opt/securetrans-release/
# 安全：不重置 admin 密码、不重建 venv、不覆盖生产数据（与 deploy.sh 全量安装互补）
# ============================================================
set -euo pipefail

VER="${1:?用法: bash cd-deploy.sh <版本号>}"
VNO="${VER#v}"
REL_DIR="/opt/securetrans-release"
PKG="${REL_DIR}/securetrans-${VNO}.tar.gz"
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
echo "[2/6] 版本校验: 包内 v${PKG_VER} == 部署 v${VER}"
[ "${PKG_VER}" = "${VNO}" ] || { echo "[错误] 版本不一致，中止"; exit 1; }

# 3. 备份当前部署（.env + data + nas 结构整体快照，防止误操作）
BACKUP_DIR="/opt/securetrans_backup_$(date +%Y%m%d_%H%M%S)"
if [ -d "${INSTALL_DIR}" ]; then
  echo "[3/6] 备份当前部署 → ${BACKUP_DIR}"
  cp -a "${INSTALL_DIR}" "${BACKUP_DIR}"
  # 保留最近 5 份备份，防止磁盘膨胀
  ls -dt /opt/securetrans_backup_* 2>/dev/null | tail -n +6 | xargs -r rm -rf
fi

# 4. 轻量升级：复制程序文件（保留 .env/data/nas/venv/__pycache__）
echo "[4/6] 复制程序文件（保留 .env/data/nas/venv）..."
mkdir -p "${INSTALL_DIR}"
if [ -f "${INSTALL_DIR}/.env" ]; then cp -a "${INSTALL_DIR}/.env" "${INSTALL_DIR}/.env.deploybak"; fi
tar --exclude='./.env' --exclude='./.env.*' --exclude='./data' --exclude='./nas' \
    --exclude='./venv' --exclude='./__pycache__' \
    -C "${SRC_DIR}/src" -cf - . | tar -C "${INSTALL_DIR}" -xf -
# 同步 infra/tests（smoke.sh 等最新验证脚本）
if [ -d "${SRC_DIR}/infra" ]; then
  tar -C "${SRC_DIR}" -cf - infra tests 2>/dev/null | tar -C "${INSTALL_DIR}" -xf - || true
fi
if [ -f "${INSTALL_DIR}/.env.deploybak" ]; then mv "${INSTALL_DIR}/.env.deploybak" "${INSTALL_DIR}/.env"; fi
chown -R securetrans:securetrans "${INSTALL_DIR}" 2>/dev/null || true

# 5. 重启服务并健康检查
echo "[5/6] 重启服务 ${SERVICE}..."
# 5.0 结构一致性：确保 systemd WorkingDirectory 指向标准结构 /opt/securetrans
#    （历史手工部署可能指向 /opt/securetrans/src 残留目录，导致服务静默跑旧代码）
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
PORT=$(grep -oP '(?<=^PORT=).*' "${INSTALL_DIR}/.env" 2>/dev/null | head -1)
PORT="${PORT:-8000}"
HOST=$(grep -oP '(?<=^HOST=).*' "${INSTALL_DIR}/.env" 2>/dev/null | head -1)
HOST="${HOST:-127.0.0.1}"
HEALTH="http://${HOST}:${PORT}/healthz"
for i in 1 2 3 4 5; do
  if curl -sf "${HEALTH}" -o /dev/null; then echo "  健康检查通过: ${HEALTH}"; break; fi
  [ "$i" = 5 ] && { echo "[错误] 健康检查失败: ${HEALTH}"; journalctl -u "${SERVICE}" -n 30 --no-pager 2>/dev/null || true; exit 1; }
  sleep 2
done
# 5.5 版本生效校验：确认 gunicorn 实际从标准目录加载（防 src/ 残留静默跑旧代码）
PID=$(pgrep -f "gunicorn.*app:app" 2>/dev/null | head -1)
CWD=$(readlink "/proc/${PID}/cwd" 2>/dev/null || echo unknown)
echo "  服务加载目录: ${CWD}"
[ "${CWD}" = "${INSTALL_DIR}" ] || {
  echo "[错误] 服务加载目录异常: ${CWD}（应为 ${INSTALL_DIR}），请检查 systemd WorkingDirectory"
  exit 1
}

# 6. 只读冒烟（生产环境不跑全量 TDD，避免数据污染；ADR-024）
echo "[6/6] 只读冒烟..."
if [ -f "${INSTALL_DIR}/infra/smoke.sh" ]; then
  cd "${INSTALL_DIR}" && bash infra/smoke.sh && echo "  SMOKE-OK" || echo "  [警告] 冒烟有失败项，详见输出（服务已启动，请人工复核）"
else
  echo "  冒烟脚本缺失，健康检查已通过（服务可用）"
fi

echo "============================================================"
echo "  CD-DEPLOY-COMPLETE v${VER} | 备份: ${BACKUP_DIR}"
echo "============================================================"
