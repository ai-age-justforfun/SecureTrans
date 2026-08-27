# SecureTrans 服务器部署指南

> 版本：v1.4 | 日期：2026-08-26 | 阶段：PSF 原型验证
> 技术栈：Flask 3.0 + Flask-Login + SQLite + Gunicorn + Nginx + os.rename 0拷贝摆渡

---

## 一、核心问题：代码传到服务器可以直接运行吗？

**简短回答：不能直接运行，但经过本指南的准备步骤后可一键部署。**

### 1.1 为什么不能直接运行

| 问题 | 说明 | 本部署包是否已解决 |
|------|------|-------------------|
| Windows venv 不兼容 | 原目录的 `venv/` 是 Windows 版（Scripts/ 而非 bin/），拷到 Linux 无法使用 | ✅ 已排除，部署时自动重建 |
| 测试数据残留 | `data/securetrans.db` 和 `nas/external/` 含本地测试数据 | ✅ 已排除，首次启动自动创建干净数据库 |
| gunicorn 未安装 | `requirements.txt` 中 gunicorn 被注释，生产环境需要 | ✅ 已启用 |
| 前端页面缺失 | `static/` 目录为空，只有简陋的登录页 fallback | ✅ 已补充完整前端（index.html + login.html） |
| 生产配置缺失 | 没有 systemd service、nginx 配置、生产 .env | ✅ 已提供 |
| 服务用户/权限 | 需要专用系统用户和最小权限 | ✅ deploy.sh 自动创建 |

### 1.2 部署后能达到什么状态

- ✅ 后端 API 全部可用（35 项测试全通过）
- ✅ 前端 Web 界面完整可用（登录、提交、审批、下载、管理）
- ✅ os.rename 0拷贝摆渡生效（前提：staging/external/archive 同文件系统）
- ✅ systemd 托管，开机自启，崩溃自动重启
- ✅ Nginx 反向代理，支持大文件上传
- ⚠️ AD/LDAP 认证为 stub（PSF 阶段用本地用户，PMF 阶段接入）
- ⚠️ SQLite 单文件数据库（PSF 阶段够用，规模化后迁 PostgreSQL）

---

## 二、部署包内容说明

```
项目根目录/
├── src/                      # 后端程序
│   ├── app.py                # Flask 主程序（单文件，含所有 API）
│   ├── requirements.txt      # Python 依赖
│   ├── .env.example          # 环境变量示例
│   ├── .env.production       # 生产环境变量模板
│   ├── start.sh              # 测试环境启动脚本
│   ├── start-production.sh   # 生产环境启动脚本（gunicorn）
│   └── static/               # 前端静态文件
│       ├── index.html        # 主应用（完整 SPA，对接所有 API）
│       └── login.html        # 登录页
├── tests/
│   └── test_api.py           # 全量 API 测试脚本（35项）
└── infra/                    # 部署配置（本目录）
    ├── deploy.sh             # 一键部署脚本（核心）
    ├── verify.sh             # 部署后验证脚本（35项全量测试）
    ├── DEPLOY.md             # 本部署指南
    ├── securetrans.service   # systemd 服务文件
    └── nginx-securetrans.conf # Nginx 反向代理配置
```

---

## 三、服务器环境要求

### 3.1 硬件最低要求

| 项目 | 最低配置 | 推荐配置 |
|------|---------|---------|
| CPU | 2 核 | 4 核 |
| 内存 | 2 GB | 4 GB |
| 系统盘 | 20 GB | 50 GB |
| 数据盘/NAS | 根据文件量，建议 100GB+ | NAS 挂载 |

### 3.2 操作系统

- ✅ Ubuntu 20.04 / 22.04 / 24.04（推荐）
- ✅ Debian 11 / 12
- ✅ CentOS 7 / 8 / Stream 9
- ✅ RHEL 8 / 9
- ⚠️ 其他 systemd Linux 发行版可参考调整

### 3.3 必须预装的软件（封闭数据中心手工安装）

> 以下软件需要在服务器上**提前安装好**，deploy.sh 不会自动安装系统级软件。

#### A. Python 3.10+（必须）

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y python3 python3-venv python3-pip

# CentOS/RHEL 8+
sudo dnf install -y python3 python3-pip
# CentOS 7 需要额外源
sudo yum install -y centos-release-scl
sudo yum install -y rh-python38
scl enable rh-python38 bash
```

验证：
```bash
python3 --version   # 需要 >= 3.10
python3 -m venv --help  # 确认 venv 模块可用
```

#### B. Nginx（必须，反向代理）

```bash
# Ubuntu/Debian
sudo apt install -y nginx

# CentOS/RHEL
sudo dnf install -y nginx
```

#### C. NAS 挂载（必须，文件存储）

SecureTrans 的 staging/external/archive 三个目录**必须在同一个文件系统**，os.rename 才能实现 0拷贝。

**NFS 挂载示例：**
```bash
# 安装 NFS 客户端
# Ubuntu/Debian
sudo apt install -y nfs-common
# CentOS/RHEL
sudo dnf install -y nfs-utils

# 创建挂载点
sudo mkdir -p /mnt/nas/securetrans

# 挂载 NAS（替换为实际 NAS 地址和导出路径）
sudo mount -t nfs -o rw,hard,intr,rsize=8192,wsize=8192 nas-server:/export/securetrans /mnt/nas/securetrans

# 验证同文件系统
df -h /mnt/nas/securetrans/staging /mnt/nas/securetrans/external /mnt/nas/securetrans/archive
# 三个目录的 Filesystem 列必须相同
```

**开机自动挂载（/etc/fstab）：**
```
nas-server:/export/securetrans  /mnt/nas/securetrans  nfs  defaults,rw,hard,intr  0  0
```

> **如果没有 NAS**：可以直接使用服务器本地磁盘，将 `.env` 中 `NAS_ROOT` 指向本地路径（如 `/opt/securetrans/data/nas`），三个目录自然在同一文件系统。PSF 原型验证阶段完全够用。

#### D. 可选：SSL 证书（生产环境建议）

如果需要 HTTPS，准备好证书文件：
- 证书：`/etc/nginx/ssl/securetrans.crt`
- 私钥：`/etc/nginx/ssl/securetrans.key`

PSF 原型验证阶段可以先用 HTTP。

### 3.4 网络端口要求

| 端口 | 用途 | 说明 |
|------|------|------|
| 80 | Nginx HTTP | 内网用户访问 |
| 443 | Nginx HTTPS | 生产环境（可选） |
| 8000 | Gunicorn | 仅本地回环 127.0.0.1，不对外暴露 |

> 防火墙配置：仅开放 80/443 给内网网段，8000 不对外开放。

---

## 四、部署步骤（一站式）

### 4.1 上传部署包

将整个 `securetrans-deploy/` 目录上传到服务器，例如：

```bash
# 从本地 scp 上传（替换为实际服务器地址）
scp -r securetrans-deploy user@server:/tmp/

# 或通过 U 盘 / 堡垒机 / 其他方式上传到 /tmp/securetrans-deploy
```

### 4.2 执行一键部署

```bash
cd /tmp/securetrans-deploy
sudo bash deploy.sh
```

deploy.sh 会自动完成以下 9 个步骤：

1. **前置检查** — 验证 Python 3.10+、venv 模块可用
2. **创建服务用户** — 创建 `securetrans` 系统用户（无登录权限）
3. **备份旧版本** — 如果 `/opt/securetrans` 已存在，自动备份
4. **复制程序文件** — 复制到 `/opt/securetrans/`
5. **配置 .env** — 从模板生成，自动生成随机 SECRET_KEY
6. **创建虚拟环境** — 安装 Python 依赖（Flask、gunicorn 等）
7. **NAS 存储目录** — 创建 staging/external/archive，验证同文件系统
8. **设置权限** — 最小权限原则，.env 仅 640
9. **安装 systemd 服务** — 注册为系统服务，设为开机自启
10. **启动并验证** — 启动服务，执行健康检查

### 4.3 部署后必须做的手工配置

deploy.sh 完成后，需要根据实际环境修改以下配置：

#### A. 修改 .env 配置

```bash
sudo vi /opt/securetrans/.env
```

**必须修改的项：**

| 配置项 | 说明 | 示例值 |
|--------|------|--------|
| `NAS_ROOT` | 存储根目录，必须指向真实 NAS 挂载或本地数据盘 | `/mnt/nas/securetrans` |
| `SECRET_KEY` | 已自动生成随机值，确认即可 | （自动生成） |

**可选修改的项：**

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `MAX_CONTENT_LENGTH` | 1073741824 (1GB) | 单文件上传上限 |
| `EXTERNAL_EXPIRY_DAYS` | 30 | external 文件过期天数 |
| `HOST` | 127.0.0.1 | gunicorn 监听地址（nginx 代理时保持 127.0.0.1） |
| `PORT` | 8000 | gunicorn 监听端口 |

修改后重启服务：
```bash
sudo systemctl restart securetrans
```

#### B. 配置 Nginx 反向代理

```bash
# 复制配置模板
sudo cp /tmp/securetrans-deploy/infra/nginx-securetrans.conf /etc/nginx/conf.d/securetrans.conf

# 编辑配置，修改 server_name 为实际域名或 IP
sudo vi /etc/nginx/conf.d/securetrans.conf

# 测试配置
sudo nginx -t

# 重载 Nginx
sudo systemctl reload nginx
```

> **如果没有域名**：将 `server_name` 改为服务器 IP 或 `_`（默认 server）。

#### C. 配置防火墙

```bash
# Ubuntu/Debian (ufw)
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw reload

# CentOS/RHEL (firewalld)
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

### 4.4 验证部署

```bash
cd /tmp/securetrans-deploy
bash verify.sh
```

verify.sh 会执行：
1. 服务健康检查（`/api/health`）
2. 存储目录与同文件系统验证
3. 全量 35 项 API 测试（登录、上传、提交、审批、摆渡、下载、用户管理、配置、审计日志等）

**预期结果：35 项全部通过，通过率 100%。**

---

## 五、PSF 原型测试指南

### 5.1 初始账号

| 用户名 | 密码 | 角色 | 说明 |
|--------|------|------|------|
| `admin` | `Admin@123` | 系统管理员 | 首次登录强制修改密码 |

### 5.2 创建测试用户

登录 admin 后，进入「用户管理」→「新建用户」，创建以下测试角色：

| 用户名 | 角色 | 用途 |
|--------|------|------|
| `user01` | 普通用户 | 测试文件提交 |
| `manager01` | 部门主管 | 测试一级审批 |
| `exec01` | 公司高管 | 测试二级审批 |

### 5.3 核心测试流程

#### 流程 A：免审批自动摆渡（特征码匹配）

1. 用 `user01` 登录
2. 进入「文件提交」，上传一个 PDF 文件（匹配特征码）
3. 填写接收方信息，提交
4. 系统提示「免审批自动通过」
5. 进入「外网下载」，可看到文件已摆渡，可下载
6. 物理验证：`ls /mnt/nas/securetrans/external/` 可看到文件目录

#### 流程 B：人工审批摆渡（特征码不匹配）

1. 用 `user01` 登录，上传一个 EXE 文件（不匹配特征码）
2. 提交，状态变为「待一级审批」
3. 用 `manager01` 登录，进入「待我审批」，点击「通过」
4. 如果接收方类型是「非合作方」，状态变为「待二级审批」
5. 用 `exec01` 登录，进入「待我审批」，点击「通过」
6. 文件 os.rename 摆渡到 external，状态变为「已摆渡」
7. 进入「外网下载」可下载

#### 流程 C：驳回

1. 在审批页面点击「驳回」，填写驳回原因
2. 文件 os.rename 到 archive，状态变为「已驳回」

#### 流程 D：大文件上传

1. 上传一个 100MB+ 的文件
2. 观察上传过程（流式上传，内存占用稳定）
3. 上传完成后 MD5 自动计算
4. 摆渡操作毫秒级完成（os.rename 0拷贝）

### 5.4 验证 os.rename 0拷贝

```bash
# 在服务器上执行
# 1. 创建 100MB 测试文件
dd if=/dev/zero of=/mnt/nas/securetrans/staging/test.bin bs=1M count=100

# 2. 计时移动（模拟摆渡）
time mv /mnt/nas/securetrans/staging/test.bin /mnt/nas/securetrans/external/test.bin

# 3. 如果耗时 < 0.1 秒，说明是 0拷贝（同文件系统）
# 4. 清理测试文件
rm /mnt/nas/securetrans/external/test.bin
```

---

## 六、日常运维

### 6.1 服务管理

```bash
# 查看状态
sudo systemctl status securetrans

# 启动/停止/重启
sudo systemctl start securetrans
sudo systemctl stop securetrans
sudo systemctl restart securetrans

# 查看日志
sudo journalctl -u securetrans -f          # 实时跟踪
sudo journalctl -u securetrans -n 100      # 最近100行
sudo journalctl -u securetrans --since today  # 今天的日志

# 应用日志
tail -f /opt/securetrans/data/securetrans.log
tail -f /opt/securetrans/data/gunicorn-error.log
tail -f /opt/securetrans/data/gunicorn-access.log
```

### 6.2 数据备份

```bash
# 数据库备份（SQLite 热备份）
sudo sqlite3 /opt/securetrans/data/securetrans.db ".backup /backup/securetrans_$(date +%Y%m%d).db"

# 归档文件备份（NAS 层保障冗余，如需额外备份）
rsync -av /mnt/nas/securetrans/archive/ /backup/archive/

# 定时备份（crontab）
sudo crontab -e
# 每天凌晨 3 点备份数据库
0 3 * * * sqlite3 /opt/securetrans/data/securetrans.db ".backup /backup/securetrans_$(date +\%Y\%m\%d).db"
```

### 6.3 定时任务说明

系统内置 APScheduler 定时任务：
- **每天凌晨 2:00**：自动清理 external 中超过有效期的文件，os.rename 到 archive
- 可通过 admin → 系统配置 →「手动触发过期清理」立即执行

### 6.4 升级部署

```bash
# 1. 上传新版本到 /tmp/securetrans-deploy-new
# 2. 重新执行 deploy.sh（会自动备份旧版本）
cd /tmp/securetrans-deploy-new
sudo bash deploy.sh

# 3. 验证
bash verify.sh
```

> deploy.sh 会自动备份旧版本到 `/opt/securetrans_backup_YYYYMMDD_HHMMSS/`，如需回滚：
> ```bash
> sudo systemctl stop securetrans
> sudo mv /opt/securetrans /opt/securetrans_failed
> sudo mv /opt/securetrans_backup_YYYYMMDD_HHMMSS /opt/securetrans
> sudo systemctl start securetrans
> ```

---

## 七、故障排查

| 问题 | 排查步骤 |
|------|---------|
| 服务启动失败 | `sudo systemctl status securetrans` → `sudo journalctl -u securetrans -n 100` → 检查端口占用 `ss -tlnp \| grep 8000` |
| 页面无法访问 | 检查 nginx `sudo systemctl status nginx` → 检查防火墙 → 直接测试后端 `curl http://127.0.0.1:8000/api/health` |
| 上传大文件失败 | 检查 `.env` 中 `MAX_CONTENT_LENGTH` → 检查 nginx `client_max_body_size` → 检查磁盘空间 `df -h` |
| 摆渡失败（os.rename） | 确认 staging/external/archive 在同一文件系统 `df -h` → 检查目录权限 `ls -la /mnt/nas/securetrans` |
| 登录失败 | 检查用户名密码 → 查看日志 `tail -f data/securetrans.log` → AD 用户确认 `AD_ENABLED` 配置 |
| 页面空白 | 检查 `static/index.html` 是否存在 → 浏览器 F12 看控制台错误 → 检查 nginx 静态文件配置 |
| 定时任务不执行 | 确认 APScheduler 已安装（在 requirements.txt 中）→ 查看日志中是否有「定时任务已启动」 |
| 数据库锁定 | SQLite WAL 模式一般不会锁；如锁定检查是否多进程写入（gunicorn worker 数不要过多） |
| 权限错误 | 确认 `/opt/securetrans` 和 NAS 目录属主为 `securetrans:securetrans` → `sudo chown -R securetrans:securetrans /opt/securetrans /mnt/nas/securetrans` |

---

## 八、安全基线检查清单

部署完成后，逐项确认：

- [ ] admin 初始密码已修改（首次登录强制）
- [ ] `.env` 中 `SECRET_KEY` 已为随机字符串（deploy.sh 自动生成）
- [ ] `.env` 中 `FLASK_DEBUG=false`
- [ ] Nginx 已配置，gunicorn 仅监听 127.0.0.1
- [ ] 防火墙仅开放 80/443，8000 不对外
- [ ] NAS 目录权限最小化（`securetrans` 用户专属）
- [ ] 数据库文件权限 600
- [ ] `.env` 文件权限 640
- [ ] 生产环境使用 gunicorn + systemd，不使用 Flask 自带服务器
- [ ] （可选）HTTPS 已配置

---

## 九、从 PSF 到 PMF 的升级路径

| 阶段 | 前端 | 后端 | 存储 | 认证 |
|------|------|------|------|------|
| **PSF（当前）** | 纯 HTML+JS（本包） | Flask + SQLite | 本地磁盘/NAS | 本地用户 |
| **PMF** | 调用后端 API（本包已实现） | Flask + SQLite | NAS 挂载 | AD 集成 |
| **规模化** | Vue/React 工程化 | Flask + PostgreSQL | NAS + 备份 | AD + SSO |

### PMF 阶段需要做的事

1. **AD/LDAP 对接**：`pip install ldap3`，在 `app.py` 的 `authenticate_ad()` 函数中实现真实 LDAP 认证（代码中有 TODO 注释和示例）
2. **Nginx HTTPS**：配置 SSL 证书
3. **数据库迁移**：如用户量超过 200 人，考虑从 SQLite 迁移到 PostgreSQL
4. **双网卡物理隔离**：内网（提交/审批）和外网（下载）使用不同网卡，nginx 分别监听

---

## 十、联系方式与技术支持

- 后端主程序：`/opt/securetrans/app.py`（单文件，约 1200 行，含详细注释）
- API 文档：见 `README.md` 中的 API 接口一览
- 测试脚本：`/opt/securetrans/test_api.py`（35 项全量测试）

---

*部署指南结束 | SecureTrans v1.4 | 2026-08-26*
