# GitLab CICD 实验线（隔离终态 2026-09-16）

> 状态：**已隔离归档（2026-09-16 起）+ 收尾完成（v2.7.3）+ 仓库终态对齐——GitLab 自此隔离，不再使用**。
> 配置资产已全部固化到主仓库（Gitea main / GitHub 备份仓）。双开发域分离：**个人开发域 = 本地 + Gitea + GitHub；
> 公司开发域 = GitLab**（由另一 AI 工具独立访问维护，本工具不再访问 GitLab）。如需再启用 GitLab 实验线，须用户明确指示（ADR-049）。
> **收尾动作（2026-09-16）**：开发分支 `gitlabcicotest` 已合并 main 并删除（分支引用删除，内容全量保留在 main 历史）；
> CI 触发从分支改为 **main**（push main 触发 ci-check）；v2.7.3 在 main 上完整 CI-release-CD 全链验证通过（仅 GitLab 实验环境 18080，不碰 Rocky/生产）；
> **澄清**：job 的 `tags: [gitlabcicotest]` = runner 选择标签（专用物理 Runner `gitlabcicotest-docker`），**不是分支依赖**，与分支同名纯属巧合；
> **终态**：GitLab main=4a7ffe6 已与 Gitea/GitHub 对齐（本地=origin=4a7ffe6），此后不再推送 GitLab。
> 历史：v2.7.1 rc 首验落地（2026-09-15）——第三条平台线（Gitea 权威 + GitHub 备份/云端闭环 + GitLab 实验）
> 验证 GitLab CI/CD 全链路并沉淀跨平台迁移方法论。**实验线隔离纪律：绝不碰 Rocky 测试/生产环境（ADR-045 强制）**。

---

## 1. 目标与边界

| 项 | 内容 |
|----|------|
| GitLab | 10.10.30.9（HTTP 80 可达、HTTPS 未启用、SSH 22 已放通） |
| 项目 | `root/securetrans`（id=209，私有，默认分支 main） |
| 分支策略 | 单分支 main（开发分支 `gitlabcicotest` 已合并删除，2026-09-16）；tag `v*` 触发 Release+CD |
| 隔离 | WSL `gitlabcicotest`（Ubuntu 24.04）+ 独立 docker + `/opt/securetrans-gitlab` 数据 + 18080 端口 |
| 认证 | root PAT（`~/.securetrans/gitlab-token.txt`）+ `GITLAB_PAT` 仓库变量（ADR-042） |

## 2. 环境组成

| 组件 | 说明 |
|------|------|
| GitLab 服务 | 用户自建（Windows docker engine 内或独立部署），本项目只消费其 API |
| Runner | `gitlabcicotest-docker`（id=19）：gitlab-runner 19.3.3 + docker executor + `pull_policy=if-not-present` + 卷挂 `docker.sock`、`/opt/securetrans-gitlab`；WSL 内 `nohup` 直跑 |
| CI 镜像 | `securetrans-gitlab-ci:3.12`（488MB）：复用 `infra/docker/Dockerfile`，wheelhouse 来自 Gitea 网关 Release offline-deps |
| 运行镜像 | `securetrans-gitlab:v<验证版本>`（v2.7.1/v2.7.3 实证）：`Dockerfile.run`（python:3.12.11-slim-bookworm，uid 1000） |
| 部署 | 容器 `securetrans-gitlab`：宿主 18080→8000，数据 `/opt/securetrans-gitlab/{data,nas}` |

## 3. 流水线（.gitlab-ci.yml）

```
push main ──────────► ci-check（静态+版本+env键+脚本+全量TDD）   ← 2026-09-16 改 main 触发
push tag v* ────────► ci-check → release（打包+Release+资产）→ deploy（独立docker+冒烟）
```

- **ci-check**：`py_compile` + `static_check.py` + 版本双源 + env 键一致性 + 脚本完整性 + `bash infra/ci_test.sh`（干净 /data + mock + 性能门禁）
- **release**：wheelhouse→offline-deps → `package.sh` → md5/sha256 → GitLab Release 创建（**4 个自动 sources 源码包**，无业务资产——实验线有意简化，与 Gitea 7 资产/GitHub 4+GHCR 不一致；未来公司域正式用需补 `upload-asset`）+ 主包上传 Generic Package；artifacts 传 deploy
- **deploy**：`Dockerfile.run` 构建 → 先停旧容器 → `docker run`（18080 + 独立卷 + 干净 env）→ **容器 IP** 只读冒烟（health 版本 + login 200）

## 4. 验证结果

**2026-09-16 收尾验证（v2.7.3，main 触发，最后一次全链）**
- 流水线 #695（main push）ci-check ✅ / #696（tag v2.7.3）ci-check → release → deploy 全绿 ✅（stages 严格顺序实证）
- CD 独立部署：容器 `securetrans-gitlab`（172.17.0.x:8000，宿主 18080 对外）→ 只读冒烟 PASS（health v2.7.3）
- **隔离确认**：全程仅 GitLab 实验 WSL（Ubuntu 24.04）+ 独立 docker + `/opt/securetrans-gitlab` 数据；Rocky 测试/生产**未触碰**；Gitea/GitHub 未推（main 无 v2.7.3 tag）

**2026-09-15 首验（v2.7.1）**：流水线 686/688 全绿（CI：静态+版本+env+脚本+全量 TDD 通过；Release：v2.7.1 四资产；CD：独立部署冒烟通过）
- 独立部署验证：`health: {"deployMode":"production","envRole":"prod","status":"ok","version":"v2.7.1"}`；`/api/auth/login` admin 登录成功
- Windows 浏览器访问：`http://localhost:18080`（WSL localhost 转发）
- GitLab 页面：`http://10.10.30.9/root/securetrans`（Release v2.7.1 可见）
- 生产 Rocky：**未触碰**（数据全在 `/opt/securetrans-gitlab`）

## 5. 跨平台 CI/CD 迁移教训（ADR-045）

| # | 坑 | 修复 |
|---|----|------|
| 1 | Windows autocrlf 新文件入库 CRLF | `.gitattributes *.yml eol=lf` + `core.autocrlf=false`；LF 权威验证在 Linux 侧（PowerShell 管道计数是伪影） |
| 2 | docker executor 默认 pull_policy=always 拉远端失败 | `pull_policy = "if-not-present"` |
| 3 | 容器内 uid 1000 写宿主卷 PermissionError | `mkdir` 后 `chown -R 1000:1000` |
| 4 | env 模板行尾注释致 `int()` 失败 | 生成干净 env 去行首+行尾注释（sed 双规则） |
| 5 | job 容器内 localhost 非宿主 | 冒烟用 `docker inspect` 取容器 IP |
| 6 | ci_test.sh 找不到 workspace | `GITHUB_WORKSPACE=$CI_PROJECT_DIR` |

## 6. 复用手册（新平台迁移模板）

1. 建仓库 + PAT（最小 scope）→ git remote + push 开发分支
2. 新建独立 WSL（Ubuntu/Rocky）+ docker daemon + `pull_policy=if-not-present`
3. CI 镜像复用 `infra/docker/Dockerfile`（wheelhouse 同源）→ `gitlab-runner register`（volumes 挂 docker.sock + 独立数据目录）
4. `.gitlab-ci.yml` 三阶段（ci/release/deploy）→ push 分支验证 CI → tag 验证全链路
5. 验证独立部署（独立端口+数据）→ 冒烟（容器 IP）+ 登录 → 记录 ADR + 手册

## 7. 配置资产全量清单（2026-09-16 同步固化）

> 目的：GitLab 隔离后（ADR-049），**CI/release/CD 全部配置在主仓库（Gitea/GitHub）可完整复现与审计**；
> GitLab 服务器侧现状保留，不再访问。

### 7.1 仓库内资产（已入库，权威）
| 资产 | 路径 | 说明 |
|------|------|------|
| 流水线入口 | `.gitlab-ci.yml`（仓库根） | **GitLab 执行入口**：定义 stages + `include: local` 引用 `.gitlab/workflows/*.yml`（对标 .gitea/.github 的 workflows 拆分）；校验：`git diff gitlab/gitlabcicotest origin/main -- .gitlab-ci.yml` = 0（旧单文件版与 GitLab 分支一致，本次仅重构为 include 拆分，job 逐行未变） |
| CI workflow | `.gitlab/workflows/ci.yml` | ci-check job（静态+版本+env键+脚本+全量 TDD） |
| Release workflow | `.gitlab/workflows/release.yml` | release job（打包+Release+资产） |
| Deploy workflow | `.gitlab/workflows/deploy.yml` | deploy job（独立 docker+冒烟） |
| 本手册 | `docs/15-gitlab-cicd.md` | 环境/流水线/验证/教训/复用（本文件） |
| CI 镜像 Dockerfile | `infra/docker/Dockerfile` | wheelhouse 同源，构建 `securetrans-gitlab-ci:3.12` |
| 运行镜像 Dockerfile | `infra/docker/Dockerfile.run` | python:3.12.11-slim-bookworm，uid 1000 |

> 三平台 workflow 目录对标：`.gitea/workflows/{ci,release,cd}.yml` ↔ `.github/workflows/{ci,release,cd-sim}.yml` ↔ `.gitlab-ci.yml`（入口）+ `.gitlab/workflows/{ci,release,deploy}.yml`（明细）。

### 7.2 服务器侧配置（不入库，仅记录；如需重建按此恢复）
| 项 | 配置 | 说明 |
|----|------|------|
| Runner config.toml（关键段） | `concurrent = 1`；`[[runners]] name="gitlabcicotest-docker"`；`executor = "docker"`；`tags = ["gitlabcicotest"]`；`pull_policy = "if-not-present"`；`volumes = ["/var/run/docker.sock:/var/run/docker.sock", "/opt/securetrans-gitlab:/opt/securetrans-gitlab"]` | gitlab-runner 19.3.3；WSL 内 `nohup` 直跑（非 systemd） |
| 仓库 CI/CD 变量 | `GITLAB_PAT`（最小 scope，ADR-042） | 仅 release job 使用；本地另有 `~/.securetrans/gitlab-token.txt` |
| 运行环境 | WSL distro `gitlabcicotest`（Ubuntu 24.04）+ docker daemon | 独立于 rocky10-ci / rocky10-st |
| 数据目录 | `/opt/securetrans-gitlab/{data,nas}` | 独立，chown 1000:1000 |
| 端口 | 宿主 18080 → 容器 8000 | 与生产 8000 / 实验 18080 各自独立 |
| 镜像 | `securetrans-gitlab-ci:3.12`（488MB）、`securetrans-gitlab:v2.7.1` | 已构建于 WSL，重建可复用 infra/docker/* |

### 7.3 触发矩阵（GitLab 侧）
| 事件 | 流水线 | 说明 |
|------|--------|------|
| push `gitlabcicotest` | ci-check | 仅 CI |
| push tag `v*` | ci-check → release → deploy | 全链路 |

## 8. 隔离状态（2026-09-16 起，ADR-049）

- **双开发域分离**：个人开发域 = 本地 Windows + Gitea + GitHub（本 AI 工具）；公司开发域 = GitLab（另一 AI 工具独立访问维护）
- **主仓库不再推送 GitLab remote**；GitLab 服务器现状保留不动（含 gitlabcicotest 分支、Runner、数据）
- 配置资产已固化（§7），GitLab 侧再出问题可由另一 AI 工具按 §7 恢复
- 再启用条件：用户明确指示（如公司侧需要重跑实验线）

---

*文档结束 | GitLab CICD 实验线（gitlabcicotest）| 已隔离归档 2026-09-16*
