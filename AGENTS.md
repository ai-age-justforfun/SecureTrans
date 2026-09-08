# SecureTrans 项目 AI 协作指南

> 本文件指导 AI Agent 在本项目中的协作行为，确保代码和文档的一致性。

---

## 项目概况

- **项目名**：SecureTrans — 轻量级跨网文件审批摆渡系统
- **当前阶段**：PSF（问题-方案匹配验证）— Alpha 内测进行中
- **当前版本**：v2.2.14（版本号单一来源：`src/app.py` 的 `APP_VERSION`，前端 index.html 同步）
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
- **认证**：Flask-Login，本地用户 + AD用户（LDAP直连）统一会话管理
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
- **调测门禁（双环境 TDD 全量回归）**：本地调测中间阶段——Windows 开发环境（testing：`python test_api.py` 172 项）
  + WSL 测试环境（production：`infra/verify.sh` 172 项），**全部通过才允许 bump + 发布**
- 版本号是发布产物属性，APP_VERSION 只在代码发布时递增

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
4. **测试**：全量回归（`tests/test_api.py` 172项）+ Bug修复
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

- **测试脚本**：`tests/test_api.py`，使用Python标准库urllib，无额外依赖
- **测试范围**：全量172项，覆盖所有API和核心业务流程（含合作方白名单、审批人配置、i18n双语、网络面隔离）
- **运行方式**：先启动服务（`cd src && python app.py`），再 `cd tests && python test_api.py`，预期通过率100%
- **部署验证**：`infra/verify.sh`（172项全量，BASE_URL 自动适配 .env HOST/PORT——HOST=具体IP时自动用 http://<IP>:PORT）
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

### 网络面业务语义（重要）

- 内/外网**均属公司内部网络分区**：内网=提交/审批区，外网=接收/下载区
- 无 NAT、不向互联网开放、无攻击威胁——分面隔离是**单向摆渡流程管控**而非防攻击
- `INTERNAL_CIDRS=10.10.10.0/24,10.10.30.0/24`（当前），后续加网段逗号追加 + restart
- 单网卡：防火墙放行 8000 即可，用户内/外网访问同一网址，应用层按源 IP 分面（external 仅登录+下载，管理接口 403）
- 双网卡（可选）：Nginx 双 server 注入 `X-Network-Zone` 头 + 应用层兜底

### 部署脚本（infra/）

- `infra/deploy.sh`：一键式部署（root运行；Python 3.12 获取优先级：系统已有 → offline-python/ 离线RPM → dnf AppStream/EPEL；离线 wheel 优先；NAS_ROOT 可环境变量覆盖并写回 .env；systemd ReadWritePaths 模板渲染——NAS 不存在时只保留 /opt/securetrans，避免 systemd 226/NAMESPACE）
- `infra/get-offline-python.sh`：离线 Python 3.12 RPM 获取（联网 Rocky8 运行一次，产出 offline-python/ 随包离线携带）
- `infra/verify.sh`：部署验证（172项全量测试，BASE_URL 自适应绑定地址）
- `infra/nginx-securetrans.conf` / `nginx-securetrans-single.conf`：Nginx 双/单网卡反向代理配置
- `infra/securetrans.service`：systemd服务配置（gunicorn，${HOST}:${PORT} 变量展开）
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

---

*AGENTS.md v1.7 | 2026-09-08*
