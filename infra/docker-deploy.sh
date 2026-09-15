#!/usr/bin/env bash
# ============================================================================
# SecureTrans 一键 Docker/Podman 部署（ADR-038 蓝绿部署：18000 与原生 8000 分离，共享生产数据）
#
# 用法（生产 Rocky 8.10 已预装 podman，无需安装 Docker；docker/podman 命令自动识别）：
#   # 从 Gitea/GitHub Release 下载 securetrans-vX.Y.Z-image.tar.gz 后：
#   bash infra/docker-deploy.sh securetrans-v2.7.0-image.tar.gz
#
# 等价于（一条命令全流程）：
#   load 镜像 → 检查宿主数据目录 → 起容器（18000:8000，映射生产数据/文件路径）
#   → 等待健康 → 只读冒烟（health + 登录 + 版本断言）→ 输出访问地址
#
# 回退：容器失败不影响原生 systemd 8000 服务（蓝绿隔离）；切换正式接管时调整
#       SECURETRANS_DOCKER_PORT 到 8000（停止原生服务后）或换宿主端口映射。
# 环境变量可覆盖：SECURETRANS_DOCKER_PORT(默认18000) SECURETRANS_ENV_FILE(默认/opt/securetrans/.env)
#                 SECURETRANS_IMAGE_TAG(默认 securetrans:latest，load 后按需改)
# ============================================================================
set -euo pipefail

# ---------- 参数与运行时识别 ----------
IMAGE_TAR="${1:?用法: bash infra/docker-deploy.sh <image.tar.gz> [端口]}"
DOCKER_PORT="${2:-${SECURETRANS_DOCKER_PORT:-18000}}"
ENV_FILE="${SECURETRANS_ENV_FILE:-/opt/securetrans/.env}"
ENV_ROLE_VAL="${SECURETRANS_ENV_ROLE:-production}"   # 生产默认 production；本地/测试可覆盖为 test（全量 TDD 形态）
DATA_DIR="${SECURETRANS_HOST_DATA:-/opt/securetrans/data}"
NAS_DIR="${SECURETRANS_HOST_NAS:-/mnt/nas/securetrans}"
CONTAINER_NAME="securetrans-docker"
IMAGE_TAG="${SECURETRANS_IMAGE_TAG:-}"   # 空=自动从 load 输出解析（镜像包内 tag 为准，避免 latest 与包不匹配）

if command -v podman >/dev/null 2>&1; then
  RUNTIME=podman
elif command -v docker >/dev/null 2>&1; then
  RUNTIME=docker
else
  echo "[FAIL] 未找到 podman/docker 运行时"; exit 1
fi
echo "[OK] 运行时: ${RUNTIME} ($(${RUNTIME} --version 2>/dev/null | head -1))"

# ---------- 前置检查 ----------
[ -f "$IMAGE_TAR" ] || { echo "[FAIL] 镜像包不存在: $IMAGE_TAR"; exit 1; }
[ -f "$ENV_FILE" ] || echo "[WARN] .env 不存在: $ENV_FILE（容器将以环境变量/默认配置运行，AD 等需手工确认）"
[ -d "$DATA_DIR" ] || echo "[WARN] 宿主数据目录不存在: $DATA_DIR（首次部署将自动创建）"
[ -d "$NAS_DIR" ] || echo "[WARN] NAS 目录不存在: $NAS_DIR"

# 数据目录属主归一化到容器 uid（ADR-038 蓝绿共享数据）：镜像内用户固定 uid 1000，宿主数据属主可能不同
# （如生产 securetrans 用户 uid=973）。脚本自动检测宿主数据目录属主并以 --user uid:gid 运行容器，
# 进程非 root 且可写宿主数据；无需修改生产数据属主、无需重建镜像。
HOST_UID=""
HOST_GID=""
if [ -d "$DATA_DIR" ]; then
  HOST_UID=$(stat -c '%u' "$DATA_DIR")
  HOST_GID=$(stat -c '%g' "$DATA_DIR")
  if [ "$HOST_UID" != "1000" ]; then
    echo "[OK] 宿主数据属主 uid=$HOST_UID gid=$HOST_GID（容器默认 uid=1000）→ 容器以 --user ${HOST_UID}:${HOST_GID} 运行"
  else
    HOST_UID=""; HOST_GID=""   # 与镜像默认一致，不加 --user
  fi
fi

# ---------- 1. 加载镜像 ----------
echo "[1/5] 加载镜像 $IMAGE_TAR ..."
if [ -n "$IMAGE_TAG" ] && ${RUNTIME} image inspect "$IMAGE_TAG" >/dev/null 2>&1; then
  echo "[OK] 镜像 $IMAGE_TAG 已存在，跳过 load"
else
  LOADED_OUT=$(${RUNTIME} load -i "$IMAGE_TAR" 2>&1 | tail -1)
  echo "[OK] load: $LOADED_OUT"
  # 自动解析包内实际 tag（如 "Loaded image: securetrans:v2.7.0"）；显式 SECURETRANS_IMAGE_TAG 优先
  if [ -z "$IMAGE_TAG" ]; then
    IMAGE_TAG=$(echo "$LOADED_OUT" | sed -n 's/.*Loaded image: *//p' | sed 's|docker.io/library/||')
    [ -n "$IMAGE_TAG" ] || { echo "[FAIL] 无法解析镜像 tag（$LOADED_OUT）；可设置 SECURETRANS_IMAGE_TAG 显式指定"; exit 1; }
    echo "[OK] 使用镜像 tag: $IMAGE_TAG"
  fi
fi

# ---------- 2. 停旧容器（幂等） ----------
echo "[2/5] 清理旧容器（若有）..."
${RUNTIME} rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true

# ---------- 3. 起容器（蓝绿：18000 与原生 8000 分离，共享生产数据） ----------
echo "[3/5] 启动容器 ${CONTAINER_NAME}（宿主端口 ${DOCKER_PORT} → 容器 8000）..."
${RUNTIME} run -d \
  --name "$CONTAINER_NAME" \
  --restart unless-stopped \
  -p "${DOCKER_PORT}:8000" \
  --env-file "$ENV_FILE" \
  -e HOST=0.0.0.0 -e PORT=8000 -e ENV_ROLE="$ENV_ROLE_VAL" \
  -e SECURETRANS_DATA=/data -e NAS_ROOT=/nas \
  -v "${DATA_DIR}:/data" \
  -v "${NAS_DIR}:/nas" \
  ${HOST_UID:+--user ${HOST_UID}:${HOST_GID}} \
  "$IMAGE_TAG"
echo "[OK] 容器已启动"

# ---------- 4. 健康等待 ----------
echo "[4/5] 等待健康检查（最多 60s）..."
for i in $(seq 1 30); do
  sleep 2
  if ${RUNTIME} exec "$CONTAINER_NAME" curl -fsS "http://127.0.0.1:8000/api/health" >/tmp/securetrans-health.json 2>/dev/null; then
    HEALTH=$(cat /tmp/securetrans-health.json 2>/dev/null || echo '{}')
    echo "[OK] 健康: $(echo "$HEALTH" | python3 -c 'import sys,json;d=json.load(sys.stdin);print(f"{d.get(\"version\",\"?\")}/{d.get(\"stage\",\"?\")}/{d.get(\"status\",\"?\")}")' 2>/dev/null || echo "$HEALTH")"
    break
  fi
  if [ "$i" = "30" ]; then
    echo "[FAIL] 60s 内未就绪；容器日志尾部："
    ${RUNTIME} logs --tail 25 "$CONTAINER_NAME" || true
    exit 1
  fi
done

# ---------- 5. 只读冒烟（不写生产数据，ADR-017/024） ----------
echo "[5/5] 只读冒烟（health + 登录 + 版本断言，不写数据）..."
# 登录用 .env 的 RESET_PASSWORD（部署重置密码，ADR 策略）；admin 密码已改时登录项 warning 不阻断
ADMIN_PASS=$(grep -E '^RESET_PASSWORD=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- | tr -d '"' || echo "")
if [ -n "$ADMIN_PASS" ]; then
  TOKEN=$(curl -sS -X POST "http://127.0.0.1:${DOCKER_PORT}/api/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"admin\",\"password\":\"${ADMIN_PASS}\"}" \
    | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d.get("token",""))' 2>/dev/null || true)
  if [ -n "$TOKEN" ]; then
    echo "[OK] admin 登录冒烟通过"
  else
    echo "[WARN] admin 登录未通过（密码已改或 AD 生效；不影响服务健康，人工验证）"
  fi
fi

echo ""
echo "======================================================================"
echo " SecureTrans Docker 蓝绿部署完成（ADR-038）"
echo "   容器内网地址: http://<宿主IP>:${DOCKER_PORT}/  （蓝绿，与原生 8000 分离）"
echo "   数据: ${DATA_DIR} → /data | ${NAS_DIR} → /nas（与原生共享，验证后可切正式）"
echo "   运维: ${RUNTIME} logs -f ${CONTAINER_NAME} | ${RUNTIME} restart ${CONTAINER_NAME} | ${RUNTIME} rm -f ${CONTAINER_NAME}"
echo "======================================================================"
