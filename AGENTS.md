# SecureTrans 项目 AI 协作指南

> 本文件指导 AI Agent 在本项目中的协作行为，确保代码和文档的一致性。

---

## 项目概况

- **项目名**：SecureTrans — 轻量级跨网文件审批摆渡系统
- **当前阶段**：PSF（问题-方案匹配验证）— Alpha 内测进行中
- **当前版本**：v2.2.23（版本号单一来源：`src/app.py` 的 `APP_VERSION`，前端 index.html 同步）
- **技术栈**：Flask 3.0 + Flask-Login + SQLite + os.rename 0拷贝
- **代码架构**：后端单文件（`src/app.py`），前端单页应用（`src/static/index.html`）
- **开发模式**：主干开发（Trunk-Based Development），单分支 main
- **部署目标**：封闭数据中心，Rocky Linux 8.10 单网卡（10.10.30.8），gunicorn + systemd，Python 3.12 venv

---

## 代码规范

### 后端（Python / Flask）

- **单文件架构**：所有后端逻辑在 `src/app.py` 中，不拆分模块（PSF阶段保持简单）
- **配置**：所有可配置项通过环境变量读取，默认值在代码中定义，`.env` 文件覆盖
- **部署模式**：`DEPLOY_MODE=testing`（本地文件系统+Flask）/ `production`（NAS+gunicorn+systemd），一个开关切换
- **数据库**：SQLite，使用 `sqlite3` 标准库，不使用 ORM（保持轻量）
- **认证**：Flask-Login，本地用户 + AD用户（LDAP直连，UPN 绑定与 sssd 兼容）统一会话管理；
  AD 属性字段可配置（AD_USER_FIELD/AD_DISPLAY_FIELD/AD_MAIL_FIELD/AD_GROUP_FIELD，默认 AD 标准属性，非硬编码）；
  AD 登录失败原因写入审计日志 detail（未启用/密码错误/连接异常/ldap3未装）；
  **AD 连接配置运行期以 SQLite ad_config 为权威（ADR-010）**：首次从 .env 播种/导入，管理页"系统配置→AD 配置"可查看、导入、保存（source=env/db，空值回退 .env/默认），保存即时生效无需重启
- **文件操作**：必须使用 `os.rename` 实现0拷贝摆渡，禁止使用 `shutil.move`（会退化为复制）
- **大文件上传**：流式读取（`file.stream.read(65536)`），边读边算MD5，不加载整个文件到内存
- **日志**：使用 `logging` 模块，同时输出到文件和控制台
- **错误处理**：API 返回 JSON `{"error": "描述"}` + 合适的HTTP状态码
- **模块级初始化**：`init_db()` 和 `start_scheduler()` 必须在模块级别调用，不能只在 `if __name__ == "__main__"` 中（gunicorn导入时不执行该块）

### 前端（HTML / JS / CSS）

- **单页应用**：所有前端逻辑在 `src/static/index.html` 中，内联CSS和JS，不使用构建工具
- **API调用**：使用 `fetch()`，`credentials: 'same-origin'`，JSON格式请求体
- **样式**：简洁商务风格，蓝色主色调（#2563eb / #1e3a5f），不使用框架
- **角色权限**：前端根据 `currentUser.role` 显示/隐藏菜单，但后端必须做权限校验（前端只做体验优化）；权限模型简化——仅 admin 可管理配置，其他用户默认普通用户，审批权限通过 approvers 表配置
- **i18n 双语**：全部界面中英双语（`I18N` 字典 zh/en + `t()` 取文案 + `data-i18n` 属性 + `applyI18n()` 统一渲染），右上角语言切换（localStorage 记忆，默认中文）；后端经 `after_request` 自动附加 `error_en`/`message_en`
- **时间显示**：统一为服务器操作系统时区时间，不做时区转换（侧边栏已标注"时间=服务器系统时区"）；英文文案注意单复数；业务数据（文件名/姓名）不翻译

### Git 提交规范

**主干开发，原子化提交**：

```
<type>(<scope>): <简短描述>
[可选] 详细说明
[可选] Story关联: #story-xxx
```

- **type**：feat / fix / docs / refactor / test / chore
- **scope**：auth / submission / approval / admin / deploy / doc / frontend / infra
- **不强制带 Sprint 编号**：Sprint是管理节奏，不是代码的身份证
- **可关联 Story 编号**：当需要追踪需求来源时
- **原子化**：每个独立功能点一次commit，便于回退和追溯

---

## 文档规范

### 文档清单与位置

| 文档 | 位置 | 更新时机 |
|------|------|---------|
| PRD | `docs/02-prd.md`（内部版本 v2.2，文件名不带版本号） | 需求变更时 |
| PSF流程 | `docs/03-psf-process.md` | 流程调整时 |
| PMF流程 | `docs/04-pmf-process.md` | 流程调整时 |
| 测试用例 | `docs/05-test-cases.md` | 新增功能时 |
| 测试报告 | `docs/06-test-report.md` | 每次全量测试后 |
| 迭代小结 | `docs/07-psf-sprint4-retrospective.md` | 每个Sprint结束 |
| 生产预验收 | `docs/09-preprod-verification.md` | 预验收前 |
| 生产模拟验证 | `docs/10-prod-sim-verification.md` | 生产模拟后 |
| 架构演进 | `docs/11-architecture-evolution.md` | 技术路线决策时 |
| 部署指南（测试/生产/双OS/网络隔离/防火墙，唯一） | `docs/DEPLOY.md` | 部署流程变更时 |
| README | `README.md`（人 + AI 同步查阅） | 项目概况变更时 |
| AI协作指南 | `AGENTS.md`（AI 默认扫根目录） | 规范变更时 |

### 文档原则

- **聚焦关键内容**：不追求大公司级完美，重点记录决策、结论、行动项
- **可追溯**：每个技术决策有ADR记录（README 汇总 + PRD 章节），每个Sprint有复盘文档
- **版本化**：重要文档带版本号和日期，旧版本保留（不覆盖）
- **文件名不含版本号**：版本号写在文档内部（各领域文档内部版本号统一），文件名固定（如 `02-prd.md`）；关键需求变更用 Git tag 记录，最终以发布版本（git tag vX.Y）为准
- **中文为主**：项目文档使用中文，代码注释中英文均可
- **Sprint作为研发分解阶段**：在过程文档中体现，不用目录结构做版本管理

---

## 技术决策记录（ADR）

| ADR | 决策 | 位置 |
|-----|------|------|
| ADR-001 | os.rename 而非软链接/拷贝（0拷贝摆渡） | README / PRD v2.2 |
| ADR-002 | Flask 而非 FastAPI（生态成熟、团队成本低） | README / PRD v2.2 |
| ADR-003 | 主干开发 + 单分支（Sprint 只在文档体现） | README |
| ADR-004 | Python 3.12 + venv 隔离（离线 wheel cp312 匹配） | README |
| ADR-005 | 非硬编码原则：环境变量驱动（配置/部署/运行），含 systemd 变量展开生效机制（原 ADR-005/006 合并） | README + 本文件部署规范 |
| ADR-006 | 网络面安全假设（封闭数据中心：IPsec+防火墙内部，系统防火墙可不启用，应用层流程管控隔离） | README + 本文件网络面语义 |
| ADR-007 | 发布策略与调测门禁（调测期密集发布 / RTM 后手工发布 / 文档-only 不发布 / 双环境 TDD 全量回归门禁） | README + 本文件发布流程 |
| ADR-008 | 端口/网络面部署选型（单/双网卡 × 单/双端口三方案对比；当前封闭内网保持方案1 单网卡单端口，PMF 按需升级方案2 双端口，互联网暴露才用方案3 双网卡） | README + 本文件网络面语义 |
| ADR-009 | 部署凭据策略：每次部署重置 admin 密码为 .env RESET_PASSWORD（单一来源/verify 凭据自适应/测试不碰真实密码） | README + 本文件部署规范 |
| ADR-010 | .env 与 SQLite 配置一致性：配置权威矩阵（部署级 .env 唯一 / 运行时 SQLite 唯一不再回写 / AD 配置迁 SQLite+管理页+配置总览，播种一次、DB 优先、来源标记防遗忘） | README + 本文件部署规范 + DEPLOY.md |
| ADR-011 | 数据生命周期与运维功能化：备份/恢复/出厂重置/模拟数据进系统（菜单"系统工具" + API + TDD 可调）；三环境一套代码配置数据脚本（dev/test 模拟数据+verify 闭环，prod 备份/恢复/重置）；脚本仅保留首部署与离线场景（ops-backup/restore/reset/mock）；部署级 .env RESET_DB=1 可触发出厂重置 | README + 本文件部署规范 + DEPLOY.md |

### ADR-005 详述：非硬编码原则（强制）

prototype/MVP 阶段代码内默认值可快速验证；但本地(Windows) → 测试(WSL) → 生产(Rocky) 环境差异大，
配置越来越复杂、环境越来越灵活，**新增代码/脚本一律不得写死地址、端口、网段、路径**：

- 环境相关配置从 `.env` 环境变量读取，代码/脚本只保留合理默认值（HOST=0.0.0.0、PORT=8000）作 fallback，生产必须显式配置
- 动态采集：deploy.sh 健康检查/防火墙端口、verify.sh BASE_URL 运行期从 .env grep，不静态编码
- 动态部署：deploy.sh 探测环境自适应（Python 三级获取、ReadWritePaths 按 NAS 存在性渲染、防火墙按 firewalld 状态）
- 动态运行：systemd EnvironmentFile + `${HOST}:${PORT}` 变量展开，改 .env + `systemctl restart` 即生效（原 ADR-005 并入）
- 前端 API 相对路径（同源），不写死服务器地址
- 已落点：v2.2.14（app.py / securetrans.service / deploy.sh / verify.sh / start-production.sh / release.ps1）

### ADR-006 详述：网络面安全假设（强制边界）

服务器位于数据中心防火墙内部，办公网 ↔ 数据中心经 IPsec 加密隧道互联；内/外网均为公司内部网络分区，
无 NAT、不向互联网开放、无攻击威胁。**决策：假设网络层安全由公司基础设施承担，系统防火墙（firewalld）可不启用**；
应用层保留流程管控级隔离（外网面仅登录+下载、管理接口 403）+ 认证/审批权限/审计/文件限制底线。
**边界**：仅适用于封闭数据中心场景；若部署到互联网可达环境，必须启用 Nginx + HTTPS + firewalld（DEPLOY.md）。

### ADR-007 详述：发布策略与调测门禁（强制）

- 发布 = 正式版本（Gitea Release + git tag + 包资产），代表可部署产物
- **调测期（PSF Alpha/Beta）**：代码/脚本/配置模板每次变更即发布（密集发布，便于服务器验证）
- **RTM 后**：默认不逐次发布，关键里程碑手工发布
- **文档-only 变更**：commit + push main，不 bump、不打包、不建 Release（随仓库演进，代码发布时包内自动带入最新）
- **调测门禁（双环境 TDD 全量回归）**：本地调测中间阶段——Windows 开发环境（testing：`python test_api.py` 221项）
  + WSL 测试环境（production：`infra/verify.sh` 221项），**全部通过才允许 bump + 发布**
- 版本号是发布产物属性，APP_VERSION 只在代码发布时递增


### ADR-008 详述：端口/网络面部署选型（强制边界）
- 三方案：①单网卡单端口（当前，源IP+INTERNAL_CIDRS 应用层分面，外网面仅登录+下载、管理接口 403）；②单网卡双端口（SDT式：up 内网提交/审批 + down 外网下载，防火墙层隔离提交面，代码零改动——X-Network-Zone 头现成）；③双网卡双端口（物理隔离，仅互联网暴露场景需要）
- 决策：**PSF Alpha 保持方案1**（人员少、封闭数据中心、ADR-006 假设成立）；PMF 按需升方案2；互联网暴露才用方案3
- 方案2 增益/成本比最高（一个迭代），方案3 在封闭内网边际增益趋近零
- 所有方案 HTTP 明文同风险，内网 Alpha 可暂缓 HTTPS；外网面暴露时必须 Nginx + HTTPS + firewalld

### ADR-009 详述：部署凭据策略——每次部署重置 admin 密码（强制）
- **单一来源**：`.env RESET_PASSWORD` 是重置密码唯一配置源（默认 Init@123456）；界面"重置密码"、部署重置、verify 凭据三者同源，代码/文档禁止出现第二份默认密码
- **每次部署重置**：deploy.sh 9.7 步调用 `python app.py --reset-admin-password` 重置 admin 密码为 .env RESET_PASSWORD 并置强制改密标记；deploy.sh 4.6 步确保 .env 含 RESET_PASSWORD 行（缺失自动追加）
- **verify 凭据自适应**：verify.sh 从 .env RESET_PASSWORD 取凭据；`VERIFY_ADMIN_USER`/`VERIFY_ADMIN_PASS` 环境变量可显式覆盖（admin 密码手工修改后：`VERIFY_ADMIN_PASS=xxx bash infra/verify.sh`）
- **测试安全**：test_api.py 凭据参数化 TEST_ADMIN_USER/TEST_ADMIN_PASS；改密测试用专用用户 testpwuser，不碰真实 admin 密码
- **已落点**：v2.2.18（app.py / deploy.sh / verify.sh / test_api.py）

### ADR-010 详述：.env 与 SQLite 配置一致性——配置权威矩阵（强制）
- **三档配置，各档唯一权威，禁止双重配置**：
  - **部署级配置（.env 唯一，进程启动读取，改后 restart 生效）**：DEPLOY_MODE / HOST / PORT / INTERNAL_CIDRS / NAS_ROOT / SECURETRANS_DATA / SECRET_KEY / RESET_PASSWORD；由 systemd EnvironmentFile 机制加载，界面只读展示
  - **运行时配置（SQLite 唯一，界面可改、即时生效，不再回写 .env）**：system_config（app_name / auto_approval_enabled / default_expiry_days / max_file_size_mb）；api_update_system_config 已删除 .env 回写，防两处漂移
  - **AD 连接配置（SQLite ad_config 权威，管理页可配）**：10 键 ad_enabled/ad_host/ad_domain/ad_base_dn/ad_bind_dn/ad_bind_password/ad_user_field/ad_display_field/ad_mail_field/ad_group_field；首次部署表空从 .env 播种（source=env）→ 管理页可"从 .env 导入"/保存（source=db，即时生效）→ 空值回退 .env/默认；authenticate_ad / api_login 域判断 / api_search_ad 全部运行时读取
- **一致性机制**：①播种一次（空表从 .env 导入）；②**配置总览页**（系统配置页卡片：.env 部署级只读 + DB 运行时配置，逐项标来源 env/db 与更新时间）；③**冲突规则 DB 优先**（界面保存即权威，.env 不回写）；④文档化（README/AGENTS/DEPLOY 三处同步）
- **边界**：部署级配置不迁 DB；AD_BIND_PASSWORD 脱敏显示（前2位+****），重新输入才覆盖；.env 仅部署级参数与首次播种
- **已落点**：v2.2.20（app.py ad_config 表/AD_ENV_MAP/get_ad_config_value/mask_secret/运行时读取改造 + GET·PUT /api/admin/ad-config + POST /api/admin/ad-config/import + GET /api/admin/config-overview + 前端 AD 配置/配置总览卡片 + test_api.py 201 项）

### ADR-011 详述：数据生命周期与运维功能化（强制）
- **三环境一套代码/配置/数据脚本**：dev(Windows) / test(WSL) / prod(Rocky) 程序配置完全一样（DEPLOY_MODE 开关 + .env）；差异只在数据策略——dev/test 用**模拟数据生成 + verify.sh 全量验证**闭环，prod 用**备份/恢复/出厂重置**；代码、配置、数据三者分离，可自由组合
- **运维功能进系统（应收尽收）**：只有"整个系统外"的功能（首部署、离线场景）用脚本；运维期内有用的功能全部进系统——admin 菜单 **系统工具** 页 + API，TDD 可直接调用、管理员可网页手工调用
  - **备份**：`POST /api/admin/ops/backup` / 列表 `GET /api/admin/ops/backups`（DB sqlite backup API 一致性快照 + NAS 业务目录 → data/backups/backup-<ts>）
  - **恢复**：`POST /api/admin/ops/restore`（需确认码 RESTORE；替换 DB + NAS，回退=再恢复之前的备份；建议低峰/停服执行）
  - **出厂重置**：`POST /api/admin/ops/reset-factory`（需确认码 RESET；**自动先备份** → 清空业务库与 NAS → init_db 重建 → admin 密码重置为 .env RESET_PASSWORD，与 ADR-009 同源）
  - **模拟数据**：`POST /api/admin/ops/mock-data`（需确认码 MOCK；生成测试用户/审批人/合作方/各状态提交单；**仅 DEPLOY_MODE=testing 允许**，生产/预生产 403）
- **脚本（infra/，离线文件级，服务停止时最安全）**：`ops-backup.sh`（备份）/ `ops-restore.sh <name>`（恢复）/ `ops-reset.sh`（备份+清理，调 CLI `--reset-factory`）/ `ops-mock.sh`（模拟数据，调 CLI `--mock-data`，testing 才执行）；deploy.sh 支持 `RESET_DB=1 bash deploy.sh` 部署时出厂重置（测试环境用）
- **恢复/重置注意**：恢复/重置后审计日志回到备份/出厂时点；恢复应在同一部署路径（提交单 current_path 为绝对路径）
- **与 ADR-010 关系**：不重叠——ADR-010 管配置权威（静态三档），ADR-011 管数据生命周期与运维操作（动态）；mock+verify 构成 ADR-007 调测门禁的执行闭环
- **已落点**：v2.2.23（app.py ops 路由 + CLI --reset-factory/--mock-data + 前端系统工具页 + test_api.py 221 项 + infra/ops-*.sh + deploy.sh 9.8 RESET_DB）
## 研发流程

### 阶段划分（Lean Startup）

1. **PSF**（当前）：问题-方案匹配验证，1周Sprint，聚焦技术验证和用户反馈
2. **PMF**（下一阶段）：产品-市场匹配验证，2周Sprint，聚焦真实部署和使用数据
3. **Scale**（未来）：规模化，持续交付

### Git 工作流（主干开发）

```
main ────●────●────●────●────  始终可部署
           \        /
            feature-xxx  临时分支（开发→测试→合入→删除）
```

- **main 分支**：始终可部署，直接推送或PR合入
- **临时分支**：开发新功能时拉取（如 `feature/ad-ldap`、`fix/upload-bug`），测试通过后合入 main 并删除
- **Sprint 不体现在分支名或目录名中**：Sprint是研发工作分解阶段，在过程文档（docs/）中记录

### Sprint 流程（Scrum）

1. **需求**：Sprint Planning，拆分Story，确认验收标准
2. **设计**：复杂功能技术方案，API定义，ADR记录
3. **开发**：编码 + 单元测试 + 每日站会
4. **测试**：全量回归（`tests/test_api.py` 221项）+ Bug修复
5. **验证**：Sprint Review，PO验收，收集反馈
6. **复盘**：Retrospective，输出迭代小结文档（`docs/07-psf-sprintN-retrospective.md`）

### 每个Sprint必须交付

- [ ] 可工作的代码（`tests/test_api.py` 全通过）
- [ ] 迭代小结文档（`docs/07-psf-sprintN-retrospective.md`）
- [ ] 测试报告（如测试有变化）
- [ ] Git 提交（原子化，清晰的commit信息，不带Sprint编号）
- [ ] 推送到 Gitea 仓库 main 分支
- [ ] 发布（打包 + Gitea Release + git tag，如版本变化）

---

## 测试规范

### 自动化测试

- **测试脚本**：`tests/test_api.py`，使用Python标准库urllib，无额外依赖；**admin 凭据参数化**：`TEST_ADMIN_USER`/`TEST_ADMIN_PASS` 环境变量（默认 admin/Admin@123，Windows dev 场景）
- **测试范围**：全量221项，覆盖所有API和核心业务流程（含合作方白名单、审批人配置、i18n双语、网络面隔离、部署凭据策略、AD 配置管理/配置总览）
- **运行方式**：先启动服务（`cd src && python app.py`），再 `cd tests && python test_api.py`，预期通过率100%
- **部署验证**：`infra/verify.sh`（221项全量，BASE_URL 自动适配 .env HOST/PORT——HOST=具体IP时自动用 http://<IP>:PORT；**admin 凭据自动取 .env RESET_PASSWORD**（部署时 admin 密码已重置为该值），admin 密码被手工修改时用 `VERIFY_ADMIN_PASS` 显式传入）
- **新增功能**：必须在 test_api.py 中添加对应测试用例
- **i18n 测试**：双语回归组覆盖后端 error_en/message_en、动态模板翻译、前端 I18N 字典资源检查

### 测试通过标准

- P0 测试用例 100% 通过
- 核心流程（提交→审批→摆渡→下载）端到端跑通
- 无 P0/P1 未修复 Bug
- 权限隔离验证通过

---

## 部署规范

### 双模式部署

| 模式 | DEPLOY_MODE | 存储 | 启动方式 | 适用 |
|------|-------------|------|---------|------|
| 测试环境 | `testing`（默认） | 本地磁盘 `./nas` | `python app.py`（Flask自带） | 开发/测试验证 |
| 生产环境 | `production` | NAS 挂载 | `gunicorn app:app`（systemd 服务 securetrans） | 正式部署 |

切换方式：修改 `.env` 中的 `DEPLOY_MODE` 和 `NAS_ROOT`，换启动命令。代码完全不变。

### 配置生效机制（v2.2.9+）

- `securetrans.service` 用 `EnvironmentFile=/opt/securetrans/.env` + `-b ${HOST}:${PORT}` 变量展开
- **改 .env 后 `sudo systemctl restart securetrans` 即生效，无需重跑部署**（HOST/PORT/INTERNAL_CIDRS 等全部一致）
- `.env` 由 deploy.sh 保护：已存在则不覆盖（.env.deploybak 备份），需要重置时手工删除后重跑

### 配置权威矩阵（ADR-010，强制）

**三档配置，各档唯一权威，禁止双重配置**：

| 档位 | 权威位置 | 操作方式 | 生效方式 | 内容 |
|------|---------|---------|---------|------|
| 部署级配置 | `.env` 唯一 | 编辑 .env | restart 生效（systemd EnvironmentFile） | DEPLOY_MODE/HOST/PORT/INTERNAL_CIDRS/NAS_ROOT/SECURETRANS_DATA/SECRET_KEY/RESET_PASSWORD |
| 运行时配置 | SQLite system_config | 系统配置页 | 即时生效，**不再回写 .env** | app_name/auto_approval_enabled/default_expiry_days/max_file_size_mb |
| AD 连接配置 | SQLite ad_config | 系统配置页→AD 配置（导入 .env/保存） | 即时生效（空值回退 .env/默认） | ad_enabled/ad_host/ad_domain/ad_base_dn/ad_bind_dn/ad_bind_password/ad_user_field/ad_display_field/ad_mail_field/ad_group_field |

- **一致性机制**：①首次部署表空从 .env 播种（source=env）；②配置总览页（.env 只读 + DB 配置，逐项标来源 env/db + 更新时间）；③**DB 优先**（界面保存即权威）；④README/AGENTS/DEPLOY 三处文档同步
- **AD 配置首次启用**：系统配置页→AD 配置卡片→"从 .env 导入"把 .env 当前值读入 DB（source=env）→ 按需修改保存（source=db）→ 即时生效；AD_BIND_PASSWORD 脱敏显示（前2位+****），重新输入才覆盖
- **改 .env 里的 AD 参数不再生效**（运行期读 DB）；如需重置为 .env 值，管理页"从 .env 导入"

### 网络面业务语义（重要）

- 内/外网**均属公司内部网络分区**：内网=提交/审批区，外网=接收/下载区
- 无 NAT、不向互联网开放、无攻击威胁——分面隔离是**单向摆渡流程管控**而非防攻击
- `INTERNAL_CIDRS=10.10.10.0/24,10.10.30.0/24`（当前），后续加网段逗号追加 + restart
- 单网卡：防火墙放行 8000 即可，用户内/外网访问同一网址，应用层按源 IP 分面（external 仅登录+下载，管理接口 403）
- 双网卡（可选）：Nginx 双 server 注入 `X-Network-Zone` 头 + 应用层兜底

### 提交业务语义（接收方类型，v2.2.23+）

- **接收类型三分类（提交信息最前部，与接收密级并列）**：
  - `internal` 公司内部：仅需接收人姓名，单位可空；不入合作方清单；审批流等同非合作方
  - `partner` 合作方：优先从已配置合作方下拉选择（选择后自动填单位）；不在清单可自填单位+姓名，提交后**自动加入合作方清单**（信任模式，去重 NOCASE）
  - `non-partner` 非合作方：需填单位+姓名；**不加入**合作方清单，仅作为下载任务与日志记录
- 后端校验：internal 单位可空；partner/non-partner 单位必填；email 一律可选

### 部署脚本（infra/）

- `infra/deploy.sh`：一键式部署（root运行；Python 3.12 获取优先级：系统已有 → offline-python/ 离线RPM → dnf AppStream/EPEL；离线 wheel 优先；NAS_ROOT 可环境变量覆盖并写回 .env；systemd ReadWritePaths 模板渲染——NAS 不存在时只保留 /opt/securetrans，避免 systemd 226/NAMESPACE）
- `infra/get-offline-python.sh`：离线 Python 3.12 RPM 获取（联网 Rocky8 运行一次，产出 offline-python/ 随包离线携带）
- `infra/verify.sh`：部署验证（221项全量测试，BASE_URL 自适应绑定地址，admin 凭据自动取 .env RESET_PASSWORD）
- `infra/nginx-securetrans.conf` / `nginx-securetrans-single.conf`：Nginx 双/单网卡反向代理配置
- `infra/securetrans.service`：systemd服务配置（gunicorn，${HOST}:${PORT} 变量展开）
- `infra/ops-backup.sh` / `ops-restore.sh <name>` / `ops-reset.sh` / `ops-mock.sh`：数据生命周期离线脚本（ADR-011；服务停止时最安全；ops-mock 仅 testing 环境）
- deploy.sh 支持 `RESET_DB=1 bash deploy.sh`：部署时出厂重置（测试环境用，ADR-011）
- 脚本必须使用LF换行，不能有CRLF；修改后必须 `bash -n` 语法检查

### 生产环境要求

- Python 3.12（与离线 wheel cp312 匹配；venv 与系统完全隔离；Rocky 8 用 AppStream/EPEL/离线 RPM 获取，不做源码编译）
- Nginx（可选，Alpha 阶段 gunicorn 直连即可）
- NAS挂载（staging/external/archive同文件系统，os.rename才能0拷贝）
- systemd（服务管理）
- gunicorn（WSGI服务器，不用Flask自带服务器）

### 发布流程

**触发规则（详见 ADR-007）**：
- 调测期（PSF Alpha/Beta）：代码/脚本/配置模板每次变更即发布（双环境 TDD 全量回归通过后）
- RTM 后：默认不逐次发布，关键里程碑手工发布
- 文档-only 变更：commit + push main，不 bump、不打包、不建 Release


- **打包**：`bash infra/package.sh <版本>` → `packages/securetrans-<版本>.tar.gz`（含 offline-python/ + offline-deps）
- **发布**：`powershell -File infra/release.ps1 -Version v<版本>` → Gitea Release（源码包 + offline-deps 资产）
- **版本记录**：`git tag v<版本>` + push tags；每次部署打包=发布，需明确发布版本和 Gitea 记录

---

## 安全规范

- **密码**：bcrypt哈希存储，不明文
- **密钥**：SECRET_KEY通过.env配置，不硬编码在代码中
- **权限**：后端每个管理接口必须有 `@role_required` 装饰器
- **审计**：所有关键操作（登录、提交、审批、配置变更）记录审计日志
- **文件上传**：限制大小（MAX_CONTENT_LENGTH），流式写入磁盘
- **会话**：Flask-Login，HTTPOnly cookie，SameSite=Lax
- **权限模型（简化）**：仅 admin 可管理配置（用户/系统/特征码/合作方/审批人）；其他用户默认普通用户无提权能力；审批权限通过 approvers 表由 admin 配置，不设复杂 role/group 体系
- **网络面隔离**：应用层 `get_network_zone()` 两级识别（X-Network-Zone 头 → 客户端IP+INTERNAL_CIDRS 兜底）——外网面仅开放登录+下载接口，管理接口返回 403

---

## 常见陷阱

1. **不要用 shutil.move 做摆渡**：跨目录时会退化为复制+删除，大文件很慢。必须用 os.rename。
2. **不要在 if __name__ == "__main__" 中初始化数据库**：gunicorn导入时不执行该块，数据库表不会创建。初始化必须在模块级别。
3. **不要把 venv 目录提交到 Git**：不同平台不兼容，部署时自动重建。
4. **不要把测试数据提交到 Git**：data/securetrans.db 和 nas/ 中的测试文件应排除，首次启动自动创建。
5. **不要在前端做权限校验**：前端只做体验优化，后端必须校验每个接口的权限。
6. **不要用 CRLF 换行保存 shell 脚本**：Linux上会报 "command not found" 错误。
7. **不要按Sprint建目录**：主干开发按功能模块组织代码（src/），Sprint在文档中体现，Git历史追溯变更。
8. **不要在commit message中强制带Sprint编号**：Sprint是管理节奏，不是代码的身份证。
9. **不要以为改 .env 需要重跑部署**：v2.2.9+ 改 .env 后 `systemctl restart securetrans` 即生效（systemd 变量展开）。
10. **verify.sh 绑定自适应**：未传参时自动从 .env HOST/PORT 构造 BASE_URL（HOST=具体IP → http://<IP>:PORT），不要在服务器上手动传 127.0.0.1。
11. **verify 凭据取 .env RESET_PASSWORD**：每次部署 deploy.sh 会将 admin 密码重置为 .env RESET_PASSWORD（默认 Init@123456），verify.sh 自动读取；**改密测试用专用用户 testpwuser，不碰真实 admin 密码**；admin 密码手工修改后验证需 `VERIFY_ADMIN_PASS=xxx bash infra/verify.sh`。

---

*AGENTS.md v1.9 | 2026-09-09*
