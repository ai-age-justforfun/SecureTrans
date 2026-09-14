# AI 辅助 Agile-Scrum 流程模板（v2.0）

> 版本：v2.0 | 日期：2026-09-14 | 适用：SecureTrans 及后续项目（PSF/PMF/Scale 通用）
> 定位：以 **AI 辅助为中心**的人机协同 Scrum 裁剪版。基于 Scrum Guide 2020 审计后重写，取代 v1.0。
> 原则：保留 Scrum 经验主义内核（透明/检视/适应），裁剪人机协同下无收益的形式（站会/看板），一切围绕"每 Sprint 产出可部署增量"。

---

## 一、规范性审计结论（对照 Scrum Guide 2020）

### ✅ 符合项（保留）
- Sprint 固定时长（1-2 周）、迭代增量交付
- Story 验收标准（可验证行为清单）
- DoD 概念、复盘三问、Review 由 PO 验收
- 每 Sprint 产出可部署代码 + 提交 + 复盘

### ❌ 偏差项（本次修正）
| # | Scrum Guide 2020 要求 | v1.0 偏差 | 修正 |
|---|----------------------|----------|------|
| 1 | Scrum 团队 = PO / SM / Developers 三类 Accountability | 未定义角色分工（单人+AI 场景下 AI 承担什么不明） | 见 §二 人机 Accountability 映射 |
| 2 | 工件各有承诺：Product Goal / Sprint Goal / DoD | Product Goal 未显式化；Sprint Goal 未声明"期内不可变" | 见 §五 承诺 |
| 3 | 事件是"检视+适应"节点，**不是瀑布阶段门** | "需求→设计→开发→测试→验证→复盘"六阶段易退化成小瀑布（设计完才开发） | 改为"规划→实施（设计/开发/测试为 Sprint Backlog 内并行工作）→Review→Retro" |
| 4 | Daily Scrum 是团队同步事件 | 仅提"每日站会"无格式；人机协同下收益存疑 | 裁剪为"异步站会（可选）"，见 §三 |
| 5 | Product Backlog 持续精化（Refinement 非正式事件） | 混入 Planning | 独立为"Backlog 精化"活动（PSF 收尾阶段尤其重要） |
| 6 | Sprint Review 需"根据新情况调整 Backlog" | 未体现 | 补入 Review 输出 |
| 7 | DoD 应含质量门（可发布性） | DoD 未联动 CI/CD 实际能力 | DoD 与 CI/CD 门禁绑定，见 §五 |

### ✂️ 裁剪决策（人机协同，用户确认）
- **站会**：保留为**人机协同站会**（每日 3-5 分钟信息对齐，AI 生成摘要、人做决策），不召开多人会议——模板见 §九
- **看板**：保留为**轻量看板**（Gitea Issues + 每日一览表，不引入看板软件）——模板见 §九
- **Sprint 周期演进**：以协同效率为准，参考 AI 能力调整（2 周 → 1 周 → 1-2 天），规则见 §三 Sprint 定义
- **工作量估算**：保留 XS/S/M/L 粗估（AI 时代按"复杂度+验证成本"，不追求精确点数）
- **Sprint Review 演示**：AI 准备演示/验收证据（测试报告+版本差异），人做验收决策

---

## 二、人机 Accountability 映射（Scrum 团队裁剪版）

| Scrum Guide 2020 | 本项目映射 | 职责 |
|------------------|-----------|------|
| Product Owner（产品负责人） | **人（你）** | 需求决策、优先级、验收、Product Goal 定义 |
| Scrum Master（流程守护） | **人（你）** + AI 辅助 | 流程纪律、障碍排除；AI 提供流程检查清单/审计提醒 |
| Developers（开发者） | **AI 主力 + 人审核** | AI：编码/测试/文档初稿/CI 执行；人：审核/联调/最终决定 |

> 关键：**AI 是 Developers 的一员，不是替代 PO/SM**。所有"决策/验收/优先级"保留给人；
> AI 负责"执行/建议/留痕"。任何 AI 产出必须有人工验收环节（Story 验收标准 = 可执行断言）。

---

## 三、事件（裁剪后）

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

### 2. 实施（Sprint 第 1-5 天，设计/开发/测试为 Backlog 内并行工作）
- 设计：复杂 Story 出方案 + ADR（仅架构级决策，PSF 小功能跳过）
- 开发：AI 按 AGENTS.md Part A 六步工作流执行（探查→约束→证据→执行→验证→交付）；TDD（测试先行）
- 测试：L1 单测 / L2 API 全量（test_api.py）/ L3 场景 / L4 探索；CI 容器门禁
- **人机协同站会（每日开工，3-5 分钟信息对齐）**：AI 生成摘要（昨日 git/CI/测试）、人确认今日计划、AI 标记阻塞/风险——提示词模板见 §九；2+ 人时人之间只对齐依赖
- **质量门**：CI 全绿（静态门禁 + 全量 TDD）；双环境回归（Windows dev + WSL test）；无 P0/P1 Bug

### 3. Sprint Review（验收，Sprint 最后 1 天，30-45 分钟）
- AI：准备演示与验收证据（测试报告、版本 diff、Release 资产）
- 人（PO）：对照验收标准逐条确认 → 通过/返工
- **输出**：验收结论、反馈清单（新需求/Bug/建议）、**Backlog 按新情况调整**、未完成项移回 Backlog
- 质量门：PO 确认 Sprint Goal 达成；未完成项已登记（不允许静默消失）

### 4. Sprint Retrospective（复盘，Review 后，30 分钟）
- AI：生成数据摘要（commit 数、测试通过率、回退/假设变更、ADR 新增、CI 运行）
- 人：三问（做好/待改进/下一步行动 ≤3 条，每条有负责人+期限）
- **输出**：复盘文档（docs/07-迭代小结）、行动项入下个 Sprint、**技术债+假设状态刷新（docs/13）**

---

## 四、工件与工具

| 工件 | Scrum Guide 定义 | 本项目落地（工具） |
|------|-----------------|-------------------|
| Product Backlog | 有序的需求列表，唯一来源 | **Gitea Issues**（标签：P0/P1/P2、hypothesis、tech-debt）；**docs/13** 为"假设型需求"专项清单 |
| Sprint Backlog | 本 Sprint 承诺的工作 + 达成 Sprint Goal 的计划 | **Gitea Milestone** + 关联 Issues |
| Increment | 可用且满足 DoD 的增量（每 Sprint 至少一个） | **git tag + Release**（发布包 + offline-deps + md5/sha256） |

**看板**：轻量看板 = **Gitea Issues + 每日一览表**（模板见 §九），不引入看板软件。
若将来 ≥3 人团队，列升级为：`待办 → 本期承诺 → 实施中 → 验收 → 已完成`。

---

## 五、承诺（工件必须有承诺）

### Product Goal（产品目标，长期）
- 当前（PSF）：**beta 被真实用户持续使用，问题/方案验证通过**（对应 docs/13 C 类指标）
- PMF 启动后更新为 docs/04 的市场目标

### Sprint Goal（迭代目标，Sprint 期内不可变）
- 一句话；变更只能与 PO 协商，否则视为取消 Sprint

### Definition of Done（DoD，一个 Story 算完成必须全部满足）
- [ ] 代码提交 Git（commit 规范：`type(scope): 描述`，不写 Sprint 编号）
- [ ] 对应 TDD 用例已加且通过（新增功能必加测试，计数只增不减）
- [ ] CI 全绿（静态门禁 + 全量 TDD ≥ 当前基线）
- [ ] 双环境回归通过（Windows dev + WSL test）
- [ ] 无 P0/P1 未修复 Bug
- [ ] 文档已同步（PRD/测试报告/i18n/ADR，如涉及）
- [ ] 代码可部署（deploy/verify 脚本通过；生产只跑冒烟）

---

## 六、Story 模板（AI 协同版）

```markdown
## Story: 作为<角色>，我可以<功能>，以便<价值>
- 优先级：P0/P1/P2
- 估算：XS/S/M/L
- 类型：feat/fix/docs/test/refactor
- 假设标记：无 / [假设] docs/13 #A1（未验证假设不得直接实现）

### 验收标准（可执行断言，每个都对应 TDD 或验证步骤）
1. 当<操作>，应<可观察结果>
2. ...

### 实施记录
- AI 生成标注：[AI-Generated] 基于<模型/日期>生成，人工审查通过
- 相关 commit / 测试组 / ADR
```

---

## 七、Sprint 节奏总表（PSF 1 周）

| 天 | 事件/活动 | 人（PO/SM） | AI（Dev） |
|----|----------|------------|-----------|
| 周一 | Sprint Planning | 定 Goal、选 Story、确认验收 | 拆 Story、估点、风险 |
| 周一-周四 | 实施（并行） | 审核、决策、必要联调 | 设计/编码/TDD/文档初稿；异步站会摘要 |
| 周四 | 测试冻结 | 确认无 P0/P1 | 全量回归 + CI + 双环境 |
| 周五上午 | Sprint Review | 对照验收标准逐条验收 | 演示/验收证据 |
| 周五下午 | Retrospective + 发布 | 三问、行动项 ≤3 | 数据摘要、技术债/假设刷新 |

---

## 八、与 Lean Startup 衔接

- **PSF（当前）**：1 周 Sprint；只做"被使用验证的需求"；假设清单（docs/13）逐轮核销
- **PMF**：2 周 Sprint（docs/04）；Backlog 按 RICE 排序；试点用户验证层（docs/04 §2.4）
- **每 Sprint 交付**：可部署 Increment + 复盘 + 假设/技术债状态刷新 + git 归档（push main + 按需发布）

---

## 九、人机协同模板（直接复用）

### 9.1 人机协同站会（每日，3-5 分钟）

**触发**：每天开工前，人发起，AI 执行信息对齐。

**提示词模板**（直接粘贴到对话）：

```text
【人机协同站会】<日期>
1. 昨日进展：根据 git log（昨日 commit）+ CI 运行结果 + 测试状态，用 3-5 条摘要昨天完成了什么
2. 今日计划：我今天要推进 <Story/任务>，请拆成可执行步骤（含 TDD 顺序和验收标准）
3. 阻塞/风险：检查 CI、测试、配置不一致、未提交变更、待决事项，列出需要我决策的点
4. 看板刷新：按 §9.2 的列给出当前所有 Story 一览表
5. 结论：本 Sprint Goal 还剩多少、节奏是否正常（若偏离给出建议）
```

**人机分工**：AI 只做**摘要/建议**（git log、CI 状态、测试结果、风险清单）；人只做**决策**（今日做哪个 Story、阻塞怎么解、是否需要调整计划）。站会不做设计讨论，超 5 分钟转"专项对齐"。

### 9.2 人机协同看板（每日一览表）

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
| Story | 优先级 | 列 | 验收标准进度 | CI | 阻塞/待决 |
|-------|--------|----|------------|----|-----------|
| <ID> <标题> | P0 | 实施中 | 3/5 | ✅ | 无 |
| <ID> <标题> | P1 | 验收 | 5/5 | ✅ | 待 PO 确认 |
```

**看板纪律**：每日站会后刷新一次；Story 只能按列前进，**不允许跳过验收列直接 Done**；Sprint 结束时本 Sprint 未验收项移回"待办"（不静默消失）。

---

*文档结束 | AI 辅助 Agile-Scrum 流程模板 v2.0 | 2026-09-14*
