# GitLab CICD 实验线（gitlabcicotest）

> 状态：**Active（v2.7.1 rc 首验落地，2026-09-15）**
> 定位：第三条平台线（Gitea 权威 + GitHub 备份/云端闭环 + GitLab 实验）——验证 GitLab CI/CD 全链路
> 并沉淀跨平台迁移方法论。**实验线隔离纪律：绝不碰 Rocky 测试/生产环境（ADR-045 强制）**。
> **可选流程（2026-09-15 起）**：本实验线的全部代码（.gitlab-ci.yml、docs/15、ADR-045/046）已随仓库
> 合入 Gitea main / GitHub 备份仓，但 **GitLab CI/release/CD 默认不触发**——各平台只执行自己的
> workflow 文件（Gitea 只跑 .gitea/workflows/*，GitHub 只跑 .github/workflows/*，均不执行 .gitlab-ci.yml），
> 且默认分支不推送 GitLab remote。**仅当需要再跑 GitLab 实验线时**：手动 `git push gitlab gitlabcicotest`
> 才会触发 GitLab 流水线（推送后 GitLab Runner 自动执行 ci-check/release/deploy）。

## 1. 目标与边界

| 项 | 内容 |
|----|------|
| GitLab | 10.10.30.9（HTTP 80 可达、HTTPS 未启用、SSH 22 已放通） |
| 项目 | `root/securetrans`（id=209，私有，默认分支 gitlabcicotest） |
| 分支策略 | 开发分支 `gitlabcicotest` 单线（实验），tag `v*` 触发 Release+CD |
| 隔离 | WSL `gitlabcicotest`（Ubuntu 24.04）+ 独立 docker + `/opt/securetrans-gitlab` 数据 + 18080 端口 |
| 认证 | root PAT（`~/.securetrans/gitlab-token.txt`）+ `GITLAB_PAT` 仓库变量（ADR-042） |

## 2. 环境组成

| 组件 | 说明 |
|------|------|
| GitLab 服务 | 用户自建（Windows docker engine 内或独立部署），本项目只消费其 API |
| Runner | `gitlabcicotest-docker`（id=19）：gitlab-runner 19.3.3 + docker executor + `pull_policy=if-not-present` + 卷挂 `docker.sock`、`/opt/securetrans-gitlab`；WSL 内 `nohup` 直跑 |
| CI 镜像 | `securetrans-gitlab-ci:3.12`（488MB）：复用 `infra/docker/Dockerfile`，wheelhouse 来自 Gitea 网关 Release offline-deps |
| 运行镜像 | `securetrans-gitlab:v2.7.1`：`Dockerfile.run`（python:3.12.11-slim-bookworm，uid 1000） |
| 部署 | 容器 `securetrans-gitlab`：宿主 18080→8000，数据 `/opt/securetrans-gitlab/{data,nas}` |

## 3. 流水线（.gitlab-ci.yml）

```
push gitlabcicotest ──► ci-check（静态+版本+env键+脚本+全量TDD）
push tag v* ─────────► ci-check → release（打包+Release+资产）→ deploy（独立docker+冒烟）
```

- **ci-check**：`py_compile` + `static_check.py` + 版本双源 + env 键一致性 + 脚本完整性 + `bash infra/ci_test.sh`（干净 /data + mock + 性能门禁）
- **release**：wheelhouse→offline-deps → `package.sh` → md5/sha256 → GitLab Release 创建（4 个自动 sources 资产）+ 主包上传 Generic Package；artifacts 传 deploy
- **deploy**：`Dockerfile.run` 构建 → 先停旧容器 → `docker run`（18080 + 独立卷 + 干净 env）→ **容器 IP** 只读冒烟（health 版本 + login 200）

## 4. 本次验证结果（2026-09-15）

- 流水线 686/688 全绿（CI：静态+版本+env+脚本+全量 TDD 通过；Release：v2.7.1 四资产；CD：独立部署冒烟通过）
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
