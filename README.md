# SecureTrans — 轻量级跨网文件审批摆渡系统

> 版本：v2.7.6 | 阶段：Release（正式发布）— RC 验收通过，生产运行观察期 1 周（2026-11-27 起）
> 技术栈：Flask 3.0 + Flask-Login + SQLite + os.rename 0拷贝摆渡
> 开发模式：主干开发（Trunk-Based Development）+ 单分支 main + AI 辅助人机协同（AGENTS v2.0）
> 部署：Rocky Linux 8.10 单网卡（10.10.30.8），**podman 容器 `securetrans-docker` 监听 8000**（ADR-043），Python 3.12 venv，容器 TZ=Asia/Shanghai；原生 gunicorn+systemd 保留为回退通道

---

## 项目简介

SecureTrans 是面向中小企业的轻量级单向跨网文件审批摆渡系统，解决内网红区/黄区到外网绿区的文件安全外发问题。

**核心价值**：审批可控、摆渡0拷贝、归档可审计。

**核心设计**：
- **os.rename 0拷贝摆渡**：同文件系统内只改目录项，不移动数据块，毫秒级完成
- **免审批机制**：特征码匹配的文件自动通过（支持压缩包/Vivado Bitstream 等规则，可手工配置；v2.4.0 起支持组合规则 = 特征码 AND 后缀，如 tar.gz/Vivado .bin,.bit）
- **分级审批**：合作方一级审批，非合作方二级审批（二级审批人已在一级审批过则自动跳过）
- **轻量级部署**：单服务器 + SQLite + NAS，支撑50人到200人
- **双模式部署**：测试环境（本地文件系统+Flask）/ 生产环境（NAS + 容器内 gunicorn），`.env` 一个开关切换；生产默认 podman 容器形态，原生 systemd 为回退
- **双 OS 支持**：Windows（waitress）与 Linux（gunicorn）均可一键部署，离线依赖随发布包内置
- **飞书审批通知（v2.7.x，ADR-051~055）**：提交/审批/驳回 7 个事件异步推送飞书，失败不阻塞业务；独立配置域（开关/网关地址/token/超时/App ID 可配），App Secret 只存网关 `.env` 可经界面一次性下发；待审批通知自动补"提交人部门 + 请部门负责人审批"
- **网络面隔离（业务语义）**：内/外网均属公司内部网络分区（内网=提交/审批区，外网=接收/下载区），无 NAT、不向互联网开放、无攻击威胁；分面隔离为**单向摆渡流程管控**而非防攻击——外网面仅登录+下载，管理接口 403。单网卡按来源网段（`INTERNAL_CIDRS`）识别，双网卡可绑内网 IP 物理隔离

---

## 快速开始

### 本地开发 / 测试环境

```bash
cd src
cp env/test.env .env          # 测试环境配置（默认 DEPLOY_MODE=testing）
python -m venv venv
# Windows: venv\Scripts\activate
# Linux:   source venv/bin/activate
pip install -r requirements.txt
python app.py
```

访问 http://localhost:8000，初始账号 `admin / Init@123456`（统一为 .env `RESET_PASSWORD` 默认值；Windows dev 与生产部署一致，部署后每次重置为该密码，登录后建议尽快修改（不强制）改密）。

### 运行测试

```bash
# 先启动服务（在 src/ 目录下）
cd src && python app.py

# 另一个终端运行测试
cd tests
python test_api.py
# 预期：380项测试全部通过，通过率100%（Windows dev）；CI 容器全量 + 性能门禁
```

### 一键部署（服务器，Rocky Linux）

```bash
# 1. 上传发布包 securetrans-<版本>.tar.gz 到服务器
tar xzf securetrans-v2.6.0.tar.gz -C /opt/securetrans --strip-components=1
cd /opt/securetrans

# 2. 一键部署（容器形态：podman load 镜像 → docker-deploy.sh；原生回退用 deploy.sh）
sudo bash infra/deploy.sh

# 3. 部署验证（510 项全量测试；admin 凭据自动取 .env RESET_PASSWORD；BASE_URL 自动适配 .env HOST/PORT；若 admin 密码已手工修改，用 VERIFY_ADMIN_PASS 显式传入）
bash infra/verify.sh   # 510 项全量；admin 凭据自动取 .env RESET_PASSWORD

# 4. 防火墙放行 8000（Alpha 内测：内网 + 办公外网访问）
sudo firewall-cmd --permanent --add-port=8000/tcp && sudo firewall-cmd --reload
```

详见 [部署指南（唯一）](docs/DEPLOY.md) — 测试/生产/单双网卡/Windows/Alpha 上线/防火墙配置，统一到一份文档。

---

## 目录结构

```
SecureTrans/
├── README.md                 # 本文件（项目入口，人 + AI 同步查阅）
├── AGENTS.md                 # AI协作指南 v2.0（Part A=AI辅助软件工程方法+Prompt模板，Part B=项目规范）
├── .gitignore                # Git忽略规则
├── LICENSE                   # MIT许可证
├── src/                      # 源代码（按功能模块组织）
│   ├── app.py                # Flask主程序（单文件，含所有API，模块级初始化）
│   ├── requirements.txt      # Python依赖
│   ├── start.sh              # 测试环境启动脚本（Flask自带服务器）
│   ├── start-production.sh   # 生产环境启动脚本（gunicorn）
│   ├── start.bat             # Windows启动脚本
│   ├── env/                  # 12-Factor 分层配置（ADR-016）
│   │   ├── test.env          # 测试环境配置（WSL + AD mock）
│   │   ├── dev.env           # 开发环境配置（Windows 本地 + AD mock）
│   └── static/               # 前端静态文件（SPA + 登录页）
├── tests/                    # 自动化测试
│   └── test_api.py           # 全量API测试脚本（510项，标准库urllib无额外依赖；凭据参数化 TEST_ADMIN_USER/TEST_ADMIN_PASS）
├── docs/                     # 统一文档（数字前缀排序，持续刷新）
│   ├── 00-lean-startup-phase-map.md   # Lean Startup三阶段映射与决策门
│   ├── 01-scrum-io-definition.md      # AI时代人机协同Agile方法论模板(v3.0，SE 3.0+变更分级+三重范式+防眩晕)
│   ├── 02-prd.md                     # 产品需求文档（内部版本v2.2，文件名不带版本号）
│   ├── 03-psf-process.md              # PSF阶段标准流程
│   ├── 04-pmf-process.md              # PMF阶段标准流程（下一阶段准备）
│   ├── 05-test-cases.md               # 测试用例
│   ├── 06-test-report.md              # 测试报告（510项全通过 + 生产实测记录）
│   ├── 07-psf-sprint4-retrospective.md # PSF阶段迭代小结
│   ├── 08-cicd-gitops-architecture.md # CICD/GitOps架构规划
│   ├── 09-preprod-verification.md     # 生产预验收清单
│   ├── 10-prod-sim-verification.md    # 生产模拟验证（+ 测试报告txt）
│   ├── 11-architecture-evolution.md   # 架构演进（Flask→FastAPI→Nginx 等决策）
│   ├── 12-project-retrospective.md   # 项目复盘总结（PSF 阶段全链路）
│   ├── 13-backlog-hypotheses.md      # Backlog 推演假设与验证标准（PMF 前哨，ADR-027）
│   └── DEPLOY.md                      # 部署指南（唯一，含测试/生产/双OS/网络隔离/防火墙）
└── infra/                    # 基础设施配置
    ├── deploy.sh             # 一键部署脚本（9步自动化, Linux）
    ├── deploy.ps1            # 一键部署脚本（Windows）
    ├── verify.sh             # 部署验证脚本（510项，BASE_URL 自适应 + 凭据自动取 .env RESET_PASSWORD）
    ├── smoke.sh              # 生产只读冒烟（11 项，部署门禁，ADR-053）
    ├── feishu-gateway/       # 飞书单向通知网关（10.10.30.114:8090，ADR-052/055）
    ├── get-offline-python.sh # 离线 Python 3.12 RPM 获取（联网 Rocky8 跑一次）
    ├── nginx-securetrans.conf        # Nginx双网卡配置
    ├── nginx-securetrans-single.conf # Nginx单网卡配置
    ├── securetrans.service   # systemd服务配置（gunicorn，${HOST}:${PORT} 变量展开）
    └── package.sh / release.ps1 # 打包与Gitea发布
```

---

## 核心业务流程

```
用户上传文件 → 计算MD5 + 特征码匹配 → 免审批判定
                                          │
                          ┌───────────────┴───────────────┐
                          │                               │
                    所有文件匹配特征码                存在不匹配文件
                          │                               │
                    自动通过（0级）                   人工审批流
                          │                               │
                          │                    ┌──────────┴──────────┐
                          │                    │                     │
                          │              合作方（一级审批）    非合作方（二级审批）
                          │                    │                     │
                          └────────────────────┴─────────────────────┘
                                               │
                                          os.rename 0拷贝
                                          staging → external
                                               │
                                          外网下载（流式读取）
                                               │
                                          过期清理（凌晨2点）
                                          os.rename external → archive
```

---

## API 接口一览

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/auth/login | 登录 |
| GET/POST | /api/auth/logout | 退出登录 |
| GET | /api/auth/me | 获取当前用户 |
| POST | /api/auth/change-password | 修改密码 |
| POST | /api/submissions/upload | 上传文件（流式，支持大文件） |
| POST | /api/submissions | 创建提交单 |
| GET | /api/submissions | 提交单列表 |
| GET | /api/submissions/{id} | 提交单详情 |
| GET | /api/submissions/pending/my | 待我审批 |
| POST | /api/submissions/{id}/approve | 审批（通过/驳回） |
| GET | /api/external/files | 已摆渡文件列表 |
| GET | /api/external/{id}/download/{filename} | 下载文件 |
| GET/POST | /api/admin/local-users | 用户管理 |
| DELETE | /api/admin/local-users/{username} | 删除用户 |
| POST | /api/admin/local-users/{username}/reset-password | 重置密码 |
| POST | /api/admin/partners | 合作方白名单管理 |
| POST | /api/admin/approvers | 审批人配置管理 |
| GET/POST | /api/admin/feature-rules | 特征码规则管理（含单规则 toggle） |
| GET/POST | /api/admin/role-mappings | AD角色映射 |
| POST | /api/admin/ad/search | 搜索AD用户 |
| POST | /api/admin/cleanup-expired | 手动触发过期清理 |
| GET | /api/config/feature-rules | 特征码规则（含单规则开关） |
| GET/PUT | /api/config/system | 系统配置（有效期/大小上限/免审批总开关） |
| GET | /api/audit-logs | 审计日志（时间线 + 统计） |
| GET | /api/stats | 统计数据 |
| GET | /api/health | 健康检查（含 deployMode/stage/resetPassword 字段） |

---

## 发布与版本

- **版本号单一来源**：`src/app.py` 的 `APP_VERSION`（前端 index.html 同步），文档内版本号统一
- **发布阶段（.env APP_STAGE，显示 vX.Y.Z-stage）**：alpha=自测 → beta=内部测试 → rc=发布候选 → release=正式发布；`/api/health` 返回 `stage`，登录页/品牌副标题/页面显示 `vX.Y.Z-stage`，运维期可随时改 .env 切换阶段。**v2.7.6 起生产 APP_STAGE=release**
- **打包**：`bash infra/package.sh <版本>` → `packages/securetrans-<版本>.tar.gz`（含 offline-deps 离线 wheel）
- **发布**：`powershell -File infra/release.ps1 -Version v<版本>` → Gitea Release（源码包 + 离线依赖包）
- **Docker 双通道（v2.7.0 起，ADR-038/039）**：Gitea Release 第 5 资产 `securetrans-vX.Y.Z-image.tar.gz`（离线 `docker load` / `podman load`）；GitHub 走 GHCR（`ghcr.io/ai-age-justforfun/SecureTrans`，在线 pull）
- **版本记录**：Git tag（`v2.7.6`）+ Gitea Release 资产 + SHA256 校验
- **变更记录**：文档内部版本号（如 PRD v2.2）独立演进，关键需求变更用 Git tag
- **发布触发规则**：
  - **文档-only 变更**（README/AGENTS/docs/*.md）：commit + push main 即可，**不 bump 版本、不打包、不建 Release**——文档随仓库持续演进，代码发布时包内自动带入最新
  - **代码/脚本/配置模板变更**（影响可部署产物）：bump APP_VERSION + 全量回归 + package + release + git tag
  - 版本号是发布产物属性，APP_VERSION 只在代码发布时递增；文档内部版本号（如 PRD v2.2、AGENTS v1.6）独立演进
  - **RC/Release 后**（Alpha/Beta 完成）：默认不逐次发布，关键里程碑手工发布

---

## 研发流程

### 方法论
- **大阶段**：Lean Startup（PSF → PMF → Scale），每阶段有决策门
- **迭代**：Scrum（1周Sprint for PSF，2周Sprint for PMF），Sprint作为研发工作分解阶段，在过程文档中体现
- **开发模式**：主干开发（Trunk-Based Development），单分支 main，临时开发拉分支，合入后删除
- **交付**：DevOps（轻量CI/CD，蓝绿部署）
- **可复用模板**：AI 人机协同敏捷工程模板（独立仓库 [openwrtadmin/ai-collab-agile-template](http://localhost:3000/openwrtadmin/ai-collab-agile-template)，供其他创业项目复用）

### Git 工作流

```
main ────●────●────●────●────  始终可部署
           \        /
            feature-xxx  临时分支（开发→测试→合入→删除）
```

- **main 分支**：始终可部署，直接推送或PR合入
- **临时分支**：开发新功能时拉取（如 `feature/ad-ldap`），测试通过后合入 main 并删除
- **Commit 规范**：`<type>(<scope>): <描述>`，不强制带 Sprint 编号，可关联 Story 编号

### 当前阶段
**PSF → Release（v2.7.6 正式发布）**：服务器（Rocky 8.10 单网卡 10.10.30.8）部署完成，
510 项自动化测试 100%（Windows dev）+ CI 容器全量 TDD + 800MB 性能压力测试 + 3-5 用户并发测试通过
（MD5 端到端一致）+ CD 全自动部署打通（Release 发布 → 生产自动升级）+ **Docker 双通道发布（Gitea image.tar.gz + GitHub GHCR，ADR-038/039）**；
beta 功能验收已完成，进入 RC 验证（生产 18000 蓝绿容器部署验证），通过后正式 release。全项目复盘见 [项目复盘总结](docs/12-project-retrospective.md)。

详见：
- [Lean Startup阶段映射](docs/00-lean-startup-phase-map.md)
- [AI 时代人机协同 Agile 方法论模板 v3.0（SE 3.0 + L1/L2/L3 变更分级 + HITL/HOTL/HOOTL + PDCA 微循环 + RTM 缓冲 + 防眩晕）](docs/01-scrum-io-definition.md)
- [产品需求文档 PRD v2.2](docs/02-prd.md)
- [PSF阶段标准流程](docs/03-psf-process.md)
- [测试用例](docs/05-test-cases.md)
- [测试报告（510项全通过 + 生产实测）](docs/06-test-report.md)
- [PSF阶段迭代小结](docs/07-psf-sprint4-retrospective.md)
- [项目复盘总结（PSF 全链路）](docs/12-project-retrospective.md)
- [版本结果汇总（v1.5.0→v2.7.6 全量）](docs/17-version-summary.md)
- [PSF 阶段 Scrum 复盘（Inspect & Adapt 标准版）](docs/18-psf-retrospective.md)
- [GitHub 迁移方案（Active，v2.6.5 首验落地）](docs/14-github-migration.md)
- [GitLab CICD 实验线（已隔离归档 2026-09-16；配置资产全量固化 §7；ADR-049 双开发域分离，主仓库不再推送 GitLab）](docs/15-gitlab-cicd.md)
- [跨平台 CICD 指南（Gitea/GitHub/GitLab 对比+模板+入门）](docs/CICD.md)
- [用户使用手册（普通用户 + 管理员）](docs/16-user-manual.md)
- [生产预验收清单](docs/09-preprod-verification.md)
- [部署指南（唯一部署文档）](docs/DEPLOY.md)

### 下一阶段
**PMF（产品-市场匹配验证）**— 流程文档已就绪，核心是AD/LDAP集成和真实部署试点。

详见 [PMF标准流程](docs/04-pmf-process.md)。

---

## 技术决策记录（ADR）

| # | 主题（完整决策见 docs/ADR.md） | 版本 |
|---|--------------------------------|------|
| 001 | os.rename 0拷贝摆渡 | v2.2 |
| 002 | Flask 而非 FastAPI | v2.2 |
| 003 | 主干开发 + 单分支（sprint 只作文档阶段） | v2.2 |
| 004 | Python 3.12 + venv 隔离（离线 wheel cp312） | v2.2 |
| 005 | 非硬编码：环境变量驱动（配置/部署/运行） | v2.2.14 |
| 006 | 网络面安全假设（封闭数据中心，firewalld 可跳过） | v2.2.14 |
| 007 | 发布策略：代码变更才发布 / 文档-only 不 bump | v2.2.14 |
| 008 | 端口/网络面选型（当前：单网卡单端口，演进见文） | v2.2.14 |
| 009 | 部署凭据：RESET_PASSWORD 全链路唯一源 | v2.2.27 |
| 010 | .env 与 SQLite 配置一致性：三档权威矩阵 | v2.2.20 |
| 011 | 数据生命周期与运维功能化（备份/恢复/重置/mock） | v2.2.27 |
| 012 | 性能与文件完整性：800MB + MD5 四方一致 | v2.2.24 |
| 013 | AD 真实 LDAP：精确匹配 + 连接测试 + openldap-clients | v2.2.29 |
| 014 | 外网下载链路 + 备份删除 + 系统工具抬头 | v2.2.30 |
| 015 | 备份彻底分离 + 审批人闭环 + 可见性治理 | v2.2.31 |
| 016 | 12-Factor 三环境一体化（env/ 模板） | v2.2.26 |
| 017 | 测试/生产环境隔离（verify 全量 / smoke 只读） | v2.2.27 |
| 018 | CI/CD 分层：fast-check→tdd→package + 计数门禁 | v2.2.26 |
| 019 | CI 运行环境隔离（runner 常驻 + 容器化目标态） | v2.2.26 |
| 020 | 配置单一来源 + 容器 CI 实跑 + 系统依赖统一 | v2.3.7 |
| 021 | WSL CI 稳定性根因（保活 + 单 job 规避 needs bug） | v2.3.7 |
| 022 | 依赖双轨（在线优先离线兜底）/ 支持矩阵 / 发布形态 | v2.3.7 |
| 023 | 文件名安全清理 + AD 改密前端拦截 | v2.3.7 |
| 024 | CD 自动部署（Release → 生产，SSH 密钥） | v2.3.7 |
| 025 | AI 辅助人机协同开发流程规范（方法论） | v2.4.x |
| 026 | 以 git 为中心三环境 + WSL 原生路径 | v2.4.x |
| 027 | 技术-商业双闭环复盘（stepping-stone 方法论） | v2.4.x |
| 028 | 特征码精简 / 审批审计修复 / 并发与 UX | v2.5.1 |
| 029 | 特征码规则合并 / 配置持久化 / 免审批判定修复 | v2.6.0 |
| 030 | .ltx 格式化JSON / 性能门禁入CI / 发布说明 / 审批人首次播种 | v2.6.1 |
| 031 | 合作方全量编辑 / WSL 测试退居二线 / 生产冒烟=业界标准 | v2.6.2 |
| 032 | 合作方联系人必填 / 无状态上传+临时清理 / 文档体系单源化 | v2.6.3 |
| 033 | 审计策略：系统动作审计边界（超时归档审计 / 临时清理不审计） | v2.6.4 |
| 034 | 有效期口径统一：文件有效期为唯一超时源（pending/approved 共用） | v2.6.5 |
| 035 | 管理员附件审查下载（仅内网）+ 环境前置检查 preflight | v2.6.6 |
| 036 | 单一权威仓库 + 备份仓库体系（架构决策，docs/14 为执行手册） | v2.6.6 |
| 037 | 环境职责分层 + 双仓 CI/CD/Release 职责对齐（测试合一/发布权限隔离/CD 目标隔离） | v2.6.7 |
| 038 | Docker 一站式交付 + 蓝绿部署验证 + Registry 分发策略（RC 启动，ADR-039 修订决策 2） | v2.7.0 |
| 039 | kaniko 废弃 → 容器内 docker CLI + 宿主 docker.sock / WSL 环境重建 / v2.7.0=RC | v2.7.0 |
| 040 | act_runner 脱离 systemd → nohup 直跑 + 无窗口保活（WSL systemd 非 PID1 周期性重置修复） | v2.7.0 |
| 041 | v2.7.0 双通道发布回归修复（release.yml 版本提取 + cd.yml MD5 资产歧义） | v2.7.0 |
| 042 | AI 访问外部系统认证：token > ssh >> 账号密码 + 本地 credential 文件不入库（方法论）；**读取约定=按 token 前缀（ghp_/github_pat_ 等）取真 token 行，标签行勿当 token（L0 误读事故已记）** | v2.7.3 |
| 043 | 部署形态正式切换：Docker 默认、原生退役 + 蓝绿切换顺序纪律（先停原生再起容器） | v2.7.0 |
| 044 | 审计统计四维口径重构（提交文件数按名去重+审批+下载+管理操作仅admin）+ CD 正式切换 Docker 通道（v2.7.1 首个验证） | v2.7.1 |
| 045 | GitLab CICD 实验线打通（gitlabcicotest：独立 WSL+docker+数据，跨平台 CI/CD 迁移教训，docs/15） | v2.7.1 |
| 046 | Git 服务器选型：Gitea/GitHub/GitLab 优劣势对比 + 场景选型建议（方法论，未来项目可复用） | v2.7.1 |
| 047 | 发布触发自动化与 AI 边界：触发=git 事件自动（tag→Release→CD 全链自治）；AI 只保留打 tag/发布决策+应急 dispatch；执行顺序=GitLab stages 严格顺序 / Gitea-GitHub 事件链（CI+Release 并行、CD 在后）；失败回退=先回滚生产再修代码，生产回滚≠代码回退（docs/CICD §10.4） | v2.7.1 |
| 048 | AI 时代人机协同 Agile 方法论采纳（v2.0→v3.0）：SE 3.0 范式 + L1/L2/L3 变更分级 + HITL/HOTL/HOOTL + PDCA 微循环 + RTM 缓冲并入 Agile + 防眩晕 | v2.7.1 |
| 049 | GitLab 隔离——双开发域分离：个人域=本地+Gitea+GitHub，公司域=GitLab（另一 AI 工具）；**隔离终态 4a7ffe6 不再使用**：gitlabcicotest 已合并删除、CI 触发改 push main、tags=runner 标签非分支、Release=仅 4 sources 源码包（有意简化）、main 全链实证全绿、已与 Gitea/GitHub 对齐；GitHub 认证=PAT token（2FA） | v2.7.3 |
| 050 | CICD Workflow 组织方式——总分式（入口+明细）vs 单文件：触发即作用域/权限最小化/失败隔离/跨平台迁移优，传值与配置共享劣；单文件适用纯 CI 单平台线性项目；本项目保持总分式（薄壳+infra/*.sh+secret 最小作用域）；GitLab 根 .gitlab-ci.yml=平台硬性入口（不扫描 .gitlab/，删根文件则不执行流水线，根文件 include 明细非冗余） | v2.7.2 |
| 051 | 飞书审批通知=独立旁路通道：异步派发、失败不阻塞业务；7 事件固定（免审批直通仅发提交人）；账号→AD 邮箱→飞书三级解析；界面三列表+详情可观测（成功/失败/跳过） | v2.7.3 |
| 052 | 关键服务器零出网 + 专用单向通知网关（10.10.30.114:8090）：仅放行 open.feishu.cn:443 + 源 IP 白名单（仅生产机）+ 预共享 token；网关只做鉴权→渲染→发送→记账，不做业务决策/不落正文；App ID/Secret 只存两处且禁入 git | v2.7.3 |
| 053 | 生产部署只读冒烟全量通过=发布门禁：`smoke.sh` 任一失败即 `exit 1`（禁"警告继续"假绿），docker/原生两通道一致；冒烟用内网 IP、凭据取 RESET_PASSWORD（改密用 VERIFY_ADMIN_PASS）；断言须容错、登录失败明示凭据原因 | v2.7.3 |
| 054 | 飞书通知=独立配置域（外挂式 channel）：`feishu_config` 表（DB 权威、`.env` 播种/回退），配置页独立卡片可配 9 项（开关/网关 IP·端口·路径·完整 URL/token/超时/入口/AppID）；App Secret 仍只存网关；保存即时生效；`NOTIFY_HOOKS` hook 化（业务 8 处调用点零改动，可并接钉钉/邮件）；`POST /api/admin/feishu-config/test` 可单测通知，配置页显示网关 /health 状态灯；测试基线 467→496 | v2.7.3 |
| 055 | 飞书 App Secret 受控下发 + 部门补全：网关 `POST /admin/secret`（白名单 IP + token，先验凭据再原子写 `.env` 600 并热重建客户端）；业务侧只做内存转发不落库/不落盘/不回显（审计只记动作）；`deploy-gateway.sh` 支持 `--secret-file` 且升级沿用本机 `.env`（不依赖 AI）；待审批通知经飞书通讯录补"提交人部门 + 请部门负责人审批"（缺权限自动省略不阻塞）；`/health` 增 `app_id_masked/contact_readable`；测试基线 496→510 | v2.7.6 |
| 056 | 通知可读性收口 + 生产时区：通知单号只显示短号 `#8位hex`（不引入流水号，A 方案）；部门取主部门（`is_primary_dept`）；`submission_status` 无审批人不再渲染"审批人：-"；容器时区 `Asia/Shanghai`（`-e TZ` 固化进 docker-deploy.sh，同时带 `PATH=/venv/bin:...`）；**外网下载可见性=提交人本人，有意设计不修改**；`/api/health` 回显 `resetPassword` 保留（reset 即回初始密码） | v2.7.6 |

> **使用方式**：决策冲突时以 docs/ADR.md 对应条目为准；新增决策只追加编号（ADR-0xx），不修改历史条目。
> 最新落点摘要（ADR-031/032/033/034 核心）：合作方全量编辑+联系人必填；WSL 测试收敛为 dev+CI 两环境；生产只读冒烟=业界标准；
> 无状态上传明示+未提交临时文件 24h 系统回收（TEMP_FILE_HOURS 可配）；ADR 全文集中在 docs/ADR.md；
> 审计闭环：已审批未下载超时归档逐单审计（system_archive_expired）、手动清理留痕（admin_cleanup_manual）、临时清理不审计（ADR-033）；
> 有效期统一：提交未审批+审批未下载统一按"文件有效期"（default_expiry_days）超时归档，审计区分超时原因（ADR-034）。
> 仓库治理（ADR-036 架构）：单一权威仓库（本地 Gitea，承载全部 git 操作与生产 CD）+ 备份仓库（GitHub 等，容灾/分发/独立验证）；每阶段聚焦主要矛盾、其余跟随调整形成动态平衡；备份仓永不接触生产；切换权威的触发条件见 docs/14。
> GitHub 独立 CI/CD/Release 闭环（2026-09-15）：两条链路完全独立——Gitea（权威仓）CI→Release→CD→生产；GitHub（备份仓）CI-TDD→RELEASE（ubuntu 云端构建 4 资产）→CD-SIM（ubuntu 云端 Docker 仿真，无本地 Docker/self-hosted runner）；历史手动双传保留为对齐手段，正常发布以 release.yml 云构建为准（docs/14）。CD-SIM 含数据洁净门禁（业务文件=0+提交记录=0，验证全新容器）；actions 已升级 v7（Node24 消除弃用告警）。
> Docker 镜像构建路径（ADR-039 修订，2026-09-15）：kaniko 废弃（本地 Debian bookworm 宿主工具链污染导致 kaniko 构建 apt postinst 报 GLIBC_2.38 失败）；改为 Gitea release job 容器内 docker-ce-cli + act_runner container.options 挂载宿主 docker.sock → 本地 WSL docker daemon 构建（runc 完整隔离）；WSL 测试宿主重建为真实 Rocky 10.1（rocky10-ci，glibc 2.39 干净环境）；v2.7.0 阶段定为 rc（Release Candidate）。

## 许可证

[MIT License](LICENSE) — 可自由使用、修改、分发，保留版权声明即可。

---

---

*SecureTrans v2.7.6（Release）| 2026-11-27*
