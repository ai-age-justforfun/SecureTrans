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
│  push/PR  │  lint    │  pytest  │  94项全量 │  package.sh   │
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

*文档结束 | SecureTrans CI/CD + GitOps 架构 v1.0 | 2026-08-27*
