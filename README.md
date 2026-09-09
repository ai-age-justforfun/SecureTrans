# SecureTrans — 轻量级跨网文件审批摆渡系统

> 版本：v2.2.14 | 阶段：PSF（问题-方案匹配验证）— Alpha 内测中
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

访问 http://localhost:8000，初始账号 `admin / Admin@123`（Windows dev 场景；生产部署后 admin 密码每次自动重置为 .env `RESET_PASSWORD`，默认 Init@123456，首次登录强制改密）。

### 运行测试

```bash
# 先启动服务（在 src/ 目录下）
cd src && python app.py

# 另一个终端运行测试
cd tests
python test_api.py
# 预期：193项测试全部通过，通过率100%
```

### 一键部署（服务器，Rocky Linux）

```bash
# 1. 上传发布包 securetrans-<版本>.tar.gz 到服务器
tar xzf securetrans-v2.2.14.tar.gz -C /opt/securetrans --strip-components=1
cd /opt/securetrans

# 2. 一键部署（9步自动化：Python 3.12 获取 → venv → 依赖 → .env → systemd → 启动验证）
sudo bash infra/deploy.sh

# 3. 部署验证（193项全量测试；admin 凭据自动取 .env RESET_PASSWORD；BASE_URL 自动适配 .env HOST/PORT；若 admin 密码已手工修改，用 VERIFY_ADMIN_PASS 显式传入）
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
│   └── test_api.py           # 全量API测试脚本（193项，标准库urllib无额外依赖；凭据参数化 TEST_ADMIN_USER/TEST_ADMIN_PASS）
├── docs/                     # 统一文档（数字前缀排序，持续刷新）
│   ├── 00-lean-startup-phase-map.md   # Lean Startup三阶段映射与决策门
│   ├── 01-scrum-io-definition.md      # Scrum各阶段输入输出定义
│   ├── 02-prd.md                     # 产品需求文档（内部版本v2.2，文件名不带版本号）
│   ├── 03-psf-process.md              # PSF阶段标准流程
│   ├── 04-pmf-process.md              # PMF阶段标准流程（下一阶段准备）
│   ├── 05-test-cases.md               # 测试用例
│   ├── 06-test-report.md              # 测试报告（193项全通过）
│   ├── 07-psf-sprint4-retrospective.md # PSF阶段迭代小结
│   ├── 08-cicd-gitops-architecture.md # CICD/GitOps架构规划
│   ├── 09-preprod-verification.md     # 生产预验收清单
│   ├── 10-prod-sim-verification.md    # 生产模拟验证（+ 测试报告txt）
│   ├── 11-architecture-evolution.md   # 架构演进（Flask→FastAPI→Nginx 等决策）
│   └── DEPLOY.md                      # 部署指南（唯一，含测试/生产/双OS/网络隔离/防火墙）
└── infra/                    # 基础设施配置
    ├── deploy.sh             # 一键部署脚本（9步自动化, Linux）
    ├── deploy.ps1            # 一键部署脚本（Windows）
    ├── verify.sh             # 部署验证脚本（193项，BASE_URL 自适应 + 凭据自动取 .env RESET_PASSWORD）
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
| GET | /api/health | 健康检查（含 deployMode 字段） |

---

## 发布与版本

- **版本号单一来源**：`src/app.py` 的 `APP_VERSION`（前端 index.html 同步），文档内版本号统一
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
**PSF（问题-方案匹配验证）— Alpha 内测进行中**：服务器（Rocky 8.10 单网卡 10.10.30.8）部署完成，deploy.sh/verify.sh 全部通过，193项自动化测试 100%，内部人工测试启动中（内网全功能 + 办公外网下载）。

详见：
- [Lean Startup阶段映射](docs/00-lean-startup-phase-map.md)
- [Scrum各阶段输入输出定义](docs/01-scrum-io-definition.md)
- [产品需求文档 PRD v2.2](docs/02-prd.md)
- [PSF阶段标准流程](docs/03-psf-process.md)
- [测试用例](docs/05-test-cases.md)
- [测试报告（193项全通过）](docs/06-test-report.md)
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
  - **调测门禁**：本地调测中间阶段保持双环境 TDD 全量回归——Windows 开发环境（testing：`python test_api.py` 193项）
    + WSL 测试环境（production：`infra/verify.sh` 193项），**全部通过才允许 bump + 发布**
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

### ADR-009：部署凭据策略——每次部署重置 admin 密码为 .env RESET_PASSWORD
- **背景**：verify.sh 原用写死的 admin/Admin@123 登录验证；生产环境 admin 密码被手工修改后验证直接 401 失败。
  且用户重置密码（Init@123456）固定不可配、界面显示与 .env 可能不一致。
- **决策**：
  - **单一来源**：`.env RESET_PASSWORD` 是重置密码唯一配置源（默认 Init@123456），界面"重置密码"显示、部署重置、verify 凭据三者同源，禁止其他位置出现第二份默认密码
  - **每次部署重置**：deploy.sh 9.7 步调用 `python app.py --reset-admin-password`，将 admin 密码重置为 .env RESET_PASSWORD 并置强制改密标记（幂等；保证部署完成即可登录、verify 直接通过）；`--reset-admin-password` 为独立 CLI，不启动 Web 服务
  - **verify 凭据自适应**：verify.sh 自动从 .env RESET_PASSWORD 取凭据（`VERIFY_ADMIN_USER`/`VERIFY_ADMIN_PASS` 环境变量可显式覆盖）；admin 密码被手工修改后，验证时显式传 `VERIFY_ADMIN_PASS=xxx`
  - **测试不碰真实密码**：test_api.py 凭据参数化（TEST_ADMIN_USER/TEST_ADMIN_PASS）；改密测试用专用用户 testpwuser（创建→改密→新密码登录→改回→清理），绝不修改真实 admin 密码（生产安全）
  - **deploy.sh 兜底**：.env 缺失 RESET_PASSWORD 行时自动追加默认值，避免 verify 凭据与部署重置不一致（此坑已在 WSL 环境实测命中）
- **已落点**：v2.2.18（app.py CLI / deploy.sh 9.7+4.6 / verify.sh 凭据读取 / test_api.py 参数化+专用用户）
- **边界**：Windows dev 场景 admin 初始仍为 Admin@123（init_db 首次创建），不随部署重置；生产环境以 RESET_PASSWORD 为准

---

## 许可证

[MIT License](LICENSE) — 可自由使用、修改、分发，保留版权声明即可。

---

*SecureTrans v2.2.14 | 2026-09-08*

