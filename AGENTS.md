# SecureTrans 项目 AI 协作指南

> 本文件指导 AI Agent 在本项目中的协作行为，确保代码和文档的一致性。

---

## 项目概况

- **项目名**：SecureTrans — 轻量级跨网文件审批摆渡系统
- **当前阶段**：PSF（问题-方案匹配验证）
- **技术栈**：Flask 3.0 + Flask-Login + SQLite + os.rename 0拷贝
- **代码架构**：后端单文件（`src/app.py` ~1350行），前端单页应用（`src/static/index.html`）
- **开发模式**：主干开发（Trunk-Based Development），单分支 main
- **部署目标**：封闭数据中心，Linux服务器，一键部署

---

## 代码规范

### 后端（Python / Flask）

- **单文件架构**：所有后端逻辑在 `src/app.py` 中，不拆分模块（PSF阶段保持简单）
- **配置**：所有可配置项通过环境变量读取，默认值在代码中定义，`.env` 文件覆盖
- **部署模式**：`DEPLOY_MODE=testing`（本地文件系统+Flask）/ `production`（NAS+gunicorn），一个开关切换
- **数据库**：SQLite，使用 `sqlite3` 标准库，不使用 ORM（保持轻量）
- **认证**：Flask-Login，本地用户 + AD用户（LDAP直连）统一会话管理
- **文件操作**：必须使用 `os.rename` 实现0拷贝摆渡，禁止使用 `shutil.move`（会退化为复制）
- **大文件上传**：流式读取（`file.stream.read(65536)`），边读边算MD5，不加载整个文件到内存
- **日志**：使用 `logging` 模块，同时输出到文件和控制台
- **错误处理**：API 返回 JSON `{"error": "描述"}` + 合适的HTTP状态码
- **模块级初始化**：`init_db()` 和 `start_scheduler()` 必须在模块级别调用，不能只在 `if __name__ == "__main__"` 中（gunicorn导入时不执行该块）

### 前端（HTML / JS / CSS）

- **单页应用**：所有前端逻辑在 `src/static/index.html` 中，内联CSS和JS，不使用构建工具
- **API调用**：使用 `fetch()`，`credentials: 'same-origin'`，JSON格式请求体
- **样式**：简洁商务风格，蓝色主色调（#2563eb / #1e3a5f），不使用框架
- **角色权限**：前端根据 `currentUser.role` 显示/隐藏菜单，但后端必须做权限校验（前端只做体验优化）

### Git 提交规范

**主干开发，原子化提交**：

```
<type>(<scope>): <简短描述>
[可选] 详细说明
[可选] Story关联: #story-xxx
```

- **type**：feat / fix / docs / refactor / test / chore / refactor
- **scope**：auth / submission / approval / admin / deploy / doc / frontend / infra
- **不强制带 Sprint 编号**：Sprint是管理节奏，不是代码的身份证
- **可关联 Story 编号**：当需要追踪需求来源时
- **原子化**：每个独立功能点一次commit，便于回退和追溯

示例：
```
feat(submission): 增加tar系列压缩包自动解包
fix(auth): 修复gunicorn启动时数据库不初始化的问题
docs(deploy): 补充测试环境部署指南
refactor: 目录结构重构为主干开发模式(src/tests/infra)
```

---

## 文档规范

### 文档清单与位置

| 文档 | 位置 | 更新时机 |
|------|------|---------|
| PRD | `docs/02-prd-v*.md` | 需求变更时 |
| PSF流程 | `docs/03-psf-process.md` | 流程调整时 |
| PMF流程 | `docs/04-pmf-process.md` | 流程调整时 |
| 测试用例 | `docs/05-test-cases.md` | 新增功能时 |
| 测试报告 | `docs/06-test-report.md` | 每次全量测试后 |
| 迭代小结 | `docs/07-psf-sprintN-retrospective.md` | 每个Sprint结束 |
| 测试环境部署指南 | `docs/TESTING-DEPLOY.md` | 部署流程变更时 |
| 生产环境部署指南 | `infra/DEPLOY.md` | 部署流程变更时 |
| README | `README.md` | 项目概况变更时 |

### 文档原则

- **聚焦关键内容**：不追求大公司级完美，重点记录决策、结论、行动项
- **可追溯**：每个技术决策有ADR记录，每个Sprint有复盘文档
- **版本化**：重要文档带版本号和日期，旧版本保留（不覆盖）
- **中文为主**：项目文档使用中文，代码注释中英文均可
- **Sprint作为研发分解阶段**：在过程文档中体现，不用目录结构做版本管理

---

## 研发流程

### 阶段划分（Lean Startup）

1. **PSF**（当前）：问题-方案匹配验证，1周Sprint，聚焦技术验证和用户反馈
2. **PMF**（下一阶段）：产品-市场匹配验证，2周Sprint，聚焦真实部署和使用数据
3. **Scale**（未来）：规模化，持续交付

### Git 工作流（主干开发）

```
main ────●────●────●────●────  始终可部署
           \        /
            feature-xxx  临时分支（开发→测试→合入→删除）
```

- **main 分支**：始终可部署，直接推送或PR合入
- **临时分支**：开发新功能时拉取（如 `feature/ad-ldap`、`fix/upload-bug`），测试通过后合入 main 并删除
- **Sprint 不体现在分支名或目录名中**：Sprint是研发工作分解阶段，在过程文档（docs/）中记录

### Sprint 流程（Scrum）

1. **需求**：Sprint Planning，拆分Story，确认验收标准
2. **设计**：复杂功能技术方案，API定义，ADR记录
3. **开发**：编码 + 单元测试 + 每日站会
4. **测试**：全量回归（`tests/test_api.py` 88项）+ Bug修复
5. **验证**：Sprint Review，PO验收，收集反馈
6. **复盘**：Retrospective，输出迭代小结文档（`docs/07-psf-sprintN-retrospective.md`）

### 每个Sprint必须交付

- [ ] 可工作的代码（`tests/test_api.py` 全通过）
- [ ] 迭代小结文档（`docs/07-psf-sprintN-retrospective.md`）
- [ ] 测试报告（如测试有变化）
- [ ] Git 提交（原子化，清晰的commit信息，不带Sprint编号）
- [ ] 推送到 Gitea 仓库 main 分支

---

## 测试规范

### 自动化测试

- **测试脚本**：`tests/test_api.py`，使用Python标准库urllib，无额外依赖
- **测试范围**：18大类88项，覆盖所有API和核心业务流程（含合作方白名单、审批人配置）
- **运行方式**：先启动服务（`cd src && python app.py`），再 `cd tests && python test_api.py`，预期通过率100%
- **新增功能**：必须在 test_api.py 中添加对应测试用例

### 测试通过标准

- P0 测试用例 100% 通过
- 核心流程（提交→审批→摆渡→下载）端到端跑通
- 无 P0/P1 未修复 Bug
- 权限隔离验证通过

---

## 部署规范

### 双模式部署

| 模式 | DEPLOY_MODE | 存储 | 启动方式 | 适用 |
|------|-------------|------|---------|------|
| 测试环境 | `testing`（默认） | 本地磁盘 `./nas` | `python app.py`（Flask自带） | 开发/测试验证 |
| 生产环境 | `production` | NAS 挂载 | `gunicorn app:app` | 正式部署 |

切换方式：修改 `.env` 中的 `DEPLOY_MODE` 和 `NAS_ROOT`，换启动命令。代码完全不变。

### 部署脚本（infra/）

- `infra/deploy.sh`：一键部署（9步自动化），必须在Linux服务器以root运行
- `infra/verify.sh`：部署验证（88项全量测试），确认部署正确
- `infra/nginx-securetrans.conf`：Nginx反向代理配置
- `infra/securetrans.service`：systemd服务配置
- 脚本必须使用LF换行，不能有CRLF

### 生产环境要求

- Python 3.10+
- Nginx（反向代理）
- NAS挂载（staging/external/archive同文件系统，os.rename才能0拷贝）
- systemd（服务管理）
- gunicorn（WSGI服务器，不用Flask自带服务器）

---

## 安全规范

- **密码**：bcrypt哈希存储，不明文
- **密钥**：SECRET_KEY通过.env配置，不硬编码在代码中
- **权限**：后端每个管理接口必须有 `@role_required` 装饰器
- **审计**：所有关键操作（登录、提交、审批、配置变更）记录审计日志
- **文件上传**：限制大小（MAX_CONTENT_LENGTH），流式写入磁盘
- **会话**：Flask-Login，HTTPOnly cookie，SameSite=Lax

---

## 常见陷阱

1. **不要用 shutil.move 做摆渡**：跨目录时会退化为复制+删除，大文件很慢。必须用 os.rename。
2. **不要在 if __name__ == "__main__" 中初始化数据库**：gunicorn导入时不执行该块，数据库表不会创建。初始化必须在模块级别。
3. **不要把 venv 目录提交到 Git**：不同平台不兼容，部署时自动重建。
4. **不要把测试数据提交到 Git**：data/securetrans.db 和 nas/ 中的测试文件应排除，首次启动自动创建。
5. **不要在前端做权限校验**：前端只做体验优化，后端必须校验每个接口的权限。
6. **不要用 CRLF 换行保存 shell 脚本**：Linux上会报 "command not found" 错误。
7. **不要按Sprint建目录**：主干开发按功能模块组织代码（src/），Sprint在文档中体现，Git历史追溯变更。
8. **不要在commit message中强制带Sprint编号**：Sprint是管理节奏，不是代码的身份证。

---

*AGENTS.md v1.1 | 2026-08-27*
