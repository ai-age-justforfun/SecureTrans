# 飞书通知网关：运行环境与离线复现手册

> 版本：网关 `0.2.2` ｜ 盘点日期：2026-11-28 ｜ 主机：`10.10.30.114`（`feishu-sdk-server-securetrans`）
> 关联：ADR-052（关键服务器零出网 + 单向通知网关）、ADR-055（App Secret 受控下发）、ADR-057（测试域拆除）
> 本文只写环境事实与复现路径，不含任何密钥明文。

---

## 1. 现状事实（实测，非推断）

| 维度 | 事实 | 取证方式 |
|------|------|---------|
| 操作系统 | Rocky Linux 8.10 (Green Obsidian)，kernel `4.18.0-553.el8_10.x86_64` | `cat /etc/os-release; uname -a` |
| Python | **3.11.7**（venv `/opt/securetrans-notify/venv`，156MB） | `venv/bin/python -V; du -sh venv` |
| 依赖管理 | venv + `pip freeze` 锁（**无 requirements.txt，无锁文件入库**，本次补齐 `requirements-lock.txt`） | `pip freeze` |
| 容器 | **无 docker**；宿主有 podman 4.9 但网关不使用 | `command -v docker` → 空；`podman --version` |
| 数据库 | **无数据库**。审计落地为追加写 JSONL：`/var/lib/securetrans-notify/notify.jsonl`（当前 8KB） | `ls -l /var/lib/securetrans-notify` |
| 进程管理 | systemd `securetrans-notify.service`（`active` / `enabled`，`User=root`） | `systemctl cat/is-active/is-enabled` |
| 监听 | `10.10.30.114:8090`（仅内网，非 `0.0.0.0`） | `ss -lntp \| grep 8090` |
| 代码 | `/opt/securetrans-notify/srv/notify_app.py`（20089B，`VERSION="0.2.2"`） | `sha256sum`（见归档 manifest） |
| 配置 | `/opt/securetrans-notify/.env`（`600 root:root`，9 个键，含 App Secret） | `ls -l; grep '^[A-Z_]*=' \| sed 's/=.*/=<redacted>/'` |
| 日志 | `/var/log/securetrans-notify.log`、`/var/log/securetrans-notify.err.log`（systemd append） | 单元文件 `StandardOutput/StandardError` |
| 出站 | 仅放行 `open.feishu.cn:443`（防火墙策略，ADR-052） | 策略侧；网关侧无 curl |

`.env` 键集合（值全部脱敏）：`FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`FEISHU_NOTIFY_TOKEN`、`NOTIFY_BIND`、`NOTIFY_PORT`、`NOTIFY_DATA_DIR`、`NOTIFY_MAX_RECIPIENTS`、`NOTIFY_ALLOW_CIDRS`、`SECURETRANS_APP_URL`。

---

## 2. 飞书 SDK 版本快照（可定位、可回退）

| 组件 | 版本 | 定位方式 | 用途 |
|------|------|---------|------|
| `lark-oapi`（飞书官方 Python SDK） | **1.7.3** | PyPI `https://pypi.org/project/lark-oapi/1.7.3/`；源码仓 `https://github.com/larksuite/oapi-sdk-python`（tag `v1.7.3`） | 构建 `lark.Client` 并**承载消息发送**（`im.v1.message.create`）；token 获取与通讯录仍走 `httpx` 直连 |
| `fastapi` | 0.141.1 | PyPI `https://pypi.org/project/fastapi/0.141.1/` | HTTP 服务框架 |
| `uvicorn` | 0.53.0 | PyPI `https://pypi.org/project/uvicorn/0.53.0/` | ASGI 运行时 |
| `httpx` | 0.28.1 | PyPI `https://pypi.org/project/httpx/0.28.1/` | 直连 `open.feishu.cn` 的 HTTP 调用 |
| 其余 19 个传递依赖 | 见 `requirements-lock.txt` | 同文件逐行 `==` 固定 | — |

> 说明：本网关**不 vendor** 官方 SDK 仓库，只锁版本号 + venv 快照；需要升级时按 `requirements-lock.txt` 全量替换并在 dryrun 对照通过后再上线。SDK 实际承担的接口面只有一个——`im.v1.message.create`（`POST /open-apis/im/v1/messages`）；`tenant_access_token`、通讯录 `batch_get_id`/`users/:id` 由 `notify_app.py` 用 `httpx` 直连、不经 SDK。因此 SDK 升级的回归面 = 单条消息发送 + 其余 HTTP 路径不受影响（见 §2.1）。

### 2.1 版本评估（2026-11-28，决定：保持 1.7.3，不升级）

| 项 | 事实 |
|----|------|
| 线上锁定版本 | `lark-oapi == 1.7.3`（2026-08-19 发布），venv 快照同版本 |
| 官方最新稳定版 | **1.9.0**（2026-11-25 发布）；GitHub tag `v1.9.0`，wheel `lark_oapi-1.9.0-py3-none-any.whl` 7,712,542B，sha256 `0ca3bc134714a8d96316fdcf9fac9bf909ffd644ca6c1b12ffb4fa633a983da9` |
| 是否存在 2.x | 仅 `2.0.0.dev0~dev4`（2026-04 预发布），**无正式 2.0.0**，不采用 |
| 中间版本 | 1.7.4（10-12）、1.7.5（10-15）、1.8.0（11-16）、1.9.0（11-25） |
| 1.7.3→1.9.0 变更规模 | 17 commit / 19 文件，全部在 `lark_oapi/` 内（GitHub compare `v1.7.3...v1.9.0`） |
| 变更内容 | ①webhook 校验令牌强制生效 + 动态 webhook 凭据 provider；②WebSocket 自定义连接 host / 握手 header；③ISV `ClientAssertion` 认证 + OAuth 错误详情保留；④OAuth 显式 audience |
| 依赖树差异 | **无**：`requests>=2.25`、`requests_toolbelt>=0.9`、`pycryptodome>=3.9`、`websockets<16,>=11`、`httpx<1.0,>=0.24` 三个版本完全一致 |
| 与本网关相关性 | 四个变更簇（webhook / WebSocket / ISV / OAuth）**均未使用**；`im.v1.message.create` 的入参出参未变 → 不改代码即可升级，但也没有收益 |
| 结论 | **保持 1.7.3**（观察期优先稳定）；升级窗口留待下个版本，触发条件见下 |

**升级触发条件（满足任一才动）**：①官方发布修复 `im.v1.message.create` 相关缺陷或安全公告；②我们需要 ISV `ClientAssertion`、WebSocket 长连接或 webhook 收事件能力；③官方发布正式 2.0.0 且有明确迁移指南。

**升级执行清单（复用本次 dryrun 口径）**：隔离实例（18090、独立 venv、`127.0.0.1`）→ 装 1.9.0 并按 `requirements-lock.txt` 全量重锁 → 鉴权四路径（无 token 401 / 错 token 401 / 非法事件 400 / 非法邮箱 400）→ 上游不可达 502 → **真实投递 1 条**（校验 `message_id` 与部门补全）→ `pip freeze` 与单元 sha256 对照 → 重打 venv 快照并更新 `docs/19` 与 Release 归档。

---

## 3. 归档内容（`securetrans-feishu-gateway-0.2.2.tar.gz`）

```
securetrans-feishu-gateway-0.2.2/
├── srv/notify_app.py                     # 网关源码（与线上 sha256 一致）
├── securetrans-notify.service            # systemd 单元
├── deploy-gateway.sh                     # 首次部署/升级脚本（支持 --secret-file）
├── README.md                             # 接口与运维说明
├── requirements-lock.txt                 # pip freeze 全量锁
├── ENVIRONMENT.md                        # 本文件
├── env/gateway.env.template              # 9 键模板（值留空，600 权限提示）
└── MANIFEST.sha256                       # 上述文件校验和
```

配套的**运行环境快照**另存：`securetrans-feishu-gateway-0.2.2-venv-py311.tar.gz`（`/opt/securetrans-notify/venv` 原样打包，含 `pyvenv.cfg` 与 site-packages）。

---

## 4. 离线复现（可复制、可 dryrun）

在**同型号 Rocky 8.10** 机器（或本机 `/tmp`）执行：

```bash
# 1) 落位代码
mkdir -p /opt/securetrans-notify/srv
tar xzf securetrans-feishu-gateway-0.2.2.tar.gz -C /tmp
cp /tmp/securetrans-feishu-gateway-0.2.2/srv/notify_app.py /opt/securetrans-notify/srv/

# 2) 恢复运行环境（二选一）
#    A. 快照直解（推荐，离线、字节级一致）
tar xzf securetrans-feishu-gateway-0.2.2-venv-py311.tar.gz -C /opt/securetrans-notify/
#    B. 有 PyPI 通道时按锁重建
python3.11 -m venv /opt/securetrans-notify/venv
/opt/securetrans-notify/venv/bin/pip install -r requirements-lock.txt

# 3) 配置（值按现场填，权限 600）
install -m 600 env/gateway.env.template /opt/securetrans-notify/.env

# 4) systemd
install -m 644 securetrans-notify.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now securetrans-notify
```

**注意**：venv 快照绑定 Python 3.11 与 Rocky 8 glibc，跨大版本（如 Rocky 10 / Python 3.12）不可直接复用，须按 `requirements-lock.txt` 重建。

---

## 5. dryrun 对照口径

`docs/19-feishu-gateway-archive.md` 记录本轮 dryrun 结果，对照维度固定为 6 项：

1. 代码 sha256（归档 vs 线上）；
2. `pip freeze` 集合（快照重建 venv vs 线上 venv）；
3. `/health` 字段（除 `uptime_sec`）；
4. `/notify` 鉴权与失败路径（错误 token → 401、白名单外 → 403、上游不可达 → 502）；
5. 文件清单（`/opt/securetrans-notify` 下非 venv 文件）；
6. systemd 单元文本 diff。

六项全等才算“全盘对照通过”。
