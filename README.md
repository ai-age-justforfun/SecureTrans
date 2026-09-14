# SecureTrans — 轻量级跨网文件审批摆渡系统

> 版本：v2.6.2 | 阶段：PSF→Beta（问题-方案匹配验证）— Beta 内部测试（运行收集问题中）
> 技术栈：Flask 3.0 + Flask-Login + SQLite + os.rename 0拷贝摆渡
> 开发模式：主干开发（Trunk-Based Development）+ 单分支 main + AI 辅助人机协同（AGENTS v2.0）
> 部署：Rocky Linux 8.10 单网卡（10.10.30.8），gunicorn + systemd，Python 3.12 venv

---

## 项目简介

SecureTrans 是面向中小企业的轻量级单向跨网文件审批摆渡系统，解决内网红区/黄区到外网绿区的文件安全外发问题。

**核心价值**：审批可控、摆渡0拷贝、归档可审计。

**核心设计**：
- **os.rename 0拷贝摆渡**：同文件系统内只改目录项，不移动数据块，毫秒级完成
- **免审批机制**：特征码匹配的文件自动通过（支持压缩包/Vivado Bitstream 等规则，可手工配置；v2.4.0 起支持组合规则 = 特征码 AND 后缀，如 tar.gz/Vivado .bin,.bit）
- **分级审批**：合作方一级审批，非合作方二级审批（二级审批人已在一级审批过则自动跳过）
- **轻量级部署**：单服务器 + SQLite + NAS，支撑50人到200人
- **双模式部署**：测试环境（本地文件系统+Flask）/ 生产环境（NAS+gunicorn+systemd），`.env` 一个开关切换
- **双 OS 支持**：Windows（waitress）与 Linux（gunicorn）均可一键部署，离线依赖随发布包内置
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
# 预期：361项测试全部通过，通过率100%（Windows dev）；WSL 测试环境 361 项
```

### 一键部署（服务器，Rocky Linux）

```bash
# 1. 上传发布包 securetrans-<版本>.tar.gz 到服务器
tar xzf securetrans-v2.6.0.tar.gz -C /opt/securetrans --strip-components=1
cd /opt/securetrans

# 2. 一键部署（9步自动化：Python 3.12 获取 → venv → 依赖 → .env → systemd → 启动验证）
sudo bash infra/deploy.sh

# 3. 部署验证（361项全量测试；admin 凭据自动取 .env RESET_PASSWORD；BASE_URL 自动适配 .env HOST/PORT；若 admin 密码已手工修改，用 VERIFY_ADMIN_PASS 显式传入）
bash infra/verify.sh

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
│   └── test_api.py           # 全量API测试脚本（361项，标准库urllib无额外依赖；凭据参数化 TEST_ADMIN_USER/TEST_ADMIN_PASS）
├── docs/                     # 统一文档（数字前缀排序，持续刷新）
│   ├── 00-lean-startup-phase-map.md   # Lean Startup三阶段映射与决策门
│   ├── 01-scrum-io-definition.md      # AI辅助Agile-Scrum流程模板(v2.0，Scrum Guide审计+裁剪)
│   ├── 02-prd.md                     # 产品需求文档（内部版本v2.2，文件名不带版本号）
│   ├── 03-psf-process.md              # PSF阶段标准流程
│   ├── 04-pmf-process.md              # PMF阶段标准流程（下一阶段准备）
│   ├── 05-test-cases.md               # 测试用例
│   ├── 06-test-report.md              # 测试报告（361项全通过）
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
    ├── verify.sh             # 部署验证脚本（361项，BASE_URL 自适应 + 凭据自动取 .env RESET_PASSWORD）
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
- **发布阶段（.env APP_STAGE，显示 vX.Y.Z-stage）**：alpha=自测 → beta=内部测试 → rtm=内部使用 → release=正式发布；`/api/health` 返回 `stage`，登录页/品牌副标题/页面显示 `vX.Y.Z-stage`，运维期可随时改 .env 切换阶段
- **打包**：`bash infra/package.sh <版本>` → `packages/securetrans-<版本>.tar.gz`（含 offline-deps 离线 wheel）
- **发布**：`powershell -File infra/release.ps1 -Version v<版本>` → Gitea Release（源码包 + 离线依赖包）
- **版本记录**：Git tag（`v2.2.x`）+ Gitea Release 资产 + SHA256 校验
- **变更记录**：文档内部版本号（如 PRD v2.2）独立演进，关键需求变更用 Git tag
- **发布触发规则**：
  - **文档-only 变更**（README/AGENTS/docs/*.md）：commit + push main 即可，**不 bump 版本、不打包、不建 Release**——文档随仓库持续演进，代码发布时包内自动带入最新
  - **代码/脚本/配置模板变更**（影响可部署产物）：bump APP_VERSION + 全量回归 + package + release + git tag
  - 版本号是发布产物属性，APP_VERSION 只在代码发布时递增；文档内部版本号（如 PRD v2.2、AGENTS v1.6）独立演进
  - **RTM 后**（Alpha/Beta 完成）：默认不逐次发布，关键里程碑手工发布

---

## 研发流程

### 方法论
- **大阶段**：Lean Startup（PSF → PMF → Scale），每阶段有决策门
- **迭代**：Scrum（1周Sprint for PSF，2周Sprint for PMF），Sprint作为研发工作分解阶段，在过程文档中体现
- **开发模式**：主干开发（Trunk-Based Development），单分支 main，临时开发拉分支，合入后删除
- **交付**：DevOps（轻量CI/CD，蓝绿部署）

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
**PSF（问题-方案匹配验证）— Beta 内部测试运行中**：服务器（Rocky 8.10 单网卡 10.10.30.8）部署完成，
deploy.sh/verify.sh 全部通过，361项自动化测试 100%（Windows dev + WSL test）+ 800MB 性能压力测试 + 3-5 用户并发测试通过
（MD5 端到端一致）+ CD 全自动部署打通（Release 发布 → 生产自动升级，run #136）；**清库后启动内部
同事 beta 测试，运行收集问题，持续迭代**。全项目复盘见 [项目复盘总结](docs/12-project-retrospective.md)。

详见：
- [Lean Startup阶段映射](docs/00-lean-startup-phase-map.md)
- [AI辅助Agile-Scrum流程模板 v2.0](docs/01-scrum-io-definition.md)
- [产品需求文档 PRD v2.2](docs/02-prd.md)
- [PSF阶段标准流程](docs/03-psf-process.md)
- [测试用例](docs/05-test-cases.md)
- [测试报告（361项全通过）](docs/06-test-report.md)
- [PSF阶段迭代小结](docs/07-psf-sprint4-retrospective.md)
- [项目复盘总结（PSF 全链路）](docs/12-project-retrospective.md)
- [生产预验收清单](docs/09-preprod-verification.md)
- [部署指南（唯一部署文档）](docs/DEPLOY.md)

### 下一阶段
**PMF（产品-市场匹配验证）**— 流程文档已就绪，核心是AD/LDAP集成和真实部署试点。

详见 [PMF标准流程](docs/04-pmf-process.md)。

---

## 技术决策记录（ADR）

### ADR-001：os.rename 而不是软链接
- 0拷贝性能等价，但全平台原生支持，NAS兼容性好，权限简单
- 详见 PRD v2.2 第2.2节

### ADR-002：Flask 而不是 FastAPI
- Flask-Login生态成熟，团队学习成本低，50人规模性能不是瓶颈
- 详见 PRD v2.2 第3.2节

### ADR-003：主干开发 + 单分支
- 小团队/副业项目，避免多分支合并冲突，main始终可部署
- Sprint作为研发分解阶段在文档中体现，不用目录结构做版本管理

### ADR-004：Python 3.12 + venv 隔离
- 与系统环境完全隔离（`python -m venv --copies`），离线 wheel cp312 匹配；Rocky 8 用 AppStream/EPEL/离线 RPM 获取，无需源码编译

### ADR-005：非硬编码原则——环境变量驱动（配置/部署/运行）
- **背景**：prototype/MVP 阶段代码内默认值可快速验证；但环境从 Windows 本地开发 → WSL 测试 → Rocky 生产
  逐步复杂、逐步灵活，地址/端口/网段/存储路径/密钥必须动态配置，不能写死
- **决策**：
  - **动态采集**：所有环境相关配置从 `.env` 环境变量读取，代码/脚本只保留合理默认值（如 HOST=0.0.0.0、PORT=8000）作 fallback，生产必须显式配置
  - **动态部署**：deploy.sh 运行期探测环境自适应——Python 3.12 三级获取（系统→离线RPM→dnf）、ReadWritePaths 按 NAS 存在性渲染、防火墙按 firewalld 启用状态执行、健康检查目标从 .env HOST/PORT 构造
  - **动态运行**：systemd EnvironmentFile + `${HOST}:${PORT}` 变量展开，改 .env + `systemctl restart` 即生效，无需重跑部署（原 ADR-005 并入）
  - **动态采集（脚本）**：verify.sh BASE_URL、deploy.sh 防火墙端口均运行期从 .env grep 采集，不静态编码
  - **前端**：API 全部相对路径（同源），不写死服务器地址；时间显示用服务器系统时区
- **已落点（v2.2.14）**：app.py（HOST/PORT/NAS_ROOT/SECURETRANS_DATA/AD_HOST/SECRET_KEY 全 os.getenv）；
  **v2.2.19 起 AD 属性字段可配置**：AD_USER_FIELD（登录名查询属性，默认 sAMAccountName）/ AD_DISPLAY_FIELD（默认 displayName）/
  AD_MAIL_FIELD（默认 mail）/ AD_GROUP_FIELD（默认 memberOf），企业 AD 定制字段时在 .env 调整，非硬编码
  securetrans.service（变量展开）、deploy.sh（健康检查/防火墙/ReadWritePaths 自适应）、verify.sh（BASE_URL/防火墙检查）、
  start-production.sh（`-b ${HOST:-127.0.0.1}:${PORT}`）、release.ps1（GITEA_BASE 环境变量覆盖）
- **强制要求**：新增代码/脚本禁止写死地址、端口、网段、路径；必须从 `.env` 或运行环境读取，默认值仅作开发 fallback

### ADR-006：网络面安全假设（封闭数据中心场景）
- **背景**：服务器位于数据中心防火墙内部，办公网 ↔ 数据中心经 IPsec 加密隧道互联；内/外网均为公司内部网络分区
  （内网=提交/审批区，外网=接收/下载区），无 NAT、不向互联网开放、无攻击威胁
- **决策**：假设网络层安全由公司基础设施承担（IPsec 加密 + 防火墙边界），**系统防火墙（firewalld）可不启用**（简化部署）；
  应用层保留**流程管控级隔离**：外网面仅登录+下载、管理接口 403（get_network_zone 两级识别），并保留认证/审批权限/审计/文件限制底线
- **已落点**：INTERNAL_CIDRS 业务语义、get_network_zone()（X-Network-Zone 头 → 客户端IP+网段兜底）、deploy.sh/verify.sh 防火墙可跳过
- **边界（重要）**：本假设仅适用于当前封闭数据中心；若部署到互联网可达环境，必须启用 Nginx + HTTPS + firewalld（见 DEPLOY.md）

### ADR-007：发布策略与调测门禁
- **背景**：小团队/副业项目，调测期迭代密集；发布 = 正式版本（Gitea Release + git tag + 包资产），代表可部署产物
- **决策**：
  - **调测期（PSF Alpha/Beta）**：代码/脚本/配置模板每次变更即发布（密集发布，便于服务器及时验证）
  - **正式发布后（RTM）**：默认不逐次发布，关键里程碑手工发布
  - **文档-only 变更**（README/AGENTS/docs/*.md）：commit + push main，不 bump、不打包、不建 Release（随仓库演进，代码发布时包内自动带入最新）
  - **调测门禁**：本地调测中间阶段保持双环境 TDD 全量回归——Windows 开发环境（testing：`python test_api.py` 361项）
    + WSL 测试环境（production：`infra/verify.sh` 361项），**全部通过才允许 bump + 发布**
  - 版本号是发布产物属性，APP_VERSION 只在代码发布时递增；文档内部版本号独立演进

### ADR-008：端口/网络面部署选型（单/双网卡 × 单/双端口）
- **背景**：参考商用 SDT 工具——单网卡双端口部署（对内 up:8089 提交/审批、对外 down:8889 下载）；
  我们当前为单网卡单端口（8000，源 IP 分面）。需评估"端口分面"是否带来实质安全增益，并确定演进路径
- **三方案对比**：
  | 方案 | 架构 | 分面机制 | 防伪造提交 | 部署复杂度 |
  |---|---|---|---|---|
  | 1 单网卡单端口（当前） | 8000 单端口 | 应用层 403（外网面仅登录+下载，管理接口拒绝） | 应用层校验 + 会话认证兜底 | ★ 已落地 |
  | 2 单网卡双端口（SDT 式） | up:8089 内网提交/审批 + down:8889 外网下载 | 网络层隔离（防火墙只放内网→up 端口） | 提交面外网物理不可达，增益/成本比最高 | ★★ |
  | 3 双网卡双端口 | 双网卡各自绑定 | 网络层 + 物理层隔离 | 最强 | ★★★★ |
- **关键判断**：
  - **防伪造报文**：方案1 的弱点是提交类接口若应用层识别有漏洞（如伪造转发头），外网仍可达；方案2 把提交面在
    防火墙层关死（外网到不了 up 端口）；方案3 物理隔离
  - **方案2 增益/成本比最高**：仅新增 Nginx 双 server + 防火墙规则，代码零改动（get_network_zone 已支持
    X-Network-Zone 头）——这是 SDT 选双端口的真实原因：隔离面从应用层下沉到网络层
  - **方案3 当前不值得**：在封闭数据中心（ADR-006）前提下，双网卡物理隔离的边际增益趋近零，运维复杂度翻倍
  - **方案2 代价**：两个端口均明文 HTTP，与方案1 同风险，不构成新弱点；真正要补的是 HTTPS（Nginx 终止），内网 Alpha 可暂缓
- **决策**：当前（PSF Alpha、人员少、封闭数据中心、ADR-006 安全假设成立）**保持方案1 不变**。
  演进路径：Alpha 方案1 → PMF 阶段按需升级方案2（一个迭代：Nginx 双 server + 防火墙规则 + 文档）→
  仅当外网面真实暴露互联网时启用方案3（DEPLOY.md 已有双网卡配置参考）
- **已落点**：v2.2.14（单网卡单端口 + INTERNAL_CIDRS + get_network_zone 两级识别；nginx-securetrans-single.conf
  单网卡配置 + nginx-securetrans.conf 双网卡配置保留备用）

### ADR-009：部署凭据策略——admin 密码全链路统一（部署重置=测试默认=界面提示，不强制改密）
- **背景**：verify.sh 原用写死的 admin/Admin@123 登录验证；生产环境 admin 密码被手工修改后验证直接 401 失败；init_db 首次播种写死 Admin@123、登录页写死提示、deploy.sh 重置为 RESET_PASSWORD、verify 又取另一套——三处不一致导致反复出现"部署后 verify 用户名或密码错""界面显示与实情不符"。
- **决策（全链路统一，禁止出现第二份默认密码）**：
  - **单一来源**：`.env RESET_PASSWORD` 是唯一重置密码配置源（默认 Init@123456）。init_db 首次播种 admin、deploy.sh 每次部署重置、verify.sh/test_api.py 测试默认凭据、登录页提示、admin 重置密码接口——**全部同源**，默认值统一 Init@123456
  - **每次部署重置**：deploy.sh 9.7 步调用 `python app.py --reset-admin-password`，将 admin 密码重置为 .env RESET_PASSWORD（幂等；保证部署完成即可登录、verify 直接通过）；`--reset-admin-password` 为独立 CLI，不启动 Web 服务
  - **不强制改密，仅建议**：去掉"首次登录强制修改"，改为"登录后建议尽快修改（不强制）"；admin 可自行修改，修改后 verify 用 `VERIFY_ADMIN_PASS` 显式传当前密码
  - **verify 凭据自适应**：verify.sh 自动从 .env RESET_PASSWORD 取凭据（`VERIFY_ADMIN_USER`/`VERIFY_ADMIN_PASS` 环境变量可显式覆盖）
  - **测试不碰真实密码**：test_api.py 凭据参数化（TEST_ADMIN_USER/TEST_ADMIN_PASS，默认取 RESET_PASSWORD）；改密测试用专用用户 testpwuser（创建→改密→新密码登录→改回→清理），绝不修改真实 admin 密码（生产安全）
  - **deploy.sh 兜底**：.env 缺失 RESET_PASSWORD 行时自动追加默认值，避免 verify 凭据与部署重置不一致
- **已落点**：v2.2.27（app.py init_db 播种 RESET_PASSWORD / CLI --reset-admin-password / 登录页动态显示密码+建议改密 / 全库清理 Admin@123 硬编码；deploy.sh/verify.sh/test_api.py 文案与凭据统一）

### ADR-010：.env 与 SQLite 配置一致性——配置权威矩阵（强制）
- **背景**：system_config 存 SQLite、AD 参数在 .env、另有 feature_rules/approvers 等，长期调整后文本配置与数据库共存，管理员和开发者不清楚哪个生效，出现"改了 .env 没生效 / 改了界面被 .env 覆盖"等配置错误与遗忘问题。
- **决策（配置权威矩阵，三档，各档唯一权威）**：
  - **部署级配置（.env 唯一，进程启动读取，改后 restart 生效）**：DEPLOY_MODE / HOST / PORT / INTERNAL_CIDRS / NAS_ROOT / SECURETRANS_DATA / SECRET_KEY / RESET_PASSWORD。由 systemd EnvironmentFile 机制加载，.env 是唯一操作点，界面只读展示（配置总览页）。
  - **运行时配置（SQLite 唯一，界面可改、即时生效，不再回写 .env）**：system_config（app_name / auto_approval_enabled / default_expiry_days / max_file_size_mb）。api_update_system_config 已删除 .env 回写，防止两处漂移。
  - **AD 连接配置（从 .env 过渡迁移到 SQLite ad_config，管理页可配，运行期 DB 权威）**：10 个键（ad_enabled / ad_host / ad_domain / ad_base_dn / ad_bind_dn / ad_bind_password / ad_user_field / ad_display_field / ad_mail_field / ad_group_field）。首次部署 init_db 在表空时从 .env 播种一次（source=env）；系统配置页"从 .env 导入"可把 .env 当前值导入 DB；保存后 source=db 即时生效（无需重启）；某键为空值时读取回退 .env/默认。AD 登录、AD 用户查询、登录域后缀判断全部改运行时读取。
  - **AD 手工验证（/api/admin/ad/search 返回 verifyCommand）**：AD 用户搜索接口同源生成 `ldapsearch` 验证命令（bind 密码用 **** 占位），管理员可在服务器上手工执行确认 bind 凭据/网络连通；**程序直连 AD 无需服务器入域、无需 SSSD**——应用通过 ldap3 协议 bind 查询，与服务器是否加入 AD 域完全独立（用户已有大规模 sssd 场景不受影响，二者互不干扰）
- **一致性机制**：①播种一次（ad_config 空表从 .env 导入，避免手工重复录入）；②**配置总览页**（系统配置页卡片：左 .env 部署级只读 + 右 DB 运行时配置，逐项标来源 env/db 与更新时间，防遗忘）；③**冲突规则：DB 优先**（运行时配置界面保存即权威，.env 不再回写）；④**文档化**：本 ADR + AGENTS.md + DEPLOY.md 三处同步，明文公开口径。
- **边界**：部署级配置不迁 DB（systemd EnvironmentFile 机制依赖 .env）；AD_BIND_PASSWORD 脱敏显示（前2位+****），重新输入才覆盖；.env 仅负责部署级参数与首次播种，运行期不再参与业务判断。
- **已落点**：v2.2.20（app.py：ad_config 表/AD_ENV_MAP/get_ad_config_value/mask_secret/authenticate_ad·api_login·api_search_ad 运行时读取/api_update_system_config 去回写 + 3 个管理 API：GET·PUT /api/admin/ad-config、POST /api/admin/ad-config/import、GET /api/admin/config-overview + 前端 AD 配置卡片与配置总览卡片 + test_api.py 318 项全量回归）

### ADR-011：数据生命周期与运维功能化（强制）
- **背景**：测试环境部署时需要清空老库/恢复初始配置，生产环境原则上不能动数据但需要按需备份+清理、备份、恢复；开发/测试/生产环境代码配置数据不分离导致验证不可靠。业界最佳实践：运维期内有用的功能应收尽收进系统（Web API + 界面 + TDD 可调），脚本只保留首部署与离线场景。
- **决策（三环境一套代码配置数据脚本）**：dev(Windows) / test(WSL) / prod(Rocky) 程序与配置完全一致（DEPLOY_MODE 开关 + .env）；差异只在数据策略——dev/test 用**模拟数据 + verify.sh 全量验证**闭环，prod 用**备份/恢复/出厂重置**；代码、配置、数据三者分离可自由组合。
- **系统功能（admin 菜单"系统工具"，确认码保护）**：备份 `POST /api/admin/ops/backup` + 列表 `GET /api/admin/ops/backups`（**scope 拆分**：`system`=仅系统 DB（升级前后回退用）/ `business`=仅 NAS 业务文件（换存储/归档用）/ `all`=两者，界面系统/业务两个备份卡 + 列表 hasDb/hasNas 标记；DB 用 sqlite backup API 一致性快照 + NAS 业务目录 → data/backups/backup-<ts>）；恢复 `POST /api/admin/ops/restore`（确认码 RESTORE，支持 scope，回退=再恢复之前的备份）；出厂重置 `POST /api/admin/ops/reset-factory`（确认码 RESET，**自动先备份** → 清空 → init_db 重建 → admin 密码重置为 .env RESET_PASSWORD）；模拟数据 `POST /api/admin/ops/mock-data`（确认码 MOCK，**仅 testing 模式**，生产 403）。
- **离线脚本（infra/，服务停止时最安全）**：`ops-backup.sh [all|system|business]` / `ops-restore.sh <name> [all|system|business]` / `ops-reset.sh`（备份+清理，调 CLI `--reset-factory`）/ `ops-mock.sh`（调 CLI `--mock-data`）；deploy.sh 支持 `RESET_DB=1` 部署时出厂重置（测试环境用）。
- **与 ADR-010 不重叠**：ADR-010 管配置权威（静态三档），ADR-011 管数据生命周期与运维操作（动态）；mock+verify 构成 ADR-007 调测门禁的执行闭环。
- **已落点**：v2.2.27（app.py ops 路由 scope 拆分 + 前端系统/业务备份卡 + ops-*.sh scope 参数 + test_api.py 318 项 + deploy.sh 9.8 RESET_DB；v2.2.23 初版：ops 路由 + CLI --reset-factory/--mock-data + 前端系统工具页 + test_api.py 318 项 + infra/ops-*.sh）
- **v2.2.29 强化（备份命名区分，普通人可识别）**：备份目录名改为 `backup-system-<ts>` / `backup-business-<ts>` / `backup-all-<ts>`（名字即类型）；列表带 `type` 字段；系统工具页**两个独立备份列表**（系统备份列表 / 业务数据备份列表），恢复按钮不再选 scope——**后端按备份名自动推导类型**，杜绝"从同一个备份混恢复"；旧版 `backup-<ts>` 兼容识别为 all
- **v2.2.30 备份删除（不永久保留）**：新增 `DELETE /api/admin/ops/backups/<name>`（admin）——前端备份列表行加"删除"按钮（确认后删除，删除不可恢复）；后端校验备份名（backup- 前缀 + 无路径穿越，路径穿越由 Flask 路由 405 兜底）；审计日志 ops_delete_backup

### ADR-012：性能与文件完整性——800MB 全链路压力测试 + MD5 端到端四方一致（强制）
- **背景**：生产部署前需要正式的性能与完整性验证——800MB 大文件 上传→审批摆渡→下载 全链路性能；文件完整性（MD5）端到端保证，防止传输/摆渡过程损坏。
- **决策**：
  - **MD5 四方一致（强制）**：上传流式计算 MD5 存入 submission_files → 下载时从 DB 取 MD5 写入 download_records.md5 并回传响应头 `X-File-MD5` → 下载内容本地再算 MD5 比对（上传值 = DB 值 = 响应头 = 下载内容）；审计日志 download 记录带 MD5；前端上传列表/详情显示完整 MD5
  - **性能压力测试工具 tests/perf_test.py（系统级能力，TDD 可调）**：流式生成大文件（边写边算 MD5）→ 流式 multipart 上传 → 合作方提交单一级审批（计时含 os.rename 摆渡）→ 流式下载 → MD5 四方比对 → JSON 报告 + 阈值断言 + 自动清理；`PERF_SIZE_MB`（默认 800）/`PERF_ADMIN_*`/`PERF_MAX_*_S` 环境变量，退出码 0/2
  - **上传上限统一口径**：`.env MAX_FILE_SIZE_MB`（单文件上限，默认 800）唯一配置；`MAX_CONTENT_LENGTH` 自动 = 文件上限 + 1MB（multipart 封装余量），禁止手工配置——否则 800MB 文件 + boundary 封装会 413（v2.2.24 实测命中并修复）
  - **删除提交单（运维功能，admin + 确认码 DEL）**：清 DB 三关联表 + STAGING/EXTERNAL/ARCHIVE 三目录，防误触；对 admin 前端可见
- **与 ADR-011 不重叠**：ADR-011 管数据生命周期（备份/恢复/重置），ADR-012 管性能验证与文件完整性（删除提交单是其中运维项，确认码机制一致）
- **已落点**：v2.2.24（app.py：download_records.md5 迁移/下载 X-File-MD5/删除提交单 API/MAX_FILE_SIZE_MB；前端完整 MD5 + 删除按钮；tests/perf_test.py；test_api.py 318 项；800MB 实测：上传 338 MB/s / 摆渡 34ms / 下载 350 MB/s / 全链路 5.94s / MD5 四方一致）

### ADR-013：AD 真实 LDAP 集成——精确匹配 + 连接测试 + openldap-clients 依赖（强制）
- **背景**：v2.2.28 前 `/api/admin/ad/search` 在 ad_enabled=true 时是 TODO 占位（永远返回空 users + 手工命令），界面"查询失败，没有匹配"但手工 ldapsearch 成功——根因是**程序从未实现真实查询**，不是密码/网络问题；复制命令按钮把多行命令内联进 onclick 导致换行截断（只复制出"="）；verifyCommand 在用户名后加 `*` 通配（用户要求精确匹配：有就是有，没有就是没有）。
- **决策**：
  - **真实 LDAP 查询（ldap3，已内置依赖）**：`_ad_connection()` 用 AD_HOST/AD_BIND_DN/AD_BIND_PASSWORD 做 bind（同源读取 ad_config/.env）；`_ad_search_users()` 按 `(&(objectClass=user)(<ad_user_field>=<keyword>))` **精确匹配**（无通配符 `*`），返回 username/displayName/mail/department；异常翻译成可读原因（49/52e=凭据错、socket/timeout=网络、NoSuchObject=base_dn 错、invalidDN=DN 格式错），界面显示 error 不再静默"无匹配"
  - **空关键字不 dump**：返回提示"请输入用户名关键字"（不返回全量用户，防泄露）；打桩模式（ad_enabled=false）仍返回 mock 演示用户
  - **AD 连接测试（新增 `POST /api/admin/ad/test`）**：AD 配置卡片"测试连接"按钮 + 可选输入用户名——用当前配置实测 bind + 精确搜索该用户（存在/不存在/失败原因），生成审计日志 ad_test；替代/补充手工 ldapsearch
  - **openldap-clients 为部署必装项**：deploy.sh 自动安装（联网 dnf/apt），离线环境提前准备 RPM；verifyCommand 注释附带安装提示；AD 配置卡片展示提示
  - **复制命令修复**：多行命令改用 JS 数组缓存 + 索引 onclick（`copyAdCmd(i)`），不再内联进 HTML 属性
  - **程序直连 AD 无需入域**：应用 ldap3 bind+search，与服务器是否加入 AD 域（sssd）完全独立，互不干扰（已有大规模 sssd 场景不受影响）
- **与 ADR-010 不重叠**：ADR-010 管 AD 配置存储权威（SQLite），ADR-013 管 AD 查询执行与验证方式（真实查询/精确匹配/连接测试/依赖）
- **已落点**：v2.2.29（app.py：_ad_err/_ad_connection/_ad_fields/_ad_search_users + api_search_ad 真实查询/精确匹配/error 字段 + POST /api/admin/ad/test；前端：AD 配置卡片测试连接按钮 + 搜索错误显示 + copyAdCmd 修复；deploy.sh openldap-clients 自动安装；test_api.py 318 项）

### ADR-014：外网下载链路修复 + 备份删除 + 系统工具抬头确认（强制）
- **背景（第一批需求第一个 story 回归）**：内网提交→审批→外网下载，但用户实测"内网可下载、外网无法下载"——根因：前端下载弹窗 `showDownloadFiles()` 调 `/api/submissions/<id>` 拉详情，该路径**不在外网白名单**（EXTERNAL_ALLOW_PREFIXES 仅 /login /static/ /api/auth/* /api/health /api/external/），外网一律 403 → 弹窗打不开 → 无法下载。内网全放行所以正常。**测试遗漏**：网络面矩阵只测了列表/下载接口，未测下载弹窗的详情链路。
- **决策**：
  - **外网详情接口 `GET /api/external/submissions/<sub_id>`**（login_required）：仅 approved/downloaded 状态可见，返回提交单详情 + files 明细（与内网详情同构）；前端下载弹窗改用该接口（`/api/external/` 前缀内外网均放行）——内网外网同一弹窗同一接口
  - **`/api/health` 加入外网放行**：外网页需显示版本/阶段（loadUser 调用），仅返回版本/模式/时间无敏感数据；此前外网 403 靠前端 try/catch 兜底降级，属隐性缺陷
  - **管理详情接口维持拒绝**：`/api/submissions/<id>` 外网仍 403（回归保护测试：外网管理详情被拒 + 外网详情放行）
  - **备份删除（不永久保留）**：`DELETE /api/admin/ops/backups/<name>`（admin），前端备份列表行加"删除"按钮（confirm 确认，删除不可恢复）；后端校验 backup- 前缀、拒绝路径穿越；属 ADR-011 数据生命周期运维功能化的补充（备份本身可删，数据删除纪律不变）
  - **系统工具页抬头修复（真实根因）**：navigate() 特判曾正确设置"系统工具 / System Tools"，但**语言刷新 applyI18n() 的 titles 映射缺 ops 键** → `t(_titles['ops']||'ops')` 回退键名覆盖为 "ops"（renderOps 异步完成后触发，故用户看到抬头变成 ops）。修复：applyI18n 对 `currentPage==='ops'` 同样输出固定中英双语；浏览器实测中英切换后仍为"系统工具 / System Tools"
- **外网面测试清单（自动化 + 手工，alpha 收尾前逐项验证）**：
  - 自动化（tests/test_api.py 22d 网络面矩阵，已覆盖）：登录页/首页/静态资源/me/health/外网列表/外网详情/下载文件 放行；修改密码/提交列表/上传/用户管理/合作方/审批人/特征码/系统配置/审计/统计/管理详情 拒绝；非法 X-Network-Zone 回退 internal
  - 手工（生产环境，双网段/双网卡）：
    1. 外网（办公网段）打开 → 仅"外网下载"菜单，无提交/审批/管理菜单，无修改密码入口
    2. 外网登录 → 外网下载列表可见已摆渡文件 → 点下载 → 弹窗含文件明细 → 下载成功且 MD5 一致
    3. 外网直接输入管理 URL（/api/admin/*、/api/config/*）→ 403
    4. 外网切换中英文 → 正常显示、下载功能不受影响（不出现"管理操作请从内网访问"误报）
    5. 外网浏览器刷新/强刷（Ctrl+F5）→ 页面为最新版（防缓存旧前端）
    6. 内网对照：全功能正常（提交/审批/管理/系统工具）
- **与 ADR-003 不重叠**：ADR-003 管网络模式（单/双网卡）部署选型，ADR-014 管外网下载功能链路与测试矩阵；备份删除并入 ADR-011 生命周期，此处仅记录本版落点
- **已落点**：v2.2.30（app.py：/api/external/submissions/<sub_id> + /api/health 放行 + DELETE /api/admin/ops/backups/<name>；index.html：showDownloadFiles 用外网详情接口 + 备份删除按钮 + i18n；test_api.py 318 项（新增：外网管理详情拒绝/外网详情放行/health 放行/备份删除成功/列表不含/404/非法名/applyI18n ops 特判；10d 段自包含强化）；双环境 TDD Windows 318 / WSL 318 全通过）

---

### ADR-015：备份彻底分离 + 生产备份健壮性 + 可见性治理 + 审批人闭环（强制）
- **背景（v2.2.31 用户验收 6+1 组问题）**：① verify.sh 生产业务备份 500（v2.2.29 基线，本地/WSL 全过但生产 NAS 环境失败——copytree 对已存在目标/符号链接/特殊文件名不健壮）；② 改密提示方位写"右上角"，实际按钮在左下角；③ 备份界面仍混合（"全部备份"按钮 + 列表含 all 类型 + "恢复系统"文案混淆）；④ 免审批开关已关仍显示"匹配特征码"；⑤ 合作方选中后接收方单位仍显示；⑥ 外网下载显示所有人文件（应仅本人且已走完审批）；⑦ 无审批人配置时提交 pending 永久卡死。
- **决策**：
  1. **备份健壮化**：copytree 加 `dirs_exist_ok=True + symlinks=True + ignore 临时/锁文件(.nfs*/.DS_Store/*.tmp/*.lock)`，异常清理半成品并返回可读错误（不再裸 500）。
  2. **备份界面彻底分离**：移除"全部备份"按钮与列表 all 混合过滤；系统区块只列 backup-system-*（创建/列表/恢复/删除），业务区块只列 backup-business-*（创建/列表/恢复/删除）；恢复按钮统一"恢复"；旧版混合备份 backup-all-* 不显示，给出提示建议删除。API 层保留 all 兼容（旧脚本），界面不暴露。
  3. **特征码匹配受免审批总开关约束**：MD5 必选；匹配判定 = 免审批开关开启 且 对应特征码启用，否则 matched=false、matchedRules=[]（不显示"匹配特征码"）。
  4. **合作方选中隐藏姓名/单位/邮箱**：仅"其他（自行填写）"显示三字段（提交后自动加入合作方清单，去重）。
  5. **外网可见性治理**：外网列表/详情/下载三处均校验 submitter=当前用户——每个用户只能看自己提交且已批准（approved/downloaded）的文件，杜绝看/下载他人文件。
  6. **审批人闭环**：init_db 幂等播种 admin 为一级+二级审批人（界面可见、逻辑闭环）；提交时按接收方类型校验审批人存在——公司内部/合作方必须有一级审批人，非合作方必须有一级+二级审批人，缺失则提交失败返回可读提示（不产生无法审批的死单）。
  7. **改密提示方位**：左下角（实际按钮在侧栏底部）。
- **已落点**：v2.2.31（Windows 318 / WSL 318 全过；生产业务备份 500 修复后需在服务器重跑 verify 复验）

### ADR-016：12-Factor 三环境一体化（强制）
- **决策**：`env/*.env` 分层配置（dev/test/prod 三模板）为唯一配置键源；app.py 启动自动加载同目录 `.env`（不覆盖已注入环境变量，systemd EnvironmentFile 优先）；`AD_MOCK_MODE` 模拟目录（dev/test 用，生产 false）；tests/mock 种子与基线（docs/07 需求↔测试追踪矩阵）；Gitea Actions CI（.gitea/workflows/ci.yml + 本地 runner）
- **已落点**：v2.2.26（env/ 三模板 + 12-Factor 加载 + mock 目录 + CI 首跑）；详见 DEPLOY.md 5.5

### ADR-017：测试/生产环境隔离（三合一，强制）
- **背景**：verify.sh 原为三环境同一全量脚本，生产跑全量必污染（建用户/上传/审批/备份/改配置/改密/清理归档）。
- **决策**：
  1. **代码合一**：`tests/test_api.py` 单脚本承载全量回归 + 冒烟白名单（组 24，10 项纯只读：health/登录/会话/查询/网络面模拟/i18n 资源/登出）。
  2. **入口分离**：`infra/verify.sh`=dev/test/CI 全量（ENV_ROLE=test，本脚本读 .env 自动注入）；`infra/smoke.sh`=生产 allowlist 只读冒烟（SMOKE_MODE=1，仅组 24）。
  3. **fail-safe 护栏（宁可误拒不可误写）**：ENV_ROLE=prod 或 SMOKE_MODE=1 时，组 1~23 整组代码不执行（含请求层拦截 POST/PUT/DELETE/PATCH 与上传），生产误跑全量零副作用；`/api/health` 返回 `envRole` 便于监控确认。
  4. **与 ADR-016 不重叠**：ADR-016 管三环境配置/数据分层与 CI 骨架；ADR-017 管测试执行入口与生产零写护栏。

### ADR-018：CI/CD 分层与质量门禁（强制）
- **背景**：原 CI 仅单 job 全量回归（push 触发），无秒级门禁、无测试计数防缩水、发布包靠本地手工 package.sh。
- **决策**：
  1. **分层流水线（最便宜门禁先失败）**：`fast-check`（语法 py_compile / 版本号双源一致性 / env 模板 ENV_ROLE / 关键脚本完整性，秒级，总是执行）→ `tdd-verify`（全量 TDD，needs fast-check 失败即停）→ `package`（仅 `tags: v*` 触发）。
  2. **质量门禁（防静默删减）**：`test_api.py` 报告段断言计数基线——全量模式 ≥300 项、冒烟模式 ==10 项（白名单为显式维护集合，增减需同步门禁）。
  3. **tag 驱动发布构建（build once, deploy many）**：push tag v* 自动 clone 该 tag → 复用 /opt/securetrans/packages 的 offline-deps → package.sh 构建 → 制品落到共享 packages/（离线环境无 node/网络，不使用 actions/upload-artifact@v4）；实际 Release 资产由 `infra/release.ps1` 手工上传同一制品（发布策略 ADR-014：调测期密集手工，关键点人工发布）。
  4. **并行与 fail-fast**：tdd-verify needs fast-check（秒级门禁失败不浪费全量资源）；package needs 前两者。
  5. **与 ADR-016/017 不重叠**：ADR-016 管三环境配置/数据分层，ADR-017 管测试/生产执行隔离，ADR-018 管流水线结构与门禁。

### ADR-019：CI 运行环境隔离与静态门禁（强制）

- **背景**：CI 首跑发现 ① act_runner 偶发 shutdown（WSL 会话回收，导致 push 漏跑）；② act_runner 直接在宿主执行 job，公开仓库有逃逸到主机的风险；③ CI 与测试环境共用 /opt/securetrans，存在版本/数据干扰。
- **决策**：
  1. **runner 常驻**：act_runner 以 systemd 单元（`/etc/systemd/system/act_runner.service`）常驻，`Restart=always` + 开机自启（WSL 重启/崩溃自动拉起）。
  2. **静态门禁前置**：新增 `infra/static_check.py`（零依赖 AST 检查：语法编译 / 未定义名称（作用域链）/ 重复函数类定义 / 未使用 import），挂入 ci.yml fast-check 第一步之后；已清理历史遗留未使用 import（app.py render_template、test_api.py time）。
  3. **CI 容器化隔离（目标态）**：构建可复用镜像 `securetrans-ci:3.12`（python:3.12-slim + 离线 wheelhouse 同源依赖）；容器入口 `infra/ci_test.sh`（无 systemd 直接 gunicorn loopback；配置经环境变量注入不写 .env；数据目录 /data 随容器销毁）→ 每次 job 全新容器 + 新配置 + 新数据，避免版本干扰与宿主污染。切换前提：Docker Desktop 启用 WSL Integration（需重启 Docker Desktop，短暂中断 Gitea）→ act_runner label 改 `docker://securetrans-ci:3.12`。
  4. **与 ADR-016/017/018 关系**：ADR-016 管三环境配置/数据分层；ADR-017 管测试/生产执行隔离；ADR-018 管流水线结构与计数门禁；ADR-019 管 runner 运行方式与 job 运行环境隔离。

### ADR-020：配置单一来源 + 容器 CI 实跑 + 系统依赖统一（强制）
- **背景**：① CI 用环境变量注入、测试/生产用 .env，两条路配置信息可能漂移（CI 漏注入 AD_MOCK_MODE 曾致 AD mock 登录 401）；② "能否与 gitea 无关另起 docker 做 CI"——需要验证；③ 生产缺 openldap-clients 等系统工具，测试环境同样缺（环境不一致）。
- **决策**：
  1. **配置单一来源**：`env/*.env` 是唯一配置键定义源——CI 容器 `source env/test.env` 全键注入（app.py 12-Factor env 优先，不写 .env 文件）；测试环境 deploy 用 test.env 生成 .env；生产用 prod.env.template 生成 .env；fast-check 新增"配置键一致性"门禁（dev/test 键集合完全一致、prod 可多不可缺），防三环境配置漂移。**配置信息一致 = 同源键 + 自动校验**，而非仅读取过程一致。
  2. **WSL 独立 docker daemon**：`dnf install docker-ce`（WSL rocky10-st 在线装 29.8.0），与 Docker Desktop（跑 Gitea）完全独立——不启用 WSL Integration、不重启 Docker Desktop、Gitea 零中断。镜像 `docker save`（Windows）→ `docker load`（WSL）传输。
  3. **容器 CI 实跑**：act_runner 双 label（`securetrans-wsl:host` 宿主 / `securetrans-ci:docker://securetrans-ci:3.12` 容器）；fast-check/tdd-verify 跑容器（全新环境），package 留宿主（访问共享 packages/）。容器 job 关键点：① act_runner 容器模式**不自动 checkout**，需显式 `git clone`（容器经 **WSL 网关 IP** 172.29.x.1:3000 访问 Gitea，/proc/net/route 动态解析）；② 测试端口 18000 避开宿主 8000；③ 实测 fast-check 稳定 3s、tdd-verify 容器内 309/309 全绿。
  4. **runner 抗信号**：WSL 环境偶发外部 SIGTERM（journal 无 Stopping），`shutdown_timeout: 3h` 让 runner 收到信号后**等运行中 job 完成再退**，不再中断 CI（根因调查记 docs/08 Backlog B5）。
  5. **系统依赖统一**：程序运行依赖全走 venv + wheelhouse（离线打包）；系统级工具（ldapsearch/openldap-clients 等）**在线 dnf / 离线 rpm 双模式**——测试环境先装齐（已装），生产离线时 rpm 进离线依赖包。
- **已落点**：2026-09-11 容器化 CI 首跑（run 81-87）；fast-check 稳定成功；容器 TDD 309/309 本地+CI 实测；config.yaml.example 入仓；文档四件套同步。

### ADR-021：WSL CI 稳定性根因与修复（强制）
- **背景**：CI 在 WSL rocky10-st 间歇性中断/假绿（run 91 tdd 卡 14 分钟、run 92/93/94 tdd 20s 假绿"成功"但无测试输出），逐层取证（wslmon 进程监控 / act_runner 日志 / docker ps / workspace 残留 / 容器内进程抓取）定位双因。
- **决策**：
  1. **WSL 发行版空闲自动终止 → 保活**：WSL2 发行版无交互会话即被终止（后台 daemon 不算活跃），act_runner 因此反复 SIGTERM。修复：Windows 计划任务 `WSL-Rocky10-KeepAlive` 每 1 分钟执行 `wsl.exe -d rocky10-st -- sleep 45`（保持连接）。实证：13:24:25 后 act_runner 连续稳定 >20 分钟（此前每 1-3 分钟必崩）。
  2. **act_runner v0.2.11 needs bug → 单 job**：含 `needs` 的容器 job 解析异常（"runs-on not defined"/"No steps found"→ 容器秒退、Gitea 误标成功）。修复：**合并 fast-check+tdd-verify 为单 job `ci-check`**（无 needs，静态门禁步骤在前秒级先失败、全量 TDD 在后），package 去 needs（仅 tag 独立跑）。
  3. **CI 可信基线**：run 97 实证 ci-check 22s 成功；容器内进程取证 ci_test.sh + gunicorn + pytest 真跑；318/318 全绿（模拟同流程 20s 完成 318 项，SQLite 毫秒级）。
- **与 ADR-019/020 关系**：ADR-019 管 runner 常驻/容器隔离；ADR-020 管配置单一来源/双 label/依赖统一；ADR-021 管"WSL 发行版保活 + CI 单 job 规避 needs bug"（运行稳定性修复）。
- **已落点**：2026-09-11 修复闭环；docs/08 第十节 + Backlog B5 更新为已解决；保活计划任务已创建（Windows 管理员可见）。**修正（同日）**：网络核实 WSL 2.6.1.0 无终端会话 15-20s 关闭 VM（microsoft/WSL#13416）——诊断为版本相关行为；保活计划任务因每 1 分钟弹窗已删除，改为"用户保持 WSL 终端活跃 + CI job 22s 短时"策略，如再现空闲终止再启用隐藏版保活。

### ADR-022：依赖双轨 / 支持矩阵 / 发布形态（强制）
- **背景**：用户确认三个业界实践方向，并要求"在线优先、离线兜底"在测试环境实测。
- **决策**：
  1. **依赖安装在线优先、离线兜底**：deploy.sh 统一为先 `dnf/pip 在线` → 失败自动回退 `offline-python/`（Python 3.12 RPM）/ `offline-deps/`（cp312 wheel）→ 再无则明确报错退出（不静默降级）。在线命令固化在脚本+文档，离线包为 Release asset——**两者均入 Gitea**。
  2. **支持矩阵只保证一种组合**：Python 3.12 + Rocky 8.10（生产）/ WSL rocky10-st（测试）/ Windows dev（开发）；venv（--copies 与系统隔离）+ wheelhouse（cp312）三环境一致；其他组合 best-effort；后续升级整体评估。
  3. **发布形态两轨并存**：仓库=源码全工程（"源码即发布"）；Release=发行包（tar.gz + offline-deps + md5/sha256）。**保持全量打包不精简**——理由：离线部署一包全含（src/infra/env/offline-deps/offline-python/tests/docs）、服务器可自测 verify、体积数 MB 可忽略；未来对外分发或体积显著增长时拆"源码包+部署包"。
- **已落点**：2026-09-11 deploy.sh 双轨反转完成（在线优先）+ docs/08 第十一节 + WSL 测试环境实测记录。

### ADR-023：文件名安全清理 + AD 改密前端拦截（v2.3.7，强制）
- **背景**：Beta 手工验收发现两个缺陷——① 文件夹上传（webkitdirectory）任何数量文件均 HTTP 500（根因：File.name 携带相对路径如 sub/a.txt，后端 open() 因子目录缺失抛 FileNotFoundError）；② AD 用户点击"修改密码"仍弹表单（后端 400 兜底但前端无拦截）。
- **决策**：
  1. **上传接口文件名安全清理**：对 file.filename 统一取 basename（先替换 `\`→`/` 再取末段），空名/`.`/`..` 拒绝（400"非法文件名"）；既防相对路径导致的目录缺失 500，也防路径穿越。
  2. **AD 改密前端拦截**：showChangePwdModal 中 `window._cu.source === 'ad'` 直接提示"AD 用户请在域控制器修改"，不再弹表单（后端 api_change_password 400 兜底不变）。
  3. **空文件夹提示**：handleFiles 空列表直接提示"所选文件夹为空或无文件"；上传成功 toast 显示后端清理后的文件名（data.name）。
- **已落点**：2026-09-11 v2.3.7；复现脚本验证（路径分隔符 500→200，中文/0字节/多文件全 200）；Windows dev 全量 TDD 318/318 通过。

### ADR-024：CD 自动部署打通（Gitea Release → 生产服务器，强制）
- **背景**：从"手工开发/测试/部署"升级为"AI 辅助全自动开发/测试/部署"：CI（静态门禁+TDD）已自动化，部署仍手工。用户放开生产服务器 SSH（10.10.30.8），要求 Release 发布后自动推送部署。
- **决策**：
  1. **CD 链路**：Gitea Release 发布（release: published）或手动 workflow_dispatch → CD job（WSL act_runner 容器 securetrans-ci:3.12，已含 openssh-client/rsync/jq）→ 经 WSL 网关访问 Gitea API 下载发布资产 + MD5 校验 → scp 到服务器 /opt/securetrans-release/ → ssh 执行 infra/cd-deploy.sh（轻量升级：备份→代码更新保留 .env/data/nas/venv→重启→健康检查→只读冒烟）→ 结果回报。
  2. **SSH 认证**：CD 专用 ed25519 密钥（WSL 生成，公钥入服务器 authorized_keys，私钥经 Gitea repo secret `CD_SSH_KEY` 注入容器，不入仓库）。
  3. **生产安全**：CD 部署不重置 admin 密码、不重建 venv、不覆盖生产数据（与 deploy.sh 全量安装互补，全量安装仅依赖/结构变更时手工执行）；生产只跑只读冒烟 smoke.sh，全量 TDD 只在测试环境（防数据污染）；部署前整体备份（保留最近 5 份）。
  4. **版本策略**：CD 基础设施变更（Dockerfile/cd 脚本/workflow）不 bump 应用版本；应用代码变更才 bump 并发布 Release（ADR-014 调测期密集手工发布不变）。
- **排障要点（已固化为脚本逻辑）**：
  1. **容器访问 Gitea 网关**：act_runner 每任务创建独立 bridge 网络，默认网关 IP 随机且不可达；CI/CD 统一 `CI_GW="${CI_GATEWAY:-172.17.0.1}"`（docker0，实测任意自定义网络容器内稳定可达），保留环境变量覆盖。
  2. **Release 资产 URL**：Gitea API 返回的 `browser_download_url` 为 `http://localhost:3000/...`，容器内 localhost 指向容器自身；下载前 sed 替换 host 为 `${GITEA}`。
  3. **认证回退**：`${{ github.token }}` 经 curl `-H` 注入曾出现 exit 7（值异常）；现为 token 优先 + 失败回退匿名（仓库 public 可读；转 private 后须保证 token 可用）。
  4. **CD job 需先 clone 仓库**：act_runner 容器工作目录默认无仓库文件，`< infra/cd-deploy.sh` 会 No such file；与 ci.yml 一致先 `git clone`（经 CI_GITEA_URL 网关匿名克隆）。
- **已落点**：2026-09-11 v2.3.7 链路打通并全自动部署成功（run #136 success：MD5 校验通过 → scp 35MB → cd-deploy.sh 6/6 → 只读冒烟 11/11 PASS → 服务 active + HEALTH-OK）；备份 /opt/securetrans_backup_20260911_174451。



### ADR-025：AI 辅助人机协同开发流程规范（方法论，强制）
- **背景**：SecureTrans 是首个 AI 辅助人机协同完成的项目（PSF→Beta，166 提交/24 ADR/318 测试/CD 全自动）。
  为后续项目"站在巨人肩膀上"，将 AI 辅助软件工程方法沉淀为规范化、模版化指南。
- **决策**：
  1. **AGENTS.md v2.0（Part A）为 AI 辅助软件工程方法唯一来源**：人机协同分工模型（人=决策/验收，AI=执行/建议）、
     AI 工作流六步（探查→约束→证据→执行→验证→交付）、**Prompt 任务卡模板**（类型/目标/上下文/约束/验收标准/交付形态——
     验收标准必须可执行断言）、敏捷（Scrum/Story）AI 参与点、TDD 底线、CICD 可信原则、发布前 8 项质量门禁。
  2. **复用规则**：新项目复制 AGENTS.md Part A + 任务卡模板；Part B（项目规范）按项目替换。
  3. **与 ADR-024 不重叠**：ADR-024 管 CD 链路实现（Release→生产自动部署），ADR-025 管 AI 辅助开发流程规范（方法论）；
     二者构成"AI 辅助全自动开发/测试/部署"的完整闭环（流程规范 + 工具链路）。
- **已落点**：2026-09-11 AGENTS.md v2.0 + docs/12-project-retrospective.md（首个项目复盘沉淀）。

### ADR-026：以 git 为中心的三环境独立 + WSL 原生路径（强制）
- **背景**：WSL 经 `/mnt/c`（9p 挂载）访问 Windows 文件系统极慢——rsync 逐个 stat 上万文件导致全量回归从"几十秒"退化到"十几分钟"；`package.sh` 在 `/mnt/c` 上 `cp -r` 曾卡死（D+ 状态）。且 9p 的权限/锁语义与 Linux 原生不一致，易产生环境差异误判。
- **决策**：
  1. **以 git 为中心**：Windows dev / WSL test / 生产 三环境各持**独立 git 工作副本**，唯一同步通道 = Gitea（push / pull / clone）。**禁止 rsync/scp 直拷代码目录**（慢 + 版本漂移）。
  2. **WSL 必须使用原生 Linux 路径**（如 `/opt/securetrans`）；**禁止在 WSL 中使用 `/mnt/c`、`/mnt/d` 等 Windows 挂载路径**做开发、测试、打包、运行。
  3. **变更以 commit 为唯一载体**：Windows 侧编辑 → `commit + push main` → WSL `pull`（或 CI/CD 容器 clone）→ 测试/部署。CI/CD 容器每次从 Gitea clone，不接触任何宿主目录。
  4. **环境态不入库**：`.env` / `data/` / `venv/` / `offline-python/` 等由 .gitignore 排除，`git fetch/checkout` 不影响（untracked 保留，已实证）；生产 .env 由部署流程管理。
  5. **WSL runner 运行配置保护**：`/opt/securetrans/.runner` + `config.yaml`（act_runner 注册与配置，label 含 `securetrans-ci:docker://securetrans-ci:3.12`）**不入库**；备份/重置/清理操作**禁止移动或删除二者**——2026-09-12 曾因备份操作丢失（进程内存持有配置才未断 CI），已从 `/opt/securetrans_backup_20260911_142320/` 恢复；缺失时重启 runner 将丢失容器 label。
- **已落点**：2026-09-12 WSL `/opt/securetrans` 初始化为 git 仓库并 pull（HEAD=548a21c，.env/data 保留）；全量回归耗时 十几分钟 → **58.6s**；三环境结果 Windows 350/350 + WSL 100% + CI run 149 success。

### ADR-027：技术-商业双闭环复盘（PSF 收尾 · stepping-stone 方法论，过程成果，强制）
- **背景**：v2.4.x beta 运行期（PSF 收尾），用户要求跳出技术/工程复盘，对"技术-商业双闭环"展开复盘并将过程成果留痕。代码零改动。
- **决策与共识**：
  1. **nginx 暂不引入（日均 5-10 次访问）**：gunicorn 直连 8000 已满足；收益（HTTPS/静态/缓冲/限速）在封闭数据中心（ADR-006）+ 低并发下边际趋近零，成本（多进程面/离线组件/运维面）明确。**升级触发条件**：① 并发上传/下载出现 worker 阻塞（如 2 人同时传 800MB）；② 需要对外 HTTPS/域名/访问限速。届时启用 `infra/nginx` 预研模板（预研不预装）。
  2. **特性治理原则（"想多了"回退复盘）**：PSF 阶段只实现"被使用验证的需求"；"推演需求"一律标记为假设（Backlog/PMF 预备），不在当前实现。已回退案例：双网卡→单网卡单端口（ADR-008）、role 体系→纯 approvers（ADR-015）、强制改密→建议改密（ADR-009）。AI 侧规矩：推演特性标"假设"，用户/真实用户确认"确实需要"才进当前迭代。
  3. **阶段定位**：beta = PSF 收尾（问题/方案验证）；PMF 才验证市场。发布成功 ≠ 产品成功；"万里长征第一步"，可进可退——每个版本是 stepping-stone，密集发布是低成本验证（ADR-014 已固化）。
  4. **方法论：重型 V 模型 → stepping-stone**：需求冻结/大设计/大测试/一次性交付 → 小步快跑、按需调整；**技术债显式记账 + 偿还触发条件**，PSF 阶段是合理投资而非原罪；回退 = 信息。
  5. **人机协同双闭环**：闭环 A（技术-工程-产品：需求→ADR→TDD→CI/CD→发布→beta 已闭环）；闭环 B（商业：PSF 问题/方案验证→PMF 市场验证→Scale，正在收尾 PSF）；过程层（体会/回退/心态）同为项目资产，决策留痕 = 下一轮决策输入。
- **已落点**：2026-09-14 本记录；nginx 升级触发条件列入 Backlog；代码零改动。

### ADR-028：特征码精简 / 审批审计修复 / 并发与 UX（v2.5.1，强制）
- **背景**：beta 手工验收发现三类问题——① Vivado 特征码多条规则重叠（扩展名 .bit 独立规则无同步字也可命中、仅同步字规则无后缀过宽），且真实文件验证发现 .ltx（ILA 探针，JSON 文本）无 bitstream 同步字；② 审批详情审计链错误：内部提交一级通过被误插"自动跳过二级"幻影记录；③ 性能/UX 需求增补。
- **决策**：
  1. **Vivado 规则精简为模板**（内置 22→21 条）：删除"Vivado Bitstream(.bit)"（extension）与"Vivado Bit同步字"（binary 无后缀）；保留唯一 `Vivado Bitstream组合(特征码+后缀)`（hex:AA995566;665599AA AND .bin,.bit，实测覆盖 BOOT.BIN/chiptop.bit）；新增 `Vivado ILA探针(.ltx)`（extension，覆盖 JSON 探针文件）。迁移按 name+type+ext_pattern IS NULL 精确清理旧规则；新规则补充播种默认禁用（老规矩：特征码默认全禁用、免审批总开关默认关闭，管理员手工配置）。
  2. **审批详情审计修复**：公司内部/合作方一级审批通过即摆渡，审批链**不得出现二级记录**（含"自动跳过"注释）；语义B（同人自动跳过二级）仅限非合作方；迁移删除 internal 提交的历史幻影 level=2 记录（仅限 comment 精确匹配"自动跳过二级"者，人工二级记录不受影响）。
  3. **多用户并发性能 story**：`tests/perf_test.py` 新增 `PERF_CONCURRENCY`（3-5 用户 × 独立会话全链路 + MD5 校验）+ `PERF_CONC_SIZE_MB`/`PERF_CONC_MAX_S`；本地实测 3 用户 × 1MB 墙钟 0.56s 全部成功；作为性能回归（非 CI 默认项，按需启用避免拉长流水线）。
  4. **提交页"取消/清空"按钮**：submit.btnCancel 双语 + `cancelSubmit()` 重置所选文件与表单（本地重置，staging 临时文件由系统清理任务回收）；防止"准备文件不对无法取消"。
  5. **AD mock 三环境审计（确认结论）**：dev/test/CI 一律 `AD_MOCK_MODE=true`（组 23 自动探测 mock 全链路，不触网）；生产 `AD_MOCK_MODE=false` 直连真实 AD（SSSD/LDAP 同源兼容）；组 23 生产自动跳过、组 24 冒烟白名单只读。
- **与 ADR-024/025 不重叠**：本 ADR 管单版本功能/审计/性能落点；ADR-024 管 CD 链路；ADR-025 管 AI 辅助流程方法论。
- **已落点**：v2.5.1（Windows dev 全量 TDD 361/361 通过；10g3 审计详情修复 / 10g4 取消按钮 / 10b1 21 条规则覆盖均有断言）。

### ADR-029：特征码规则合并 / 配置持久化 / 免审批判定修复（v2.6.0，强制）
- **背景**：beta 手工验收发现五类问题——① 压缩包类（zip/tar/gz/bz2/xz/zstd）同时存在"后缀名规则 + 二进制特征码规则"两条，需合并为唯一组合规则（同 bitstream 严格度）；② .ltx（Vivado ILA 探针，标准 JSON 文本）仅扩展名规则，需加二进制特征码；③ 特征码"启用/禁用"不持久化——升级/重启后管理员已启用的配置被重置为禁用；④ 免审批开关全开且特征码命中仍走人工审批（生产复现）；⑤ v2.5.0 已 tag 但 Release 记录缺失（发布链路间隙，已补建）。
- **决策**：
  1. **压缩包双规则合并**（内置 21→15 条）：删除 6 条纯后缀 + 6 条纯特征码 + 旧 .ltx 扩展名规则（共 13 条），新增组合规则 `特征码 AND 后缀`：ZIP(hex:504B0304 AND .zip)、TAR(ustar AND .tar)、GZIP(hex:1F8B AND .gz)、TAR.GZ(hex:1F8B AND .tar.gz,.tgz 保留)、BZIP2(hex:425A68 AND .bz2,.tbz2)、XZ(hex:FD377A585A00 AND .xz,.txz)、ZSTD(hex:28B52FFD AND .zst)。迁移 `_merge_pairs` 按 name+type+pattern+ext_pattern 精确删除内置旧模板（用户自定义规则不受影响），新组合规则补充播种默认禁用。
  2. **.ltx 组合规则**：`Vivado ILA探针组合(特征码+后缀)` = JSON 根键 `{"ltx_root`（hex:7B226C74785F726F6F74，头部 4KB 内）AND .ltx。
  3. **特征码配置持久化**：删除 init_db 中"旧库已有规则强制重置 enabled=0"逻辑（升级后管理员配置被重置的根因）；内置模板默认禁用仅对首次播种/新规则补充播种生效，已存在规则尊重管理员配置。
  4. **免审批判定修复**：`check_auto_approval` 原只传文件名不传路径 → `file_header=None` → binary/组合规则永远不命中 → 免审批必然走人工审批（上传页显示 matched=True 而提交仍待审批即此因）。修复：files_info 携带 `path`，匹配时构造 Path 读取真实文件头；兼容旧格式无 path 回退。
  5. **TDD 教训（用例命名）**：`is_partner` 为子串匹配（`pname in name`），测试用例"自动加入合作方测试公司"包含已创建合作方"测试公司"子串 → 误判已配置跳过自动加入。改用例名为独立名称"新合作方自动加入测试"（业务逻辑不变；真实业务中子串误判可另行评审）。
- **与 ADR-028 不重叠**：028 管 Vivado 精简/审批审计/性能 UX；029 管压缩包组合规则统一、配置持久化、免审批路径修复。
- **已落点**：v2.6.0（Windows dev 全量 TDD 361/361 通过；10b1 改 15 条断言+组合负向×2，新增 10b2 免审批回归组：.gz 含 1F8B 提交自动通过、.bin 含 AA995566 提交自动通过——直击生产复现场景）。

### ADR-030：.ltx 格式化JSON修复 / 性能门禁入CI / 发布说明 / 审批人仅首次播种（v2.6.1，强制）
- **背景**：beta 验收与审计发现五类问题——① 生产启用 .ltx 规则+免审批后真实 Vivado 文件不匹配（chiptop.ltx 为格式化 JSON `{\n    "ltx_root":`，旧紧凑 hex 特征 `{"ltx_root` 不命中）；② 多用户并发性能未纳入 CI（每次 CI 需验证最低性能，防静默退化）；③ Release 发布说明仅一句"自动发布"，缺新功能/性能/bug 修复摘要；④ admin 默认审批人每次启动都被补种——管理员删除后重启/升级又被加回；⑤ 审计留痕与生产冒烟方式需澄清（见下）。
- **决策**：
  1. **.ltx 特征码改为文本模式**：`"ltx_root"`（带引号的 JSON 根键，UTF-8 子串匹配 4KB 头部）——兼容紧凑/格式化两种 JSON 排版；新增迁移精确更新 v2.6.0 内置模板（hex:7B226C74785F726F6F74 → `"ltx_root"`），用户自定义规则不受影响。新增 10b3 回归组：格式化 JSON（真实 Vivado 输出）提交免审批通过 + 紧凑 JSON 兼容 + 无 ltx_root 负向。
  2. **性能门禁入 CI（ci_test.sh [3.5/4]）**：每次 CI 容器跑 `perf_test.py` 100MB 大文件全链路（上传→摆渡→下载→MD5）+ 3 用户并发（PERF_CONCURRENCY=3），秒级断言（本地实测 100MB 全链路 1.05s、并发 0.54s）；最低性能要求防静默退化。
  3. **Release 发布说明自动生成**：package job 克隆深度 1→30，Release body 用 `git log --oneline -15 --no-merges` 生成近版变更摘要（conventional commits：feat/fix/docs/perf 一目了然），不再只写"自动发布"。
  4. **admin 默认审批人仅首次播种**：init_db 以 system_config 标记 `approvers_initialized` 控制——首次初始化（表空）播种 admin 为一级+二级审批人（开箱闭环），置位后【永不自动补回】；审批人完全人工配置；无一级/二级审批人时提交 API 已有明确失败提醒（"未配置一级审批人/二级审批人"）。新增源码金丝雀断言。
  5. **审计留痕口径**：每个环节有记录——TDD（docs/06-test-report.md + verify.sh 输出）、CI（Gitea Actions run 日志留痕）、Release（Gitea Releases 含 body 变更摘要）、CD（cd.yml run + cd-deploy.sh 日志）、生产验证（/api/health + smoke.sh 只读冒烟）。生产冒烟 = 只读白名单 11 项（健康/登录/外网隔离/审计可达），不写生产数据（ADR-017 fail-safe）；admin 密码已改时冒烟登录项为 warning 不阻断（CD 以服务健康 + 版本生效 + 加载目录校验为门禁），生产功能验收靠人工 beta 走查。
  6. **WSL 测试环境与 CI 容器关系**：已合一——CI 容器（securetrans-ci:3.12）即运行于 WSL（rocky10-st 独立 docker daemon），同一镜像/同一 Python 3.12/同一依赖/同一全量 TDD（ci_test.sh）；差异仅数据：WSL 本机为持久数据，CI 每次全新容器+新配置+新数据（干净回归，防版本干扰）。Windows dev 全量 TDD 为第一道门禁，CI 容器为发布门禁，生产只读冒烟为部署门禁。
- **与 ADR-029 不重叠**：029 管压缩包规则合并/配置持久化/免审批路径修复；030 管 .ltx 格式化 JSON 修复/性能门禁/发布说明/审批人播种规则/审计口径。
- **已落点**：v2.6.1（Windows dev 全量 TDD 366/366 通过；真实 chiptop.ltx 匹配验证通过；性能 100MB 全链路 1.05s + 3 并发 0.54s；10b3 新增 4 项 + ADR-030 金丝雀 1 项）。

### ADR-031：合作方全量编辑 / WSL测试环境退居二线 / 生产冒烟为业界标准（v2.6.2，强制）
- **背景**：beta 使用中发现三件事——① 合作方在提交时自动加入清单后，管理页仅能"禁用/删除"，无法编辑（名称/联系人/邮箱修正只能删除重建）；② 用户质疑"WSL 独立测试环境 + CI 容器测试环境"双环境冗余；③ 用户求证"生产只读冒烟"是否为业界最佳实践。
- **决策**：
  1. **合作方全量编辑**：新增 `PUT /api/admin/partners/<id>`（名称/联系人/邮箱；名称必填 + 去重检查排除自身 COLLATE NOCASE，与提交自动加入一致；404 不存在/400 空名/400 重名）；前端表格加"编辑"按钮 + 编辑弹窗（复用新增弹窗，预填当前值）；审计日志 update_partner；TDD 新增 6 项（编辑生效/空名拒绝/重名拒绝/404/清理）。
  2. **WSL 常驻测试环境退居二线**：职责已被覆盖——Windows dev 全量 TDD（第一道快速门禁，秒级）+ CI 容器全量 TDD（发布门禁，Linux 环境，每次全新数据）。WSL 不再单独跑 verify.sh / 不再做"三环境 git 副本 push 同步"（ADR-026 修订：以 git 为中心不变，但测试执行收敛到 dev + CI 两环境）；WSL 保留为 CI 容器宿主（rocky10-st docker daemon）与 Linux 问题排查入口（按需 `docker run securetrans-ci:3.12` 复现）。
  3. **生产只读冒烟 = 业界标准**：生产环境自动化验证遵循"健康检查 + 只读冒烟 + 版本/目录校验"（SRE/DevOps 标准：smoke test in prod 必须 read-only，写测试数据只允许在测试环境；蓝绿/金丝雀部署的 validation hook 同此原则）。本系统单实例无灰度，CD 以 healthz + 包内版本=部署版本 + 加载目录校验为门禁，smoke.sh 只读 11 项；功能验收靠人工 beta 走查（符合 12-Factor / ADR-017 fail-safe）。
- **与 ADR-030 不重叠**：030 管 .ltx/性能门禁/发布说明/审批人播种；031 管合作方编辑功能、测试环境收敛、生产冒烟原则确认。
- **已落点**：v2.6.2（Windows dev 全量 TDD 372/372 通过；合作方编辑 6 项新增用例；CI 容器全量 + 性能门禁；生产 CD 部署后 `/api/health` = v2.6.2/beta/ok/production）。

---

## 许可证

[MIT License](LICENSE) — 可自由使用、修改、分发，保留版权声明即可。

---

---

*SecureTrans v2.6.2 | 2026-09-14*
