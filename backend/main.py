"""
SecureTrans - 轻量级跨网文件审批摆渡系统 后端
单文件 FastAPI + SQLite，PMF 阶段部署用
"""
import os
import sys
import json
import time
import uuid
import hashlib
import sqlite3
import zipfile
import logging
import datetime
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import bcrypt

# ============================================================
# 配置
# ============================================================
BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = Path(os.getenv("SECURETRANS_DATA", str(BASE_DIR / "data")))
DB_PATH = DATA_DIR / "securetrans.db"
NAS_MOUNT = Path(os.getenv("NAS_MOUNT", str(DATA_DIR / "nas")))
ARCHIVE_DIR = NAS_MOUNT / "archive"
INTERNAL_DIR = NAS_MOUNT / "internal" / "pending"
EXTERNAL_DIR = NAS_MOUNT / "external" / "published"
STATIC_DIR = BASE_DIR / "static"
SECRET_KEY = os.getenv("SECRET_KEY", "securetrans-dev-secret-change-in-production")
TOKEN_EXPIRE_HOURS = int(os.getenv("TOKEN_EXPIRE_HOURS", "24"))

# AD 配置（PMF 阶段先模拟，生产接入真实 LDAP）
AD_ENABLED = os.getenv("AD_ENABLED", "false").lower() == "true"
AD_HOST = os.getenv("AD_HOST", "")
AD_BASE_DN = os.getenv("AD_BASE_DN", "")
AD_BIND_DN = os.getenv("AD_BIND_DN", "")
AD_BIND_PASSWORD = os.getenv("AD_BIND_PASSWORD", "")

# 日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(DATA_DIR / "securetrans.log", encoding="utf-8"), logging.StreamHandler()]
)
logger = logging.getLogger("securetrans")

# ============================================================
# 数据库
# ============================================================
def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

@contextmanager
def db_conn():
    conn = get_db()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    """初始化数据库表和初始数据"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for d in [ARCHIVE_DIR, INTERNAL_DIR, EXTERNAL_DIR, STATIC_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    with db_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS local_users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT,
            email TEXT,
            role TEXT DEFAULT 'internal-user',
            status TEXT DEFAULT 'active',
            must_change_password INTEGER DEFAULT 0,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS role_mappings (
            id TEXT PRIMARY KEY,
            principal_type TEXT NOT NULL,
            principal_value TEXT NOT NULL,
            display_name TEXT,
            role TEXT NOT NULL,
            granted_by TEXT,
            granted_at TEXT,
            note TEXT
        );

        CREATE TABLE IF NOT EXISTS submissions (
            id TEXT PRIMARY KEY,
            submitter TEXT,
            submitter_name TEXT,
            receiver_name TEXT,
            receiver_email TEXT,
            receiver_type TEXT,
            security_level TEXT,
            reason TEXT,
            expiry_days INTEGER DEFAULT 30,
            status TEXT DEFAULT 'pending',
            auto_approved INTEGER DEFAULT 0,
            archive_path TEXT,
            submit_time TEXT,
            file_count INTEGER DEFAULT 0,
            total_size INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS submission_files (
            id TEXT PRIMARY KEY,
            submission_id TEXT,
            path TEXT,
            name TEXT,
            size INTEGER,
            type TEXT,
            md5 TEXT,
            matched INTEGER DEFAULT 0,
            is_archive INTEGER DEFAULT 0,
            FOREIGN KEY (submission_id) REFERENCES submissions(id)
        );

        CREATE TABLE IF NOT EXISTS approvals (
            id TEXT PRIMARY KEY,
            submission_id TEXT,
            level INTEGER,
            approver TEXT,
            approver_name TEXT,
            action TEXT,
            comment TEXT,
            time TEXT,
            FOREIGN KEY (submission_id) REFERENCES submissions(id)
        );

        CREATE TABLE IF NOT EXISTS feature_rules (
            id TEXT PRIMARY KEY,
            name TEXT,
            rule_type TEXT,
            pattern TEXT,
            enabled INTEGER DEFAULT 1,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS partners (
            id TEXT PRIMARY KEY,
            name TEXT,
            contact TEXT,
            email TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS approvers (
            id TEXT PRIMARY KEY,
            level INTEGER,
            username TEXT,
            display_name TEXT,
            scope TEXT
        );

        CREATE TABLE IF NOT EXISTS system_config (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS audit_logs (
            id TEXT PRIMARY KEY,
            time TEXT,
            user TEXT,
            action TEXT,
            target TEXT,
            detail TEXT,
            ip TEXT
        );
        """)

        # 初始管理员
        cursor = conn.execute("SELECT COUNT(*) as c FROM local_users WHERE username='admin'")
        if cursor.fetchone()["c"] == 0:
            admin_hash = bcrypt.hashpw("Admin@123".encode(), bcrypt.gensalt()).decode()
            conn.execute(
                "INSERT INTO local_users (id,username,password_hash,display_name,email,role,status,must_change_password,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), "admin", admin_hash, "系统管理员", "admin@localhost", "admin", "active", 1, now_str())
            )
            logger.info("初始管理员 admin 已创建（密码 Admin@123，首次登录需修改）")

        # 初始系统配置
        defaults = {
            "auto_approval_enabled": "true",
            "default_expiry_days": "30",
            "max_file_size_gb": "10",
            "app_name": "SecureTrans",
        }
        for k, v in defaults.items():
            conn.execute("INSERT OR IGNORE INTO system_config (key,value) VALUES (?,?)", (k, v))

        # 初始特征码规则
        cursor = conn.execute("SELECT COUNT(*) as c FROM feature_rules")
        if cursor.fetchone()["c"] == 0:
            rules = [
                ("PDF文档", "extension", ".pdf", 1),
                ("Word文档", "extension", ".doc,.docx", 1),
                ("Excel表格", "extension", ".xls,.xlsx", 1),
                ("图片文件", "extension", ".png,.jpg,.jpeg,.gif", 1),
            ]
            for name, rtype, pattern, enabled in rules:
                conn.execute(
                    "INSERT INTO feature_rules (id,name,rule_type,pattern,enabled,created_at) VALUES (?,?,?,?,?,?)",
                    (str(uuid.uuid4()), name, rtype, pattern, enabled, now_str())
                )

    logger.info("数据库初始化完成: %s", DB_PATH)

# ============================================================
# 工具函数
# ============================================================
def now_str() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def gen_submission_id() -> str:
    return f"{uuid.uuid4().hex[:8]}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"

def md5_file(filepath: Path, chunk_size: int = 8192) -> str:
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()

def get_file_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    types = {
        ".pdf": "PDF文档", ".doc": "Word文档", ".docx": "Word文档",
        ".xls": "Excel表格", ".xlsx": "Excel表格", ".ppt": "PPT", ".pptx": "PPT",
        ".png": "图片", ".jpg": "图片", ".jpeg": "图片", ".gif": "图片",
        ".zip": "压缩包", ".rar": "压缩包", ".7z": "压缩包",
        ".txt": "文本", ".csv": "文本", ".json": "代码", ".py": "代码",
    }
    return types.get(ext, "未知类型")

def format_size(size: int) -> str:
    if size < 1024: return f"{size} B"
    if size < 1024*1024: return f"{size/1024:.1f} KB"
    if size < 1024*1024*1024: return f"{size/1024/1024:.1f} MB"
    return f"{size/1024/1024/1024:.2f} GB"

def add_audit_log(user: str, action: str, target: str = "", detail: str = "", ip: str = ""):
    with db_conn() as conn:
        conn.execute(
            "INSERT INTO audit_logs (id,time,user,action,target,detail,ip) VALUES (?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), now_str(), user, action, target, detail, ip)
        )

def row_to_dict(row) -> dict:
    return {k: row[k] for k in row.keys()}

# ============================================================
# 认证
# ============================================================
class LoginRequest(BaseModel):
    username: str
    password: str

class TokenData(BaseModel):
    user_id: str
    username: str
    display_name: str
    role: str
    source: str  # local / ad

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())

def authenticate_local(username: str, password: str) -> Optional[dict]:
    with db_conn() as conn:
        row = conn.execute("SELECT * FROM local_users WHERE username=? AND status='active'", (username,)).fetchone()
        if row and verify_password(password, row["password_hash"]):
            return row_to_dict(row)
    return None

def authenticate_ad(username: str, password: str) -> Optional[dict]:
    """AD 认证。PMF 阶段模拟，生产环境接入 ldap3"""
    if not AD_ENABLED:
        return None
    # TODO: 生产环境接入真实 LDAP 认证
    # from ldap3 import Server, Connection, ALL
    # server = Server(AD_HOST, get_info=ALL)
    # conn = Connection(server, user=f"{AD_BASE_DN}\\{username}", password=password, auto_bind=True)
    # ... 查询用户信息和组
    return None

def get_user_role(username: str, source: str) -> str:
    """获取用户角色：本地用户从 local_users 取，AD 用户从 role_mappings 查，默认普通用户"""
    if source == "local":
        with db_conn() as conn:
            row = conn.execute("SELECT role FROM local_users WHERE username=?", (username,)).fetchone()
            if row:
                return row["role"]
    # AD 用户：查角色映射
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT role FROM role_mappings WHERE principal_type='user' AND principal_value=?",
            (username,)
        ).fetchall()
        roles = [r["role"] for r in rows]
        # TODO: 查用户所属 AD 组的组级映射
        if roles:
            return roles[0]  # 多角色取第一个，PMF 阶段简化
    return "internal-user"

def create_token(user: dict, source: str) -> str:
    """简化版 token：base64 编码用户信息。生产用 JWT"""
    import base64
    payload = json.dumps({
        "user_id": user.get("id", ""),
        "username": user["username"],
        "display_name": user.get("display_name", user["username"]),
        "role": get_user_role(user["username"], source),
        "source": source,
        "exp": time.time() + TOKEN_EXPIRE_HOURS * 3600,
    })
    return base64.b64encode(payload.encode()).decode()

def decode_token(token: str) -> Optional[TokenData]:
    import base64
    try:
        payload = json.loads(base64.b64decode(token.encode()).decode())
        if payload["exp"] < time.time():
            return None
        return TokenData(**payload)
    except Exception:
        return None

def get_current_user(request: Request) -> TokenData:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录")
    token = auth[7:]
    user = decode_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    return user

def require_role(*roles: str):
    def dependency(user: TokenData = Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="权限不足")
        return user
    return dependency

# ============================================================
# 特征码匹配
# ============================================================
def match_feature_rules(filename: str, file_path: Path = None) -> tuple[bool, list]:
    """检查文件是否匹配特征码规则，返回 (是否匹配, 匹配的规则名列表)"""
    with db_conn() as conn:
        rules = conn.execute("SELECT * FROM feature_rules WHERE enabled=1").fetchall()
    matched = []
    ext = Path(filename).suffix.lower()
    for rule in rules:
        if rule["rule_type"] == "extension":
            exts = [e.strip().lower() for e in rule["pattern"].split(",")]
            if ext in exts:
                matched.append(rule["name"])
        elif rule["rule_type"] == "filename":
            import re
            if re.search(rule["pattern"], filename, re.IGNORECASE):
                matched.append(rule["name"])
        elif rule["rule_type"] == "binary" and file_path:
            try:
                with open(file_path, "rb") as f:
                    header = f.read(8)
                if rule["pattern"].encode() in header:
                    matched.append(rule["name"])
            except Exception:
                pass
    return (len(matched) > 0, matched)

def check_auto_approval(files: list) -> dict:
    """检查是否可以免审批：开关开启 + 所有文件都匹配特征码"""
    with db_conn() as conn:
        row = conn.execute("SELECT value FROM system_config WHERE key='auto_approval_enabled'").fetchone()
    if not row or row["value"] != "true":
        return {"canAutoApprove": False, "reason": "免审批总开关已关闭", "matchedRules": [], "unmatchedFiles": []}
    if not files:
        return {"canAutoApprove": False, "reason": "没有文件", "matchedRules": [], "unmatchedFiles": []}
    all_matched = True
    all_rules = set()
    unmatched = []
    for f in files:
        matched, rules = match_feature_rules(f["name"])
        if matched:
            all_rules.update(rules)
        else:
            all_matched = False
            unmatched.append(f["name"])
    if all_matched:
        return {"canAutoApprove": True, "reason": "", "matchedRules": list(all_rules), "unmatchedFiles": []}
    return {"canAutoApprove": False, "reason": f"{len(unmatched)} 个文件不匹配特征码", "matchedRules": list(all_rules), "unmatchedFiles": unmatched}

# ============================================================
# FastAPI 应用
# ============================================================
app = FastAPI(title="SecureTrans API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def startup():
    init_db()

# ---------- 认证接口 ----------
@app.post("/api/auth/login")
def login(req: LoginRequest, request: Request):
    username = req.username.strip()
    # 支持 域\用户名 格式
    if "\\" in username:
        username = username.split("\\", 1)[1]
        source = "ad"
    elif "@" in username and username.endswith(("@nexskysemi.com", "@company.com")):
        username = username.split("@", 1)[0]
        source = "ad"
    else:
        source = "auto"

    # 先尝试本地
    user = authenticate_local(username, req.password)
    if user:
        token = create_token(user, "local")
        add_audit_log(username, "login", "", "本地用户登录成功", request.client.host if request.client else "")
        return {"token": token, "user": {
            "username": user["username"], "displayName": user["display_name"],
            "role": get_user_role(username, "local"), "source": "local"
        }}

    # 再尝试 AD
    if source in ("ad", "auto"):
        user = authenticate_ad(username, req.password)
        if user:
            token = create_token(user, "ad")
            add_audit_log(username, "login", "", "AD用户登录成功", request.client.host if request.client else "")
            return {"token": token, "user": {
                "username": username, "displayName": user.get("display_name", username),
                "role": get_user_role(username, "ad"), "source": "ad"
            }}

    add_audit_log(username, "login_failed", "", "登录失败", request.client.host if request.client else "")
    raise HTTPException(status_code=401, detail="用户名或密码错误")

@app.get("/api/auth/me")
def me(user: TokenData = Depends(get_current_user)):
    return {"username": user.username, "displayName": user.display_name, "role": user.role, "source": user.source}

@app.post("/api/auth/change-password")
def change_password(old_password: str = Form(...), new_password: str = Form(...), user: TokenData = Depends(get_current_user)):
    if user.source != "local":
        raise HTTPException(status_code=400, detail="AD用户请在域控制器修改密码")
    with db_conn() as conn:
        row = conn.execute("SELECT * FROM local_users WHERE username=?", (user.username,)).fetchone()
        if not row or not verify_password(old_password, row["password_hash"]):
            raise HTTPException(status_code=400, detail="原密码错误")
        new_hash = hash_password(new_password)
        conn.execute("UPDATE local_users SET password_hash=?, must_change_password=0 WHERE username=?", (new_hash, user.username))
    add_audit_log(user.username, "change_password", "", "修改密码成功")
    return {"message": "密码修改成功"}

# ---------- 文件上传与提交 ----------
@app.post("/api/submissions/upload")
async def upload_file(file: UploadFile = File(...), user: TokenData = Depends(get_current_user)):
    """上传单个文件到临时目录，计算MD5，返回文件信息"""
    if user.role not in ("internal-user", "admin"):
        raise HTTPException(status_code=403, detail="只有内网用户可以提交文件")
    temp_id = str(uuid.uuid4())
    temp_path = DATA_DIR / "temp" / temp_id
    temp_path.mkdir(parents=True, exist_ok=True)
    file_path = temp_path / file.filename
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)
    md5 = md5_file(file_path)
    size = len(content)
    ftype = get_file_type(file.filename)
    matched, rules = match_feature_rules(file.filename, file_path)
    # 压缩包自动解包列清单（PMF 阶段仅 zip）
    inner_files = []
    is_archive = file.filename.lower().endswith((".zip",))
    if is_archive:
        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                for info in zf.infolist():
                    if not info.is_dir():
                        inner_files.append({"name": info.filename, "size": info.file_size, "type": get_file_type(info.filename)})
        except Exception:
            pass
    return {
        "tempId": temp_id, "name": file.filename, "size": size, "type": ftype,
        "md5": md5, "matched": matched, "matchedRules": rules,
        "isArchive": is_archive, "innerFiles": inner_files,
    }

class SubmitRequest(BaseModel):
    tempIds: List[str]
    receiverName: str
    receiverEmail: str = ""
    receiverType: str = "non-partner"
    securityLevel: str = "internal"
    reason: str = ""
    expiryDays: int = 30

@app.post("/api/submissions")
def create_submission(req: SubmitRequest, user: TokenData = Depends(get_current_user), request: Request = None):
    """创建提交单：将临时文件移入归档目录，生成manifest，创建审批记录"""
    if user.role not in ("internal-user", "admin"):
        raise HTTPException(status_code=403, detail="只有内网用户可以提交文件")
    if not req.tempIds:
        raise HTTPException(status_code=400, detail="请先上传文件")
    if not req.receiverName:
        raise HTTPException(status_code=400, detail="请填写接收方姓名")

    sub_id = gen_submission_id()
    sub_archive = ARCHIVE_DIR / sub_id / "files"
    sub_archive.mkdir(parents=True, exist_ok=True)

    files_info = []
    total_size = 0
    for tid in req.tempIds:
        temp_dir = DATA_DIR / "temp" / tid
        if not temp_dir.exists():
            continue
        for f in temp_dir.iterdir():
            if f.is_file():
                dest = sub_archive / f.name
                f.rename(dest)
                md5 = md5_file(dest)
                ftype = get_file_type(f.name)
                matched, _ = match_feature_rules(f.name, dest)
                files_info.append({"name": f.name, "size": dest.stat().st_size, "type": ftype, "md5": md5, "matched": matched})
                total_size += dest.stat().st_size
        # 清理临时目录
        try:
            temp_dir.rmdir()
        except Exception:
            pass

    # 生成 manifest.json
    manifest = {"submissionId": sub_id, "submitTime": now_str(), "submitter": user.username, "files": files_info}
    with open(ARCHIVE_DIR / sub_id / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    # 免审批判定
    auto_result = check_auto_approval(files_info)
    auto_approved = 1 if auto_result["canAutoApprove"] else 0
    status = "ready" if auto_approved else "pending_approval_1"

    with db_conn() as conn:
        conn.execute(
            """INSERT INTO submissions (id,submitter,submitter_name,receiver_name,receiver_email,receiver_type,security_level,reason,expiry_days,status,auto_approved,archive_path,submit_time,file_count,total_size)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (sub_id, user.username, user.display_name, req.receiverName, req.receiverEmail, req.receiverType,
             req.securityLevel, req.reason, req.expiryDays, status, auto_approved, str(ARCHIVE_DIR / sub_id),
             now_str(), len(files_info), total_size)
        )
        for i, fi in enumerate(files_info):
            conn.execute(
                "INSERT INTO submission_files (id,submission_id,path,name,size,type,md5,matched,is_archive) VALUES (?,?,?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), sub_id, f"files/{fi['name']}", fi["name"], fi["size"], fi["type"], fi["md5"], 1 if fi["matched"] else 0, 0)
            )
        if auto_approved:
            conn.execute(
                "INSERT INTO approvals (id,submission_id,level,approver,approver_name,action,comment,time) VALUES (?,?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), sub_id, 0, "system", "系统", "approve", "免审批自动通过", now_str())
            )
            # 自动摆渡：创建外网软链接
            _create_external_symlink(sub_id)

    add_audit_log(user.username, "create_submission", sub_id, f"提交{len(files_info)}个文件，{'免审批自动通过' if auto_approved else '待审批'}", request.client.host if request and request.client else "")
    return {"id": sub_id, "status": status, "autoApproved": bool(auto_approved), "fileCount": len(files_info)}

def _create_external_symlink(sub_id: str):
    """创建外网软链接（零拷贝摆渡）"""
    target = ARCHIVE_DIR / sub_id
    link = EXTERNAL_DIR / sub_id
    try:
        if link.exists() or link.is_symlink():
            link.unlink()
        os.symlink(str(target), str(link), target_is_directory=True)
        logger.info("摆渡完成: %s -> %s", link, target)
    except Exception as e:
        logger.error("创建软链接失败: %s", e)
        # fallback: 复制
        import shutil
        shutil.copytree(str(target), str(link), dirs_exist_ok=True)

# ---------- 提交单查询 ----------
@app.get("/api/submissions")
def list_submissions(status: str = "", user: TokenData = Depends(get_current_user)):
    with db_conn() as conn:
        query = "SELECT * FROM submissions WHERE 1=1"
        params = []
        if user.role == "internal-user":
            query += " AND submitter=?"
            params.append(user.username)
        if status:
            query += " AND status=?"
            params.append(status)
        query += " ORDER BY submit_time DESC LIMIT 200"
        rows = conn.execute(query, params).fetchall()
    return [row_to_dict(r) for r in rows]

@app.get("/api/submissions/{sub_id}")
def get_submission(sub_id: str, user: TokenData = Depends(get_current_user)):
    with db_conn() as conn:
        sub = conn.execute("SELECT * FROM submissions WHERE id=?", (sub_id,)).fetchone()
        if not sub:
            raise HTTPException(status_code=404, detail="提交单不存在")
        files = conn.execute("SELECT * FROM submission_files WHERE submission_id=?", (sub_id,)).fetchall()
        approvals = conn.execute("SELECT * FROM approvals WHERE submission_id=? ORDER BY level,time", (sub_id,)).fetchall()
    return {**row_to_dict(sub), "files": [row_to_dict(f) for f in files], "approvals": [row_to_dict(a) for a in approvals]}

@app.get("/api/submissions/pending/my")
def my_pending_approvals(user: TokenData = Depends(get_current_user)):
    """待我审批的列表"""
    if user.role not in ("dept-manager", "executive", "admin"):
        return []
    with db_conn() as conn:
        if user.role == "executive":
            rows = conn.execute("SELECT * FROM submissions WHERE status='pending_approval_2' ORDER BY submit_time DESC").fetchall()
        else:
            rows = conn.execute("SELECT * FROM submissions WHERE status='pending_approval_1' ORDER BY submit_time DESC").fetchall()
    return [row_to_dict(r) for r in rows]

# ---------- 审批 ----------
class ApprovalRequest(BaseModel):
    action: str  # approve / reject
    comment: str = ""

@app.post("/api/submissions/{sub_id}/approve")
def approve_submission(sub_id: str, req: ApprovalRequest, user: TokenData = Depends(get_current_user), request: Request = None):
    if user.role not in ("dept-manager", "executive", "admin"):
        raise HTTPException(status_code=403, detail="没有审批权限")
    with db_conn() as conn:
        sub = conn.execute("SELECT * FROM submissions WHERE id=?", (sub_id,)).fetchone()
        if not sub:
            raise HTTPException(status_code=404, detail="提交单不存在")
        # 判断审批级别
        level = 1
        if sub["status"] == "pending_approval_2":
            level = 2
            if user.role not in ("executive", "admin"):
                raise HTTPException(status_code=403, detail="需要公司高管二级审批")
        elif sub["status"] == "pending_approval_1":
            level = 1
        else:
            raise HTTPException(status_code=400, detail="当前状态不需要审批")

        conn.execute(
            "INSERT INTO approvals (id,submission_id,level,approver,approver_name,action,comment,time) VALUES (?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), sub_id, level, user.username, user.display_name, req.action, req.comment, now_str())
        )

        if req.action == "reject":
            new_status = "rejected"
        elif level == 1:
            # 一级通过：合作方直接摆渡，非合作方进入二级
            if sub["receiver_type"] == "partner":
                new_status = "ready"
                _create_external_symlink(sub_id)
            else:
                new_status = "pending_approval_2"
        else:
            # 二级通过：摆渡
            new_status = "ready"
            _create_external_symlink(sub_id)

        conn.execute("UPDATE submissions SET status=? WHERE id=?", (new_status, sub_id))

    add_audit_log(user.username, f"approval_{req.action}", sub_id, f"{'通过' if req.action=='approve' else '驳回'}，级别{level}，备注：{req.comment}", request.client.host if request and request.client else "")
    return {"status": new_status, "message": "审批完成"}

# ---------- 外网下载 ----------
@app.get("/api/external/files")
def list_external_files(user: TokenData = Depends(get_current_user)):
    """已摆渡到外网的文件列表"""
    with db_conn() as conn:
        rows = conn.execute("SELECT * FROM submissions WHERE status='ready' ORDER BY submit_time DESC LIMIT 200").fetchall()
    return [row_to_dict(r) for r in rows]

@app.get("/api/external/{sub_id}/download/{filename}")
def download_file(sub_id: str, filename: str, user: TokenData = Depends(get_current_user)):
    """下载文件（通过外网软链接路径）"""
    file_path = EXTERNAL_DIR / sub_id / "files" / filename
    if not file_path.exists():
        # fallback: 直接从归档取
        file_path = ARCHIVE_DIR / sub_id / "files" / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    add_audit_log(user.username, "download", sub_id, f"下载文件: {filename}")
    return FileResponse(str(file_path), filename=filename)

# ---------- 用户管理 ----------
@app.get("/api/admin/local-users")
def list_local_users(user: TokenData = Depends(require_role("admin"))):
    with db_conn() as conn:
        rows = conn.execute("SELECT id,username,display_name,email,role,status,created_at FROM local_users ORDER BY created_at").fetchall()
    return [row_to_dict(r) for r in rows]

class LocalUserRequest(BaseModel):
    username: str
    password: str
    displayName: str = ""
    email: str = ""
    role: str = "internal-user"

@app.post("/api/admin/local-users")
def create_local_user(req: LocalUserRequest, user: TokenData = Depends(require_role("admin"))):
    with db_conn() as conn:
        exists = conn.execute("SELECT COUNT(*) as c FROM local_users WHERE username=?", (req.username,)).fetchone()["c"]
        if exists:
            raise HTTPException(status_code=400, detail="用户名已存在")
        conn.execute(
            "INSERT INTO local_users (id,username,password_hash,display_name,email,role,status,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), req.username, hash_password(req.password), req.displayName, req.email, req.role, "active", now_str())
        )
    add_audit_log(user.username, "create_local_user", req.username, f"创建本地用户，角色{req.role}")
    return {"message": "创建成功"}

@app.delete("/api/admin/local-users/{username}")
def delete_local_user(username: str, user: TokenData = Depends(require_role("admin"))):
    if username == "admin":
        raise HTTPException(status_code=400, detail="不能删除admin")
    with db_conn() as conn:
        conn.execute("DELETE FROM local_users WHERE username=?", (username,))
    add_audit_log(user.username, "delete_local_user", username, "删除本地用户")
    return {"message": "删除成功"}

@app.post("/api/admin/local-users/{username}/reset-password")
def reset_local_password(username: str, user: TokenData = Depends(require_role("admin"))):
    new_pwd = "Init@123456"
    with db_conn() as conn:
        conn.execute("UPDATE local_users SET password_hash=?, must_change_password=1 WHERE username=?", (hash_password(new_pwd), username))
    add_audit_log(user.username, "reset_password", username, "重置密码")
    return {"message": f"密码已重置为 {new_pwd}，用户首次登录需修改"}

# ---------- AD 角色映射 ----------
@app.get("/api/admin/role-mappings")
def list_role_mappings(user: TokenData = Depends(require_role("admin"))):
    with db_conn() as conn:
        rows = conn.execute("SELECT * FROM role_mappings ORDER BY granted_at DESC").fetchall()
    return [row_to_dict(r) for r in rows]

class RoleMappingRequest(BaseModel):
    principalType: str  # user / group
    principalValue: str
    displayName: str = ""
    role: str
    note: str = ""

@app.post("/api/admin/role-mappings")
def create_role_mapping(req: RoleMappingRequest, user: TokenData = Depends(require_role("admin"))):
    with db_conn() as conn:
        conn.execute(
            "INSERT INTO role_mappings (id,principal_type,principal_value,display_name,role,granted_by,granted_at,note) VALUES (?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), req.principalType, req.principalValue, req.displayName, req.role, user.username, now_str(), req.note)
        )
    add_audit_log(user.username, "create_role_mapping", req.principalValue, f"授予角色{req.role}，类型{req.principalType}")
    return {"message": "角色映射创建成功"}

@app.delete("/api/admin/role-mappings/{mapping_id}")
def delete_role_mapping(mapping_id: str, user: TokenData = Depends(require_role("admin"))):
    with db_conn() as conn:
        conn.execute("DELETE FROM role_mappings WHERE id=?", (mapping_id,))
    add_audit_log(user.username, "delete_role_mapping", mapping_id, "删除角色映射")
    return {"message": "删除成功"}

@app.post("/api/admin/ad/search")
def search_ad_user(keyword: str = Form(...), user: TokenData = Depends(require_role("admin"))):
    """搜索 AD 用户（PMF 阶段模拟，生产接入真实 LDAP 查询）"""
    if not AD_ENABLED:
        # 模拟返回
        mock = [
            {"username": "zhangsan", "displayName": "张三", "email": "zhangsan@nexskysemi.com", "department": "研发部"},
            {"username": "lisi", "displayName": "李四", "email": "lisi@nexskysemi.com", "department": "研发部"},
            {"username": "wangzong", "displayName": "王总", "email": "wangzong@nexskysemi.com", "department": "公司高管"},
        ]
        return [u for u in mock if keyword.lower() in u["username"].lower() or keyword in u["displayName"]]
    # TODO: 生产环境真实 AD 查询
    return []

# ---------- 系统配置 ----------
@app.get("/api/config/feature-rules")
def list_feature_rules(user: TokenData = Depends(get_current_user)):
    with db_conn() as conn:
        rows = conn.execute("SELECT * FROM feature_rules ORDER BY created_at").fetchall()
    return [row_to_dict(r) for r in rows]

@app.get("/api/config/system")
def get_system_config(user: TokenData = Depends(get_current_user)):
    with db_conn() as conn:
        rows = conn.execute("SELECT key,value FROM system_config").fetchall()
    return {r["key"]: r["value"] for r in rows}

@app.put("/api/config/system")
def update_system_config(config: Dict[str, str], user: TokenData = Depends(require_role("admin"))):
    with db_conn() as conn:
        for k, v in config.items():
            conn.execute("INSERT OR REPLACE INTO system_config (key,value) VALUES (?,?)", (k, str(v)))
    add_audit_log(user.username, "update_system_config", "", json.dumps(config, ensure_ascii=False))
    return {"message": "配置已保存"}

# ---------- 审计日志 ----------
@app.get("/api/audit-logs")
def list_audit_logs(action: str = "", user: str = "", limit: int = 200, user_obj: TokenData = Depends(require_role("admin", "dept-manager", "executive"))):
    with db_conn() as conn:
        query = "SELECT * FROM audit_logs WHERE 1=1"
        params = []
        if action:
            query += " AND action LIKE ?"
            params.append(f"%{action}%")
        if user:
            query += " AND user LIKE ?"
            params.append(f"%{user}%")
        query += " ORDER BY time DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
    return [row_to_dict(r) for r in rows]

# ---------- 统计 ----------
@app.get("/api/stats")
def get_stats(user: TokenData = Depends(get_current_user)):
    with db_conn() as conn:
        today = datetime.date.today().strftime("%Y-%m-%d")
        today_count = conn.execute("SELECT COUNT(*) as c FROM submissions WHERE submit_time LIKE ?", (f"{today}%",)).fetchone()["c"]
        pending = conn.execute("SELECT COUNT(*) as c FROM submissions WHERE status LIKE 'pending%'").fetchone()["c"]
        ready = conn.execute("SELECT COUNT(*) as c FROM submissions WHERE status='ready'").fetchone()["c"]
        auto = conn.execute("SELECT COUNT(*) as c FROM submissions WHERE auto_approved=1").fetchone()["c"]
        total = conn.execute("SELECT COUNT(*) as c FROM submissions").fetchone()["c"]
        files = conn.execute("SELECT COUNT(*) as c FROM submission_files").fetchone()["c"]
    return {
        "todaySubmitted": today_count, "pendingApproval": pending, "ready": ready,
        "autoApprovalRate": round(auto / total * 100, 1) if total else 0,
        "archivedFiles": files, "avgFerryTime": "~0.1s",
    }

# ---------- 健康检查 ----------
@app.get("/api/health")
def health():
    return {"status": "ok", "time": now_str(), "version": "1.0.0"}

# ---------- 静态文件（前端页面） ----------
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

# ============================================================
# 启动
# ============================================================
if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    logger.info("SecureTrans 启动: http://%s:%s", host, port)
    uvicorn.run(app, host=host, port=port)
