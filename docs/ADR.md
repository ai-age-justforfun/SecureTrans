# SecureTrans 技术决策记录（ADR）

> 定位：全部架构/流程/安全/运维关键决策的唯一权威文档，与 PRD（docs/02）并列。
> README 与 AGENTS 仅保留最新落点摘要与索引，全文以本文件为准（ADR-032 文档体系决策）。
> 命名规则：ADR-<序号>：<主题>（决策强制程度标注）。编号只增不减，一旦记录不修改历史结论，只追加。
> 检索：ADDR 编号 → 关联版本（v2.x.x）→ 关联代码落点。

---
### ADR-001：os.rename 而不是软链接
- 0拷贝性能等价，但全平台原生支持，NAS兼容性好，权限简单
- 详见 PRD v2.2 第2.2节

---

---

### ADR-002：Flask 而不是 FastAPI
- Flask-Login生态成熟，团队学习成本低，50人规模性能不是瓶颈
- 详见 PRD v2.2 第3.2节

---

---

### ADR-003：主干开发 + 单分支
- 小团队/副业项目，避免多分支合并冲突，main始终可部署
- Sprint作为研发分解阶段在文档中体现，不用目录结构做版本管理

---

---

### ADR-004：Python 3.12 + venv 隔离
- 与系统环境完全隔离（`python -m venv --copies`），离线 wheel cp312 匹配；Rocky 8 用 AppStream/EPEL/离线 RPM 获取，无需源码编译

---

---

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

---

---

### ADR-006：网络面安全假设（封闭数据中心场景）
- **背景**：服务器位于数据中心防火墙内部，办公网 ↔ 数据中心经 IPsec 加密隧道互联；内/外网均为公司内部网络分区
  （内网=提交/审批区，外网=接收/下载区），无 NAT、不向互联网开放、无攻击威胁
- **决策**：假设网络层安全由公司基础设施承担（IPsec 加密 + 防火墙边界），**系统防火墙（firewalld）可不启用**（简化部署）；
  应用层保留**流程管控级隔离**：外网面仅登录+下载、管理接口 403（get_network_zone 两级识别），并保留认证/审批权限/审计/文件限制底线
- **已落点**：INTERNAL_CIDRS 业务语义、get_network_zone()（X-Network-Zone 头 → 客户端IP+网段兜底）、deploy.sh/verify.sh 防火墙可跳过
- **边界（重要）**：本假设仅适用于当前封闭数据中心；若部署到互联网可达环境，必须启用 Nginx + HTTPS + firewalld（见 DEPLOY.md）

---

---

### ADR-007：发布策略与调测门禁
- **背景**：小团队/副业项目，调测期迭代密集；发布 = 正式版本（Gitea Release + git tag + 包资产），代表可部署产物
- **决策**：
  - **调测期（PSF Alpha/Beta）**：代码/脚本/配置模板每次变更即发布（密集发布，便于服务器及时验证）
  - **正式发布后（RTM）**：默认不逐次发布，关键里程碑手工发布
  - **文档-only 变更**（README/AGENTS/docs/*.md）：commit + push main，不 bump、不打包、不建 Release（随仓库演进，代码发布时包内自动带入最新）
  - **调测门禁**：本地调测中间阶段保持双环境 TDD 全量回归——Windows 开发环境（testing：`python test_api.py` 361项）
    + WSL 测试环境（production：`infra/verify.sh` 361项），**全部通过才允许 bump + 发布**
  - 版本号是发布产物属性，APP_VERSION 只在代码发布时递增；文档内部版本号独立演进
  - **发布触发自动化与 AI 边界**：见 **ADR-047**（三平台触发机制=git 事件自动；AI 只保留打 tag/发布决策 + 应急 dispatch，流水线本体平台自治）

---

---

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

---

---

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

---

---

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

---

---

### ADR-011：数据生命周期与运维功能化（强制）
- **背景**：测试环境部署时需要清空老库/恢复初始配置，生产环境原则上不能动数据但需要按需备份+清理、备份、恢复；开发/测试/生产环境代码配置数据不分离导致验证不可靠。业界最佳实践：运维期内有用的功能应收尽收进系统（Web API + 界面 + TDD 可调），脚本只保留首部署与离线场景。
- **决策（三环境一套代码配置数据脚本）**：dev(Windows) / test(WSL) / prod(Rocky) 程序与配置完全一致（DEPLOY_MODE 开关 + .env）；差异只在数据策略——dev/test 用**模拟数据 + verify.sh 全量验证**闭环，prod 用**备份/恢复/出厂重置**；代码、配置、数据三者分离可自由组合。
- **系统功能（admin 菜单"系统工具"，确认码保护）**：备份 `POST /api/admin/ops/backup` + 列表 `GET /api/admin/ops/backups`（**scope 拆分**：`system`=仅系统 DB（升级前后回退用）/ `business`=仅 NAS 业务文件（换存储/归档用）/ `all`=两者，界面系统/业务两个备份卡 + 列表 hasDb/hasNas 标记；DB 用 sqlite backup API 一致性快照 + NAS 业务目录 → data/backups/backup-<ts>）；恢复 `POST /api/admin/ops/restore`（确认码 RESTORE，支持 scope，回退=再恢复之前的备份）；出厂重置 `POST /api/admin/ops/reset-factory`（确认码 RESET，**自动先备份** → 清空 → init_db 重建 → admin 密码重置为 .env RESET_PASSWORD）；模拟数据 `POST /api/admin/ops/mock-data`（确认码 MOCK，**仅 testing 模式**，生产 403）。
- **离线脚本（infra/，服务停止时最安全）**：`ops-backup.sh [all|system|business]` / `ops-restore.sh <name> [all|system|business]` / `ops-reset.sh`（备份+清理，调 CLI `--reset-factory`）/ `ops-mock.sh`（调 CLI `--mock-data`）；deploy.sh 支持 `RESET_DB=1` 部署时出厂重置（测试环境用）。
- **与 ADR-010 不重叠**：ADR-010 管配置权威（静态三档），ADR-011 管数据生命周期与运维操作（动态）；mock+verify 构成 ADR-007 调测门禁的执行闭环。
- **已落点**：v2.2.27（app.py ops 路由 scope 拆分 + 前端系统/业务备份卡 + ops-*.sh scope 参数 + test_api.py 318 项 + deploy.sh 9.8 RESET_DB；v2.2.23 初版：ops 路由 + CLI --reset-factory/--mock-data + 前端系统工具页 + test_api.py 318 项 + infra/ops-*.sh）
- **v2.2.29 强化（备份命名区分，普通人可识别）**：备份目录名改为 `backup-system-<ts>` / `backup-business-<ts>` / `backup-all-<ts>`（名字即类型）；列表带 `type` 字段；系统工具页**两个独立备份列表**（系统备份列表 / 业务数据备份列表），恢复按钮不再选 scope——**后端按备份名自动推导类型**，杜绝"从同一个备份混恢复"；旧版 `backup-<ts>` 兼容识别为 all
- **v2.2.30 备份删除（不永久保留）**：新增 `DELETE /api/admin/ops/backups/<name>`（admin）——前端备份列表行加"删除"按钮（确认后删除，删除不可恢复）；后端校验备份名（backup- 前缀 + 无路径穿越，路径穿越由 Flask 路由 405 兜底）；审计日志 ops_delete_backup

---

---

### ADR-012：性能与文件完整性——800MB 全链路压力测试 + MD5 端到端四方一致（强制）
- **背景**：生产部署前需要正式的性能与完整性验证——800MB 大文件 上传→审批摆渡→下载 全链路性能；文件完整性（MD5）端到端保证，防止传输/摆渡过程损坏。
- **决策**：
  - **MD5 四方一致（强制）**：上传流式计算 MD5 存入 submission_files → 下载时从 DB 取 MD5 写入 download_records.md5 并回传响应头 `X-File-MD5` → 下载内容本地再算 MD5 比对（上传值 = DB 值 = 响应头 = 下载内容）；审计日志 download 记录带 MD5；前端上传列表/详情显示完整 MD5
  - **性能压力测试工具 tests/perf_test.py（系统级能力，TDD 可调）**：流式生成大文件（边写边算 MD5）→ 流式 multipart 上传 → 合作方提交单一级审批（计时含 os.rename 摆渡）→ 流式下载 → MD5 四方比对 → JSON 报告 + 阈值断言 + 自动清理；`PERF_SIZE_MB`（默认 800）/`PERF_ADMIN_*`/`PERF_MAX_*_S` 环境变量，退出码 0/2
  - **上传上限统一口径**：`.env MAX_FILE_SIZE_MB`（单文件上限，默认 800）唯一配置；`MAX_CONTENT_LENGTH` 自动 = 文件上限 + 1MB（multipart 封装余量），禁止手工配置——否则 800MB 文件 + boundary 封装会 413（v2.2.24 实测命中并修复）
  - **删除提交单（运维功能，admin + 确认码 DEL）**：清 DB 三关联表 + STAGING/EXTERNAL/ARCHIVE 三目录，防误触；对 admin 前端可见
- **与 ADR-011 不重叠**：ADR-011 管数据生命周期（备份/恢复/重置），ADR-012 管性能验证与文件完整性（删除提交单是其中运维项，确认码机制一致）
- **已落点**：v2.2.24（app.py：download_records.md5 迁移/下载 X-File-MD5/删除提交单 API/MAX_FILE_SIZE_MB；前端完整 MD5 + 删除按钮；tests/perf_test.py；test_api.py 318 项；800MB 实测：上传 338 MB/s / 摆渡 34ms / 下载 350 MB/s / 全链路 5.94s / MD5 四方一致）

---

---

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

---

---

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

---

---

### ADR-016：12-Factor 三环境一体化（强制）
- **决策**：`env/*.env` 分层配置（dev/test/prod 三模板）为唯一配置键源；app.py 启动自动加载同目录 `.env`（不覆盖已注入环境变量，systemd EnvironmentFile 优先）；`AD_MOCK_MODE` 模拟目录（dev/test 用，生产 false）；tests/mock 种子与基线（docs/07 需求↔测试追踪矩阵）；Gitea Actions CI（.gitea/workflows/ci.yml + 本地 runner）
- **已落点**：v2.2.26（env/ 三模板 + 12-Factor 加载 + mock 目录 + CI 首跑）；详见 DEPLOY.md 5.5

---

---

### ADR-017：测试/生产环境隔离（三合一，强制）
- **背景**：verify.sh 原为三环境同一全量脚本，生产跑全量必污染（建用户/上传/审批/备份/改配置/改密/清理归档）。
- **决策**：
  1. **代码合一**：`tests/test_api.py` 单脚本承载全量回归 + 冒烟白名单（组 24，10 项纯只读：health/登录/会话/查询/网络面模拟/i18n 资源/登出）。
  2. **入口分离**：`infra/verify.sh`=dev/test/CI 全量（ENV_ROLE=test，本脚本读 .env 自动注入）；`infra/smoke.sh`=生产 allowlist 只读冒烟（SMOKE_MODE=1，仅组 24）。
  3. **fail-safe 护栏（宁可误拒不可误写）**：ENV_ROLE=prod 或 SMOKE_MODE=1 时，组 1~23 整组代码不执行（含请求层拦截 POST/PUT/DELETE/PATCH 与上传），生产误跑全量零副作用；`/api/health` 返回 `envRole` 便于监控确认。
  4. **与 ADR-016 不重叠**：ADR-016 管三环境配置/数据分层与 CI 骨架；ADR-017 管测试执行入口与生产零写护栏。

---

---

### ADR-018：CI/CD 分层与质量门禁（强制）
- **背景**：原 CI 仅单 job 全量回归（push 触发），无秒级门禁、无测试计数防缩水、发布包靠本地手工 package.sh。
- **决策**：
  1. **分层流水线（最便宜门禁先失败）**：`fast-check`（语法 py_compile / 版本号双源一致性 / env 模板 ENV_ROLE / 关键脚本完整性，秒级，总是执行）→ `tdd-verify`（全量 TDD，needs fast-check 失败即停）→ `package`（仅 `tags: v*` 触发）。
  2. **质量门禁（防静默删减）**：`test_api.py` 报告段断言计数基线——全量模式 ≥300 项、冒烟模式 ==10 项（白名单为显式维护集合，增减需同步门禁）。
  3. **tag 驱动发布构建（build once, deploy many）**：push tag v* 自动 clone 该 tag → 复用 /opt/securetrans/packages 的 offline-deps → package.sh 构建 → 制品落到共享 packages/（离线环境无 node/网络，不使用 actions/upload-artifact@v4）；实际 Release 资产由 `infra/release.ps1` 手工上传同一制品（发布策略 ADR-014：调测期密集手工，关键点人工发布）。
  4. **并行与 fail-fast**：tdd-verify needs fast-check（秒级门禁失败不浪费全量资源）；package needs 前两者。
  5. **与 ADR-016/017 不重叠**：ADR-016 管三环境配置/数据分层，ADR-017 管测试/生产执行隔离，ADR-018 管流水线结构与门禁。

---

---

### ADR-019：CI 运行环境隔离与静态门禁（强制）

- **背景**：CI 首跑发现 ① act_runner 偶发 shutdown（WSL 会话回收，导致 push 漏跑）；② act_runner 直接在宿主执行 job，公开仓库有逃逸到主机的风险；③ CI 与测试环境共用 /opt/securetrans，存在版本/数据干扰。
- **决策**：
  1. **runner 常驻**：act_runner 以 systemd 单元（`/etc/systemd/system/act_runner.service`）常驻，`Restart=always` + 开机自启（WSL 重启/崩溃自动拉起）。
  2. **静态门禁前置**：新增 `infra/static_check.py`（零依赖 AST 检查：语法编译 / 未定义名称（作用域链）/ 重复函数类定义 / 未使用 import），挂入 ci.yml fast-check 第一步之后；已清理历史遗留未使用 import（app.py render_template、test_api.py time）。
  3. **CI 容器化隔离（目标态）**：构建可复用镜像 `securetrans-ci:3.12`（python:3.12-slim + 离线 wheelhouse 同源依赖）；容器入口 `infra/ci_test.sh`（无 systemd 直接 gunicorn loopback；配置经环境变量注入不写 .env；数据目录 /data 随容器销毁）→ 每次 job 全新容器 + 新配置 + 新数据，避免版本干扰与宿主污染。切换前提：Docker Desktop 启用 WSL Integration（需重启 Docker Desktop，短暂中断 Gitea）→ act_runner label 改 `docker://securetrans-ci:3.12`。
  4. **与 ADR-016/017/018 关系**：ADR-016 管三环境配置/数据分层；ADR-017 管测试/生产执行隔离；ADR-018 管流水线结构与计数门禁；ADR-019 管 runner 运行方式与 job 运行环境隔离。

---

---

### ADR-020：配置单一来源 + 容器 CI 实跑 + 系统依赖统一（强制）
- **背景**：① CI 用环境变量注入、测试/生产用 .env，两条路配置信息可能漂移（CI 漏注入 AD_MOCK_MODE 曾致 AD mock 登录 401）；② "能否与 gitea 无关另起 docker 做 CI"——需要验证；③ 生产缺 openldap-clients 等系统工具，测试环境同样缺（环境不一致）。
- **决策**：
  1. **配置单一来源**：`env/*.env` 是唯一配置键定义源——CI 容器 `source env/test.env` 全键注入（app.py 12-Factor env 优先，不写 .env 文件）；测试环境 deploy 用 test.env 生成 .env；生产用 prod.env.template 生成 .env；fast-check 新增"配置键一致性"门禁（dev/test 键集合完全一致、prod 可多不可缺），防三环境配置漂移。**配置信息一致 = 同源键 + 自动校验**，而非仅读取过程一致。
  2. **WSL 独立 docker daemon**：`dnf install docker-ce`（WSL rocky10-st 在线装 29.8.0），与 Docker Desktop（跑 Gitea）完全独立——不启用 WSL Integration、不重启 Docker Desktop、Gitea 零中断。镜像 `docker save`（Windows）→ `docker load`（WSL）传输。
  3. **容器 CI 实跑**：act_runner 双 label（`securetrans-wsl:host` 宿主 / `securetrans-ci:docker://securetrans-ci:3.12` 容器）；fast-check/tdd-verify 跑容器（全新环境），package 留宿主（访问共享 packages/）。容器 job 关键点：① act_runner 容器模式**不自动 checkout**，需显式 `git clone`（容器经 **WSL 网关 IP** 172.29.x.1:3000 访问 Gitea，/proc/net/route 动态解析）；② 测试端口 18000 避开宿主 8000；③ 实测 fast-check 稳定 3s、tdd-verify 容器内 309/309 全绿。
  4. **runner 抗信号**：WSL 环境偶发外部 SIGTERM（journal 无 Stopping），`shutdown_timeout: 3h` 让 runner 收到信号后**等运行中 job 完成再退**，不再中断 CI（根因调查记 docs/08 Backlog B5）。
  5. **系统依赖统一**：程序运行依赖全走 venv + wheelhouse（离线打包）；系统级工具（ldapsearch/openldap-clients 等）**在线 dnf / 离线 rpm 双模式**——测试环境先装齐（已装），生产离线时 rpm 进离线依赖包。
- **已落点**：2026-09-11 容器化 CI 首跑（run 81-87）；fast-check 稳定成功；容器 TDD 309/309 本地+CI 实测；config.yaml.example 入仓；文档四件套同步。

---

---

### ADR-021：WSL CI 稳定性根因与修复（强制）
- **背景**：CI 在 WSL rocky10-st 间歇性中断/假绿（run 91 tdd 卡 14 分钟、run 92/93/94 tdd 20s 假绿"成功"但无测试输出），逐层取证（wslmon 进程监控 / act_runner 日志 / docker ps / workspace 残留 / 容器内进程抓取）定位双因。
- **决策**：
  1. **WSL 发行版空闲自动终止 → 保活**：WSL2 发行版无交互会话即被终止（后台 daemon 不算活跃），act_runner 因此反复 SIGTERM。修复：Windows 计划任务 `WSL-Rocky10-KeepAlive` 每 1 分钟执行 `wsl.exe -d rocky10-st -- sleep 45`（保持连接）。实证：13:24:25 后 act_runner 连续稳定 >20 分钟（此前每 1-3 分钟必崩）。
  2. **act_runner v0.2.11 needs bug → 单 job**：含 `needs` 的容器 job 解析异常（"runs-on not defined"/"No steps found"→ 容器秒退、Gitea 误标成功）。修复：**合并 fast-check+tdd-verify 为单 job `ci-check`**（无 needs，静态门禁步骤在前秒级先失败、全量 TDD 在后），package 去 needs（仅 tag 独立跑）。
  3. **CI 可信基线**：run 97 实证 ci-check 22s 成功；容器内进程取证 ci_test.sh + gunicorn + pytest 真跑；318/318 全绿（模拟同流程 20s 完成 318 项，SQLite 毫秒级）。
- **与 ADR-019/020 关系**：ADR-019 管 runner 常驻/容器隔离；ADR-020 管配置单一来源/双 label/依赖统一；ADR-021 管"WSL 发行版保活 + CI 单 job 规避 needs bug"（运行稳定性修复）。
- **已落点**：2026-09-11 修复闭环；docs/08 第十节 + Backlog B5 更新为已解决；保活计划任务已创建（Windows 管理员可见）。**修正（同日）**：网络核实 WSL 2.6.1.0 无终端会话 15-20s 关闭 VM（microsoft/WSL#13416）——诊断为版本相关行为；保活计划任务因每 1 分钟弹窗已删除，改为"用户保持 WSL 终端活跃 + CI job 22s 短时"策略，如再现空闲终止再启用隐藏版保活。

---

---

### ADR-022：依赖双轨 / 支持矩阵 / 发布形态（强制）
- **背景**：用户确认三个业界实践方向，并要求"在线优先、离线兜底"在测试环境实测。
- **决策**：
  1. **依赖安装在线优先、离线兜底**：deploy.sh 统一为先 `dnf/pip 在线` → 失败自动回退 `offline-python/`（Python 3.12 RPM）/ `offline-deps/`（cp312 wheel）→ 再无则明确报错退出（不静默降级）。在线命令固化在脚本+文档，离线包为 Release asset——**两者均入 Gitea**。
  2. **支持矩阵只保证一种组合**：Python 3.12 + Rocky 8.10（生产）/ WSL rocky10-st（测试）/ Windows dev（开发）；venv（--copies 与系统隔离）+ wheelhouse（cp312）三环境一致；其他组合 best-effort；后续升级整体评估。
  3. **发布形态两轨并存**：仓库=源码全工程（"源码即发布"）；Release=发行包（tar.gz + offline-deps + md5/sha256）。**保持全量打包不精简**——理由：离线部署一包全含（src/infra/env/offline-deps/offline-python/tests/docs）、服务器可自测 verify、体积数 MB 可忽略；未来对外分发或体积显著增长时拆"源码包+部署包"。
- **已落点**：2026-09-11 deploy.sh 双轨反转完成（在线优先）+ docs/08 第十一节 + WSL 测试环境实测记录。

---

---

### ADR-023：文件名安全清理 + AD 改密前端拦截（v2.3.7，强制）
- **背景**：Beta 手工验收发现两个缺陷——① 文件夹上传（webkitdirectory）任何数量文件均 HTTP 500（根因：File.name 携带相对路径如 sub/a.txt，后端 open() 因子目录缺失抛 FileNotFoundError）；② AD 用户点击"修改密码"仍弹表单（后端 400 兜底但前端无拦截）。
- **决策**：
  1. **上传接口文件名安全清理**：对 file.filename 统一取 basename（先替换 `\`→`/` 再取末段），空名/`.`/`..` 拒绝（400"非法文件名"）；既防相对路径导致的目录缺失 500，也防路径穿越。
  2. **AD 改密前端拦截**：showChangePwdModal 中 `window._cu.source === 'ad'` 直接提示"AD 用户请在域控制器修改"，不再弹表单（后端 api_change_password 400 兜底不变）。
  3. **空文件夹提示**：handleFiles 空列表直接提示"所选文件夹为空或无文件"；上传成功 toast 显示后端清理后的文件名（data.name）。
- **已落点**：2026-09-11 v2.3.7；复现脚本验证（路径分隔符 500→200，中文/0字节/多文件全 200）；Windows dev 全量 TDD 318/318 通过。

---

---

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



---

---

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

---

---

### ADR-026：以 git 为中心的三环境独立 + WSL 原生路径（强制）
- **背景**：WSL 经 `/mnt/c`（9p 挂载）访问 Windows 文件系统极慢——rsync 逐个 stat 上万文件导致全量回归从"几十秒"退化到"十几分钟"；`package.sh` 在 `/mnt/c` 上 `cp -r` 曾卡死（D+ 状态）。且 9p 的权限/锁语义与 Linux 原生不一致，易产生环境差异误判。
- **决策**：
  1. **以 git 为中心**：Windows dev / WSL test / 生产 三环境各持**独立 git 工作副本**，唯一同步通道 = Gitea（push / pull / clone）。**禁止 rsync/scp 直拷代码目录**（慢 + 版本漂移）。
  2. **WSL 必须使用原生 Linux 路径**（如 `/opt/securetrans`）；**禁止在 WSL 中使用 `/mnt/c`、`/mnt/d` 等 Windows 挂载路径**做开发、测试、打包、运行。
  3. **变更以 commit 为唯一载体**：Windows 侧编辑 → `commit + push main` → WSL `pull`（或 CI/CD 容器 clone）→ 测试/部署。CI/CD 容器每次从 Gitea clone，不接触任何宿主目录。
  4. **环境态不入库**：`.env` / `data/` / `venv/` / `offline-python/` 等由 .gitignore 排除，`git fetch/checkout` 不影响（untracked 保留，已实证）；生产 .env 由部署流程管理。
  5. **WSL runner 运行配置保护**：`/opt/securetrans/.runner` + `config.yaml`（act_runner 注册与配置，label 含 `securetrans-ci:docker://securetrans-ci:3.12`）**不入库**；备份/重置/清理操作**禁止移动或删除二者**——2026-09-12 曾因备份操作丢失（进程内存持有配置才未断 CI），已从 `/opt/securetrans_backup_20260911_142320/` 恢复；缺失时重启 runner 将丢失容器 label。
- **已落点**：2026-09-12 WSL `/opt/securetrans` 初始化为 git 仓库并 pull（HEAD=548a21c，.env/data 保留）；全量回归耗时 十几分钟 → **58.6s**；三环境结果 Windows 350/350 + WSL 100% + CI run 149 success。

---

---

### ADR-027：技术-商业双闭环复盘（PSF 收尾 · stepping-stone 方法论，过程成果，强制）
- **背景**：v2.4.x beta 运行期（PSF 收尾），用户要求跳出技术/工程复盘，对"技术-商业双闭环"展开复盘并将过程成果留痕。代码零改动。
- **决策与共识**：
  1. **nginx 暂不引入（日均 5-10 次访问）**：gunicorn 直连 8000 已满足；收益（HTTPS/静态/缓冲/限速）在封闭数据中心（ADR-006）+ 低并发下边际趋近零，成本（多进程面/离线组件/运维面）明确。**升级触发条件**：① 并发上传/下载出现 worker 阻塞（如 2 人同时传 800MB）；② 需要对外 HTTPS/域名/访问限速。届时启用 `infra/nginx` 预研模板（预研不预装）。
  2. **特性治理原则（"想多了"回退复盘）**：PSF 阶段只实现"被使用验证的需求"；"推演需求"一律标记为假设（Backlog/PMF 预备），不在当前实现。已回退案例：双网卡→单网卡单端口（ADR-008）、role 体系→纯 approvers（ADR-015）、强制改密→建议改密（ADR-009）。AI 侧规矩：推演特性标"假设"，用户/真实用户确认"确实需要"才进当前迭代。
  3. **阶段定位**：beta = PSF 收尾（问题/方案验证）；PMF 才验证市场。发布成功 ≠ 产品成功；"万里长征第一步"，可进可退——每个版本是 stepping-stone，密集发布是低成本验证（ADR-014 已固化）。
  4. **方法论：重型 V 模型 → stepping-stone**：需求冻结/大设计/大测试/一次性交付 → 小步快跑、按需调整；**技术债显式记账 + 偿还触发条件**，PSF 阶段是合理投资而非原罪；回退 = 信息。
  5. **人机协同双闭环**：闭环 A（技术-工程-产品：需求→ADR→TDD→CI/CD→发布→beta 已闭环）；闭环 B（商业：PSF 问题/方案验证→PMF 市场验证→Scale，正在收尾 PSF）；过程层（体会/回退/心态）同为项目资产，决策留痕 = 下一轮决策输入。
- **已落点**：2026-09-14 本记录；nginx 升级触发条件列入 Backlog；代码零改动。

---

---

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

---

---

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

---

---

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

---

---

### ADR-031：合作方全量编辑 / WSL测试环境退居二线 / 生产冒烟为业界标准（v2.6.2，强制）
- **背景**：beta 使用中发现三件事——① 合作方在提交时自动加入清单后，管理页仅能"禁用/删除"，无法编辑（名称/联系人/邮箱修正只能删除重建）；② 用户质疑"WSL 独立测试环境 + CI 容器测试环境"双环境冗余；③ 用户求证"生产只读冒烟"是否为业界最佳实践。
- **决策**：
  1. **合作方全量编辑**：新增 `PUT /api/admin/partners/<id>`（名称/联系人/邮箱；名称必填 + 去重检查排除自身 COLLATE NOCASE，与提交自动加入一致；404 不存在/400 空名/400 重名）；前端表格加"编辑"按钮 + 编辑弹窗（复用新增弹窗，预填当前值）；审计日志 update_partner；TDD 新增 6 项（编辑生效/空名拒绝/重名拒绝/404/清理）。
  2. **WSL 常驻测试环境退居二线**：职责已被覆盖——Windows dev 全量 TDD（第一道快速门禁，秒级）+ CI 容器全量 TDD（发布门禁，Linux 环境，每次全新数据）。WSL 不再单独跑 verify.sh / 不再做"三环境 git 副本 push 同步"（ADR-026 修订：以 git 为中心不变，但测试执行收敛到 dev + CI 两环境）；WSL 保留为 CI 容器宿主（rocky10-st docker daemon）与 Linux 问题排查入口（按需 `docker run securetrans-ci:3.12` 复现）。
  3. **生产只读冒烟 = 业界标准**：生产环境自动化验证遵循"健康检查 + 只读冒烟 + 版本/目录校验"（SRE/DevOps 标准：smoke test in prod 必须 read-only，写测试数据只允许在测试环境；蓝绿/金丝雀部署的 validation hook 同此原则）。本系统单实例无灰度，CD 以 healthz + 包内版本=部署版本 + 加载目录校验为门禁，smoke.sh 只读 11 项；功能验收靠人工 beta 走查（符合 12-Factor / ADR-017 fail-safe）。
- **与 ADR-030 不重叠**：030 管 .ltx/性能门禁/发布说明/审批人播种；031 管合作方编辑功能、测试环境收敛、生产冒烟原则确认。
- **已落点**：v2.6.2（Windows dev 全量 TDD 372/372 通过；合作方编辑 6 项新增用例；CI 容器全量 + 性能门禁；生产 CD 部署后 `/api/health` = v2.6.2/beta/ok/production）。

---

### ADR-032：合作方联系人必填 / 无状态上传与临时文件清理 / 文档体系单源化（v2.6.3，强制）
- **背景**：beta 评审发现三类问题——① 合作方编辑弹窗联系人非必填（提交可无联系人，无法追溯对接人）；② 上传选择文件但未提交，刷新后消失（无状态设计），staging 残留临时目录无清理机制（浪费空间、不归档）；③ 文档体系：ADR 全文散在 README/AGENTS（重复维护、易漂移），需求方要求"ADR 独立成文 + README/AGENTS 仅引用"。
- **决策**：
  1. **合作方联系人必填（名称 + 联系人双必填）**：创建/编辑接口统一校验 `contact` 非空（400"联系人不能为空"）；前端弹窗联系人带 `*` 标记 + 提交前强制检查；自动加入清单路径（提交时信任模式）不受影响（contact=receiverName，天然非空）。邮箱保持可选。
  2. **无状态上传（明示行为）**：前端选择文件仅写入浏览器会话（tempId），未提交则刷新即弃——这是有意的无状态设计（无草稿箱），已写入 PRD 明示；已提交前不产生提交单、不正式归档、不进入审计。
  3. **未提交临时文件清理（系统级回收）**：新增 `cleanup_abandoned_temp()`——扫描 staging 下无 submissions 记录的临时目录（已提交目录跳过，走过期归档流程），超时（`TEMP_FILE_HOURS`，.env 可配，默认 24h）直接删除、不归档、不记审计（从未入库）；每天 2:10 定时执行；`POST /api/admin/cleanup-expired` 手动 API 合并返回（cleaned + tempCleaned + message_en 双语）。
  4. **文档体系单源化**：新建 `docs/ADR.md` 为全部 ADR 唯一权威文档（与 PRD 并列）；README 仅保留 ADR 索引表 + 最新落点摘要；AGENTS B4 保留关键摘要（AI 快速查阅）并指向 docs/ADR.md 全文；各文档不再重复维护 ADR 全文，只更新索引与落点。与 ADR-007（文档-only 不发布）不冲突：本决策涉及代码变更（联系人校验/临时清理），随 v2.6.3 发布；纯文档调整（README/AGENTS 瘦身）随代码发布一并生效。
- **与 ADR-011 不重叠**：ADR-011 管已入库数据生命周期（备份/恢复/重置/过期归档）；ADR-032 管未入库临时文件的系统级回收与无状态上传行为明示。
- **已落点**：v2.6.3（Windows dev 全量 TDD 380/380 通过；创建/编辑联系人必填 2 项 + 临时清理 6 项新增用例；docs/ADR.md 独立成文；README/AGENTS 引用瘦身；PRD v2.6.3 注记）。

---

### ADR-033：审计策略——系统动作审计边界（v2.6.4，强制）
- **背景**：用户审查"所有动作都有日志以便审计"时发现两类定时系统动作——① 已审批未下载的提交单超时自动归档（`cleanup_expired_files`：status approved/downloaded，从 approved_time 起算达到有效期即 os.rename 到 archive）；② 未提交临时文件超时清理（`cleanup_abandoned_temp`：无 submissions 记录的上传残留直接删除）。两类此前都只写服务端运行日志（logger），审计界面（audit_logs）看不到，审计链路不完整。
- **决策**（审计边界，按"是否涉及业务动作"划分）：
  1. **已审批未下载的超时归档 = 必须审计**（action=`system_archive_expired`，user=`system`）：该提交单已经历完整业务动作（提交→审批通过），本应由人操作下载而人未下载，系统将文件移入 archive 是**对已发生业务数据的系统保护动作**——逐单记录，detail 明示"超时归档：审批通过后 N 天未下载/未处理，达到有效期 M 天"，target=提交单 id。
  2. **未提交临时文件清理 = 不写审计**（维持原结论）：临时文件从未入库、从未产生提交单/审批等业务动作，纯存储残留清理——只记运行日志（防遗漏、可追踪清理是否完成），不产生审计记录。审计界面查 `system_cleanup_temp` 恒为空即为预期。
  3. **管理员手动触发清理 API = 必须审计**（action=`admin_cleanup_manual`，user=操作者）：管理员动作一律留痕，detail 含过期归档/临时清理计数；逐单明细由 `system_archive_expired` 承担，不重复。
  4. 统一原则：**审计覆盖"用户/管理员动作 + 涉及业务数据的定时系统动作"；纯垃圾/临时清理不审计**（属于运维运行日志范畴）。
- **与 ADR-011 不重叠**：ADR-011 管数据生命周期功能（备份/恢复/重置）；ADR-033 管审计留痕策略（哪些系统动作进审计）。
- **已落点**：v2.6.4（Windows dev 全量 TDD 384/384 通过；新增 4 项断言：超时归档留痕+detail 含"超时归档"、手动清理留痕、临时清理不写审计反向断言；定时 2:00 归档 + 2:10 临时清理 + 手动 API 行为一致）。

---

### ADR-034：有效期口径统一——文件有效期为唯一超时源（v2.6.5，强制）
- **背景**：用户对账有效期时发现三个时间点口径不一——① 上传未提交的临时文件清理（TEMP_FILE_HOURS=24h）；② 提交未审批（pending）的超时处理**此前未定义**（cleanup_expired_files 只处理 approved/downloaded，pending 永不清，存在"提交后一直挂起占空间/无终态"缺口）；③ 审批未下载已有定义（approved_time + 系统配置有效期）。用户要求统一：除"上传未提交"外，其余超时都用系统管理的"文件有效期"（default_expiry_days）。
- **决策**：
  1. **有效期唯一源**：系统管理"文件有效期"（default_expiry_days，.env EXTERNAL_EXPIRY_DAYS 初始，界面可配，提交时固化到提交单 expiry_days）统一作用于两类业务超时——**提交未审批**（pending，从 submit_time 起算）与**审批未下载**（approved/downloaded，从 approved_time 起算）；超期即 os.rename 到 archive（0拷贝，终态），逐单审计。
  2. **上传未提交保持独立**：TEMP_FILE_HOURS=24h（.env 可配）只管从未入库的上传残留清理（无业务动作、不审计，ADR-033），与文件有效期不混用。
  3. **审计区分超时原因**：system_archive_expired 的 detail 按场景明示——"提交后 N 天未审批" / "审批通过后 N 天未下载/处理"。
  4. **TDD 幂等性**：审批人测试组创建前幂等清理历史 approvers 残留（中断重跑不再因重复配置 400）。
- **与 ADR-033 不重叠**：ADR-033 管审计边界（哪些系统动作进审计）；ADR-034 管超时口径（哪些状态、从何时起算、统一到哪个配置）。
- **已落点**：v2.6.5（Windows dev 全量 TDD 392/392 通过；pending 超时归档 +5 项断言（状态 archived/文件入 archive/审计留痕/detail 区分/恢复默认）；定时 2:00 统一处理 pending+approved+downloaded）。

---

### ADR-035：管理员附件审查下载 + 环境前置检查 preflight（v2.6.6，强制）
- **背景**：① 用户（管理员）需要在"所有历史提单"中审查附件（查看/下载），此前提交记录/日志只有元数据没有附件访问能力；要求仅内网可用，外网绝对不允许。② 用户反馈多轮迭代中 Windows dev / WSL test / CI 三环境频繁出现"依赖缺失 / 数据残留 / 服务未启动 / 版本不一致"，希望运行前统一检查环境并清理残留。
- **决策（附件审查）**：
  1. **新增 API** `GET /api/admin/submissions/<id>/download/<filename>`：仅 admin（role_required），任意状态提交单附件可审（pending→staging / approved·downloaded→external / rejected·archived→archive，current_path 优先 + 三目录 fallback）。
  2. **外网隔离复用现成机制**：外网面白名单（EXTERNAL_ALLOW_PREFIXES）不含 /api/admin/ → before_request 直接 403，无需新增外网判断代码（ADR-008 网络面隔离的既有保证）。
  3. **路径穿越防护**：显式拒绝含 ".." / "/" 的文件名 + basename 归一化。
  4. **审计留痕**：action=admin_download（含文件名+MD5）；不入 download_records（非接收方下载，避免污染下载统计）。
  5. **前端**："所有提交记录"详情文件清单新增"下载"列（仅 admin 可见），adminDownloadFile 用 fetch blob 下载。
- **决策（preflight）**：
  1. 新增 `infra/preflight.sh`：核心文件/脚本完整性 → Python 3.12 → 核心依赖可导入（flask/gunicorn/apscheduler/ldap3）→ 版本双源一致 → 端口占用（PORT 可配）→ 残留数据目录清理（仅显式 CLEAN_DIR 传入才删，防误删生产/开发数据）；任一 FAIL 退出 1 阻断。
  2. **接入位置**：Gitea CI（ci-check job 第一步）与 GitHub CI（依赖安装后第一步）都先跑 preflight，FAIL 即阻断；本地 WSL/Windows 可手动调用。
- **与既有 ADR 不重叠**：ADR-008（网络面隔离）为机制，本 ADR 复用其白名单实现"仅内网"；ADR-033/034（审计/超时）不涉及管理员审查动作。
- **已落点**：v2.6.6（Windows dev 全量 TDD 403/403 通过；+11 项：admin 下载 pending/archive 附件 MD5 一致、外网 403、普通用户 403、审计留痕、路径穿越、前端按钮、清理确认码；preflight 接入 Gitea/GitHub CI）。

---

### ADR-036：单一权威仓库 + 备份仓库体系（v2.6.6，架构决策）
- **背景**：用户提出仓库治理的关键技术路径选择——"保证**一个权威仓库**（各种 git 操作的工作仓库）+ **备份仓库**（GitHub，甚至本地另外一个 Gitea、或者企业的 GitLab）；每个阶段有每个阶段的主要矛盾，抓住主要矛盾聚焦处理，其他的跟随主要矛盾进行变动，形成新的动态平衡体系"。这不是一个需求，而是长期架构选型，需成文固化。
- **决策**：
  1. **单一事实源（Single Source of Truth）**：任意时刻**只有一个权威仓库**承载全部 git 工作操作（push / 分支 / 发布依据 / 生产 CD 触发）；其余仓库一律是**备份 / 分发 / 协作**角色，不构成第二权威（避免分叉）。
  2. **权威仓库 = 本地 Gitea**（openwrtadmin/SecureTrans，内网封闭自持）：生产 CD 只从权威仓触发，生产 SSH 凭据仅存权威仓 Secrets，**备份仓永不接触生产**（ADR-021 边界 + docs/14 执行手册）。
  3. **备份仓库三职责**：① 容灾（本地权威丢失可完整恢复）；② 分发/协作（未来开源、团队协作出入口）；③ 独立验证（GitHub CI-TDD 全量门禁 + CD-SIM 本地 Docker 仿真，生产零影响）。
  4. **主矛盾驱动 + 动态平衡**：每个阶段聚焦该阶段的主要矛盾，权威/备份布局随主矛盾调整、跟随变动，形成新的动态平衡——不追求一次性"完美架构"（与 ADR-007 stepping-stone、ADR-014 渐进发布一致）。当前主矛盾 = 内网封闭 + 快速迭代验证 + 生产安全；PMF/开源阶段主矛盾将转为协作与扩散，届时权威可切换（见 6）。
  5. **同步机制按需演进**：当前 = 方案 1（git 双推，Gitea 权威 → GitHub 备份）；规模化后可切 Gitea 内置 push/pull mirror（自动推送/拉取，免手动）；将来若以 GitHub 协作为主，切"GitHub 权威 + Gitea pull-mirror 分发"，本地 CD 仍可保留；**严禁双权威双向写**（分叉风险最高）。
  6. **切换权威的触发条件**（与主矛盾一致）：公开开源 / 团队主要协作点移到 GitHub / 本地数据中心不可用——任一发生即评估切换；切换是配置与镜像方向的变更，不涉及代码改造。
- **与既有 ADR 不重叠**：docs/14 为执行手册（具体命令、凭据、首验记录），本 ADR 为架构原则（权威/备份/主矛盾/动态平衡）；ADR-021 管生产 CD 安全边界；ADR-032 管文档体系单源化（本决策本身遵循"ADR 唯一权威 + README/AGENTS 引用"）。
- **已落点**：v2.6.6（Gitea 权威：CI #124/#125 success → Release v2.6.6 4 资产 → CD #126 → 生产 v2.6.6/beta/ok；GitHub 备份：CI-TDD #3/#4/#5 success + CD-SIM #2 success → 仿真 v2.6.6/sim/ok，生产零影响；双向推送脚本化）。

---

### ADR-037：环境职责分层 + 双仓 CI/CD/Release 职责对齐（v2.6.7，架构决策）
- **背景**：用户澄清并确认三件事：① 本地 WSL 测试环境与 CI 环境是否应合一（都做全量 TDD + mock 数据）；② 独立的发布环境 / 独立 CD 环境是否有必要、与 CI 隔离到什么程度；③ GitHub 与 Gitea 是否"一个 docker 跑 3 个 flow"、权限如何隔离。并据此要求：本地 Gitea 的 package job 改名 release、独立出 CI（对齐 GitHub 命名与职责），全程跑通验证后发布新版本作为验证。
- **决策（环境职责分层，不加第四类物理环境）**：
  1. **测试层合一**：本地 WSL 测试环境 ≈ CI 环境（都做全量 TDD + mock），合一合理——WSL 本机不再单独全量跑（ADR-026），CI 每次全新容器承接全量回归；两者不再拆开。
  2. **发布层"逻辑/权限隔离"而非"物理独立"**：发布是动作不是环境——打包产物（md5/sha256、版本绑定）与测试共享同一 runner 池，业界（GitHub Actions / GitLab CI / semantic-release）均为"同一池子、独立 job、最小权限"；小团队 + 副业项目不新增发布专用物理环境（避免过度工程）。
  3. **CD 层目标环境物理隔离**：两个 CD 目标都必须是独立环境——① 生产 10.10.30.8（真实部署，只读冒烟 ADR-017/024）；② GitHub CD-SIM（云端一次性仿真，备份仓永不触生产 ADR-021/036）。
- **决策（CI / Release / CD 职责分离，与 GitHub 完全一致）**：
  1. **CI = 完整质量门禁**：preflight + 静态检查 + 全量 TDD + mock 数据（ci.yml / CI-TDD）。
  2. **Release = 只做发布**：生成 offline-deps → package.sh 打包 → 产物完整性校验 → 创建/上传 Release（不含任何验证步骤，验证归 CI）。
  3. **CD = 只做部署**：Gitea cd.yml（release published → SSH 生产部署）；GitHub cd-sim.yml（release published → 云端 Docker 仿真）。
  4. **Gitea 拆分落地**：`.gitea/workflows/ci.yml` 只留 ci-check（完整门禁）；原 package job 独立为 `.gitea/workflows/release.yml`（job 名 release，触发 push tag v*，仅打包+校验+上传）；`.gitea/workflows/cd.yml` 不变（release published 触发）。触发链：CI（push/tag 并行完整门禁）→ Release（tag）→ CD（release published）。
- **决策（权限隔离机制，双仓一致）**：
  1. **Secret 最小作用域**：RELEASETOKEN 仅注入 release job；CD_SSH_KEY 仅注入 cd job；ci job 无任何写凭据。
  2. **令牌最小权限**：GitHub release.yml 显式 `permissions: contents: write`（仅该 workflow 生效）；Gitea 用 repo secret + API token 作用域。
  3. **每 job 全新执行环境**：GitHub 每 job 一个临时 ubuntu VM（自带 docker，job 结束销毁）；Gitea 每 job 从 securetrans-ci:3.12 镜像拉起全新容器实例——前 job 的环境变量/文件/凭据零残留。
  4. **事件触发链权限上下文**：push（CI，只读）→ tag（Release，写 Release）→ release published（CD，生产凭据）——不同事件不同权限上下文，天然逐级收敛。
  5. **澄清"一个 docker 跑 3 个 flow"不成立**：双仓均为"每 job 独立执行环境"，非常驻容器依次跑 3 个 workflow；容器/VM 生命周期即隔离边界。
- **决策（环境即代码）**：CI/CD 的 Python 3.12 由官方基础镜像 `FROM python:3.12-slim` 提供（GitHub .github/docker/Dockerfile.sim 在线装依赖；Gitea infra/docker/Dockerfile 离线 wheelhouse + /venv），**免手工安装 Python**；唯一例外是生产裸机（Rocky 8.10 systemd，deploy.sh + offline-python RPM）。升级 Python/依赖 = 改 FROM 行 + 重建镜像 + 重新生成 wheelhouse（pip download --python-version NNN）+ 同步生产 RPM——环境即代码，升级是改一行 + 重建。
- **决策（Dockerfile 位置保持 infra/docker/）**：Gitea 对 Dockerfile 位置无默认约定（workflow 目录 .gitea/workflows/ 有约定，Dockerfile 是构建时 -f 指定）；移动 .github/docker 与 infra/docker 无收益且破坏既有引用（ci.yml 构建命令、release.yml -r 路径），保持原样。
- **与既有 ADR 不重叠**：ADR-016/017/018/019/020/021（CI 分层/容器隔离/环境角色）为运行机制，本 ADR 为职责划分与对齐决策；ADR-036 管仓库权威/备份，本 ADR 管环境职责与 flow 命名对齐；ADR-007 管发布策略。
- **已落点**：v2.6.7（Gitea 权威：ci.yml 仅 CI #137/#138 success → release.yml 独立发布 Release v2.6.7 4 资产（31.05MB+md5+sha256+offline-deps）→ cd.yml #139 → 生产 v2.6.7/beta/ok；GitHub 备份：CI-TDD #14~#18 success → RELEASE #3/#5 success（云端构建 4 资产）→ CD-SIM #6 success（云端 Docker 仿真 + 版本断言 v2.6.7）。**关键修复（GitHub 保护机制）**：GITHUB_TOKEN 创建的 Release 不触发 release 事件（防递归）→ release.yml 末尾显式 `gh workflow run cd-sim.yml -f version=<V>`（permissions 加 actions: write + GH_TOKEN），CD-SIM 支持 workflow_dispatch inputs.version 做版本断言；双仓 flow 命名对齐：Gitea package→release）。

---

### ADR-038：Docker 一站式交付 + 蓝绿部署验证 + Registry 分发策略（v2.7.0 RC 启动，架构决策）【阶段命名与决策 2 已被 ADR-039 修订】
- **背景（问题与场景）**：进入 RTM 阶段前，用户复盘从零部署生产的完整成本——新建 Rocky 8.10 虚拟机 → 临时开防火墙到 mirror → dnf 下载开发环境 → **手工编译 Python 3.12 venv** → pip 装依赖 → 手工传包解压 → deploy.sh/verify.sh → 手工改 .env（.env 不入包）→ 配置 AD/审批人/密码 → 才进入 alpha/beta。结论：**即使有 AI 指导，很多步骤（网络、防火墙、本地 .env）AI 不能代做，一般运维工程师没有耐心做这种部署**；诉求 = **发布时同时提供 Docker 方案，一条命令部署运行，功能性能一步到位**。同时用户提出三个疑问：① 本地是 Rocky 10 / Ubuntu 24.04 WSL，能否构建目标为 Rocky 8.10 的镜像？② 只提供 Dockerfile（部署环境自建）还是 compose？③ 运行是否必须 Rocky 8.10，还是任何 Linux？担心不同发行版差异导致需要维护多个镜像。
- **原理澄清（决策依据）**：容器 = **共享宿主内核 + 镜像内完整用户态**。① 构建产物与构建机器/目标发行版解耦——任何有 Docker 的 Linux 都能构建同一个镜像（构建时 apt/dnf 装的是镜像内依赖，不碰宿主）；② 容器只依赖宿主**内核 ABI**（不是宿主 glibc/发行版）——关键兼容参数 = 镜像内 glibc 的最低内核要求 vs 宿主内核版本：`python:3.12.11-slim-bookworm`（Debian 12，glibc 2.36）最低内核 3.2；Ubuntu 24.04 基础镜像（glibc 2.39）最低内核 3.2（x86-64）；**生产 Rocky 8.10 内核 4.18 >> 3.2 完全兼容**；反向（旧 glibc 镜像跑新内核）同样兼容。真正风险仅限容器程序调用新内核专有 syscall（本系统无）。**这就是"一个镜像，处处运行"的依据——Docker 设计上消除了"为每个发行版维护一个镜像"的问题**。
- **备选方案与对比**：
  - **镜像基础**：① `python:3.12.11-slim-bookworm`（采纳）——官方预编译 3.12、镜像小、glibc 2.36 与 CI 镜像同源；构建时实测 `python:3.12-slim` 浮动 tag 已漂移到 trixie/Debian13（glibc 升级有内核要求不确定性）→ **固定 bookworm 防漂移**。② `rockylinux:8` + dnf python3.12（备选，与生产 glibc 2.28 完全同源，最"原生"，但镜像大、维护重、需 EPEL/AppStream 处理）。③ trixie/Debian13（否决，glibc 升级引入不必要不确定性）。**当前采纳 ①，若后续遇兼容问题切 ②**（决策 1）。
  - **Gitea 镜像构建路径**：① kaniko 无特权（采纳）——release job 在容器 label 内，kaniko 静态二进制可直接构建+导出 tar，无需 docker daemon/特权/双 label。② 挂 docker.sock（否决——引入宿主逃逸面、需改 runner 配置、违背单 label 归一化）。③ 宿主 label 构建（否决——双 label 回归）。④ 手工本地构建传资产（过渡可用，不自动化，否决为长期方案）。
  - **GitHub 镜像分发通道**：① GHCR（采纳）——GitHub 原生 OCI registry，账号即 registry 账号（零注册/OAuth 打通），Actions 内 GITHUB_TOKEN 自带 packages:write，public 免费。② Docker Hub（对比——public 免费但限拉取、需单独 Docker 账号、与 GitHub 无 OAuth）。③ Quay.io（对比——Red Hat，public 免费）。④ 阿里云 ACR 个人版（对比——国内加速场景）。**GitHub 生态首选 GHCR**。
  - **交付形态**：① Registry + Release 附件双通道（采纳）——在线 `podman/docker pull`，封闭数据中心 `docker load < image.tar.gz`（第 5 资产离线兜底）。② 仅 Registry（否决——封闭数据中心无外网拉取）。③ 仅 Release 附件（否决——非业界主通道，缺少 OCI 标准分发）。
- **决策 1（镜像基础：python:3.12.11-slim-bookworm）**：ABI 兼容归一化 + 镜像最小（实测 304MB）；固定 bookworm 防浮动 tag 漂移；后续遇兼容问题切换 `rockylinux:8` 同源。
- **决策 2（Gitea 自动化镜像构建：kaniko 无特权）**：release job 内 kaniko 静态二进制 `--tar-path` 导出 OCI 镜像 tar → gzip 为 `securetrans-vX.Y.Z-image.tar.gz` 作为 Gitea Release 第 5 资产（+md5/sha256）；不引入 docker.sock、不改 runner 特权、不恢复双 label；用户已授权安装使用 kaniko。**【2026-09-15 已被 ADR-039 正式替代**：kaniko 在本地宿主构建 Debian apt postinst 失败（GLIBC_2.38 混入）、--use-new-run 卡死；改为容器内 docker CLI + 宿主 docker.sock，见 ADR-039 决策 1】**
- **决策 3（蓝绿部署验证：Docker 18000 共享生产数据）**：生产 10.10.30.8 保持原生 systemd 8000 不动；Docker 容器 18000（宿主端口映射 18000→容器 8000），**直接映射当前全部持久化数据/文件路径**（SECURETRANS_DATA=/opt/securetrans/data、NAS_ROOT=/mnt/nas/securetrans）。同网段走通后正式切换 Docker 为唯一部署形态。**为什么 RTM 而非正式 release 做**：当前仅 2 个 beta 用户，风险小可控；最坏情况 = 道歉 + 重置生产与程序（尽量避免）；业务全量上线后共享数据的蓝绿必须更谨慎。**数据丢失/不一致本身视为一次部署验证机会**。
- **决策 4（数据卷映射宿主目录）**：与裸机路径完全一致，Docker 与原生两条路线**数据可互换、可回退**。
- **建议 1（直接用当前部署环境）→ 实证结论**：生产检查 = Rocky 8.10（内核 4.18.0-553）/ **podman 4.9.4-rhel 已预装**（Rocky 8.10 原生自带，docker 命令兼容、systemd 集成、无 daemon）/ Docker 未装亦**无需装** / SELinux Disabled / firewalld inactive（数据中心防火墙管控）/ 磁盘 255G 可用 / 内存 7.5G / /mnt/nas/securetrans 三目录就绪 / 原生 gunicorn 8000 运行中。**结论：即插即用，零安装**——比预期（需装 docker）更简单。
- **建议 2（端口分离 + 逐步切换）**：18000 与 8000 分离；同网段验证通过后切换；用几次迭代验证"一站式部署运维"目标。
- **建议 3（Registry 分发：GHCR 为标准，image.tar.gz 为离线兜底）**：详见"GitHub 镜像分发通道"对比；本 ADR 落地 = Gitea Release 保留第 5 资产（封闭内网离线 load），GitHub 走 GHCR push（在线 pull），两者并存。
- **实施与验证实证（本 ADR 决策已落）**：
  1. `infra/docker/Dockerfile.run`（FROM python:3.12.11-slim-bookworm；ldap-utils=AD 查询命令行，Debian 包名对应 RHEL 系 openldap-clients；curl/procps；离线 wheelhouse 装依赖；非 root uid 1000；/data /nas 卷）。
  2. `infra/docker/compose.yaml`（蓝绿 18000→8000；env_file=/opt/securetrans/.env；卷映射与裸机一致）。
  3. `infra/docker-deploy.sh`（一条命令：load→run→health→只读冒烟；podman/docker 自动识别）。
  4. 本地 WSL docker 构建验证：**镜像 304MB；容器 health v2.6.7/production/ok；admin 登录通过；ldapsearch 已装；gunicorn 非 root 运行**。
  5. 清理历史遗留：Windows Docker Desktop 旧 `securetrans-sim` 容器（占 18000，上轮"待退役"项）已删；WSL 内 securetrans 手工部署进程保留（用户环境）。
  6. **RC 启动（v2.7.0，ADR-039 修订为 RC 而非 RTM）**：Gitea release.yml 加镜像构建（kaniko→ADR-039 改容器内 docker CLI + 宿主 sock）；GitHub release.yml 加 GHCR push（GITHUB_TOKEN 认证，permissions packages:write）；**原生裸机发布/release 形态不变**；**Gitea 保留 image.tar.gz，GitHub 不传 img 只用 GHCR**；从 v2.7.0 起进入 RC。
- **与既有 ADR 不重叠**：ADR-037 管双仓 flow 职责对齐（本 ADR 在其上新增镜像资产与 registry 通道）；ADR-016 管 12-Factor 配置（复用 env 抽象做卷/端口映射）；ADR-008 单网卡方案不变（容器内单端口 + 网络面白名单）；ADR-020/021 容器隔离与生产边界（蓝绿共享数据是**有意的受控风险**，beta 期 2 用户，非生产常规）。
- **已落点**：v2.7.0 RTM 启动（kaniko 构建 + GHCR push + 第 5 资产 + 生产 18000 蓝绿验证，实施见 Gitea/GitHub workflow 与验证记录）。
- **实证落点（2026-09-15，v2.7.0 RC 蓝绿全链路验证）**：
  1. **本地 WSL（rocky10-ci）docker 全量 TDD 403/403 通过**：镜像 `securetrans:v2.7.0` 容器 18000:8000 + 卷映射（`.data/.nas` 宿主目录）+ mock AD，`BASE_URL=http://127.0.0.1:18000` 全量回归 100%；测试数据挂载到宿主目录（test_api.py 需直接 `os.utime` staging 文件）——**TDD 对容器版要求卷映射，不能只跑容器内 API 形态**。
  2. **生产蓝绿部署成功（10.10.30.8）**：`bash infra/docker-deploy.sh /opt/securetrans-release/securetrans-2.7.0-image.tar.gz 18000` → podman load（tag `securetrans:v2.7.0`）→ 容器 `securetrans-docker` 18000:8000 → health `v2.7.0/rc/ok/production` → 容器内可见共享数据（external=34/staging=21）；原生 systemd 8000 不受影响（蓝绿隔离）。
  3. **实测发现 1——env 内联注释 vs docker env-file**：`env/test.env`（及 dev 模板）含 `KEY=value  # 注释`，docker `--env-file` 不支持内联注释（bash source 支持），导致 `int(os.environ[...])` 解析失败。**生产 .env 已验证干净（0 内联，37 行首注释）不受影响**；dev/test 模板用于 docker 时需清洗（`sed -E 's/[[:space:]]+#.*$//'`）。
  4. **实测发现 2——容器 uid 与宿主数据属主不匹配**：镜像内用户固定 uid 1000（Dockerfile useradd -u 1000），生产 `securetrans` 用户 uid=973、NAS 数据属主 973 → 容器 uid1000 无法写。**决策：docker-deploy.sh 自动检测宿主数据目录属主并以 `--user uid:gid` 运行容器**（非 root、不 chown 生产数据、不重建镜像）；实测 `--user 973:972` 全量 TDD 与写权限通过。
  5. **实测发现 3——镜像 tag 与默认值不匹配**：image.tar.gz 包内 tag 为 `securetrans:v2.7.0`（非 `securetrans:latest`），脚本默认 `securetrans:latest` 导致 run 失败。**决策：docker-deploy.sh 从 load 输出自动解析实际 tag**（`SECURETRANS_IMAGE_TAG` 可显式覆盖）。
  6. **并发写提醒（ADR-038-3 既定策略）**：18000 容器与 8000 原生共享 SQLite DB + NAS——验收期低并发可接受（beta 期 2 用户），**验收通过后必须停其一**（切 Docker 正式形态则停 systemd 原生，或回退则停容器），避免 SQLite 并发写锁。
---
### ADR-039：kaniko 废弃 → 容器内 docker CLI + 宿主 docker.sock / WSL 环境重建 / v2.7.0 定为 RC（v2.7.0，架构决策修订）
- **背景（问题与实证）**：ADR-038 决策 2 选定 kaniko 无特权构建，实施时实证失败：
  1. **kaniko 双版本失败**（v1.23.2 / v1.24.0）：在本地 WSL 宿主（真实身份 = Debian bookworm，glibc 2.36）上构建 `python:3.12.11-slim-bookworm` 的 apt postinst 时，`ca-certificates`（rehash）与 `procps`（update-alternatives）报 `GLIBC_2.38 not found`——kaniko 默认 RUN 实现把宿主要求 2.38 的库（libacl 等）混入镜像 rootfs 执行环境；`--use-new-run`（experimental）实测卡死 10+ 分钟无产物；同一 Dockerfile 用 `docker build`（runc 完整隔离）成功——**缺陷在 kaniko 的 run 隔离，与 Dockerfile 无关**。kaniko GitHub release 无二进制资产（v1.23.2/v1.24.0 均仅容器分发），固化 executor 到 CI 镜像亦不解决。
  2. **宿主工具链污染诊断**（决定性）：rocky10-st 表面叫 "rocky10"，实为 **Debian bookworm + 混入 Rocky EL10 库**：`systemctl` 链接 `/usr/lib64/systemd/libsystemd-shared-257-13.el10.rocky.0.1.so`（要求 GLIBC_2.38/2.39 + OPENSSL_3.4.0）；`git` 为手工放置的要求 GLIBC_2.38 二进制；`iptables` 缺 libxtables.so.12 / libmnl.so.0；dpkg 残留 half-configured（ca-certificates/procps）。**连锁后果**：docker daemon 无法创建容器网络（iptables DROP 规则失败）→ 连 docker build / CI 容器 job 都不可用 → 环境不可逆损坏。
- **决策 1（Gitea 镜像构建：放弃 kaniko → 容器内 docker CLI + 宿主 docker.sock）**：release job 仍用 `securetrans-ci` 容器 label（单 label 归一化不变），但 CI 镜像内置 **docker-ce-cli**（Docker 官方 bookworm 源，静态 CLI，轻量），act_runner `container.options: -v /var/run/docker.sock:/var/run/docker.sock` 挂载宿主 socket → 容器内 `docker build` 调 **本地 WSL docker daemon** 执行（runc 完整隔离，与 `docker build` 语义完全一致，无 kaniko 快照/glibc 缺陷）。**docker.sock 逃逸风险按"可信代码模型"接受**：CI 容器代码 = 本仓库代码（非第三方不可信内容），与 GitHub Actions 挂 docker 的业界实践一致；生产 CD 凭据仍在 cd.yml 最小作用域，不经此路径。
- **决策 2（WSL 环境重建：rocky10-ci 新 distro）**：授权重建——用 `D:\iso\Rocky-10-WSL-Base-10.1-20251116.0.x86_64.wsl` 导入新 distro `rocky10-ci`（真实 Rocky Linux 10.1，glibc 2.39，干净环境），承载 docker daemon + act_runner + securetrans-ci 镜像；旧 `rocky10-st` 保留作回滚（不删除）。重建后重配：dnf 装 docker-ce / 拷贝 act_runner（v3.4.2）+ `.runner` + `config.yaml`（含 sock 挂载）/ 构建 `securetrans-ci:3.12`（wheelhouse 自 packages 解压）。
- **决策 3（阶段命名：v2.7.0 = RC，非 RTM）**：用户明确"本次不能叫 RTM，改为 rc（Release Candidate）"——生产 `.env` 的 `APP_STAGE=rc`；Release body 标注 RC；RTM 延后至 RC 验证通过后另行发布。
- **与既有 ADR 不重叠**：ADR-020（双 label / 容器 CI）——本次明确 release 亦走容器 label + sock（宿主 label 因环境损坏不可用，且更干净）；ADR-037（flow 职责对齐）不变；ADR-038 决策 2 被本 ADR **正式替代**（kaniko 路径废弃）。
- **已落点**：2026-09-15 v2.7.0（RC）：act_runner config.yaml 增 `container.options` 挂 sock 并重启生效（v3.4.2 已 declare labels: [securetrans-wsl securetrans-ci]）；CI 镜像 Dockerfile 改 docker-ce-cli（去 kaniko COPY）；release.yml 改容器内 docker build + docker save；rocky10-ci 新 distro 导入（Rocky 10.1 glibc 2.39）；双端 workflow 同步。详见 Gitea/GitHub Actions runs 与部署记录。
---
*文档结束 | SecureTrans ADR 全录 | 2026-09-15*
### ADR-040：act_runner 脱离 systemd → nohup 直跑 + 无窗口保活（v2.7.0 RC，运行稳定性修复）
- **背景**：rocky10-ci 重建后（ADR-039），act_runner 以 systemd service（Restart=always）常驻，但出现**周期性崩溃**（18:15→18:32→18:38→18:52→19:00→19:07 共 6 次，间隔 6-17 分钟），正在执行的 CI job 中断。诊断三层取证：
  1. **非内核重启**：/proc/uptime 连续（469133s，VM 未重启）；
  2. **systemd 整体重置**：journalctl --list-boots 仅 boot 0 且 FIRST ENTRY 随每次重置刷新、/run/systemd/system mtime 更新、journal 显示 systemd[524] Startup finished——**WSL 中 systemd 非 PID 1，是 Microsoft init 的子进程，被 WSL 空闲终止机制周期关闭**；
  3. **网络核实（Microsoft 官方）**：WSL release notes 明示"实例终止超时 = 最后 WSL 进程退出后 15 秒"；Microsoft Learn 建议"需要一个 Microsoft init 的子进程（如交互 shell）保持 WSL 不被 idle-terminating"，后台 daemon 不算活跃（microsoft/WSL#8854、#13416）。
- **决策**（双保险，与 ADR-021 互补）：
  1. **Windows 计划任务无窗口保活**：新建 WSL-Rocky10-CI-KeepAlive（schtasks，每 1 分钟 wscript.exe wsl-keepalive-rocky10-ci.vbs，VBS 内 Wscript.Shell.Run "wsl.exe -d rocky10-ci -- sleep 45", 0, False）——隐藏窗口执行（规避 ADR-021 当年"每 1 分钟弹窗"问题），使 WSL 始终存在活跃进程、不被空闲终止。
  2. **act_runner 脱离 systemd → nohup 直跑**：systemctl disable --now act_runner 后 
ohup act_runner daemon --config /opt/securetrans/config.yaml > /var/log/securetrans/act_runner_nohup.log 2>&1 &——act_runner 成为 WSL init 直接子进程，systemd 崩溃不再连带；与保活组合：保活防 VM 空闲终止，nohup 防 systemd 崩溃连带。
  3. **开机自启**：nohup 进程在 VM 生命周期内持续；若 Windows 重启，需手工/登录计划任务拉起（已记录，后续按需补 onlogon 任务）。
- **实证**：修复前 act_runner 6-17 分钟必崩；修复后（保活 + nohup）连续 5 分钟+ 无重启，systemd 亦未再重置。故障 job 幂等 rerun 即可恢复。
- **与既有 ADR 不重复**：ADR-021 为 rocky10-st 时代"WSL 空闲终止→保活计划任务（因弹窗删除）"记录；本 ADR 为 rocky10-ci 新环境落地：无窗口 VBS 保活 + nohup 脱离 systemd（双保险），并补充"WSL systemd 非 PID 1、被 init 空闲关闭"的新诊断。
- **已落点**：2026-09-15 v2.7.0 RC；计划任务 WSL-Rocky10-CI-KeepAlive + C:\Users\jinta\.securetrans\wsl-keepalive-rocky10-ci.vbs + nohup 启动 act_runner；release #156 在修复后 rerun 执行中。
---

### ADR-041：v2.7.0 双通道发布回归修复（release.yml 版本提取 + cd.yml MD5 资产歧义，v2.7.0 RC）
- **背景**：v2.7.0 首次双通道发布（原生包 + docker 镜像第 5 资产）暴露两个回归，均源于**新资产改变了原有单值假设**：
  1. **release.yml 通配歧义**：上传/校验步骤用 `PKG=$(ls packages/securetrans-*.tar.gz | head -1)` 选主包——镜像步骤新增 `securetrans-2.7.0-image.tar.gz` 后，ls 字母序 i<t 使 head -1 选中镜像包 → V=2.7.0-image → Release 被创建为错误 tag `v2.7.0-image` 且主包（+其 md5/sha256）完全丢失。线上实证：Gitea 出现错误 Release `v2.7.0-image`（仅 4 镜像资产）。
  2. **cd.yml MD5 选择器歧义**：`select(.name|endswith(".tar.gz.md5"))` 同时匹配主包 md5 与 `-image.tar.gz.md5` → jq 输出两行 → curl URL malformed（exit 3）→ CD 部署失败。
- **决策**：
  1. **版本号单一来源**：所有步骤 V 一律从 src/app.py 的 APP_VERSION 精确提取（与 Docker 镜像构建步骤一致），禁止从文件名通配反推（文件名非权威源，且随资产演进不可靠）。
  2. **资产精确匹配**：主包用 `securetrans-${V}.tar.gz`（精确等于），md5 用 `securetrans-${V}.tar.gz.md5`（精确等于），不再用 endswith 宽松匹配。
  3. **回归教训固化**：发布链路任何"新增同前缀资产/文件"改动，必须同步审计所有通配/前缀匹配（grep head -1 / endswith / *.tar.gz），并跑通一次端到端 Release→CD 验证。
- **与既有 ADR 不重复**：ADR-039/040 管环境与运行机制；本 ADR 管发布链路数据流正确性（版本提取与资产选择）。
- **已落点**：2026-09-15 v2.7.0 RC：commit 16cab42（release.yml 修复，Gitea run #241 success → 7 资产齐全：主包+md5+sha256+offline-deps+image.tar.gz+md5+sha256）；commit 5dc748a（cd.yml 修复，Gitea CD run #244 success → 生产 10.10.30.8 v2.7.0 部署+只读冒烟通过）；GitHub 平行 RELEASE+CI-TDD+CD-SIM 全绿；错误 Release/tag（v2.7.0-image）已清理。
---

### ADR-042：AI 访问外部系统认证——token 优先（token > ssh >> 账号密码）+ 本地 credential 文件不入库（强制，方法论）
- **背景（问题与实证）**：AI Agent 频繁认证访问外部系统（Gitea / GitHub / GitLab / registry 等）做 push、API、Release、镜像分发。早期直接使用账号密码认证引发实际问题：① **Git Credential Manager 账户选择弹窗**——本机凭据管理器同时存在 `x-access-token` 与 `ai-age-justforfun` 两个 GitHub 账户凭据，git push 时不确定选谁而弹窗阻塞（用户多次被"Select an account"打断，git 命令挂起等待）；② **账号密码明文本地保存**风险高于最小权限 token；③ 凭据分散、无统一目录与命名规范，AI 换环境后找不到凭据。
- **决策（认证优先级与凭据管理规范）**：
  1. **优先级：token（PAT）> SSH key >> 账号密码**。首次访问某系统时，用账号密码登录系统**一次性创建** PAT 或 SSH key；创建完成后**后续一律不再使用账号密码**认证（账号密码不出现在任何脚本/URL/配置中）。
  2. **本地 credential 文件**：token/密钥存放于**版本管理目录（git/svn 仓库）之外**的专用目录（本项目 `~/.securetrans/`，即 `C:\Users\jinta\.securetrans\`），命名按业界惯例 `gitea-token.txt` / `github-token.txt` / `gitlab-token.txt` / `github-token-clean.txt` 等；**严禁将凭据文件或内容合入版本管理**（.gitignore 保护，仓库内只允许引用"从本地 credential 文件读取"的过程说明，不存值）。
  3. **token 权限最小化**：按用途创建最小 scope（如 GitHub `contents:write`+`packages:write` 用于 Release/镜像、只读 scope 用于查询），不用全部权限 token 做只读操作；**不使用账号密码生成硬编码 URL 认证**（如 `https://user:pass@host`）。
  4. **避免弹窗/多账户歧义**：本机 git 固定 `git config --global credential.https://<host>.username <账号>`，凭据管理器按用户名直接匹配已存 token 凭据，不再弹账户选择；多账户凭据（如 Actions 的 `x-access-token`）清理或忽略。
  5. **与 CI/CD secret 分离**：服务端凭据（CD_SSH_KEY、RELEASETOKEN 等 repo secret）只注入 CI/CD job 容器，**本地 credential 文件与 repo secret 两套体系互不混用**（本地=AI 开发侧，secret=流水线侧）。
- **与既有 ADR 不重复**：ADR-009 管业务系统内 admin 密码（RESET_PASSWORD 全链路）；ADR-024 管 CD 的 SSH 认证（ed25519 密钥走 repo secret）；ADR-037 管 CI/CD secret 最小作用域。**本 ADR 管 AI 开发侧的本地凭据管理**（外部系统认证的创建/存放/优先级/防弹窗），是方法论层规范，可复用于后续项目。
- **已落点**：2026-09-15（v2.7.0 RC 期间）——GitHub PAT 存 `C:\Users\jinta\.securetrans\github-token.txt`（带标题注释行，使用时 regex 提取 `ghp_...`）；Gitea API token 存 `~/.securetrans/`（origin remote URL 引用）；v2.7.0 draft Release 发布/阶段调整（alpha/beta/rc）全部通过 token API 完成（无账号密码）；git 固定 `credential.https://github.com.username = ai-age-justforfun` 消除弹窗；后续新系统（GitLab 等）按本 ADR 执行。
- **补充（2026-09-16，credential 文件读取约定，强制）**：**从 credential 文件读 token 必须先核对行结构与前缀，禁止盲取第一行**——本项目 `github-token.txt` 结构=**L0 标签行（`github-token: ...`，勿当 token）+ L1 才是真 token（`ghp_...` classic，40 字符）**；本次事故=误取 L0 标签行致 API Bad credentials，实际 token（`securetrans-ci`，scope=repo,workflow）一直有效。读取规范：① 逐行 Trim 后按前缀识别（`ghp_`/`github_pat_`/`glpat-` 等 token 特征），取**首个匹配 token 前缀的行**；② 标签行/注释行（含 `:`、中文说明、`#`）跳过；③ 读取后用 API 快速验证（`GET /user` 200）再使用；④ 写入凭据管理器用真 token 行，防"存了错值弹窗歧义"。已修正凭据管理器并验证（非交互 ls-remote 通过）。
- **补充（2026-11-27，"两处存放"边界，强制）**：外部系统凭据只允许存在于**两处**——①开发机本地（`server_credential.md` 与 `~/.securetrans/`，均 gitignore 保护）；②受控服务端 `.env`（如通知网关 `/opt/.../.env`，权限 600）。**禁止第三处**（业务机、git 仓库、CI 明文变量、聊天/工单/邮件）。本次落点：`server_credential.md` 入库前先加 `.gitignore` 规则 `server_credential*.md` 并 `git check-ignore` 验证通过，再提交（提交 `48fce2b` 只含规则，不含凭据本体）。
---

### ADR-043：部署形态正式切换——Docker 为默认形态、原生退役为备选 + 蓝绿切换顺序纪律（v2.7.0 RC，强制）
- **背景**：Docker 蓝绿验收完成（18000 验证 docker 形态：health/只读冒烟通过），用户验收后决策——**后续新版本默认改为 docker 部署，除非强制要求，否则不再推送原生部署**。切换中发现并纠正三处关键问题：① 蓝绿两实例**共享同一 SQLite/NAS**（ADR-038 已记录），曾误以"先起容器、后停原生"顺序执行，存在双实例并发写窗口（虽最终状态正确，但顺序违反数据安全）；② 容器内 ENV_ROLE 被 docker-deploy.sh 默认覆盖为 `production`，与 .env 的 `prod` 不一致，导致冒烟 health 断言失败；③ 冒烟从 127.0.0.1 访问被判外网面（不在 INTERNAL_CIDRS）→ 管理接口 403（安全设计的正确行为，但冒烟需从内网 IP 执行）。
- **决策**：
  1. **正式形态 = Docker（podman）容器 `securetrans-docker` 监听 8000**；原生 systemd 退役（stop + disable），`deploy.sh` 保留为回退/首次引导通道；**后续新版本 CD 部署改为 docker 通道**（cd.yml/cd-deploy.sh 指向 docker-deploy.sh，原生部署仅强制要求时使用）。
  2. **切换顺序纪律（强制）**：蓝绿两实例**严禁同时运行**（共享 SQLite 并发写）；正确顺序 = **先停原生 8000 → 再部署/启动容器**；回滚 = 先停容器 → 再启原生。18000 仅为蓝绿验收临时端口，验收后不保留（正式形态用 8000，用户访问/防火墙/文档地址不变）。
  3. **ENV_ROLE 尊重 .env**：docker-deploy.sh 默认从 .env 读取 `ENV_ROLE`（如 prod），`SECURETRANS_ENV_ROLE` 仅显式覆盖（本地/测试可传 test）；禁止脚本默认值覆盖生产部署配置。
  4. **冒烟视角（生产）**：只读冒烟从**内网 IP** 执行（`bash infra/smoke.sh http://<内网IP>:8000`，smoke.sh 支持位置参数 BASE_URL）；127.0.0.1 不在 INTERNAL_CIDRS → 判外网 → 管理接口 403 是安全设计正确行为，不应从 127.0.0.1 验证管理接口。
  5. **WSL 原生路径（呼应 ADR-026，强制）**：生产操作/WSL 测试/git/docker 构建**全部在 Linux 原生路径独立进行**，禁止 /mnt/c、/mnt/d（9P 转发性能差且环境不独立）；跨 Windows 传内容经 base64 写入 WSL 原生路径。
- **与既有 ADR 不重复**：ADR-038 管 docker 交付方案与蓝绿部署形态；**本 ADR 管形态正式切换的决策、顺序纪律与运维视角**（Docker 默认、原生退役、切换顺序、ENV_ROLE 尊重 .env、冒烟内网 IP、WSL 原生路径），是 ADR-038 的落点深化。
- **已落点**：2026-09-15 v2.7.0 RC——生产正式切换：原生 `systemctl stop && disable`（inactive）；容器 `securetrans-docker` 8000（--user 973:972，envRole=prod，health OK）；内网 IP 冒烟 **11/11 100%**；18000 验收容器已清除；docker-deploy.sh ENV_ROLE 修复（尊重 .env，SECURETRANS_ENV_ROLE 显式覆盖）已同步仓库。
---

### ADR-044：审计统计口径重构（四维独立计数）+ CD 正式切换 Docker 通道（v2.7.1，首个验证）
- **背景（问题与实证）**：用户报告"审计日志-统计"页面统计错误：① alpha 完成后清理过生产环境，admin 数据有误；② 其他人的文件数"感觉多计算了"；③ 普通用户本无管理操作却有统计。根因（`src/app.py` `/api/audit-logs/stats` 旧逻辑）：
  - **粗分类误判**：把所有审计行按"detail 里能否正则提取 `.ext`"分类，提取不到一律归"管理操作"——`create_submission`（detail="提交N个文件，待审批"）、`approval_*`（detail="通过，级别N"）均无文件名 → 普通用户大量业务动作被误标"管理操作"；`login/logout/改密`也计入管理操作。
  - **宽正则误吞**：`[\w.\-]+\.\w{1,8}` 会把 IP（10.10.30.8）吞成"其他文件"。
  - **文件数虚高**：同一文件全链路（upload + download + admin_download）各 +1；admin 的登录/配置/清理/测试动作全部累加为"管理操作"。
- **决策（用户明确拍板的口径）**：**四维独立计数**，每维口径单一、互不混淆——
  1. **提交文件数**：按 `upload` 动作从 detail 提取**白名单后缀**文件名（ext_map：pdf/doc/docx/xls/xlsx/ppt/pptx/zip/rar/7z/tar/gz/bz2/xz/zst/bin/bit/ltx 等；正则按后缀长度倒序，杜绝 IP/日期误匹配），按 **(user, 文件名, 日期)** 去重（同一文件同一天重传不重复 +1）；类型列顺序固定 STAT_TYPES，无则不出列。
  2. **审批次数**：`approval_*` 动作数（一级/二级审批各计）。
  3. **下载次数**：`download` + `admin_download` 动作数。
  4. **管理操作**：仅 `user in (admin, system)` 且**排除** login/login_failed/logout/change_password/create_submission 的动作；**普通用户永不出现"管理操作"列**（无该列）。
  - 前端仅更新统计标题"人员 × 类型 × 每日"（中英 + 默认文本 3 处），渲染矩阵结构不变（types 由后端自动填充），避免前端与后端口径二次漂移。
- **TDD（只增不减，ADR-018）**：tests/test_api.py 组 11 追加 5 项断言（普通用户无管理操作 / 上传 2 个新 pdf → admin PDF文档 +2 / 同名同日再传不 +1 / 审批独立计数存在 / 下载独立计数存在）；测试基线 403 → 407。
- **CD 正式切换 Docker 通道（ADR-043 首个执行版本）**：`infra/cd-deploy.sh` 重写为**形态自动检测**（存在容器 `securetrans-docker` 或原生 systemd inactive → docker 模式；否则原生回退）——docker 模式 = 校验/备份/同步程序文件与 infra/tests → 调 `docker-deploy.sh <镜像包> <port>`（内部先 rm 旧容器再起，天然满足 ADR-043 切换顺序纪律）→ 从 `hostname -I` 取内网 IP 跑完整只读冒烟（127.0.0.1 属外网面 403，只能内网 IP）；原生模式保留原 systemd 升级逻辑作为回退。`.gitea/workflows/cd.yml` 资产下载按 ADR-041 教训**精确 == 匹配**（主包 tar.gz + 主包 md5 + `-image.tar.gz` + 镜像 md5 四资产），MD5 双校验，scp 主包+镜像包两文件，汇总改查 podman ps + 内网 IP health。
- **与既有 ADR 不重复**：ADR-034 管有效期口径；ADR-035 管管理员附件审查；**本 ADR 管审计统计的可视化口径正确性**（业务动作分类 + 去重 + 白名单后缀），并承载 CD docker 通道改造的落点。ADR-040 的 act_runner 空闲终止问题在 v2.7.1 CI 期**复发实证**（WSL 空闲后 act_runner 无进程、队列积压 4 个 queued run），按 ADR-040 方式 nohup 直跑重启即恢复；后续纳入 WSL 保活监控（Windows 计划任务 VBS 已在位）。
- **已落点**：2026-09-15 v2.7.1（rc 阶段，首个 docker 通道 CD）——commit 813851d 推 Gitea main + GitHub 备份仓；WSL 容器化全量 TDD（复刻 CI：ci_test.sh 干净数据）通过（100MB 全链路 0.82s、MD5 四方一致、3 用户并发 0.68s 全过）；Gitea CI run 251（v2.7.1）→ Release → CD docker 通道 → 生产 10.10.30.8 容器 8000 内网冒烟；统计正确性由用户在内网页面人工复核（生产不跑全量 TDD，ADR-017）。
---
### ADR-045：GitLab CICD 实验线打通（gitlabcicotest，v2.7.1 rc，方法论+隔离纪律）
- **背景**：用户开通自建 GitLab（10.10.30.9，HTTP/SSH 防火墙放通、HTTPS 未启用），要求：将本项目推送新 GitLab 仓库，打通 CI/CD（gitlabcicotest 命名）；必要时新建独立 WSL Ubuntu 24.04 distro 做 CI/CD；**绝对不允许碰当前 Rocky 测试/生产环境**，用新建环境独立测试、独立部署（docker 隔离）。这是继 Gitea（权威）+ GitHub（备份/云端闭环，docs/14）后第三条平台验证线，目标是"gitlab 也发布成功"并沉淀可复用 CI/CD 迁移方法论。
- **决策**：
  1. **环境隔离（强制）**：实验线全套独立——`gitlabcicotest` WSL（Ubuntu 24.04，D:\wsl\gitlabcicotest）+ 内部独立 docker daemon + 独立数据目录 `/opt/securetrans-gitlab/{data,nas}` + 独立端口 18080（容器 8000）+ 独立 .env（prod 模板清洗 + 实验覆盖）。**与生产 Rocky 10.10.30.8 /opt/securetrans、/mnt/nas/securetrans 完全零接触**；GitLab 实验 Release 用独立 tag 记录，不影响 Gitea/GitHub 主链 tag（本地 tag 恢复主链指向）。
  2. **认证**：root 登录创建 PAT（api/read/write，存 `~/.securetrans/gitlab-token.txt`，ADR-042）；git remote URL 用 `oauth2:<token>@host`（不入库）；`GITLAB_PAT` 仓库变量（API 创建）供 release job 调 GitLab Release API。
  3. **Runner（gitlabcicotest-docker）**：gitlab-runner 19.3.3 官方二进制 + docker executor（`pull_policy = "if-not-present"` 用本地镜像，**docker executor 默认 always 会尝试拉远端 registry 导致失败**）+ volumes 挂 `/var/run/docker.sock` 与 `/opt/securetrans-gitlab`（CD 经 docker.sock 操作宿主 daemon，可信代码模型同 ADR-039）+ tag `gitlabcicotest,docker`；WSL 无 systemd → `nohup gitlab-runner run &`（同 ADR-040 经验）。
  4. **CI 镜像复用**：`securetrans-gitlab-ci:3.12` 直接复用 `infra/docker/Dockerfile`（python:3.12-slim + wheelhouse 离线依赖，offline-deps 从 Gitea 网关 172.29.112.1:3000 Release 下载解压）——**同一镜像、同一 Python、同一依赖、同一全量 TDD**（与 Gitea CI 容器完全同源，WSL 测试=CI 合一原则延伸）。
  5. **流水线职责对齐（ADR-037）**：`ci-check`（push gitlabcicotest 或 tag v*：py_compile + static_check + 版本双源 + env 键一致性 + 脚本完整性 + `bash infra/ci_test.sh` 全量 TDD）→ `release`（tag v*：wheelhouse 打包 offline-deps + package.sh + md5/sha256 + GitLab Release 创建 + 主包上传 Generic Package）→ `deploy`（tag v*：Dockerfile.run 构建运行镜像 + 独立 docker 部署 18080 + 容器 IP 只读冒烟）。`GITHUB_WORKSPACE` 变量须设为 `$CI_PROJECT_DIR`（ci_test.sh 的 workspace 探测默认 /workspace）。
  6. **实验部署冒烟视角**：job 容器内 localhost 是 job 容器自身，**冒烟必须用 `docker inspect` 取容器 IP**；实验 env 覆盖 `INTERNAL_CIDRS=127.0.0.0/8,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16`（localhost/docker bridge 判内网）供手工全流程验证（生产保持真实网段，ADR-043 冒烟纪律不适用实验环境）。
- **教训（跨平台 CI/CD 迁移沉淀）**：
  1. **Windows git autocrlf**：新文件入库被转 CRLF（bash 脚本在 Linux 容器报 `\r` 错误）→ 仓库 `.gitattributes` 加 `*.yml text eol=lf` + 本仓库 `core.autocrlf=false`；**Windows 侧 `git cat-file | python` 管道计数 CRLF 是 PowerShell 管道伪影，权威验证必须在 Linux 侧**（`git cat-file -p origin/xxx:.gitlab-ci.yml | grep -c $'\r'`）。
  2. **docker executor pull_policy** 默认 always → 本地构建镜像必须 `pull_policy = "if-not-present"`。
  3. **卷属主**：容器内 uid 1000（Dockerfile.run USER）写宿主卷，`mkdir` 后必须 `chown -R 1000:1000`（否则 PermissionError: /nas/staging）。
  4. **env 模板行尾注释**：`prod.env.template` 的 `TEMP_FILE_HOURS=24  # 注释` 直接 `--env-file` 会导致 `int() invalid literal`——生成干净 env 须同时去行首与行尾注释（`sed -e 's/^#.*//' -e 's/[[:space:]]*#.*$//'`）。
  5. **GitLab Release 资产**：GitLab 自动为 tag 生成 4 个 sources（zip/tar.gz/tar.bz2/tar）即"发布成功"；文件资产另走 Generic Package Registry。
- **与既有 ADR 不重复**：ADR-036 管权威/备份仓库（Gitea+GitHub）；ADR-042 管认证方法论（本 ADR 落点 GitLab PAT）；**本 ADR 管第三条平台线（GitLab）的 CICD 实验打通与环境隔离纪律**，沉淀跨平台 CI/CD 迁移的共同坑（CRLF/pull_policy/卷属主/env 注释/容器冒烟视角）。
- **已落点**：2026-09-15 v2.7.1 rc——GitLab 项目 `root/securetrans`（id=209，私有，默认分支 gitlabcicotest）；Runner id=19；CI 镜像 488MB；流水线 686/688 全绿（CI 全量 TDD + Release v2.7.1 四资产 + CD 独立部署）；18080 独立部署冒烟 OK（health v2.7.1/prod/ok）+ admin 登录成功；生产 Rocky 未触碰（数据全在 /opt/securetrans-gitlab）。

### ADR-046：Git 服务器选型——Gitea / GitHub / GitLab 优劣势对比与场景选型建议（方法论，未来项目可复用）
- **背景**：本项目先后打通三条 git 平台线并全链路验证——Gitea（权威仓，生产 CD）、GitHub（备份仓，云端 CI/Release/CD-SIM 独立闭环）、GitLab（实验线，独立 WSL+docker 隔离部署，ADR-036/042/045），沉淀了三平台第一手经验（操作细节见 docs/CICD.md，对比+带注释模板）。未来项目（尤其 AI 辅助人机协同、小团队/副业、封闭数据中心、以及需要公网分发的场景）都会面临"选哪个 git 服务器"决策；若无沉淀，每个项目都要重新调研。本 ADR = **三平台通用优劣势归纳 + 场景选型建议**，是可复用方法论，不绑定本项目实例。
- **决策（三平台优劣势）**：
  1. **Gitea（自托管轻量）**——优势：本地部署、完全掌控数据（封闭数据中心可用）、免费轻量（单二进制/小内存）、act_runner 容器 label + docker.sock 构建镜像天然自包含、Release API 资产灵活（7 资产含离线包/镜像）、离线依赖（wheelhouse）友好；劣势：Actions 生态与文档少于 GitHub、无内置镜像 registry（需外挂 GHCR/自建）、act_runner 已知 bug（needs 解析假绿、大产物清理误报，ADR-021/041 教训）、无公网托管需自建出网。**适用：封闭数据中心、私有代码、小团队/副业、离线环境、需要权威仓掌控生产 CD。**
  2. **GitHub（公有云托管）**——优势：public 仓库 CI/CD/存储免费、托管 runner 零运维（ubuntu-latest 云 VM 自带 docker）、云端闭环（CI+Release+GHCR+CD-SIM 全在云）、GHCR 免费 registry（GITHUB_TOKEN 零注册）、生态最大（marketplace action）、PR 协作成熟、天然公网分发；劣势：private 仓库有额度限制、**无法直连封闭数据中心（CD 只能仿真 CD-SIM，真实生产 CD 必须本地权威仓）**、代码在第三方云（合规敏感不可用）、大 artifact/大仓库限制。**适用：开源/公网项目、需要公网分发与协作、备份/容灾仓、云原生。**
  3. **GitLab（自托管全家桶）**——优势：单文件 .gitlab-ci.yml 多阶段（stages/rules）、内置 registry+package+Release 一体化（CE 免费）、权限模型细（group/role）、docker executor 灵活、Issue/Wiki 全家桶；劣势：CE 功能受限（部分需 EE）、资源占用重于 Gitea、runner 配置需手工改 config.toml（pull_policy 等）、Release 文件资产需 API（Generic Package）、无公网托管。**适用：公司级多项目多团队统一平台、需要全家桶（CI+registry+package）、GitLab 已是组织标准。**
- **决策（场景选型建议矩阵）**：
  | 场景 | 推荐 | 理由 |
  |---|---|---|
  | 封闭数据中心 + 小团队/副业 | **Gitea**（权威）+ GitHub（备份/分发，若能出网） | 数据掌控 + 生产 CD 本地闭环 |
  | 开源/公网 + 社区协作 | **GitHub** | 托管免费、生态最大、天然分发 |
  | 公司多项目多团队统一 | **GitLab** | 全家桶 + 细权限 + 集团标准 |
  | 需要容器镜像分发 | GitHub（GHCR）或自建 registry | GHCR 免费零注册；Gitea 侧用 image.tar.gz 离线兜底 |
  | 多平台并存（本项目模式） | 权威 Gitea + 备份 GitHub + 实验（GitLab 或 GitHub） | 权威仓永不漂移、备份仓独立验证、实验线零风险 |
  - **选型原则（跨平台沉淀）**：① **一个权威仓库 + 一个备份仓库**（权威=所有 git 操作与生产 CD 唯一；备份=容灾/分发/独立验证，永不接触生产，ADR-036）；② **认证 token > SSH >> 账号密码**，本地 credential 文件不入库（ADR-042）；③ **CI 门禁逻辑平台无关**（放 infra/*.sh，三平台 workflow 只是"壳"，迁移平台零重写门禁）；④ **环境即代码**（FROM python:3.12-slim 官方镜像 + 离线 wheelhouse，CI/CD 免手工装依赖）；⑤ 每个阶段聚焦主要矛盾、跟随调整形成动态平衡（ADR-027）。
- **与既有 ADR 不重复**：ADR-036 管本项目权威/备份仓库体系实例（Gitea+GitHub）；ADR-042 管认证方法论；ADR-045 管 GitLab 实验线打通实例；docs/CICD.md 管三平台操作手册（对比表/模板/入门）。**本 ADR 管三平台通用优劣势归纳与未来项目选型方法论**（决策可复用、不绑定本项目），三者互补不重叠。
- **已落点**：2026-09-15——三平台全链路实证（Gitea CI/Release/CD 生产全绿；GitHub CI-TDD/RELEASE/CD-SIM 云闭环全绿；GitLab ci-check/release/deploy 实验线全绿）；docs/CICD.md（操作手册）+ 本 ADR（选型方法论）同步入库。

### ADR-047：发布触发自动化与 AI 边界——AI 孵化 → 平台自治（方法论 + 本项目强制）
- **背景**：2026-09-15 对三平台（Gitea/GitHub/GitLab）全部 workflow 触发机制逐条审核，回答"触发是靠 AI 还是靠 git 机制"。结论=**触发全部是 git 服务器原生事件钩子**（push/tag/release published），AI 不在流水线中间介入；唯一需要人/AI 的动作是"打 tag"（发布决策）。成熟期目标是 AI 不再深度介入，由平台机制自治保证。
- **决策（触发机制审核结论，三平台对齐）**：
  | 平台 | CI | Release | CD | 触发者 |
  |---|---|---|---|---|
  | Gitea | push main / push tag v* | push tag v* / release | release published / workflow_dispatch | git 事件（自动） |
  | GitHub | push main / push tag v* / pull_request | push tag v* / release / workflow_dispatch | release published / workflow_dispatch | git 事件（自动） |
  | GitLab | tag ^v / branch gitlabcicotest | tag ^v | tag ^v | git 事件（自动） |
  - **发布链全自动**：`git tag vX.Y.Z && git push origin vX.Y.Z`（人/AI 唯一介入点）→ tag 事件 → release workflow（构建资产+建 Release）→ release published 事件 → CD workflow（Gitea 真实生产 / GitHub 云仿真 / GitLab 实验 18080）——**链式全自动，无 AI 介入**。
  - **tag 推送范围 = 发布范围**：三平台 remote 独立，推 tag 到哪个 remote 就触发哪个平台的 release/CD（Gitea=生产 CD、GitHub=云闭环+GHCR、GitLab=实验线 18080）；**日常同步只推 main（不推 tag）就不会触发任何 release/CD**。GitHub 多 pull_request 触发（云协作预留，本地主干开发用不上）；GitLab 实验线 ci-check 限定 gitlabcicotest 分支（推 main 不触发，已验证 2026-09-15）。
  - **AI 边界（阶段演进）**：孵化期=AI 深度介入（编写 workflow/脚本、配置 runner/secret、试运行与排障）；成熟期=AI 只保留两件事——① 发布决策：执行 `git tag` + push（ADR-007 由人拍板）；② 应急：手动 workflow_dispatch 重跑。**流水线本体（CI 门禁→Release→CD）平台自治，AI 不再深度介入**。
- **与既有 ADR 不重复**：ADR-007 管发布节奏与门禁（何时发、发不发）；ADR-037 管环境职责分层（CI=门禁/Release=发布/CD=部署）；ADR-046 管平台选型。**本 ADR 管"谁触发流水线 + AI 与平台自治的边界"**，三者互补。
- **已落点**：2026-09-15——三平台 workflow 触发段逐条审核入库（docs/CICD.md §10）；三平台 main 全同步 57d89bf；已验证推 GitLab main 不触发流水线（rules 过滤）。
- **补充（2026-09-16，执行顺序与失败回退，docs/CICD.md §10.4）**：
  - **顺序机制（三平台对齐，最终语义一致）**：
    | 平台 | CI → Release | CD |
    |---|---|---|
    | GitLab（单流水线） | **顺序**（stages 串行） | 同一流水线内，顺序 |
    | Gitea/GitHub（事件链） | **并行**（tag 同时触发 ci.yml + release.yml） | Release published 后触发 |
    GitLab 的 `stages:` 语义=同一 stage 内多个 job 并行、stage 之间严格串行；本项目三 job 各占一个 stage，必须 ci-check 全绿 → release 成功 → deploy 才会跑（deploy 另有 `dependencies: [release]` 依赖 release 制品，双保险）。Gitea/GitHub push tag 时 ci.yml 与 release.yml **同时触发（并行）**，CD 由 release published 在 Release 建成后触发。**两者最终结果一致**（CI 门禁不过→Release 建不出；Release 不发布→CD 不启动），只是编排机制不同。
  - **失败处理**：CI 失败=看 run 日志→改代码 push→rerun（幂等）；Release 失败=修后重跑 release，资产损坏删 Release 重建（ADR-041）；CD 失败=先确认生产状态→修脚本 rerun 或 workflow_dispatch 手动补部署；部署后发现问题=①生产回滚（ADR-043 蓝绿"先停再起"）②打新 tag 修复版（推荐）③git revert 后重走全链。
  - **回退铁律**：先回滚生产恢复业务，再修代码；**生产回滚 ≠ 代码回退**（git revert 不影响已部署实例）。

### ADR-048：AI 时代人机协同 Agile 方法论采纳（v2.0 → v3.0，方法论+强制）
- **背景**：2026-09-15 项目进入 PSF 收尾→PMF 准备节点（第一个"客户"完成）。用户与 DeepSeek 深度沟通后获得"AI 时代人机协同 Agile 方法论"原型（share/kg8xxzwitepqj4dt42），核心判断=软件工程从 SE 2.0（AI 辅助）进入 SE 3.0（Agentic Software Engineering），传统敏捷的实现细节被颠覆、概念内核保留。本项目两周实证（AI 辅助开发→测试→CICD→三平台发布）已证明传统敏捷大量形式无收益，需方法论升级以指导本项目与下一项目。
- **决策**：
  1. **采纳并融合**：docs/01 升级 v2.0→v3.0（AI 时代人机协同 Agile 方法论模板），保留 Scrum 经验主义内核（透明/检视/适应）与 v2.0 精华（人机分工/事件裁剪/承诺/站会看板模板），新增——SE 3.0 范式说明、循环迭代流程（Design Thinking→Lean Startup→Agile→DevOps/GitOps→Release→回流）、L1/L2/L3 变更分级（影响半径+可逆性，事件触发）、HITL/HOTL/HOOTL 三重范式、超级XP PDCA 微循环、RTM 缓冲并入 Agile 检查/适应环节（会诊：Agent 影响分析→人 Fix/As Designed/Won't Fix/Postpone；RC 序列；L1 无需/L2 轻量/L3 完整）、防眩晕机制（变更预算 ≤2-3 L3/10 L2 + WIP=1 + 漂移检测 + 周报压缩）、极简工件体系（Repo as Memory：PRD/ADR/复盘/AGENTS 唯一事实来源，不用 Jira）、分阶段落地路径、一句话方法论（单 Agent + Repo as Memory + Prompt as Process + Human as Gate + PDCA 微循环 + 分级变更控制 + RTM 缓冲并入 Agile + Release 渐进交付）。
  2. **AGENTS.md Part A 同步**：A1 补人机协同范式与变更分级；A4 补 RTM 缓冲行；A8 补防眩晕实践（第 10 条）。
  3. **Commit 规范升级**：commit 携带变更级别标记 `[L1|L2|L3]`（L3 必须已获人确认）；AI 识别到 L3 倾向必须停下请求决策。
  4. **本项目落点**：RTM 缓冲=现有 rc 阶段（v2.7.x，APP_STAGE=rc，ADR-043）；防眩晕=日常迭代已按变更预算收敛；下一项目直接套用 docs/01 v3.0 模板。
- **与既有 ADR 不重复**：ADR-025 管 AGENTS Part A 唯一来源（本 ADR 是其内容升级的依据）；ADR-027 管双闭环复盘（PSF/PMF 节奏）；ADR-047 管发布触发自动化。**本 ADR 管 AI 时代人机协同方法论（SE 3.0 范式+变更分级+范式+防眩晕）采纳与模板升级**。
- **已落点**：2026-09-15——docs/01 v3.0（模板本体）+ AGENTS Part A（协作契约）同步升级入库；commit 携带 [L1|L2|L3] 标记从本 ADR 起执行。

### ADR-049：GitLab 隔离——双开发域分离（2026-09-16，方法论+强制）
- **背景**：用户决策——进入 GitLab 即公司开发域，与本地/Gitea/GitHub（个人开发域）严格分离，改用另一 AI 工具独立访问维护 GitLab。同步前发现 GitLab CI/release/CD 配置完整性存疑：核实结果=`.gitlab-ci.yml` 已入库且与 gitlabcicotest 分支一致（git diff=0），缺的是 Runner 侧配置（config.toml 关键段）、仓库 CI/CD 变量清单与完整配置资产清单未文档化。
- **决策**：
  1. **配置资产全量固化**：docs/15 新增 §7 配置资产全量清单——仓库内资产（.gitlab-ci.yml 权威配置、docs/15、infra/docker/Dockerfile、Dockerfile.run）+ 服务器侧配置记录（Runner config.toml 关键段、GITLAB_PAT、WSL/docker/数据目录/端口/镜像），保证 Gitea/GitHub 侧可完整复现与审计。
  2. **双开发域分离（强制）**：个人开发域=本地 Windows + Gitea（权威）+ GitHub（备份/云端闭环）；公司开发域=GitLab（另一 AI 工具访问）。主仓库**不再推送 GitLab remote**；GitLab 服务器现状保留（gitlabcicotest 分支/Runner/数据/Release v2.7.1），由另一 AI 工具维护。
  3. **再启用条件**：仅当用户明确指示（如公司侧需重跑实验线）才允许推送 GitLab 并触发流水线；默认保持隔离。
- **与既有 ADR 不重复**：ADR-036 管权威+备份双仓（Gitea/GitHub）；ADR-045 管 GitLab 实验线打通与隔离纪律；ADR-046 管三平台选型。**本 ADR 管 GitLab 从"实验线"转"公司开发域"的隔离与配置资产固化**。
- **已落点**：2026-09-16——docs/15 更新为"已隔离归档"（§7 配置资产全量清单 + §8 隔离状态）；README/AGENTS 同步；本次 commit 仅推送 Gitea + GitHub（不推送 GitLab）。
- **补充（2026-09-16，隔离前收尾，v2.7.3 实证）**：
  - **开发分支终结方式**：Git 分支=指向 commit 的引用（ref），merge 后源分支**不会自动删除**；删除分支引用 ≠ 删除内容——commit 已在 main 历史永久保留，GitLab 流水线/MR/审计记录全保留。收尾动作：`gitlabcicotest` 已合并 main 并 `git push gitlab --delete gitlabcicotest` 删除远端分支（本地分支保留作过程存档）。
  - **CI 触发改 main**：`.gitlab/workflows/ci.yml` rules 从 `$CI_COMMIT_BRANCH == "gitlabcicotest"` 改为 `"main"`——push main 触发 ci-check（tag 仍触发三阶段）。副作用确认：删分支后"分支推送触发 CI"路径消失，tag 触发时 ci-check 照跑；按本 ADR 隔离（不再推 GitLab）实际无影响。
  - **GitLab Release 资产口径（有意简化，非异常）**：GitLab 对任何 tag 自动生成 4 种 sources 源码包（zip/tar.gz/tar.bz2/tar），实验线 release 未显式上传业务资产（主部署包/md5/offline-deps/镜像）——与 Gitea 7 资产/GitHub 4+GHCR 不一致是**实验线有意简化**（ADR-045 只验证链路对齐）；未来公司域正式用需在 release.yml 补 `upload-asset`。已记录 docs/15 §3。
  - **收尾全链实证**：v2.7.3——push main 触发 ci-check ✅（#695）、push tag v2.7.3 触发 ci-check→release→deploy 全绿 ✅（#696，stages 严格顺序），CD 部署容器 `securetrans-gitlab`（18080 对外）+ 只读冒烟 PASS；全程仅 GitLab 实验 WSL（Ubuntu 24.04）+ 独立 docker + `/opt/securetrans-gitlab`，Rocky 测试/生产未触碰，Gitea/GitHub 未推（无 v2.7.3 tag）。
  - **runner 标签澄清（2026-09-16 用户误解澄清，重要）**：三个 job 的 `tags: [gitlabcicotest]` 是 **GitLab runner 选择标签，不是分支依赖**——job 靠 tags 派发给注册该标签的专用物理 runner（`gitlabcicotest-docker`，Ubuntu 24.04 WSL docker executor）；恰与开发分支同名纯属巧合。tag v* 触发的 release/deploy 不经过任何分支条件；删改 tags 会导致 job 找不到 runner 卡死。教训：GitLab Web UI 中 tags 与分支同名易误导，文档需显式区分"触发条件 rules（分支/tag）vs 运行载体 tags（runner）"。
  - **隔离终态（2026-09-16）**：GitLab 仓库 main=4a7ffe6（含收尾全部 commit：53005e3 收尾主提交 + 7e3de0d 根入口注释修正 + 4a7ffe6 release 描述清理）；已与 Gitea/GitHub 对齐（本地 main=origin=4a7ffe6）。**GitLab 自此隔离不再使用**；公司开发域由另一 AI 工具独立维护；主仓库仅 Gitea（权威）+ GitHub（备份），GitHub 认证=**PAT token**（官方 2FA 已启用，禁用账号密码；token 含特殊字符需 URL 编码或 credential helper，ADR-042）。

### ADR-050：CICD Workflow 组织方式——总分式（入口+明细拆分）vs 单文件（2026-09-16 复盘，方法论）
- **背景**：三平台（Gitea/GitHub/GitLab）CICD 全 workflow 流程的组织方式复盘。本项目现行=总分式多文件（Gitea `.gitea/workflows/{ci,release,cd}.yml`；GitHub `.github/workflows/{ci,release,cd-sim}.yml`；GitLab `.gitlab-ci.yml` 入口 + `.gitlab/workflows/{ci,release,deploy}.yml`），与"全部写在一个 workflow 文件"对比评估优劣势。
- **对比结论**：
  1. 总分式优势=触发即作用域（push→CI/tag→Release/release→CD 天然分离，rules 简单）、权限最小化（每 workflow 独立 secrets：CI 零写、Release 持 RELEASETOKEN、CD 持 CD_SSH_KEY）、失败隔离（单阶段独立 rerun，CD 失败不污染 CI）、可读维护（文件小 diff 小）、跨平台迁移（workflow 仅薄壳，门禁逻辑全在 infra/*.sh 平台无关，逐平台易对齐）。
  2. 总分式代价=跨阶段传值需 artifacts（release→cd 下载）、默认 env/镜像 tag 多份复制有漂移风险（以 infra/*.sh 单一来源缓解）、新手需先懂触发矩阵。
  3. 单文件优势=needs+outputs 同文件传值简单、配置一处定义、一文件看全流程；代价=rules/if 条件复杂易错（ADR-041 同源教训）、secret 难隔离（Gitea 尤其弱）、rerun 粒度粗、低频 CD 拖累高频 CI 队列、跨平台迁移整体重写。
- **决策**：本项目保持总分式（现状即正确）。理由：①三平台 workflow 是薄壳（ADR-037 平台无关门禁）；②安全关键——Release/CD 需写凭据，拆开才能 secret 最小作用域；③触发矩阵天然三分，单文件 rules 复杂是 ADR-041 出 bug 的同类复杂度；④GitLab 侧以根入口 + include local 对标（GitLab 官方惯例，全局 stages 留根文件）。
- **单文件适用边界**（未来项目判断）：纯 CI 单平台、阶段线性无独立发布/部署、无跨平台对齐需求、团队偏好一文件看全流程——可单文件；命中"多平台/有发布部署/安全敏感"任意一条则优先总分式。
- **落点**：2026-09-16 复盘入库；docs/CICD.md §2.1 结构表更新为入口+明细（原"单文件三阶段"表述过时已修正）；三平台目录对齐清单见 docs/15 §7.1。
- **补充（2026-09-16，GitLab 根文件=平台硬性机制，非冗余）**：GitLab 流水线配置文件**必须**名为 `.gitlab-ci.yml` 且**必须位于仓库根目录**——GitLab 不扫描 `.gitlab/` 目录（区别于 Gitea/GitHub 扫描 workflows 目录下所有 yml 各为独立 workflow）；删掉根文件则 GitLab 完全不执行流水线。故 GitLab 总分式的实现=**根文件做"总入口"（stages + include: local 引用明细）+ `.gitlab/workflows/*.yml` 做明细**，根文件不是重复文件而是执行链第一环；`include: local` 支持子文件用相对仓库根路径（`'.gitlab/workflows/ci.yml'`），子文件内 stages/needs 照常生效。Gitea/GitHub 无"总入口"概念（目录即集合），GitLab 必须有——这是三平台总分式对标中唯一的机制差异。

### ADR-051：飞书审批通知——独立旁路通道、失败不阻塞业务、界面可观测（强制，2026-11-27）
- **背景**：关键提交/审批节点需要触达提交人与一级/二级审批人；免审批直通必须跳过全部审批人、只通知提交人。通知依赖外部系统（飞书开放平台 + 内网通知网关），其可用性不受本项目控制。若把通知纳入业务事务，外部系统抖动会直接放大成"提交失败/审批失败"，与摆渡系统的核心可用性目标冲突。另需解决"通知发没发出去、失败在哪一环"的定位问题——否则运维只能靠猜。
- **决策**：
  1. **独立旁路**：通知与业务事务**完全解耦**，异步发送（线程池/队列），**绝不阻塞**提交、审批、下载主流程；通知失败不改变任何业务状态机。
  2. **固定触发点（7 类，不多不少）**：①提交成功（需审批）→ 当前待办层级审批人；②提交成功（免审批直通）→ **仅提交人**；③一级通过（内部/合作方直接摆渡）→ 提交人；④一级通过（同人具备二级权限、自动跳过二级）→ 提交人；⑤一级通过（非合作方进入二级）→ 提交人 + 二级审批人；⑥二级通过 → 提交人；⑦任一环节驳回 → 提交人（含驳回意见）。
  3. **失败语义**：成功/失败/跳过统一落 `notification_logs`（每单每节点一条，供界面与详情读取）；仅失败额外写一条审计 `notify_failed`（detail 只记错误摘要，不记正文/文件内容）；**不抛异常、不回滚业务、不做阻塞式重试**。
  4. **可观测性（强制）**：提交列表 / 待审批列表 / 所有提交记录直接显示飞书通知状态（成功/失败/跳过/无记录 + 事件 + 时间 + 错误摘要）；详情页展示最近 20 条通知记录；提交/审批成功提示中注明"飞书通知异步发送，状态见列表"。目的是让"通知异常"在业务界面第一时间被发现，从而快速区分是飞书网关、开放平台权限还是网络问题。
  5. **收件人解析（AD → 邮箱 → 飞书，三级）**：统一"账号 → 工作邮箱 → 飞书人员"——`local_users.email` 优先；未命中再查 AD `mail`（生产 AD 字段名 `mail`）；仍解析不到则记 `skipped` 并继续，不阻塞业务。实证（2026-11-27）：AD 账号 `jintao` → `tonyj@nexskysemi.com` → 飞书按 `receive_id_type=email` 投递成功；结论=**最小权限 `im:message` + `im:message:send_as_bot` 足够，无需 `contact:user.base:readonly`**，也不需要 open_id。
  6. **开关与降级**：`FEISHU_NOTIFY_ENABLED=false` 时全链路静默（记 `skipped`），用于网关不可用时的应急降级。
- **落点（v2.7.3 已实现，2026-11-27）**：
  - 配置项（`.env`，全部非硬编码）：`FEISHU_NOTIFY_ENABLED`、`FEISHU_NOTIFY_URL`、`FEISHU_NOTIFY_TOKEN`、`FEISHU_NOTIFY_TIMEOUT`（默认 5s）、`FEISHU_NOTIFY_APP_URL`（通知正文中的处理入口）；模板见 `env/dev.env`、`env/test.env`、`env/prod.env.template`，生产真实 token 只写生产 `.env`（不入库）。
  - 代码（`src/app.py`）：新增 7 事件白名单 `NOTIFY_EVENTS`、`resolve_email()`（本地表→AD `mail`）、`notify_event()`（daemon 线程派发、永不抛异常）、`_notify_worker()`（app_context 内解析邮箱→POST 网关→落库→失败写审计 `notify_failed`）、`get_notify_map()`（列表批量取最新一条，避免 N+1）、`_mask_email()`（`t***@n***`）；新增表 `notification_logs(submission_id,event,recipients,status,detail,created_at)`；`User` 类新增 `email` 并贯通 session（修复 AD 用户登录不落库导致"提交人无邮箱"的缺口）。
  - 触发点：提交（免审批→`submission_auto_approved` 仅提交人；需审批→`submission_status` 提交人 + `submission_pending_l1` 一级审批人）；一级通过（进入二级→`submission_status` 提交人 + `submission_pending_l2` 二级；内部/合作方直接通过→`submission_approved` 提交人；自动跳过二级→`approval_level_skipped` 提交人）；终审→`submission_approved`；驳回→`submission_rejected`（含原因）。
  - 接口：`/api/submissions`、`/api/admin/submissions/all`、`/api/submissions/pending/my` 每条附 `notify`（最新 status/event/detail/time）；`/api/submissions/<id>` 附 `notifications`（近 20 条，收件人已掩码）。
  - 界面（`src/static/index.html`）：三个列表新增"飞书通知"列（成功/失败/跳过/无记录徽标 + 事件名），详情页新增"通知记录"区块，提交/审批成功提示注明异步发送；i18n 中英双语键 `notify.*` 完整。
  - 网关：`infra/feishu-gateway/`（FastAPI，8090），7 事件模板 + `X-Notify-Token` 鉴权 + `request_id` 幂等 + JSONL 记账。
  - 测试：`tests/test_api.py` 组 25（通知桩 `127.0.0.1:18099`），21 条断言覆盖七事件、AD/本地邮箱、免审批"仅提交人"强断言、网关 502 不阻塞 + `notify_failed` 审计；**组 26 独立功能验证**（2026-11-27）追加 22 条：幂等键形态、收件人脱敏、列表/详情字段齐备、成功投递不写失败审计（反向断言）、无邮箱降级 `skipped`、内部提交跳过二级、语义B 自动跳过二级、网关契约异常三态（`partial`/401/超时）均不阻塞业务——**全量 467/467 通过**（干净库基线）。
  - **测试执行约束（教训）**：全量 TDD **必须在项目根**执行 `python tests/test_api.py`——`NAS_ROOT=./nas`、`SECURETRANS_DATA=./data` 是相对路径，按进程 CWD 解析，在 `tests/` 下运行会指向 `tests/nas` 而使 staging 断言错位；审计接口 `@role_required("admin")`，统计 `notify_failed` 须在 admin 会话下取，否则 403 静默取 0（本轮即因此产生一条假失败/假通过）。
  - 已知边界：收件人无可用邮箱→`skipped`（不回退通知管理员）；生产 `.env` 与容器出站策略属部署步骤（见 ADR-052 落点）。
  - 生产下发（2026-11-27 验证态）：`.env` 增 `FEISHU_NOTIFY_ENABLED/URL/TOKEN/TIMEOUT/APP_URL`；因 podman 4.9 `commit` 对 docker-format 图层报 `unsupported MIME type for compression`，改用 `podman export` + `podman import` 生成临时镜像 `securetrans:v2.7.3-feishu-r1`（保留 `securetrans:v2.7.1-rollback` 回退点），以原 run 参数（同端口/卷/`--user 973:972`）重建容器，`/api/health` = `v2.7.3` 且页面 200。**该镜像非发布资产，正式版本须以标准 `image.tar.gz`（Dockerfile.run 构建 + CD 通道）替换。**

### ADR-052：关键服务器零出网 + 专用单向通知网关（安全，强制，2026-11-27）
- **背景**：SecureTrans 生产（10.10.30.8）是公司关键文件摆渡节点，其可用性与数据安全优先级最高。若业务机自行直连互联网出站，一旦被攻破即具备外传与反连能力，且出站面分散、审计困难、飞书凭据需落在业务机。改为"业务机零出网 + 单台专用网关出网"后，攻击面、审计面、凭据面三处同时收敛。
- **决策**：
  1. **业务机零出网**：SecureTrans 生产容器不配置互联网出站；唯一外部调用路径 = 内网 POST 到 `feishu-sdk-server-securetrans`（10.10.30.114）。
  2. **网关单向最小化**：网关仅放行 `open.feishu.cn:443`（**已在防火墙上落地**），**禁止**任意 URL 转发/透传——防止退化为 SSRF 跳板或开放代理。
  3. **网关鉴权（已在防火墙上落地源 IP 限制）**：源 IP 白名单仅 `10.10.30.8` + 预共享 token（`FEISHU_NOTIFY_TOKEN`，请求头校验），双重校验缺一不可。
  4. **凭据最小化（强制）**：飞书 App Secret 只允许存在于**两处**——开发机本地凭据文件（`server_credential.md` / `~/.securetrans/`，均已 gitignore）与网关 `.env`；**禁止**出现在业务机、git 仓库、Gitea/GitHub、聊天/工单/邮件。
  5. **网关职责边界**：只做「鉴权 → 模板渲染 → 调 lark-oapi 发送 → 记账」四件事；**不做业务决策**（不判断该不该审批、不改业务状态），**不落业务正文**（不存文件名/文件内容）。
  6. **脱敏日志**：网关侧只记元数据（时间、收件人标识哈希或掩码、模板、结果、飞书错误码），保留期限与业务审计一致。
- **落点**：
  - ✅ 已落地（2026-11-27）：网关防火墙 443 白名单（仅 `open.feishu.cn`）+ 源 IP 白名单（仅 `10.10.30.8`）；主机改名 `feishu-sdk-server-securetrans`；通知服务独立于 CICD 的 8080，绑定 `10.10.30.114:8090`（只监内网 IP，`127.0.0.1` 被拒属预期）；`securetrans-notify` systemd active+enabled；venv 复用网关机既有站点包（出网只放行 443，无法在线 pip 装包）；`.env` 600（`FEISHU_APP_ID`/`FEISHU_APP_SECRET`/`FEISHU_NOTIFY_TOKEN`/`NOTIFY_BIND`/`NOTIFY_PORT`/`NOTIFY_DATA_DIR`/`SECURETRANS_APP_URL`）；审计 `/var/lib/securetrans-notify/notify.jsonl`（含 `client` 源 IP、收件人掩码）。
  - ✅ 端到端实证（2026-11-27）：生产机 `10.10.30.8` → `POST http://10.10.30.114:8090/notify`（`event=submission_pending_l1`）→ `HTTP 200 / sent=1 / message_id=om_x100b7fa1e02864b0df13d5f36785be8`；网关审计 `client=10.10.30.8`，用户收到消息原文确认标题/单号/提交人/文件名/事由/时间/入口正确。
  - ✅ 应用层源 IP 白名单（2026-11-27，fail-closed）：`notify_app.py` 新增 `_client_allowed()`（`NOTIFY_ALLOW_CIDRS` 未配置即拒绝，默认拒绝而非放行）；`/notify` 首行校验 `request.client.host`，不在白名单返回 `403 client ip not allowed`。实测：网关本机（`10.10.30.114`）POST → **403**；生产容器 POST → **200**。`NOTIFY_ALLOW_CIDRS=10.10.30.8/32` 已写入网关 `.env`；`deploy-gateway.sh` 对空值显式告警。
  - ✅ 生产部署形态联通（2026-11-27）：生产容器（`--user 973:972`，仅挂 `/data`、`/nas`）内直接 POST 网关 → `200 / sent=1 / message_id=om_x100b7fa25bd450a0c1ffd42f65fcc23`，证明"容器零出网 + 仅内网通知"在真实部署形态下可用。
  - ✅ 开机自恢复（2026-11-27）：生产 `podman-restart.service` 原为 disabled（容器 `RestartPolicy=unless-stopped` 只在 podman 运行期间有效，rootful 无守护进程 → 主机重启后容器不自启），已 `enable --now`，`is-enabled=enabled`、`is-active=active`。
  - ⏳ 待落地（属部署步骤，非代码缺陷）：生产 `.env` 写入 `FEISHU_NOTIFY_URL=http://10.10.30.114:8090/notify` 与真实 `FEISHU_NOTIFY_TOKEN` 并重启容器；SecureTrans 容器出站策略显式拒绝互联网（仅内网放行到 10.10.30.114:8090）；token 轮换流程（建议 180 天，与飞书 App Secret 同步）。
  - 关联：ADR-042（凭据只存本地/受控服务端两处）、ADR-051（失败不阻塞与界面可观测）。

### ADR-053：生产部署只读冒烟全量通过 = 发布门禁（强制，2026-11-27）
- **背景**：CD 落地（`cd-deploy.sh`）此前在冒烟失败时只打印"警告"后继续，退出码仍为 0——流水线显示绿色，但生产实际存在失败项（假绿）。对关键摆渡节点，冒烟是唯一在真实部署形态下验证"装上去还能用"的自动化手段，若允许"警告即通过"，等于门禁失效。
- **决策**：
  1. **硬门禁**：生产只读冒烟（`infra/smoke.sh`，组 24 白名单 + 质量门禁）**全量通过**才视为部署成功；任一失败 → CD 任务失败（`exit 1`），docker 通道与原生回退通道一致，不允许告警式放行。
  2. **凭据单一来源**：冒烟凭据取 `.env RESET_PASSWORD`（ADR-009）；生产若已手工改密，用 `VERIFY_ADMIN_PASS='<当前密码>' bash infra/smoke.sh <BASE_URL>`，不在脚本内硬编码第二份默认密码。
  3. **断言必须容错**：冒烟断言不得因响应体非 JSON 而抛栈——登录失败要给出"凭据不匹配/是否改密"的明确提示，否则真实原因被 `AttributeError` 掩盖（2026-11-27 首次生产冒烟即命中该缺陷）。
  4. **目标地址**：生产冒烟必须用内网 IP（`http://<内网IP>:8000`）；`127.0.0.1` 不在 `INTERNAL_CIDRS` 被判外网面、管理接口 403 属正确行为（ADR-043）。
- **落点**：
  - `infra/cd-deploy.sh`：docker 通道与原生通道的 `smoke.sh` 调用由 `|| echo "[警告]…"` 改为 `|| { echo "[错误] 生产冒烟未通过（发布门禁）"; exit 1; }`。
  - `tests/test_api.py` 组 24：`24-2` 登录断言增加 `isinstance(data, dict)` 保护并输出凭据提示；`24-3`/`24-4` 统一安全取值，避免登录失败时后续断言连锁崩溃。
  - 本地全量回归：**467/467 通过**（干净库）。
  - 关联：ADR-017（冒烟白名单）、ADR-009（部署凭据）、ADR-024（CD 流程）、ADR-007（发布门禁）。

### ADR-054：飞书通知=独立配置域（外挂式 channel，DB 权威/运行期生效/hook 化，2026-11-27）
- **背景**：飞书通知落地后（ADR-051/052）配置仍是模块级 env 常量（`FEISHU_NOTIFY_*`），带来三个问题：
  ① 运维期没有 AI 参与时，改地址/token/开关必须改 `.env` 并重启，无法在界面自查；② 生产部署后若网关换机/换端口，只能手工改文件；
  ③ 通知逻辑硬编码在 8 处业务调用点，将来接钉钉/邮件要改业务代码。同时用户明确要求"飞书当外挂看，IP 等作为完整配置统一体现，和 AD 域一样是独立一组配置"。
- **决策**：
  1. **独立配置域**：新增 `feishu_config` 表（与 `ad_config` 同构：key/value/source/updated_at），配置页"飞书通知"独立成卡片，与 AD 域同级；首次空表从 `.env` 播种一次（source=env），此后 DB 权威（source=db），留空回退 `.env`（沿用 ADR-010 配置权威口径）。
  2. **配置项完整**：`feishu_enabled`（开关）、`feishu_gateway_host` / `feishu_gateway_port` / `feishu_gateway_path`（网关地址，IP 显式可见）、`feishu_gateway_url`（完整 URL 覆盖，兼容旧 env）、`feishu_notify_token`（预共享 token）、`feishu_timeout`、`feishu_app_url`（消息里的系统入口）、`feishu_app_id`（仅展示/核对）。
  3. **Secret 边界不放宽（ADR-052 不变）**：App Secret **不落业务机、不入库、不下发、不展示**；配置页只通过网关 `GET /health` 展示 `app_configured/token_configured/allow_cidrs`，用于确认"应用已配置"，并给出策略说明。
  4. **运行期生效**：所有通知读取改走 `get_feishu_config_value / feishu_gateway_url / _feishu_enabled`，保存即生效（无需重启）；删除了模块级 `FEISHU_NOTIFY_*` 常量，杜绝双源。
  5. **hook 化（外挂式）**：`NOTIFY_HOOKS` + `register_notify_hook(name, fn)`；`notify_event` 退化为派发器，遍历已注册通道逐个调用并自吞异常；飞书作为默认通道 `feishu` 注册，业务 8 处调用点零改动。新增钉钉/邮件只需再注册一条通道。
  6. **可单独测试**：`POST /api/admin/feishu-config/test` 给当前管理员发一条真实飞书消息（同步等待网关，失败返 `ok=false` 而不 500），配合 `/api/admin/feishu-config/hooks` 与配置页"发送测试通知"按钮，实现"飞书功能可单独验证、再与 SecureTrans 对接"。
  7. **凭据/审计**：token 只回显掩码（`te****`），掩码回存不覆盖真实值；保存写审计 `update_feishu_config`（token 掩码）、导入写 `import_feishu_config`、自测写 `test_feishu_notify`（失败另记 `notify_failed`）。
- **落点**：
  - `src/app.py`：`FEISHU_ENV_MAP` / `FEISHU_DEFAULTS`、`feishu_config` 表与播种、`get_feishu_config_value`、`_compose_gateway_url` / `feishu_gateway_url` / `feishu_gateway_health_url` / `_feishu_gateway_probe`、`_feishu_enabled` / `_feishu_timeout`、`NOTIFY_HOOKS` 注册表与 `notify_event` 派发器、4 个 admin 接口（GET/PUT/import/test）与 hooks 枚举、`config-overview` 增 `feishu_config` 段。
  - `src/static/index.html`：配置页新增"飞书通知（外挂服务，数据库权威）"卡片（9 字段 + 网关状态灯 + 保存/导入/发送测试通知），i18n 中英双语 `fsConfig.*`；配置总览并入飞书组。
  - `tests/test_api.py`：新增组 27（29 项）——配置组可读/9 项齐备、token 掩码不泄明文、Secret 不在业务机、网关探活、hook 枚举、非法端口/超时 400、保存后 host+port+path 组装、来源标 db、掩码回存不覆盖、运行期生效（DB 地址+原 token 实际到达桩）、关闭开关→skipped 且不发请求、自测 400/200/403 边界、网关不可达优雅失败、审计留痕、配置总览脱敏、配置页可配可见；**全量基线 467 → 496**（496/496 通过，干净库）。
  - 关联：ADR-051（旁路不阻塞/界面可观测）、ADR-052（零出网与网关边界）、ADR-010（配置权威与来源标记）、ADR-005（非硬编码）。


---

## ADR-055 飞书 App 凭据受控下发 + 部门补全（2026-11-27，强制）

- **背景**：
  ① ADR-054 把飞书做成独立配置域，但 App Secret 只允许存在网关 `.env`，导致运维面临"哑巴服务器"问题——每次网关重装/换机都要人工上机输入密钥，若无 AI 参与就没人会配；
  ② 用户要求"配置菜单里能看到能配"，且不希望每次部署都依赖 AI；
  ③ 审批人可能有多位，通知正文若不带提交人部门与"请部门负责人审批"提示，容易出现漏批/重复批（AD 侧 department/title/manager 对现有账号实测全为空，部门只能取自飞书通讯录）。
- **决策**：
  1. **Secret 走受控下发通道，不落业务机**：新增网关 `POST /admin/secret`（仅白名单源 IP + 预共享 token），只接受 `app_id/app_secret` 两键；网关**先向 `open.feishu.cn` 验证凭据**，通过后原子写入其 `.env`（600）并**热重建 SDK 客户端**（无需重启），失败明确返 400/401/403/502 原因。
  2. **业务侧只做内存转发**：`POST /api/admin/feishu-config/secret` 仅 admin，登录态内接收后立即转发，**不落库、不落盘、不回显**；配置页填写后点"下发到网关"，成功即清空输入框。审计只记 `push_feishu_secret`（含 app_id 前 6 位 + 成功/失败），**绝不含密钥正文**。
  3. **部署脚本支持"无人值守升级"**：`deploy-gateway.sh` 增加 `--app-id/--secret-file/--secret`；升级时若本机 `.env` 已有凭据则直接复用，**只更新代码、不再要求输入密钥**（首次部署或轮换才需要人工一次）。
  4. **部门补全放在网关侧（持凭据方）**：业务侧在 `vars` 中新增 `submitter_email`（取自本地邮箱→AD mail），网关对 `submission_pending_l1/l2` 用飞书通讯录 `contact/v3/users` + `departments` 解析部门名，渲染为"提交人部门：X / 请部门负责人进行审批"；**查不到或缺通讯录读权限时该行自动省略，绝不阻塞发送**。
  5. **通讯录读权限最小化**：只需 `contact:contact.base:readonly`（用户基本信息含 department_ids）+ `contact:department.base:readonly`（部门名）；不申请全员敏感字段；权限变更后**必须"创建并发布版本"**才生效（飞书机制）。
  6. **可观测**：网关 `/health` 增 `app_id_masked / contact_readable`，配置页状态灯显示"应用已配 + App ID 掩码 + 通讯录是否可读"，运维无需 AI 即可判断"凭据通不通、部门能不能查"。
  7. **Secret 边界不变**：仍只存两处（开发机 `server_credential.md` + 网关 `.env` 600）；业务机数据库、日志、审计、前端均不得出现明文（TDD 直接读 SQLite 反证）。
- **落点**：
  - `infra/feishu-gateway/notify_app.py`（0.2.0）：`/admin/secret`、运行时热重建客户端、`/health` 扩展、`_lookup_department`（tenant_access_token 缓存 + 部门缓存 1h）、待审批模板按部门条件渲染。
  - `infra/feishu-gateway/deploy-gateway.sh`：凭据来源三选一（env / `--secret-file` / `--secret`），升级沿用本机 `.env`。
  - `src/app.py`：`feishu_gateway_admin_url`、`api_push_feishu_secret`、`_notify_worker` 增 `submitter_email`、探活返回 `app_id_masked/contact_readable`。
  - `src/static/index.html`：配置页新增"App Secret（一次性下发到网关，本系统不保存）"输入 + "下发到网关"按钮 + 结果区 + 部门说明文案（中英 `fsConfig.*`）。
  - `tests/test_api.py`：新增组 28（13 项）——下发成功/网关实收凭据与 token、SQLite 无密钥（不落库）、接口不回显、缺参 400、掩码 400、网关校验失败 ok=false、普通用户 403、网关不可达优雅失败、审计无明文、探活暴露 app_id_masked/通讯录状态、待审批通知携带 `submitter_email`、配置页入口可见；**全量基线 496 → 509**（509/509 通过，干净库）。
  - 关联：ADR-052（网关边界与 Secret 两处存放）、ADR-054（独立配置域）、ADR-051（旁路不阻塞）、ADR-005（非硬编码）。
  - **落点补充（v2.7.5，P1 修复）**：生产实测 6 位一级审批人 → 网关串行投递 ~5.6s，业务侧默认 5s 超时先到，
    **消息已送达却记 `failed`**（界面误导）。修复=①网关 **0.2.1** 并发投递（`ThreadPoolExecutor`，上限 8，
    结果顺序与收件人一致）；②业务侧 `_feishu_timeout()` 默认 5s→**10s**（配置域仍可覆盖 0.5~60s）；
    ③TDD 增补「一级审批人多人时全员投递（收件人=全部一级审批人）」，基线 509→**510**。
    教训：外部投递类旁路的超时必须按"最多收件人 × 单次 RTT"估算，否则会出现"已送达却记失败"的假失败。
  - **落点补充 2（v2.7.6）**：①通知单号改短号 `#<8位hex>`（详情页仍全 ID，A 方案，不引入流水号）；②待审批通知部门取**主部门**（`orders.is_primary_dept`，回退 `department_ids[0]`），名称缺失回退 `i18n_name.zh_cn`；③`submission_status` 模板仅在确有审批人时渲染"X 级审批已通过"，修复提交提示出现"1 级审批已通过（审批人：-）"；④生产容器时区 UTC→`Asia/Shanghai`（`-e TZ` 入 `docker-deploy.sh`，避免 CD 重建后又回 UTC），容器重建需同时带 `SECURETRANS_DATA=/data`、`NAS_ROOT=/nas`、`PATH=/venv/bin:...`（漏 PATH 会 `gunicorn not found`）。

---

## ADR-056 通知可读性收口 + 生产时区 + 外网下载可见性（2026-11-27，v2.7.6，强制）

- **背景**：v2.7.5 上线飞书通知后，生产验收发现四处体验问题——
  ① 通知里"单号"是 `uuid8位_时间戳` 整串，看着像乱码，用户问"我们真有单号吗"；
  ② 一级审批通知缺"提交人部门"行（通讯录 99991672 缺 `contact:contact.base:readonly`），且取的是 `department_ids[0]` 而非主部门；
  ③ 生产容器时区是 UTC（宿主机 CST），通知与审计时间差 8 小时；
  ④ 提交提示出现"1 级审批已通过（审批人：-）"——模板硬写审批人行，而提交事件本就没有审批人。
- **决策**：
  1. 单号采用 **A 案短号**：通知只显示 `#<8位hex>`，不引入 `ST-YYYYMMDD-NNN` 流水号；详情页保留完整 ID。
  2. 部门取 **主部门**：`orders.is_primary_dept` 优先，回退 `department_ids[0]`；名称 `name` 为空回退 `i18n_name.zh_cn`；查不到则整行省略、不阻塞。
  3. `submission_status` 模板**仅在确有审批人时**渲染"X 级审批已通过"，否则只输出"当前状态：…"。
  4. 容器 **`TZ=Asia/Shanghai`**，并固化进 `infra/docker-deploy.sh`（含 `PATH=/venv/bin:...` 与数据卷路径覆盖），避免 CD 重建后退回 UTC 或 `gunicorn not found`。
  5. **外网下载可见性＝提交人本人**（`submitter = current_user`）：业务模型是"自己提交→审批→自己下载"，接收方字段只作记录；**有意不改**为接收方视角。
  6. `/api/health` 的 `resetPassword` 字段保留：reset 语义=回到初始密码，admin 登录后立即改密；不视为漏洞扩大面。
- **落点**：`infra/feishu-gateway/notify_app.py` 0.2.2（短号/主部门/条件模板）、`infra/docker-deploy.sh`（TZ/PATH）、
  生产 `.env`（`TZ=Asia/Shanghai`、`APP_STAGE=release`）、`infra/feishu-gateway/deploy-gateway.sh`（无变更）；
  文档：ADR-055 落点补充 2、PRD §11–§12、docs/05–06、docs/13 D1–D6、README/AGENTS/DEPLOY 同步。
- **验证**：全量 TDD 510/510；生产冒烟 11/11；容器 `date`=CST；`submission_pending_l1 sent=6 failed=0`、`department=软件开发部`；
  外网面 `jintao` 可见自己 2 单（`admin` 为空属正常）。
- **教训**：①"看起来像乱码"往往不是显示 bug 而是**标识设计**缺一层；②外部依赖的权限按官方返回的**最小必要**申请，别把错误串里的所有 scope 当清单（本次误报 3 个不存在的 scope）；③容器形态下时区/路径/PATH 是**部署参数**，不写进脚本就会在下次重建时复发。
