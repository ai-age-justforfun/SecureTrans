# SecureTrans 项目 AI 协作指南（v2.0）

> 本文件指导 AI Agent 在本项目中的协作行为。Part A 是**可复用于后续项目的 AI 辅助软件工程方法**
> （人机协同分工 + Prompt 模板 + 敏捷/TDD/CICD 最佳实践）；Part B 是 SecureTrans 项目特定规范。
> 版本：v2.0（2026-09-11，项目复盘后升级——首个 AI 辅助人机协同项目的方法论沉淀）

---

# Part A：AI 辅助软件工程方法（方法论，可复用）

## A1 人机协同分工模型

| 角色 | 人（PO/架构） | AI（执行/建议） |
|------|--------------|----------------|
| 需求 | 定义目标、优先级、验收意图 | 拆 Story、写验收标准草案、识别隐含需求 |
| 设计 | 拍板技术路线、关键决策 | 出方案对比（表格）、ADR 草稿、风险评估 |
| 开发 | 审核、合入、发布决策 | 编码、测试、文档、修复 |
| 测试 | 定测试意图与边界 | 全量回归、补测试、性能验证 |
| 验证 | 人工走查、最终验收 | 冒烟、走查清单、证据整理 |
| 复盘 | 判断方向、定下一步 | 数据汇总、经验沉淀、教训提取 |

**核心原则**：AI 永远给"推荐 + 理由 + 代价"，人来拍板；AI 不擅自扩大范围，
只改被点名的范围；拿不准就问（一次问清，不把互斥分支丢给人）。

## A2 AI 工作流（每项任务必走：探查 → 约束 → 证据 → 执行 → 验证 → 交付）

1. **探查**：先读全需求指定输入（文档/代码/附件），不跳读；核实版本/名词/接口，不猜。
2. **约束**：用户点名的技术栈/结构/交付形态是硬约束，偏离需先说明；只改点名范围。
3. **证据**：每个数字有来源（输入/信源/可复现计算），外部事实附来源，区分已查证/一方称。
4. **执行**：用真实工具真实执行；受阻换通道（换命令/目录/依赖/路径），不降级交付物。
5. **验证**：用"可能失败"的方式回读（跑测试/构建/真实入口/渲染/重算），验证通过才完成。
6. **交付**：写明产物名、路径、打开方式；交付通道改变后重新验证可访问性。

**受阻规则**：同一动作失败两次 → 换通道；warning 伴成功也要处理；同类错误再出现查共同成因。

## A3 Prompt 工程：任务卡模板（规范模版化）

给 AI 派任务统一用**任务卡**，六要素齐全，AI 按卡执行、按卡验收：

```markdown
## 任务卡
【类型】story 实现 / bug 修复 / 设计评审 / 代码评审 / 测试补充 / 部署 / 复盘 / 文档
【目标】一句话可验收的目标
【上下文】相关文件路径 / 接口 / 数据 / 历史决策（ADR 编号）
【约束】技术栈 / 规范 / 只改范围 / 禁止项（如"不得改动 X"）
【验收标准】可逐项打勾的清单（可测试、可观察）
【交付形态】文件路径 / 代码 / 文档 / 报告（明确载体）
```

**验收标准写法**（必须是可执行断言，不是形容词）：
- ❌ "性能要好" → ✅ "800MB 上传 ≤ 10s，摆渡 ≤ 1s，MD5 四方一致"
- ❌ "修复登录问题" → ✅ "admin 用 .env RESET_PASSWORD 登录成功；错误密码 401；verify.sh 通过"

**AI 回复格式**（复杂任务）：
```
结论（先给）→ 证据/依据 → 执行记录 → 验证结果 → 遗留/风险
```

## A4 敏捷（Scrum/Story）中的 AI 参与点

| Scrum 环节 | AI 做什么 | 输出 |
|-----------|----------|------|
| Sprint Planning | 拆 Story（用户故事格式）、排优先级、写验收标准 | Story 列表（ST-xxx） |
| 设计 | 技术方案对比表、API 定义、ADR 草稿 | docs/ + ADR |
| 开发 | TDD 编码（先写测试→实现→回归）、原子化 commit | 代码 + 提交 |
| 测试 | 全量回归、补测试用例、性能/边界验证 | test_api.py / 报告 |
| Sprint Review | 走查清单、演示准备、PO 验收证据 | 验证记录 |
| Retrospective | 数据汇总（提交/测试/缺陷）、教训提取、行动项 | docs/07-xxx-retrospective.md |

**Story 规范**：`作为<角色>，可以<动作>，以便<价值>`；Story 关联验收标准；
**Sprint 是研发分解阶段**——体现在过程文档，不体现在分支名/目录名/commit 编号。

## A5 TDD 与 AI（质量底线）

- **测试先行**：新增功能先写测试用例（test_api.py 对应组），再实现，再全量回归
- **测试只增不减**：计数基线门禁（全量 ≥300 / 冒烟 ==10），防静默删减
- **测试要覆盖用户真实链路**：不只测 API，还要测前端调用链（弹窗→接口→权限→界面）
- **生产零写**：生产环境只跑只读冒烟（smoke.sh 白名单），全量 TDD 只在 dev/test/CI
- **三环境基线**：Windows dev + WSL test 全量 100% 通过才允许 bump 版本

## A6 CICD 与 AI（GitOps）

- **CI 必须可信**：有测试输出才叫通过；"绿色但没跑"= 假绿，必须取证（进程/日志/输出）
- **CI 独立容器**：每次 job 全新容器 + 新配置 + 新数据（防逃逸、防版本干扰）
- **配置单一来源**：env/*.env 唯一键源 + 键一致性门禁（CI 与 .env 两路信息一致）
- **CD 安全**：密钥走 repo secret 不入仓库；部署保留 .env/data/nas/venv；生产只读冒烟
- **发布即版本**：代码变更才 bump + Release + tag；文档-only 变更只 commit push

## A7 质量门禁与验收（发布前必过）

```
1. 静态检查（语法/未定义名/重复定义/未使用 import）
2. 版本号一致性（app.py ↔ index.html ↔ 文档）
3. env 键一致性（dev/test 键集合一致，prod 可多不可缺）
4. 脚本完整性 + bash -n 语法
5. 全量 TDD 双环境 100%（Windows dev + WSL test）
6. 冒烟 11/11（生产只读）
7. 文档同步审计（README/AGENTS/DEPLOY 与代码一致）
8. 发布：package.sh + release.ps1 + git tag
```

## A8 本项目沉淀的 Prompt/协作最佳实践（复用清单）

1. **凭据/配置永远给单一来源**，跨脚本跨页面强制统一（本项目：RESET_PASSWORD 唯一源）
2. **三环境路径配置一致**，能本地复现的问题不带进生产（12-Factor 一体化）
3. **排障要取证**：run 级日志、进程证据、复现脚本，不靠猜（本项目 CI 假绿排查范式）
4. **配置要有权威矩阵 + 可视化总览**，杜绝"改了没生效"
5. **运维功能进系统**：运维期有用的功能应收尽收（Web API + 界面 + TDD 可调），脚本只留首部署/离线
6. **文档与代码同源演进**：决策写 ADR（背景/决策/落点三段式），三处同步
7. **安全第一**：生产数据不碰（只读冒烟）、测试不碰真实密码、部署前自动备份
8. **发布节奏明确**：文档-only 不发布、代码才发布、关键里程碑手工发布
9. **复盘是阶段小结**：聚焦关键结论 + 数据 + 教训 + 行动项，不追求大公司级完美

---

# Part B：SecureTrans 项目规范（项目特定，与 README 同步）

## B1 项目概况

- **项目**：SecureTrans — 轻量级跨网文件审批摆渡系统（内网提交/审批 → 外网下载）
- **阶段/版本**：PSF→Beta（v2.6.0，APP_STAGE=beta；版本号单一来源 `src/app.py` APP_VERSION，前端 index.html 同步）
- **技术栈**：Flask 3.0 + Flask-Login + SQLite + os.rename 0拷贝；Python 3.12 venv
- **架构**：后端单文件 `src/app.py`，前端单页 `src/static/index.html`（i18n 双语）
- **开发模式**：主干开发，单分支 main；Sprint 只进文档不进目录/commit
- **部署**：封闭数据中心，Rocky 8.10 单网卡 10.10.30.8，gunicorn + systemd

## B2 代码规范

- **后端**：单文件 app.py；配置全部 os.getenv（.env 覆盖，默认值仅 fallback）；SQLite 标准库无 ORM；
  Flask-Login 认证（本地 + AD ldap3 直连，AD 配置运行期读 SQLite ad_config，ADR-010）；
  文件摆渡**必须 os.rename**（禁 shutil.move）；大文件流式读取边算 MD5；模块级 init_db/start_scheduler（gunicorn 导入不执行 __main__）
- **前端**：SPA 单文件；fetch 同源相对路径；i18n 双语（I18N 字典 + t() + applyI18n()，localStorage 记忆默认中文）；
  时间统一服务器系统时区；业务数据（文件名/姓名）不翻译
- **权限**：仅 admin 管理配置；普通用户提交/审批（approvers 表配置）；后端每个管理接口必须 @role_required；
  前端只做体验优化，权限以后端为准
- **Git 提交**：`<type>(<scope>): <描述>`（feat/fix/docs/refactor/test/chore/ci），原子化，不强制 Sprint 编号，可关联 Story

## B3 文档规范

| 文档 | 位置 | 更新时机 |
|------|------|---------|
| 项目入口 | README.md（人+AI） | 概况变更时 |
| AI 协作指南 | AGENTS.md（本文件） | 规范变更时 |
| PRD | docs/02-prd.md（文件名不带版本号） | 需求变更时 |
| 测试用例/报告 | docs/05-test-cases.md / 06-test-report.md | 功能/测试变更时 |
| 迭代小结 | docs/07-psf-sprintN-retrospective.md | 每个 Sprint 结束 |
| 部署指南（唯一） | docs/DEPLOY.md | 部署流程变更时 |
| 复盘总结 | docs/12-project-retrospective.md | 阶段里程碑 |
| GitHub 迁移方案（Active，v2.6.6 首验落地） | docs/14-github-migration.md | GitHub 独立闭环已打通：CI-TDD（GitHub-hosted）+ RELEASE（云端构建 4 资产）+ CD-SIM（ubuntu 云端 Docker 仿真+数据洁净门禁，无本地 Docker/self-hosted runner） |

**文档原则**：聚焦关键内容；文件名不含版本号（版本写文档内，关键变更用 git tag）；
ADR 三段式（背景/决策/落点）；README/AGENTS/DEPLOY 三处同步。

## B4 技术决策（ADR 摘要）

**完整全文与全部条目见 `docs/ADR.md`（唯一权威，与 PRD 并列）**；README 只有索引表。关键强制项摘要：
- **ADR-005 非硬编码**：新增代码/脚本禁止写死地址/端口/网段/路径，必须从 .env 或运行环境读取
- **ADR-007 发布策略**：文档-only 不发布；代码才 bump+打包+Release+tag；调测门禁=双环境 TDD 全量 100%
- **ADR-009 部署凭据**：`.env RESET_PASSWORD`（默认 Init@123456）唯一源；禁止出现第二份默认密码；
  每次部署重置 admin 密码；verify/smoke 凭据自适应；测试不碰真实密码（专用 testpwuser）
- **ADR-010 配置权威**：部署级 .env 唯一 / 运行时 SQLite 唯一不回写 / AD 配置 SQLite 权威（空表从 .env 播种一次）；
  配置总览页标来源 env/db；DB 优先
- **ADR-011 数据生命周期**：备份/恢复/出厂重置/模拟数据进系统工具（确认码 RESTORE/RESET/MOCK）；
  备份拆分 system（仅DB）/ business（仅NAS），名字即类型；mock 仅 testing 环境
- **ADR-017 测试隔离**：verify.sh=全量（dev/test/CI）；smoke.sh=生产只读白名单 11 项；ENV_ROLE fail-safe
- **ADR-018 CI 门禁**：fast-check 秒级前置；计数基线 全量≥300 / 冒烟==10
- **ADR-024 CD**：Release → 容器 job → MD5 → scp → cd-deploy.sh → 冒烟；CD_SSH_KEY 走 repo secret
- **ADR-025 流程规范**：AGENTS.md Part A=AI 辅助软件工程方法唯一来源；任务卡模板 + 六步工作流 + 发布前门禁
- **ADR-026 git 为中心**：三环境各自独立 git 副本，唯一同步通道=Gitea；WSL 禁用 /mnt/c、/mnt/d 用原生路径；
  /opt/securetrans/.runner + config.yaml 保护（备份/清理禁止移动删除）
- **ADR-027 双闭环复盘**：nginx 暂不引入（日均个位数访问，触发条件=worker阻塞/对外HTTPS）；PSF 只做"被使用验证的需求"，推演特性标假设；beta=PSF 收尾→PMF 万里长征第一步；stepping-stone 方法论，技术债显式记账+偿还触发；人机协同过程/体会留痕=决策资产
- **ADR-028 v2.5.1 落点**：Vivado 规则精简为唯一组合规则（同步字 AND .bin/.bit）+ .ltx 扩展名规则（旧 .bit 独立规则/仅同步字规则删除，迁移清理）；公司内部/合作方一级通过不产生二级审批记录（审计链修复+历史幻影记录清理，语义B仅限非合作方）；性能并发 story（perf_test.py PERF_CONCURRENCY 3-5 用户）；提交页取消/清空按钮；AD mock 三环境审计（dev/test/CI=true、生产=false，组23自动探测）
- **ADR-029 v2.6.0 落点**：压缩包双规则合并（内置 21→15 条：ZIP/TAR/GZIP/BZIP2/XZ/ZSTD 各自唯一组合规则=特征码 AND 后缀，TAR.GZ 保留；迁移 `_merge_pairs` 精确删除 13 条旧内置模板，用户规则不受影响）；.ltx 升级组合规则（JSON 根键 hex:7B226C74785F726F6F74 AND .ltx）；特征码启用/禁用配置持久化（删除升级重置 enabled=0 逻辑，管理员配置跨版本保留，默认禁用仅首次播种）；免审批判定修复（check_auto_approval 必须传文件真实路径，binary/组合规则才可命中；files_info 携带 path，旧格式兼容）；测试教训=用例命名避开 is_partner 子串匹配（改用例名"新合作方自动加入测试"）
- **ADR-030 v2.6.1 落点**：.ltx 特征码改文本 `"ltx_root"`（真实 Vivado 为格式化 JSON `{\n    "ltx_root":`，旧紧凑 hex 不命中；迁移精确更新内置模板，10b3 回归：格式化+紧凑+负向）；性能门禁入 CI（ci_test.sh [3.5/4] 每次跑 100MB 全链路+3 用户并发，秒级断言）；Release body 自动生成近版变更摘要（clone depth 30 + git log，不再只写"自动发布"）；admin 默认审批人仅首次播种（approvers_initialized 标记，置位后永不补回，无审批人提交失败提醒已有）；审计留痕口径（TDD 报告/CI run/Release body/CD 日志/生产只读冒烟各环节留痕）；WSL 测试=CI 容器合一（同一镜像同一全量 TDD，差异仅数据持久性）
- **ADR-031 v2.6.2 落点**：合作方全量编辑（PUT /api/admin/partners/<id>：名称/联系人/邮箱，去重排除自身 COLLATE NOCASE，前端编辑按钮+弹窗，TDD 6 项）；WSL 常驻测试环境退居二线（测试执行收敛 dev+CI 两环境，WSL 仅作 CI 容器宿主与 Linux 排查入口，ADR-026 修订）；生产只读冒烟=业界标准（healthz+版本+目录校验为 CD 门禁，smoke.sh 只读 11 项，写测试数据只在测试环境）
- **ADR-032 v2.6.3 落点**：合作方联系人必填（创建/编辑 400"联系人不能为空"，前端 * 标记+强制检查，自动加入路径天然非空不受影响）；无状态上传明示（未提交刷新即弃，写入 PRD）+ 未提交临时文件系统级回收（cleanup_abandoned_temp：staging 无提交记录目录超时 TEMP_FILE_HOURS 默认 24h 直接删除不归档不审计；每天 2:10 定时 + /api/admin/cleanup-expired 手动合并，双语返回）；文档体系单源化（docs/ADR.md 唯一权威，README 索引表+落点摘要，AGENTS B4 摘要+引用）
- **ADR-041 v2.7.0 落点（发布链路回归修复）**：新增镜像资产后两处单值假设失效——release.yml `ls *.tar.gz | head -1` 字母序选中 -image 包致错误 tag `v2.7.0-image` 且主包丢失；cd.yml `endswith(.tar.gz.md5)` 同命中主包与镜像 md5 致 curl exit 3。修复=版本号一律从 src/app.py APP_VERSION 精确提取、资产精确匹配（==），禁止通配/前缀反推；教训=发布链路新增同前缀资产必须审计全部通配匹配并跑通 Release→CD 端到端
- **ADR-040 v2.7.0 落点（运行稳定性）**：WSL（rocky10-ci）systemd 非 PID1、被 Microsoft init 空闲终止机制周期关闭（官方 15s 终止超时；需活跃子进程），连带杀死 act_runner systemd service。修复双保险=Windows 计划任务无窗口 VBS 保活（每分钟 wsl sleep 45，规避 ADR-021 弹窗）+ act_runner 脱离 systemd 改 nohup 直跑（WSL init 直接子进程）；故障 job 幂等 rerun 恢复
- **ADR-039 v2.7.0 决策（架构修订，RC 启动）**：kaniko 废弃（v1.23.2/v1.24.0 在本地宿主构建 Debian apt postinst 报 GLIBC_2.38 失败、--use-new-run 卡死）→ Gitea release job 容器内 docker-ce-cli + act_runner `container.options: -v /var/run/docker.sock:/var/run/docker.sock` 挂载宿主 socket → 本地 WSL docker daemon 构建（runc 完整隔离，可信代码模型）；WSL 测试宿主重建为真实 Rocky 10.1（rocky10-ci，glibc 2.39，旧 rocky10-st 保留回滚）；**v2.7.0 阶段 = rc（Release Candidate）**，生产 .env APP_STAGE=rc
- **ADR-038 v2.7.0 前决策（架构，RC 准备）**：Docker 一站式交付=发布第 5 资产 image.tar.gz（FROM python:3.12.11-slim-bookworm 固定防漂移，ABI 兼容归一化，任何 Linux+docker/podman 一条命令部署）；生产 Rocky 8.10 已预装 podman 4.9 免装 docker；蓝绿部署=容器 18000 与原生 8000 分离、共享生产数据路径（ADR-038-3/4）；Gitea 镜像构建原走 kaniko 无特权（**已被 ADR-039 替代**）；GitHub 侧镜像分发业界最佳实践=GHCR（ghcr.io，GitHub 账号即 registry 账号、GITHUB_TOKEN 免注册认证、public 免费），Release 附件 image.tar.gz 保留为封闭数据中心离线兜底。**2026-09-15 实证落点**：本地 WSL docker 全量 TDD 403/403（卷映射+uid 973 模拟）；生产 18000 蓝绿部署成功（podman load → --user 973:972 → health v2.7.0/rc/ok，容器可见共享数据 external=34/staging=21）；docker-deploy.sh 增强=uid/gid 自动适配宿主数据属主（--user）、镜像 tag 从 load 输出自动解析、ENV_ROLE 可覆盖（默认 production）；env 模板内联注释与 docker --env-file 不兼容（dev/test 需清洗，生产 .env 干净）；蓝绿验收后必须停 8000 或 18000 其一（共享 SQLite 并发写）
- **ADR-037 v2.6.7 落点（架构）**：环境职责分层=测试层（WSL+CI 合一，全量 TDD+mock）→ 发布层（逻辑/权限隔离非物理独立，release job 持写凭据）→ CD 层（生产只读冒烟 + GitHub 云端仿真，物理隔离）；CI=完整门禁、Release=只发布、CD=只部署（Gitea ci.yml/release.yml/cd.yml 与 GitHub 三 workflow 职责对齐）；权限隔离=secret 最小作用域（RELEASETOKEN 仅 release、CD_SSH_KEY 仅 cd）+ 每 job 全新容器/VM + 事件链权限上下文；环境即代码（FROM python:3.12-slim 官方镜像，CI/CD 免手工装 Python，生产裸机走 deploy.sh+offline-python）
- **ADR-036 v2.6.6 落点（架构）**：单一权威仓库（Gitea=所有 git 操作与生产 CD 的唯一权威）+ 备份仓库（GitHub=容灾/分发/独立验证 CI-TDD+CD-SIM）；每个阶段聚焦主要矛盾、其余跟随调整形成动态平衡；备份仓永不接触生产；切换权威的触发条件=开源/协作主点迁移/本地不可用（docs/14 为执行手册）
- **发布资产双传（2026-09-15）**：GitHub Release 资产与 Gitea 对齐（主包+md5+sha256+offline-deps），脚本化双传（docs/14 §6）
- **ADR-035 v2.6.6 落点**：管理员附件审查下载（GET /api/admin/submissions/<id>/download/<filename>，仅 admin、仅内网（外网白名单 403）、任意状态可审、路径穿越防护、审计 admin_download）+ 环境前置检查 preflight（infra/preflight.sh：文件/脚本完整性、Python3.12、依赖可导入、版本双源一致、端口占用、残留目录清理；已接入 Gitea/GitHub CI 第一步，FAIL 即阻断）
- **ADR-034 v2.6.5 落点**：有效期口径统一——提交未审批（pending，从提交时间起算）与审批未下载（approved/downloaded，从审批时间起算）统一按系统配置"文件有效期"（default_expiry_days）超时自动归档（os.rename 0拷贝，终态）；上传未提交临时清理保持独立（TEMP_FILE_HOURS=24h，ADR-033 不审计）；system_archive_expired detail 区分"提交后 N 天未审批" / "审批通过后 N 天未下载/处理"；审批人测试组幂等清理历史 approvers 残留
- **ADR-033 v2.6.4 落点**：审计策略——系统动作审计边界。已审批未下载超时归档逐单写审计（action=system_archive_expired，user=system，detail 明示"超时归档：审批通过后 N 天未下载，达到有效期 M 天"）；管理员手动清理写审计（admin_cleanup_manual，user=操作者）；未提交临时文件清理**不写审计**（从未入库无业务动作，纯存储清理，TDD 反向断言 system_cleanup_temp=0）。统一原则：审计覆盖"用户/管理员动作 + 涉及业务数据的定时系统动作"，纯垃圾清理只记运行日志。

## B5 研发流程

**Lean Startup**：PSF（当前，1周 Sprint）→ PMF（2周 Sprint，docs/04 已就绪）→ Scale。
**Agile-Scrum 模板（v2.0，docs/01，AI 辅助裁剪版）**：人=PO/SM（决策/验收/流程守护），AI=Developers（编码/测试/文档/CI）。
**事件**：Sprint Planning（≤1h，定 Goal+选 Story+确认验收）→ 实施（设计/开发/测试并行，TDD+CI）→ Sprint Review（PO 验收+Backlog 调整）→ Retrospective（复盘 ≤3 行动项+假设/技术债刷新）。
**裁剪**：站会=人机协同站会（每日 3-5 分钟，AI 摘要人决策，提示词模板 docs/01 §9.1）；
看板=轻量每日一览表（docs/01 §9.2，不引入看板软件）；估算 XS/S/M/L；
Sprint 周期 2周→1周→1-2天，以协同效率为准演进（人审核是瓶颈则回退）。
**承诺**：Product Goal（当前=PSF beta 真实使用）；Sprint Goal 期内不可变；DoD=代码提交+TDD+CI 全绿+双环境回归+文档同步+可部署（docs/01 §五）。
**每 Sprint 交付**：可部署 Increment + 复盘 + 假设/技术债刷新 + push main + 按需发布。
**假设纪律（ADR-027）**：推演特性标假设（docs/13），证据成立才进 Sprint。

## B6 测试规范

- **全量 TDD**：`tests/test_api.py`（361 项，标准库 urllib 无额外依赖）；启动服务后 `cd tests && python test_api.py`
- **部署验证**：`infra/verify.sh`（BASE_URL 自适应 .env HOST/PORT；admin 凭据自动取 RESET_PASSWORD，
  手工改密后 `VERIFY_ADMIN_PASS=<密码> bash infra/verify.sh`）
- **生产冒烟**：`infra/smoke.sh`（只读白名单 11 项，不写业务数据；凭据同 verify）
- **性能**：`tests/perf_test.py`（800MB 阈值断言 + MD5 四方一致）
- **新增功能必加测试**：test_api.py 对应组 + 文档 + i18n 字典
- **环境路径（ADR-026）**：WSL 测试/运行一律原生路径（/opt/securetrans），禁止 /mnt/c、/mnt/d；
  同步走 git（push/pull），禁止 rsync/scp 直拷代码目录

## B7 部署规范

- **一键部署**：`sudo bash infra/deploy.sh`（Python 3.12 三级获取：系统→offline-python RPM→dnf；
  依赖在线优先→离线 wheelhouse 回退；NAS_ROOT 自适应；systemd ReadWritePaths 按 NAS 存在性渲染）
- **配置生效**：改 .env 后 `sudo systemctl restart securetrans` 即生效（systemd EnvironmentFile + 变量展开），无需重跑部署
- **双模式**：DEPLOY_MODE=testing（本地文件系统+Flask）/ production（NAS+gunicorn+systemd）
- **网络面**：单网卡源网段分面（INTERNAL_CIDRS）；外网仅登录+下载，管理接口 403
- **发布**：`bash infra/package.sh <版本>` → `powershell -File infra/release.ps1 -Version v<版本>` → Gitea Release（源码包+offline-deps+md5/sha256）
- **CD**：Release 发布自动部署生产（cd.yml）；手动触发/停止方式见 DEPLOY.md 5.6
- **数据生命周期**：系统工具页（在线）/ ops-*.sh（离线脚本）；出厂重置自动先备份
- **脚本要求**：LF 换行（禁 CRLF），修改后 `bash -n` 语法检查

## B8 安全规范

- bcrypt 哈希存储密码；SECRET_KEY 走 .env；管理接口必须 @role_required；关键操作审计日志；
  MAX_CONTENT_LENGTH 自动=文件上限+1MB；HTTPOnly cookie + SameSite=Lax；
  上传文件名 basename 清理（防路径穿越）；AD 用户改密前端拦截（到域控制器）

## B9 常见陷阱

1. 摆渡必须 os.rename，禁 shutil.move（跨目录退化为复制）
2. init_db/start_scheduler 必须模块级（gunicorn 不执行 __main__）
3. venv / data/ / nas/ / .env 不入 Git（部署时重建/生成）
4. 前端不做权限校验（体验优化而已，后端必须校验）
5. shell 脚本禁 CRLF；Sprint 不进分支名/目录名/commit 编号
6. 改 .env 不需要重跑部署（restart 即可）
7. verify.sh 自动适配 BASE_URL，不要在服务器手传 127.0.0.1
8. 测试/冒烟凭据取 RESET_PASSWORD，改密后用 VERIFY_ADMIN_PASS 传入
9. 生产只跑冒烟不跑全量（防数据污染）；出厂重置前自动备份
10. 新增测试只增不减（计数门禁）；CI 无测试输出=假绿

---

*AGENTS.md v2.0 | 2026-09-11 | Part A 方法论可复用于后续项目；Part B 与 README/ADRs 同步*
