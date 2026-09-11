# SecureTrans 部署指南

> 版本：v2.3.6 | 日期：2026-09-11（ADR-017 测试/生产隔离 + ADR-018 CI/CD 分层 + ADR-019 CI 容器隔离与静态门禁）
> 唯一部署文档：测试环境（本地/WSL）? 生产环境（服务器），一个 `DEPLOY_MODE` 开关切换，代码完全复用
> 双 OS 支持：Windows（waitress）/ Linux（gunicorn）；单/双网卡网络隔离

---

## 一、部署模式总览

| 维度 | 测试环境 | 生产环境 |
|------|---------|---------|
| `DEPLOY_MODE` | `testing`（默认） | `production` |
| 文件存储 | 本地磁盘 `./nas` | NAS 挂载 `/mnt/nas/securetrans` |
| WSGI 服务器 | Flask 自带 `python app.py` | Linux: gunicorn / Windows: waitress |
| 反向代理 | 无，直接访问 8000 端口 | nginx 反向代理 + HTTPS |
| 进程管理 | 前台 / nohup | Linux: systemd / Windows: NSSM 或计划任务 |
| AD 认证 | 默认关闭，用本地 admin | 按需开启 |
| 适用场景 | 开发 / 功能验证 / PSF 原型 | PMF 试点 / 正式部署 |

**AD 认证配置（.env 模板 + 管理页可配，v2.2.20+）**：

> **配置权威（ADR-010）**：AD 连接参数运行期以 SQLite `ad_config` 为唯一权威，`.env` 仅作部署模板与首次播种。
> 首次启用 AD：部署完成后登录 admin →「系统配置 → AD 配置」→ 点 **从 .env 导入**（把下方 .env 值读入数据库）→ 按需修改 → **保存**（即时生效，无需重启）。
> 之后改 AD 参数在管理页操作，**改 .env 不再生效**；如需重置回 .env 值，再次点"从 .env 导入"。
> **程序直连 AD 无需服务器入域、无需 SSSD**（v2.2.27 确认）：应用通过 ldap3 协议 bind 查询，与服务器是否加入 AD 域完全独立，与既有 sssd 大规模使用互不干扰。
> **openldap-clients 为部署必装项（v2.2.29，ADR-013）**：提供 `ldapsearch` 供服务器手工验证；deploy.sh 自动安装（联网 `dnf install -y openldap-clients` / `apt install -y ldap-utils`），**离线环境需提前下载 RPM 放入部署包**（可先 `dnf install --downloadonly openldap-clients` 在联网机准备）。未安装不影响系统运行，AD 配置页有「测试连接」可替代手工验证。
> **AD 真实查询 + 连接测试（v2.2.29，ADR-013）**：AD 用户搜索为**真实 LDAP 查询（ldap3，精确匹配）**——用户名后无通配符 `*`，有就是有、没有就是没有；空关键字不返回全量用户（防泄露）。AD 配置卡片新增 **测试连接** 按钮：用当前配置实测 bind，可输入用户名做精确验证（存在/不存在/失败原因），失败原因可读（52e=bind 凭据错、网络不通/base_dn 错等），并写审计日志。
> **手工验证命令（v2.2.27）**：用户管理/审批人 → AD 用户搜索 → 复制页面生成的 `ldapsearch` 命令到服务器执行（bind 密码处替换为实际密码），可独立确认 AD 连通与凭据；`52e` = bind 凭据错误，先查账号密码与 bind DN。

| 配置项（.env 键） | 管理页键 | 默认值 | 说明 |
|--------|------|--------|------|
| `AD_ENABLED` | ad_enabled | `false` | 开启 AD 认证（总开关） |
| `AD_HOST` | ad_host | 空 | `ldap://<DC>:389` 或 `ldaps://<DC>:636` |
| `AD_DOMAIN` | ad_domain | 空 | 构造 UPN `用户名@域`（与 sssd 同协议，兼容） |
| `AD_BASE_DN` | ad_base_dn | 空 | 用户搜索基准，如 `DC=company,DC=com` |
| `AD_BIND_DN` / `AD_BIND_PASSWORD` | ad_bind_dn / ad_bind_password | 空 | 可选服务账户（未配置则用 UPN 直绑）；管理页密码脱敏显示（前2位+****），重新输入才覆盖 |
| `AD_USER_FIELD` | ad_user_field | `sAMAccountName` | 登录名查询属性（企业 AD 定制字段时调整，非硬编码） |
| `AD_DISPLAY_FIELD` | ad_display_field | `displayName` | 显示名属性 |
| `AD_MAIL_FIELD` | ad_mail_field | `mail` | 邮箱属性 |
| `AD_GROUP_FIELD` | ad_group_field | `memberOf` | 组属性 |

**AD 登录验证**：支持 `用户名`（先本地后 AD）/ `域\用户名` / `用户名@AD_DOMAIN` 三种格式；
登录结果与失败原因（未启用/密码错误/连接异常/ldap3 未装）写入审计日志可查；AD 用户登录不落库，
角色默认普通用户，审批权限由 admin 在「审批人配置」按用户名直接配置。

**配置总览（防遗忘）**：「系统配置 → 配置总览」卡片同时展示 `.env` 部署级参数（只读）与数据库运行时配置
（system_config + ad_config，逐项标来源 env/db 与更新时间），一眼识别配置差异与权威位置。

**切换方式**：修改 `.env` 中的 `DEPLOY_MODE` 和 `NAS_ROOT`，换启动命令。代码不变。

**外网下载链路（v2.2.31，ADR-014）**：外网页下载弹窗调用外网专用详情接口 `GET /api/external/submissions/<id>`（仅 approved/downloaded 可见，含文件明细）；管理详情 `/api/submissions/<id>` 外网仍拒绝 403；`/api/health` 已加入外网放行（外网页版本/阶段显示）。外网面完整放行清单：`/login /static/ /api/auth/login|logout|me /api/health /api/external/`，其余一律 403。**外网手工验收清单见 README ADR-014**（菜单仅外网下载/无改密入口/弹窗下载 MD5 一致/管理 URL 403/中英切换正常/强刷防缓存）。



### 1.1 网络模式（单网卡 / 双网卡，部署时二选一）

| 模式 | 配置 | 识别方式 | 适用 |
|------|------|---------|------|
| 单网卡 | `NETWORK_MODE=single`，Nginx 单 server + geo 网段识别 | 按来源 IP 网段（`INTERNAL_CIDRS`）自动分 internal/external | 只有一张网卡，防火墙放行内外网访问同一地址 |
| 双网卡 | `NETWORK_MODE=dual`，Nginx 内/外网两个 server 绑定不同网卡 | 按访问入口（网卡）分面 | 物理隔离的内外网两张网卡 |

应用层只认 `X-Network-Zone` 头（Nginx 注入）；无 Nginx 直连（Windows 本地/单网卡直连）时，应用层按 `INTERNAL_CIDRS` 兜底识别来源网段。**内外网功能隔离由应用层统一保证**：外网面仅开放登录 + 下载，管理/审批/配置接口一律 403，与单/双网卡无关。

.env 示例：
```ini
NETWORK_MODE=single
INTERNAL_CIDRS=10.0.0.0/8,172.16.0.0/12,192.168.0.0/16   # 逗号分隔，留空=全部视为内网
```

---

## 二、测试环境

### 2.1 为什么测试环境在本地构建

企业数据中心完全隔离互联网，服务器上无法安装依赖、无法快速迭代。测试环境构建在本地：
- **Windows 直接运行**：快速开发调试，AI 辅助编码
- **WSL Rocky Linux**：模拟生产 Linux 环境，验证部署脚本和 Linux 兼容性
- 加速测试循环，充分使用 AI 辅助能力
- 验证通过后再推送到隔离的生产服务器

### 2.2 方式 A：Windows 直接运行（最快）

一键部署（自动建 venv + 装依赖 + 生成 .env）：
```powershell
powershell -ExecutionPolicy Bypass -File infra/deploy.ps1 -InstallDir C:\SecureTrans -Start
```

访问 http://localhost:8000，账号 `admin / Init@123456`（统一为 .env `RESET_PASSWORD` 默认值，ADR-009 全链路统一；Windows dev 与生产一致，每次部署重置，见 3.0）。

运行测试（另一个终端）：
```bash
cd tests
python test_api.py    # 318项全通过
```

### 2.3 方式 B：WSL Rocky Linux（模拟生产环境）

```powershell
# 导入 Rocky WSL 镜像（微软无官方 Rocky 镜像，用 D:\iso 下的 Rocky-10-WSL 镜像）
wsl --import rocky10-st D:\wsl\rocky10-securetrans D:\iso\Rocky-10-WSL-Base-10.1-20251116.0.x86_64.wsl
wsl -d rocky10-st
```

```bash
# 进入 WSL 后
dnf install -y python3 python3-pip python3-devel gcc
cp -r /mnt/c/Users/jinta/.doubao/lark-chats/2026-08-25/new-chat ~/securetrans
cd ~/securetrans/src
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python app.py    # 部署模式: testing
```

Windows 浏览器访问 http://localhost:8000（WSL2 自动端口转发）。运行测试：
```bash
cd ~/securetrans/tests && python3 test_api.py   # 318项全通过
```

### 2.4 测试验证清单

- [ ] 访问 http://服务器IP:8000 显示登录页
- [ ] admin 登录成功（密码 = .env `RESET_PASSWORD`，默认 Init@123456，部署重置=测试默认=界面提示；登录后建议尽快修改，不强制）
- [ ] 上传 PDF（匹配特征码，免审批自动通过）
- [ ] 上传 EXE（不匹配，进入人工审批）
- [ ] 上传 ZIP/TAR.GZ（自动解包列清单）
- [ ] 上传 .bit（Vivado Bitstream 识别）
- [ ] 一级审批通过（合作方直接摆渡）
- [ ] 二级审批通过（非合作方摆渡到 external）
- [ ] 外网下载文件成功
- [ ] os.rename 0拷贝验证：staging → external 毫秒级完成
- [ ] 用户管理、特征码规则、审计日志正常
- [ ] 系统工具：备份/恢复/出厂重置/模拟数据（ADR-011；模拟数据仅 testing 环境）

**测试环境数据闭环（ADR-011）**：dev/test 数据策略 = 模拟数据 + 全量验证——
```bash
# 部署时直接出厂重置（清空老库恢复初始状态，自动备份）
RESET_DB=1 sudo bash infra/deploy.sh
# 或运行期：系统工具页点"模拟数据"（确认码 MOCK），或离线脚本
sudo bash infra/ops-mock.sh
# 全量自动化验证（Windows dev 318项 / WSL 生产面 318项，凭据自动取 .env RESET_PASSWORD）
sudo bash infra/verify.sh
```


---

## 2.5 环境一致性（关键：为什么 WSL 成功、服务器失败）

**三环境路径约定（已对齐）**：

| 环境 | 安装目录 | NAS_ROOT | 存储/启动方式 | systemd |
|------|---------|----------|--------------|---------|
| 本地 Windows dev | `src/` | 默认 `src/nas`（testing） | 本地文件系统 + Flask 内置 | 无 |
| WSL 测试（影子环境） | `/opt/securetrans` | `/mnt/nas/securetrans` | NAS 目录 + gunicorn + systemd | 257 |
| 服务器生产 | `/opt/securetrans` | `/mnt/nas/securetrans` | NAS 挂载 + gunicorn + systemd | 239 |

**为什么 WSL 成功而 ESXi 服务器失败（226/NAMESPACE）**：
1. **systemd 版本差异（主因）**：WSL Rocky10 = systemd 257，**忽略** ReadWritePaths 中不存在的路径；ESXi Rocky 8.10 = systemd 239，**严格失败**（226/NAMESPACE）
2. **路径存在性（诱因）**：服务器 NAS 未挂载 → `/mnt/nas/securetrans` 不存在；WSL 当时特意用了存在且干净的 `/var/nas/securetrans`
3. **CRLF 污染（帮凶）**：`.env`/service 模板 CRLF → `NAS_ROOT` 值带 `\r` → 异形目录 + ReadWritePaths 渲染异常路径
4. v2.2.0 时代 WSL 的 service 模板是 CRLF，ReadWritePaths 带 `\r`（路径"不存在"），257 忽略 → 服务照常启动；同样的模板在 239 上必炸

**因此**：WSL 无法直接复现 226（257 太宽容），deploy.sh 已加 **preflight 自检** 兜底——检查 ReadWritePaths 每个路径存在且无 CR，WSL 跑通 = 服务器行为一致。

**部署注意（防再次踩坑）**：
- 不要从 Windows 工作区直接运行 `deploy.sh`（`src/` 含本地开发产物 `.env`/`data`/`nas`/`venv`）；deploy.sh 已用 tar 排除这些目录并保护生产 `.env`
- 全量测试前必须**重置干净基线**：删除 `data/securetrans.db` + 清空 NAS 下 `staging/external/archive`（admin 密码由 deploy.sh 自动重置为 .env `RESET_PASSWORD`，无需手工重置）；**推荐用 `RESET_DB=1 bash infra/deploy.sh`（ADR-011 自动备份+出厂重置）**
- `.env` 用 LF 保存（Windows 记事本会写 CRLF，VSCode 右下角可切换）

## 三、生产环境部署（封闭数据中心）—— Rocky 8.10

> 适用：新建 Rocky Linux 8.10 虚拟机服务器（可配置 mirrors 在线源，但**默认走离线包**）

### 3.0 一键式部署（推荐，Python 3.12 自动获取）

上传部署包后，一条命令完成全部部署（Python 获取 → venv → 依赖 → .env → systemd → 启动验证）：

```bash
# 1. 上传部署包（含内置 offline-deps 离线 wheel）并解压
tar xzf securetrans-<版本>.tar.gz -C /opt/securetrans --strip-components=1
# 2. 一键部署（root 运行）
sudo bash /opt/securetrans/infra/deploy.sh
# 3. 验证（ADR-017 测试/生产隔离）：
#    - 开发/测试环境（ENV_ROLE=test）：全量 TDD
#      sudo bash /opt/securetrans/infra/verify.sh
#    - 生产环境（ENV_ROLE=prod）：只读冒烟（allowlist 组24，10项；不创建任何业务数据）
#      sudo bash /opt/securetrans/infra/smoke.sh
#    - 注意：ENV_ROLE=prod 下误跑 verify.sh 会被 fail-safe 拒绝（组1~23 不执行），请用 smoke.sh
sudo bash /opt/securetrans/infra/verify.sh
```

> **部署凭据（ADR-009，全链路统一）**：**每次运行 deploy.sh 都会将 admin 密码重置为 `.env` 的 `RESET_PASSWORD`**
> （默认 `Init@123456`；init_db 播种 / 部署重置 / verify·test 默认凭据 / 登录页提示全部同源）。因此：
> - 部署完成即可用 `admin / <RESET_PASSWORD>` 登录，verify.sh 自动使用该凭据验证
> - 登录后请立即修改 admin 密码；之后若需再跑 verify，用 `VERIFY_ADMIN_PASS=<你的密码> sudo bash infra/verify.sh` 显式传参
> - `.env` 缺失 `RESET_PASSWORD` 行时 deploy.sh 自动追加默认值；改密码只改 .env 这一处

**Python 3.12 三种获取方式**（deploy.sh 自动按序尝试）：

| 优先级 | 来源 | 说明 |
|--------|------|------|
| 1 | 系统已有 Python 3.10+（**优先 3.12**） | 优先用 3.12（匹配 cp312 wheel）；非 3.12 且部署包有离线 3.12 RPM 时自动切换 3.12 |
| 2 | `offline-python/*.rpm`（离线） | 见下方「离线 Python 获取」 |
| 3 | 在线 `dnf module` 安装 | 需网络，防火墙临时放行 80/443 访问镜像 |

**离线 Python 获取**（在可联网的 Rocky 8 环境运行一次，生成 RPM 随部署包携带）：

```bash
sudo bash infra/get-offline-python.sh   # 产出 offline-python/*.rpm（python3.12 + 依赖）
# 将整个 offline-python/ 目录随部署包携带；离线服务器一键部署自动 dnf localinstall
```

> **网络要求**：完全离线时无需放行外网（Python RPM + 离线 wheel 全内置）；仅当走"在线安装"分支时，才需防火墙临时放行 80/443 访问镜像源（repo.huaweicloud.com / mirrors.aliyun.com / mirrors.rockylinux.org）。

### 3.1 分阶段执行手册（可选，逐步验证）

> 一键部署已自动完成 阶段0-3。如需逐步验证每个环节（测试→生产→NAS→网络隔离→验收），按以下阶段执行，每阶段有明确"通过标准"，测试不过不进下一阶段。

> 总览：阶段0 基础准备 → 阶段1 上传+离线依赖 → 阶段2 测试环境验证 → 阶段3 生产环境验证 → 阶段4 NAS → 阶段5 网络隔离 → 阶段6 手工验收+内部试用

### 阶段0：服务器基础准备（一键部署已自动完成，此处为手工参考）

```bash
cat /etc/rocky-release                 # 确认 Rocky Linux release 8.10
hostnamectl                            # 确认主机名、系统
ip a                                   # 确认 IP（阶段5 会加第二块网卡）
dnf repolist                           # 确认 mirrors 源 repo 可用

# 安装 Python 3.12（Rocky 8 AppStream 直接提供 python3.12 包套件，无需 module enable、无需源码编译）
# 若 AppStream 缺失（老版本/精简源），先启用 EPEL 8: dnf install -y epel-release
dnf install -y python3.12 python3.12-pip python3.12-devel
alternatives --set python3 /usr/bin/python3.12 2>/dev/null || true
python3 --version          # 预期 Python 3.12.x
python3 -m venv --help >/dev/null && echo "venv OK"

# 基础工具
dnf install -y tar gzip curl nginx git
systemctl enable --now nginx 2>/dev/null || true

# 防火墙（如启用）：内网联调先放行 8000，阶段5 后改由 Nginx 80/443 代理
systemctl status firewalld --no-pager | head -3
firewall-cmd --permanent --add-port=8000/tcp && firewall-cmd --reload
```

> 备选：若 module 里没有 3.12，可用 `dnf install -y python3.11`（离线 wheel 按 cp312 打包，若用 3.11 需另取对应 wheel，建议统一 3.12）。

### 阶段1：上传部署包 + 离线安装依赖

把 `securetrans-<当前版本>.tar.gz`（如 v2.2.14）从本地传到服务器（scp / U盘 / 堡垒机）：

```bash
scp securetrans-2.1.0.tar.gz root@<服务器IP>:/root/

# 解压到安装目录
mkdir -p /opt/securetrans
cd /root
tar xzf securetrans-2.1.0.tar.gz -C /opt/securetrans --strip-components=1
ls /opt/securetrans        # 应看到 src/ tests/ infra/ docs/ offline-deps/ offline-deps-win/ README

# 创建虚拟环境 + 离线安装依赖（离线 wheel 已内置 offline-deps/）
cd /opt/securetrans/src
python3 -m venv venv
./venv/bin/pip install --no-index --find-links=/opt/securetrans/offline-deps -r requirements.txt
./venv/bin/pip install --no-index --find-links=/opt/securetrans/offline-deps gunicorn==21.2.0

# 验证（必须都成功）
./venv/bin/python -c "import flask, flask_login, bcrypt, apscheduler, ldap3, gunicorn; print('依赖 OK:', flask.__version__)"
```

> **在线备选**（若服务器临时可上网）：`./venv/bin/pip install -r requirements.txt && ./venv/bin/pip install gunicorn`。离线包始终保留，数据中心部署首选离线。

### 阶段2：测试环境部署 + 自动化测试（DEPLOY_MODE=testing）

> 目的：先用最简模式（本地文件系统 + Flask 自带服务器）确认程序在服务器上能跑、318项全过。

```bash
cd /opt/securetrans/src
cp env/test.env .env
grep -E '^(DEPLOY_MODE|NAS_ROOT)=' .env   # 应为 DEPLOY_MODE=testing, NAS_ROOT=./nas

nohup ./venv/bin/python app.py > /tmp/st-testing.log 2>&1 &
sleep 4
curl -s http://127.0.0.1:8000/api/health
# 预期: {"deployMode":"testing","status":"ok",...}

cd /opt/securetrans/tests
python3 test_api.py
# 预期: 总计318 | 通过318 | 通过率100.0%
```

**通过标准**
- [ ] 健康检查返回 `deployMode":"testing"`
- [ ] 318项测试 100% 通过
- [ ] 浏览器访问 `http://<内网IP>:8000`，admin 登录（密码 = .env `RESET_PASSWORD`，默认 Init@123456；登录后建议尽快修改，不强制）

### 阶段3：生产环境部署 + 自动化测试（DEPLOY_MODE=production）

> 目的：切到生产模式（gunicorn + systemd），本地磁盘先当存储，验证生产形态全链路。
> 也可直接用 `bash infra/deploy.sh` 一键部署（9 步自动化，等价于阶段0-3，root 执行）。

```bash
pkill -f 'app.py' || true
sleep 1
cd /opt/securetrans/src
cp env/prod.env.template .env

# 先用本地磁盘当存储（阶段4 再切 NAS）
sed -i 's|^NAS_ROOT=.*|NAS_ROOT=/opt/securetrans/nas|' .env
# 生成随机 SECRET_KEY
SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
sed -i "s|^SECRET_KEY=.*|SECRET_KEY=${SECRET}|" .env
grep -E '^(DEPLOY_MODE|NAS_ROOT|HOST|PORT|FLASK_DEBUG|SECRET_KEY)=' .env

# 安装 systemd 服务（gunicorn 2 worker）
cd /opt/securetrans
cp infra/securetrans.service /etc/systemd/system/securetrans.service
# 关键：本阶段 NAS_ROOT 是本地目录，systemd 的 ReadWritePaths 需放开（阶段4 再指向 /mnt/nas）
# 注：service 含 PrivateTmp/ProtectSystem=strict/ReadWritePaths 加固（实测兼容 systemd 239/257）；
# 但 systemd 239（RHEL8/Rocky8）对 ReadWritePaths 中不存在的路径（如 NAS 未挂载）启动报 226/NAMESPACE——
# deploy.sh 已按 NAS_ROOT 存在性渲染（不存在则仅 /opt/securetrans）；NAS 挂载后重跑部署自动补全。
# 注意：.env 若在 Windows 编辑保存为 CRLF（行尾 \r\n），NAS_ROOT 值会带 \r，
# 将创建"异形目录"(securetrans$'\r') 且 ReadWritePaths 渲染含 \r 路径，再次触发 226——
# deploy.sh 现已自动将 .env 转 LF 并剥离 NAS_ROOT 的 \r；如服务器已有异形目录，先清理再重跑部署：
#   rm -rf "/mnt/nas/securetrans"$'\r' && sed -i 's/\r$//' /opt/securetrans/.env && bash infra/deploy.sh
systemctl daemon-reload
systemctl enable --now securetrans
systemctl status securetrans --no-pager -l | head -15

# 生产模式验证 + 全量自动化测试
curl -s http://127.0.0.1:8000/api/health
# 预期: {"deployMode":"production",...}
systemctl is-active securetrans       # 预期 active
cd /opt/securetrans/tests
python3 test_api.py    # 自动读取 /opt/securetrans/.env 的 NAS_ROOT，无需手工传参；
                        # 若 .env 缺失（直接跑 app.py 未部署），才需手工指定：NAS_ROOT=... python3 test_api.py
# 预期: 总计318 | 通过318 | 通过率100.0%
```

**通过标准**
- [ ] systemd 服务 active，`deployMode":"production"`
- [ ] 318项测试 100% 通过（生产模式）
- [ ] 确认 gunicorn 多 worker 无并发初始化报错
- [ ] 首次访问初始化正常：`/opt/securetrans/data/securetrans.db`、`/opt/securetrans/nas/{staging,external,archive}` 自动创建

### 阶段4：NAS 切换（本地磁盘 OK 后）

> 前置：阶段3 全部通过。staging/external/archive 三个目录**必须在同一个文件系统**，os.rename 才能 0拷贝。

```bash
# 在 NAS 存储管理端（如 TrueNAS）创建 dataset，例如 securetrans，记录导出路径如 /mnt/tank/securetrans
# 服务器上创建挂载点并挂载（NFS 示例）
mkdir -p /mnt/nas/securetrans
mount -t nfs <NAS_IP>:/mnt/tank/securetrans /mnt/nas/securetrans
echo '<NAS_IP>:/mnt/tank/securetrans /mnt/nas/securetrans nfs defaults,_netdev 0 0' >> /etc/fstab

# 迁移本地 nas 中已有数据（若需保留；全新环境可跳过）
cp -a /opt/securetrans/nas/. /mnt/nas/securetrans/ 2>/dev/null || true

# 切 NAS_ROOT + systemd ReadWritePaths 指回 NAS
cd /opt/securetrans/src
sed -i 's|^NAS_ROOT=.*|NAS_ROOT=/mnt/nas/securetrans|' .env
sed -i 's|/opt/securetrans/nas|/mnt/nas/securetrans|' /etc/systemd/system/securetrans.service
systemctl daemon-reload && systemctl restart securetrans

# 验证
curl -s http://127.0.0.1:8000/api/health   # production + ok
df -h /mnt/nas/securetrans/staging /mnt/nas/securetrans/external /mnt/nas/securetrans/archive | awk '{print $1,$NF}'
# 三行 Filesystem 必须相同
```

**通过标准**
- [ ] NAS 三个目录同一文件系统
- [ ] 生产模式在 NAS 上再跑 318项自动化测试 100%
- [ ] os.rename 0拷贝：上传→审批→摆渡 毫秒级

> **说明：测试/内网试用阶段不需要 Nginx**——gunicorn 已是生产 WSGI 服务器，直接监听 8000 即可完整服务。
> Nginx 仅为以下场景可选安装：① 双网卡隔离（注入 X-Network-Zone 头）；② HTTPS 对外；③ 大文件上传限制（client_max_body_size）。
> 安装：`dnf install nginx`（离线环境需提前下载 nginx RPM 随包携带）；配置模板：`infra/nginx-securetrans.conf`（双网卡）/ `infra/nginx-securetrans-single.conf`（单网卡按网段识别）。


### 阶段5：网络隔离（双网卡 / 单网卡 geo 二选一）

> 应用层网络面隔离（读 X-Network-Zone 头）已被 test_api.py 在本地 100% 覆盖；本阶段验证**真实网络隔离 + Nginx 头注入**。

**5.1 双网卡模式**（物理隔离内外网两张网卡时）：

```bash
# 虚拟机配置双网卡（VM 层手工完成）：添加第二块虚拟网卡（外网面），配置两块网卡 IP，确认路由
cd /opt/securetrans
cp infra/nginx-securetrans.conf /etc/nginx/conf.d/securetrans.conf
vi /etc/nginx/conf.d/securetrans.conf
# 修改：内网 server_name → securetrans.internal.<域名>；外网 server_name → securetrans.external.<域名>
#       确认两个 server 分别绑定各自网卡 IP、proxy_set_header X-Network-Zone internal / external
nginx -t && systemctl reload nginx
```

**5.2 单网卡模式**（只有一张网卡、防火墙放行内外网访问同一地址时）：

```bash
cd /opt/securetrans
cp infra/nginx-securetrans-single.conf /etc/nginx/conf.d/securetrans.conf
vi /etc/nginx/conf.d/securetrans.conf
# 修改：server_name → 实际域名/IP；geo $network_zone 中的网段 → 实际内网网段（与 INTERNAL_CIDRS 一致）
nginx -t && systemctl reload nginx
```

应用层 .env 同步：`NETWORK_MODE=single` + `INTERNAL_CIDRS=<内网网段>`。无 Nginx 直连（Windows 本地 / 单网卡直连）时应用层按网段兜底，行为一致。

**5.3 验收**：按 `09-preprod-verification.md` 执行——内网面完整功能、外网面仅下载、外网管理接口 403、Nginx 头注入确认、防火墙两网卡规则。

**通过标准**
- [ ] 内网地址访问管理面正常
- [ ] 外网地址仅能下载，管理接口 403
- [ ] `nginx -T` 确认头注入（双网卡：两个 server；单网卡：geo 网段）

### 阶段6：手工验收 + 内部试用发布

**6.1 清理初始测试数据（重要）**：自动化测试会在数据库写入测试数据，内部试用前恢复干净初始状态：

```bash
# 方式A：重置数据库（推荐，全新开始）
systemctl stop securetrans
rm -f /opt/securetrans/data/securetrans.db /opt/securetrans/data/securetrans.log
rm -rf /opt/securetrans/nas/staging/* /opt/securetrans/nas/external/* /opt/securetrans/nas/archive/*
systemctl start securetrans
# 首次启动自动重建 admin/Init@123456（= .env RESET_PASSWORD 默认）、默认系统配置、特征码模板(默认禁用)
# 方式B：仅清理业务数据（保留配置，用 Web 界面删测试用户/合作方/特征码）
```

**6.2 配置正式数据**（Web 界面，admin 登录）：
- [ ] 修改 admin 初始密码
- [ ] 创建正式用户（普通用户）+ 设置是否使能（生产默认关闭，admin 永久使能）
- [ ] 配置一级/二级审批人
- [ ] 配置合作方白名单（是否使能）
- [ ] 按需启用特征码规则（默认模板全禁用，按需打开）
- [ ] 确认系统配置：免审批总开关、默认有效期 7 天、最大文件 800MB

**6.3 手工验收清单**：

| # | 验收项 | 结果 |
|---|--------|------|
| 1 | admin 登录（密码 = .env RESET_PASSWORD，默认 Init@123456）+ 建议尽快修改（不强制） | ? |
| 2 | 普通用户内网面菜单（文件提交/我的提交/外网下载） | ? |
| 3 | 外网面仅下载、管理菜单不可见 | ? |
| 4 | 提交文件→特征码匹配免审批直通 / 不匹配进审批 | ? |
| 5 | 一级审批→合作方直通；二级审批→非合作方摆渡 | ? |
| 6 | 一级审批人=二级审批人时自动跳过二级（语义B） | ? |
| 7 | 外网下载文件成功，内容完整 | ? |
| 8 | 过期文件自动归档（audit 日志确认） | ? |
| 9 | 审计日志 + 统计 Tab（人员/文件类型/每日） | ? |
| 10 | os.rename 0拷贝：摆渡毫秒级 | ? |
| 11 | 大文件（>100MB）上传/下载正常 | ? |
| 12 | 大文件端到端完整性：下载内容 MD5 = 响应头 X-File-MD5 = 上传时 MD5 | ? |

**6.3.1 性能与完整性验证（v2.2.24 起）**：

| 项 | 命令 | 说明 |
|----|------|------|
| 800MB 全链路性能 + MD5 完整性 | `python tests/perf_test.py http://<服务器IP>:8000` | 上传→审批摆渡→下载全链路计时 + MD5 四方一致；退出码 0=通过 |
| 生产凭据 | `PERF_ADMIN_USER` / `PERF_ADMIN_PASS`（或 `VERIFY_ADMIN_PASS` 同源） | 生产 admin 已被改密时必填 |
| 测试文件大小 | `PERF_SIZE_MB`（默认 800） | 按需调整（如 100/500） |
| 阈值 | `PERF_MAX_UPLOAD_S` / `PERF_MAX_DOWNLOAD_S` / `PERF_MAX_TOTAL_S` | 默认 600/600/900 秒 |
| 保留数据 | `PERF_KEEP=1`（默认自动清理） | 测试完成后自动删除提交单与临时文件 |

**6.3.2 上传大小配置（v2.2.24 起统一口径）**：
- `.env` 新增 `MAX_FILE_SIZE_MB`（单文件大小上限，默认 800）；请求体限制 `MAX_CONTENT_LENGTH` 自动 = 文件上限 + 1MB（multipart 封装余量），**不要手工配置 MAX_CONTENT_LENGTH**。
- 兼容旧 .env：若仍配置了 `MAX_CONTENT_LENGTH` 且未配置 `MAX_FILE_SIZE_MB`，文件上限自动取该值-1MB（迁移建议：改配 MAX_FILE_SIZE_MB）。
- 运行时界面"系统配置→最大文件大小"保存后生效（来源=DB，见 5.1 配置权威矩阵）。

**6.4 内部试用发布**：
- [ ] 通知试用用户（内网地址）
- [ ] 设定试用期与反馈收集方式（见 `03-psf-process.md`）
- [ ] 试用期结束按 PMF 流程评估（`04-pmf-process.md`）

### 附录：常见问题

| 问题 | 处理 |
|------|------|
| 服务启动失败 | `journalctl -u securetrans -n 100` → 检查端口占用 `ss -tlnp \| grep 8000` |
| 页面无法访问 | 检查 nginx → 防火墙 → 直接测后端 `curl http://127.0.0.1:8000/api/health` |
| 摆渡失败 | 确认 staging/external/archive 同文件系统 `df -h` → 检查目录权限 |
| 大文件上传失败 | 检查 `MAX_CONTENT_LENGTH` → nginx `client_max_body_size` → 磁盘空间 |
| 外网下载 403 | 确认 Nginx 是否注入 `X-Network-Zone: external` / geo 网段是否含该来源 |

---

### 阶段7：正式上线——内部 Alpha 测试（可选不启动 Nginx）

> **结论：Alpha 阶段可以不启动 Nginx**，gunicorn 直接监听（绑定地址由 .env HOST/PORT 控制，restart 即生效）即可供内部测试人员访问；只需防火墙放行 8000 端口。
> 初期访问量不大、以功能与基本性能为验证目标，无需 Nginx 的反代/HTTPS/大文件能力。

**网络面隔离（无 Nginx 时仍生效）**：
应用层 `get_network_zone()` 两级识别——① 优先读 Nginx 注入的 `X-Network-Zone` 头；② 未注入时按
客户端 IP + `INTERNAL_CIDRS` 网段兜底（直连/无代理场景）。因此不启动 Nginx 时，外网 IP 访问管理接口
仍返回 403，隔离能力不丢失（318项测试含网络面用例）。

**Alpha 测试访问路径**：数据中心内网与办公外网用户访问**同一网址** `http://10.10.30.8:8000`，
应用层按源 IP 自动分面——内网网段（10.10.10.0/24、10.10.30.0/24）→ internal 全功能（提交/审批/管理）；
办公外网网段 → external 仅登录+下载（防从外网发起提交/审批/管理）。

**步骤（在阶段6 手工验收通过后）**：

```bash
# 1. 配置监听地址（二选一）
#    方案A 单网卡：监听全部网卡，应用层 INTERNAL_CIDRS 识别内外网（默认已配 HOST=0.0.0.0）
#    方案B 双网卡物理隔离：只监听内网 IP，外网卡不开放 8000 端口（无需 Nginx 即内外网隔离）
sed -i 's|^HOST=.*|HOST=<内网IP或0.0.0.0>|' /opt/securetrans/.env

# 2. 使绑定生效（v2.2.9+：systemd 变量展开，改 .env 后 restart 即生效，无需重跑部署）
sudo systemctl restart securetrans

# 3. 防火墙放行 8000 —— Alpha 内测（数据中心内网 + 办公外网都要能访问）
#    场景说明：内/外网均属公司内部网络，无 NAT、不向互联网开放、无攻击威胁 → 简单放行即可
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --reload
#    可选最小权限（按网段限定，适合想收紧的场景）：
#    sudo firewall-cmd --permanent --add-rich-rule='rule family=ipv4 source address=10.10.10.0/24 port port=8000 protocol=tcp accept'
#    sudo firewall-cmd --permanent --add-rich-rule='rule family=ipv4 source address=10.10.30.0/24 port port=8000 protocol=tcp accept'
#    sudo firewall-cmd --permanent --add-rich-rule='rule family=ipv4 source address=<办公外网网段> port port=8000 protocol=tcp accept'
#    sudo firewall-cmd --reload
#    验证放行：sudo firewall-cmd --list-all | grep 8000

# 4. 验证监听与访问
ss -tlnp | grep 8000        # 期望 0.0.0.0:8000 或 <内网IP>:8000（非仅 127.0.0.1）
# 数据中心内网用户访问 http://10.10.30.8:8000（源IP在内网段 → internal 全功能）
# 办公外网用户访问 http://10.10.30.8:8000（源IP为办公网段 → external 仅登录+下载）
# 办公外网如需经防火墙 DNAT/路由转发，须保留原始源 IP（不 SNAT），应用层才能正确分面

# 5. 回归确认
cd /opt/securetrans/tests && python3 test_api.py   # 318项全通过
```

**何时再引入 Nginx**（Alpha 验证结束、正式发布前）：
- 需要 HTTPS（对外/合规）
- 需要 Nginx 大文件上限（client_max_body_size，当前 gunicorn 直连按 .env MAX_CONTENT_LENGTH 生效）
- 需要 Nginx 注入 `X-Network-Zone` 权威头（双网卡正式模式）
- 需要负载均衡/静态资源加速

## 四、Windows 服务器部署（可选，与 Linux 同等一键式）

客户端/服务器是 Windows 时同样支持，无需 Nginx（应用层网段识别直接生效）。

**Python 3.10+ 三种获取方式**（deploy.ps1 自动按序尝试）：

| 优先级 | 来源 | 说明 |
|--------|------|------|
| 1 | 系统已装 Python 3.10+（**优先 3.12**） | 优先用 3.12；非 3.12 且 offline-python-win 有 3.12 安装器时自动切换 3.12 |
| 2 | `offline-python-win/python-*.exe`（离线） | 官方安装器放入该目录，deploy.ps1 自动静默安装 |
| 3 | 在线下载安装 | https://www.python.org/downloads/ ，勾选 *Add python.exe to PATH* |

```powershell
# 1. 上传/解压发布包到服务器，进入项目根目录
# 2. 一键部署（离线优先：Python 自动获取 + venv + 离线 wheel + .env + 启动）
powershell -ExecutionPolicy Bypass -File infra/deploy.ps1 -InstallDir C:\SecureTrans -Start
# 3. 编辑 .env：NAS_ROOT、INTERNAL_CIDRS、SECRET_KEY
notepad C:\SecureTrans\.env
# 4. 生产启动（waitress，Windows 生产推荐，替代 Linux 的 gunicorn）
cd C:\SecureTrans
.\venv\Scripts\waitress-serve.exe --host=0.0.0.0 --port=8000 app:app
```

Windows 服务化（开机自启）可用 NSSM：`nssm install SecureTrans` 指向 venv python + app.py；或用计划任务。单网卡直连时，`INTERNAL_CIDRS` 决定内外网：内网段全功能，非内网段仅登录+下载。

**Windows 部署验证清单**（与 Linux 同等完善）：

| # | 验证项 | 结果 |
|---|--------|------|
| 1 | `python --version` ≥ 3.10（deploy.ps1 自动检测） | ? |
| 2 | 一键部署成功，`C:\SecureTrans\.env` 生成 | ? |
| 3 | 访问 http://localhost:8000，admin 登录（密码 = .env RESET_PASSWORD） | ? |
| 4 | 运行全量测试：`cd tests; python test_api.py`（318项） | ? |
| 5 | waitress 生产启动健康检查通过 | ? |
| 6 | 单网卡隔离：内网段全功能，非内网段仅登录+下载（管理接口403） | ? |
| 7 | NSSM/计划任务服务化（可选） | ? |

---

## 五、日常运维

### 5.1 配置权威矩阵（ADR-010，改配置前先看这里）

**三档配置，各档唯一权威，禁止双重配置**：

| 档位 | 权威位置 | 怎么改 | 生效方式 |
|------|---------|-------|---------|
| 部署级配置 | `.env` | 编辑 `.env` | 改后 `systemctl restart securetrans` |
| 运行时配置 | 数据库 system_config | 系统配置页（界面） | 即时生效，**不再回写 .env** |
| AD 连接配置 | 数据库 ad_config | 系统配置页 → AD 配置（导入 .env / 保存） | 即时生效，空值回退 .env/默认 |

- 部署级配置 = DEPLOY_MODE / HOST / PORT / INTERNAL_CIDRS / NAS_ROOT / SECURETRANS_DATA / SECRET_KEY / RESET_PASSWORD / APP_STAGE（发布阶段 alpha→beta→rtm→release，页面显示 vX.Y.Z-stage）
- 运行时配置 = app_name / auto_approval_enabled / default_expiry_days / max_file_size_mb（界面保存即权威，.env 同步回写已删除，防两处漂移）
- AD 连接配置 = 上方 AD 表 10 键；首次部署表空自动从 .env 播种（source=env），管理页可"从 .env 导入"/保存（source=db）
- **防遗忘机制**：系统配置页「配置总览」卡片左右对照——左 `.env` 只读、右 DB 配置，逐项标来源 env/db 与更新时间
- **冲突规则**：DB 优先（运行时/AD 配置界面保存即权威；.env 仅部署级参数与首次播种，不参与运行期业务判断）

### 5.2 常用运维命令

```bash
sudo systemctl status securetrans       # 查看状态
sudo systemctl restart securetrans      # 重启
sudo journalctl -u securetrans -f       # 实时日志
tail -f /opt/securetrans/data/securetrans.log  # 应用日志
sudo sqlite3 /opt/securetrans/data/securetrans.db ".backup /backup/securetrans_$(date +%Y%m%d).db"  # SQLite 热备份
```

### 5.3 数据生命周期（ADR-011）：备份 / 恢复 / 出厂重置 / 模拟数据

**三环境一套代码配置数据脚本**：dev(Windows) / test(WSL) / prod(Rocky) 程序与配置完全一致（DEPLOY_MODE 开关 + .env），
差异只在数据策略——dev/test 用 **模拟数据 + verify.sh 全量验证**闭环，prod 用 **备份/恢复/出厂重置**；
代码、配置、数据三者分离，可自由组合。运维期内有用的功能已收进系统（admin 菜单"系统工具"），脚本仅保留离线场景。

**方式 A：系统工具页（在线，推荐日常使用）**——admin 登录 → 系统工具：
- 立即备份 / 备份列表 / 恢复（确认码 RESTORE），**备份拆分 scope（v2.2.27）**：
  - **系统备份（system）**：仅系统 DB（system_config/ad_config/users/audit 等），升级/回退前后用
  - **业务数据备份（business）**：仅 NAS 业务文件（staging/external/archive），更换存储目录/历史归档用
  - 列表含 hasDb/hasNas 标记，恢复按备份类型还原
- 出厂重置（确认码 RESET；**自动先备份** → 清空 → 出厂状态，admin 密码重置为 .env RESET_PASSWORD）
- 模拟数据（确认码 MOCK；**仅 DEPLOY_MODE=testing**，生产 403）

**方式 B：离线脚本（服务停止时最安全；生产手工运维首选）**：
```bash
sudo systemctl stop securetrans                       # 可选，文件级操作更安全
sudo bash infra/ops-backup.sh [all|system|business]   # 备份 → data/backups/backup-<时间戳>（scope 默认 all）
sudo bash infra/ops-restore.sh backup-20260909_120000 [all|system|business] # 恢复（先 ls data/backups/ 看名称）
sudo bash infra/ops-reset.sh                          # 备份+清理 → 出厂重置（admin 密码= .env RESET_PASSWORD）
sudo bash infra/ops-mock.sh                           # 模拟数据（仅 testing 环境；配 verify.sh 做验证闭环）
```

**部署时出厂重置（测试环境）**：`RESET_DB=1 sudo bash infra/deploy.sh`（deploy.sh 9.8 步：清空老库恢复出厂，原数据自动备份）。

**注意**：
- 恢复/出厂重置会替换当前全部业务数据，回退 = 再恢复之前的备份；审计日志回到备份/出厂时点。
- 恢复应在同一部署路径执行（提交单 current_path 为绝对路径，跨机器恢复会断链）。
- 备份位置 `data/backups/` 建议定期归档到备份存储，不随业务 NAS 混放。

### 5.4 .env 生命周期：生成 / 保留 / 刷新（v2.2.26 起显式机制）

**发布包不含 .env**（`.gitignore` 排除 + package.sh 打包时删除），三个模板随包携带：`env/dev.env`（开发）/ `env/test.env`（测试）/ `env/prod.env.template`（生产，ADR-016）。

| 场景 | 机制 | 说明 |
|------|------|------|
| **首次部署** | `deploy.sh` 检测 `.env` 不存在 → 从 `env/prod.env.template` 复制生成 + **随机 SECRET_KEY** | 之后编辑 `.env` 改 NAS_ROOT/INTERNAL_CIDRS 等 |
| **升级部署（默认）** | `deploy.sh` 检测 `.env` 已存在 → **原样保留**（先备份 `.env.deploybak`，tar 解包排除 `.env`/`.env.*`，解包后恢复） | 老配置（IP/网段/密钥/AD）绝不被覆盖 |
| **刷新格式（按需）** | `sudo bash infra/env-refresh.sh` | 备份 → 按模板**只增不覆盖**追加缺失键 → 报告新增/保留/旧键 |

**env-refresh.sh 行为（安全三原则）**：
1. 先备份 `.env` → `.env.bak-<时间戳>`（可回退）
2. **备份删除（v2.2.31）**：系统工具页备份列表行"删除"按钮（确认后删除，不可恢复）；后端 `DELETE /api/admin/ops/backups/<name>` 校验 backup- 前缀 + 防路径穿越；删除写审计日志 ops_delete_backup。
2. 模板有、现有缺失的键 → 追加模板默认值；**已有键原值绝不覆盖**；`SECRET_KEY` 缺失时随机生成（不从模板占位符复制）；`AD_BIND_PASSWORD` 缺失时留空并提示
3. 模板已删除的旧键（如 `MAX_CONTENT_LENGTH`）→ **提示不自动删**，确认后手工清理
4. 完成后 `sudo systemctl restart securetrans` 生效（systemd EnvironmentFile）

**典型用法（v2.2.24 起 MAX_CONTENT_LENGTH → MAX_FILE_SIZE_MB 迁移）**：
```bash
sudo bash infra/env-refresh.sh   # 追加 MAX_FILE_SIZE_MB=800 等新键，保留原有值
# 按报告提示删除旧键 MAX_CONTENT_LENGTH=（可选，程序对旧键有兼容兜底：上限自动=该值-1MB）
sudo systemctl restart securetrans
```

**为什么不自动刷新**：升级静默改动生产配置有风险（如新增键默认值可能不适合实际环境）；刷新是**显式运维动作**，只增不覆盖，避免"升级后配置被悄悄改掉"。

---

## 5.5、12-Factor 三环境一体化（ADR-016）

### 环境矩阵

| 环境 | 配置 | 数据 | AD |
|---|---|---|---|
| 开发（Windows） | `env/dev.env` → `src/.env`（启动自动加载） | `./data` | `AD_MOCK_MODE=true`（模拟目录） |
| 测试（WSL） | `env/test.env` → `/opt/securetrans/.env` | `/opt/securetrans/data` | `AD_MOCK_MODE=true`（模拟目录） |
| 生产（Rocky） | `env/prod.env.template` → `.env`（deploy.sh 生成，真实值人工填） | `/mnt/nas/securetrans` | `AD_MOCK_MODE=false`（真实 AD/SSSD） |

### 关键机制

1. **`.env` 启动自动加载**：`app.py` 启动时加载同目录 `.env`（不覆盖已注入的环境变量，
   生产 systemd EnvironmentFile 优先，行为不变）；开发/测试直接 `python app.py` 即生效。
2. **AD 模拟**：`AD_MOCK_MODE=true` 时 AD 搜索/登录走内置模拟目录（`MOCK_AD_USERS`，与生产典型
   数据脱敏一致，不触网）；生产必须 `false`。
3. **测试边界**：全面 TDD 回归只在开发/测试环境执行（写数据）；生产只做只读冒烟 + 人工验收
   （需求↔测试追踪矩阵见 `docs/07-requirements-traceability.md`）。
4. **CI**：`.gitea/workflows/ci.yml` + 本地 runner（注册见 `infra/ci-runner.md`），
   push 到 main 自动跑全量回归；生产发布保留人工门禁。
5. **配置纪律**：生产 `.env`/密钥/数据永不入 git；三模板随发布包携带。

---

## 六、文件清单

```
项目根目录/
├── src/                      # 源代码
│   ├── app.py                # Flask主程序
│   ├── requirements.txt      # Python依赖（含 waitress，Windows WSGI）
│   └── static/               # 前端SPA（index.html，单页应用）
├── env/                      # 12-Factor 分层配置（ADR-016）
│   ├── dev.env               # 开发环境（Windows 本地 + AD mock）
│   ├── test.env              # 测试环境（WSL + AD mock）
│   └── prod.env.template     # 生产环境模板（真实 AD，NAS）
├── tests/
│   ├── test_api.py           # 318项全量测试（WSL 生产面 318项）
│   └── mock/                 # 模拟数据与 AD 模拟目录（ADR-016：mock_ad.py 校验 / mock_expected.json 基线）
├── .gitea/workflows/ci.yml  # Gitea Actions CI（本地 runner，全量 TDD 回归）
├── infra/                    # 部署脚本和配置
│   ├── deploy.sh             # 一键部署 (Linux，RESET_DB=1 部署时出厂重置)
│   ├── deploy.ps1            # 一键部署 (Windows)
│   ├── verify.sh             # 部署验证（318项全量测试，凭据自动取 .env RESET_PASSWORD）
│   ├── ops-backup.sh / ops-restore.sh / ops-reset.sh / ops-mock.sh  # 数据生命周期离线脚本（ADR-011）
│   ├── env-refresh.sh        # .env 配置刷新（备份+只增不覆盖，ADR-010/5.4）
│   ├── nginx-securetrans.conf       # Nginx 双网卡模式
│   ├── nginx-securetrans-single.conf # Nginx 单网卡模式
│   ├── securetrans.service   # systemd 服务
│   ├── ci-runner.md         # Gitea Actions runner 注册指南（ADR-016）
│   └── package.sh / release.ps1     # 打包与 Gitea 发布
├── docs/                     # 文档
│   ├── DEPLOY.md             # 本部署指南（唯一部署文档）
│   ├── 09-preprod-verification.md   # 生产预验收清单
│   └── ...（PRD/PSF/PMF/测试/复盘等）
└── README.md
```

---

---

*部署指南 v2.3.6 | 2026-09-11*
