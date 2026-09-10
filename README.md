# SecureTrans — 轻量级跨网文件审批摆渡系统

> 版本：v2.2.29 | 阶段：PSF（问题-方案匹配验证）— Alpha 内测中
> 技术栈：Flask 3.0 + Flask-Login + SQLite + os.rename 0拷贝摆渡
> 开发模式：主干开发（Trunk-Based Development）+ 单分支 main
> 部署：Rocky Linux 8.10 单网卡（10.10.30.8），gunicorn + systemd，Python 3.12 venv

---

## 项目简介

SecureTrans 是面向中小企业的轻量级单向跨网文件审批摆渡系统，解决内网红区/黄区到外网绿区的文件安全外发问题。

**核心价值**：审批可控、摆渡0拷贝、归档可审计。

**核心设计**：
- **os.rename 0拷贝摆渡**：同文件系统内只改目录项，不移动数据块，毫秒级完成
- **免审批机制**：特征码匹配的文件自动通过（支持压缩包/Vivado Bitstream 等规则，可手工配置）
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
cp .env.testing .env          # 测试环境配置（默认 DEPLOY_MODE=testing）
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
# 预期：266项测试全部通过，通过率100%（Windows dev）；WSL 测试环境 265 项（production 模式环境自适应差异 1 项）
```

### 一键部署（服务器，Rocky Linux）

```bash
# 1. 上传发布包 securetrans-<版本>.tar.gz 到服务器
tar xzf securetrans-v2.2.14.tar.gz -C /opt/securetrans --strip-components=1
cd /opt/securetrans

# 2. 一键部署（9步自动化：Python 3.12 获取 → venv → 依赖 → .env → systemd → 启动验证）
sudo bash infra/deploy.sh

# 3. 部署验证（266项全量测试；admin 凭据自动取 .env RESET_PASSWORD；BASE_URL 自动适配 .env HOST/PORT；若 admin 密码已手工修改，用 VERIFY_ADMIN_PASS 显式传入）
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
├── AGENTS.md                 # AI协作指南（AI 默认扫根目录）
├── .gitignore                # Git忽略规则
├── LICENSE                   # MIT许可证
├── src/                      # 源代码（按功能模块组织）
│   ├── app.py                # Flask主程序（单文件，含所有API，模块级初始化）
│   ├── requirements.txt      # Python依赖
│   ├── start.sh              # 测试环境启动脚本（Flask自带服务器）
│   ├── start-production.sh   # 生产环境启动脚本（gunicorn）
│   ├── start.bat             # Windows启动脚本
│   ├── .env.example          # 环境变量通用示例
│   ├── .env.testing          # 测试环境配置模板
│   ├── .env.production       # 生产环境配置模板（唯一生产配置源）
│   └── static/               # 前端静态文件（SPA + 登录页）
├── tests/                    # 自动化测试
│   └── test_api.py           # 全量API测试脚本（266项，标准库urllib无额外依赖；凭据参数化 TEST_ADMIN_USER/TEST_ADMIN_PASS）
├── docs/                     # 统一文档（数字前缀排序，持续刷新）
│   ├── 00-lean-startup-phase-map.md   # Lean Startup三阶段映射与决策门
│   ├── 01-scrum-io-definition.md      # Scrum各阶段输入输出定义
│   ├── 02-prd.md                     # 产品需求文档（内部版本v2.2，文件名不带版本号）
│   ├── 03-psf-process.md              # PSF阶段标准流程
│   ├── 04-pmf-process.md              # PMF阶段标准流程（下一阶段准备）
│   ├── 05-test-cases.md               # 测试用例
│   ├── 06-test-report.md              # 测试报告（266项全通过）
│   ├── 07-psf-sprint4-retrospective.md # PSF阶段迭代小结
│   ├── 08-cicd-gitops-architecture.md # CICD/GitOps架构规划
│   ├── 09-preprod-verification.md     # 生产预验收清单
│   ├── 10-prod-sim-verification.md    # 生产模拟验证（+ 测试报告txt）
│   ├── 11-architecture-evolution.md   # 架构演进（Flask→FastAPI→Nginx 等决策）
│   └── DEPLOY.md                      # 部署指南（唯一，含测试/生产/双OS/网络隔离/防火墙）
└── infra/                    # 基础设施配置
    ├── deploy.sh             # 一键部署脚本（9步自动化, Linux）
    ├── deploy.ps1            # 一键部署脚本（Windows）
    ├── verify.sh             # 部署验证脚本（266项，BASE_URL 自适应 + 凭据自动取 .env RESET_PASSWORD）
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
**PSF（问题-方案匹配验证）— Alpha 内测进行中**：服务器（Rocky 8.10 单网卡 10.10.30.8）部署完成，deploy.sh/verify.sh 全部通过，266项自动化测试 100%（WSL production 265 项）+ 800MB 性能压力测试通过（MD5 端到端一致），内部人工测试启动中（内网全功能 + 办公外网下载）。

详见：
- [Lean Startup阶段映射](docs/00-lean-startup-phase-map.md)
- [Scrum各阶段输入输出定义](docs/01-scrum-io-definition.md)
- [产品需求文档 PRD v2.2](docs/02-prd.md)
- [PSF阶段标准流程](docs/03-psf-process.md)
- [测试用例](docs/05-test-cases.md)
- [测试报告（266项全通过）](docs/06-test-report.md)
- [PSF阶段迭代小结](docs/07-psf-sprint4-retrospective.md)
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
  - **调测门禁**：本地调测中间阶段保持双环境 TDD 全量回归——Windows 开发环境（testing：`python test_api.py` 233项）
    + WSL 测试环境（production：`infra/verify.sh` 232项），**全部通过才允许 bump + 发布**
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
- **已落点**：v2.2.20（app.py：ad_config 表/AD_ENV_MAP/get_ad_config_value/mask_secret/authenticate_ad·api_login·api_search_ad 运行时读取/api_update_system_config 去回写 + 3 个管理 API：GET·PUT /api/admin/ad-config、POST /api/admin/ad-config/import、GET /api/admin/config-overview + 前端 AD 配置卡片与配置总览卡片 + test_api.py 201 项全量回归）

### ADR-011：数据生命周期与运维功能化（强制）
- **背景**：测试环境部署时需要清空老库/恢复初始配置，生产环境原则上不能动数据但需要按需备份+清理、备份、恢复；开发/测试/生产环境代码配置数据不分离导致验证不可靠。业界最佳实践：运维期内有用的功能应收尽收进系统（Web API + 界面 + TDD 可调），脚本只保留首部署与离线场景。
- **决策（三环境一套代码配置数据脚本）**：dev(Windows) / test(WSL) / prod(Rocky) 程序与配置完全一致（DEPLOY_MODE 开关 + .env）；差异只在数据策略——dev/test 用**模拟数据 + verify.sh 全量验证**闭环，prod 用**备份/恢复/出厂重置**；代码、配置、数据三者分离可自由组合。
- **系统功能（admin 菜单"系统工具"，确认码保护）**：备份 `POST /api/admin/ops/backup` + 列表 `GET /api/admin/ops/backups`（**scope 拆分**：`system`=仅系统 DB（升级前后回退用）/ `business`=仅 NAS 业务文件（换存储/归档用）/ `all`=两者，界面系统/业务两个备份卡 + 列表 hasDb/hasNas 标记；DB 用 sqlite backup API 一致性快照 + NAS 业务目录 → data/backups/backup-<ts>）；恢复 `POST /api/admin/ops/restore`（确认码 RESTORE，支持 scope，回退=再恢复之前的备份）；出厂重置 `POST /api/admin/ops/reset-factory`（确认码 RESET，**自动先备份** → 清空 → init_db 重建 → admin 密码重置为 .env RESET_PASSWORD）；模拟数据 `POST /api/admin/ops/mock-data`（确认码 MOCK，**仅 testing 模式**，生产 403）。
- **离线脚本（infra/，服务停止时最安全）**：`ops-backup.sh [all|system|business]` / `ops-restore.sh <name> [all|system|business]` / `ops-reset.sh`（备份+清理，调 CLI `--reset-factory`）/ `ops-mock.sh`（调 CLI `--mock-data`）；deploy.sh 支持 `RESET_DB=1` 部署时出厂重置（测试环境用）。
- **与 ADR-010 不重叠**：ADR-010 管配置权威（静态三档），ADR-011 管数据生命周期与运维操作（动态）；mock+verify 构成 ADR-007 调测门禁的执行闭环。
- **已落点**：v2.2.27（app.py ops 路由 scope 拆分 + 前端系统/业务备份卡 + ops-*.sh scope 参数 + test_api.py 250 项 + deploy.sh 9.8 RESET_DB；v2.2.23 初版：ops 路由 + CLI --reset-factory/--mock-data + 前端系统工具页 + test_api.py 221 项 + infra/ops-*.sh）
- **v2.2.29 强化（备份命名区分，普通人可识别）**：备份目录名改为 `backup-system-<ts>` / `backup-business-<ts>` / `backup-all-<ts>`（名字即类型）；列表带 `type` 字段；系统工具页**两个独立备份列表**（系统备份列表 / 业务数据备份列表），恢复按钮不再选 scope——**后端按备份名自动推导类型**，杜绝"从同一个备份混恢复"；旧版 `backup-<ts>` 兼容识别为 all

### ADR-012：性能与文件完整性——800MB 全链路压力测试 + MD5 端到端四方一致（强制）
- **背景**：生产部署前需要正式的性能与完整性验证——800MB 大文件 上传→审批摆渡→下载 全链路性能；文件完整性（MD5）端到端保证，防止传输/摆渡过程损坏。
- **决策**：
  - **MD5 四方一致（强制）**：上传流式计算 MD5 存入 submission_files → 下载时从 DB 取 MD5 写入 download_records.md5 并回传响应头 `X-File-MD5` → 下载内容本地再算 MD5 比对（上传值 = DB 值 = 响应头 = 下载内容）；审计日志 download 记录带 MD5；前端上传列表/详情显示完整 MD5
  - **性能压力测试工具 tests/perf_test.py（系统级能力，TDD 可调）**：流式生成大文件（边写边算 MD5）→ 流式 multipart 上传 → 合作方提交单一级审批（计时含 os.rename 摆渡）→ 流式下载 → MD5 四方比对 → JSON 报告 + 阈值断言 + 自动清理；`PERF_SIZE_MB`（默认 800）/`PERF_ADMIN_*`/`PERF_MAX_*_S` 环境变量，退出码 0/2
  - **上传上限统一口径**：`.env MAX_FILE_SIZE_MB`（单文件上限，默认 800）唯一配置；`MAX_CONTENT_LENGTH` 自动 = 文件上限 + 1MB（multipart 封装余量），禁止手工配置——否则 800MB 文件 + boundary 封装会 413（v2.2.24 实测命中并修复）
  - **删除提交单（运维功能，admin + 确认码 DEL）**：清 DB 三关联表 + STAGING/EXTERNAL/ARCHIVE 三目录，防误触；对 admin 前端可见
- **与 ADR-011 不重叠**：ADR-011 管数据生命周期（备份/恢复/重置），ADR-012 管性能验证与文件完整性（删除提交单是其中运维项，确认码机制一致）
- **已落点**：v2.2.24（app.py：download_records.md5 迁移/下载 X-File-MD5/删除提交单 API/MAX_FILE_SIZE_MB；前端完整 MD5 + 删除按钮；tests/perf_test.py；test_api.py 233 项；800MB 实测：上传 338 MB/s / 摆渡 34ms / 下载 350 MB/s / 全链路 5.94s / MD5 四方一致）

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
- **已落点**：v2.2.29（app.py：_ad_err/_ad_connection/_ad_fields/_ad_search_users + api_search_ad 真实查询/精确匹配/error 字段 + POST /api/admin/ad/test；前端：AD 配置卡片测试连接按钮 + 搜索错误显示 + copyAdCmd 修复；deploy.sh openldap-clients 自动安装；test_api.py 266 项）

---

## 许可证

[MIT License](LICENSE) — 可自由使用、修改、分发，保留版权声明即可。

---

*SecureTrans v2.2.29 | 2026-09-10*

