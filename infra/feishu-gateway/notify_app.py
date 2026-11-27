"""SecureTrans 飞书通知网关（单向通知服务）

职责边界（ADR-052）：鉴权 -> 模板渲染 -> 调飞书发送 -> 记账。
不做业务决策、不做任意 URL 转发、不做通用代理。

启动：uvicorn notify_app:app --host $NOTIFY_BIND --port $NOTIFY_PORT
依赖：lark-oapi（飞书官方 SDK）+ fastapi/uvicorn（复用网关机既有 venv）
"""
from __future__ import annotations

import hmac
import json
import os
import re
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Tuple

import lark_oapi as lark
from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse
from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

VERSION = "0.1.0"
STARTED_AT = time.time()

APP_ID = os.getenv("FEISHU_APP_ID", "").strip()
APP_SECRET = os.getenv("FEISHU_APP_SECRET", "").strip()
NOTIFY_TOKEN = os.getenv("FEISHU_NOTIFY_TOKEN", "").strip()
DATA_DIR = os.getenv("NOTIFY_DATA_DIR", "/var/lib/securetrans-notify")
MAX_RECIPIENTS = int(os.getenv("NOTIFY_MAX_RECIPIENTS", "20"))
ALLOW_CIDRS = [x.strip() for x in os.getenv("NOTIFY_ALLOW_CIDRS", "").split(",") if x.strip()]
APP_URL = os.getenv("SECURETRANS_APP_URL", "").strip()

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

app = FastAPI(title="SecureTrans Feishu Notify Gateway", version=VERSION)

_client = (
    lark.Client.builder().app_id(APP_ID).app_secret(APP_SECRET).build()
    if APP_ID and APP_SECRET
    else None
)


def _mask_email(email: str) -> str:
    """日志脱敏：t***@n***.com"""
    if not email or "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    head = local[0] if local else "*"
    dom = domain[0] if domain else "*"
    return f"{head}***@{dom}***"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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
    sid_text = f"#{sid}" if sid else "-"

    if event == "submission_pending_l1":
        return (
            "【SecureTrans 待审批 · 一级】\n"
            f"单号：{sid_text}\n提交人：{submitter}\n文件：{filename}\n事由：{note}\n"
            f"提交时间：{when}\n处理入口：{app_url}"
        )
    if event == "submission_pending_l2":
        return (
            "【SecureTrans 待审批 · 二级】\n"
            f"单号：{sid_text}\n提交人：{submitter}\n文件：{filename}\n事由：{note}\n"
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
        return (
            "【SecureTrans 审批进度】\n"
            f"单号：{sid_text}\n文件：{filename}\n"
            f"{level} 级审批已通过（审批人：{approver}）\n当前状态：{status_text}\n时间：{when}"
        )
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


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "securetrans-notify",
        "version": VERSION,
        "app_configured": _client is not None,
        "token_configured": bool(NOTIFY_TOKEN),
        "uptime_sec": int(time.time() - STARTED_AT),
        "allow_cidrs": ALLOW_CIDRS,
    }


@app.post("/notify")
def notify(payload: Dict[str, Any], request: Request, x_notify_token: str = Header(default="")) -> JSONResponse:
    if not NOTIFY_TOKEN or not hmac.compare_digest(x_notify_token, NOTIFY_TOKEN):
        return JSONResponse(status_code=401, content={"code": 401, "msg": "invalid notify token"})

    event = str(payload.get("event") or "")
    recipients: List[str] = payload.get("recipients") or []
    variables: Dict[str, Any] = payload.get("vars") or {}
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

    try:
        text = _render(event, variables)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"code": 400, "msg": str(exc)})

    results = []
    sent = failed = 0
    for email in emails:
        ok, code, msg, mid = _send_one(email, text)
        sent += 1 if ok else 0
        failed += 0 if ok else 1
        results.append({"recipient": _mask_email(email), "ok": ok, "code": code, "msg": msg, "message_id": mid})

    body: Dict[str, Any] = {
        "code": 0 if sent else 502,
        "event": event,
        "sent": sent,
        "failed": failed,
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
            "recipients": [_mask_email(e) for e in emails],
            "sent": sent,
            "failed": failed,
            "results": results,
            "client": request.client.host if request.client else "-",
        }
    )
    return JSONResponse(status_code=200 if sent else 502, content=body)
