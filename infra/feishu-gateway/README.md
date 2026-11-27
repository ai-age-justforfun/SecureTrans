# SecureTrans 飞书通知网关（feishu-gateway）

> 归属：ADR-051（通知独立旁路、失败不阻塞业务）、ADR-052（关键机零出网 + 专用单向通知网关）。
> 运行机：`feishu-sdk-server-securetrans`（内网 `10.10.30.114`），与 CICD 的 `feishu-api:8080` **完全分离**。

## 职责边界（硬约束）

服务只做四件事：**鉴权 → 模板渲染 → 调飞书发送 → 记账**。

明确不做：不判业务状态、不算审批人、不做任意 URL 转发、不做通用代理（否则退化为 SSRF / 开放代理）。
收件人邮箱由业务侧（SecureTrans）解析后传入，网关不查 AD、不查数据库。

## 目录

| 文件 | 用途 |
|---|---|
| `notify_app.py` | FastAPI 服务（`/health`、`/notify`） |
| `securetrans-notify.service` | systemd 单元（`securetrans-notify`） |
| `deploy-gateway.sh` | 网关侧安装/升级脚本（复制 venv、写 .env、起服务、自检） |

网关侧运行形态：

```
/opt/securetrans-notify/
├── srv/notify_app.py
├── venv/            # 复制自 /opt/feishu-cicd/venv（出网只放行 open.feishu.cn:443，pip 无法在线装包）
└── .env             # 600，含 App ID/Secret 与预共享 token
/var/lib/securetrans-notify/notify.jsonl   # 审计（收件人已脱敏）
/var/log/securetrans-notify.log / .err.log
```

## 部署 / 升级

在网关机上：

```bash
FEISHU_APP_ID=<cli_xxx> \
FEISHU_APP_SECRET=<secret> \
NOTIFY_PORT=8090 \
SECURETRANS_APP_URL=http://10.10.30.8:8000 \
bash deploy-gateway.sh
```

脚本行为：复用/复制既有 venv → 安装代码 → 生成或保留 `FEISHU_NOTIFY_TOKEN` → `systemctl enable --now` → `curl /health` 自检。

> 首次部署后须把生成的 `FEISHU_NOTIFY_TOKEN` 抄到开发机 `server_credential.md`，并在 SecureTrans `.env` 配同一值。
> 该 token 只允许存在于**两处**：网关 `.env` 与 SecureTrans `.env`。

## 接口

### `GET /health`

```json
{"status":"ok","service":"securetrans-notify","version":"0.1.0",
 "app_configured":true,"token_configured":true,"uptime_sec":123,"allow_cidrs":[]}
```

### `POST /notify`

请求头 `X-Notify-Token: <FEISHU_NOTIFY_TOKEN>`（缺失或错误返回 401）。

```json
{
  "event": "submission_pending_l1",
  "recipients": ["someone@example.com"],
  "request_id": "uuid-or-business-key",
  "vars": {
    "submission_id": 123,
    "filename": "design.bin",
    "submitter": "jintao",
    "note": "说明",
    "approver": "张三",
    "reason": "驳回原因",
    "level": 1,
    "status_text": "一级审批通过",
    "app_url": "http://10.10.30.8:8000",
    "external_url": "http://10.10.30.8:8000"
  }
}
```

响应：

```json
{"code":0,"event":"submission_pending_l1","sent":1,"failed":0,
 "results":[{"recipient":"t***@n***","ok":true,"code":0,"msg":"ok","message_id":"om_xxx"}],
 "duplicate":false}
```

- `code=0` 只要有一条发送成功；全部失败返回 502（业务侧应视作旁路失败，不阻塞主流程）。
- 带 `request_id` 时同 id 重复请求返回首次结果（`duplicate: true`），避免重试放大消息量。
- 收件人上限由 `NOTIFY_MAX_RECIPIENTS`（默认 20）控制。
- **源 IP 白名单（应用层，fail-closed）**：`NOTIFY_ALLOW_CIDRS` 配置允许的来源网段（逗号分隔，如 `10.10.30.8/32`）；
  **未配置即全部拒绝**，不在名单内返回 `403 {"code":403,"msg":"client ip not allowed","client":"<ip>"}`。
  这是防火墙/设备 ACL 之外的第二道校验，防止上游 ACL 被误改或漏配后网关变成任意来源可用的发送代理。

### 支持的事件

| event | 典型收件人 |
|---|---|
| `submission_pending_l1` | 一级审批人 |
| `submission_pending_l2` | 二级审批人 |
| `submission_status` | 提交人（一级通过等中间态） |
| `submission_approved` | 提交人 |
| `submission_rejected` | 提交人（含驳回原因） |
| `submission_auto_approved` | **仅提交人**（免审批直通，跳过审批人） |
| `approval_level_skipped` | 提交人（二级被自动跳过） |

## 运维

- 状态：`systemctl status securetrans-notify`
- 日志：`journalctl -u securetrans-notify -n 50 --no-pager`、`/var/log/securetrans-notify.err.log`
- 审计：`tail -f /var/lib/securetrans-notify/notify.jsonl`（只记元数据，收件人均已掩码）
- Token 轮换：改 `NOTIFY_TOKEN` 生成新值 → 更新 `/opt/securetrans-notify/.env` 与 SecureTrans `.env` → 两边同时 `systemctl restart`
- 端口：`NOTIFY_PORT` 默认 8090；绑定地址 `NOTIFY_BIND` 默认取本机首张网卡 IP（不写死）
- 来源白名单：`NOTIFY_ALLOW_CIDRS`（fail-closed，空值 = 拒绝全部来源）；改后 `systemctl restart securetrans-notify`，
  用 `GET /health` 的 `allow_cidrs` 字段确认已生效

> 监听 `127.0.0.1:8090` 会连接被拒——这是正常的：服务绑定的是内网 IP，本机回环不通，**只接受内网来源**。


## 6. App 凭据运维（ADR-055）

| 场景 | 做法 | 是否依赖 AI |
|---|---|---|
| 首次部署 | `FEISHU_APP_ID=... FEISHU_APP_SECRET=... bash deploy-gateway.sh` 或 `--secret-file /root/feishu-app-secret.txt` | 否（人工一次） |
| 升级/换机后重装 | 直接 `bash deploy-gateway.sh` —— 自动沿用本机 `.env` 里既有 App ID/Secret | 否 |
| 凭据轮换 | SecureTrans 管理页“飞书通知” → 填 App Secret → **下发到网关**（`POST /admin/secret`） | 否 |
| 校验是否生效 | `curl http://<网关IP>:8090/health` 看 `app_configured=true` / `app_id_masked` / `contact_readable` | 否 |

- `POST /admin/secret` 仅接受白名单源 IP（`NOTIFY_ALLOW_CIDRS`）+ `X-Notify-Token`；只接受 `app_id/app_secret`；
  **先调飞书 `tenant_access_token` 验证，通过后才写 `.env`（600）并热重建客户端**，无需重启服务。
- 业务机只做内存转发：不入库、不落盘、不回显；审计只记动作（`push_feishu_secret`），不含密钥正文。
- **部门补全**：`/notify` 对待审批事件用 `submitter_email` 查飞书通讯录（用户 → `department_ids` → 部门名），
  渲染“提交人部门：X / 请部门负责人进行审批”；缺 `contact:contact.base:readonly` + `contact:department.base:readonly`
  或查不到时该行自动省略，**不影响消息发送**。权限变更后必须在飞书“版本管理与发布”里**创建并发布版本**才生效。
