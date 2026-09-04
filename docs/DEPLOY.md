# SecureTrans 部署指南

> 版本：v2.1.0 | 日期：2026-09-04
> 双模式部署：测试环境（本地/WSL）↔ 生产环境（服务器），一个 `DEPLOY_MODE` 开关切换，代码完全复用

---

## 一、双模式部署总览

| 维度 | 测试环境 | 生产环境 |
|------|---------|---------|
| `DEPLOY_MODE` | `testing`（默认） | `production` |
| 文件存储 | 本地磁盘 `./nas` | NAS 挂载 `/mnt/nas/securetrans` |
| WSGI 服务器 | Flask 自带 `python app.py` | gunicorn `gunicorn app:app` |
| 反向代理 | 无，直接访问 8000 端口 | nginx 反向代理 + HTTPS |
| 进程管理 | 前台 / nohup | systemd 服务 |
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
python test_api.py    # 171项全通过
```

### 2.3 方式 B：WSL Rocky Linux（模拟生产环境）

详见下方「三、WSL Rocky Linux 测试环境构建」。

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

## 三、WSL Rocky Linux 测试环境构建

### 3.1 前置要求

- Windows 10/11，已启用 WSL2
- Rocky Linux WSL 镜像：`D:\iso\Rocky-10-WSL-Base-10.1-20251116.0.x86_64.wsl`
- 项目代码在 Windows 本地（WSL 可通过 `/mnt/c/` 或 `/mnt/d/` 访问）

### 3.2 导入 Rocky Linux WSL 镜像

```powershell
# 在 PowerShell 中执行
# 创建 WSL 安装目录
mkdir D:\wsl\rocky10-securetrans

# 导入镜像（名称: rocky10-st，安装目录: D:\wsl\rocky10-securetrans，镜像: D:\iso\Rocky-10...wsl）
wsl --import rocky10-st D:\wsl\rocky10-securetrans D:\iso\Rocky-10-WSL-Base-10.1-20251116.0.x86_64.wsl

# 验证导入
wsl -l -v
# 应看到 rocky10-st 状态 Stopped

# 启动并进入
wsl -d rocky10-st
```

### 3.3 初始化 Rocky Linux 环境

```bash
# 进入 WSL 后执行

# 1. 检查系统版本
cat /etc/rocky-release
# 预期: Rocky Linux release 10.1

# 2. 安装 Python 3.10+ 和基础工具（Rocky 10 默认 Python 3.12）
dnf install -y python3 python3-pip python3-devel gcc

# 验证
python3 --version    # 需要 >= 3.10
python3 -m venv --help

# 3. 创建非 root 用户（可选，模拟生产环境）
useradd -m -s /bin/bash devuser
passwd devuser
# 后续可以 su - devuser 切换

# 4. 设置 WSL 默认用户（在 /etc/wsl.conf 中）
cat > /etc/wsl.conf << 'EOF'
[user]
default=devuser

[boot]
systemd=true
EOF
```

退出 WSL 并重启使配置生效：
```powershell
wsl --terminate rocky10-st
wsl -d rocky10-st
```

### 3.4 在 WSL 中部署项目

```bash
# 方式1：从 Windows 磁盘复制项目（推荐，代码在 Windows 编辑，WSL 运行）
cp -r /mnt/c/Users/jinta/.doubao/lark-chats/2026-08-25/new-chat ~/securetrans
cd ~/securetrans

# 方式2：从 Gitea 克隆（如果 WSL 能访问 Gitea）
# git clone http://<gitea-ip>:3000/openwrtadmin/SecureTrans.git ~/securetrans
# cd ~/securetrans

# 部署到 src/
cd src
cp .env.testing .env

# 创建虚拟环境并安装依赖
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 启动服务
python app.py
# 预期看到: 部署模式: testing, 存储目录: ./nas
```

在 Windows 浏览器访问 http://localhost:8000（WSL2 自动端口转发）。

### 3.5 在 WSL 中运行全量测试

```bash
# 另一个 WSL 终端
cd ~/securetrans/tests
python3 test_api.py
# 预期: 171项全部通过，通过率100%
```

### 3.6 WSL 中验证生产模式（可选）

```bash
cd ~/securetrans/src
cp .env.production .env
# 修改 NAS_ROOT 为本地路径（WSL 中没有 NAS，用本地磁盘模拟）
# sed -i 's|NAS_ROOT=/mnt/nas/securetrans|NAS_ROOT=/home/devuser/securetrans/nas|' .env
sed -i 's|^NAS_ROOT=.*|NAS_ROOT=/home/devuser/securetrans/nas|' .env

# 安装 gunicorn
pip install gunicorn

# 用 gunicorn 启动（模拟生产）
gunicorn -w 2 -b 0.0.0.0:8000 -t 300 app:app

# 验证健康检查（应返回 deployMode=production）
curl http://localhost:8000/api/health
```

### 3.7 WSL 常用命令

```powershell
# 查看已安装的发行版
wsl -l -v

# 启动指定发行版
wsl -d rocky10-st

# 停止指定发行版
wsl --terminate rocky10-st

# 删除发行版（谨慎！会丢失所有数据）
wsl --unregister rocky10-st

# 从 Windows 访问 WSL 文件
# 资源管理器输入: \\wsl$\rocky10-st
```

---

## 四、生产环境部署（封闭数据中心）

### 4.1 服务器环境要求

| 项目 | 最低配置 | 推荐配置 |
|------|---------|---------|
| CPU | 2 核 | 4 核 |
| 内存 | 2 GB | 4 GB |
| 系统盘 | 20 GB | 50 GB |
| 数据盘/NAS | 100GB+ | NAS 挂载 |

**操作系统**：Rocky 8/9/10、RHEL 8/9、Ubuntu 20.04+、Debian 11+

**必须预装的软件**（封闭数据中心手工安装）：
- Python 3.10+（含 venv 和 pip）
- Nginx（反向代理）
- NAS 挂载（staging/external/archive 同文件系统）

```bash
# Rocky/RHEL 安装 Python 和 Nginx
sudo dnf install -y python3 python3-pip nginx

# Ubuntu/Debian
sudo apt install -y python3 python3-venv python3-pip nginx
```

### 4.2 NAS 挂载（关键）

staging/external/archive 三个目录**必须在同一个文件系统**，os.rename 才能 0拷贝。

```bash
# NFS 挂载示例
sudo mkdir -p /mnt/nas/securetrans
sudo mount -t nfs nas-server:/export/securetrans /mnt/nas/securetrans

# 验证同文件系统
df -h /mnt/nas/securetrans/staging /mnt/nas/securetrans/external /mnt/nas/securetrans/archive
# 三个目录的 Filesystem 列必须相同
```

> 没有 NAS 时可用本地磁盘替代，`NAS_ROOT` 指向本地路径即可。

### 4.3 一键部署

```bash
# 1. 上传项目到服务器 /tmp/securetrans（scp / U盘 / 堡垒机）

# 2. 执行一键部署
cd /tmp/securetrans
sudo bash infra/deploy.sh
```

`deploy.sh` 自动完成 9 步：前置检查 → 创建服务用户 → 备份旧版本 → 复制程序 → 配置 .env → 创建虚拟环境 → NAS 目录准备 → 设置权限 → 安装 systemd 服务 → 启动验证。

### 4.4 部署后手工配置

```bash
# 修改 .env（NAS_ROOT、SECRET_KEY 等）
sudo vi /opt/securetrans/.env
sudo systemctl restart securetrans

# 配置 Nginx 反向代理（单/双网卡二选一）
# 双网卡：内网卡+外网卡两个 server，绑定各自网卡 IP
#   sudo cp /tmp/securetrans/infra/nginx-securetrans.conf /etc/nginx/conf.d/securetrans.conf
# 单网卡：一个 server，geo 按来源网段自动分内外网（推荐简化方案）
sudo cp /tmp/securetrans/infra/nginx-securetrans-single.conf /etc/nginx/conf.d/securetrans.conf
sudo vi /etc/nginx/conf.d/securetrans.conf   # 修改 server_name 与 geo 网段
sudo nginx -t && sudo systemctl reload nginx
```

### 4.5 部署验证

```bash
cd /tmp/securetrans
bash infra/verify.sh
# 预期: 健康检查通过 + 171项API测试全通过
```

### 4.6 初始账号

| 用户名 | 密码 | 角色 |
|--------|------|------|
| `admin` | `Admin@123` | 系统管理员（首次登录强制改密） |

### 4.7 Windows 服务器部署（可选）

客户端/服务器是 Windows 时同样支持，无需 Nginx（应用层网段识别直接生效）：

**前置**：安装 Python 3.10+（https://www.python.org/downloads/ ，安装时勾选 *Add python.exe to PATH*）。封闭离线环境提前下载 Windows 安装包（离线 wheel 已随发布包内置 `offline-deps-win/`）。

```powershell
# 1. 上传/解压发布包到服务器，进入项目根目录
# 2. 一键部署（离线优先，自动建 venv + 装依赖 + 生成 .env）
powershell -ExecutionPolicy Bypass -File infra/deploy.ps1 -InstallDir C:\SecureTrans

# 3. 编辑 .env：NAS_ROOT、INTERNAL_CIDRS、SECRET_KEY
notepad C:\SecureTrans\.env

# 4. 生产启动（waitress，Windows 生产推荐，替代 Linux 的 gunicorn）
cd C:\SecureTrans
.\venv\Scripts\waitress-serve.exe --host=0.0.0.0 --port=8000 app:app
```

Windows 服务化（开机自启）可用 NSSM：`nssm install SecureTrans` 指向 venv python + app.py；或用计划任务。单网卡直连时，`INTERNAL_CIDRS` 决定内外网：内网段全功能，非内网段仅登录+下载。

---

## 五、日常运维

### 5.1 服务管理

```bash
sudo systemctl status securetrans       # 查看状态
sudo systemctl restart securetrans      # 重启
sudo journalctl -u securetrans -f       # 实时日志
tail -f /opt/securetrans/data/securetrans.log  # 应用日志
```

### 5.2 数据备份

```bash
# SQLite 热备份
sudo sqlite3 /opt/securetrans/data/securetrans.db ".backup /backup/securetrans_$(date +%Y%m%d).db"
```

### 5.3 故障排查

| 问题 | 排查 |
|------|------|
| 服务启动失败 | `journalctl -u securetrans -n 100` → 检查端口占用 `ss -tlnp \| grep 8000` |
| 页面无法访问 | 检查 nginx → 防火墙 → 直接测试后端 `curl http://127.0.0.1:8000/api/health` |
| 摆渡失败 | 确认 staging/external/archive 同文件系统 `df -h` → 检查目录权限 |
| 大文件上传失败 | 检查 `MAX_CONTENT_LENGTH` → nginx `client_max_body_size` → 磁盘空间 |

---

## 六、从测试环境切到生产环境

测试验证通过后，3 步切换，代码不变：

```bash
# 1. 换配置
cp .env.production .env
# 修改 NAS_ROOT 为实际 NAS 挂载路径
# 修改 SECRET_KEY 为随机字符串

# 2. 挂载 NAS（staging/external/archive 同文件系统）
sudo mount -t nfs nas-server:/export/securetrans /mnt/nas/securetrans

# 3. 换启动方式
# 测试: python app.py（Flask自带）
# 生产: gunicorn app:app（或 systemd 服务）
sudo systemctl start securetrans
```

---

## 七、文件清单

```
项目根目录/
├── src/                      # 源代码
│   ├── app.py                # Flask主程序
│   ├── requirements.txt      # Python依赖
│   ├── start.sh              # 测试环境启动（Flask）
│   ├── start-production.sh   # 生产环境启动（gunicorn）
│   ├── .env.testing          # 测试环境配置
│   ├── .env.production       # 生产环境配置
│   └── static/               # 前端SPA
├── tests/
│   └── test_api.py           # 171项全量测试
├── infra/                    # 部署脚本和配置
│   ├── deploy.sh             # 一键部署 (Linux)
│   ├── deploy.ps1            # 一键部署 (Windows)
│   ├── verify.sh             # 部署验证
│   ├── nginx-securetrans.conf       # Nginx 双网卡模式
│   ├── nginx-securetrans-single.conf # Nginx 单网卡模式
│   ├── securetrans.service
│   └── package.sh / release.ps1     # 打包与 Gitea 发布
└── docs/
    └── DEPLOY.md             # 本部署指南
```

---

*部署指南 v1.5.0 | 2026-08-27*
