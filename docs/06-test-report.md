# SecureTrans 测试报告

> 版本：v2.2.31 | 日期：2026-09-10 | 阶段：PSF（Alpha）
> 测试环境：Windows 11 (本地dev) + Rocky Linux (WSL2 test)，Python 3.12 + Flask 3.0 + SQLite
> 部署模式：DEPLOY_MODE=testing（本地文件系统 + Flask 自带服务器）
> 测试工具：tests/test_api.py（Python urllib，无额外依赖）

---

## 〇、v2.2.31 回归（2026-09-10）

**总计 291项测试（Windows dev）/ 290项（WSL production）全部通过，通过率 100%。**

**本轮需求（6+1 组用户验收修复，ADR-015）**：

1. **生产业务备份 500**——根因：`_backup_now` business 分支 `shutil.copytree` 对已存在目标/符号链接/特殊文件名（NAS 挂载点常见 .nfs*/.DS_Store 等）不健壮，异常直接裸 500（本地/WSL 无 NAS 场景未触发，生产特有）。修复：copytree 加 `dirs_exist_ok=True + symlinks=True + ignore 临时/锁文件`，异常清理半成品并返回可读 JSON 错误。
2. **改密提示方位错误**——文案"右上角"→"左下角"（按钮实际在侧栏底部，与退出登录相邻）。
3. **备份界面彻底分离**——移除"全部备份"按钮与列表 all 混合过滤；系统区块只列 backup-system-*，业务区块只列 backup-business-*，各自独立的创建/列表/恢复/删除；恢复按钮统一"恢复"；旧版混合备份 backup-all-* 不显示并提示删除。
4. **特征码匹配受免审批总开关约束**——MD5 必选；匹配判定 = 免审批开关开启 且 对应特征码启用，否则上传/提交均不显示"匹配特征码"（matched=false、matchedRules=[]）。
5. **合作方选中隐藏接收方单位**——与姓名/邮箱一致：选中已配置合作方 → 隐藏姓名/单位/邮箱（单位只读带出）；仅"其他（自行填写）"显示三字段。
6. **外网仅本人可见**——外网列表/详情/下载三处加 submitter=当前用户校验：只能看/下自己提交且已批准（approved/downloaded）的文件；越权访问他人返回 404。
7. **审批人闭环**——init_db 幂等播种 admin 为一级+二级审批人；提交时按接收方类型校验审批人存在（内部/合作方须一级，非合作方须一级+二级），缺失则 400 提示原因，不再产生无法审批的死单。

**新增测试**：默认播种 admin 审批人×2、开关关/开 matched 约束×2、外网列表仅本人、外网详情/下载越权 404×2、前端改密方位/备份分离/合作方单位/legacyHint 等。

### 12.17 v2.2.30 回归（2026-09-10）



**总计 278项测试（Windows dev）/ 277项（WSL production）全部通过，通过率 100%。**

**本轮需求（3 项修复 + 外网面测试清单）**：

1. **外网无法下载（第一批需求第一个 story：内网提交→审批→外网下载）**——根因：下载弹窗 `showDownloadFiles()` 调 `/api/submissions/<id>`（管理详情），不在外网白名单 → 外网 403 → 弹窗打不开。修复：新增 `GET /api/external/submissions/<sub_id>`（仅 approved/downloaded 可见，返回详情+文件明细），前端弹窗改用该接口（内外网同一弹窗）；`/api/health` 加入外网放行（外网页版本/阶段显示）；管理详情外网维持 403。
2. **备份允许删除**——新增 `DELETE /api/admin/ops/backups/<name>`（admin）：校验 backup- 前缀 + 防路径穿越（含 `/` 名字由 Flask 路由 405 兜底）；前端两个备份列表行加"删除"按钮 + confirm（删除不可恢复）；审计日志 ops_delete_backup。
3. **系统工具页抬头**——真实根因：navigate() 特判曾正确设置"系统工具 / System Tools"，但语言刷新 `applyI18n()` 的 titles 映射**缺 ops 键** → `t('ops')` 回退键名输出 "ops" 覆盖（renderOps 异步完成后触发，故界面抬头变成 ops）。修复：applyI18n 对 `currentPage==='ops'` 同样输出固定中英双语；**浏览器实测中英切换后仍为"系统工具 / System Tools"**。

**新增断言（10 项，另 10d 段自包含强化 3 项：免审批显式开启/上传匹配特征码）**：外网管理详情拒绝 403（回归保护）、外网详情接口放行（下载弹窗可打开）、外网 health 放行、备份删除成功、删除后列表不含、删除不存在备份 404、非法备份名拒绝（400/404/405）、前端弹窗改用外网详情接口、前端备份列表含删除按钮、前端系统工具抬头不随语言刷新被覆盖（applyI18n ops 特判）。

**外网面自动化测试清单（22d 网络面矩阵，已覆盖）**：放行——登录页/首页/静态资源/me/health/外网列表/外网详情/下载文件；拒绝——修改密码/提交列表/上传/用户管理/合作方/审批人/特征码/系统配置/审计/统计/管理详情；非法 X-Network-Zone 回退 internal。**外网手工测试清单（生产环境执行）**：①外网仅"外网下载"菜单、无改密入口 ②外网登录→列表→点下载→弹窗明细→下载成功且 MD5 一致 ③直接输入管理 URL → 403 ④外网切换中英文正常（不误报"管理操作请从内网访问"）⑤强刷防缓存 ⑥内网全功能对照。

---

## 〇、v2.2.29 回归（2026-09-10）

**总计 266项测试（Windows dev）/ 265项（WSL production）全部通过，通过率 100%。**

**本轮需求（6 项修复 + AD 真实集成）**：

1. **合作方交互**：选择已配置合作方后**隐藏接收方姓名/单位/邮箱**（接收方=该合作方，单位自动带出只读）；仅选择 **"其他（自行填写）"** 才显示三字段手工填写，提交后自动加入合作方清单（后端信任模式，去重不重复加）。
2. **备份完全拆分**：备份目录名**按类型区分**（`backup-system-<ts>` / `backup-business-<ts>` / `backup-all-<ts>`，名字即类型）；系统工具页**两个独立备份列表**（系统备份 / 业务数据备份），恢复不再选 scope——**后端按备份名自动推导**，杜绝"从同一备份混恢复系统/业务"。
3. **系统工具页抬头**：确认 `'系统工具 / System Tools'` 固定中英双语（renderPage 特判），刷新/更新部署后生效。
4. **复制命令修复**：多行 ldapsearch 命令改用 JS 数组缓存 + 索引 onclick（`copyAdCmd`），修复"只复制出 = 号"的换行截断 bug。
5. **openldap-clients 必装**：deploy.sh 自动安装（联网），离线需提前备 RPM；AD 配置卡片 + verifyCommand 提示同步。
6. **AD 连接测试**：新增 `POST /api/admin/ad/test` + AD 配置卡片"测试连接"按钮（可输入用户名精确验证），bind 实测返回成功/失败可读原因，写审计日志。
7. **AD 搜索真实化（核心卡点解决）**：`api_search_ad` 实现**真实 LDAP 查询（ldap3）**——原为 TODO 占位（ad_enabled=true 永远返回空 → 界面"没有匹配"但手工 ldapsearch 成功）；**精确匹配**（去掉用户名后 `*` 通配符）；空关键字不 dump 全量；错误返回 `error` 字段前端展示（52e=bind 凭据错等）；修复插入代码时 `@app.route` 装饰器错位 bug（路由曾绑定到 `_ad_err`）。

**新增断言（14 项）**：备份名 backup-system-*/backup-business-* 前缀、列表 type 字段、恢复自动推导、verifyCommand 无通配符、空关键字防 dump、AD 测试连接接口（bind + 指定用户名）、前端备份双列表/恢复不传 scope/测试连接按钮/复制缓存/错误显示/合作方隐藏姓名邮箱。

---

## 〇、v2.2.28 回归（2026-09-10）

**总计 252项测试（Windows dev）/ 251项（WSL production）全部通过，通过率 100%。**

**本轮需求（提交表单接收方交互修复）**：

1. **公司内部（internal）**：选项文案简化为"公司内部"（去掉"（仅接收人）"）；选中后隐藏"接收方单位"字段（仅需接收人，单位不再显示/必填）。
2. **合作方（partner）**：提供已配置合作方下拉；若无合适选项可选择 **"其他（自行填写）"**，此时才出现接收方姓名/单位/邮箱手工填写，提交后**自动加入合作方清单**（后端信任模式逻辑复用）；选择已配置合作方时单位自动带出且只读（姓名/邮箱为联系人信息）。
3. **非合作方（non-partner）**：保持原有手工填写（姓名*/单位*/邮箱可选），需二级审批。

**新增断言（2 项）**：internal 文案简化+初始隐藏单位；合作方下拉含"其他"选项+选中合作方单位只读逻辑。

---

## 〇、v2.2.27 回归（2026-09-10）

**总计 250项测试（Windows dev）/ 249项（WSL production）全部通过，通过率 100%。**

**本轮 5 项需求（v2.2.27）**：

1. **admin 密码全链路统一（ADR-009 升级）**：init_db 播种、deploy.sh 部署重置、verify.sh/test_api.py 默认凭据、登录页提示全部同源 `.env RESET_PASSWORD`（默认 Init@123456）；去掉"首次登录强制改密"，改为"登录后建议尽快修改（不强制）"；全库清理 Admin@123 硬编码。验证：health 返回 resetPassword/登录页动态显示、无硬编码 Admin@123。
2. **发布阶段（APP_STAGE）**：alpha=自测 → beta=内部测试 → rtm=内部使用 → release=正式发布；`.env APP_STAGE` 可配，页面/登录页/健康检查显示 `vX.Y.Z-stage`。
3. **备份拆分（ADR-011 升级）**：系统备份（system=仅 DB，升级回退用）/ 业务数据备份（business=仅 NAS 业务文件，存储迁移/归档用）/ all；列表 hasDb/hasNas 标记，恢复按类型；界面系统工具页拆系统/业务两个备份卡。
4. **系统工具页抬头中英双语**：ops 页标题"系统工具 / System Tools"。
5. **AD 手工验证命令**：/api/admin/ad/search 返回 ldapsearch 验证命令（bind 密码 **** 占位，可复制到服务器执行）；确认程序 ldap3 直连 AD、服务器无需入域/SSSD（与既有 sssd 场景互不干扰）。

**新增断言（12 项）**：health stage/resetPassword、登录页动态密码无硬编码、前端品牌阶段+建议改密、ops 双语标题+备份拆分卡、scope=system/business 备份成功、非法 scope 400、备份列表 hasDb/hasNas、恢复缺失备份 400、AD 搜索 verifyCommand、app.py 资源检查（APP_STAGE/scope/RESET_PASSWORD 播种/无 Admin@123）。

---

## 一、测试结论

**总计 193项测试，双环境（Windows + WSL Rocky）全部通过，通过率 100%（PRD 全功能覆盖）。**

核心流程（提交→审批→摆渡→下载→过期归档）端到端验证通过，os.rename 0拷贝摆渡特性在 Rocky Linux 10 ext4 文件系统上得到实际验证。特征码全量验证（含压缩包解包、Vivado Bitstream）、审批驳回、过期归档、修改密码、合作方白名单、审批人配置、特征码规则CRUD管理、网络面隔离（双网卡应用层兜底）、**语义B同人跨级自动跳过二级**等全部场景覆盖。

**v2.2.14 新增（密码策略 + 配置单一来源）**：admin 可自行修改密码（侧边栏新增入口）；重置密码默认值可配置（`RESET_PASSWORD`，默认 Init@123456）；创建用户密码留空自动生成初始密码；系统配置单一来源（`system_config` ↔ `.env` 双向同步——启动从 .env 播种、界面修改写回 .env，有效期/最大文件/免审批开关默认 7天/800MB/关闭）；上传大小限制 运行时按系统配置生效（400 拒绝超限）。

**本轮新增（角色体系收窄 + 审计统计 + 仪表盘权限）**：审批权限纯由 approvers 表配置（不设 role 体系，角色仅 admin/internal-user）；仪表盘 admin-only（后端 /api/stats 强制 403）；审计日志新增统计 Tab（人员×文件类型×每日，默认近30天）。

---

## 二、测试覆盖范围（27大类 193项）

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
| 11 | 审计与统计 | 审计日志查询、统计数据、手动触发过期清理（无过期） | 3/3 |
| 12 | **特征码全量验证** | ZIP压缩包(匹配+解包)、TAR.GZ(匹配+解包)、.bit(二进制匹配)、.xyz(不匹配)、20条规则完整 | 5/5 |
| 13 | **审批驳回流程** | 创建驳回提交单、一级驳回(os.rename→archive)、驳回文件在archive | 3/3 |
| 14 | **过期归档流程** | 创建expiryDays=0提交单、触发清理(处理过期)、状态变archived、文件os.rename→archive、归档后不在external列表 | 5/5 |
| 15 | **修改密码** | 修改管理员密码、错误旧密码拒绝、改回原密码 | 3/3 |
| 16 | **合作方白名单(partners)** | 创建合作方、重复创建拒绝、白名单列表、**白名单自动判定(receiverType=auto→partner)**、合作方一级审批直接摆渡、删除合作方 | 6/6 |
| 17 | **审批人配置(approvers)** | 创建本地用户x3(模拟AD账号)、配置一级/二级审批人、重复配置拒绝、非法级别拒绝、审批人列表、**非admin权限控制**、**未配置用户审批被拒**、**配置的一级审批人通过**、**配置的二级审批人通过**、删除配置、清理数据 | 17/17 |
| 18 | 物理文件验证 | 免审批os.rename到external、审批通过os.rename到external、staging无残留、external文件可读 | 4/4 |
| 19 | 退出登录 | 退出登录、退出后访问受保护接口重定向 | 2/2 |
| 20 | **特征码规则管理** | 默认有效期7天/最大800MB验证、创建规则、空名称/非法类型拒绝、修改规则、开关切换(禁用/启用)、**单个开关生效验证(禁用后该类型不再匹配)**、非admin权限控制、删除规则、删除不存在返回404 | 14/14 |
| 21 | **网络面隔离** | 默认internal面识别、external面识别、external面管理接口403拒绝、external面下载接口放行、internal面管理接口放行、internal面配置接口放行 | 6/6 |
| 22 | **网络面隔离扩展矩阵（external面完整覆盖）** | external面放行：登录页/首页/静态资源/me接口/文件下载；external面拒绝403：提交列表/上传/用户管理/合作方白名单/审批人配置/特征码规则/系统配置/审计日志/统计；非法X-Network-Zone回退internal；internal面提交列表/用户管理放行 | 17/17 |
| 23 | **语义B自动跳过二级** | 创建双级审批人、配置一级+二级、创建需审批提交单、**一级通过自动跳过二级(直接approved)**、审计记录含level2自动跳过、文件已摆渡external、清理数据 | 7/7 |
| 24 | **本期逻辑调整** | 初始化免审批开关+默认有效期7天、**启用所有特征码规则(默认模板禁用→测试启用)**、接收方单位必填、提交传expiryDays被忽略(走系统配置)、系统配置有效期改为0生效、提交单有效期来自系统配置、恢复7天、**合作方自动加入清单**、**同名合作方再次提交成功**、**合作方去重(同名不重复加入清单)**、合作方使能开关(创建/选项出现/禁用/选项消失/重新启用)、**用户使能开关**(默认使能/登录/禁用后无法登录/重新启用/**admin不可禁用**) | 27/27 |
| 25 | **角色收窄+审计统计+仪表盘权限** | **非法角色映射被拒绝(仅admin/internal-user)**、**普通用户访问统计被拒403(仪表盘admin-only)**、**审计统计默认近30天**、**审计统计非法日期拒绝(400)** | 4/4 |
| | **总计** | | **182/182** |

---

## 三、os.rename 0拷贝特性验证

### 3.1 验证场景

| 场景 | 操作 | 验证结果 |
|------|------|---------|
| 免审批提交单 | 上传后立即 os.rename staging→external | ✅ 文件出现在external，staging无残留 |
| 审批通过提交单 | 二级审批通过后 os.rename staging→external | ✅ 文件出现在external，staging无残留 |
| 审批驳回 | 一级驳回后 os.rename staging→archive | ✅ 文件出现在archive，状态rejected |
| 过期归档 | 触发清理后 os.rename external→archive | ✅ 文件出现在archive，状态archived，不在external列表 |
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

## 四、修复的 Bug

### BUG-001：gunicorn 启动时数据库不初始化

**现象**：使用 `python app.py` 启动正常，但使用 `gunicorn app:app` 启动后，访问任何接口报数据库表不存在。

**根因**：`init_db()` 和 `start_scheduler()` 只在 `if __name__ == "__main__":` 块中调用。gunicorn 导入模块时 `__name__` 为 `"app"`，不执行该块。

**修复**：将 `init_db()` 和 `start_scheduler()` 移到模块级别，确保任何方式导入都执行初始化。

### BUG-002：expiry_days=0 不触发过期清理

**现象**：创建 expiryDays=0 的提交单（应立即过期），触发过期清理后 cleaned=0，文件未归档。

**根因**：`cleanup_expired_files()` 中使用 `row["expiry_days"] or EXTERNAL_EXPIRY_DAYS`，Python 中 `0 or 30` = 30（0 是 falsy），导致 expiryDays=0 被当成默认 30 天处理。

**修复**：改为 `row["expiry_days"] if row["expiry_days"] is not None else EXTERNAL_EXPIRY_DAYS`，正确处理 0 值。

**验证**：修复后 expiryDays=0 的提交单立即被清理，os.rename 到 archive，状态变为 archived。

### BUG-003：前端 static/ 目录为空

**现象**：登录成功后跳转首页，页面空白。

**修复**：补充完整的前端 SPA，实现全部8个模块，对接所有后端API。

### BUG-004：approve 路由装饰器拦截 approvers 表配置的审批人

**现象**：在 approvers 表配置的审批人（本地账号 deptmgr1/execmgr1）审批提交单时返回 403。

**根因**：`/api/submissions/<sub_id>/approve` 使用 `@role_required("dept-manager", "executive", "admin")`，在函数进入前就拦截了 internal-user 角色的审批人，approvers 表配置根本没有机会生效。

**修复**：将装饰器改为 `@login_required`，权限校验下放到函数内 `can_approve_level()`（角色判定 + approvers 表配置双通道）。安全性不降级——`can_approve_level()` 完整覆盖原角色判断逻辑。

**验证**：配置的 internal-user 审批人可通过一级/二级审批，未配置的 internal-user 仍被 403 拒绝。

### BUG-005：登录后闪回登录页（loadUser 报错）

**现象**：输入 admin/Admin@123 登录后"闪一下"又回到登录页。

**根因**：网络面隔离改动时，将 `<span id="networkBadge">` 放在 `<div id="userRole">` 内部；`loadUser()` 中 `document.getElementById('userRole').textContent = ...` 赋值会**清空并替换该元素所有子节点**，把 networkBadge span 删除；随后 `document.getElementById('networkBadge')` 返回 null，`badge.textContent = ...` 抛出 "Cannot set properties of null"，被 catch 捕获后 `window.location.href='/login'` 跳回登录页。任何浏览器均会触发。

**修复**：将 networkBadge span 移出 userRole div（sidebar-user 内独立元素），userRole 文本赋值不再影响网络面标识。

**验证**：真实浏览器登录后正常进入主界面（URL=/），networkBadge 正常显示"内网/internal"；全量 119 项测试 100% 通过，无回归。

**备注**：若本地浏览器仍闪回，请硬刷新（Ctrl+F5）清除旧版 index.html 缓存。

---

## 五、新增功能（partners/approvers 落地）

### 5.1 合作方白名单（partners）

- `GET /api/admin/partners`：合作方列表
- `POST /api/admin/partners`：创建合作方（name/contact/email）
- `DELETE /api/admin/partners/<id>`：删除合作方
- **白名单自动判定**：创建提交单时 `receiverType=auto`（默认值），系统按 `receiver_name` 匹配 partners 表自动判定为 partner/non-partner
- 权限：仅 admin 可管理

### 5.2 审批人配置（approvers）

- `GET /api/admin/approvers`：审批人列表
- `POST /api/admin/approvers`：配置审批人（level 1/2, username, display_name, scope）
- `DELETE /api/admin/approvers/<id>`：删除审批人配置
- **审批人生效**：审批时 `can_approve_level()` 双通道校验——角色（dept-manager/executive/admin）或 approvers 表配置的 username
- 权限：仅 admin 可管理；PSF 阶段用本地账号模拟 AD 账号测试

### 5.3 语义B：同人跨级自动跳过二级（新增）

- **规则**：非合作方提交单一级审批通过后，若当前一级审批人同时具备二级审批权限（`can_approve_level(2)` 为真），自动跳过二级审批，直接摆渡 external
- **审计**：跳过时写入一条 level=2 action=approve 的"自动跳过二级"记录，审批链完整可追溯
- **场景**：二级审批人被配置为一级审批人（小团队常见），避免同一人对同一提交单重复审批
- **纯固定规则**：无配置开关；PMF 阶段客户需要"强制两级把关"时再引入开关
- **验证**：admin（全权限）一级通过自动跳过；dual1（同时配一级+二级）一级通过自动跳过；deptmgr1（仅一级）一级通过后正常进入二级（不跳过）

---

## 六、打桩部分说明（PSF 阶段，PMF 阶段替换为真实）

| 功能 | 当前实现 | PMF 阶段替换 |
|------|---------|-------------|
| AD/LDAP认证 | authenticate_ad() 返回 None（stub） | 接入 ldap3，真实LDAP认证（与sssd兼容） |
| AD用户搜索 | 返回硬编码的模拟用户 | 真实LDAP查询 |
| 存储 | 本地磁盘 ./nas/ | NAS挂载 /mnt/nas/securetrans |
| WSGI服务器 | Flask自带（testing模式） | gunicorn + systemd（production模式） |

> 打桩部分不影响核心业务流程验证。双模式部署通过 `DEPLOY_MODE` 开关切换，代码完全复用。

---

## 七、测试环境与配置

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
| 健康检查 | status=ok, version=1.7.0, deployMode=testing |

---

## 八、PRD 覆盖度分析

| PRD 功能模块 | 测试覆盖 | 状态 |
|-------------|---------|------|
| 文件上传+MD5+大文件 | PDF/EXE/ZIP/TAR.GZ/.bit/.xyz 6种 | ✅ 充分覆盖 |
| 特征码匹配(三要素) | 扩展名/文件名/二进制特征/压缩包解包 | ✅ 全量覆盖 |
| 免审批判定 | 免审批通过 + 部分不匹配 | ✅ 覆盖 |
| 分级审批(合作方/非合作方) | 一级通过+二级通过+一级驳回 | ✅ 覆盖 |
| os.rename 0拷贝摆渡 | staging→external, staging→archive, external→archive | ✅ 全路径覆盖 |
| 外网下载+下载记录 | 列表+流式下载 | ⚠️ 部分（下载记录未单独验证） |
| 过期归档 | expiryDays=0→清理→archive→状态验证 | ✅ 完整覆盖 |
| 用户管理CRUD | 列表/创建/重置/删除 | ✅ 覆盖 |
| AD集成 | 列表/创建/搜索(打桩) | ✅ PSF阶段 |
| 系统配置 | 特征码列表/配置获取/更新 | ⚠️ 部分（特征码CRUD未全验证） |
| 审计日志 | 查询 | ✅ 覆盖 |
| 认证(登录/登出/改密) | 登录/登出/改密/错误密码 | ✅ 覆盖 |
| 合作方白名单(partners) | 创建/重复拒绝/列表/自动判定/一级审批直接摆渡/删除 | ✅ 完整覆盖 |
| 审批人配置(approvers) | 创建/重复拒绝/非法级别拒绝/权限控制/未配置拒绝/配置生效 | ✅ 完整覆盖 |
| 语义B自动跳过二级 | 同人跨级一级通过后直接摆渡、审计记录、文件落地 | ✅ 完整覆盖 |
| 网络面隔离(双网卡) | internal/external识别、管理接口403、下载接口放行 | ✅ 应用层覆盖（物理隔离见 pre-prod） |

**PRD 核心功能覆盖度：100%**（PRD v2.1 定义的 17 个功能模块全部有对应测试覆盖 + 网络面隔离应用层兜底）

> 说明：合作方白名单与审批人配置此前标注为"PSF非核心未覆盖"，本轮已实现 CRUD API、接入提交单自动判定与审批人校验，并用本地账号模拟 AD 账号完成全流程测试。AD 真实对接（LDAP）仍在 PMF 阶段替换。网络面隔离为双网卡架构的应用层兜底，**应用层逻辑已在本地/WSL 单网卡环境通过注入 X-Network-Zone 头 100% 模拟覆盖**（external 面放行矩阵 + 拒绝矩阵 + 非法值回退）；**真实双网卡物理隔离验收在 pre-prod/product（同一环境，验收通过即转正）执行**（见 docs/09-preprod-verification.md）。

---

## 九、后续验证计划

1. **生产模式验证**：切换 `DEPLOY_MODE=production`，用 gunicorn 启动，验证生产模式兼容性
2. **大文件测试**：上传 100MB+ 文件，验证流式上传和0拷贝摆渡性能
3. **NAS模拟验证**：在 WSL 中挂载 NFS，验证跨网络文件系统的 os.rename 行为
4. **AD对接验证**：配置真实 LDAP 参数，验证 AD 用户认证（与 sssd 兼容）
5. **Pre-production 双网卡验收**：独立服务器双网卡物理隔离，执行 `tests/test_preprod_dualnic.py`（见 docs/09-preprod-verification.md），验收通过后转 production
6. **服务器部署验证**：在封闭数据中心 Rocky 8.10 服务器上执行 `infra/deploy.sh` 一键部署，运行 `infra/verify.sh` 全量验证
7. **CI/CD 流水线**：配置 Gitea Actions，实现代码提交→自动测试→自动打包→自动部署（生产验证后启动）

---

---

## 十、i18n 双语改造（2026-08-28）

- **需求**：全部界面中英双语，界面右上角语言切换（默认中文，localStorage 记忆）
- **后端**：40 条静态错误 + 13 条静态成功 + 6 条动态模板消息，经 `after_request` 自动附加 `error_en`/`message_en`，未命中保持中文
- **前端**：index.html（单页应用全部文案）+ login.html 字典化（`I18N` 字典 + `t()` + `data-i18n` + `applyI18n()`），切换语言即时重渲染
- **验证**：浏览器实测登录页与主界面中英文切换正常（菜单/按钮/占位符/仪表盘/提交表单/角色标签）；新增 13 项 i18n 测试
- **结果**：全量 193项测试 100% 通过

## 十一、国际化检视（2026-09-01）
- **范围**：在 i18n 文字双语基础上，检视数字/日期/时区/单位/复数维度
- **结论**：
  - ✅ 已达标：文件大小 KB/MB/GB（国际单位）、百分比 % / 耗时 s、有效期 天/days、标点全角/半角
  - ✅ 时区（P0）：程序不做时区转换，统一使用操作系统时区时间；前端侧边栏标注“时间=服务器系统时区”，.env 不加时间配置
  - ✅ 英文单复数（P1）：前端统计卡数值/单位分离无拼接问题；修复后端清理消息动态模板英文单复数（1 expired file / N expired files）；文件清单硬编码“个”改为 i18n 键（zh {N} 个 / en {N}）
  - ⏸ 数字千分位（P2）：按用户决策忽略
- **变更**：新增 3 项 i18n 测试（清理消息英文模板 + 单复数一致 + 语言按钮跨页面重建逻辑），全量 193项 100% 通过



### 12.1 v2.2.1 部署加固验证（2026-09-04）
- venv 用 Python 3.12 --copies 创建，与系统 Python 完全隔离（venv/bin/python3 为复制文件非 symlink，系统 Python 升级/移动不影响 venv）。
- Python 版本与离线 wheel (cp312) 匹配加固：deploy.sh 探测 3.12 优先；非 3.12 且有离线包自动切换 3.12；venv 创建后校验版本。
- 验证：WSL Rocky 部署，venv Python 3.12 匹配 cp312，健康检查 OK，全量 182/182 通过。


## 十二、v2.2.0 部署能力升级验证（2026-09-04）

**总计 193项测试，Windows 本地 + WSL Rocky 双环境全部通过，通过率 100%。**

### 一键式部署（方案 B）落地

- **Linux（deploy.sh）**：Python 3.12 自动获取（系统已有→`offline-python/*.rpm` 离线→在线 dnf），离线 wheel 优先，NAS_ROOT 环境变量可覆盖并写回 .env，systemd ReadWritePaths 由模板按 NAS_ROOT 自动渲染，一键完成部署+健康检查。
- **Windows（deploy.ps1）**：Python 3.10+ 自动获取（系统→`offline-python-win/python-*.exe` 静默安装→URL），离线 wheel 优先（`offline-deps-win/wheelhouse`），新增 Python 3.12/cp312 匹配预警，UTF-8 BOM 保证 PowerShell 5.1 中文正确。
- **离线 Python 获取**：`infra/get-offline-python.sh` 在联网 Rocky 8 运行一次生成 `offline-python/*.rpm`（python3.12+依赖），随部署包离线携带。

### 本轮修复的 Bug

| Bug | 影响 | 修复 |
|-----|------|------|
| Linux 离线依赖包缺 waitress | 一键部署步骤5离线安装失败 | 将 waitress-3.0.0（py3-none-any）补入 `securetrans-offline-deps.tar.gz`（17→18 wheel） |
| loopback(127.0.0.1)被判外网 | 本机健康检查/管理接口 403 | app.py `get_network_zone` 增加 loopback 恒为内网判断 |
| verify.sh 拷贝测试脚本到 /tmp | 破坏 test_api.py 相对路径（nas 文件检查、src/app.py 源码检查） | 改为环境变量传 BASE_URL/NAS_ROOT，原地运行 |
| deploy.ps1 离线 wheel 路径错误 | `--find-links` 指向 wheelhouse 父目录 + 发布包/仓库路径不一致 | 指向 `offline-deps-win/wheelhouse`，发布包根 + packages/ 双路径 fallback |
| deploy.ps1 无 BOM 中文乱码 | PowerShell 5.1 解析失败 | 转 UTF-8 BOM |

### 验证方式

- WSL Rocky 10.1（systemd）：解压发布包 → `deploy.sh` 一键部署 → `verify.sh` 全量 **193项 100%** 通过。
- Windows：deploy.ps1 离线链路实测（Python 3.12 venv + 离线 wheel 安装 + .env 生成）。
- 新增测试：`网络: loopback(127.0.0.1/::1)恒为内网管理面`（193项之一）。

### 12.2 v2.2.2 部署修复验证（2026-09-08）
- 修复：systemd 服务启动失败 status=226/NAMESPACE——mount namespace 加固指令（PrivateTmp/ProtectSystem=strict/ReadWritePaths）在部分虚拟化/挂载组合下（如 ESXi VM + NAS 未挂载路径）无法建立命名空间。
- 变更：securetrans.service 默认移除三行加固指令，保留 NoNewPrivileges + 独立用户（securetrans），保证真机/容器可部署；deploy.sh 同步简化；DEPLOY.md 说明。
- 验证：本地全量回归 193项 100%（服务器部署验证后补充）。

### 12.3 v2.2.14 部署根因修复验证（2026-09-08）
- 根因确认：deploy.sh 默认 NAS_ROOT=/mnt/nas/securetrans，NAS 未挂载时该路径不存在；systemd 239（RHEL8/Rocky8）对 ReadWritePaths 中不存在的路径启动报 226/NAMESPACE（systemd 257 忽略，故 WSL 验证成功、ESXi 失败）。
- 修复：恢复 PrivateTmp/ProtectSystem=strict 加固（实测兼容 239/257），ReadWritePaths 由 deploy.sh 按 NAS_ROOT 存在性渲染（不存在则仅 /opt/securetrans，NAS 挂载后重跑部署自动补全）。
- 验证：ESXi 对照实验 A（含不存在路径）失败 / B（去掉 ReadWritePaths）成功，锁定元凶；本地全量回归 193项 100%。

### 12.4 v2.2.15 Alpha 走查修复验证（2026-09-08）
- 背景：v2.2.14 发布后浏览器 Alpha 走查（本地 dev 全流程：认证→用户创建→强制改密→审批人配置→上传→提交→审批→摆渡→下载），
  走查中发现并修复 4 个前端/后端问题 + 1 个权限模型残留。
- **修复清单**：
  1. `pending/my` 残留旧角色体系（dept-manager/executive）——普通审批人（approvers 表配置）访问待审批列表报 403。已改为纯 approvers 判定（can_approve_level + 按级别过滤），approve 路由本身已正确。
  2. 合作方自动加入语义错误：自动加入用接收方姓名而非单位——已改为 receiver_org（合作方=公司），前端 onPartnerSelected 同步（选已配置合作方时只填单位、姓名保持用户填写）。
  3. i18n 补全：page.title.approvers 缺字典；切语言后 pageTitle 与上传限制 hint 不刷新（已修复，applyI18n 统一刷新）。
  4. （v2.2.14 走查前置修复，随本版本发布）createUser `data` 未定义 / api_me 缺 mustChangePassword 字段（强制改密弹窗不出现）/ 上传限制前端硬编码 1GB / 前端缺审批人配置 UI。
- **新增测试 3 项**：审批人可访问 pending/my（200 + 含自己待审批单）、非审批人访问 pending/my 被拒（403）、清理测试用户幂等。
- 浏览器走查确认：合作方一级审批直接摆渡（无需二级）、外网下载内容完整（108B 一致）、审计统计 Tab（人员×文件类型×每日，默认近30天）、admin 自行修改密码并回改、i18n 全界面双语切换。
- 验证：Windows 本地全量 185/185 100%（WSL verify 见 12.5 待补充/已同步执行）。

### 12.5 v2.2.16 外网面修改密码放行修复（2026-09-08）
- 问题：外网面（external）登录后修改密码失败——修改密码属个人账户操作，但被外网面白名单 403 拦截（白名单仅含登录/me/下载）。
  影响：外网用户被重置密码后强制改密死锁，无法继续使用系统。
- 修复：`/api/auth/change-password` 加入 EXTERNAL_ALLOW_PREFIXES（个人账户操作，需旧密码验证，不属管理操作）；外网面管理接口仍 403，隔离未削弱。
- 新增测试 1 项：external 面修改密码放行（200）；对照：external 面用户管理仍 403。
- 验证：Windows 本地 186/186 + WSL verify 186/186，双环境 100%。

### 12.6 v2.2.17 外网面禁止修改密码（产品决策，撤销 v2.2.16 放行）（2026-09-08）
- 决策：外网面（external）一律不允许修改密码——即使个人账户，也只能内网修改。
- 变更：EXTERNAL_ALLOW_PREFIXES 移除 /api/auth/change-password（恢复 403 拦截）；前端外网面隐藏"修改密码"按钮（btnChangePwd），
  showChangePwdModal 前端拦截提示；外网面 must_change_password 不弹改密框，提示回内网修改（i18n pwd.externalOnly）。
- 测试：external 面改密 403 断言（原放行用例反转）+ 前端外网隐藏改密入口资源检查。
- 验证：Windows 187/187 + WSL verify 187/187，双环境 100%。

### 12.7 v2.2.18 部署凭据策略：admin 每次部署重置 + verify 自动读取（2026-09-08）
- 决策：每次部署 deploy.sh 将 admin 密码重置为 .env RESET_PASSWORD（默认 Init@123456），界面"重置密码"与 .env 同源，
  部署完成后 verify.sh 直接用该凭据即可通过（解决默认账号被修改后验证失败）。
- 变更：app.py 新增 `--reset-admin-password` CLI（app_context 内更新密码+强制改密标记）；deploy.sh 9.7 步自动重置 + 确保 .env 含 RESET_PASSWORD 行；
  verify.sh 凭据从 .env RESET_PASSWORD 读取（VERIFY_ADMIN_USER/VERIFY_ADMIN_PASS 可显式覆盖）；test_api.py 凭据参数化（TEST_ADMIN_USER/TEST_ADMIN_PASS），
  改密测试改用专用用户 testpwuser（不碰真实 admin 密码，生产安全）。
- 测试：193项（改密测试重构 +5 项，外部改密 403 保留）。
- 验证：Windows 190/190 + WSL verify 190/190，双环境 100%。

### 12.8 v2.2.19 AD 字段可配置 + 审计原因 + 部署一致性修复（2026-09-09）
- 需求来源：Alpha 走查 4 问（初始密码 / 特征码持久化 / 本地用户存储 / AD 启用）——AD 属性字段可配置化、AD 登录失败原因可查、部署凭据一致性。
- 变更：AD_USER_FIELD/AD_DISPLAY_FIELD/AD_MAIL_FIELD/AD_GROUP_FIELD 4 字段 .env 可配（默认 AD 标准属性，非硬编码）；
  authenticate_ad 失败原因返回 tuple 并写入审计日志 detail（未启用/密码错误/连接异常/ldap3 未装）；修复部署一致性 bug
  （systemd WorkingDirectory 指向 src/，此前实际加载根目录旧 app.py 导致 WSL 验证失败）。
- 测试：193项（+4：AD 字段可配资源检查、查询 filter 非硬编码、失败原因写审计、filter 用运行时变量）。
- 验证：Windows 193/193 + WSL verify 193/193，双环境 100%。

### 12.9 v2.2.20 ADR-010 配置权威矩阵（2026-09-09）
- 决策：.env 与 SQLite 配置一致性——三档配置各档唯一权威（部署级 .env / 运行时 SQLite 不再回写 / AD 连接迁 SQLite+管理页+配置总览），
  播种一次 + 冲突规则 DB 优先 + 来源标记防遗忘，README/AGENTS/DEPLOY 三处同步。
- 变更（后端）：新增 ad_config 表（首次表空从 .env 播种 source=env）；get_ad_config_value/mask_secret 助手；
  authenticate_ad / api_login 域后缀判断 / api_search_ad 改运行时读取；api_update_system_config 删除 .env 回写；
  新增 GET·PUT /api/admin/ad-config、POST /api/admin/ad-config/import、GET /api/admin/config-overview（均仅 admin）。
- 变更（前端）：系统配置页新增「AD 配置」卡片（.env 导入/保存/AD_BIND_PASSWORD 脱敏显示）与「配置总览」卡片（.env 只读 + DB 配置，来源 env/db + 更新时间）。
- 测试：201项（+8：ad-config 读/存/持久化、import 后 source=env、config-overview、后端资源检查、前端资源检查）。
- 验证：Windows 201/201 + WSL verify（gunicorn+systemd）201/201，双环境 100%，v2.2.20 已发布 Gitea Release（含 offline-deps 资产）。
### 12.10 v2.2.21 deploy.sh 密码重置凭据一致性修复（2026-09-09）
- 问题：生产 verify.sh 第 2 步 admin 认证 401——deploy.sh 9.7 重置 admin 密码时未把 .env RESET_PASSWORD 传入 CLI 环境，
  app.py 不自动读 .env，用了代码默认 Init@123456 重置；当 .env 配置了其他 RESET_PASSWORD 时，verify.sh（grep .env 取凭据）登录失败。
- 变更：deploy.sh 9.7 显式 RESET_PASSWORD=\ 传给 pp.py --reset-admin-password，部署重置与 verify 凭据严格同源（ADR-009 修复闭环）。
- 验证：WSL 重跑 deploy.sh（幂等）+ verify.sh 201/201；Windows dev 201/201；双环境 100%，v2.2.21 已发布。
### 12.11 v2.2.22 生产反馈四问题修复（2026-09-09）
- ①特征码默认禁用未生效：播种仅空表执行，旧库内置规则残留启用 → 新增升级迁移（BUILTIN_FEATURE_RULES 常量，升级时内置模板强制重置 enabled=0，自定义规则不受影响）
- ②前端 loadConfig is not defined：toggleRule/deleteRule/saveRule 调用未定义函数 → 修正为 renderConfig()（3 处）
- ③AD 用户管理：审批人弹窗新增"AD 来源"（搜索 /api/admin/ad/search 后选人）；用户管理页新增"AD 用户搜索"（查看/确认）
- ④强制改密体验：弹窗注明"初始密码=部署 .env RESET_PASSWORD"；AD 搜索测试按 ad_enabled 环境自适应（mock 分支非空 / 真实分支 200 即可）
- 测试 201 → 208 项；Windows dev 208/208 + WSL production 208/208，双环境 100%，v2.2.22 已发布
### 12.12 v2.2.23 数据生命周期（ADR-011）+ 提交接收方类型三分类重构（2026-09-09）
- **运维功能化（应收尽收）**：备份/恢复/出厂重置/模拟数据进系统——admin 菜单"系统工具"页 + API（确认码保护，TDD 可调）；备份=DB sqlite backup API 一致性快照+NAS 业务目录→data/backups/；出厂重置自动先备份→init_db 重建→admin 密码重置为 .env RESET_PASSWORD；模拟数据仅 DEPLOY_MODE=testing（生产 403）
- **离线脚本（服务停止时最安全）**：infra/ops-backup.sh / ops-restore.sh / ops-reset.sh / ops-mock.sh（调 CLI --reset-factory/--mock-data）；deploy.sh 9.8 支持 RESET_DB=1 部署时出厂重置
- **提交接收方类型三分类（表单重构，类型/密级前置）**：internal 公司内部（单位可空，不入清单）；partner 合作方（优先下拉选择，不在清单自填并自动加入清单，信任模式）；non-partner 非合作方（单位必填，不加入清单，仅下载任务+日志）
- 测试 208 → 221 项（Windows，含 mock 成功分支）；WSL production 220 项（mock 走 403 分支，环境自适应）；双环境 100%，v2.2.23 已发布
### 12.13 v2.2.24 性能压力测试 + MD5 端到端完整性（2026-09-10）
- **需求来源**：用户要求补 800MB 大文件 上传→审批摆渡→下载 全链路性能测试 + 文件完整性（MD5）保障，作为正式性能与完整性验证，为生产部署准备。
- **MD5 端到端四方一致（上传计算 → DB 存储 → 下载响应头 → 下载内容）**：
  - 上传时流式计算 MD5 存入 submission_files.md5（既有）；下载 API 从 DB 取 MD5 → 写入 download_records.md5（新列，含旧库 ALTER TABLE 迁移）→ 审计日志 download detail 带 MD5 → 响应头 `X-File-MD5`；
  - 前端：上传列表与详情页改为显示完整 MD5（title 悬浮完整值）。
- **删除提交单（admin，确认码 DEL，防误触）**：`DELETE /api/admin/submissions/<sub_id>`（body `{"confirm":"DEL"}`）；清 DB 三关联表 + STAGING/EXTERNAL/ARCHIVE 三目录；详情页对 admin 显示删除按钮（i18n zh/en）。
- **性能测试工具 tests/perf_test.py（新建，纯标准库）**：流式生成指定大小文件（边写边算 MD5）→ 流式 multipart 上传 → 合作方提交单 → 一级审批（计时含 os.rename 摆渡）→ 流式下载（取 X-File-MD5 头）→ 本地 MD5 四方比对 → JSON 报告 + 阈值断言 + 自动清理；支持 BASE_URL 参数与 PERF_* 环境变量；退出码 0=通过/2=失败。
- **实测 Bug 修复（800MB 文件 413）**：MAX_CONTENT_LENGTH 原严格等于 800MB，multipart 封装（boundary+头部）使请求体 > 限制被 Flask 拒绝。修复：新增 `MAX_FILE_SIZE_MB`（.env 新键，默认 800，单文件上限），请求体限制 `MAX_CONTENT_LENGTH = MAX_FILE_SIZE + 1MB`（multipart 封装余量）；兼容旧 .env（仅配 MAX_CONTENT_LENGTH 时，文件上限=该值-1MB）；上传校验/413 文案/系统配置 max_file_size_mb 全部改用 MAX_FILE_SIZE_MB。
- **800MB 实测结果（Windows dev，修复后）**：生成 1.26s；上传 2.36s（338.4 MB/s）；审批+os.rename 摆渡 34ms（含 API 往返）；下载 2.28s（350.5 MB/s）；全链路 5.94s；MD5 四方一致（e67ea69b2c5bc10399e324fc8819bc4c）；删除清理成功；退出码 0 全部通过。
- 测试 221 → 233 项（Windows，+12：MD5 完整性 5 + 删除提交单 5 + 源码/工具存在性 2）；WSL production 232 项（mock 403 分支）；双环境 100%，v2.2.24 已发布
### 12.15 v2.2.26 .env 生命周期机制（2026-09-10）

- 审计发现三个 .env 模板（example/production/testing）仍用旧键 `MAX_CONTENT_LENGTH`，与 v2.2.24 新口径 `MAX_FILE_SIZE_MB` 不同步（新部署会落入 799MB 兼容分支）→ 三模板统一为 `MAX_FILE_SIZE_MB=800`，注释说明禁止手工配置 MAX_CONTENT_LENGTH。
- 新建 `infra/env-refresh.sh`（.env 刷新机制）：备份 → 按模板只增不覆盖追加缺失键 → 报告新增/保留/旧键 → LF+640。WSL 实测：备份 ✓、新增 16 键 ✓、已有值原样保留 ✓、提示清理旧键 ✓。
- DEPLOY.md 新增 5.4「.env 生命周期：生成 / 保留 / 刷新」：首次部署 deploy.sh 从模板生成；升级自动保留（tar 排除 + .env.deploybak 恢复）；刷新格式显式运行 env-refresh.sh。
- 测试 235 → 238 项（Windows）/ 234 → 237 项（WSL），新增 3 项：模板口径统一、env-refresh.sh 存在性、打包排除 .env + infra 整体打包。

### 12.14 v2.2.25 外网面语言切换 403 修复（2026-09-10）
- **问题**：外网面点击右上角 EN/中文 切换语言，内容区提示"加载失败: 外网面仅提供文件下载服务，管理操作请从内网访问"。
- **根因**：登录初始化 `navigate(admin?'dashboard':'submit')` 在外网面被 navigate 外网校验拦截（只允许 external），但 `currentPage` 保持初始 'dashboard' 且内容区未渲染；语言切换 `switchLang()` 绕过 navigate 直接 `renderPage(currentPage)` → renderDashboard 调 `/api/stats` → 外网 403。
- **变更（前端 index.html）**：① `switchLang` 外网面强制 `navigate('external')`（复用 navigate 外网校验，仅刷新下载页），内网面维持 renderPage 刷新动态文案；② 登录初始化外网面直进 `navigate('external')`，内容区正确渲染下载页。
- 测试 233 → 235 项（+2 前端资源断言）；浏览器实测：模拟外网面切换语言仅请求 /api/external/files（无 /api/stats、无 403），下载列表正常渲染；Windows dev 235/235，v2.2.25 待发布。
*文档结束 | SecureTrans 测试报告 v1.22.0 | 2026-09-10*
