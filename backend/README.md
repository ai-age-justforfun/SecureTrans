# SecureTrans 后端部署说明

> 轻量级跨网文件审批摆渡系统 - PMF 阶段部署包
> 单文件 FastAPI + SQLite + 软链接零拷贝摆渡

## 目录结构

```
backend/
├── main.py              # 后端主程序（单文件，含所有API）
├── requirements.txt     # Python 依赖
├── .env.example         # 环境变量配置示例
├── start.bat            # Windows 启动脚本
├── start.sh             # Linux 启动脚本
├── README.md            # 本文件
├── data/                # 运行时数据（自动创建）
│   ├── securetrans.db   # SQLite 数据库
│   ├── securetrans.log  # 日志
│   ├── temp/            # 上传临时目录
│   └── nas/             # NAS 模拟目录（生产环境替换为真实NAS挂载）
│       ├── archive/     # 归档（唯一真实存储）
│       ├── internal/    # 内网软链接（审批用）
│       └── external/    # 外网软链接（下载用）
└── static/              # 前端静态文件（将 MVP HTML 放入此目录）
```

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
python main.py
```

启动后访问：**http://localhost:8000**

初始管理员：**admin / Admin@123**（首次登录强制修改密码）

## 生产环境部署

### 1. NAS 挂载配置

将真实 NAS 挂载到服务器，然后在 `.env` 中配置：

```bash
NAS_MOUNT=/mnt/nas
```

确保目录结构存在：
```bash
mkdir -p /mnt/nas/archive
mkdir -p /mnt/nas/internal/pending
mkdir -p /mnt/nas/external/published
```

**重要**：NAS 文件系统必须支持软链接（symlink）。大部分 NFS/SMB 挂载支持，但需确认。

### 2. 双网卡网络配置

- eth0：内网（提交、审批）
- eth1：外网（下载）

Nginx 反向代理配置示例：
```nginx
server {
    listen 80;
    server_name securetrans.internal.company.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        client_max_body_size 10G;  # 大文件上传
    }
}
```

### 3. HTTPS 配置

生产环境建议配置 SSL，使用 Nginx 终止 TLS：
```nginx
server {
    listen 443 ssl;
    server_name securetrans.company.com;
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    # ... 同上 proxy 配置
}
```

### 4. systemd 服务（Linux 生产环境）

创建 `/etc/systemd/system/securetrans.service`：
```ini
[Unit]
Description=SecureTrans File Ferry Service
After=network.target

[Service]
Type=simple
User=securetrans
WorkingDirectory=/opt/securetrans/backend
EnvironmentFile=/opt/securetrans/backend/.env
ExecStart=/opt/securetrans/backend/venv/bin/python /opt/securetrans/backend/main.py
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

### 5. AD/LDAP 对接

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
3. 在 `main.py` 的 `authenticate_ad` 函数中实现真实 LDAP 认证逻辑（代码中有 TODO 注释和示例）

## 前端部署

将 MVP 原型 HTML 文件放入 `backend/static/` 目录，后端会自动托管静态文件：

```bash
cp ferry-mvp-prototype-offline.html backend/static/index.html
cp vue.global.prod.js backend/static/
cp element-plus.min.js backend/static/
cp element-plus.min.css backend/static/
```

> 注意：MVP 原型是纯前端（localStorage），与后端 API 是独立的。
> PMF 阶段需要将前端改为调用后端真实 API（前后端联调）。

## API 接口一览

### 认证
- `POST /api/auth/login` - 登录
- `GET /api/auth/me` - 获取当前用户
- `POST /api/auth/change-password` - 修改密码

### 提交与文件
- `POST /api/submissions/upload` - 上传文件
- `POST /api/submissions` - 创建提交单
- `GET /api/submissions` - 提交单列表
- `GET /api/submissions/{id}` - 提交单详情
- `GET /api/submissions/pending/my` - 待我审批

### 审批
- `POST /api/submissions/{id}/approve` - 审批（通过/驳回）

### 外网下载
- `GET /api/external/files` - 已摆渡文件列表
- `GET /api/external/{id}/download/{filename}` - 下载文件

### 用户管理（admin）
- `GET/POST/DELETE /api/admin/local-users` - 本地用户管理
- `POST /api/admin/local-users/{username}/reset-password` - 重置密码
- `GET/POST/DELETE /api/admin/role-mappings` - AD角色映射
- `POST /api/admin/ad/search` - 搜索AD用户

### 系统配置
- `GET /api/config/feature-rules` - 特征码规则
- `GET/PUT /api/config/system` - 系统配置

### 审计与统计
- `GET /api/audit-logs` - 审计日志
- `GET /api/stats` - 统计数据
- `GET /api/health` - 健康检查

## 数据备份

### 数据库备份
```bash
# SQLite 备份（热备份）
sqlite3 data/securetrans.db ".backup backup/securetrans_$(date +%Y%m%d).db"
```

### 归档文件备份
归档文件在 NAS 上，由 NAS 层保障冗余。如需额外备份：
```bash
rsync -av /mnt/nas/archive/ /backup/archive/
```

### 定时备份（crontab）
```bash
# 每天凌晨2点备份数据库
0 2 * * * /opt/securetrans/backup.sh
```

## 故障排查

| 问题 | 排查 |
|------|------|
| 启动失败 | 查看 `data/securetrans.log`，检查端口是否被占用 |
| 上传大文件失败 | 检查 Nginx `client_max_body_size` 和磁盘空间 |
| 摆渡失败（软链接） | 检查 NAS 是否支持 symlink，目录权限是否正确 |
| AD 登录失败 | 检查 AD 连接配置，测试 `ldapsearch` 能否连通 |
| 页面空白 | 检查 `static/` 目录是否有前端文件，浏览器 F12 看控制台 |
| 数据库锁定 | SQLite WAL 模式，一般不会锁；如锁定检查是否多进程写入 |

## 安全基线检查清单

- [ ] admin 初始密码已修改
- [ ] 生产环境 SECRET_KEY 已改为随机字符串
- [ ] HTTPS 已配置（Nginx SSL）
- [ ] NAS 目录权限最小化（仅服务账号可读写）
- [ ] 数据库文件权限最小化（600）
- [ ] 防火墙配置（仅内网可访问管理端口）
- [ ] 日志定期备份和清理
- [ ] AD 服务账号权限最小化（只读）

---

*SecureTrans 后端部署说明 v1.0 | 2026-08-26*
