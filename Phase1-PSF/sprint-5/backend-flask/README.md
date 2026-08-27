# SecureTrans 后端部署说明（Flask 版）

> 轻量级跨网文件审批摆渡系统 - v1.4
> Flask + Flask-Login + SQLite + os.rename 0拷贝摆渡
> 适配初创公司 50 人规模，支撑到 200 人不改架构

---

## 目录结构

```
backend-flask/
├── app.py              # Flask 主程序（单文件，含所有 API）
├── requirements.txt    # Python 依赖
├── .env.example        # 环境变量配置示例
├── start.bat           # Windows 一键启动
├── start.sh            # Linux 一键启动
├── README.md           # 本文件
├── data/               # 运行时数据（自动创建）
│   ├── securetrans.db  # SQLite 数据库
│   └── securetrans.log # 日志
├── nas/                # 存储目录（生产替换为真实 NAS 挂载）
│   ├── staging/        # 刚上传，待审核
│   ├── external/       # 审核通过，可外网下载
│   └── archive/        # 过期/驳回，永久归档
└── static/             # 前端静态文件（放入 index.html）
```

---

## 核心架构：os.rename 0拷贝摆渡

```
刚上传   → /nas/staging/{id}/     status=pending
审核通过 → os.rename → /nas/external/{id}/   status=approved  (0拷贝，毫秒级)
外网下载 → 从 /nas/external/ 流式读取，物理文件不动
过期清理 → os.rename → /nas/archive/{id}/    status=archived  (0拷贝，定时任务半夜执行)
```

**为什么 os.rename 是 0 拷贝？**
在同一个文件系统内，`os.rename()` 只修改目录项（directory entry），不移动任何数据块。文件内容在磁盘上的物理位置完全不变。因此：
- 移动 1KB 和 500MB 耗时相同（毫秒级）
- 不占用额外磁盘空间
- 原子操作，不会半移动

**前提条件**：staging/external/archive 三个目录必须在**同一个文件系统**（同一个磁盘分区或同一个 NAS 挂载）。如果跨文件系统，os.rename 会退化为复制+删除。

---

## 快速开始

### Windows

```bash
# 1. 安装 Python 3.10+（已安装可跳过）
# 2. 双击 start.bat，或命令行执行：
start.bat
```

### Linux

```bash
# 1. 安装 Python 3.10+
# Ubuntu/Debian: sudo apt install python3 python3-venv python3-pip
# CentOS/RHEL: sudo yum install python3

# 2. 赋予执行权限并启动
chmod +x start.sh
./start.sh
```

### 手动启动（通用）

```bash
# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate    # Linux/Mac
# venv\Scripts\activate     # Windows

# 安装依赖
pip install -r requirements.txt

# 配置环境变量（可选，有默认值）
cp .env.example .env
# 编辑 .env 修改配置

# 启动
python app.py
```

启动后访问：**http://localhost:8000**

初始管理员：**admin / Admin@123**（首次登录强制修改密码）

---

## 生产环境部署

### 1. NAS / 存储配置

将真实 NAS 挂载到服务器，确保 staging/external/archive 在同一个文件系统：

```bash
# Linux NFS 挂载示例
sudo mkdir -p /mnt/nas
sudo mount -t nfs nas-server:/export/securetrans /mnt/nas

# 确保三个子目录存在
mkdir -p /mnt/nas/staging /mnt/nas/external /mnt/nas/archive
```

在 `.env` 中配置：
```bash
NAS_ROOT=/mnt/nas
```

**验证 os.rename 0拷贝**：
```bash
# 创建测试文件
dd if=/dev/zero of=/mnt/nas/staging/test.bin bs=1M count=100
# 计时移动
time mv /mnt/nas/staging/test.bin /mnt/nas/external/test.bin
# 如果耗时 < 0.1 秒，说明是 0拷贝（同文件系统）
```

### 2. 双网卡网络配置

- eth0：内网（提交、审批）
- eth1：外网（下载）

Nginx 反向代理配置（大文件上传需配置 client_max_body_size）：

```nginx
server {
    listen 80;
    server_name securetrans.internal.company.com;

    # 大文件上传支持（1GB）
    client_max_body_size 1G;
    proxy_request_buffering off;  # 流式上传，不缓冲到磁盘

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;  # 大文件上传超时
    }
}
```

### 3. HTTPS 配置

生产环境建议配置 SSL：
```nginx
server {
    listen 443 ssl;
    server_name securetrans.company.com;
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    client_max_body_size 1G;
    # ... 同上 proxy 配置
}
```

### 4. WSGI 服务器（生产环境不要用 Flask 自带服务器）

**Linux 推荐 gunicorn**：
```bash
pip install gunicorn
gunicorn -w 2 -b 0.0.0.0:8000 -t 300 app:app
```

**Windows 推荐 waitress**：
```bash
pip install waitress
waitress-serve --listen=0.0.0.0:8000 --threads=4 app:app
```

### 5. systemd 服务（Linux 生产环境）

创建 `/etc/systemd/system/securetrans.service`：
```ini
[Unit]
Description=SecureTrans File Ferry Service
After=network.target

[Service]
Type=simple
User=securetrans
WorkingDirectory=/opt/securetrans/backend-flask
EnvironmentFile=/opt/securetrans/backend-flask/.env
ExecStart=/opt/securetrans/backend-flask/venv/bin/gunicorn -w 2 -b 0.0.0.0:8000 -t 300 app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

启用：
```bash
sudo systemctl daemon-reload
sudo systemctl enable securetrans
sudo systemctl start securetrans
sudo systemctl status securetrans
```

### 6. Windows 服务（可选）

使用 NSSM（Non-Sucking Service Manager）将 Flask 注册为 Windows 服务：
```bash
nssm install SecureTrans "C:\path\to\venv\Scripts\python.exe" "C:\path\to\app.py"
nssm set SecureTrans AppDirectory "C:\path\to\backend-flask"
nssm start SecureTrans
```

---

## 大文件上传处理（500MB 极限）

### 配置
- `MAX_CONTENT_LENGTH=1073741824`（1GB 上限，可在 .env 调整）
- Nginx `client_max_body_size 1G`
- Nginx `proxy_request_buffering off`（流式上传）
- gunicorn `--timeout 300`（5 分钟超时）

### 原理
- Werkzeug 的 `request.files['file']` 自动流式写入临时文件，不加载到内存
- 代码中使用 `file.stream.read(65536)` 分块读取，边保存边计算 MD5
- 500MB 文件上传时，Python 内存占用稳定在几十 MB
- 上传完成后文件直接在 staging 目录，无需二次移动

### 上传流程
1. 前端选择文件 → POST `/api/submissions/upload`
2. Flask 流式接收 → 写入 `/nas/staging/{temp_id}/files/`
3. 边写边计算 MD5 → 返回文件信息
4. 用户确认提交 → POST `/api/submissions`
5. 临时文件 os.rename 到正式提交目录（0拷贝）
6. 审批通过 → os.rename 到 external（0拷贝摆渡）

---

## AD/LDAP 对接

PMF 阶段 AD 对接代码已预留接口（`authenticate_ad` 函数），生产环境需：

1. 安装 ldap3：`pip install ldap3`
2. 在 `.env` 中配置 AD 参数：
   ```bash
   AD_ENABLED=true
   AD_HOST=dc01.company.com
   AD_BASE_DN=DC=company,DC=com
   AD_BIND_DN=CN=svc_ldap,OU=Service,DC=company,DC=com
   AD_BIND_PASSWORD=your-password
   ```
3. 在 `app.py` 的 `authenticate_ad` 函数中实现真实 LDAP 认证（代码中有 TODO 注释和示例）

**登录流程**：
- 默认自动探测：先查本地用户表，匹配则本地认证；不匹配则走 AD
- 支持 `域\用户名` 格式强制走 AD
- 本地 admin 固定走本地认证

---

## API 接口一览

### 认证
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/auth/login | 登录（支持 JSON 和表单） |
| GET/POST | /api/auth/logout | 退出登录 |
| GET | /api/auth/me | 获取当前用户 |
| POST | /api/auth/change-password | 修改密码 |

### 提交与文件
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/submissions/upload | 上传文件（流式，支持大文件） |
| POST | /api/submissions | 创建提交单 |
| GET | /api/submissions | 提交单列表 |
| GET | /api/submissions/{id} | 提交单详情 |
| GET | /api/submissions/pending/my | 待我审批 |

### 审批
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/submissions/{id}/approve | 审批（通过/驳回，os.rename 摆渡） |

### 外网下载
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/external/files | 已摆渡文件列表 |
| GET | /api/external/{id}/download/{filename} | 下载文件（流式） |

### 用户管理（admin）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | /api/admin/local-users | 本地用户管理 |
| DELETE | /api/admin/local-users/{username} | 删除本地用户 |
| POST | /api/admin/local-users/{username}/reset-password | 重置密码 |
| GET/POST | /api/admin/role-mappings | AD 角色映射 |
| DELETE | /api/admin/role-mappings/{id} | 删除角色映射 |
| POST | /api/admin/ad/search | 搜索 AD 用户 |
| POST | /api/admin/cleanup-expired | 手动触发过期清理 |

### 系统配置
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/config/feature-rules | 特征码规则 |
| GET/PUT | /api/config/system | 系统配置 |

### 审计与统计
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/audit-logs | 审计日志 |
| GET | /api/stats | 统计数据 |
| GET | /api/health | 健康检查 |

---

## 定时任务：过期文件清理

- 默认每天凌晨 2 点自动执行（APScheduler）
- 检查 external 中超过有效期的文件
- os.rename 到 archive（0拷贝归档）
- 更新状态为 archived
- 可通过 API `/api/admin/cleanup-expired` 手动触发
- 可在 `.env` 中配置 `EXTERNAL_EXPIRY_DAYS`（默认 30 天）

---

## 数据备份

### 数据库备份
```bash
# SQLite 热备份
sqlite3 data/securetrans.db ".backup backup/securetrans_$(date +%Y%m%d).db"
```

### 归档文件备份
归档文件在 NAS 的 archive 目录，由 NAS 层保障冗余。如需额外备份：
```bash
rsync -av /mnt/nas/archive/ /backup/archive/
```

### 定时备份（crontab）
```bash
# 每天凌晨 3 点备份数据库
0 3 * * * /opt/securetrans/backup.sh
```

---

## 故障排查

| 问题 | 排查 |
|------|------|
| 启动失败 | 查看 `data/securetrans.log`，检查端口是否被占用、依赖是否安装 |
| 上传大文件失败 | 检查 `MAX_CONTENT_LENGTH` 配置、Nginx `client_max_body_size`、磁盘空间 |
| 摆渡失败（os.rename） | 确认 staging/external/archive 在同一个文件系统；检查目录权限 |
| AD 登录失败 | 检查 AD 连接配置，用 `ldapsearch` 测试连通性；确认服务账号权限 |
| 页面空白 | 检查 `static/` 目录是否有前端文件；浏览器 F12 看控制台 |
| 定时任务不执行 | 确认 APScheduler 已安装；查看日志中是否有 "定时任务已启动" |
| 数据库锁定 | SQLite WAL 模式一般不会锁；如锁定检查是否多进程写入 |

---

## 安全基线检查清单

- [ ] admin 初始密码已修改
- [ ] 生产环境 SECRET_KEY 已改为随机字符串（至少32字符）
- [ ] HTTPS 已配置（Nginx SSL）
- [ ] NAS 目录权限最小化（仅服务账号可读写）
- [ ] 数据库文件权限最小化（600）
- [ ] 防火墙配置（仅内网可访问管理端口，外网仅开放下载）
- [ ] 日志定期备份和清理
- [ ] AD 服务账号权限最小化（只读）
- [ ] 生产环境使用 gunicorn/waitress，不使用 Flask 自带服务器
- [ ] FLASK_DEBUG=false

---

## 从 MVP 到生产的升级路径

| 阶段 | 前端 | 后端 | 存储 | 认证 |
|------|------|------|------|------|
| PSF（当前） | 纯 HTML+JS，localStorage | 无 | 浏览器模拟 | 模拟登录 |
| PSF 深化 | 纯 HTML+JS | Flask 后端（本包） | 本地磁盘/NAS | 本地用户 |
| PMF | 调用后端 API | Flask 后端 | NAS 挂载 | AD 集成 |
| 规模化 | 调用后端 API | Flask + PostgreSQL | NAS + 备份 | AD + SSO |

---

*SecureTrans 后端部署说明 v1.4 | 2026-08-26*
