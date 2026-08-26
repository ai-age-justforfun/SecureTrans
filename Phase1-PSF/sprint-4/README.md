# Sprint 4 — 服务器部署包与封闭数据中心交付

> Sprint：PSF-Sprint-4 | 阶段：PSF（问题-方案匹配验证）
> 核心交付：一键部署包 + 部署指南 + 部署验证脚本，可直接到封闭数据中心落地

---

## 一、核心问题：代码传到服务器可以直接运行吗？

**简短回答：不能直接运行，但经过本部署包准备后可一键部署。**

原代码存在 6 个必须解决的问题，本 Sprint 全部解决：

| # | 问题 | 原状态 | 本 Sprint 解决方案 |
|---|------|--------|-------------------|
| 1 | Windows venv 不兼容 | `venv/` 是 Windows 版（Scripts/ 而非 bin/），拷到 Linux 无法使用 | 部署包已排除 venv，`deploy.sh` 自动重建 Linux venv |
| 2 | 测试数据残留 | `data/securetrans.db` 和 `nas/` 含本地测试数据 | 部署包已排除，首次启动自动创建干净数据库 |
| 3 | gunicorn 未安装 | requirements.txt 中 gunicorn 被注释 | 已启用 gunicorn==21.2.0 |
| 4 | 前端页面缺失 | `static/` 目录为空，只有简陋的登录页 fallback | 已补充完整 SPA（index.html + login.html），8个模块对接所有API |
| 5 | gunicorn 不初始化 DB | `init_db()` 只在 `if __name__ == "__main__"` 块执行，gunicorn 导入时不执行 | 已修复为模块级别执行，任何方式导入都初始化 |
| 6 | 生产配置缺失 | 无 systemd service、nginx 配置、生产 .env | 已全部提供在 `config/` 目录 |

---

## 二、部署包内容

```
securetrans-deploy/                          （压缩后 38.7KB，17个文件）
├── deploy.sh                                # 一键部署脚本（9步自动化）
├── verify.sh                                # 部署验证脚本（35项全量API测试）
├── DEPLOY.md                                # 详细部署指南（10个章节）
├── backend-flask/                           # 清理后的后端代码（不含venv/测试数据）
│   ├── app.py                               # Flask主程序（已修复gunicorn初始化问题）
│   ├── requirements.txt                     # Python依赖（含gunicorn）
│   ├── test_api.py                          # 35项全量API测试脚本
│   ├── .env.example                         # 环境变量示例
│   ├── start.sh                             # Linux启动脚本
│   └── static/                              # 前端静态文件
│       ├── index.html                       # 主应用SPA（42KB，8个模块）
│       └── login.html                       # 登录页
└── config/                                  # 生产环境配置模板
    ├── .env.production                      # 生产环境变量模板
    ├── securetrans.service                  # systemd服务文件
    └── nginx-securetrans.conf               # Nginx反向代理配置
```

---

## 三、封闭数据中心：需要手工预装的软件

`deploy.sh` **不会**自动安装系统级软件，以下需在服务器上提前装好：

### 必须安装

| 软件 | 用途 | Ubuntu/Debian 安装命令 |
|------|------|----------------------|
| **Python 3.10+** | 运行时 | `apt install python3 python3-venv python3-pip` |
| **Nginx** | 反向代理 | `apt install nginx` |
| **NFS 客户端** | NAS 挂载 | `apt install nfs-common` |

### NAS 挂载（必须）

SecureTrans 的 staging/external/archive 三个目录**必须在同一个文件系统**，os.rename 才能实现 0拷贝。

```bash
# 创建挂载点
sudo mkdir -p /mnt/nas/securetrans

# 挂载 NAS（替换为实际 NAS 地址和导出路径）
sudo mount -t nfs -o rw,hard,intr nas-server:/export/securetrans /mnt/nas/securetrans

# 验证同文件系统（三个目录的 Filesystem 列必须相同）
df -h /mnt/nas/securetrans/staging /mnt/nas/securetrans/external /mnt/nas/securetrans/archive
```

> **如果没有 NAS**：直接用服务器本地磁盘，将 `.env` 中 `NAS_ROOT` 指向本地路径（如 `/opt/securetrans/data/nas`），三个目录自然在同一文件系统。PSF 原型验证完全够用。

### 可选：SSL 证书

生产环境建议配置 HTTPS，准备好证书文件：
- 证书：`/etc/nginx/ssl/securetrans.crt`
- 私钥：`/etc/nginx/ssl/securetrans.key`

PSF 原型验证阶段可先用 HTTP。

---

## 四、部署三步曲

### 第一步：上传并解压

```bash
# 从本地上传部署包到服务器
scp securetrans-deploy.tar.gz user@server:/tmp/

# 登录服务器并解压
ssh user@server
cd /tmp && tar xzf securetrans-deploy.tar.gz
```

### 第二步：一键部署

```bash
cd /tmp/securetrans-deploy
sudo bash deploy.sh
```

`deploy.sh` 自动完成 9 步：
1. 前置检查（Python 3.10+、venv 模块）
2. 创建服务用户（securetrans，无登录权限）
3. 备份旧版本（如存在）
4. 复制程序文件到 `/opt/securetrans/backend-flask/`
5. 配置 `.env`（从模板生成，自动生成随机 SECRET_KEY）
6. 创建 Python 虚拟环境并安装依赖
7. NAS 存储目录准备 + 同文件系统验证
8. 设置最小权限
9. 安装 systemd 服务并启动 + 健康检查

### 第三步：手工配置 + 验证

```bash
# 1. 修改 .env 配置（重点是 NAS_ROOT）
sudo vi /opt/securetrans/backend-flask/.env

# 2. 重启服务使配置生效
sudo systemctl restart securetrans

# 3. 配置 Nginx 反向代理
sudo cp config/nginx-securetrans.conf /etc/nginx/conf.d/securetrans.conf
sudo vi /etc/nginx/conf.d/securetrans.conf   # 修改 server_name
sudo nginx -t && sudo systemctl reload nginx

# 4. 运行全量验证（35项测试，预期100%通过）
bash verify.sh
```

---

## 五、PSF 原型测试指南

### 初始账号

| 用户名 | 密码 | 角色 | 说明 |
|--------|------|------|------|
| `admin` | `Admin@123` | 系统管理员 | 首次登录强制修改密码 |

### 创建测试用户

登录 admin → 用户管理 → 新建用户，创建以下角色：

| 用户名 | 角色 | 用途 |
|--------|------|------|
| `user01` | 普通用户 | 测试文件提交 |
| `manager01` | 部门主管 | 测试一级审批 |
| `exec01` | 公司高管 | 测试二级审批 |

### 核心测试流程

#### 流程 A：免审批自动摆渡（特征码匹配）

1. `user01` 登录 → 文件提交 → 上传 PDF 文件（匹配特征码）
2. 填写接收方信息 → 提交
3. 系统提示「免审批自动通过」
4. 外网下载 → 可见文件已摆渡，可下载
5. 物理验证：`ls /mnt/nas/securetrans/external/` 可见文件目录

#### 流程 B：人工审批摆渡（特征码不匹配）

1. `user01` 上传 EXE 文件（不匹配特征码）→ 提交 → 状态「待一级审批」
2. `manager01` 登录 → 待我审批 → 通过 → 非合作方进入「待二级审批」
3. `exec01` 登录 → 待我审批 → 通过 → os.rename 摆渡到 external
4. 外网下载 → 可下载

#### 流程 C：驳回

审批页面点击「驳回」→ 填写驳回原因 → 文件 os.rename 到 archive → 状态「已驳回」

#### 流程 D：大文件上传

上传 100MB+ 文件 → 观察流式上传（内存稳定几十MB）→ 摆渡操作毫秒级完成（os.rename 0拷贝）

### 验证 os.rename 0拷贝

```bash
# 创建 100MB 测试文件
dd if=/dev/zero of=/mnt/nas/securetrans/staging/test.bin bs=1M count=100

# 计时移动（模拟摆渡）
time mv /mnt/nas/securetrans/staging/test.bin /mnt/nas/securetrans/external/test.bin

# 耗时 < 0.1 秒 = 0拷贝（同文件系统）
# 清理
rm /mnt/nas/securetrans/external/test.bin
```

---

## 六、部署后日常运维

```bash
# 服务管理
sudo systemctl status securetrans
sudo systemctl restart securetrans
sudo systemctl stop securetrans

# 查看日志
sudo journalctl -u securetrans -f                    # 实时跟踪
sudo journalctl -u securetrans -n 100 --no-pager     # 最近100行
tail -f /opt/securetrans/backend-flask/data/securetrans.log

# 数据备份
sqlite3 /opt/securetrans/backend-flask/data/securetrans.db ".backup /backup/securetrans_$(date +%Y%m%d).db"

# 升级部署（上传新版本后重新执行 deploy.sh，自动备份旧版本）
cd /tmp/securetrans-deploy-new
sudo bash deploy.sh
```

---

## 七、本 Sprint 修复的 Bug

### BUG-001：gunicorn 启动时数据库不初始化

**现象**：`python app.py` 启动正常，但 `gunicorn app:app` 启动后访问任何接口报数据库表不存在。

**根因**：`init_db()` 和 `start_scheduler()` 只在 `if __name__ == "__main__":` 块中调用。gunicorn 导入模块时 `__name__` 为 `"app"`，不执行该块。

**修复**：将 `init_db()` 和 `start_scheduler()` 移到模块级别（文件末尾，`if __name__` 块之前），确保任何方式导入都执行初始化。

### BUG-002：前端 static/ 目录为空

**现象**：登录成功后跳转首页，页面空白。

**根因**：原 `backend-flask/static/` 目录为空，app.py 只有简陋的登录页 fallback，没有主应用页面。

**修复**：补充完整前端 SPA（index.html 42KB + login.html 4KB），实现仪表盘、文件提交、我的提交、待我审批、外网下载、用户管理、系统配置、审计日志全部 8 个模块，对接所有后端 API。

---

## 八、测试结果

**总计 35 项测试，全部通过，通过率 100%。**

覆盖 13 大类：基础服务、认证、文件上传、提交单创建、提交单查询、审批流程、外网下载、用户管理、AD角色映射、系统配置、审计与统计、物理文件验证（os.rename 0拷贝）、退出登录。

详见 `../../docs/06-test-report.md`。

---

*Sprint 4 交付文档 | 2026-08-26*
