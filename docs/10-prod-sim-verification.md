# SecureTrans 本地生产模拟环境验证报告

> 版本：v1.0 | 日期：2026-08-31 | 阶段：PSF → production
> 目的：在**本地 test 环境（WSL Rocky Linux）**以**生产模式（DEPLOY_MODE=production + gunicorn）**全面模拟生产环境，验证"代码可直接部署到生产"的可行性，并在部署前发现生产环境特有的问题。

---

## 一、为什么做本地生产模拟

生产环境 = 封闭数据中心 Linux 服务器（Python 3.10+ + gunicorn + NAS 挂载 + systemd + Nginx）。

- 开发（dev）与回归（test）此前一直在 **Windows / Flask 自带服务器**（testing 模式）下验证。
- **gunicorn 不支持 Windows**，多 worker 并发、模块级初始化、NAS 同文件系统 0 拷贝等**生产特性从未被验证过**。
- 在真实生产服务器上第一次跑就暴露问题，返工成本高；先在本地 WSL Rocky 里以生产模式完整走一遍，是最低成本的生产可部署性验证。

---

## 二、模拟环境构成

| 项 | 生产环境 | 本地模拟（本次） |
|----|---------|-----------------|
| OS | 封闭数据中心 Linux | **WSL Rocky Linux 10.1**（`rocky10-st`，Python 3.12.14） |
| WSGI | gunicorn 多 worker | **gunicorn 21.2.0，4 worker**（同 `start-production.sh` 参数） |
| DEPLOY_MODE | production | **production** |
| 存储 | NAS 挂载 `/mnt/nas/securetrans` | **本地目录 `/opt/securetrans/nas`**（同一 ext4 文件系统，验证 os.rename 0拷贝） |
| 数据库 | `/opt/securetrans/data` | 同路径（绝对路径，与生产一致） |
| SECRET_KEY | 随机 | 随机（secrets.token_hex(32)） |
| FLASK_DEBUG | false | **false** |
| AD | 启用（LDAP/sssd） | 关闭（本地模拟无 AD，AD 对接在真实生产启用，代码路径相同） |

**启动方式（与生产完全一致）**：
```bash
cd /opt/securetrans/src
set -a; source .env; set +a
gunicorn -b 127.0.0.1:8000 -w 4 --timeout 120 app:app
```

---

## 三、验证过程与结果

### 3.1 全量自动化回归

- 测试脚本：`tests/test_api.py`（标准库 urllib，无额外依赖）
- 运行：`cd /opt/securetrans/tests && NAS_ROOT=/opt/securetrans/nas python3 test_api.py`
- **结果：150 项测试，全部通过，通过率 100%**

覆盖 24 个大类：基础服务 / 认证 / 文件上传 / 提交单 / 审批 / 外网下载 / 用户管理 / AD 角色映射 / 合作方白名单 / 审批人配置 / 语义B自动跳过二级 / 特征码规则 / 网络面隔离（双网卡应用层兜底）/ 系统配置 / 审计统计 / 特征码全量 / 审批驳回 / 过期归档 / 修改密码 / **物理文件验证（os.rename 0拷贝）** / 外网面隔离扩展矩阵 / 本期逻辑调整 / 退出登录。

完整逐项报告见 `docs/09-prod-sim-test-report.txt`。

### 3.2 生产关键点验证

| 验证项 | 结果 |
|--------|------|
| gunicorn 多 worker 启动 | ✅ 1 master + 4 worker 正常，健康检查 `deployMode=production` |
| 数据库首次初始化（模块级 init_db） | ✅ `/opt/securetrans/data/securetrans.db` 自动创建，admin 用户、系统配置、20 条特征码模板就绪 |
| NAS 目录初始化 | ✅ staging / external / archive 自动创建 |
| 同文件系统 0 拷贝 | ✅ WSL 根文件系统为 ext4（`/dev/sdg`），测试物理验证 staging→external→archive 均走 os.rename |
| 测试后服务稳定性 | ✅ 150 项测试跑完后 gunicorn 仍健康运行 |
| external/archive 摆渡结果 | ✅ external 有已审批文件、archive 有归档/驳回文件 |

---

## 四、发现并修复的生产环境 Bug（关键发现）

### Bug：gunicorn 多 worker 并发启动时数据库初始化竞态

**现象**：首次以 gunicorn 4 worker 启动，所有 worker 启动失败，错误：
```
sqlite3.IntegrityError: UNIQUE constraint failed: local_users.username
```

**根因**：`init_db()` 在**模块级**执行（gunicorn 导入 `app:app` 时，4 个 worker 各自执行一遍）。初始管理员插入用的是 `SELECT COUNT → 若为 0 则 INSERT`：
- worker A 与 worker B 几乎同时执行 SELECT，都读到 0（此时谁都还没插入）；
- 随后 A 插入 admin 成功，B 再插入 admin → UNIQUE 冲突 → worker 启动失败。

**为什么本地开发没发现**：Windows 本地用 Flask 自带服务器（单进程），`init_db()` 只执行一次，永远不会触发该竞态。**这是只在生产模式（gunicorn 多 worker）下才暴露的问题。**

**修复**（`src/app.py`）：
1. 初始管理员改为 **`INSERT OR IGNORE`**（用户名 UNIQUE 约束冲突时忽略，幂等安全），与系统配置种子数据已有的做法一致。
2. 数据库迁移 `ALTER TABLE` 改为 **`try/except sqlite3.OperationalError` 包裹**（并发迁移时"列已存在"的冲突被忽略）。

修复后验证：清空 data/nas 全新启动 gunicorn 4 worker → 正常；150 项测试全过。

**生产部署提示**：`infra/deploy.sh` 用 gunicorn 部署时若未同步此修复，同样会启动失败。请确保部署的代码包含本次修复。

---

## 五、生产部署前核对清单（本次模拟已覆盖项）

- [x] 代码可在 Linux + gunicorn 多 worker 下启动（并发初始化 Bug 已修复）
- [x] 全量 150 项自动化测试 100% 通过
- [x] 数据库/NAS 目录首次自动初始化正确
- [x] os.rename 0拷贝摆渡在同一文件系统工作正常
- [x] 网络面隔离（双网卡应用层兜底）在 production 模式生效
- [x] 特征码全量、过期归档、审批语义B 等完整流程通过
- [ ] （真实生产才验证）NAS 挂载 / Nginx 双网卡 / systemd / AD-LDAP 对接 —— 见 `docs/09-preprod-verification.md`

---

*文档结束 | SecureTrans 本地生产模拟验证 v1.0 | 2026-08-31*
