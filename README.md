# SecureTrans — 轻量级跨网文件审批摆渡系统

> 版本：v2.0.1 | 阶段：PSF（问题-方案匹配验证）
> 技术栈：Flask 3.0 + Flask-Login + SQLite + os.rename 0拷贝摆渡
> 开发模式：主干开发（Trunk-Based Development）+ 单分支 main

---

## 项目简介

SecureTrans 是面向中小企业的轻量级单向跨网文件审批摆渡系统，解决内网红区/黄区到外网绿区的文件安全外发问题。

**核心价值**：审批可控、摆渡0拷贝、归档可审计。

**核心设计**：
- **os.rename 0拷贝摆渡**：同文件系统内只改目录项，不移动数据块，毫秒级完成
- **免审批机制**：特征码匹配的文件自动通过，提升效率（支持20条规则，含压缩包/Vivado Bitstream）
- **分级审批**：合作方一级审批，非合作方二级审批
- **轻量级部署**：单服务器 + SQLite + NAS，支撑50人到200人
- **双模式部署**：测试环境（本地文件系统+Flask）/ 生产环境（NAS+gunicorn），一个开关切换
- **双 OS 支持**：Windows（waitress）与 Linux（gunicorn）均可一键部署，离线依赖随发布包内置
- **单/双网卡网络隔离**：单网卡按来源网段识别内外网（Nginx geo / 应用层 INTERNAL_CIDRS 兜底）；双网卡绑定内/外网卡，应用层隔离统一——外网面仅登录+下载，管理接口 403

---

## 快速开始

### 本地开发 / 测试环境

```bash
cd src
cp .env.testing .env          # 测试环境配置（默认 DEPLOY_MODE=testing）
python -m venv venv
# Windows: venv\Scripts\activate
# Linux:   source venv/bin/activate
pip install -r requirements.txt
python app.py
```

访问 http://localhost:8000，初始账号 `admin / Admin@123`。

### 运行测试

```bash
# 先启动服务（在 src/ 目录下）
cd src && python app.py

# 另一个终端运行测试
cd tests
python test_api.py
# 预期：171项测试全部通过，通过率100%
```

### 测试环境部署（服务器验证）

详见 [部署指南](docs/DEPLOY.md) — 本地/WSL 测试环境 + 生产环境 + 单/双网卡 + Windows 部署，统一到一份文档。

### 生产环境部署

```bash
# 部署脚本在 infra/
cd infra
sudo bash deploy.sh    # 一键部署（9步自动化）
bash verify.sh         # 部署验证（171项全量测试）
```

详见 [生产环境部署指南](docs/DEPLOY.md)。

---

## 目录结构

```
SecureTrans/
├── README.md                 # 本文件（项目入口）
├── AGENTS.md                 # AI协作指南（工具默认扫根目录）
├── .gitignore                # Git忽略规则
├── LICENSE                   # MIT许可证
├── src/                      # 源代码（按功能模块组织）
│   ├── app.py                # Flask主程序（单文件，含所有API）
│   ├── requirements.txt      # Python依赖
│   ├── start.sh              # 测试环境启动脚本（Flask自带服务器）
│   ├── start-production.sh   # 生产环境启动脚本（gunicorn）
│   ├── start.bat             # Windows启动脚本
│   ├── .env.example          # 环境变量通用示例
│   ├── .env.testing          # 测试环境配置模板
│   ├── .env.production       # 生产环境配置模板
│   ├── README.md             # 后端代码说明
│   └── static/               # 前端静态文件
│       ├── index.html        # 主应用SPA
│       └── login.html        # 登录页
├── tests/                    # 自动化测试
│   └── test_api.py           # 全量API测试脚本（14大类166项）
├── docs/                     # 统一文档（数字前缀排序，持续刷新）
│   ├── 00-lean-startup-phase-map.md   # Lean Startup三阶段映射与决策门
│   ├── 01-scrum-io-definition.md      # Scrum各阶段输入输出定义
│   ├── 02-prd-v1.4.md                 # 产品需求文档（最新）
│   ├── 03-psf-process.md              # PSF阶段标准流程
│   ├── 04-pmf-process.md              # PMF阶段标准流程（下一阶段准备）
│   ├── 05-test-cases.md               # 测试用例
│   ├── 06-test-report.md              # 测试报告（166项全通过）
│   ├── 07-psf-sprint4-retrospective.md # PSF阶段迭代小结
│   └── TESTING-DEPLOY.md              # 测试环境部署指南
└── infra/                    # 基础设施配置
    ├── deploy.sh             # 一键部署脚本（9步自动化）
    ├── verify.sh             # 部署验证脚本（171项全量测试）
    ├── DEPLOY.md             # 生产环境详细部署指南
    ├── nginx-securetrans.conf # Nginx反向代理配置
    └── securetrans.service   # systemd服务配置
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
| GET | /api/health | 健康检查（含 deployMode 字段） |

---

## 研发流程

### 方法论
- **大阶段**：Lean Startup（PSF → PMF → Scale），每阶段有决策门
- **迭代**：Scrum（1周Sprint for PSF，2周Sprint for PMF），Sprint作为研发工作分解阶段，在过程文档中体现
- **开发模式**：主干开发（Trunk-Based Development），单分支 main，临时开发拉分支，合入后删除
- **交付**：DevOps（轻量CI/CD，蓝绿部署）

### Git 工作流

```
main ────●────●────●────●────  始终可部署
           \        /
            feature-xxx  临时分支（开发→测试→合入→删除）
```

- **main 分支**：始终可部署，保护分支，直接推送或PR合入
- **临时分支**：开发新功能时拉取（如 `feature/ad-ldap`），测试通过后合入 main 并删除
- **Commit 规范**：`<type>(<scope>): <描述>`，不强制带 Sprint 编号，可关联 Story 编号

### 当前阶段
**PSF（问题-方案匹配验证）**— 技术验证全部通过，测试环境部署方案就绪，待服务器验证。

详见：
- [Lean Startup阶段映射](docs/00-lean-startup-phase-map.md)
- [Scrum各阶段输入输出定义](docs/01-scrum-io-definition.md)
- [产品需求文档 PRD v1.4](docs/02-prd-v1.4.md)
- [PSF阶段标准流程](docs/03-psf-process.md)
- [测试用例](docs/05-test-cases.md)
- [测试报告（166项全通过）](docs/06-test-report.md)
- [PSF阶段迭代小结](docs/07-psf-sprint4-retrospective.md)
- [测试环境部署指南](docs/TESTING-DEPLOY.md)

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

### ADR-003：主干开发 + 单分支
- 小团队/副业项目，避免多分支合并冲突，main始终可部署
- Sprint作为研发分解阶段在文档中体现，不用目录结构做版本管理

---

## 许可证

[MIT License](LICENSE) — 可自由使用、修改、分发，保留版权声明即可。

---

*SecureTrans v2.0.1 | 2026-09-01*
