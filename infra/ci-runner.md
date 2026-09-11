# SecureTrans Gitea Actions CI 接入指南（ADR-016）

目标：push 到 main 后，在本地测试环境（WSL rocky10-st）自动执行全量 TDD 回归（verify.sh），
形成"开发（Windows）→ 测试（WSL）→ 持续集成"闭环；后续打通 ssh 后可扩展为 CD（自动部署生产，保留人工门禁）。

## 架构（ADR-018 分层流水线）

- **Runner**：Gitea Actions 的本地执行器，运行在 WSL rocky10-st（`labels=securetrans-wsl`）
- **分层（最便宜门禁先失败）**：
  1. **fast-check**（总是执行，秒级）：py_compile 语法 / 版本号双源一致性（app.py ↔ index.html）/ env 模板 ENV_ROLE / 关键脚本完整性（deploy/verify/smoke/package/release）
  2. **tdd-verify**（needs fast-check）：clone 最新 main → 同步到 `/opt/securetrans`（保留 .env/data/nas/venv）→ restart → `verify.sh` 全量回归（含 ADR-017 fail-safe 与 ADR-018 计数门禁）
  3. **package**（仅 push tag v*，needs 前两者）：clone 该 tag → 复用 `/opt/securetrans/packages` 的 offline-deps → `package.sh` 构建 → 制品落到共享 packages/（build once, deploy many；离线环境无 node/网络，不用 actions/upload-artifact@v4）
- **发布**：CI 构建产物在 WSL packages/ 后，发布时 `wsl cp packages/securetrans-<v>.tar.gz* <win>/packages/` 再 `infra/release.ps1 -Version v<v>` 上传 Release 资产（发布策略 ADR-014）
- **测试环境配置**：`env/test.env`（AD_MOCK_MODE=true，内置模拟目录，不触网）

## 一、Gitea 启用 Actions

Gitea 站点管理（Admin 面板 → Actions）启用 Actions；本地 Gitea（docker）默认支持。

## 二、Runner 前置依赖（WSL 测试环境）

```bash
# git（workflow 第一步 clone 必需；sudo 下 PATH 不包含 Windows git）
sudo dnf install -y git
```

## 三、注册本地 Runner（WSL 执行）

```bash
# 1. 下载 act_runner（与 Gitea 版本匹配，Linux amd64；资产名为连字符格式，gitea.com 官方镜像）
VERSION=0.2.11   # 按需调整；GitHub 资产名同样为 act_runner-${VERSION}-linux-amd64
curl -sL -o /tmp/act_runner "https://gitea.com/gitea/act_runner/releases/download/v${VERSION}/act_runner-${VERSION}-linux-amd64"
chmod +x /tmp/act_runner
sudo mv /tmp/act_runner /usr/local/bin/act_runner

# 2. 获取注册 token（仓库或组织级；以下用 API，需有管理权限的令牌 GITEA_ADMIN_TOKEN）
TOKEN=$(curl -s -X POST -H "Authorization: token ${GITEA_ADMIN_TOKEN}" \
  http://localhost:3000/api/v1/admin/runners/registration-token | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')

# 3. 注册（instance 指向 Gitea 地址；WSL 访问 Windows localhost 互通）
sudo mkdir -p /var/lib/act_runner
sudo act_runner register \
  --instance http://localhost:3000 \
  --token "$TOKEN" \
  --name securetrans-wsl \
  --labels securetrans-wsl:host \
  --no-interactive

# 4. 以 systemd 常驻运行
sudo act_runner generate-config > /var/lib/act_runner/config.yaml
sudo act_runner daemon --config /var/lib/act_runner/config.yaml &
```

> 生产化常驻：`sudo cp /usr/local/bin/act_runner /usr/local/bin/act_runner` 后创建
> systemd unit（`/etc/systemd/system/act_runner.service`）或直接由 CI 触发时启动。

## 四、配置仓库 Secret（可选）

仓库 `Settings → Actions → Secrets` 新增（**当前仓库 public，clone 无需凭据；私有化后必须配置**）：
- `GITEA_TOKEN`：有该仓库读权限的访问令牌（用户设置 → 应用 → 生成令牌，勾选 read:repository）
  （用于 workflow 内 clone 私有仓库）

## 五、验证

1. 推送一个 commit 到 main（或 Actions 页面手动 Run workflow）
2. Actions 标签页查看 `CI-TDD` 运行：应看到 Clone → Sync → Restart → Full TDD regression 四步
3. 全量通过 = 绿灯；失败项与本地 `bash infra/verify.sh` 一致（同一脚本）

## 六、后续扩展（CD，ssh 打通后）

- `on: push: tags: ['v*']` 触发打包：`bash infra/package.sh` → 上传 Release 资产（release.ps1 逻辑）
- 生产部署 job（ssh）：解压 → `deploy.sh`（保留 .env）→ 冒烟 → 通知人工验收门禁
- 生产**不做**写数据自动化测试（冲击真实数据），验收按 RTM 走冒烟 + 人工（见 docs/07）

- **常驻**：act_runner 以 systemd 服务运行（`systemctl status act_runner`，Restart=always，开机自启）；日志 `/var/log/act_runner.log`。
- **容器化目标态（ADR-019）**：镜像 `securetrans-ci:3.12`（infra/docker/Dockerfile + 离线 wheelhouse）；容器入口 `infra/ci_test.sh`（无 systemd、环境变量注入、/data 随容器销毁）。切换步骤：Docker Desktop → Resources → WSL Integration 勾选 rocky10-st → 重启 → `.runner` label 改 `docker://securetrans-ci:3.12` → 重启 act_runner。
