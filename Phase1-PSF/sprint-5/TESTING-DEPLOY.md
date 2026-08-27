# SecureTrans 测试环境部署指南

> 版本：v1.5.0 | 部署模式：testing
> 适用：测试服务器验证 / 本地开发 / PSF 阶段原型测试
> 目标：用最简单的方式跑起来，验证功能，不涉及 NAS/gunicorn/nginx

---

## 一、测试环境 vs 生产环境

| 维度 | 测试环境（本指南） | 生产环境（后续） |
|------|-------------------|----------------|
| 部署模式 | `DEPLOY_MODE=testing` | `DEPLOY_MODE=production` |
| 文件存储 | 本地磁盘 `./nas` | NAS 挂载 `/mnt/nas/securetrans` |
| WSGI 服务器 | Flask 自带 `python app.py` | gunicorn `gunicorn app:app` |
| 反向代理 | 无，直接访问 8000 端口 | nginx 反向代理 + HTTPS |
| 进程管理 | 前台运行 / nohup | systemd 服务 |
| AD 认证 | 默认关闭，用本地 admin | 启用，对接 AD/sssd |
| 适用阶段 | PSF 验证 / 功能测试 | PMF 试点 / 正式部署 |

**核心思路**：测试环境用最少的依赖跑起来，验证功能通过后，切到生产环境只需改 `.env` 配置 + 换启动方式，代码完全复用。

---

## 二、测试环境部署步骤

### 前置要求

- Linux 服务器（CentOS/Rocky 8.x / Ubuntu 20.04+）或 Windows 开发机
- Python 3.10+
- 网络：测试客户端能访问服务器 8000 端口
- **不需要**：NAS、gunicorn、nginx、AD（这些是生产环境的事）

### 第一步：上传代码

将 `backend-flask/` 目录上传到测试服务器，例如 `/opt/securetrans/`：

```bash
# 方式1：scp 上传
scp -r backend-flask/ user@test-server:/opt/securetrans/

# 方式2：从 Gitea 克隆
git clone http://gitea-server/openwrtadmin/SecureTrans.git
cd SecureTrans/Phase1-PSF/sprint-5/backend-flask
```

### 第二步：配置环境变量

```bash
cd /opt/securetrans/backend-flask

# 使用测试环境配置（直接复制 .env.testing 即可）
cp .env.testing .env

# 检查配置
cat .env
# 确认 DEPLOY_MODE=testing
# 确认 NAS_ROOT=./nas（本地路径）
```

> `.env.testing` 已经配置好了测试环境的所有参数，直接复制即可用。唯一建议修改的是 `SECRET_KEY`（测试环境不改也能跑）。

### 第三步：启动服务

```bash
# 方式1：用启动脚本（自动创建 venv + 安装依赖 + 启动）
bash start.sh

# 方式2：手动启动
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

启动成功后会看到：

```
========================================
  SecureTrans 启动
  部署模式: testing
  存储目录: ./nas
  访问地址: http://0.0.0.0:8000
  初始管理员: admin / Admin@123
  [测试模式] Flask自带服务器，适合开发和测试验证
========================================
```

### 第四步：验证服务

```bash
# 健康检查（应返回 deployMode=testing）
curl http://localhost:8000/api/health
# 期望: {"status":"ok","deployMode":"testing",...}

# 浏览器访问
# 打开 http://服务器IP:8000
# 用 admin / Admin@123 登录
```

### 第五步：后台运行（可选）

测试时如果需要后台运行：

```bash
# nohup 后台运行
nohup bash start.sh > securetrans.log 2>&1 &

# 查看日志
tail -f securetrans.log

# 停止服务
pkill -f "python app.py"
```

---

## 三、测试验证清单

部署完成后，按以下清单验证：

### 基础功能

- [ ] 访问 http://服务器IP:8000 显示登录页
- [ ] admin / Admin@123 登录成功
- [ ] 首次登录强制修改密码
- [ ] 修改密码后重新登录成功

### 文件提交与摆渡

- [ ] 上传 PDF 文件（匹配特征码，免审批自动通过）
- [ ] 上传 EXE 文件（不匹配特征码，进入人工审批）
- [ ] 上传 ZIP/TAR.GZ 压缩包（自动解包列清单）
- [ ] 上传 .bit 文件（Vivado Bitstream 识别）
- [ ] 一级审批通过（合作方直接摆渡）
- [ ] 二级审批通过（非合作方摆渡到 external）
- [ ] 外网下载文件成功
- [ ] 文件物理路径从 staging → external（os.rename 0拷贝）

### 管理功能

- [ ] 创建本地用户（普通用户/部门主管/公司高管）
- [ ] 用户管理列表正常
- [ ] 特征码规则列表显示 20 条规则
- [ ] 审计日志可查询
- [ ] 统计数据正常

### os.rename 0拷贝验证

```bash
# 在服务器上验证
# 1. 查看 staging 目录（提交后、审批前）
ls -la ./nas/staging/

# 2. 审批通过后，staging 中文件消失，出现在 external
ls -la ./nas/external/

# 3. 移动操作耗时毫秒级（与文件大小无关）
# 可以在日志中看到 "os.rename 0拷贝移动" 的记录
tail -f ./data/securetrans.log | grep "os.rename"
```

---

## 四、从测试环境切到生产环境

测试验证通过后，切换到生产环境只需 3 步：

### 1. 改配置

```bash
# 复制生产环境配置
cp .env.production .env

# 修改关键参数
vi .env
# DEPLOY_MODE=production
# NAS_ROOT=/mnt/nas/securetrans   # 改成实际 NAS 挂载路径
# SECRET_KEY=随机字符串            # 务必修改
# AD_ENABLED=true                  # 如需要 AD 认证
```

### 2. 准备 NAS

```bash
# 挂载 NAS（staging/external/archive 必须在同一文件系统）
sudo mount -t nfs nas-server:/export/securetrans /mnt/nas/securetrans

# 验证同文件系统
df -h /mnt/nas/securetrans/staging /mnt/nas/securetrans/external /mnt/nas/securetrans/archive
# 三个目录的 Filesystem 列必须相同
```

### 3. 换启动方式

```bash
# 生产环境用 gunicorn，不要用 python app.py
bash start-production.sh

# 或配置 systemd 服务（推荐）
# 参考 sprint-4 部署包中的 config/securetrans.service
```

**代码完全不变**，只是配置和启动方式不同。这就是 `DEPLOY_MODE` 开关的价值。

---

## 五、常见问题

### Q: 测试环境需要 NAS 吗？
A: 不需要。测试环境用本地磁盘 `./nas`，os.rename 在本地磁盘同样是 0拷贝。

### Q: 测试环境可以用 gunicorn 吗？
A: 可以，但没必要。Flask 自带服务器足够测试用。gunicorn 是生产环境的事。

### Q: 测试环境数据会保留吗？
A: 会。数据存在 `./data/securetrans.db` 和 `./nas/` 目录。删除这两个目录即可重置。

### Q: 如何重置测试环境？
A: `rm -rf data/ nas/ && python app.py`，会重新初始化数据库和目录。

### Q: AD 认证在测试环境怎么测？
A: 在 `.env` 中设 `AD_ENABLED=true`，配置 AD_HOST/AD_DOMAIN/AD_BASE_DN。程序用 LDAP 直连，与 sssd 兼容。

### Q: 端口被占用怎么办？
A: 在 `.env` 中修改 `PORT=8001` 或其他端口。

---

## 六、文件清单

```
backend-flask/
├── app.py                  # 主程序 v1.5.0
├── requirements.txt        # Python 依赖
├── test_api.py             # 35项全量测试
├── start.sh                # 测试环境启动脚本（Flask）
├── start-production.sh     # 生产环境启动脚本（gunicorn）
├── .env.testing            # 测试环境配置模板 ← 测试用这个
├── .env.production         # 生产环境配置模板
├── .env.example            # 通用配置示例
├── README.md               # 后端说明
└── static/
    ├── index.html          # 主应用 SPA
    └── login.html          # 登录页
```

---

*测试环境部署指南 v1.5.0 | 2026-08-27*
