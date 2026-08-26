# SecureTrans — 轻量级跨网文件审批摆渡系统

> 版本：v1.4 | 阶段：PSF（问题-方案匹配验证）
> 技术栈：Flask 3.0 + Flask-Login + SQLite + os.rename 0拷贝摆渡

---

## 项目简介

SecureTrans 是面向中小企业的轻量级单向跨网文件审批摆渡系统，解决内网红区/黄区到外网绿区的文件安全外发问题。

**核心价值**：审批可控、摆渡0拷贝、归档可审计。

**核心设计**：
- **os.rename 0拷贝摆渡**：同文件系统内只改目录项，不移动数据块，毫秒级完成
- **免审批机制**：特征码匹配的文件自动通过，提升效率
- **分级审批**：合作方一级审批，非合作方二级审批
- **轻量级部署**：单服务器 + SQLite + NAS，支撑50人到200人

---

## 快速开始

### 本地开发

```bash
cd Phase1-PSF/sprint-3/backend-flask
python -m venv venv
# Windows: venv\Scripts\activate
# Linux:   source venv/bin/activate
pip install -r requirements.txt
python app.py
```

访问 http://localhost:8000，初始账号 `admin / Admin@123`。

### 运行测试

```bash
cd Phase1-PSF/sprint-3/backend-flask
python test_api.py
# 预期：35项测试全部通过，通过率100%
```

### 服务器部署

```bash
# 上传部署包并解压
tar xzf Phase1-PSF/sprint-4/securetrans-deploy.tar.gz
cd securetrans-deploy

# 一键部署
sudo bash deploy.sh

# 部署验证（35项全量测试）
bash verify.sh
```

详见 [Sprint 4 部署指南](Phase1-PSF/sprint-4/README.md) 和 [DEPLOY.md](Phase1-PSF/sprint-4/securetrans-deploy/DEPLOY.md)。

---

## 目录结构

```
SecureTrans/
├── README.md                              # 本文件（项目入口）
├── AGENTS.md                              # AI协作指南（工具默认扫根目录）
├── .gitignore                             # Git忽略规则
├── docs/                                  # 所有项目文档（数字前缀排序）
│   ├── 00-lean-startup-phase-map.md       # Lean Startup三阶段映射与决策门
│   ├── 01-scrum-io-definition.md          # Scrum各阶段输入输出定义
│   ├── 02-prd-v1.4.md                     # 产品需求文档（最新）
│   ├── 03-psf-process.md                  # PSF阶段标准流程
│   ├── 04-pmf-process.md                  # PMF阶段标准流程（下一阶段准备）
│   ├── 05-test-cases.md                   # 测试用例（15个场景）
│   ├── 06-test-report.md                  # 测试报告（35项全通过）
│   └── 07-psf-sprint4-retrospective.md    # PSF Sprint4 迭代小结
└── Phase1-PSF/                            # 第一阶段：PSF（问题-方案匹配验证）
    ├── sprint-1/                          # Sprint 1：前端原型（HTML/JS/CSS）
    │   ├── ferry-mvp-prototype.html       # 前端原型（主版本）
    │   ├── ferry-mvp-prototype-offline.html # 离线版原型
    │   ├── ferry-mvp-debug.html           # 调试版原型
    │   ├── vue.global.js / vue.global.prod.js # Vue3运行时
    │   └── element-plus.min.js / .css     # Element Plus UI库
    ├── sprint-2/                          # Sprint 2：后端第一版（FastAPI，已废弃）
    │   └── backend/                       # FastAPI实现（保留参考）
    ├── sprint-3/                          # Sprint 3：后端第二版（Flask，当前主力）
    │   └── backend-flask/                 # Flask实现
    │       ├── app.py                     # Flask主程序（单文件，含所有API）
    │       ├── requirements.txt           # Python依赖
    │       ├── test_api.py                # 全量API测试脚本（35项）
    │       ├── .env.example               # 环境变量示例
    │       ├── start.sh                   # Linux启动脚本
    │       └── static/                    # 前端静态文件
    │           ├── index.html             # 主应用SPA
    │           └── login.html             # 登录页
    └── sprint-4/                          # Sprint 4：服务器部署包（封闭数据中心交付）
        ├── README.md                      # Sprint 4 交付说明（核心问题+部署指南）
        ├── securetrans-deploy.tar.gz      # 部署包压缩文件（38.7KB）
        └── securetrans-deploy/            # 部署包源码
            ├── deploy.sh                  # 一键部署脚本（9步自动化）
            ├── verify.sh                  # 部署验证脚本（35项全量测试）
            ├── DEPLOY.md                  # 详细部署指南
            ├── backend-flask/             # 清理后的后端（不含venv/测试数据）
            └── config/                    # 生产配置模板（nginx/systemd/.env）
```

---

## 核心业务流程

```
用户上传文件 → 计算MD5 + 特征码匹配 → 免审批判定
                                          │
                          ┌───────────────┴───────────────┐
                          │                               │
                    所有文件匹配特征码                存在不匹配文件
                          │                               │
                    自动通过（0级）                   人工审批流
                          │                               │
                          │                    ┌──────────┴──────────┐
                          │                    │                     │
                          │              合作方（一级审批）    非合作方（二级审批）
                          │                    │                     │
                          └────────────────────┴─────────────────────┘
                                               │
                                          os.rename 0拷贝
                                          staging → external
                                               │
                                          外网下载（流式读取）
                                               │
                                          过期清理（凌晨2点）
                                          os.rename external → archive
```

---

## API 接口一览

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/auth/login | 登录 |
| GET/POST | /api/auth/logout | 退出登录 |
| GET | /api/auth/me | 获取当前用户 |
| POST | /api/auth/change-password | 修改密码 |
| POST | /api/submissions/upload | 上传文件（流式，支持大文件） |
| POST | /api/submissions | 创建提交单 |
| GET | /api/submissions | 提交单列表 |
| GET | /api/submissions/{id} | 提交单详情 |
| GET | /api/submissions/pending/my | 待我审批 |
| POST | /api/submissions/{id}/approve | 审批（通过/驳回） |
| GET | /api/external/files | 已摆渡文件列表 |
| GET | /api/external/{id}/download/{filename} | 下载文件 |
| GET/POST | /api/admin/local-users | 用户管理 |
| DELETE | /api/admin/local-users/{username} | 删除用户 |
| POST | /api/admin/local-users/{username}/reset-password | 重置密码 |
| GET/POST | /api/admin/role-mappings | AD角色映射 |
| POST | /api/admin/ad/search | 搜索AD用户 |
| POST | /api/admin/cleanup-expired | 手动触发过期清理 |
| GET | /api/config/feature-rules | 特征码规则 |
| GET/PUT | /api/config/system | 系统配置 |
| GET | /api/audit-logs | 审计日志 |
| GET | /api/stats | 统计数据 |
| GET | /api/health | 健康检查 |

---

## 研发流程

### 方法论
- **大阶段**：Lean Startup（PSF → PMF → Scale），每阶段有决策门
- **迭代**：Scrum（1周Sprint for PSF，2周Sprint for PMF）
- **交付**：DevOps（轻量CI/CD，蓝绿部署）

### 当前阶段
**PSF（问题-方案匹配验证）**— Sprint 1~4 已完成，技术验证全部通过，部署包就绪，待用户验证。

Sprint 演进线：
- **Sprint 1**：前端原型（HTML/JS/CSS，Vue3 + Element Plus）
- **Sprint 2**：后端第一版（FastAPI，已废弃，保留参考）
- **Sprint 3**：后端第二版（Flask，当前主力，35项测试全通过）
- **Sprint 4**：服务器部署包（封闭数据中心一键部署 + 部署验证）

详见：
- [Lean Startup阶段映射](docs/00-lean-startup-phase-map.md)
- [Scrum各阶段输入输出定义](docs/01-scrum-io-definition.md)
- [产品需求文档 PRD v1.4](docs/02-prd-v1.4.md)
- [PSF阶段标准流程](docs/03-psf-process.md)
- [测试用例](docs/05-test-cases.md)
- [测试报告（35项全通过）](docs/06-test-report.md)
- [PSF Sprint4迭代小结](docs/07-psf-sprint4-retrospective.md)
- [Sprint 4 部署交付说明](Phase1-PSF/sprint-4/README.md)

### 下一阶段
**PMF（产品-市场匹配验证）**— 流程文档已就绪，核心是AD/LDAP集成和真实部署试点。

详见 [PMF标准流程](docs/04-pmf-process.md)。

---

## 技术决策记录（ADR）

### ADR-001：os.rename 而不是软链接
- 0拷贝性能等价，但全平台原生支持，NAS兼容性好，权限简单
- 详见 PRD v1.4 第2.2节

### ADR-002：Flask 而不是 FastAPI
- Flask-Login生态成熟，团队学习成本低，50人规模性能不是瓶颈
- 详见 PRD v1.4 第3.2节

---

## 许可证

[MIT License](LICENSE) — 可自由使用、修改、分发，保留版权声明即可。

---

*SecureTrans v1.4 | 2026-08-26*
