# AI 时代人机协同 Agile 方法论模板（v3.0）

> 版本：v3.0 | 日期：2026-09-15 | 适用：SecureTrans 及后续项目（PSF/PMF/Scale 通用）
> 升级记录：v2.0（2026-09-14，AI 辅助 Scrum 裁剪版）→ v3.0（2026-09-15，融合"AI 时代人机协同 Agile 方法论"：
> SE 3.0 范式、循环迭代流程、L1/L2/L3 变更分级、HITL/HOTL/HOOTL 三重范式、PDCA 超级XP微循环、RTM 缓冲并入 Agile、防眩晕机制）
> 定位：**模板本体**，指导本项目与下一个项目的开发/迭代演进；人机协作契约见 AGENTS.md Part A（与本文档同步演进）。
> 原则：保留 Scrum 经验主义内核（透明/检视/适应）；裁剪人机协同下无收益的形式；传统敏捷的"实现细节"已被 AI 颠覆，
> 但"概念内核"（Sprint/Review/Retro/DoD/经验主义）继续沿用——本模板是**以 AI 为中心**的人机协同 Scrum。

---

## 〇、范式转换：SE 2.0 → SE 3.0（为什么传统敏捷被颠覆）

- **SE 3.0（Agentic Software Engineering）**：工作单元从 User Story → **Technical Goal**；主要工件从可工作软件 → **Specification（规格说明）**；
  认知分布在**人（意图/监督/战略）+ Agent（执行/并行探索）**；团队拓扑从跨职能小组 → **N-to-N 人机网络**。
- 传统敏捷的"实现细节"（站会仪式、看板软件、点数估算、多人协作节奏）大部分被 AI 替代或简化；但**经验主义内核保留**：
  透明（全量 TDD+CI 取证）/ 检视（Review/Retro）/ 适应（Backlog 精化、变更分级）。
- **人的"慢"是特征不是缺陷**：HITL 保证关键决策由人把关；HOTL 让 AI 在边界内自主执行；HOOTL 处理低风险重复任务。

---

## 一、循环迭代的端到端流程（非分层，是一个循环）

```text
Design Thinking（人主导，AI 辅助）
    ↓ 定义问题、用户、价值假设（用户旅程图/竞品分析/Opportunity Solution Tree，AI 出草稿）
Lean Startup（人机协同）
    ↓ Build-Measure-Learn 极致压缩（MVP-PSF 小时级迭代；AI 加速 Build/Measure，人主导 Learn/Pivot）
Agile + 超级XP微循环（含 RTM 缓冲，AI 主力执行）
    ↓ 分钟级 Story 闭环，单 Agent 执行，PDCA 驱动（见 §五）
DevOps/GitOps（全自动）
    ↓ CICD、自动部署、TDD 回归（门禁逻辑 infra/*.sh 平台无关，三平台 workflow 只是壳，ADR-037/047）
Release（人决策，渐进式交付）
    ↓ 蓝绿/金丝雀/灰度 rollout，feature flag 控制可见性，Git tag 审计链（ADR-043/047）
    ↓ 回流到 PRD/ADR → 下一轮迭代
```

- 参考 IBM Garage Method：Design Thinking + Lean Startup + Agile + DevSecOps + SRE 整合为单一端到端交付框架，
  核心逻辑 = 对齐结果 → 与用户共创 → 构建最小有价值的东西 → 快速学习 → 自动化到生产的路径 → 规模化有效的东西。
- **关键原则**：快速验证 ≠ 频繁转向；Learn 环节（从数据提取洞察、判断 Pivot）由人主导。

---

## 二、人机协同范式（HITL / HOTL / HOOTL + HIC 责任原则）

| 范式 | 全称 | 人类角色 | AI 角色 | 适用场景 |
|------|------|---------|---------|---------|
| **HITL** | Human-in-the-Loop | 必须审批/决策 | 执行+分析+建议 | L3 变更、架构决策、发布、验收 |
| **HOTL** | Human-on-the-Loop | 监督/抽查（不逐条） | 自主执行+留痕 | L2 变更、Story 实现、常规测试 |
| **HOOTL** | Human-out-of-the-Loop | 只看结果摘要 | 全自动+留痕 | L1 变更、CI/CD 流水线、低风险重复任务 |
| **HIC** | Human-in-Charge | **始终对结果负责**（即使全自动） | 任意 | **责任范式（第 4 维度）**：贯穿所有级别 |

> **范式说明（业界审核，2026-09-16）**：HITL/HOTL/HOOTL 为业界主流三范式（源自 2012 年 Human Rights Watch
> 自主武器报告，按"人类是否在决策路径内/上/外"划分，是**过程干预模式**）；**HIC 不是与之同级的运行模式，
> 而是责任归属/治理原则**——无论 AI 处于哪种 loop，人类始终对系统行为与结果负责，因此用得相对少
> （它是底线承诺，不是每步都体现的模式）。本项目用法：**运行模式由变更级别决定（§三），HIC 作为 HITL/HOTL/HOOTL
> 之上的人类最终责任背书**——即使 HOOTL 全自动（如 CI 流水线），发布决策与结果责任仍归人（ADR-047）。
> 范式由**变更级别**决定（见 §三），不是由人心情决定。

---

## 三、变更分级 L1/L2/L3（整个流程的"交通规则"）

**判断标准：影响半径 + 可逆性（不是频率）**。正规流程是**事件触发**（L3 才触发），不是频率触发。

| 级别 | 判断标准 | 流程 | 人机范式 |
|------|---------|------|---------|
| **L1 执行内微调** | 不影响验收标准/PRD/架构，可逆 | 无正式流程，Git commit 即记录 | HOOTL（AI 完全自主） |
| **L2 Story/Feature 边界调整** | 影响单个 Feature/Epic 内部 | 更新 PRD 中 Story 结构，AI 摘要标记 | HOTL（AI 自主，人监督） |
| **L3 范围/架构级变更** | 影响 PRD 核心需求、Epic、架构、Sprint Goal，或不可逆 | **暂停，人类确认**，更新 PRD+ADR+AGENTS | HITL/HIC（人必须审批） |

- 提交规范携带级别标记：`feat(auth): xxx [L2]`（可关联 Story）
- AI 执行中识别到 L3 倾向 → **必须停下请求人决策**，不得自作主张扩大范围（呼应 AGENTS A1 核心原则）

---

## 四、人机 Accountability 映射（Scrum 团队裁剪版）

| Scrum Guide 2020 | 本项目映射 | 职责 | 范式 |
|------------------|-----------|------|------|
| Product Owner（产品负责人） | **人（你）** | 需求决策、优先级、验收、Product Goal 定义 | HITL |
| Scrum Master（流程守护） | **人（你）** + AI 辅助 | 流程纪律、障碍排除；AI 提供流程检查清单/审计提醒 | HOTL |
| Developers（开发者） | **AI 主力 + 人审核** | AI：编码/测试/文档初稿/CI 执行；人：审核/联调/最终决定 | HOTL/HOOTL |

> 关键：**AI 是 Developers 的一员，不是替代 PO/SM**。所有"决策/验收/优先级"保留给人（HITL）；
> AI 负责"执行/建议/留痕"。任何 AI 产出必须有人工验收环节（Story 验收标准 = 可执行断言）。

---

## 五、事件（裁剪后，含超级XP微循环与 RTM 缓冲）

### Sprint（固定 1 周 / 2 周，PSF 用 1 周，PMF 用 2 周）
**Sprint 长度一经确定，期内不改变。** 目标是产出**可部署的 Increment**（ADR-007：代码变更才发布；文档-only 不 bump）。

**周期演进策略（以人机协同效率为准）**：
- 基线：当前 PSF 用 **1 周 Sprint**；稳定 2-3 个 Sprint 后试 **3 天 mini-Sprint**；再稳定后可试 **1-2 天**
- 判断依据：参考 AI 能力（AI 执行快 → 周期可缩短；**人审核/验收是瓶颈 → 保持或回退**）
- 回退信号：Review/Retro 无实质内容、Deploy/CI 跟不上节奏、"交付节奏感"丢失 → 立即回退上一档
- 原则：Sprint 长度一致（期内不变），宁可短而实，不搞长而空

### 1. Sprint Planning（规划，Sprint 第 1 天，≤1 小时）
- 人：确认 **Sprint Goal**（一句话）+ 从 Product Backlog 选 Story + 确认验收标准
- AI：按 Goal 拆 Story、粗估（XS/S/M/L）、标记依赖/风险、检查 Backlog 假设状态（ADR-027）
- **输入**：Product Backlog（Gitea Issues）、上次复盘行动项、Lean Startup 阶段目标
- **输出**：Sprint Backlog（Gitea Milestone+Issues）、Sprint Goal、Story 验收标准
- **质量门**：P0 Story 全纳入；总容量 ≤80%；**推演假设（docs/13）无证据不得入 Sprint**

### 2. 实施（Sprint 第 1-5 天，= 超级XP PDCA 微循环）
- **微循环（分钟级 Story 闭环，单 Agent 执行）**——PDCA 四步，人机分工明确：
  ```
  Plan（人）   定义意图、验收标准、变更级别（L1/L2/L3）→ 交付给 AI
    ↓
  Do（AI）     影响扫描（ADR/相关文件/测试组）→ 执行 → 测试 → 更新工件 → 提交
    ↓
  Check（人）  验证测试是否真实覆盖验收标准（不只"测试绿"，要"测的是对的"）
    ↓
  Act（人）    接受 / 回滚 / 升级（转专项） / 调整流程（改约束/验收/分级）
    ↓（接受则进入下一微循环；不满足则回到 Do）
  ```
  - 每个 Story 一个微循环；多个微循环组成 Sprint 实施；人作为**主动监督者**（巡检 AI 摘要，半天一次）
  - **变更级别在 Plan 步定义**（L3 必须人先确认再 Do）；Do 步 AI 先做影响扫描（防止范围蔓延）
  - **Check 步是质量关键**：验证"测试真实覆盖验收标准"（ADV 反例：CI 绿但测错对象 = 假绿，ADR-018）
- 设计：复杂 Story 出方案 + ADR（仅架构级决策，PSF 小功能跳过）
- 开发：AI 按 AGENTS.md Part A 六步工作流执行（探查→约束→证据→执行→验证→交付）；TDD（测试先行）
- 测试：L1 单测 / L2 API 全量（test_api.py）/ L3 场景 / L4 探索；CI 容器门禁
- **人机协同站会（每日开工，3-5 分钟信息对齐）**：AI 生成摘要（昨日 git/CI/测试）、人确认今日计划、AI 标记阻塞/风险——提示词模板见 §十
- **质量门**：CI 全绿（静态门禁 + 全量 TDD）；双环境回归（Windows dev + WSL test）；无 P0/P1 Bug

### 3. Sprint Review（验收，Sprint 最后 1 天，30-45 分钟）
- AI：准备演示与验收证据（测试报告、版本 diff、Release 资产）
- 人（PO）：对照验收标准逐条确认 → 通过/返工
- **输出**：验收结论、反馈清单（新需求/Bug/建议）、**Backlog 按新情况调整**、未完成项移回 Backlog
- 质量门：PO 确认 Sprint Goal 达成；未完成项已登记（不允许静默消失）

### RTM 缓冲（并入 Agile 的"检查/适应"环节，不单列阶段）
- **定位**：Release 之前的安全验证缓冲区，属于 Agile 的检查/适应环节（非独立阶段，与 Release 解耦）
- **会诊机制**：Agent 生成影响分析 → **人做决策**：Fix / As Designed / Won't Fix / Postpone
- **RC 序列**：候选版本按 RC1→RC2→… 递增；RTM 状态标记（release candidate / rtm / release）
- **强度分级**：L1 无需 RTM；L2 轻量 RTM（冒烟+走查）；L3 完整 RTM（全量 TDD+场景走查+预生产验收）
- 本项目落点：v2.7.0 起阶段=rc（APP_STAGE=rc），生产走冒烟+人工验收后转正式（ADR-043）

### 4. Sprint Retrospective（复盘，Review 后，30 分钟）
- AI：生成数据摘要（commit 数、测试通过率、回退/假设变更、ADR 新增、CI 运行、**L2/L3 分布**）
- 人：三问（做好/待改进/下一步行动 ≤3 条，每条有负责人+期限）
- **输出**：复盘文档（docs/07-迭代小结）、行动项入下个 Sprint、**技术债+假设状态刷新（docs/13）**

---

## 六、工件与工具（极简工件体系：Repo as Memory）

| 工件 | Scrum Guide 定义 | 本项目落地（工具） |
|------|-----------------|-------------------|
| Product Backlog | 有序的需求列表，唯一来源 | **Gitea Issues**（标签：P0/P1/P2、hypothesis、tech-debt）；**docs/13** 为"假设型需求"专项清单 |
| Sprint Backlog | 本 Sprint 承诺的工作 + 达成 Sprint Goal 的计划 | **Gitea Milestone** + 关联 Issues |
| Increment | 可用且满足 DoD 的增量（每 Sprint 至少一个） | **git tag + Release**（发布包 + offline-deps + md5/sha256） |
| **唯一事实来源（Repo as Memory）** | PRD / ADR / 迭代摘要 / AI 契约 | **docs/02-prd.md、docs/ADR.md、docs/07-复盘、AGENTS.md** —— 不需要 Jira/看板软件 |

- **极简原则**：仓库即记忆。PRD 描述"要什么"，ADR 记录"为什么这么决策"，summaries/复盘记录"发生了什么"，
  AGENTS.md 约束"AI 怎么干"；Git commit 历史是变更留痕。
- **看板**：轻量看板 = **Gitea Issues + 每日一览表**（模板见 §十），不引入看板软件。
  若将来 ≥3 人团队，列升级为：`待办 → 本期承诺 → 实施中 → 验收 → 已完成`。

---

## 七、承诺（工件必须有承诺）

### Product Goal（产品目标，长期）
- 当前（PSF）：**beta 被真实用户持续使用，问题/方案验证通过**（对应 docs/13 C 类指标）
- PMF 启动后更新为 docs/04 的市场目标

### Sprint Goal（迭代目标，Sprint 期内不可变）
- 一句话；变更只能与 PO 协商，否则视为取消 Sprint

### Definition of Done（DoD，一个 Story 算完成必须全部满足）
- [ ] 代码提交 Git（commit 规范：`type(scope): 描述 [L1|L2|L3]`，不写 Sprint 编号）
- [ ] 对应 TDD 用例已加且通过（新增功能必加测试，计数只增不减）
- [ ] CI 全绿（静态门禁 + 全量 TDD ≥ 当前基线）
- [ ] 双环境回归通过（Windows dev + WSL test）
- [ ] 无 P0/P1 未修复 Bug
- [ ] 文档已同步（PRD/测试报告/i18n/ADR，如涉及）
- [ ] 代码可部署（deploy/verify 脚本通过；生产只跑冒烟）

---

## 八、Story 模板（AI 协同版，含变更级别标记）

```markdown
## Story: 作为<角色>，我可以<功能>，以便<价值>
- 优先级：P0/P1/P2
- 估算：XS/S/M/L
- 类型：feat/fix/docs/test/refactor
- 变更级别：L1/L2/L3（ADR-048：影响半径+可逆性判定）
- 假设标记：无 / [假设] docs/13 #A1（未验证假设不得直接实现）

### 验收标准（可执行断言，每个都对应 TDD 或验证步骤）
1. 当<操作>，应<可观察结果>
2. ...

### 实施记录
- AI 生成标注：[AI-Generated] 基于<模型/日期>生成，人工审查通过
- 相关 commit / 测试组 / ADR
```

---

## 九、防眩晕机制（AI 时代的流程护栏）

> 目标：用**变更预算和漂移检测**控制"迭代眩晕感"，而不是用更多流程去压制它。

- **变更预算**：每个 Sprint Goal 周期允许 **≤2-3 个 L3、≤10 个 L2**；超限触发 Correct Course（回退/重排）
- **WIP = 1**：人机一次只处理一个意图（人一条指令，AI 一个闭环；不并行铺开）
- **漂移检测**：AI 每日摘要统计 L2/L3 数量、PRD 变更、ADR 新增；**L3 频繁出现 → 说明 PRD 或架构没想清楚**，应回到 Design Thinking/Learn
- **定期压缩**：每周把迭代摘要压缩成一页周报，更新 README 和 AGENTS
- **指标（不用多）**：Story 吞吐、L2/L3 分布、返工率、ADR 数量、PRD 漂移次数

---

## 十、人机协同模板（直接复用）

### 10.1 人机协同站会（每日，3-5 分钟）

**触发**：每天开工前，人发起，AI 执行信息对齐。

**提示词模板**（直接粘贴到对话）：

```text
【人机协同站会】<日期>
1. 昨日进展：根据 git log（昨日 commit）+ CI 运行结果 + 测试状态，用 3-5 条摘要昨天完成了什么
2. 今日计划：我今天要推进 <Story/任务>，请拆成可执行步骤（含 TDD 顺序和验收标准）
3. 阻塞/风险：检查 CI、测试、配置不一致、未提交变更、待决事项，列出需要我决策的点
4. 看板刷新：按 §10.2 的列给出当前所有 Story 一览表
5. 变更审计：昨日 L1/L2/L3 分布（超出预算需提醒）、ADR/PRD 漂移检测
6. 结论：本 Sprint Goal 还剩多少、节奏是否正常（若偏离给出建议）
```

**人机分工**：AI 只做**摘要/建议**（git log、CI 状态、测试结果、风险清单）；人只做**决策**（今日做哪个 Story、阻塞怎么解、是否需要调整计划）。站会不做设计讨论，超 5 分钟转"专项对齐"。

### 10.2 人机协同看板（每日一览表）

**列定义**（围绕 Scrum 事件，非阶段门）：

| 列 | 含义 | Gitea 落点 |
|----|------|-----------|
| 待办 | Product Backlog（含假设 docs/13） | Issues（无 Milestone） |
| 本期承诺 | Sprint Backlog | Milestone + Issues |
| 实施中 | 设计/开发/测试**并行**（不按阶段分列） | Issues 状态=open + 分配 |
| 验收 | 已过测试待 PO 验收 | CI 绿 + 待 Review |
| 已完成 | 满足 DoD | 关闭 + git tag/Release |

**每日一览表格式**（站会时 AI 生成）：

```markdown
| Story | 优先级 | 列 | 变更级别 | 验收标准进度 | CI | 阻塞/待决 |
|-------|--------|----|---------|------------|----|-----------|
| <ID> <标题> | P0 | 实施中 | L2 | 3/5 | ✅ | 无 |
| <ID> <标题> | P1 | 验收 | L1 | 5/5 | ✅ | 待 PO 确认 |
```

**看板纪律**：每日站会后刷新一次；Story 只能按列前进，**不允许跳过验收列直接 Done**；Sprint 结束时本 Sprint 未验收项移回"待办"（不静默消失）。

---

## 十一、分阶段落地路径（模板，本项目已走完大部分）

| 阶段 | 动作 | 目标 | 本项目状态 |
|------|------|------|-----------|
| 第 1 周：基础规则固化 | 创建 AGENTS.md、PRD、ADR 目录、约定 commit 格式与变更级别标记 | AI 每轮闭环有明确规则和记录 | ✅ 已完成 |
| 第 2-4 周：微循环建立 | 跑 PDCA 微循环（每天多次）、人巡检 AI 摘要（半天一次）、记录变更级别分布 | L1 占 70%+，L3 每周 ≤2 | ✅ 基本完成 |
| 第 2 月：RTM 与 Release 流程 | RTM 会诊机制、feature flag、首次 RC 序列 | RTM→Release 决策链清晰可审计 | ✅ 已进入（v2.7.x rc） |
| 第 3 月：优化与压缩 | 变更预算与漂移检测、summaries 压缩为周报、指标评估 | 流程成为"无感的脚手架" | 进行中 |

---

## 十二、一句话方法论

> **单 Agent + Repo as Memory + Prompt as Process + Human as Gate + PDCA 驱动微循环 + 分级变更控制 + RTM 缓冲并入 Agile + Release 渐进交付。**

所有概念（Design Thinking、Lean Startup、Agile、XP、DevOps、RTM、Release）都保留，但**管理粒度与 AI 速度对齐**。
正规流程只对 L3 触发（事件触发，非频率触发）；人的慢是特征不是缺陷；用变更预算和漂移检测控制眩晕感。

---

*文档结束 | AI 时代人机协同 Agile 方法论模板 v3.0 | 2026-09-15 | 融合 DeepSeek 方法论（share/kg8xxzwitepqj4dt42）+ 本项目实证*
