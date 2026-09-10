# SecureTrans Gitea Actions CI 接入指南（ADR-016）

目标：push 到 main 后，在本地测试环境（WSL rocky10-st）自动执行全量 TDD 回归（verify.sh），
形成"开发（Windows）→ 测试（WSL）→ 持续集成"闭环；后续打通 ssh 后可扩展为 CD（自动部署生产，保留人工门禁）。

## 架构

- **Runner**：Gitea Actions 的本地执行器，运行在 WSL rocky10-st（`labels=securetrans-wsl`）
- **执行内容**：clone 最新 main → 同步到 `/opt/securetrans`（保留 .env/data/nas/venv）→ restart → `verify.sh` 全量回归
- **测试环境配置**：`env/test.env`（AD_MOCK_MODE=true，内置模拟目录，不触网）

## 一、Gitea 启用 Actions

Gitea 站点管理（Admin 面板 → Actions）启用 Actions；本地 Gitea（docker）默认支持。

## 二、注册本地 Runner（WSL 执行）

```bash
# 1. 下载 act_runner（与 Gitea 版本匹配，Linux amd64）
wget -q https://github.com/gitea/act_runner/releases/latest/download/act_runner_linux_amd64.tar.gz
tar xzf act_runner_linux_amd64.tar.gz
sudo mv act_runner /usr/local/bin/

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

## 三、配置仓库 Secret

仓库 `Settings → Actions → Secrets` 新增：
- `GITEA_TOKEN`：有该仓库读权限的访问令牌（用户设置 → 应用 → 生成令牌，勾选 read:repository）
  （用于 workflow 内 clone 私有仓库）

## 四、验证

1. 推送一个 commit 到 main（或 Actions 页面手动 Run workflow）
2. Actions 标签页查看 `CI-TDD` 运行：应看到 Clone → Sync → Restart → Full TDD regression 四步
3. 全量通过 = 绿灯；失败项与本地 `bash infra/verify.sh` 一致（同一脚本）

## 五、后续扩展（CD，ssh 打通后）

- `on: push: tags: ['v*']` 触发打包：`bash infra/package.sh` → 上传 Release 资产（release.ps1 逻辑）
- 生产部署 job（ssh）：解压 → `deploy.sh`（保留 .env）→ 冒烟 → 通知人工验收门禁
- 生产**不做**写数据自动化测试（冲击真实数据），验收按 RTM 走冒烟 + 人工（见 docs/07）
