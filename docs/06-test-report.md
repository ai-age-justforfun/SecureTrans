# SecureTrans 测试报告

> 版本：v1.5.0 | 日期：2026-08-27 | 阶段：PSF
> 测试环境：Rocky Linux 10.1 (WSL2) + Python 3.12.11 + Flask 3.0 + SQLite
> 部署模式：DEPLOY_MODE=testing（本地文件系统 + Flask 自带服务器）
> 测试工具：tests/test_api.py（Python urllib，无额外依赖）

---

## 一、测试结论

**总计 35 项测试，全部通过，通过率 100%。**

核心流程（提交→审批→摆渡→下载）端到端验证通过，os.rename 0拷贝摆渡特性在 Rocky Linux 10 ext4 文件系统上得到实际验证。

---

## 二、测试覆盖范围（13大类 35项）

| # | 类别 | 测试项 | 通过 |
|---|------|--------|------|
| 1 | 基础服务 | 健康检查、未登录访问重定向 | 2/2 |
| 2 | 认证 | admin登录、获取当前用户、错误密码拒绝 | 3/3 |
| 3 | 文件上传 | 上传PDF（匹配特征码）、上传EXE（不匹配） | 2/2 |
| 4 | 提交单创建 | 免审批自动通过、需要人工审批 | 2/2 |
| 5 | 提交单查询 | 提交单列表、提交单详情（含文件清单和审批记录） | 2/2 |
| 6 | 审批流程 | 待我审批列表、一级审批通过、二级审批通过 | 3/3 |
| 7 | 外网下载 | 已摆渡文件列表、文件流式下载 | 2/2 |
| 8 | 用户管理 | 本地用户列表、创建用户、重置密码、删除用户 | 4/4 |
| 9 | AD角色映射 | 角色映射列表、创建用户级映射、搜索AD用户（打桩） | 3/3 |
| 10 | 系统配置 | 特征码规则列表、系统配置获取、系统配置更新 | 3/3 |
| 11 | 审计与统计 | 审计日志查询、统计数据、手动触发过期清理 | 3/3 |
| 12 | 物理文件验证 | 免审批os.rename到external、审批通过os.rename到external、staging无残留、external文件可读 | 4/4 |
| 13 | 退出登录 | 退出登录、退出后访问受保护接口重定向 | 2/2 |
| | **总计** | | **35/35** |

---

## 三、os.rename 0拷贝特性验证

### 3.1 验证场景

| 场景 | 操作 | 验证结果 |
|------|------|---------|
| 免审批提交单 | 上传后立即 os.rename staging→external | ✅ 文件出现在external，staging无残留 |
| 审批通过提交单 | 二级审批通过后 os.rename staging→external | ✅ 文件出现在external，staging无残留 |
| staging清理 | 所有已完成提交单全部移走 | ✅ staging目录无已完成提交单 |
| external可读 | 摆渡后的文件可正常读取 | ✅ 文件内容完整，大小正确 |

### 3.2 性能特征

- 移动操作耗时**毫秒级**，与文件大小无关
- 不占用额外磁盘空间（同文件系统内只改目录项）
- 原子操作，不会出现半移动状态

### 3.3 前提条件

- staging/external/archive 三个目录**必须在同一个文件系统**
- 跨文件系统时 os.rename 会退化为复制+删除（性能下降）
- 部署时需通过 `df -h` 验证三个目录的 Filesystem 列相同

---

## 四、历史修复的 Bug

### BUG-001：gunicorn 启动时数据库不初始化

**现象**：使用 `python app.py` 启动正常，但使用 `gunicorn app:app` 启动后，访问任何接口报数据库表不存在。

**根因**：`init_db()` 和 `start_scheduler()` 只在 `if __name__ == "__main__":` 块中调用。gunicorn 导入模块时 `__name__` 为 `"app"`，不执行该块。

**修复**：将 `init_db()` 和 `start_scheduler()` 移到模块级别，确保任何方式导入都执行初始化。

**验证**：修复后 gunicorn 启动正常，数据库表自动创建。

### BUG-002：前端 static/ 目录为空

**现象**：登录成功后跳转首页，页面空白。

**根因**：原 static/ 目录为空，只有简陋的登录页 fallback。

**修复**：补充完整的前端 SPA，实现全部8个模块，对接所有后端API。

---

## 五、打桩部分说明（PSF 阶段，PMF 阶段替换为真实）

| 功能 | 当前实现 | PMF 阶段替换 |
|------|---------|-------------|
| AD/LDAP认证 | authenticate_ad() 返回 None（stub） | 接入 ldap3，真实LDAP认证（与sssd兼容） |
| AD用户搜索 | 返回硬编码的模拟用户 | 真实LDAP查询 |
| 存储 | 本地磁盘 ./nas/ | NAS挂载 /mnt/nas/securetrans |
| WSGI服务器 | Flask自带（testing模式） | gunicorn + systemd（production模式） |

> 打桩部分不影响核心业务流程验证。双模式部署通过 `DEPLOY_MODE` 开关切换，代码完全复用。

---

## 六、测试环境与配置

| 项目 | 值 |
|------|-----|
| 操作系统 | Rocky Linux 10.1 "Red Quartz" (WSL2) |
| 内核 | WSL2 6.6.87.2-1 |
| Python | 3.12.11 |
| Flask | 3.0.0 |
| Flask-Login | 0.6.3 |
| bcrypt | 4.1.2 |
| APScheduler | 3.10.4 |
| 数据库 | SQLite（WAL模式） |
| 部署模式 | DEPLOY_MODE=testing |
| 存储 | 本地 ext4 文件系统 ./nas/ |
| 服务地址 | http://localhost:8000 |
| 测试脚本 | tests/test_api.py（Python urllib，无额外依赖） |
| 健康检查 | status=ok, version=1.5.0, deployMode=testing |

---

## 七、后续验证计划

1. **生产模式验证**：在 WSL 中切换 `DEPLOY_MODE=production`，用 gunicorn 启动，验证生产模式兼容性
2. **大文件测试**：上传 100MB+ 文件，验证流式上传和0拷贝摆渡性能
3. **NAS模拟验证**：在 WSL 中挂载 NFS，验证跨网络文件系统的 os.rename 行为
4. **AD对接验证**：配置真实 LDAP 参数，验证 AD 用户认证（与 sssd 兼容）
5. **服务器部署验证**：在封闭数据中心 Rocky 8.10 服务器上执行 `infra/deploy.sh` 一键部署，运行 `infra/verify.sh` 全量验证

---

*文档结束 | SecureTrans 测试报告 v1.5.0 | 2026-08-27*
