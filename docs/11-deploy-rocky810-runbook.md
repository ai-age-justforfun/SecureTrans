# SecureTrans Rocky Linux 8.10 部署执行手册（Runbook）

> 版本：v1.0 | 日期：2026-08-31 | 发布版本：**v1.5.0**（Gitea Release 记录）
> 适用：新建 Rocky Linux 8.10 虚拟机服务器（封闭数据中心，可配置 mirrors 在线源，但**默认走离线包**）
> 执行方式：**用户手工逐条执行**，每阶段有明确"通过标准"，测试不过不进下一阶段。

---

## 〇、总览

```
阶段0  服务器基础准备（Python 3.12 + 基础工具）
阶段1  上传部署包 + 离线安装依赖
阶段2  测试环境部署（testing：本地文件系统+Flask）→ 自动化测试150项
阶段3  生产环境部署（production：本地磁盘+gunicorn+systemd）→ 自动化测试150项
阶段4  NAS 切换（本地磁盘 OK 后，创建 dataset + 挂载 + 迁移）
阶段5  网络隔离（双网卡 / 单网卡 geo 二选一）
阶段6  手工验收 + 内部试用发布（清测试数据 → 正式配置）
```

**本次发布产物**（见 Gitea Release v1.5.0）：
| 文件 | 说明 |
|------|------|
| `securetrans-1.5.0.tar.gz` | 完整部署包（src+tests+infra+docs+offline-deps+离线wheel） |
| `securetrans-offline-deps.tar.gz` | 独立离线依赖包（17 个 wheel，Linux x86_64 / Python 3.12） |
| 校验和 | MD5 + SHA256（见 release 说明） |

---

## 阶段0：服务器基础准备

### 0.1 系统与网络确认

```bash
cat /etc/rocky-release                 # 确认 Rocky Linux release 8.10
hostnamectl                           # 确认主机名、系统
ip a                                  # 确认 IP（阶段5 会加第二块网卡）
dnf repolist                          # 确认 mirrors 源 repo 可用
```

### 0.2 安装 Python 3.12（关键：Rocky 8 默认 python3=3.6，不满足 3.10+）

```bash
# 查看可用 Python 模块
dnf module list python3* --quiet

# 启用 Python 3.12 并安装（含 venv/pip/devel）
dnf module enable -y python3.12
dnf install -y python3.12 python3.12-pip python3.12-devel

# 设置 python3 指向 3.12（可选，让系统命令一致）
alternatives --set python3 /usr/bin/python3.12 2>/dev/null || true

# 验证（必须 >= 3.10）
python3 --version          # 预期 Python 3.12.x
python3 -m venv --help >/dev/null && echo "venv OK"
```

> 备选：若 module 里没有 3.12，可用 `dnf install -y python3.11` 同理（离线 wheel 已按 cp312 打包，若用 3.11 需在 release 里另取对应 wheel，建议统一 3.12）。

### 0.3 安装基础工具

```bash
dnf install -y tar gzip curl nginx git
systemctl enable --now nginx 2>/dev/null || true
```

### 0.4 防火墙（如启用）

```bash
systemctl status firewalld --no-pager | head -3
# 内网联调先放行 8000（阶段5 后改由 Nginx 80/443 代理）
firewall-cmd --permanent --add-port=8000/tcp && firewall-cmd --reload
```

---

## 阶段1：上传部署包 + 离线安装依赖

### 1.1 上传部署包

把以下文件从本地传到服务器（scp / U盘 / 堡垒机，任选）：
- `securetrans-1.5.0.tar.gz`
- `securetrans-offline-deps.tar.gz`（如需独立部署依赖时用）

```bash
# 示例（本地到服务器，视网络通道而定）
scp securetrans-1.5.0.tar.gz securetrans-offline-deps.tar.gz root@<服务器IP>:/root/
```

### 1.2 解压到安装目录

```bash
mkdir -p /opt/securetrans
cd /root
tar xzf securetrans-1.5.0.tar.gz -C /opt/securetrans --strip-components=1
ls /opt/securetrans        # 应看到 src/ tests/ infra/ docs/ offline-deps(wheelhouse)/ README
```

> 若打包时离线 wheel 已内置（`offline-deps/` 或 `wheelhouse/`），可跳过 1.3 的独立解压。

### 1.3 创建虚拟环境 + 离线安装依赖

```bash
cd /opt/securetrans/src
python3 -m venv venv

# 定位离线 wheel 目录（二选一）
WH=/opt/securetrans/offline-deps   # 若打包时内置
# WH=/opt/securetrans/wheelhouse   # 若用独立离线包解压
[ -d "$WH" ] || (mkdir -p /opt/securetrans/wheelhouse && tar xzf /root/securetrans-offline-deps.tar.gz -C /opt/securetrans --strip-components=1 && WH=/opt/securetrans/wheelhouse)

# 离线安装（--no-index 强制只用本地 wheel）
./venv/bin/pip install --no-index --find-links="$WH" -r requirements.txt
./venv/bin/pip install --no-index --find-links="$WH" gunicorn==21.2.0

# 验证（必须都成功）
./venv/bin/python -c "import flask, flask_login, bcrypt, apscheduler, ldap3, gunicorn; print('依赖 OK:', flask.__version__)"
```

> **在线备选**（若服务器临时可上网）：`./venv/bin/pip install -r requirements.txt && ./venv/bin/pip install gunicorn`。离线包始终保留，数据中心部署首选离线。

---

## 阶段2：测试环境部署 + 自动化测试（DEPLOY_MODE=testing）

> 目的：先用最简模式（本地文件系统 + Flask 自带服务器）确认程序在服务器上能跑、150 项全过。

### 2.1 配置 .env（testing）

```bash
cd /opt/securetrans/src
cp .env.testing .env
grep -E '^(DEPLOY_MODE|NAS_ROOT)=' .env   # 应为 DEPLOY_MODE=testing, NAS_ROOT=./nas
```

### 2.2 启动（Flask 自带服务器）

```bash
nohup ./venv/bin/python app.py > /tmp/st-testing.log 2>&1 &
sleep 4
curl -s http://127.0.0.1:8000/api/health
# 预期: {"deployMode":"testing","status":"ok",...}
```

### 2.3 全量自动化测试

```bash
cd /opt/securetrans/tests
python3 test_api.py
# 预期: 总计150 | 通过150 | 通过率100.0%
```

### 2.4 通过标准

- [ ] 健康检查返回 `deployMode":"testing"`
- [ ] 150 项测试 100% 通过
- [ ] 页面可访问：浏览器访问 `http://<内网IP>:8000`，admin/Admin@123 登录（首次强制改密）

---

## 阶段3：生产环境部署 + 自动化测试（DEPLOY_MODE=production）

> 目的：切到生产模式（gunicorn + systemd），本地磁盘先当存储，验证生产形态全链路。

### 3.1 停测试实例，配置 .env（production）

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

# 确认关键项
grep -E '^(DEPLOY_MODE|NAS_ROOT|HOST|PORT|FLASK_DEBUG|SECRET_KEY)=' .env
```

### 3.2 安装 systemd 服务（gunicorn 2 worker）

```bash
cd /opt/securetrans
cp infra/securetrans.service /etc/systemd/system/securetrans.service

# 关键：本阶段 NAS_ROOT 是本地目录，systemd 的 ReadWritePaths 需放开（阶段4 再指向 /mnt/nas）
sed -i 's|/mnt/nas/securetrans|/opt/securetrans/nas|' /etc/systemd/system/securetrans.service

systemctl daemon-reload
systemctl enable --now securetrans
systemctl status securetrans --no-pager -l | head -15
```

### 3.3 生产模式验证

```bash
curl -s http://127.0.0.1:8000/api/health
# 预期: {"deployMode":"production",...}
systemctl is-active securetrans       # 预期 active

# 生产模式全量自动化测试
cd /opt/securetrans/tests
NAS_ROOT=/opt/securetrans/nas python3 test_api.py
# 预期: 总计150 | 通过150 | 通过率100.0%
```

### 3.4 通过标准

- [ ] systemd 服务 active，`deployMode":"production"`
- [ ] 150 项测试 100% 通过（生产模式）
- [ ] 确认 gunicorn 多 worker 无并发初始化报错（本发布已修复该 Bug）
- [ ] 首次访问初始化正常：`/opt/securetrans/data/securetrans.db`、`/opt/securetrans/nas/{staging,external,archive}` 自动创建

---

## 阶段4：NAS 切换（本地磁盘 OK 后）

> 前置：阶段3 全部通过。先本地磁盘跑稳，再切 NAS。

### 4.1 存储端创建 dataset + 服务器挂载

```bash
# 在 NAS 存储管理端（如 TrueNAS）创建 dataset，例如: securetrans
# 记录导出路径，如 /mnt/tank/securetrans（存储端）

# 服务器上创建挂载点并挂载（NFS 示例）
mkdir -p /mnt/nas/securetrans
mount -t nfs <NAS_IP>:/mnt/tank/securetrans /mnt/nas/securetrans

# 写入 /etc/fstab 持久化
echo '<NAS_IP>:/mnt/tank/securetrans /mnt/nas/securetrans nfs defaults,_netdev 0 0' >> /etc/fstab

# 验证同文件系统（staging/external/archive 必须在同一 fs，os.rename 才 0拷贝）
df -h /mnt/nas/securetrans | tail -1
```

### 4.2 迁移数据 + 切换配置

```bash
# 迁移本地 nas 中已有数据（若需保留；全新环境可跳过）
cp -a /opt/securetrans/nas/. /mnt/nas/securetrans/ 2>/dev/null || true

# 切 NAS_ROOT
cd /opt/securetrans/src
sed -i 's|^NAS_ROOT=.*|NAS_ROOT=/mnt/nas/securetrans|' .env
grep '^NAS_ROOT=' .env

# systemd ReadWritePaths 指回 NAS
sed -i 's|/opt/securetrans/nas|/mnt/nas/securetrans|' /etc/systemd/system/securetrans.service
systemctl daemon-reload && systemctl restart securetrans
```

### 4.3 验证

```bash
curl -s http://127.0.0.1:8000/api/health   # production + ok
df -h /mnt/nas/securetrans/staging /mnt/nas/securetrans/external /mnt/nas/securetrans/archive | awk '{print $1,$NF}'
# 三行 Filesystem 必须相同
```

### 4.4 通过标准

- [ ] NAS 三个目录同一文件系统
- [ ] 生产模式在 NAS 上再跑 150 项自动化测试 100%
- [ ] os.rename 0拷贝：上传→审批→摆渡 毫秒级

---

## 阶段5：双网卡 + Nginx 双 server

> 应用层网络面隔离（读 X-Network-Zone 头）已被 test_api.py 在本地 100% 覆盖；本阶段验证**真实双网卡 + Nginx 头注入**。

### 5.1 虚拟机配置双网卡（你在 VM 层手工完成）

- 添加第二块虚拟网卡（外网面）
- 配置两块网卡 IP（内网/外网），确认路由
- `ip a` 确认两块网卡 up

### 5.2 Nginx 双 server（内网管理面 + 外网下载面）

```bash
cd /opt/securetrans
cp infra/nginx-securetrans.conf /etc/nginx/conf.d/securetrans.conf
vi /etc/nginx/conf.d/securetrans.conf
# 修改：
#   内网 server_name → securetrans.internal.<域名>
#   外网 server_name → securetrans.external.<域名>
#   确认两个 server 分别 proxy_set_header X-Network-Zone internal / external
nginx -t && systemctl reload nginx
```

### 5.2 单网卡模式（替代双网卡，按实际部署二选一）

只有一张网卡、防火墙放行内外网访问同一地址时，用单网卡模板，Nginx 按来源网段自动识别内外网，
功能隔离与应用层统一（外网面仅登录+下载，管理接口 403）：

```bash
cd /opt/securetrans
cp infra/nginx-securetrans-single.conf /etc/nginx/conf.d/securetrans.conf
vi /etc/nginx/conf.d/securetrans.conf
# 修改：
#   server_name -> 实际域名/IP
#   geo $network_zone 中的网段 -> 实际内网网段（与 INTERNAL_CIDRS 一致）
nginx -t && systemctl reload nginx
```

应用层 .env 同步：`NETWORK_MODE=single` + `INTERNAL_CIDRS=<内网网段>`。
无 Nginx 直连（Windows 本地 / 单网卡直连）时应用层按网段兜底，行为一致。

### 5.3 验收

按 `docs/09-preprod-verification.md` 执行：内网面完整功能、外网面仅下载、外网管理接口 403、Nginx 头注入确认、防火墙两网卡规则。

### 5.4 通过标准

- [ ] 内网地址访问管理面正常
- [ ] 外网地址仅能下载，管理接口 403
- [ ] `nginx -T` 确认两个 server 的头注入

---

## 阶段6：手工验收 + 内部试用发布

### 6.1 清理初始测试数据（重要）

自动化测试会在数据库写入测试数据。内部试用前清理，恢复干净初始状态：

```bash
# 方式A：重置数据库（推荐，全新开始）
systemctl stop securetrans
rm -f /opt/securetrans/data/securetrans.db /opt/securetrans/data/securetrans.log
rm -rf /opt/securetrans/nas/staging/* /opt/securetrans/nas/external/* /opt/securetrans/nas/archive/*
systemctl start securetrans
# 首次启动自动重建 admin/Admin@123、默认系统配置、特征码模板(默认禁用)

# 方式B：仅清理业务数据（保留配置，用 Web 界面删测试用户/合作方/特征码）
```

### 6.2 配置正式数据（Web 界面，admin 登录）

- [ ] 修改 admin 初始密码
- [ ] 创建正式用户（普通用户）
- [ ] 配置一级/二级审批人
- [ ] 配置合作方白名单（是否使能）
- [ ] 按需启用特征码规则（默认模板全禁用，按需打开）
- [ ] 确认系统配置：免审批总开关、默认有效期 7 天、最大文件 800MB

### 6.3 手工验收清单

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

### 6.4 内部试用发布

- [ ] 通知试用用户（内网地址）
- [ ] 设定试用期与反馈收集方式（收集方式见 `docs/03-psf-process.md`）
- [ ] 试用期结束按 PMF 流程评估（`docs/04-pmf-process.md`）

---

## 附：常见问题

| 问题 | 处理 |
|------|------|
| `python3` 版本是 3.6 | 未执行阶段0.2，先 `dnf module enable python3.12` |
| pip 找不到离线包 | 确认 wheelhouse 路径，`ls $WH` 有 17 个 .whl |
| systemd 启动失败 | `journalctl -u securetrans -n 50`；检查端口占用 `ss -tlnp \| grep 8000` |
| gunicorn UNIQUE 冲突 | 代码未更新（需含"INSERT OR IGNORE"修复），重新同步 app.py |
| NAS 写入失败 | 检查 systemd `ReadWritePaths` 是否包含 NAS 路径、NAS 权限、同文件系统 |
| 外网下载 403 | Nginx external server 是否注入 `X-Network-Zone: external` |

---

*执行手册 v1.0 | 2026-08-31 | 对应 Gitea Release v1.5.0*
