"""SecureTrans 飞书通知网关（单向通知服务）

职责边界（ADR-052）：鉴权 -> 模板渲染 -> 调飞书发送 -> 记账。
不做业务决策、不做任意 URL 转发、不做通用代理。

凭据边界（ADR-055）：App Secret 只存本机 .env（600），支持两种取得方式：
  1) 部署时由 `deploy-gateway.sh` 从环境变量/凭据文件写入（人工一次性）；
  2) 运行期由 SecureTrans 管理页"下发 App Secret"经 `POST /admin/secret` 写入（
     业务机只在内存转发、不落盘），网关落 .env 后**热重建客户端**，无需重启/AI。

启动：uvicorn notify_app:app --host $NOTIFY_BIND --port $NOTIFY_PORT
依赖：lark-oapi（飞书官方 SDK）+ fastapi/uvicorn（复用网关机既有 venv）
"""
from __future__ import annotations

import concurrent.futures
import hmac
import ipaddress
import json
import os
import re
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Tuple

import lark_oapi as lark
import urllib.request
from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse
from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

VERSION = "0.2.2"
STARTED_AT = time.time()

ENV_PATH = os.getenv("NOTIFY_ENV_FILE", "/opt/securetrans-notify/.env")
APP_ID = os.getenv("FEISHU_APP_ID", "").strip()
APP_SECRET = os.getenv("FEISHU_APP_SECRET", "").strip()
NOTIFY_TOKEN = os.getenv("FEISHU_NOTIFY_TOKEN", "").strip()
DATA_DIR = os.getenv("NOTIFY_DATA_DIR", "/var/lib/securetrans-notify")
MAX_RECIPIENTS = int(os.getenv("NOTIFY_MAX_RECIPIENTS", "20"))
ALLOW_CIDRS = [x.strip() for x in os.getenv("NOTIFY_ALLOW_CIDRS", "").split(",") if x.strip()]
APP_URL = os.getenv("SECURETRANS_APP_URL", "").strip()
FEISHU_BASE = os.getenv("FEISHU_OPEN_BASE", "https://open.feishu.cn").rstrip("/")

EVENTS = {
    "submission_pending_l1",
    "submission_pending_l2",
    "submission_approved",
    "submission_rejected",
    "submission_status",
    "submission_auto_approved",
    "approval_level_skipped",
}

_lock = threading.Lock()
_idempotent: Dict[str, Dict[str, Any]] = {}
_dept_cache: Dict[str, Tuple[float, str]] = {}
_token_cache: Dict[str, Any] = {"value": "", "exp": 0.0}
_contact_ok = {"value": None}  # None=未探测 True/False=通讯录读权限是否可用

app = FastAPI(title="SecureTrans Feishu Notify Gateway", version=VERSION)


def _build_client(app_id: str, secret: str):
    return lark.Client.builder().app_id(app_id).app_secret(secret).build() if app_id and secret else None


_client = _build_client(APP_ID, APP_SECRET)


def _mask_email(email: str) -> str:
    """日志脱敏：t***@n***.com"""
    if not email or "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    head = local[0] if local else "*"
    dom = domain[0] if domain else "*"
    return f"{head}***@{dom}***"


def _mask_id(value: str) -> str:
    if not value:
        return ""
    return value[:6] + "****" + value[-4:] if len(value) > 12 else value[:4] + "****"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _http_json(path: str, payload: Dict[str, Any] = None, token: str = "", timeout: float = 8.0) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        FEISHU_BASE + path,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _tenant_token() -> str:
    """tenant_access_token（提前 5 分钟续期）；失败返回空串。"""
    with _lock:
        if _token_cache["value"] and _token_cache["exp"] - 300 > time.time():
            return _token_cache["value"]
        if not (APP_ID and APP_SECRET):
            return ""
    try:
        body = _http_json(
            "/open-apis/auth/v3/tenant_access_token/internal",
            {"app_id": APP_ID, "app_secret": APP_SECRET},
        )
        tok = body.get("tenant_access_token") or ""
        if body.get("code") == 0 and tok:
            with _lock:
                _token_cache["value"] = tok
                _token_cache["exp"] = time.time() + float(body.get("expire") or 7200)
            return tok
    except Exception:
        return ""
    return ""


def _lookup_department(email: str) -> str:
    """AD 邮箱 -> 飞书人员 -> 部门名。缺通讯录读权限时返回空串（不影响通知发送）。"""
    if not email or "@" not in email:
        return ""
    now = time.time()
    with _lock:
        hit = _dept_cache.get(email)
        if hit and hit[0] > now:
            return hit[1]
    token = _tenant_token()
    if not token:
        return ""
    try:
        ids = _http_json(
            "/open-apis/contact/v3/users/batch_get_id?user_id_type=open_id",
            {"emails": [email]},
            token,
        )
        row = ((ids.get("data") or {}).get("user_list") or [{}])[0]
        open_id = row.get("user_id") or ""
        if not open_id:
            return ""
        user = _http_json(
            f"/open-apis/contact/v3/users/{open_id}"
            "?user_id_type=open_id&department_id_type=open_department_id",
            None,
            token,
        )
        if user.get("code") != 0:
            _contact_ok["value"] = False
            return ""
        _contact_ok["value"] = True
        user_obj = ((user.get("data") or {}).get("user") or {})
        # 优先"主部门"（orders.is_primary_dept），否则退回 department_ids 首个
        primary = ""
        for o in (user_obj.get("orders") or []):
            if o.get("is_primary_dept"):
                primary = o.get("department_id") or ""
                break
        dept_ids = user_obj.get("department_ids") or []
        dept_id = primary or (dept_ids[0] if dept_ids else "")
        if not dept_id:
            return ""
        dept = _http_json(
            f"/open-apis/contact/v3/departments/{dept_id}?department_id_type=open_department_id",
            None,
            token,
        )
        if dept.get("code") != 0:
            return ""
        name = ((dept.get("data") or {}).get("department") or {}).get("name") or ""
        if not name:
            name = (((dept.get("data") or {}).get("department") or {}).get("i18n_name") or {}).get("zh_cn") or ""
        if name:
            with _lock:
                _dept_cache[email] = (now + 3600, name)
        return name
    except Exception:
        return ""


def _render(event: str, v: Dict[str, Any]) -> str:
    submitter = v.get("submitter") or v.get("username") or "-"
    filename = v.get("filename") or "-"
    note = v.get("note") or "-"
    when = v.get("time") or _now()
    approver = v.get("approver") or "-"
    reason = v.get("reason") or "-"
    level = v.get("level") or "1"
    status_text = v.get("status_text") or "-"
    app_url = v.get("app_url") or APP_URL or "-"
    external_url = v.get("external_url") or app_url
    operator = v.get("operator") or "-"
    sid = v.get("submission_id")
    # 单号口径：系统主键=<8位hex>_<提交时间戳>，通知里只显示短号（详情页仍为全 ID）
    if sid:
        sid_text = "#" + (str(sid).split("_")[0] if "_" in str(sid) else str(sid)[:8])
    else:
        sid_text = "-"
    department = (v.get("submitter_department") or "").strip()
    dept_line = f"提交人部门：{department}\n请部门负责人进行审批。\n" if department else ""

    if event == "submission_pending_l1":
        return (
            "【SecureTrans 待审批 · 一级】\n"
            f"单号：{sid_text}\n提交人：{submitter}\n{dept_line}文件：{filename}\n事由：{note}\n"
            f"提交时间：{when}\n处理入口：{app_url}"
        )
    if event == "submission_pending_l2":
        return (
            "【SecureTrans 待审批 · 二级】\n"
            f"单号：{sid_text}\n提交人：{submitter}\n{dept_line}文件：{filename}\n事由：{note}\n"
            f"一级审批人：{approver}\n一级通过时间：{when}\n处理入口：{app_url}"
        )
    if event == "submission_approved":
        return (
            "【SecureTrans 审批通过】\n"
            f"单号：{sid_text}\n文件：{filename}\n审批人：{approver}\n"
            f"时间：{when}\n外网下载入口：{external_url}"
        )
    if event == "submission_rejected":
        return (
            "【SecureTrans 已驳回】\n"
            f"单号：{sid_text}\n文件：{filename}\n审批人：{approver}\n"
            f"驳回原因：{reason}\n时间：{when}"
        )
    if event == "submission_status":
        # 只有确实带审批人才渲染"X 级审批已通过"，否则只报当前状态
        # （v2.7.6 修复：提交时 status_text=已提交待审批，旧模板却硬写"1 级审批已通过（审批人：-）"）
        lines = [
            "【SecureTrans 审批进度】",
            f"单号：{sid_text}",
            f"文件：{filename}",
        ]
        if approver and approver != "-":
            lines.append(f"{level} 级审批已通过（审批人：{approver}）")
        lines.append(f"当前状态：{status_text}")
        lines.append(f"时间：{when}")
        return "\n".join(lines)
    if event == "submission_auto_approved":
        return (
            "【SecureTrans 免审批放行】\n"
            f"单号：{sid_text}\n文件：{filename}\n提交人：{submitter}\n"
            "说明：命中免审批规则，已自动通过并完成摆渡，本次无需人工审批。\n"
            f"外网下载入口：{external_url}"
        )
    if event == "approval_level_skipped":
        return (
            "【SecureTrans 审批进度】\n"
            f"单号：{sid_text}\n文件：{filename}\n"
            f"{approver} 已通过一级审批，且具备二级权限，二级审批自动跳过。\n"
            f"当前状态：{status_text}\n时间：{when}"
        )
    raise ValueError(f"unsupported event: {event}")


def _send_one(email: str, text: str) -> Tuple[bool, int, str, str]:
    """发送单条文本消息，返回 (ok, code, msg, message_id)。"""
    if _client is None:
        return False, -1, "app credentials not configured", ""
    try:
        body = (
            CreateMessageRequestBody.builder()
            .receive_id(email)
            .msg_type("text")
            .content(json.dumps({"text": text}, ensure_ascii=False))
            .build()
        )
        req = (
            CreateMessageRequest.builder()
            .receive_id_type("email")
            .request_body(body)
            .build()
        )
        resp = _client.im.v1.message.create(req)
        if resp.success() and resp.data and resp.data.message_id:
            return True, resp.code or 0, "ok", resp.data.message_id
        return False, resp.code or -1, resp.msg or "unknown error", ""
    except Exception as exc:  # 网络/序列化异常统一收敛
        return False, -1, f"{type(exc).__name__}: {exc}", ""


def _audit(record: Dict[str, Any]) -> None:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with _lock:
            with open(os.path.join(DATA_DIR, "notify.jsonl"), "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _client_allowed(host: str) -> bool:
    """源 IP 白名单校验（ADR-052）。fail-closed：未配置 NOTIFY_ALLOW_CIDRS 时一律拒绝。"""
    if not ALLOW_CIDRS:
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    for cidr in ALLOW_CIDRS:
        try:
            if ip in ipaddress.ip_network(cidr, strict=False):
                return True
        except ValueError:
            continue
    return False


def _write_env(updates: Dict[str, str]) -> None:
    """原子更新 .env（保留其余键，权限 600）。"""
    path = ENV_PATH
    pairs: Dict[str, str] = {}
    order: List[str] = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for raw in fh:
                line = raw.rstrip("\n")
                if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                if k not in pairs:
                    order.append(k)
                pairs[k] = v
    for k, v in updates.items():
        if k not in pairs:
            order.append(k)
        pairs[k] = v
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        for k in order:
            fh.write(f"{k}={pairs[k]}\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "securetrans-notify",
        "version": VERSION,
        "app_configured": _client is not None,
        "app_id_masked": _mask_id(APP_ID),
        "token_configured": bool(NOTIFY_TOKEN),
        "contact_readable": _contact_ok["value"],
        "uptime_sec": int(time.time() - STARTED_AT),
        "allow_cidrs": ALLOW_CIDRS,
    }


@app.post("/admin/secret")
def admin_secret(
    payload: Dict[str, Any],
    request: Request,
    x_notify_token: str = Header(default=""),
) -> JSONResponse:
    """受控写入飞书应用凭据（ADR-055）。

    仅放行白名单源 IP + 预共享 token；只接受 app_id/app_secret 两个键；写入后热重建客户端。
    业务机只做内存转发，不落盘。
    """
    global APP_ID, APP_SECRET, _client
    client_host = request.client.host if request.client else ""
    if not _client_allowed(client_host):
        return JSONResponse(status_code=403, content={"code": 403, "msg": "client ip not allowed"})
    if not NOTIFY_TOKEN or not hmac.compare_digest(x_notify_token, NOTIFY_TOKEN):
        return JSONResponse(status_code=401, content={"code": 401, "msg": "invalid notify token"})

    app_id = str(payload.get("app_id") or "").strip()
    app_secret = str(payload.get("app_secret") or "").strip()
    if not app_id.startswith("cli_") or len(app_id) < 12:
        return JSONResponse(status_code=400, content={"code": 400, "msg": "invalid app_id"})
    if len(app_secret) < 16:
        return JSONResponse(status_code=400, content={"code": 400, "msg": "invalid app_secret"})

    # 先验证凭据可用，再落盘（避免写入坏凭据导致通知全失败）
    token_resp = {"code": -1}
    try:
        token_resp = _http_json(
            "/open-apis/auth/v3/tenant_access_token/internal",
            {"app_id": app_id, "app_secret": app_secret},
        )
    except Exception as exc:
        return JSONResponse(status_code=502, content={"code": 502, "msg": f"open.feishu.cn unreachable: {exc}"})
    if token_resp.get("code") != 0:
        return JSONResponse(
            status_code=400,
            content={"code": 400, "msg": f"credential rejected: {token_resp.get('code')} {token_resp.get('msg')}"},
        )

    try:
        _write_env({"FEISHU_APP_ID": app_id, "FEISHU_APP_SECRET": app_secret})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"code": 500, "msg": f"write env failed: {exc}"})

    with _lock:
        APP_ID = app_id
        APP_SECRET = app_secret
        _client = _build_client(app_id, app_secret)
        _token_cache["value"] = ""
        _token_cache["exp"] = 0.0
        _dept_cache.clear()

    _audit({"ts": _now(), "event": "admin_secret", "client": client_host, "app_id": _mask_id(app_id), "ok": True})
    return JSONResponse(
        content={
            "code": 0,
            "ok": True,
            "app_configured": _client is not None,
            "app_id_masked": _mask_id(app_id),
            "env_file": ENV_PATH,
        }
    )


@app.post("/notify")
def notify(payload: Dict[str, Any], request: Request, x_notify_token: str = Header(default="")) -> JSONResponse:
    client_host = request.client.host if request.client else ""
    if not _client_allowed(client_host):
        return JSONResponse(status_code=403, content={"code": 403, "msg": "client ip not allowed", "client": client_host})

    if not NOTIFY_TOKEN or not hmac.compare_digest(x_notify_token, NOTIFY_TOKEN):
        return JSONResponse(status_code=401, content={"code": 401, "msg": "invalid notify token"})

    event = str(payload.get("event") or "")
    recipients: List[str] = payload.get("recipients") or []
    variables: Dict[str, Any] = dict(payload.get("vars") or {})
    request_id = str(payload.get("request_id") or "")

    if event not in EVENTS:
        return JSONResponse(status_code=400, content={"code": 400, "msg": f"unsupported event: {event}"})
    if not isinstance(recipients, list) or not recipients:
        return JSONResponse(status_code=400, content={"code": 400, "msg": "recipients required"})
    if len(recipients) > MAX_RECIPIENTS:
        return JSONResponse(status_code=400, content={"code": 400, "msg": f"too many recipients (> {MAX_RECIPIENTS})"})
    emails = [str(r).strip() for r in recipients if str(r).strip()]
    if not emails:
        return JSONResponse(status_code=400, content={"code": 400, "msg": "empty recipients"})
    for e in emails:
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", e):
            return JSONResponse(status_code=400, content={"code": 400, "msg": f"invalid email: {e}"})

    if request_id and request_id in _idempotent:
        cached = dict(_idempotent[request_id])
        cached["duplicate"] = True
        return JSONResponse(content=cached)

    # 部门补全（只对"待审批"类事件有意义；缺权限/查不到则静默省略该行）
    submitter_email = str(variables.get("submitter_email") or "").strip()
    if event in ("submission_pending_l1", "submission_pending_l2") and submitter_email:
        dept = variables.get("submitter_department") or _lookup_department(submitter_email)
        if dept:
            variables["submitter_department"] = dept

    try:
        text = _render(event, variables)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"code": 400, "msg": str(exc)})

    results = []
    sent = failed = 0
    # 并发投递（v0.2.1）：一级/二级审批人可能有多个，串行会让业务侧 5s 超时先到（
    # 实际已送达但业务侧记 failed）。并发上限 8，结果顺序与收件人一致。
    if emails:
        workers = min(8, len(emails))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            outs = list(pool.map(lambda e: _send_one(e, text), emails))
        for email, (ok, code, msg, mid) in zip(emails, outs):
            sent += 1 if ok else 0
            failed += 0 if ok else 1
            results.append({"recipient": _mask_email(email), "ok": ok, "code": code, "msg": msg, "message_id": mid})

    body: Dict[str, Any] = {
        "code": 0 if sent else 502,
        "event": event,
        "sent": sent,
        "failed": failed,
        "department": variables.get("submitter_department") or "",
        "results": results,
        "duplicate": False,
    }
    if request_id:
        _idempotent[request_id] = body
        if len(_idempotent) > 500:
            _idempotent.pop(next(iter(_idempotent)))

    _audit(
        {
            "ts": _now(),
            "request_id": request_id,
            "event": event,
            "submission_id": variables.get("submission_id"),
            "department": variables.get("submitter_department") or "",
            "recipients": [_mask_email(e) for e in emails],
            "sent": sent,
            "failed": failed,
            "results": results,
            "client": request.client.host if request.client else "-",
        }
    )
    return JSONResponse(status_code=200 if sent else 502, content=body)
