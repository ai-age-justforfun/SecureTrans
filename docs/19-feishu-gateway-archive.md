# 飞书通知网关：归档备份与 dryrun 全盘对照（0.2.2）

> 日期：2026-11-28 ｜ 对象：`10.10.30.114` 上的 `securetrans-notify`（网关 0.2.2）
> 关联：ADR-052（零出网 + 单向网关）、ADR-055（App Secret 受控下发）、ADR-057（测试域拆除）
> 结论：**归档可复制、可离线复现；dryrun 六项对照 4 项字节级全等，2 项差异均为隔离环境参数（非代码差异），端到端真实投递成功。**

---

## 1. 归档清单

| 资产 | 位置 | 大小 | SHA256 |
|------|------|------|--------|
| 网关代码/单元/部署脚本/依赖锁/环境手册/配置模板 | 仓库 `infra/feishu-gateway/`；打包 `packages/securetrans-feishu-gateway-0.2.2.tar.gz` | 15,424 B | `7710badb…21f371` |
| 运行环境快照（venv，Python 3.11.7） | 网关机 `/opt/securetrans-notify/archive/securetrans-feishu-gateway-0.2.2-venv-py311.tar.gz` | 25,390,827 B | `28b8fa55…6e1b52` |
| 线上运行副本 | 网关机 `/opt/securetrans-notify/archive/`（同包） | — | 同上 |

仓库内新增（可审计、可 diff）：`requirements-lock.txt`（24 个包逐行 `==`）、`ENVIRONMENT.md`（环境事实 + 离线复现步骤 + SDK 版本定位）、`env/gateway.env.template`（9 键，值留空）。

---

## 2. 环境事实（与用户提问逐条对应）

| 提问 | 事实 |
|------|------|
| Python 架构 | 3.11.7（`/opt/securetrans-notify/venv`，156MB），x86_64 / Rocky 8.10 glibc 2.28 |
| 是否有 Docker | **无 docker**；宿主有 podman 4.9 但网关不使用。形态=**systemd + venv 直跑** |
| 数据库 | **无数据库**；审计为追加写 JSONL `/var/lib/securetrans-notify/notify.jsonl`（8KB） |
| SDK | `lark-oapi 1.7.3`（PyPI/官方仓库 tag 可定位），`fastapi 0.141.1`、`uvicorn 0.53.0`、`httpx 0.28.1` |
| 配置 | `/opt/securetrans-notify/.env`（600 root），9 键；App Secret 只在本机 |

---

## 3. dryrun 与全盘对照

做法：网关机新建 `/tmp/gw-dryrun`，解包归档 + 解包 venv 快照，用**独立数据目录、独立端口 18090、127.0.0.1 绑定**起第二实例（第二版沿用线上 `.env` 真实凭据，但不回显、不落盘），逐项比对。

| # | 对照项 | 线上 | dryrun | 结果 |
|---|--------|------|--------|------|
| 1 | 代码 SHA256 | `587a474d…fec244` | `587a474d…fec244` | ✅ 全等 |
| 2 | systemd 单元 SHA256 / 文本 | `168a1784…0e5f9` | 同 | ✅ 全等 |
| 3 | `pip freeze`（24 包） | 见锁文件 | 集合完全一致 | ✅ 全等 |
| 4 | `/notify` 鉴权与失败路径 | — | 无 token→401；错 token→401；非法事件→400；非法邮箱→400；上游失败→502 | ✅ 与线上同码 |
| 5 | 文件清单 | `srv/notify_app.py 20089` + `.env` + 备份 | `srv/notify_app.py 20089` + 归档附属文件 | ✅ 代码/单元一致，附属文件为归档增量 |
| 6 | `/health` | version 0.2.2 / ok / app_configured / token_configured | 同 | ⚠️ 2 项隔离差异，见下 |

`/health` 差异仅两项，均为**隔离环境参数**：

- `allow_cidrs`：线上 `10.10.30.8/32`，dryrun `127.0.0.1/32`（dryrun 只允许本机探针，属预期）；
- `contact_readable`：线上 `true`，dryrun 冷启动首查为 `null`（通讯录能力探测在首次调用后回填；不影响投递，见下条实证）。

**端到端实证**：dryrun 实例用真实凭据向 `tonyj@nexskysemi.com` 投递 `submission_pending_l1`，返回
`200 / sent=1 / failed=0 / department=软件开发部 / message_id=om_x100b7f90…408`，与线上路径同源。

---

## 4. 代码与脚本评审（本轮范围）

覆盖：`notify_app.py`（0.2.2）、`deploy-gateway.sh`、`securetrans-notify.service`、`docker-deploy.sh`、`smoke.sh`、`tests/test_api.py` 二级审批与通知组。

**通过的硬约束**：
- 源 IP 白名单 fail-closed（未配置 `NOTIFY_ALLOW_CIDRS` 一律拒绝），`request.client.host` 直取、不信任 `X-Forwarded-For`；
- 预共享 token 用 `hmac.compare_digest` 常量时间比较；`/admin/secret` 与 `/notify` 同源校验，先验凭据再原子写 `.env`（600），热重建客户端；
- 收件人上限 20、邮箱格式校验、事件白名单、`request_id` 幂等（上限 500 条 LRU 淘汰）；
- 并发投递（≤8 线程）解决多审批人串行导致业务侧超时假失败；部分失败返回 502 且业务侧不阻塞（TDD 组 25–26 已覆盖）；
- systemd 加固：`NoNewPrivileges`、`PrivateTmp`、`ProtectHome`，仅监听内网地址。

**遗留风险（不阻塞发布，已记账）**：
1. `notify.jsonl` 无轮转，长期运行会持续增长（建议 logrotate/按月切分，触发条件=单文件 >50MB 或 >90 天）；
2. `/health` 回显 `allow_cidrs`（内网拓扑最小暴露），可选脱敏；
3. `/notify` 未限制请求体大小（仅白名单源可调用，风险低）；
4. `lark.Client` **承载真实消息发送**（`im.v1.message.create`），并非“只构建不用”——SDK 不可裁剪（曾误记为全部走 `httpx`，2026-11-28 已按代码订正）；token/通讯录仍走 `httpx`。

---

## 5. 二级审批的覆盖结论（用户点名确认项）

| 维度 | 结论 | 证据 |
|------|------|------|
| 全量 TDD | **有覆盖**：配置审批人链路、一级通过进二级、二级通过摆渡、语义B 自动跳过二级、内部/合作方一级不含二级记录 | `tests/test_api.py` 10g1（908–916）、10g2（937–1008）、10g3（1024+）；组 25–26 覆盖二级待审批/终审通知事件 |
| 生产冒烟 | **按设计不覆盖**：`smoke.sh` 为只读白名单（11 项），不含任何写业务数据/审批动作 | ADR-017/053；`infra/smoke.sh` |
| 真实验收 | 一级、免审批已由用户在生产真实走通；二级仅 TDD 覆盖，生产无真实二级单 | 本轮盘点生产 `submissions`：approved 11 / downloaded 336 / rejected 2，无 `pending_approval_2` 存量 |

结论：**二级审批逻辑由全量 TDD 保障，生产冒烟不覆盖属隔离设计而非缺口**；若要生产真实验收，需一张进入二级的单据（可由二级审批人 `zhaizhigang` 处理），不写入常规冒烟。

---

## 6. 复现与回退

- 复现：见 `infra/feishu-gateway/ENVIRONMENT.md` §4（代码包 + venv 快照 + systemd 三步）；
- 回退：网关机保留 `notify_app.py.bak-20261127233230`（0.2.2 前版本）与 `.env.bak-20261127`，`systemctl restart securetrans-notify` 即回退；
- 本次未改动线上任何文件，只在 `/opt/securetrans-notify/archive/` 增加归档与 `/tmp/gw-dryrun` 增加隔离实例（已停）。

---

---

## 7. Gitea Release 存档现状（v2.7.7，2026-11-28）

- Release id `442` 共 **9 个资产**：7 个发布资产（主包 + md5 + sha256 + offline-deps + image.tar.gz + md5 + sha256）+ 2 个网关归档（`securetrans-feishu-gateway-0.2.2.tar.gz` 15,424B、`…-venv-py311.tar.gz` 25,390,827B）。
- GitHub 对应 Release id `461281228`（同一 7 个发布资产，云端构建）；网关归档不进 GitHub，只存 Gitea。
- 归档可复制性验证：本地下载回读 md5/sha256 **全部 OK**；网关侧原始文件仍在 `/opt/securetrans-notify/archive/`。

---

## 8. 飞书 SDK 版本评估与升级复盘入口（2026-11-28）

| 项 | 事实 | 来源 |
|----|------|------|
| 线上锁定 | `lark-oapi == 1.7.3`（2026-08-19）；venv 快照同版本 | `infra/feishu-gateway/requirements-lock.txt` |
| 最新稳定 | **1.9.0**（2026-11-25）；`v1.9.0` tag；wheel 7,712,542B，sha256 `0ca3bc13…83da9` | PyPI JSON / GitHub tags |
| 2.x | 仅 `2.0.0.dev0~dev4`（2026-04 预发布），无正式 2.0.0 | PyPI 版本列表 |
| 变更规模 | 17 commit / 19 文件，全在 `lark_oapi/` | GitHub compare `v1.7.3...v1.9.0` |
| 变更域 | webhook 校验令牌、动态 webhook 凭据、WebSocket 连接参数、ISV ClientAssertion、OAuth audience | 同上 |
| 依赖树 | 与 1.7.3 **完全一致**（requests / requests_toolbelt / pycryptodome / websockets / httpx） | PyPI `requires_dist` 三版对比 |
| 本网关实际用法 | 仅 `lark.Client.builder()` + `client.im.v1.message.create()`；token、通讯录走 `httpx` | `notify_app.py:65-66, 264-285, 105-130` |
| 决定 | **A 案：保持 1.7.3**，不改代码、不动 venv 快照 | 用户 2026-11-28 决策 |

**升级触发条件（满足任一）**：①官方修复 `im.v1.message.create` 缺陷或有安全公告；②需要 ISV 认证/WebSocket/webhook 收事件；③正式 2.0.0 发布并有迁移指南。

**升级复盘用的执行清单（与本次 dryrun 同口径）**：隔离实例 18090（独立 venv、`127.0.0.1`）→ 装新版 + 全量重锁 → 鉴权四路径（401/401/400/400）→ 上游不可达 502 → 真实投递 1 条（`message_id` + 部门补全）→ `pip freeze`/单元 sha256 对照 → 重打 venv 快照 → 更新 `docs/19`、`ENVIRONMENT.md`、Gitea Release 归档并回读校验。

**为什么现在不升**：新版能力（webhook/WebSocket/ISV/OAuth）我们一个都没用；`im.v1.message.create` 面无变化，升级只增加“重打 30MB venv 快照 + 重新归档”的工作量与风险。观察期内稳定优先，版本可复现性已由锁定文件 + venv 快照保证。
