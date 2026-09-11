# SecureTrans CI/CD + GitOps 架构方案

> 版本：v1.0 | 日期：2026-08-27 | 阶段：PSF → PMF 过渡
> 目标：从手动部署演进到持续交付，打通 Lean Startup → Agile → DevOps → GitOps

---

## 一、现状与问题

### 当前部署方式（手动）

```
本地开发 → 手动测试 → 手动打包 → scp上传 → 手动部署 → 手动验证
```

**问题**：
- 部署依赖人工操作，容易出错
- 测试环境和生产环境配置不一致
- 无法追溯"哪个版本部署到了哪个环境"
- AI 生成代码后需要人工介入才能部署
- 回滚困难

### 目标部署方式（GitOps）

```
代码提交 → CI自动测试 → 自动打包 → Git仓库更新 → 环境自动同步 → 自动验证
```

---

## 二、CI/CD 流水线设计

### 2.1 工具选型

| 工具 | 用途 | 数据中心兼容性 |
|------|------|--------------|
| **Gitea Actions** | CI/CD 流水线（Gitea 内置） | ✅ 可离线部署 |
| **GitLab CI** | CI/CD 流水线（如用 GitLab） | ✅ 可离线部署 |
| **Jenkins** | 传统 CI/CD | ✅ 可离线部署 |
| **Argo CD** | GitOps 持续交付（K8s） | ⚠️ 需要 K8s |
| **Ansible** | 配置管理 + 部署 | ✅ 可离线部署 |

**推荐**：PSF/PMF 阶段用 **Gitea Actions + Ansible**（轻量，无需 K8s）；规模化后迁 **Argo CD + K8s**。

### 2.2 流水线阶段

```
┌─────────────────────────────────────────────────────────────┐
│                        CI 流水线                              │
├──────────┬──────────┬──────────┬──────────┬────────────────┤
│  代码提交  │  静态检查  │  单元测试  │  集成测试  │  构建打包      │
│  push/PR  │  lint    │  pytest  │  102项全量 │  package.sh   │
└──────────┴──────────┴──────────┴──────────┴────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        CD 流水线                              │
├──────────────────┬──────────────────┬──────────────────────┤
│  测试环境部署       │  冒烟测试          │  生产环境部署（人工审批）│
│  Ansible deploy   │  verify.sh       │  Ansible deploy      │
└──────────────────┴──────────────────┴──────────────────────┘
```

### 2.3 Gitea Actions 流水线示例

`.gitea/workflows/ci.yml`:

```yaml
name: CI Pipeline

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: |
          cd src
          python -m venv venv
          source venv/bin/activate
          pip install -r requirements.txt
      - name: Start service
        run: |
          cd src
          cp .env.testing .env
          source venv/bin/activate
          nohup python app.py &
          sleep 3
      - name: Run integration tests
        run: |
          cd tests
          python test_api.py
      - name: Upload test report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: test-report
          path: tests/

  package:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - name: Package
        run: bash infra/package.sh ${GITHUB_SHA::7}
      - name: Upload package
        uses: actions/upload-artifact@v4
        with:
          name: securetrans-package
          path: securetrans-*.tar.gz
```

---

## 三、GitOps 架构

### 3.1 核心思想

**Git 作为唯一可信源（Single Source of Truth）**：
- 应用代码 → `src/`
- 基础设施配置 → `infra/`（Ansible playbook、nginx、systemd）
- 环境配置 → `env/testing/`、`env/production/`（.env 模板）
- 部署状态 → Git tag / release

**环境自动同步**：Git 仓库变更 → 自动触发部署 → 环境状态与 Git 一致

### 3.2 环境配置分离

```
SecureTrans/
├── src/                    # 应用代码（环境无关）
├── tests/                  # 测试
├── infra/                  # 基础设施（Ansible/nginx/systemd）
│   ├── deploy.sh
│   ├── verify.sh
│   ├── package.sh
│   ├── nginx-securetrans.conf
│   └── securetrans.service
├── env/                    # 环境配置（GitOps 核心）
│   ├── testing/            # 测试环境配置
│   │   └── .env
│   └── production/         # 生产环境配置（密钥加密）
│       └── .env
├── .gitea/
│   └── workflows/          # CI/CD 流水线
│       └── ci.yml
└── docs/
    └── 08-cicd-gitops-architecture.md  # 本文档
```

### 3.3 部署状态追踪

| 环境 | Git 分支/Tag | 部署方式 | 触发条件 |
|------|-------------|---------|---------|
| 开发 | `main` | 本地 `python app.py` | 手动 |
| 测试 | `main` 最新 | Ansible + Gitea Actions | push 到 main |
| 预发布 | `release/*` 分支 | Ansible + 人工审批 | PR 合入 release |
| 生产 | Git Tag `vX.Y.Z` | Ansible + 人工审批 | 打 Tag |

---

## 四、数据中心隔离环境特殊考虑

### 4.1 离线依赖管理

数据中心无互联网，需要本地镜像：

| 依赖类型 | 离线方案 |
|---------|---------|
| Python 包 | 本地 PyPI 镜像（devpi / pypiserver）或离线 wheel 包 |
| Linux 包 | 本地 yum/apt 镜像（Rocky: dnf reposync） |
| Docker 镜像 | 本地 Harbor / Nexus 镜像仓库 |
| Gitea Actions Runner | 离线安装 runner，预装依赖 |

**实施步骤**：
```bash
# 1. 在有网环境下载所有依赖
pip download -r src/requirements.txt -d offline-packages/

# 2. 打包传到数据中心
tar czf offline-packages.tar.gz offline-packages/

# 3. 在数据中心安装本地 PyPI
pip install pypiserver
pypi-server run -p 8080 -P . -a . offline-packages/

# 4. 配置 pip 使用本地源
pip config set global.index-url http://localhost:8080/simple/
```

### 4.2 Gitea Actions Runner 离线部署

```bash
# 在有网环境下载 runner
curl -L -o gitea-runner https://dl.gitea.com/act_runner/0.2.6/act_runner-0.2.6-linux-amd64

# 传到数据中心注册
./act_runner register --instance http://gitea.local:3000 --token <token>
./act_runner daemon
```

### 4.3 密钥管理

- `.env` 中的 `SECRET_KEY`、AD 密码等**不提交到 Git**
- 使用 **Ansible Vault** 或 **git-crypt** 加密敏感配置
- 生产环境密钥由运维人员手动注入

---

## 五、AI 持续部署

### 5.1 AI Agent 部署流程

```
AI Agent 生成代码 → 自动运行测试 → 提交到 Git → CI 自动验证 → 自动部署到测试环境 → 人工审批 → 部署到生产
```

### 5.2 AI Agent 能力要求

在数据中心部署 AI 辅助开发环境：

| 组件 | 用途 | 离线方案 |
|------|------|---------|
| **本地 LLM** | 代码生成/审查 | Ollama + Qwen/DeepSeek 模型 |
| **Gitea** | 代码托管 | 离线 Docker 部署 |
| **Gitea Actions** | CI/CD | 离线 Runner |
| **AI Agent** | 自主开发部署 | 基于本地 LLM + Gitea API |

### 5.3 AI 自主开发循环

```
1. AI Agent 从 Gitea 获取需求（Issue/Story）
2. AI Agent 创建 feature 分支，编写代码
3. AI Agent 本地运行测试，修复 Bug
4. AI Agent 提交 PR，CI 自动验证
5. CI 通过 → 自动部署到测试环境
6. 人工 Review → 合入 main → 自动部署到生产
```

---

## 六、演进路线图

### Phase 1：PSF（当前）— 手动部署

- ✅ 本地开发 + 手动测试
- ✅ 一键打包脚本（package.sh）
- ✅ 一键部署脚本（deploy.sh）
- ⬜ Gitea 仓库管理（已完成）
- ⬜ 测试报告自动化

### Phase 2：PMF — CI 自动化

- ⬜ Gitea Actions CI 流水线（自动测试+打包）
- ⬜ 测试环境自动部署（Ansible）
- ⬜ 环境配置分离（env/testing, env/production）
- ⬜ 离线依赖镜像（本地 PyPI）
- ⬜ AI Agent 辅助开发（本地 LLM）

### Phase 3：Scale — CD + GitOps

- ⬜ 生产环境自动部署（人工审批）
- ⬜ 部署状态追踪（Git Tag）
- ⬜ 自动回滚机制
- ⬜ 蓝绿部署 / 金丝雀发布
- ⬜ Argo CD + K8s（如需要）

### Phase 4：AI 驱动 — 全自动化

- ⬜ AI Agent 自主开发（从需求到代码）
- ⬜ AI 自动测试 + 自动修复
- ⬜ AI 自动部署 + 自动验证
- ⬜ 人工仅做最终审批

---

## 七、生产验证后启动的 3 件事（当前为待办）

> ⏸️ **状态说明**：以下 3 项为 CI/CD 启动清单，**待生产环境（封闭数据中心 Rocky Linux）部署测试全部通过后再启动**。
> 当前 PSF 阶段已完成的配置管理：Gitea 仓库（main 单分支）+ 一键打包（package.sh）+ 一键部署（deploy.sh）+ 74 项自动化测试。

1. **配置 Gitea Actions**：在 Gitea 中启用 Actions，添加 Runner，创建 `.gitea/workflows/ci.yml`（代码提交→自动测试→自动打包）
2. **创建 env/ 目录**：分离测试环境和生产环境配置，密钥用 Ansible Vault 加密
3. **搭建本地 PyPI 镜像**：在数据中心部署 pypiserver，预下载所有 Python 依赖

**启动条件**（全部满足后执行）：
- [ ] 生产环境 `infra/deploy.sh` 一键部署成功
- [ ] 生产环境 `infra/verify.sh` 74 项全量测试通过
- [ ] AD/LDAP 真实对接（与 sssd 兼容）验证完成
- [ ] NAS 挂载确认 staging/external/archive 同文件系统（os.rename 0拷贝生效）

---

*文档结束 | SecureTrans CI/CD + GitOps 架构 v1.1 | 2026-09-11*


---

## 九、CI 运行器落地状态与 Backlog（2026-09-11）

### 已落地（ADR-018 / ADR-019）
1. **分层流水线**：fast-check（秒级静态门禁，含 py_compile + static_check.py 零依赖 AST 检查）→ tdd-verify（全量，fail-fast）→ package（仅 tag v* 构建发布包到共享 packages/）。
2. **质量门禁**：test_api.py 计数基线（全量 ≥300 / 冒烟 ==10）。
3. **runner 常驻**：act_runner → systemd（Restart=always，开机自启），解决 WSL 会话回收导致的偶发 shutdown。
4. **容器化试点**：`securetrans-ci:3.12` 镜像 + `infra/ci_test.sh`，本地容器全量 TDD 309/309 通过、工作区零残留；证明"每次 CI 干净环境 + 新配置 + 新数据"可行。

### Backlog（按优先级）
| # | 事项 | 状态 | 说明 |
|---|------|------|------|
| B1 | ~~启用 Docker Desktop WSL Integration~~ | ✅ 已替代 | 已由 **WSL 内独立 docker-ce daemon**（dnf 在线装，29.8.0）替代：act_runner 双 label（securetrans-wsl 宿主 / securetrans-ci 容器），与 Docker Desktop/Gitea 完全无关、零中断（2026-09-11 落地） |
| B2 | 容器 job 的 workspace 策略 | ✅ 已明确 | act_runner 容器 job **不自动 checkout**：需显式 git clone（经 WSL 网关 IP 动态解析访问 Gitea）；工作区=GITHUB_WORKSPACE，数据落容器内 /data 随容器销毁，宿主零污染 |
| B3 | 数据中心离线 CI 独立化 | 📌 远期 | 生产服务器（隔离互联网）若建 CI：离线 RPM 装 docker-ce + 镜像 docker save/load 导入；系统依赖（openldap-clients 等）进离线依赖包（在线 dnf / 离线 rpm 双模式，见 ADR-020） |
| B4 | 镜像版本管理 | 📌 远期 | 依赖变更时重建镜像并打标签（如 securetrans-ci:3.12-2），Dockerfile 与 wheelhouse 已入仓（infra/docker/）可追溯 |
| B5 | act_runner 周期性 SIGTERM 调查 | ✅ 已解决 | **根因双因**（2026-09-11 实证）：① **WSL 发行版空闲自动终止**（wslhost 反复新建、systemd boot 时间变化而内核 uptime 连续；发行版无交互会话时被 WSL 终止，后台 daemon 不算活跃）→ 修复：Windows 计划任务 `WSL-Rocky10-KeepAlive` 每 1 分钟执行 `wsl.exe -d rocky10-st -- sleep 45`（保持连接，发行版不空闲，13:24 后 act_runner 连续稳定 >20 分钟）；② **act_runner v0.2.11 的 `needs` 依赖解析 bug**（"runs-on key not defined in CI-TDD/xxx"+"No steps found"→ 容器 job 秒退假绿，fast-check 无 needs 正常、tdd/package 有 needs 全假绿）→ 修复：**合并 fast-check+tdd 为单 job `ci-check`**（无 needs，串行：静态门禁秒级先失败 → 全量 TDD），package 去掉 needs。修复后实证：run 97 ci-check 22s 成功，容器内进程可见 ci_test.sh + gunicorn + pytest 真跑（317/317）。详见第十节 |
| B6 | 静态检查标准化（ruff）| 📌 待决策 | 现用 static_check.py（零依赖 AST：语法/未定义名/重复定义/未用 import）。业界标准建议引入 **ruff**（lint+format+isort 一体，Rust 实现，离线 wheel 可打包）；决策点：保持零依赖 vs 引入 ruff（两者可并存：ruff 在线环境加速，static_check.py 作为离线兜底） |
| B7 | 备忘：beta 测试通过后开放 SSH/持续发布权限 | 📌 待触发 | 用户承诺：下午 beta 手工验收通过后，开放生产服务器 SSH，由 AI 执行 CD/持续发布（配合 ADR-014 发布节奏：正式版本人工发布） |


## 十、WSL CI 稳定性根因与修复（ADR-021，2026-09-11）

> 状态：✅ 已修复并实证。背景：CI 在 WSL rocky10-st 上间歇性中断/假绿（run 91 卡 14 分钟、run 92/93/94 tdd 20s 假绿），经逐层取证定位为双因叠加。

### 10.1 根因一：WSL 发行版空闲自动终止
- **现象**：act_runner 日志高频 shutdown initiated；wslhost 进程反复新建（Windows 侧 wslmon 监控实拍）；systemd boot 时间反复变化但内核 uptime 连续（发行版级重启，非内核/VM 重启）；vmmem 内存持续（VM 存活）。
- **机制**：WSL2 发行版在**没有交互会话**时会被 WSL 服务终止（后台 systemd 服务不算"活跃交互"）；每次我执行命令激活发行版 → 命令结束 → 60 秒级空闲 → 发行版终止 → 下次访问重启 → act_runner 收到 SIGTERM。**这是 WSL 已知设计**（microsoft/WSL 相关 issue），非 systemd 自身崩溃。
- **修复**：Windows 计划任务 **WSL-Rocky10-KeepAlive**，每 1 分钟执行 wsl.exe -d rocky10-st -- sleep 45（保持 45 秒连接，发行版永不空闲）。13:24:25 后 act_runner 连续稳定 >20 分钟（此前每 1-3 分钟必崩），实证有效。
- **创建命令**（管理员 PowerShell）：
  schtasks /Create /TN "WSL-Rocky10-KeepAlive" /TR "wsl.exe -d rocky10-st -- sleep 45" /SC MINUTE /MO 1 /F

### 10.2 根因二：act_runner v0.2.11 的 needs 依赖解析 bug（假绿）
- **现象**：tdd-verify/package（有 
eeds）job 日志出现 'runs-on' key not defined in CI-TDD/fast-check + No steps found → 容器启动后立即 cleaning up → Gitea 误标"成功"（秒级假绿）；而 fast-check（无 needs）3s 正常执行。
- **机制**：act_runner v0.2.11 对含 
eeds 的容器 job 步骤解析异常（步骤丢失、空转成功），Gitea 端无法发现（job 状态被 runner 上报为成功）。
- **修复**：**合并 fast-check + tdd-verify 为单 job ci-check**（无 needs；静态门禁步骤在前秒级先失败，全量 TDD 步骤在后），package 去掉 needs（仅 tag 触发独立跑）。规避 bug 而非对抗版本。
- **实证**：run 97（修复后）ci-check 22s 成功；容器内进程取证：infra/ci_test.sh + gunicorn app:app + 	ests/test_api.py 全部在容器内真实执行（非假绿）；全量 TDD 317/317 通过（容器模拟同流程 20s 完成 317 项，SQLite 快）。

### 10.3 遗留与建议
- **WSL 保活为过渡方案**：CI 权威载体应为数据中心真实服务器（干净 systemd + 无 WSL 自动终止），B3 远期落地。
- **act_runner 升级**：后续若升级 act_runner（>v0.2.11），可评估恢复多 job + needs 结构（先在新版本复测 needs 行为再改回）。
- **CI 时间预算**：全量 317 项测试在容器内 ~20s（SQLite 毫秒级），CI 总时长 ~25s（静态门禁 + TDD），远小于 3h 超时。
