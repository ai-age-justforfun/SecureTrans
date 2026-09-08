# SecureTrans 部署指南

> 版本：v2.2.11 | 日期：2026-09-07
> 唯一部署文档：测试环境（本地/WSL）↔ 生产环境（服务器），一个 `DEPLOY_MODE` 开关切换，代码完全复用
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

**切换方式**：修改 `.env` 中的 `DEPLOY_MODE` 和 `NAS_ROOT`，换启动命令。代码不变。

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

访问 http://localhost:8000，账号 `admin / Admin@123`（首次登录强制改密）。

运行测试（另一个终端）：
```bash
cd tests
python test_api.py    # 172项全通过
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
cd ~/securetrans/tests && python3 test_api.py   # 172项全通过
```

### 2.4 测试验证清单

- [ ] 访问 http://服务器IP:8000 显示登录页
- [ ] admin / Admin@123 登录成功，首次登录强制改密
- [ ] 上传 PDF（匹配特征码，免审批自动通过）
- [ ] 上传 EXE（不匹配，进入人工审批）
- [ ] 上传 ZIP/TAR.GZ（自动解包列清单）
- [ ] 上传 .bit（Vivado Bitstream 识别）
- [ ] 一级审批通过（合作方直接摆渡）
- [ ] 二级审批通过（非合作方摆渡到 external）
- [ ] 外网下载文件成功
- [ ] os.rename 0拷贝验证：staging → external 毫秒级完成
- [ ] 用户管理、特征码规则、审计日志正常

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
- 全量测试前必须**重置干净基线**（admin/Admin@123）：删除 `data/securetrans.db` + 清空 NAS 下 `staging/external/archive`
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
# 3. 全量验证（172项）
sudo bash /opt/securetrans/infra/verify.sh
```

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

把 `securetrans-<当前版本>.tar.gz`（如 v2.2.11）从本地传到服务器（scp / U盘 / 堡垒机）：

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

> 目的：先用最简模式（本地文件系统 + Flask 自带服务器）确认程序在服务器上能跑、172 项全过。

```bash
cd /opt/securetrans/src
cp .env.testing .env
grep -E '^(DEPLOY_MODE|NAS_ROOT)=' .env   # 应为 DEPLOY_MODE=testing, NAS_ROOT=./nas

nohup ./venv/bin/python app.py > /tmp/st-testing.log 2>&1 &
sleep 4
curl -s http://127.0.0.1:8000/api/health
# 预期: {"deployMode":"testing","status":"ok",...}

cd /opt/securetrans/tests
python3 test_api.py
# 预期: 总计172 | 通过172 | 通过率100.0%
```

**通过标准**
- [ ] 健康检查返回 `deployMode":"testing"`
- [ ] 172 项测试 100% 通过
- [ ] 浏览器访问 `http://<内网IP>:8000`，admin/Admin@123 登录（首次强制改密）

### 阶段3：生产环境部署 + 自动化测试（DEPLOY_MODE=production）

> 目的：切到生产模式（gunicorn + systemd），本地磁盘先当存储，验证生产形态全链路。
> 也可直接用 `bash infra/deploy.sh` 一键部署（9 步自动化，等价于阶段0-3，root 执行）。

```bash
pkill -f 'app.py' || true
sleep 1
cd /opt/securetrans/src
cp .env.production .env

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
# 预期: 总计172 | 通过172 | 通过率100.0%
```

**通过标准**
- [ ] systemd 服务 active，`deployMode":"production"`
- [ ] 172 项测试 100% 通过（生产模式）
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
- [ ] 生产模式在 NAS 上再跑 172 项自动化测试 100%
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
# 首次启动自动重建 admin/Admin@123、默认系统配置、特征码模板(默认禁用)
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
| 1 | admin 登录 + 强制改密 | ☐ |
| 2 | 普通用户内网面菜单（文件提交/我的提交/外网下载） | ☐ |
| 3 | 外网面仅下载、管理菜单不可见 | ☐ |
| 4 | 提交文件→特征码匹配免审批直通 / 不匹配进审批 | ☐ |
| 5 | 一级审批→合作方直通；二级审批→非合作方摆渡 | ☐ |
| 6 | 一级审批人=二级审批人时自动跳过二级（语义B） | ☐ |
| 7 | 外网下载文件成功，内容完整 | ☐ |
| 8 | 过期文件自动归档（audit 日志确认） | ☐ |
| 9 | 审计日志 + 统计 Tab（人员/文件类型/每日） | ☐ |
| 10 | os.rename 0拷贝：摆渡毫秒级 | ☐ |
| 11 | 大文件（>100MB）上传/下载正常 | ☐ |

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
仍返回 403，隔离能力不丢失（172 项测试含网络面用例）。

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
cd /opt/securetrans/tests && python3 test_api.py   # 172 项全通过
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
| 1 | `python --version` ≥ 3.10（deploy.ps1 自动检测） | ☐ |
| 2 | 一键部署成功，`C:\SecureTrans\.env` 生成 | ☐ |
| 3 | 访问 http://localhost:8000，admin/Admin@123 登录 | ☐ |
| 4 | 运行全量测试：`cd tests; python test_api.py`（172项） | ☐ |
| 5 | waitress 生产启动健康检查通过 | ☐ |
| 6 | 单网卡隔离：内网段全功能，非内网段仅登录+下载（管理接口403） | ☐ |
| 7 | NSSM/计划任务服务化（可选） | ☐ |

---

## 五、日常运维

```bash
sudo systemctl status securetrans       # 查看状态
sudo systemctl restart securetrans      # 重启
sudo journalctl -u securetrans -f       # 实时日志
tail -f /opt/securetrans/data/securetrans.log  # 应用日志
sudo sqlite3 /opt/securetrans/data/securetrans.db ".backup /backup/securetrans_$(date +%Y%m%d).db"  # SQLite 热备份
```

---

## 六、文件清单

```
项目根目录/
├── src/                      # 源代码
│   ├── app.py                # Flask主程序
│   ├── requirements.txt      # Python依赖（含 waitress，Windows WSGI）
│   ├── .env.testing          # 测试环境配置模板
│   ├── .env.production       # 生产环境配置模板
│   └── static/               # 前端SPA（index.html，单页应用）
├── tests/
│   └── test_api.py           # 172项全量测试
├── infra/                    # 部署脚本和配置
│   ├── deploy.sh             # 一键部署 (Linux)
│   ├── deploy.ps1            # 一键部署 (Windows)
│   ├── verify.sh             # 部署验证（172项全量测试）
│   ├── nginx-securetrans.conf       # Nginx 双网卡模式
│   ├── nginx-securetrans-single.conf # Nginx 单网卡模式
│   ├── securetrans.service   # systemd 服务
│   └── package.sh / release.ps1     # 打包与 Gitea 发布
├── docs/                     # 文档
│   ├── DEPLOY.md             # 本部署指南（唯一部署文档）
│   ├── 09-preprod-verification.md   # 生产预验收清单
│   └── ...（PRD/PSF/PMF/测试/复盘等）
└── README.md
```

---

*部署指南 v2.2.11 | 2026-09-07*
