# GitHub 迁移方案（Proposal / 待细化落地）

> **状态：方案讨论（PROPOSAL）** — 本文件是 2026-09-14 与 AI 咨询讨论的完整记录，作为迁移 GitHub 的决策输入。
> **落地条件：版本达到发布水平（RTM/Release）后**，再细化执行步骤并真正落地（届时升级本文件状态为 ACTIVE）。
> **关联**：ADR-007（发布策略：代码变更才发布 / 文档-only 不 bump）、ADR-021（CICD 单 job 规避）、08-cicd-gitops-architecture.md（现有 Gitea CI/CD 架构）。

---

## 1. 背景与目标

SecureTrans 当前研发闭环已完全跑在 **Gitea（本地，Windows Docker Desktop 容器，局域网可访问）**：

```
Windows dev 全量 TDD（380/380）→ git push → Gitea CI（act_runner + securetrans-ci:3.12 容器）
→ tag → Release（4 资产）→ CD（cd.yml）→ 生产 10.10.30.8（封闭数据中心，单网卡单端口）
```

目标：**推 GitHub**，希望：
1. 在 GitHub 上完全端到端跑通（CI + Release + CD 到私有数据中心生产）；
2. 使用 **免费资源**，不额外购买开发 / 测试 / CI / pre-prod 的服务器或 Docker 资源；
3. 明确 GitHub 与 Gitea 的联动机制；
4. 按业界最佳实践完成"本地 PC / 私有云 → GitHub 公有云"的迁移或打通。

## 2. 核心结论（一次说清）

**能。GitHub 免费资源可端到端跑通，CD 到私有数据中心完全可以打通。**

关键认知纠正：**GitHub CD 到私有网络不是"推不进去"，而是模型问题**。业界标准是
**"内网 runner 出站拉取"**（self-hosted runner 主动连 GitHub，HTTPS 443 出站），
不是"GitHub 入站推送"。GitHub 不需要对数据中心开放任何入站端口。

## 3. 免费资源盘点

| 环节 | 免费方案 | 说明 |
|------|----------|------|
| **CI** | GitHub-hosted runner（ubuntu-latest / windows-latest） | **public 仓库：Actions 无限分钟**；private：2000 分钟/月免费额度。本项目 CI = 秒级静态检查 + 容器全量 TDD + 性能门禁，一次约 1-2 分钟 |
| **测试环境一致性** | 镜像推 **ghcr.io**（GitHub Container Registry，免费） | 现有 `securetrans-ci:3.12` 推上云，Actions 拉镜像执行——环境一致靠镜像不靠机器（与本地/WSL 同源） |
| **pre-prod** | 容器化测试（同上）或 self-hosted runner | 不需要单独购买 pre-prod 服务器 |
| **CD** | **self-hosted runner**（免费，用数据中心现有跳板机） | 见 §4，关键模型 |
| **Release 资产** | GitHub Release（免费） | tag 驱动自动建，现有 4 资产逻辑照搬 |
| **源码托管/协作** | GitHub Repo + Issues（免费） | public 全免费；private 协作免费（团队规模限制见官方定价） |

> 唯一需要花钱的场景：生产必须由 GitHub 直接 SSH 公网 IP 部署（云主机模式）。
> 本项目是封闭数据中心，正好用 self-hosted runner 免费解决。

## 4. CD 模型：业界四种模式对比

| 模式 | 机制 | 适用 | 成本 |
|------|------|------|------|
| **A. hosted CI + self-hosted CD**（业界主流，**推荐**） | CI 用 GitHub-hosted runner（云上免费）；CD 用 self-hosted runner 部署在数据中心内，出站连 GitHub 拉 job，在数据网络内执行 scp + cd-deploy.sh | 私有数据中心生产（本项目） | 免费 |
| **B. 全 self-hosted** | 所有 runner 都在内网，GitHub 只做编排 | 完全隔离 / 合规要求 | 免费（用内网机器） |
| **C. 生产侧轮询 Release**（最简） | 生产服务器 cron 定时拉 GitHub Release 资产 + MD5 校验 + 部署（pull 模型） | 极简、低频发布 | 免费 |
| **D. GitHub 直推公网 IP** | GitHub-hosted runner 直接 SSH 公网可达的生产 IP | 云上 VPS / 云主机 | 免费（但要求公网） |

**self-hosted runner 为什么能穿透封闭数据中心**（本项目已同型验证）：
- runner 部署在能访问生产网络的机器（跳板机 / 堡垒机 / 生产前一台机）；
- **runner 主动出站 HTTPS 443 连 GitHub**，GitHub 下发 job（长连接）；
- 不需要对 GitHub 开放任何入站端口，可穿过防火墙 / IPsec / 内网隔离；
- 现有 Gitea CD 已经是此模型（WSL 的 act_runner 出站连 Gitea），逻辑几乎照搬。

**CD 工作流迁移改动量**（模式 A）：现有 `cd.yml`（下载 Release 资产 → MD5 → scp → cd-deploy.sh → 只读冒烟）只改三处：
1. runner 注册方式（Gitea act_runner → GitHub self-hosted runner）；
2. Secrets：CD_SSH_KEY / Gitea API token → GitHub Actions Secrets（**永不入库**，当前已符合）；
3. Gitea API token 语义 → GitHub token。

## 5. GitHub ↔ Gitea 联动机制

**没有官方双向同步**。业界可选：

| 方式 | 机制 | 适用 |
|------|------|------|
| **Gitea push mirror**（推荐） | Gitea 仓库设置 → 镜像 → 推送镜像到 GitHub：代码 + tag 自动同步，GitHub 侧只读 | Gitea 为主、GitHub 为分发 / 公开 |
| 双 remote | `git remote add github …`，每次 push 两个远端（手动或 alias 脚本） | 双向可写，人工/脚本维护 |
| Actions 定时回推 | GitHub Actions cron `git push` 回 Gitea（Gitea token 放 Actions secret） | 反向（GitHub 为主） |
| 手动迁移 Issues/PR | Gitea → GitHub 迁移工具（一次性） | 换主站时 |

**注意**：Issues / Milestone / 看板数据**不自动同步**。本项目 Backlog 在 Gitea Issues
（见 01-scrum-io-definition.md 看板落点）——若 GitHub 为主，看板需迁移或重建。

## 6. 迁移 / 打通最佳实践（业界共识，7 步）

1. **渐进双轨，不切割**：GitHub 建 **private** 仓库 → `git remote add github` 双 push → GitHub Actions CI 与 Gitea CI **并跑 1-2 周** → 两边全绿再切换；
2. **敏感信息脱敏先行**：`git filter-repo` 清理历史（README/AGENTS 中 `10.10.30.8` 等内网 IP）；公开前必做；若 GitHub 仅作镜像（private）可暂缓；
3. **Secrets 重新治理**：CD_SSH_KEY / Gitea token / 生产凭据 → GitHub Actions Secrets，永不入库；
4. **镜像与依赖上云**：`securetrans-ci:3.12` → ghcr.io；offline-deps 作为 Release 资产（Actions 自动打，逻辑现成）；
5. **Release / tag 策略对齐**：ADR-007 不变（tag 驱动发布、代码变更才发布）；GitHub Release body 用现有 changelog 生成逻辑；
6. **明确 source of truth**：建议 **beta 收尾期 Gitea 为主**（内部开发 + 私有部署），GitHub 为"可复现性证明 + 分发渠道"；正式 release 后再决定是否迁主；
7. **验收标准**：GitHub 上全量 TDD 380 + 性能门禁绿 + CD 部署生产成功 ≥ 1 次，才算打通完成。

## 7. 对 SecureTrans 的具体建议（当前方案）

| 阶段 | 主站 | GitHub 角色 | CI | CD |
|------|------|-------------|----|----|
| **当前（beta 收尾）** | Gitea（不变） | private 镜像（push mirror）+ 可选 Actions CI 验证 | Gitea CI 继续 | Gitea CD 继续 |
| **发布水平达成后（RTM/Release）** | 决策点：Gitea 或 GitHub 为主 | 按 §6 细化执行 | 双轨并跑 → 切换 | self-hosted runner 出站模型（模式 A）或模式 C |
| **正式公开** | 决策点 | public + 分发主渠道 | GitHub Actions 主跑 | 按环境选择 |

**推荐路线**（可回退、符合 stepping-stone 方法论）：
- GitHub 开 **private** 镜像（Gitea push mirror，代码 + tag 自动同步）；
- GitHub Actions 跑 CI（证明工程可复现，为公开做准备）；
- self-hosted runner 打通 CD（免费，逻辑照搬现有 cd.yml）；
- beta 收尾、正式 release 时再决定：GitHub 公开 + 作为分发主渠道，Gitea 退为内部镜像。

## 8. 已知差距与风险清单（落地前处理）

| # | 差距 | 影响 | 处理时机 |
|---|------|------|----------|
| 1 | **CI 平台迁移**：`.gitea/workflows` + act_runner + 自建镜像是 Gitea 专属，GitHub 不认 | GitHub 上 CI 无法直接运行 | 落地时迁移到 `.github/workflows` + GitHub-hosted runner（或 ghcr.io 镜像） |
| 2 | **Secrets 不通用**：CD_SSH_KEY、Gitea API token | CD 在 GitHub 失效 | 落地时重配 GitHub Actions Secrets |
| 3 | **敏感信息脱敏**：README/AGENTS 含生产内网 IP `10.10.30.8` | 公开仓库暴露内网拓扑 | **公开前必做**（filter-repo 清历史或占位符版本） |
| 4 | **offline-deps 首次获取**：离线依赖包是 Release 资产不入仓 | 新工程师首次构建需从 Release 下载或联网 pip | README 已给路径；可补充 ghcr.io 全量镜像方案 |
| 5 | **Issues / 看板不迁移** | 换主站时 Backlog 需重建 | 换主站时处理 |
| 6 | **版本历史 / Release 资产不自动迁移** | GitHub 从零开始打 tag | 双轨期逐步对齐 |

## 9. 与现有体系的关系

- **发布策略**：本文件属于 **docs-only 变更**（ADR-007），不 bump 版本、不打包、不建 Release；
- **ADR 定位**：本文件是**方案讨论（Proposal）**，尚未决策，**不写入 docs/ADR.md**；落地时若产生关键架构决策，追加为新 ADR（如 ADR-033 GitHub 迁移/双轨）；
- **文档一致性**：README / AGENTS 的文档索引同步增加本文件条目。

---

*文档状态：PROPOSAL（方案讨论）· 创建 2026-09-14 · 落地条件：版本达发布水平后细化执行*
