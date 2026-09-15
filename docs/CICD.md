# SecureTrans 跨平台 CICD 指南（Gitea / GitHub / GitLab）

> **定位**：三平台 CICD 机制对比与快速入门手册——让人一眼看懂三种 Git 服务器的 CICD 完整设置，
> 并**对照本项目真实配置**（Gitea/GitHub/GitLab 三套 workflow 全部在仓库内，可直接复制复用）。
> **不是 ADR**：技术决策走 docs/ADR.md（ADR-037 职责分层、ADR-042 认证、ADR-045 GitLab 实验线等）；
> 本文档回答"怎么配置、怎么运行、三者差在哪"。
> 配套手册：docs/14-github-migration.md（GitHub 执行手册）、docs/15-gitlab-cicd.md（GitLab 实验线）。

---

## 1. 一页总览

| 维度 | Gitea Actions | GitHub Actions | GitLab CI/CD |
|---|---|---|---|
| 角色 | **本地权威仓**（全部 git 操作 + 生产 CD） | **公有云备份仓**（容灾/分发/独立验证） | **本地实验线**（第三条平台验证） |
| 服务地址 | http://localhost:3000 | github.com（ai-age-justforfun/SecureTrans） | http://10.10.30.9 |
| Workflow 文件 | `.gitea/workflows/{ci,release,cd}.yml` | `.github/workflows/{ci,release,cd-sim}.yml` | `.gitlab-ci.yml`（单文件三阶段） |
| Runner | act_runner（**自托管**，WSL 容器 label） | GitHub-hosted（`ubuntu-latest` 云 VM） | gitlab-runner（**docker executor** 容器） |
| 依赖安装 | 离线 wheelhouse（镜像内） | 在线 `pip install` | 离线 wheelhouse（镜像内） |
| CI 门禁 | 静态+版本+env键+脚本+全量TDD（容器内干净数据） | 同门禁（云 VM） | 同门禁（docker executor 容器） |
| Release 机制 | Gitea Release API（7 资产） | `gh release`（4 资产 + GHCR 镜像） | GitLab Release API（4 sources + Generic Package） |
| CD 目标 | **生产 10.10.30.8**（SSH 部署+只读冒烟） | CD-SIM 云端 Docker 仿真（**不碰生产**） | 独立 18080 实验部署（**不碰生产**） |
| 镜像构建 | job 内 docker CLI → **宿主 docker.sock** | 云 VM 内 docker build → GHCR | job 内 docker CLI → **宿主 docker.sock** |
| 凭据 | repo secret（RELEASETOKEN/CD_SSH_KEY） | GITHUB_TOKEN（内置，最小权限） | 仓库变量（GITLAB_PAT）+ runner token |
| 费用 | 本地免费 | 公有云免费额度 | 本地免费 |

> 一句话：**同一个 CI/CD 流程，三个平台各有一套声明文件；差异只在 Runner 宿主、Release 载体和 CD 目标**。

---

## 2. 概念先修（5 分钟看懂）

### 2.1 事件 → Workflow → Job → Step

```
git push / tag / Release 发布 / 手动触发
        │  （事件 event）
        ▼
Workflow（声明文件：.gitea/workflows/*.yml / .github/workflows/*.yml / .gitlab-ci.yml）
   │  按 on/触发条件决定"本次是否运行"
   ▼
Job（一个执行单元，runs-on 指定跑在哪个 Runner 上）
   │  同一 workflow 内多个 job 可并行（本项目为规避 act_runner bug 用单 job 串行）
   ▼
Step（job 内一串命令，任一步非零退出 → job 失败 → 流水线失败）
```

- **Workflow 声明在仓库里，随代码一起版本化**（环境即代码）。
- **Runner 是"执行者"**：接收 Git 服务器分发的 job，在隔离环境跑 Steps。

### 2.2 Runner 三种形态（本项目三种平台各用其一）

| Runner 形态 | 在哪执行 | 隔离 | 本项目实例 |
|---|---|---|---|
| **容器 label**（自托管） | 你机器的 docker daemon 拉 CI 镜像跑 job 容器 | 容器隔离（每次全新） | Gitea act_runner：`securetrans-ci:docker://securetrans-ci:3.12` |
| **云托管 VM** | GitHub 的 ubuntu-latest 虚拟机 | VM 隔离（每次全新） | GitHub Actions |
| **docker executor**（自托管） | gitlab-runner 拉起 job 容器 | 容器隔离（每次全新） | GitLab runner：`gitlabcicotest-docker` |

共同点：**每次 job = 全新环境 + 新配置 + 新数据**（防版本干扰、防逃逸污染宿主，ADR-019/037）。

### 2.3 四种 Docker 角色（重点：宿主 docker 与 workflow 的关系）

本项目里"docker"出现四种含义，先分清：

| # | Docker 角色 | 谁用 | 在哪 | 示例 |
|---|---|---|---|---|
| ① | **CI 构建镜像**（含依赖） | 人/脚本构建一次 | 本地 WSL daemon | `securetrans-ci:3.12`（infra/docker/Dockerfile） |
| ② | **CI job 运行容器** | Runner 每次拉取①执行 | 本地 WSL daemon | Gitea/GitLab 每次 job 的容器 |
| ③ | **应用运行镜像**（最终产物） | Release 阶段构建 | 宿主 docker.sock（经 job 内 docker CLI） | `securetrans:v2.7.1` / `ghcr.io/...` |
| ④ | **部署运行容器** | CD 阶段在目标机启动 | 生产 10.10.30.8（podman）/ 实验 18080 | 容器 `securetrans-docker` |

**关键关系**：
- ①→②：Runner 配置里写 `docker://<镜像名>`（Gitea label）或 executor 配置引用（GitLab），job 容器由此镜像生成。
- ③：Release job **在 ② 容器内部**调用 `docker build`（job 镜像已装 docker-ce-cli），但**真正执行构建的是宿主 daemon**——靠挂载 `docker.sock`（Gitea act_runner `container.options: -v /var/run/docker.sock:/var/run/docker.sock`；GitLab runner volumes 同）。**job 容器 → docker.sock → 宿主 daemon** 是自托管平台构建镜像的标准做法（kaniko 无特权方案已废弃，ADR-039）。
- ④：CD 把 ③ 的 image.tar.gz 传到目标机（或从 GHCR pull），`podman load`/`docker run` 启动。
- GitHub 例外：云 VM 本身有 docker，③④都在云 VM 内完成（构建 + 仿真运行），产物镜像 push GHCR 供任何人拉取。

### 2.4 凭据体系（三层，互不混用）

| 凭据 | 存哪 | 用途 | 本项目 |
|---|---|---|---|
| **repo secret / 变量** | Git 服务器设置里（不入库） | 注入 job 环境变量 | Gitea `RELEASETOKEN`、`CD_SSH_KEY`；GitLab `GITLAB_PAT` |
| **内置 token** | Runner 自动生成 | 调本服务器 API | GitHub `GITHUB_TOKEN`（自带 contents/packages 权限） |
| **本地 credential 文件** | `~/.securetrans/*.txt`（不入库） | AI/人手动操作 | gitea/github/gitlab token（ADR-042） |

> 规则（ADR-042）：**token > SSH >> 账号密码**；服务端凭据只走 repo secret/变量，本地凭据文件永不入库。

### 2.5 三阶段职责（ADR-037，三平台统一口径）

```
CI（门禁）   →   Release（发布）   →   CD（部署）
验证一切      只做打包+Release      只做部署+冒烟
静态+版本+env+脚本+全量TDD   离线依赖+主包+镜像+校验    下载+校验+目标机部署+只读冒烟
```

**关键**：CI 是完整门禁；Release 不做验证只做发布；CD 不做验证只做部署（验证在 CI，部署在 CD，职责不重叠）。

---

## 3. 共同三阶段流水线（模板骨架）

```yaml
# 事件触发（三平台差异仅语法）：
#   Gitea:  on: push: tags: ['v*']   /   release: types: [published]
#   GitHub: on: push: tags: ['v*']   /   release: types: [published]
#   GitLab: push: tags: ['v*']       /   workflows 事件语法不同（见 §6）

# ---- CI 阶段（门禁）：push main 或 tag 都跑 ----
#   1. preflight 环境检查（依赖可导入/版本双源/端口/残留清理，ADR-035）
#   2. 静态检查：py_compile + static_check.py（语法/未定义名/重复定义/未使用 import）
#   3. 版本号一致性：src/app.py APP_VERSION == src/static/index.html APP_VERSION
#   4. env 键一致性：dev/test 键集合相等，prod 可多不可缺
#   5. 脚本完整性：deploy/verify/smoke/package/release/ci_test 必须存在
#   6. 全量 TDD：bash infra/ci_test.sh（干净 /data + mock + 性能门禁）

# ---- Release 阶段（tag 触发）：只发布 ----
#   1. 生成 offline-deps（wheelhouse 打包）
#   2. package.sh 打主包（src+tests+infra+docs+env+offline-python）
#   3. 构建运行镜像 → image.tar.gz（或 push registry）
#   4. md5 + sha256 双校验
#   5. 创建/补齐 Release + 上传资产（版本号一律从 app.py 精确提取，禁通配反推 ADR-041）

# ---- CD 阶段（Release 发布后）：只部署 ----
#   1. 解析版本 → 注入部署凭据（SSH key / 目标机信息）
#   2. 下载发布资产 + MD5 校验
#   3. 传输到目标机 → 执行部署脚本（docker 形态，先停旧再起新，ADR-043）
#   4. 只读冒烟（healthz + 版本断言 + 登录；生产绝不写数据 ADR-017）
```

---

## 4. Gitea Actions 详解（本地权威仓）

### 4.1 服务器配置（一次性）

```bash
# 1) Gitea 站点启用 Actions（站点管理 → Actions → 启用）
# 2) 安装 act_runner 并注册（label 指定 CI 镜像容器模式）
act_runner register --instance http://localhost:3000 \
  --token <gitea-admin-生成的注册token> \
  --name securetrans-runner \
  --labels "securetrans-ci:docker://securetrans-ci:3.12"   # ← 容器 label：job 跑在此镜像的容器里
# 3) config.yaml 关键项（容器 label 必须挂宿主 docker.sock，供 release 构建镜像）
#    container.options: "-v /var/run/docker.sock:/var/run/docker.sock"
# 4) 常驻：systemd 或 nohup（WSL 无 systemd 用 nohup 直跑，ADR-040）
# 5) 构建 CI 镜像（wheelhouse 离线依赖自包含）：
#    docker build -f infra/docker/Dockerfile -t securetrans-ci:3.12 infra/docker
```

**依赖安装哲学**：CI 镜像预装全部依赖（wheelhouse 离线包），job 容器**不再联网装依赖**——封闭数据中心可用。

### 4.2 ci.yml（门禁，push main / tag 触发）

```yaml
name: CI-TDD
on:
  push:
    branches: [ main ]        # 分支 push → 常驻门禁
    tags: [ 'v*' ]            # tag push → 与 release.yml 并行（CI 验证 + Release 发布）
jobs:
  ci-check:                   # 单 job 串行（act_runner v0.2.11 对 needs 解析有 bug，ADR-021）
    runs-on: securetrans-ci   # ← 容器 label（§2.3 角色②）
    steps:
      # Step 1: Clone（job 容器是全新的，无代码，经 WSL 网关 clone 本仓库）
      #   CI_GATEWAY 默认 172.17.0.1（容器→宿主 docker bridge 网关）
      #   CI_GITEA_URL=http://<网关>:3000（容器内访问 Gitea 的入口）
      - name: Clone + Python 静态检查
        run: |
          set -euo pipefail
          CI_GW="${CI_GATEWAY:-172.17.0.1}"
          CI_GITEA_URL="${CI_GITEA_URL:-http://${CI_GW}:3000}"
          WS="${GITHUB_WORKSPACE:-/workspace}"        # act_runner 兼容 GitHub 变量名
          cd "$WS"
          if [ ! -f src/app.py ]; then
            rm -rf "$WS"/* "$WS"/.[!.]* 2>/dev/null || true
            git clone --depth 1 "${CI_GITEA_URL}/openwrtadmin/SecureTrans.git" "$WS"
          fi
          PORT=18000 CLEAN_DIR=/data bash infra/preflight.sh   # 环境前置检查（ADR-035）
          python -m py_compile src/app.py tests/test_api.py infra/static_check.py
          python infra/static_check.py src/app.py tests/test_api.py
      # Step 2: 版本双源一致（app.py APP_VERSION == index.html APP_VERSION）
      # Step 3: env 模板 ENV_ROLE 正确（dev/test=test，prod=prod）
      # Step 4: 关键脚本完整性（deploy/verify/smoke/package/release/ci_test 存在）
      # Step 5: 配置键一致性（dev/test 键集合相等，prod 可多不可缺——python 正则比对）
      # Step 6: 全量 TDD（bash infra/ci_test.sh：gunicorn 后台起服 → 干净 /data →
      #          全量 TDD + 性能门禁 → 停服；job 容器销毁，零宿主污染）
```

### 4.3 release.yml（发布，tag 触发）

```yaml
name: Release
on:
  push:
    tags: [ 'v*' ]
jobs:
  release:
    runs-on: securetrans-ci
    steps:
      # Step 1: Clone（--depth 30：Release body 要生成近版变更摘要 git log）
      # Step 2: 生成 offline-deps（镜像内 /wheelhouse 打 tar.gz；无则从旧 Release 下载）
      # Step 3: package.sh 打主包 securetrans-<V>.tar.gz
      # Step 4: Build Docker 运行镜像（重点：容器内 docker CLI → 宿主 docker.sock）
      #   docker build -f infra/docker/Dockerfile.run -t securetrans:v<V> .
      #   docker save securetrans:v<V> | gzip > securetrans-<V>-image.tar.gz   # 第5资产（离线兜底）
      #   md5sum / sha256sum 同生成 .md5/.sha256
      # Step 5: 产物完整性校验
      #   V 必须从 src/app.py 精确提取（禁 ls | head -1 通配反推——ADR-041 教训：
      #   packages/ 同时有主包与 -image 包时字母序会把镜像包当主包 → 错误 tag）
      #   md5sum -c / sha256sum -c 双校验
      # Step 6: 上传 Gitea Release（权限：RELEASETOKEN 仅本 job 注入，最小作用域）
      env:
        RELEASETOKEN: ${{ secrets.RELEASETOKEN }}
      run: |
        # 无 token → 跳过上传（构建校验照常，可走 release.ps1 手工发）
        # 版本精确提取 V；查 Release 是否存在（存在则补资产，不存在则创建）
        # prerelease 动态跟随 APP_STAGE：release=正式，alpha/beta/rc=prerelease
        # 资产清单（7个）：主包 + .md5 + .sha256 + offline-deps + image.tar.gz + .md5 + .sha256
```

### 4.4 cd.yml（CD 部署，Release 发布后触发）

```yaml
name: CD-Deploy
on:
  release:
    types: [ published ]          # Gitea Release 发布 → 自动部署生产
  workflow_dispatch:              # 或手动指定版本部署
jobs:
  deploy:
    runs-on: securetrans-ci
    steps:
      # Step 1: 解析部署版本（release tag > 手动输入 > 最新 tag）
      # Step 2: Clone（获取 infra/cd-deploy.sh 部署脚本）
      # Step 3: 配置 SSH 部署密钥（权限：CD_SSH_KEY 仅本 job，base64 单行存 secret）
      #   echo "${{ secrets.CD_SSH_KEY }}" | base64 -d > ~/.ssh/id_ed25519_securetrans_cd
      #   Host securetrans-prod / HostName 10.10.30.8 / User root / StrictHostKeyChecking accept-new
      # Step 4: 下载发布资产并 MD5 双校验
      #   资产精确匹配（==，禁 endswith 通配——ADR-041：-image 与主包同名前缀）
      #   jq: select(.name=="securetrans-<V>.tar.gz")   ← 精确等于
      #   browser_download_url 为 localhost，容器内替换 host 为 CI_GITEA_URL
      #   主包 MD5 + 镜像 MD5 各自比对
      # Step 5: scp 主包 + 镜像包到 /opt/securetrans-release
      # Step 6: 远程执行 bash -s <版本> < infra/cd-deploy.sh
      #   cd-deploy.sh 内部：校验 → 备份 → 同步程序 → docker-deploy.sh（先 rm 旧容器再起，
      #   满足 ADR-043 切换纪律）→ 内网 IP 只读冒烟（127.0.0.1 判外网 403 是正确行为）
      # Step 7: 结果汇总（podman ps + 内网 health 检查）
```

---

## 5. GitHub Actions 详解（公有云备份仓）

### 5.1 服务器配置（零服务器）

```bash
# GitHub 托管 runner（ubuntu-latest）——无自建 runner、无本地 docker、无需服务器
# 认证（ADR-042）：本地 PAT 存 ~/.securetrans/github-token.txt；git 固定 credential 防弹窗
# 推送 tag 后：CI-TDD（云全量）→ RELEASE（云构建）→ CD-SIM（云仿真）自动串联
```

**与 Gitea 的核心差异**：GitHub 云 VM **可以联网** → 依赖在线安装（`pip install -r requirements.txt`），不需要离线 wheelhouse；云 VM 自带 docker → 镜像构建/仿真运行全在云内完成。

### 5.2 ci.yml（门禁，与 Gitea 同门禁）

```yaml
name: CI-TDD
on:
  push:
    branches: [ main ]
    tags: [ 'v*' ]
  pull_request:                 # GitHub 特有：PR 也触发
jobs:
  ci-check:
    runs-on: ubuntu-latest      # ← 云托管 VM（非容器 label）
    steps:
      - uses: actions/checkout@v7            # 官方 checkout action（代码已就位，无需手写 clone）
      - uses: actions/setup-python@v7        # 官方 Python 安装
        with: { python-version: "3.12" }
      - run: pip install -r infra/docker/requirements.txt   # 在线装依赖
      - run: PORT=18000 bash infra/preflight.sh             # 同 Gitea：环境前置
      - run: python -m py_compile ... && python infra/static_check.py ...
      # 版本双源 / ENV_ROLE / 脚本完整性 / 全量 TDD —— 与 Gitea ci.yml 完全同一套检查
```

> **可移植性要点**：门禁脚本（preflight/static_check/ci_test）是**平台无关**的——三平台 workflow 只是"壳"，真正逻辑全部在 infra/*.sh 里，这就是"同一门禁三处跑"的实现方式。

### 5.3 release.yml（发布，tag 触发）

```yaml
name: RELEASE
on:
  push: { tags: [ 'v*' ] }
  workflow_dispatch:            # 手动指定 tag 补发
jobs:
  release:
    runs-on: ubuntu-latest
    permissions:                # GitHub 特有：job 级权限声明（最小化）
      contents: write           # 创建 Release
      packages: write           # push GHCR
      actions: write            # 触发 CD-SIM
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
      # Step: Build offline-deps（在线 pip download manylinux wheel → 打包结构含 wheelhouse/ 顶层）
      #   pip download --only-binary=:all: --platform manylinux2014_x86_64 --python-version 312 ...
      # Step: Build package tarball（同 Gitea 主包内容 + 4 资产：主包+md5+sha256+offline-deps）
      # Step: Create/Update GitHub Release（幂等）
      env: { GH_TOKEN: ${{ github.token }}}     # ← 内置 token（免手动 secret）
      run: |
        if gh release view "$V" >/dev/null 2>&1; then
          gh release upload "$V" "${FILES[@]}" --clobber    # 已存在 → 补齐/覆盖
        else
          gh release create "$V" "${FILES[@]}" --title "$V" --notes "..."  # 不存在 → 创建
        fi
      # Step: Build & Push Docker image to GHCR（镜像分发走 registry，ADR-038）
      #   docker login ghcr.io -u <actor> --password-stdin（GITHUB_TOKEN 自带权限，零注册）
      #   IMG="ghcr.io/${GITHUB_REPOSITORY,,}"（仓库名必须小写）
      #   docker push ${IMG}:<V> + :latest
      # Step: Trigger CD-SIM（显式 dispatch，绕过"GITHUB_TOKEN 创建的 Release 不触发 release 事件"限制）
```

### 5.4 cd-sim.yml（CD 仿真，云端完成，绝不碰生产）

```yaml
name: CD-SIM
on:
  release: { types: [ published ] }   # Release 发布 → 自动仿真部署
  workflow_dispatch:                  # 手动（带版本参数断言）
jobs:
  deploy-sim:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - run: docker build -f .github/docker/Dockerfile.sim -t securetrans-sim:latest .
            # 云 VM 自带 docker：直接构建运行镜像（Dockerfile.sim = 应用运行镜像）
      - run: |
          docker run -d --name securetrans-sim -p 18000:8000 \
            -e SECURETRANS_DATA=/data -e NAS_ROOT=/data \
            -e APP_STAGE=sim -e ENV_ROLE=test -e AD_MOCK_MODE=true \
            -e RESET_PASSWORD=Init@123456 securetrans-sim:latest
            # 一次性干净容器，端口 18000 与生产 8000 隔离，无持久卷
      - run: |
          # Health + 版本断言（release 事件用 tag 版本断言）
          # 数据洁净门禁：业务文件数==0（staging/external/archive 空）+ 提交记录==0
          # 证明"全新容器、无历史/测试数据，达到生产发布级洁净标准"
```

**为什么 GitHub 不做真实 CD？** 生产在封闭数据中心（10.10.30.8），GitHub 云无法直连；真实生产 CD 由 Gitea 权威仓负责（cd.yml）。CD-SIM 的作用 = **云端证明"代码可部署可运行 + 容器洁净"**，与真实 CD 分工（ADR-036：备份仓永不接触生产）。

---

## 6. GitLab CI/CD 详解（本地实验线）

### 6.1 服务器配置（一次性）

```bash
# 1) GitLab 服务（10.10.30.9，HTTP/SSH 放通）
# 2) 认证（ADR-042）：root 登录创建 PAT → 存 ~/.securetrans/gitlab-token.txt
#    git remote: http://oauth2:<token>@10.10.30.9/root/securetrans.git（token 不入库）
# 3) 安装 gitlab-runner（官方二进制）+ docker executor 注册：
#    gitlab-runner register --url http://10.10.30.9 --token <runner注册token> \
#      --executor docker --docker-image securetrans-gitlab-ci:3.12 \
#      --tag-list gitlabcicotest,docker
# 4) config.toml 关键项（注册后手工改，docker executor 默认 pull_policy=always 会拉远端失败）：
#    [[runners]] name="gitlabcicotest-docker"
#      executor = "docker"
#      [runners.docker] pull_policy = "if-not-present"     # ← 用本地镜像
#        volumes = ["/var/run/docker.sock:/var/run/docker.sock",
#                   "/opt/securetrans-gitlab:/opt/securetrans-gitlab"]  # CD 挂宿主 daemon+数据卷
# 5) WSL 无 systemd → nohup gitlab-runner run &（ADR-040 经验）
# 6) CI 镜像：docker build -f infra/docker/Dockerfile -t securetrans-gitlab-ci:3.12 infra/docker
#    （与 Gitea CI 镜像同源：wheelhouse 来自 Gitea Release offline-deps）
```

### 6.2 .gitlab-ci.yml（单文件三阶段：CI → Release → CD）

```yaml
# 与 Gitea/GitHub 最大的语法差异：三个"workflow"合并在一个 .gitlab-ci.yml 里，
# 用 stages 分阶段 + rules 控制每个 job 在什么事件下运行。

stages: [ ci-check, release, deploy ]

ci-check:
  stage: ci-check
  tags: [ gitlabcicotest, docker ]          # 指定跑在哪个 runner（tag 匹配）
  rules:                                     # 触发条件：分支 push 或 tag push 都跑
    - if: '$CI_COMMIT_BRANCH == "gitlabcicotest"' || if: '$CI_COMMIT_TAG =~ /^v.*/'
  script:
    - bash infra/preflight.sh                # 同 Gitea：环境前置
    - python -m py_compile src/app.py tests/test_api.py infra/static_check.py
    - python infra/static_check.py ...
    - # 版本双源 / env 键 / 脚本完整性 / 全量 TDD（bash infra/ci_test.sh）
  variables:
    GITHUB_WORKSPACE: "$CI_PROJECT_DIR"      # ← GitLab 特有坑：ci_test.sh 探测 /workspace 会失败

release:
  stage: release
  tags: [ gitlabcicotest, docker ]
  rules:
    - if: '$CI_COMMIT_TAG =~ /^v.*/'          # 仅 tag 触发
  script:
    - # 生成 offline-deps（wheelhouse）→ package.sh 主包 → md5/sha256
    - # Build 运行镜像（job 内 docker CLI → 宿主 docker.sock，同 Gitea 方式）
    - # GitLab Release 创建（GITLAB_PAT 变量调 API）：
    #   自动生成 4 个 sources 资产（zip/tar.gz/tar.bz2/tar）——即"发布成功"
    #   文件资产（主包/offline-deps）走 Generic Package Registry 上传
  artifacts:
    paths: [ packages/ ]                      # 传给 deploy 阶段

deploy:
  stage: deploy
  tags: [ gitlabcicotest, docker ]
  rules:
    - if: '$CI_COMMIT_TAG =~ /^v.*/'
  script:
    - # 用 artifacts 里的镜像包 → 独立 docker 部署（宿主 18080→8000，数据 /opt/securetrans-gitlab）
    - # 冒烟必须用容器 IP：docker inspect securetrans-gitlab 取 IP
    #   （job 容器内 localhost 是 job 自己，不是部署容器——ADR-045 教训5）
    - # 实验 env 覆盖 INTERNAL_CIDRS（含 docker bridge 网段）供手工全流程验证
```

### 6.3 GitLab 与 Gitea/GitHub 的关键差异

| 差异点 | GitLab |
|---|---|
| 文件形态 | 单文件 `.gitlab-ci.yml`（stages + rules），不是多 workflow |
| Runner 选择 | `tags` 匹配（`tags: [gitlabcicotest, docker]`） |
| 变量 | `$CI_*` 预置变量（`$CI_COMMIT_TAG`、`$CI_PROJECT_DIR`） |
| Release 资产 | 自动 4 sources + 手动 Generic Package（需 GITLAB_PAT 调 API） |
| 作业间传递 | `artifacts`（上传产物 → 下阶段下载） |
| 特有坑 | `GITHUB_WORKSPACE` 必须显式设 `$CI_PROJECT_DIR` |

---

## 7. 三平台 workflow 级对比矩阵

| 环节 | Gitea Actions | GitHub Actions | GitLab CI/CD |
|---|---|---|---|
| 门禁触发 | push main / tag v* | push main / tag v* / PR | 分支 push / tag v* |
| 门禁内容 | preflight+静态+版本+env+脚本+TDD（容器） | 同（云 VM） | 同（容器） |
| 门禁凭据 | 无（代码克隆经网关匿名/内置 token） | GITHUB_TOKEN | 无（runner 自带 clone） |
| Release 触发 | tag v* | tag v* / 手动 | tag v* |
| Release 权限 | **RELEASETOKEN**（仅 release job） | **permissions 声明 + GITHUB_TOKEN** | **GITLAB_PAT**（变量，仅 release） |
| 发布载体 | Gitea Release（7 资产） | GitHub Release（4 资产）+ GHCR | GitLab Release（4 sources）+ Generic Package |
| 镜像构建 | job 容器内 docker CLI → **宿主 docker.sock** | 云 VM docker build → GHCR | job 容器内 docker CLI → **宿主 docker.sock** |
| CD 触发 | Release published | Release published（→显式 dispatch） | tag（deploy stage） |
| CD 目标 | 生产 10.10.30.8（SSH + docker） | 云端 CD-SIM 18000 仿真 | 实验 18080 独立部署 |
| CD 凭据 | **CD_SSH_KEY**（仅 cd job） | GITHUB_TOKEN | 无（本地 daemon 直接部署） |
| CD 验证 | 只读冒烟 11 项（内网 IP） | 健康+版本+数据洁净断言 | 容器 IP 冒烟 + 登录 |
| 生产接触 | ✅ 唯一真实生产 CD | ❌ 永不 | ❌ 永不 |

---

## 8. 宿主 docker 与 Git 服务器 workflow 的关系（全景图）

```
                        ┌────────────────────────────────────────────────┐
                        │            Git 服务器（三选一）                 │
                        │   Gitea :3000 / GitHub / GitLab :80            │
                        │   仓库 = 代码 + workflow 声明                   │
                        └───────────────┬────────────────────────────────┘
                                        │ 事件（push/tag/release）分发 job
                                        ▼
                        ┌────────────────────────────────────────────────┐
                        │            Runner（执行者）                    │
                        │  Gitea act_runner / GitHub 云 VM / gitlab-runner│
                        └───────────────┬────────────────────────────────┘
                                        │ runs-on / tags 匹配
                                        ▼
                        ┌────────────────────────────────────────────────┐
                        │       Job 容器（每次全新，角色②）              │
                        │   Gitea: docker://securetrans-ci:3.12          │
                        │   GitHub: ubuntu-latest VM（自带 docker）       │
                        │   GitLab: docker executor 同镜像                │
                        │   内部：preflight→静态→版本→env→TDD（CI）      │
                        └───────┬──────────────┬─────────────────────────┘
                                │              │
              CI 阶段（门禁）    │              │ Release 阶段
              （不做发布）       │              │ 容器内 docker CLI
                                ▼              ▼
                   ┌─────────────────────┐   ┌──────────────────────────────┐
                   │  宿主 docker daemon  │◄──┤ docker.sock 挂载（Gitea/GitLab）│
                   │  （WSL 本地 / 生产）  │   │ 构建运行镜像（角色③）          │
                   │  Gitea/GitLab 构建   │   │ image.tar.gz / GHCR            │
                   │  GitHub=云 VM 内 docker│  └──────────────────────────────┘
                   └─────────┬───────────┘
                             │ CD 阶段：image 传输 / pull
                             ▼
                   ┌────────────────────────────────────────┐
                   │  部署目标机（角色④ 运行容器）           │
                   │  Gitea→生产 10.10.30.8 podman 8000      │
                   │  GitLab→实验 18080（/opt/securetrans-gitlab）│
                   │  GitHub→云仿真 18000（CD-SIM）           │
                   │  启动后：只读冒烟（health+版本+登录）    │
                   └────────────────────────────────────────┘
```

**四个要记住的关系**：
1. **workflow 是声明，Runner 是执行**——workflow 文件在仓库，Runner 是独立进程/VM。
2. **docker.sock 是自托管构建的桥**——Gitea/GitLab 的 job 容器靠挂载宿主 docker.sock 来构建镜像（ADR-039 可信代码模型）。
3. **GitHub 全云内闭环**——无 self-hosted runner、无本地 docker；云 VM 即 Runner 又构建又仿真。
4. **CD 目标决定一切**——能连生产（Gitea 本地）→ 真实 CD；不能连（GitHub 云）→ 仿真 CD；要实验（GitLab）→ 独立隔离部署。

---

## 9. 快速入门路径（从零到一）

### 已有这套仓库时，三平台各 5 步跑通

**Gitea（权威）**
1. 站点启用 Actions → act_runner 注册（label 容器模式 + docker.sock 挂载）
2. `docker build -f infra/docker/Dockerfile -t securetrans-ci:3.12 infra/docker`
3. push main → ci.yml 全绿（门禁）
4. 打 tag vX.Y.Z → ci.yml + release.yml 并行（发布）
5. Release 发布 → cd.yml 自动部署生产 + 冒烟

**GitHub（备份/分发）**
1. push 到 GitHub（或 mirror）
2. push main → CI-TDD 全绿（云在线装依赖）
3. 打 tag → RELEASE 云构建 4 资产 + GHCR push + 自动触发 CD-SIM
4. CD-SIM 全绿（健康+版本+数据洁净）
5. Release 页面发布（alpha/beta/prerelease 按阶段）

**GitLab（实验线）**
1. 建仓库 + PAT → push gitlabcicotest 分支
2. gitlab-runner 注册（docker executor + if-not-present + docker.sock + 数据卷）
3. 构建 CI 镜像 → push 分支 → ci-check 全绿
4. 打 tag → release（4 sources + Generic Package）+ deploy（独立 18080）
5. 容器 IP 冒烟 + 手工验证 → 完成实验闭环

### 换新项目复用（三步）
1. 复制三个平台的 workflow 文件（按项目名改 clone URL / 资产名）
2. 确认 infra/preflight.sh + static_check.py + ci_test.sh 与项目匹配（门禁逻辑全在脚本，平台无关）
3. 按 §4.1/5.1/6.1 各配置一次 Runner → push → tag 验证全链路

---

## 10. 触发机制与 AI 边界（2026-09-15 审核，ADR-047）

> 核心结论：**触发全部是 git 服务器原生事件钩子，AI 不在流水线中间介入**；人/AI 只做两件事——
> ① 打 tag（发布决策）② 应急手动 dispatch。成熟期 = 平台自治。

### 10.1 三平台触发事件（逐条审核）

| 平台 | CI | Release | CD | 触发者 |
|---|---|---|---|---|
| Gitea | push main / push tag v* | push tag v* / release | release published / workflow_dispatch | git 事件（自动） |
| GitHub | push main / push tag v* / pull_request | push tag v* / release / workflow_dispatch | release published / workflow_dispatch | git 事件（自动） |
| GitLab | tag ^v / branch gitlabcicotest | tag ^v | tag ^v | git 事件（自动） |

- Gitea 无 pull_request（单分支主干开发，不需要）；GitHub 多 pull_request（云端协作预留）
- GitLab 实验线 ci-check 限定 gitlabcicotest 分支，**推 main 到 GitLab 不触发任何流水线**（2026-09-15 已验证：API 查最近流水线仍为实验线 689/690/691）

### 10.2 发布链：tag 推送后全自动

```text
[人/AI 唯一介入点]  git tag vX.Y.Z && git push <remote> vX.Y.Z   ← 发布决策（ADR-007 人拍板）
        ↓ tag 事件（平台原生钩子，无 AI 介入）
   Gitea:  tag → release.yml(构建7资产+镜像+建Release) → published → cd.yml(真实生产 CD)     全自动
   GitHub: tag → release.yml(云构建4资产+GHCR+建Release) → published → cd-sim.yml(云仿真18000) 全自动
   GitLab: tag → release(实验资产) → deploy(实验 18080 独立容器)                             全自动
```

**tag 推送范围 = 发布范围**：三个 remote 相互独立——
- 推 tag 到 Gitea → 触发**生产 CD**（10.10.30.8 docker 8000）
- 推 tag 到 GitHub → 触发**云闭环**（CI-TDD + Release + GHCR + CD-SIM）
- 推 tag 到 GitLab → 触发**实验线**（18080 独立容器，不碰生产）
- **日常同步只推 main（不推 tag）→ 不触发任何 release/CD**（安全基线）

### 10.3 AI 边界（阶段演进，ADR-047）

| 阶段 | AI 角色 | 平台角色 |
|---|---|---|
| 孵化期（当前已过） | 深度介入：编写 workflow/脚本、配置 runner/secret、试运行与排障 | 执行 |
| 成熟期（目标态） | 只保留：① 发布决策（打 tag + push）② 应急 dispatch 重跑 | **自治**：CI 门禁→Release→CD 全链事件驱动 |

- 门禁逻辑全在 `infra/*.sh`（平台无关），三平台 workflow 只是"壳"——换平台/改门禁不需要 AI 介入流水线本体
- 应急通道：三平台 CD 均有 `workflow_dispatch`（手动触发），用于 release published 偶发失败时重跑

---

## 附：本项目三平台 workflow 索引

| 平台 | 文件 | 职责 |
|---|---|---|
| Gitea | `.gitea/workflows/ci.yml` | CI-TDD 门禁（容器） |
| Gitea | `.gitea/workflows/release.yml` | 发布（7 资产 + 镜像） |
| Gitea | `.gitea/workflows/cd.yml` | 生产 CD（SSH + docker + 冒烟） |
| GitHub | `.github/workflows/ci.yml` | CI-TDD 门禁（云 VM） |
| GitHub | `.github/workflows/release.yml` | 云发布（4 资产 + GHCR + 触发 CD-SIM） |
| GitHub | `.github/workflows/cd-sim.yml` | 云 CD 仿真（18000 + 数据洁净） |
| GitLab | `.gitlab-ci.yml` | 三阶段（ci-check/release/deploy） |

> 关联文档：ADR-016/018/019/020（CI 分层与容器隔离）、ADR-024（CD）、ADR-037（三平台职责对齐）、
> ADR-039（docker.sock 构建）、ADR-042（认证）、ADR-043（docker 部署形态）、ADR-045（GitLab 实验线）。
