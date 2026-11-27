"""
SecureTrans - 轻量级跨网文件审批摆渡系统 后端
Flask + Flask-Login + SQLite + os.rename 0拷贝摆渡
适配初创公司 50 人规模（版本号见 APP_VERSION 常量）
"""
import os
import sys
import re
import json
import time
import uuid
import shutil
import sqlite3
import hashlib
import secrets
import ipaddress
import logging
import datetime
import threading
import urllib.request
import urllib.error
from pathlib import Path
from functools import wraps

from flask import Flask, request, jsonify, send_file, redirect, url_for, session, g
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import bcrypt

# ============================================================
# 配置
# ============================================================
BASE_DIR = Path(__file__).parent.resolve()

# 12-Factor 配置加载（ADR-016）：启动时加载同目录 .env（若存在）到环境变量。
# - 不覆盖已注入的环境变量（生产 systemd EnvironmentFile 优先，行为不变）；
# - 开发/测试直接 `python app.py` 时 .env（src/.env / env 模板复制）自动生效。
_ENV_FILE_PATH = BASE_DIR / ".env"
if _ENV_FILE_PATH.exists():
    try:
        for _line in _ENV_FILE_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                _k = _k.strip()
                if _k and _k not in os.environ:
                    os.environ[_k] = _v.strip().strip('"').strip("'")
    except Exception:
        pass  # .env 解析失败不阻塞启动（后续按环境变量/默认值运行）
DATA_DIR = Path(os.getenv("SECURETRANS_DATA", str(BASE_DIR / "data")).strip()).resolve()
DB_PATH = DATA_DIR / "securetrans.db"
LOG_PATH = DATA_DIR / "securetrans.log"

# 存储目录（必须在同一个文件系统，os.rename 才能 0拷贝）
# v2.5.0: .resolve() 强制绝对路径——Flask send_file 会 join app.root_path（src/），
# 若 NAS_ROOT 为相对路径（如 ./nas）会把文件路径错拼为 src/nas/... 导致下载 500（FileNotFoundError）
NAS_ROOT = Path(os.getenv("NAS_ROOT", str(BASE_DIR / "nas")).strip()).resolve()  # strip 防 .env CRLF 污染(CR)
STAGING_DIR = NAS_ROOT / "staging"    # 刚上传，待审核
EXTERNAL_DIR = NAS_ROOT / "external"   # 审核通过，可外网下载
ARCHIVE_DIR = NAS_ROOT / "archive"     # 过期/驳回，永久归档
STATIC_DIR = BASE_DIR / "static"

# 统一时间格式（now_str 与解析共用，避免多处不一致）
TS_FMT = "%Y-%m-%d %H:%M:%S"
APP_VERSION = "v2.7.3"  # 系统版本号（唯一来源，与前端 APP_VERSION 一致）
# 发布阶段（.env APP_STAGE 可配）：alpha=自测 / beta=内部测试 / rtm=内部使用 / release=正式发布
# 显示为 vX.Y.Z-<stage>，用于页面/健康检查标识当前交付阶段
APP_STAGE = os.getenv("APP_STAGE", "alpha").strip().lower()
# 环境角色（ADR-017 测试/生产隔离）：test=开发/测试环境（允许全量写测试） / prod=生产环境（写测试 fail-safe 拒绝）
# 默认 prod：宁可误拒不可误写（.env 未配置时生产安全优先）
ENV_ROLE = os.getenv("ENV_ROLE", "prod").strip().lower()

# 安全配置
SECRET_KEY = os.getenv("SECRET_KEY", "securetrans-dev-secret-change-in-production")
# 上传上限（v2.2.24）：MAX_FILE_SIZE_MB 为单文件大小上限（MB，默认800）；
# 请求体限制 MAX_CONTENT_LENGTH = 文件上限 + 1MB（multipart 封装余量），
# 否则 800MB 文件 + boundary 封装会触发 413。
_legacy_mcl = os.getenv("MAX_CONTENT_LENGTH", "").strip()
if _legacy_mcl and not os.getenv("MAX_FILE_SIZE_MB", "").strip():
    # 兼容旧 .env：仅配置了 MAX_CONTENT_LENGTH 时，请求体限制=该值，文件上限=该值-1MB
    MAX_CONTENT_LENGTH = int(_legacy_mcl)
    MAX_FILE_SIZE_MB = max(1, MAX_CONTENT_LENGTH // 1024 // 1024 - 1)
else:
    MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "800").strip())
    MAX_FILE_SIZE_MB = max(1, MAX_FILE_SIZE_MB)
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024
if not (_legacy_mcl and not os.getenv("MAX_FILE_SIZE_MB", "").strip()):
    MAX_CONTENT_LENGTH = MAX_FILE_SIZE + 1024 * 1024  # 文件 + multipart 封装余量(1MB)

# 部署模式：testing（本地文件系统+Flask自带服务器）/ production（NAS+gunicorn）
# testing 为默认值，适合开发和测试环境验证；生产环境设为 production
DEPLOY_MODE = os.getenv("DEPLOY_MODE", "testing").strip().lower()
if DEPLOY_MODE not in ("testing", "production"):
    DEPLOY_MODE = "testing"

# AD 配置（LDAP 直连，与 sssd 兼容）
AD_ENABLED = os.getenv("AD_ENABLED", "false").lower() == "true"
AD_HOST = os.getenv("AD_HOST", "")
AD_DOMAIN = os.getenv("AD_DOMAIN", "")
AD_BASE_DN = os.getenv("AD_BASE_DN", "")
AD_BIND_DN = os.getenv("AD_BIND_DN", "")
AD_BIND_PASSWORD = os.getenv("AD_BIND_PASSWORD", "")
# AD 属性字段（可配置，默认值与 AD 标准属性一致；如企业 AD 用其他字段可在此调整）
AD_USER_FIELD = os.getenv("AD_USER_FIELD", "sAMAccountName").strip()  # 登录名查询字段
AD_DISPLAY_FIELD = os.getenv("AD_DISPLAY_FIELD", "displayName").strip()  # 显示名属性
AD_MAIL_FIELD = os.getenv("AD_MAIL_FIELD", "mail").strip()  # 邮箱属性
AD_GROUP_FIELD = os.getenv("AD_GROUP_FIELD", "memberOf").strip()  # 组属性
# AD 配置键映射（ADR-010：运行期以 SQLite ad_config 优先，.env 为 fallback/部署种子；管理页可配置）
AD_ENV_MAP = {
    "ad_enabled": "AD_ENABLED", "ad_host": "AD_HOST", "ad_domain": "AD_DOMAIN",
    "ad_base_dn": "AD_BASE_DN", "ad_bind_dn": "AD_BIND_DN", "ad_bind_password": "AD_BIND_PASSWORD",
    "ad_user_field": "AD_USER_FIELD", "ad_display_field": "AD_DISPLAY_FIELD",
    "ad_mail_field": "AD_MAIL_FIELD", "ad_group_field": "AD_GROUP_FIELD",
}

# 过期清理配置
EXTERNAL_EXPIRY_DAYS = int(os.getenv("EXTERNAL_EXPIRY_DAYS", "7"))  # external 文件默认 7 天过期
RESET_PASSWORD = os.getenv("RESET_PASSWORD", "Init@123456").strip()  # 重置密码默认值，可配置(.env)
AUTO_APPROVAL_ENABLED = os.getenv("AUTO_APPROVAL_ENABLED", "false").strip().lower()  # 免审批总开关默认关闭

# ---- 飞书通知（ADR-051：独立旁路通道，失败绝不阻塞提交/审批）----
# 关闭时（默认）所有通知记为 skipped，业务照常；开启后走通知网关（ADR-052），不在本机直连飞书。
FEISHU_NOTIFY_ENABLED = os.getenv("FEISHU_NOTIFY_ENABLED", "false").strip().lower() == "true"
FEISHU_NOTIFY_URL = os.getenv("FEISHU_NOTIFY_URL", "").strip()          # 例：http://<网关>:8090/notify
FEISHU_NOTIFY_TOKEN = os.getenv("FEISHU_NOTIFY_TOKEN", "").strip()      # 预共享 token（网关 .env 同值）
FEISHU_NOTIFY_TIMEOUT = float(os.getenv("FEISHU_NOTIFY_TIMEOUT", "5") or 5)
FEISHU_NOTIFY_APP_URL = os.getenv("FEISHU_NOTIFY_APP_URL", "").strip()  # 消息里的系统入口，默认按请求 Host 推出

# 网络面识别（单网卡模式按网段区分内外网；逗号分隔 CIDR，留空则不启用网段识别）
INTERNAL_CIDRS = os.getenv("INTERNAL_CIDRS", "").strip()

# 日志
DATA_DIR.mkdir(parents=True, exist_ok=True)
for d in [STAGING_DIR, EXTERNAL_DIR, ARCHIVE_DIR, STATIC_DIR]:
    d.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(str(LOG_PATH), encoding="utf-8"), logging.StreamHandler()]
)
logger = logging.getLogger("securetrans")

# ============================================================
# Flask 应用初始化
# ============================================================
app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="")
app.config["SECRET_KEY"] = SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# ============================================================
# 双语（i18n）——后端错误/成功消息自动附加英文
# 设计：所有 jsonify 返回的 error/message 由 after_request 钩子自动补 error_en/message_en，
#      前端按当前界面语言（zh/en）选择显示。前端静态界面文案由前端 I18N 字典管理。
# ============================================================
I18N_ERRORS = {
    "admin 为系统内置管理员，永久使能，不可禁用": "admin is the built-in administrator, permanently enabled and cannot be disabled",
    "AD用户请在域控制器修改密码": "AD users must change password on the domain controller",
    "不能删除admin": "Cannot delete admin",
    "参数不完整": "Incomplete parameters",
    "当前状态不需要审批": "Current status does not require approval",
    "该审批人已配置在此级别": "This approver is already configured at this level",
    "规则不存在": "Rule not found",
    "规则类型只能为 extension/filename/binary": "Rule type must be extension/filename/binary",
    "规则名称和匹配模式不能为空": "Rule name and pattern cannot be empty",
    "合作方不存在": "Partner not found",
    "合作方名称不能为空": "Partner name cannot be empty",
    "合作方已存在": "Partner already exists",
    "角色仅支持 admin / internal-user（审批权限请在审批人配置中设置）": "Role only supports admin / internal-user (approval rights are set in approver config)",
    "接口不存在": "API endpoint not found",
    "没有有效文件": "No valid files",
    "密码至少6位": "Password must be at least 6 characters",
    "请输入用户名和密码": "Please enter username and password",
    "请输入原密码和新密码": "Please enter current and new password",
    "请填写接收方单位": "Please fill in recipient organization",
    "请填写接收方姓名": "Please fill in recipient name",
    "请先上传文件": "Please upload files first",
    "请选择文件": "Please select a file",
    "权限不足": "Insufficient permissions",
    "日期格式错误，应为 YYYY-MM-DD": "Invalid date format, expected YYYY-MM-DD",
    "审批级别只能为1或2": "Approval level must be 1 or 2",
    "审批人用户名不能为空": "Approver username cannot be empty",
    "提交单不存在": "Submission not found",
    "外网面仅提供文件下载服务，管理操作请从内网访问": "External network only provides file download; management operations must be accessed from internal network",
    "请输入确认码 RESTORE": "Please enter confirmation code RESTORE",
    "请输入确认码 RESET": "Please enter confirmation code RESET",
    "请输入确认码 MOCK": "Please enter confirmation code MOCK",
    "删除需确认码 DEL": "Deletion requires confirmation code DEL",
    "备份不存在": "Backup not found",
    "生产/预生产环境禁止生成模拟数据（ADR-011）": "Mock data generation is forbidden in production/pre-production environments (ADR-011)",
    "文件不存在": "File not found",
    "文件不可下载": "File is not downloadable",
    "文件名不能为空": "Filename cannot be empty",
    "无效的操作": "Invalid action",
    "新密码至少6位": "New password must be at least 6 characters",
    "需要部门主管一级审批": "Department head (Level 1) approval required",
    "需要公司高管二级审批": "Company executive (Level 2) approval required",
    "用户不存在": "User not found",
    "用户名和密码不能为空": "Username and password cannot be empty",
    "用户名或密码错误": "Incorrect username or password",
    "用户名已存在": "Username already exists",
    "原密码错误": "Incorrect current password",
    "请先登录": "Please log in first",
}
I18N_MESSAGES = {
    "创建成功": "Created successfully",
    "登录成功": "Logged in successfully",
    "规则创建成功": "Rule created successfully",
    "规则已更新": "Rule updated",
    "规则已删除": "Rule deleted",
    "合作方添加成功": "Partner added successfully",
    "角色映射创建成功": "Role mapping created successfully",
    "密码修改成功": "Password changed successfully",
    "配置已保存": "Configuration saved",
    "删除成功": "Deleted successfully",
    "审批人配置成功": "Approver configured successfully",
    "审批完成": "Approval completed",
    "已退出登录": "Logged out",
}
I18N_ERROR_TEMPLATES = [
    (re.compile(r"^文件过大，最大支持 (\d+)MB$"), lambda m: f"File too large, max {m.group(1)}MB"),
]
I18N_MESSAGE_TEMPLATES = [
    (re.compile(r"^规则已(启用|禁用)$"), lambda m: f"Rule {'enabled' if m.group(1) == '启用' else 'disabled'}"),
    (re.compile(r"^合作方已(启用|禁用)$"), lambda m: f"Partner {'enabled' if m.group(1) == '启用' else 'disabled'}"),
    (re.compile(r"^用户已(启用|禁用)$"), lambda m: f"User {'enabled' if m.group(1) == '启用' else 'disabled'}"),
    (re.compile(r"^密码已重置为 (\S+)，用户首次登录需修改$"), lambda m: f"Password reset to {m.group(1)}, user must change on first login"),
    (re.compile(r"^清理完成，共处理 (\d+) 个过期文件$"), lambda m: f"Cleanup completed, {m.group(1)} expired file{'s' if int(m.group(1)) != 1 else ''} processed"),
]

def _i18n_translate(text, is_error=False):
    """把中文消息翻译为英文；未命中字典/模板时保持原文（前端可回退显示中文）。"""
    if not isinstance(text, str) or not text:
        return text
    d = I18N_ERRORS if is_error else I18N_MESSAGES
    if text in d:
        return d[text]
    templates = I18N_ERROR_TEMPLATES if is_error else I18N_MESSAGE_TEMPLATES
    for pat, fn in templates:
        m = pat.match(text)
        if m:
            return fn(m)
    return text

@app.after_request
def _i18n_attach_en(resp):
    """自动为 JSON 响应附加英文消息（error_en / message_en），前端按语言显示。"""
    if not resp.is_json:
        return resp
    data = resp.get_json(silent=True)
    if not isinstance(data, dict):
        return resp
    changed = False
    if "error" in data and "error_en" not in data:
        data["error_en"] = _i18n_translate(data["error"], is_error=True)
        changed = True
    if "message" in data and "message_en" not in data:
        data["message_en"] = _i18n_translate(data["message"], is_error=False)
        changed = True
    if changed:
        resp.set_data(json.dumps(data, ensure_ascii=False))
        resp.headers["Content-Type"] = "application/json; charset=utf-8"
    return resp

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login_page"
login_manager.login_message = "请先登录"

# ============================================================
# 数据库
# ============================================================
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(str(DB_PATH))
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()

# 内置特征码规则模板（v2.2.23 起为模块级常量）：播种 + 升级迁移共用
# 安全策略：内置=模板，默认全部禁用（enabled=0）；管理员按需启用；即使免审批总开关开启，
# 无启用的规则则无匹配 → 全部走人工审批（默认保守）
# v2.6.0（ADR-029）：压缩包类"后缀名规则 + 二进制特征码规则"合并为唯一组合规则（特征码 AND 后缀），
#   更严格更合理（单规则即完整判定，不再"后缀命中即匹配"或"仅特征命中即匹配"）；内置规则 21 -> 15 条。
#   配置持久化：内置模板仅首次播种/补充播种时默认禁用，已存在规则尊重管理员配置（升级不重置 enabled）。
BUILTIN_FEATURE_RULES = [
    # === 文档类（extension）===
    ("PDF文档", "extension", ".pdf", 0, None),
    ("Word文档", "extension", ".doc,.docx", 0, None),
    ("Excel表格", "extension", ".xls,.xlsx", 0, None),
    ("PPT演示", "extension", ".ppt,.pptx", 0, None),
    ("图片文件", "extension", ".png,.jpg,.jpeg,.gif,.bmp,.svg", 0, None),
    ("文本文件", "extension", ".txt,.csv,.md,.log,.json,.xml,.yaml,.yml", 0, None),
    # === 压缩包类（组合规则：二进制特征码 AND 后缀，v2.6.0 合并）===
    ("ZIP压缩包(特征码+后缀)", "binary", "hex:504B0304", 0, ".zip"),
    ("TAR归档(特征码+后缀)", "binary", "ustar", 0, ".tar"),
    ("GZIP压缩(特征码+后缀)", "binary", "hex:1F8B", 0, ".gz"),
    ("TAR.GZ组合(特征码+后缀)", "binary", "hex:1F8B", 0, ".tar.gz,.tgz"),
    ("BZIP2压缩(特征码+后缀)", "binary", "hex:425A68", 0, ".bz2,.tbz2"),
    ("XZ压缩(特征码+后缀)", "binary", "hex:FD377A585A00", 0, ".xz,.txz"),
    ("ZSTD压缩(特征码+后缀)", "binary", "hex:28B52FFD", 0, ".zst"),
    # === FPGA / EDA ===
    # v2.5.0: 同步字支持双字节序——BE 0xAA995566（.bit 原始流）/ LE 0x665599AA（Zynq BOOT.BIN 封装）
    # v2.5.1: Vivado 精简为唯一组合规则（特征码 AND .bin/.bit）。删除旧"扩展名 .bit 独立规则"与
    # "仅同步字无后缀规则"（过宽易误报、组合规则已全覆盖，迁移中自动清理）。
    # v2.6.0: .ltx（Vivado ILA 调试探针，JSON 文本）从"纯扩展名规则"升级为组合规则——
    #   特征码 hex:7B226C74785F726F6F74 = `{"ltx_root`（标准 JSON 根键，4KB 头内）AND 后缀 .ltx
    # v2.6.1（ADR-030）: Vivado 实际生成的 .ltx 为格式化 JSON（`{\n    "ltx_root":`，带换行与缩进），
    #   紧凑 hex 特征 `{"ltx_root` 不匹配 → 改为文本特征码 `"ltx_root"`（UTF-8 子串，兼容紧凑/格式化两种 JSON 排版）
    ("Vivado Bitstream组合(特征码+后缀)", "binary", "hex:AA995566;665599AA", 0, ".bin,.bit"),
    ("Vivado ILA探针组合(特征码+后缀)", "binary", "\"ltx_root\"", 0, ".ltx"),
]

def init_db():
    """初始化数据库表和初始数据"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS local_users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        display_name TEXT,
        email TEXT,
        role TEXT DEFAULT 'internal-user',
        status TEXT DEFAULT 'active',
        enabled INTEGER DEFAULT 1,
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
        receiver_org TEXT,
        security_level TEXT,
        reason TEXT,
        expiry_days INTEGER DEFAULT 7,
        status TEXT DEFAULT 'pending',
        auto_approved INTEGER DEFAULT 0,
        current_path TEXT,
        submit_time TEXT,
        approved_time TEXT,
        archived_time TEXT,
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
        FOREIGN KEY (submission_id) REFERENCES submissions(id) ON DELETE CASCADE
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
        FOREIGN KEY (submission_id) REFERENCES submissions(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS feature_rules (
        id TEXT PRIMARY KEY,
        name TEXT,
        rule_type TEXT,
        pattern TEXT,
        enabled INTEGER DEFAULT 1,
        created_at TEXT,
        ext_pattern TEXT
    );

    CREATE TABLE IF NOT EXISTS partners (
        id TEXT PRIMARY KEY,
        name TEXT,
        contact TEXT,
        email TEXT,
        enabled INTEGER DEFAULT 1,
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

    CREATE TABLE IF NOT EXISTS download_records (
        id TEXT PRIMARY KEY,
        submission_id TEXT,
        filename TEXT,
        downloader TEXT,
        download_time TEXT,
        ip TEXT,
        md5 TEXT
    );

    -- 飞书通知投递记录（ADR-051：旁路通道，独立于业务状态；失败只影响本条记录）
    CREATE TABLE IF NOT EXISTS notification_logs (
        id TEXT PRIMARY KEY,
        submission_id TEXT,
        event TEXT,
        recipients TEXT,   -- 脱敏后的收件人清单（逗号分隔）
        status TEXT,       -- sent / partial / failed / skipped（disabled 归入 skipped）
        detail TEXT,       -- 失败原因或跳过原因，供界面定位
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS ad_config (
        key TEXT PRIMARY KEY,
        value TEXT,
        source TEXT DEFAULT 'db',
        updated_at TEXT
    );
    """)

    # ---- 数据库迁移（兼容已存在的旧库，补列）----
    def _column_exists(table, col):
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        return col in cols

    if not _column_exists("local_users", "enabled"):
        try:
            conn.execute("ALTER TABLE local_users ADD COLUMN enabled INTEGER DEFAULT 1")
        except sqlite3.OperationalError:
            pass  # 并发迁移时列已存在，忽略
    if not _column_exists("partners", "enabled"):
        try:
            conn.execute("ALTER TABLE partners ADD COLUMN enabled INTEGER DEFAULT 1")
        except sqlite3.OperationalError:
            pass
    if not _column_exists("submissions", "receiver_org"):
        try:
            conn.execute("ALTER TABLE submissions ADD COLUMN receiver_org TEXT")
        except sqlite3.OperationalError:
            pass
    if not _column_exists("download_records", "md5"):
        try:
            conn.execute("ALTER TABLE download_records ADD COLUMN md5 TEXT")
        except sqlite3.OperationalError:
            pass
    if not _column_exists("feature_rules", "ext_pattern"):
        try:
            conn.execute("ALTER TABLE feature_rules ADD COLUMN ext_pattern TEXT")
        except sqlite3.OperationalError:
            pass
    conn.commit()

    # 初始管理员（幂等插入）
    # 注意：gunicorn 多 worker 并发启动时，每个 worker 都执行 init_db()。
    # 若用 SELECT-COUNT + INSERT 检查，两个 worker 可能同时判定 admin 不存在并插入 → UNIQUE 冲突，
    # 导致 worker 启动失败。必须用 INSERT OR IGNORE（用户名 UNIQUE 约束冲突时忽略，幂等安全）。
    # 密码 = RESET_PASSWORD（默认 Init@123456）：与 deploy.sh 部署重置 / verify.sh 测试凭据 /
    # 登录页提示 统一同源，全链路一致（ADR-013 密码策略）。must_change_password=1 仅作"建议修改"提示，不强制。
    admin_hash = bcrypt.hashpw(RESET_PASSWORD.encode(), bcrypt.gensalt()).decode()
    conn.execute(
        "INSERT OR IGNORE INTO local_users (id,username,password_hash,display_name,email,role,status,must_change_password,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (str(uuid.uuid4()), "admin", admin_hash, "系统管理员", "admin@localhost", "admin", "active", 1, now_str())
    )
    # 默认审批人（v2.2.31，ADR-015）：admin 显式播种为一级+二级审批人，保证提交审批逻辑闭环。
    # v2.6.1（ADR-030）修正：仅【首次初始化】播种一次（approvers_initialized 标记，幂等）；
    # 后续启动/升级【绝不自动补回】——审批人由管理员人工配置（删除即删除，避免"删除后重启被补回"）；
    # 无一级/二级审批人时提交 API 已提供明确失败提醒（"未配置一级审批人/二级审批人"）。
    _init_appr = conn.execute(
        "SELECT COUNT(*) as c FROM system_config WHERE key='approvers_initialized'").fetchone()["c"]
    if _init_appr == 0:
        _seed_admin = conn.execute("SELECT COUNT(*) as c FROM approvers WHERE level=1 AND username='admin'").fetchone()["c"]
        if _seed_admin == 0:
            conn.execute("INSERT INTO approvers (id,level,username,display_name,scope) VALUES (?,?,?,?,?)",
                         (str(uuid.uuid4()), 1, "admin", "系统管理员", "all"))
        _seed_admin2 = conn.execute("SELECT COUNT(*) as c FROM approvers WHERE level=2 AND username='admin'").fetchone()["c"]
        if _seed_admin2 == 0:
            conn.execute("INSERT INTO approvers (id,level,username,display_name,scope) VALUES (?,?,?,?,?)",
                         (str(uuid.uuid4()), 2, "admin", "系统管理员", "all"))
        conn.execute("INSERT OR IGNORE INTO system_config (key,value) VALUES ('approvers_initialized','1')")

    # 初始系统配置：单一来源 = .env（AUTO_APPROVAL_ENABLED / EXTERNAL_EXPIRY_DAYS / MAX_CONTENT_LENGTH）
    defaults = {
        "auto_approval_enabled": os.getenv("AUTO_APPROVAL_ENABLED", "false").strip().lower(),
        "default_expiry_days": os.getenv("EXTERNAL_EXPIRY_DAYS", "7").strip(),
        "max_file_size_mb": str(MAX_FILE_SIZE_MB),
        "max_batch_files": os.getenv("MAX_BATCH_FILES", "18").strip(),
        "app_name": "SecureTrans",
    }
    for k, v in defaults.items():
        conn.execute("INSERT OR IGNORE INTO system_config (key,value) VALUES (?,?)", (k, v))
    # 旧库迁移：免审批开关旧默认 true（硬编码）→ 与 .env 默认 false 对齐（仅当 env 未显式设置时）
    if "AUTO_APPROVAL_ENABLED" not in os.environ:
        _row = conn.execute("SELECT value FROM system_config WHERE key='auto_approval_enabled'").fetchone()
        if _row and _row["value"] == "true":
            conn.execute("UPDATE system_config SET value='false' WHERE key='auto_approval_enabled'")

    # 初始特征码规则
    # v2.4.0 修正：Xilinx 标准同步字为 0xAA995566；旧模板误写 hex:5599AA66，自动修正 pattern
    _fix = conn.execute(
        "UPDATE feature_rules SET pattern='hex:AA995566' WHERE name='Vivado Bit同步字' AND pattern='hex:5599AA66'")
    if _fix.rowcount:
        logger.info("feature_rules 修正：Vivado Bit同步字 pattern 5599AA66 → AA995566（Xilinx 标准同步字）")
    # v2.5.0 迁移：Vivado 同步字支持双字节序（BE AA995566 / LE 665599AA，Zynq BOOT.BIN 场景）
    _fix2 = conn.execute(
        "UPDATE feature_rules SET pattern='hex:AA995566;665599AA' "
        "WHERE name IN ('Vivado Bitstream组合(特征码+后缀)','Vivado Bit同步字') AND pattern='hex:AA995566'")
    if _fix2.rowcount:
        logger.info("feature_rules 迁移：Vivado 同步字 pattern 扩展为双字节序 hex:AA995566;665599AA（BE/LE）")
    # v2.5.1 迁移：删除旧 Vivado 内置规则（扩展名 .bit 独立规则 + 仅同步字规则），保留唯一组合规则
    # 注：内置模板播种时 ext_pattern 均为 NULL（extension 规则 pattern 即扩展名），故按 NULL 匹配
    _legacy_del = conn.execute(
        "DELETE FROM feature_rules WHERE (name='Vivado Bitstream(.bit)' AND rule_type='extension' AND ext_pattern IS NULL) "
        "OR (name='Vivado Bit同步字' AND rule_type='binary' AND ext_pattern IS NULL)")
    if _legacy_del.rowcount:
        logger.info(f"feature_rules 清理：删除旧 Vivado 规则 {_legacy_del.rowcount} 条（v2.5.1，保留组合规则）")
    # v2.5.1 迁移：删除历史遗留的"内部提交幻影二级审批记录"
    # 背景：旧版 approve 端点对 receiver_type='internal' 也走了"语义B自动跳过二级"分支，
    # 错误写入 level=2 的"自动跳过二级"审批记录（内部提交仅一级流程，审计链不应出现二级记录）。
    # 仅删除 comment 精确匹配"自动跳过二级"且所属提交为 internal 的记录，不影响人工二级审批记录。
    _clean = conn.execute(
        "DELETE FROM approvals WHERE level=2 AND comment='自动跳过二级：审批人同时具备一级和二级审批权限' "
        "AND submission_id IN (SELECT id FROM submissions WHERE receiver_type='internal')")
    if _clean.rowcount:
        logger.info(f"审计修复：删除 internal 提交的幻影二级审批记录 {_clean.rowcount} 条（v2.5.1）")

    # v2.6.0（ADR-029）压缩包双规则合并迁移：删除旧"后缀名独立规则"与"二进制特征码独立规则"（12 条），
    # 以及旧"Vivado ILA探针(.ltx)"纯扩展名规则；仅精确匹配 name+type+pattern+ext_pattern 的内置模板，
    # 用户自定义规则不受影响。新组合规则由下方补充播种插入（默认禁用模板）。
    _merge_pairs = [
        ("ZIP压缩包", "extension", ".zip", None),
        ("TAR归档", "extension", ".tar", None),
        ("GZIP压缩", "extension", ".gz,.tgz", None),
        ("BZIP2压缩", "extension", ".bz2,.tbz2", None),
        ("XZ压缩", "extension", ".xz,.txz", None),
        ("ZSTD压缩", "extension", ".zst", None),
        ("ZIP特征码", "binary", "hex:504B0304", None),
        ("GZIP特征码", "binary", "hex:1F8B", None),
        ("BZIP2特征码", "binary", "hex:425A68", None),
        ("XZ特征码", "binary", "hex:FD377A585A00", None),
        ("ZSTD特征码", "binary", "hex:28B52FFD", None),
        ("TAR特征码(ustar)", "binary", "ustar", None),
        ("Vivado ILA探针(.ltx)", "extension", ".ltx", None),
    ]
    _merge_sql = "DELETE FROM feature_rules WHERE " + " OR ".join(
        ["(name=? AND rule_type=? AND pattern=? AND ext_pattern IS ?)"] * len(_merge_pairs))
    _merge_arch = conn.execute(_merge_sql, [v for _pair in _merge_pairs for v in _pair])
    if _merge_arch.rowcount:
        logger.info(f"feature_rules 迁移：删除压缩包双规则与旧 .ltx 规则 {_merge_arch.rowcount} 条（v2.6.0 合并为组合规则）")

    # v2.6.1（ADR-030）迁移：.ltx 特征码升级——Vivado 实际生成的 .ltx 为格式化 JSON
    # （`{\n    "ltx_root":`，带换行与缩进），紧凑 hex 特征 `{"ltx_root` 无法命中真实生产文件；
    # 升级为文本特征码 `"ltx_root"`（UTF-8 子串匹配，兼容紧凑/格式化两种 JSON 排版）。
    # 精确匹配 v2.6.0 内置模板（name+type+pattern+ext_pattern），用户自定义修改不受影响。
    _ltx_fix = conn.execute(
        "UPDATE feature_rules SET pattern='\"ltx_root\"' "
        "WHERE name='Vivado ILA探针组合(特征码+后缀)' AND rule_type='binary' AND pattern='hex:7B226C74785F726F6F74' AND ext_pattern='.ltx'")
    if _ltx_fix.rowcount:
        logger.info(f"feature_rules 迁移：.ltx 特征码升级为文本 `\"ltx_root\"`（v2.6.1，兼容格式化 JSON）")

    cursor = conn.execute("SELECT COUNT(*) as c FROM feature_rules")
    if cursor.fetchone()["c"] == 0:
        # 内置特征码规则作为【模板】，默认全部禁用（enabled=0），由管理员按需启用。
        for name, rtype, pattern, enabled, ext_pattern in BUILTIN_FEATURE_RULES:
            conn.execute(
                "INSERT INTO feature_rules (id,name,rule_type,pattern,enabled,created_at,ext_pattern) VALUES (?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), name, rtype, pattern, enabled, now_str(), ext_pattern)
            )
    else:
        # v2.6.0（ADR-029）：配置持久化——内置模板的"默认禁用"仅对首次播种/新补充播种生效；
        # 已存在规则（含管理员已启用的内置模板）尊重管理员配置，升级/重启不重置 enabled。
        # 补充播种：新内置模板（如合并后的组合规则）在既有库中不存在时补插（默认禁用，安全）
        for _name, _rtype, _pattern, _enabled, _ext in BUILTIN_FEATURE_RULES:
            _exists = conn.execute(
                "SELECT 1 FROM feature_rules WHERE name=? AND rule_type=? AND pattern=? AND ext_pattern IS ? LIMIT 1",
                (_name, _rtype, _pattern, _ext)).fetchone()
            if not _exists:
                conn.execute(
                    "INSERT INTO feature_rules (id,name,rule_type,pattern,enabled,created_at,ext_pattern) VALUES (?,?,?,?,?,?,?)",
                    (str(uuid.uuid4()), _name, _rtype, _pattern, _enabled, now_str(), _ext))
                logger.info("feature_rules 补充播种：%s（enabled=0 模板）", _name)

    # 播种 ad_config（ADR-010）：表空时从 .env 读入一次（source=env），此后以管理页保存值（source=db）为准
    seed_rows = conn.execute("SELECT COUNT(*) as c FROM ad_config").fetchone()
    if seed_rows["c"] == 0:
        for k, envk in AD_ENV_MAP.items():
            envv = os.getenv(envk, "")
            if envv:
                conn.execute(
                    "INSERT INTO ad_config (key,value,source,updated_at) VALUES (?,?,?,?)",
                    (k, envv.strip(), "env", now_str())
                )
        conn.commit()
        logger.info("ad_config 已从 .env 播种（source=env），管理页可查看/导入/保存")

    # 容量索引（3-5 年容量保障，幂等 CREATE INDEX IF NOT EXISTS）：
    # 高频查询键建索引，避免数据增长后全表扫描。容量测算：10 条业务/天 × 365 × 5 年
    # ≈ 提交单 1.8 万 + 文件 5 万 + 审批 3.6 万 + 审计日志 ~11 万 + 下载记录 4 万 ≈ 25-30 万行，
    # SQLite 百万级内 + 索引 = 毫秒级查询；WAL 已开保证读写并发。超过 100 万行再评估迁移 PostgreSQL。
    for _idx in (
        "CREATE INDEX IF NOT EXISTS idx_submissions_submitter ON submissions(submitter)",
        "CREATE INDEX IF NOT EXISTS idx_submissions_status ON submissions(status)",
        "CREATE INDEX IF NOT EXISTS idx_submissions_submit_time ON submissions(submit_time)",
        "CREATE INDEX IF NOT EXISTS idx_submission_files_sub ON submission_files(submission_id)",
        "CREATE INDEX IF NOT EXISTS idx_approvals_sub ON approvals(submission_id)",
        "CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_logs(time)",
        "CREATE INDEX IF NOT EXISTS idx_download_sub ON download_records(submission_id)",
    ):
        conn.execute(_idx)

    conn.commit()
    conn.close()
    logger.info("数据库初始化完成: %s", DB_PATH)

# ============================================================
# 工具函数
# ============================================================
def now_str() -> str:
    return datetime.datetime.now().strftime(TS_FMT)

def gen_submission_id() -> str:
    return f"{uuid.uuid4().hex[:8]}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"

def md5_file(filepath: Path, chunk_size: int = 65536) -> str:
    """流式计算文件 MD5，不加载整个文件到内存"""
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

def get_file_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    types = {
        ".pdf": "PDF文档", ".doc": "Word文档", ".docx": "Word文档",
        ".xls": "Excel表格", ".xlsx": "Excel表格", ".ppt": "PPT", ".pptx": "PPT",
        ".png": "图片", ".jpg": "图片", ".jpeg": "图片", ".gif": "图片", ".bmp": "图片", ".svg": "图片",
        ".txt": "文本", ".csv": "文本", ".json": "代码", ".xml": "代码", ".yaml": "代码", ".yml": "代码", ".md": "文本",
        ".py": "代码", ".c": "代码", ".cpp": "代码", ".h": "代码", ".java": "代码", ".js": "代码",
        # 压缩包 - Linux 默认支持
        ".zip": "压缩包", ".tar": "压缩包",
        ".gz": "压缩包", ".tgz": "压缩包",
        ".bz2": "压缩包", ".tbz2": "压缩包",
        ".xz": "压缩包", ".txz": "压缩包",
        ".zst": "压缩包",
        ".7z": "压缩包", ".rar": "压缩包",
        # FPGA / EDA
        ".bit": "FPGA Bitstream", ".bin": "二进制文件",
        ".exe": "可执行文件", ".dll": "系统文件", ".so": "系统文件",
    }
    return types.get(ext, "未知类型")

def add_audit_log(user: str, action: str, target: str = "", detail: str = "", ip: str = ""):
    db = get_db()
    db.execute(
        "INSERT INTO audit_logs (id,time,user,action,target,detail,ip) VALUES (?,?,?,?,?,?,?)",
        (str(uuid.uuid4()), now_str(), user, action, target, detail, ip)
    )
    db.commit()

def is_partner(name: str) -> bool:
    """判断接收方是否为合作方白名单成员（仅 enabled=1 的合作方生效）"""
    if not name:
        return False
    db = get_db()
    rows = db.execute("SELECT name FROM partners WHERE enabled=1").fetchall()
    name = name.strip()
    for r in rows:
        pname = r["name"].strip()
        if name == pname or pname in name:
            return True
    return False

def get_config_value(key: str, default: str = None) -> str:
    """读取系统配置项，不存在返回 default"""
    db = get_db()
    row = db.execute("SELECT value FROM system_config WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default

def get_ad_config_value(key: str, default: str = None) -> str:
    """读取 AD 配置：SQLite ad_config 优先（ADR-010，管理页可配、即时生效），
    未配置/为空时 fallback 默认值（.env 或代码默认）。"""
    db = get_db()
    row = db.execute("SELECT value FROM ad_config WHERE key=?", (key,)).fetchone()
    if row is not None and row["value"] != "":
        return row["value"]
    return default

def mask_secret(v: str) -> str:
    """脱敏显示（密钥类配置只显示前 2 位 + ****）"""
    if not v:
        return ""
    return v[:2] + "****" if len(v) > 4 else "****"

ENV_FILE = BASE_DIR / ".env"

def write_env_config(updates: dict) -> bool:
    """系统配置变更写回 .env（单一配置源持久化）。.env 不存在时跳过（配置已存 DB）。"""
    if not ENV_FILE.exists():
        return False
    text = ENV_FILE.read_text(encoding="utf-8", errors="ignore")
    for k, v in updates.items():
        line = f"{k}={v}"
        pat = re.compile(rf"^{re.escape(k)}=.*$", re.MULTILINE)
        if pat.search(text):
            text = pat.sub(line, text, count=1)
        else:
            text = text.rstrip("\n") + "\n" + line + "\n"
    ENV_FILE.write_text(text, encoding="utf-8")
    return True

def _has_approver(level: int) -> bool:
    """该审批级别是否有可用审批人：approvers 表有 level 配置，或 admin 用户存在（admin 隐含可审批任意级别）"""
    db = get_db()
    c = db.execute("SELECT COUNT(*) as c FROM approvers WHERE level=?", (level,)).fetchone()["c"]
    if c > 0:
        return True
    c2 = db.execute("SELECT COUNT(*) as c FROM local_users WHERE username='admin' AND enabled=1").fetchone()["c"]
    return c2 > 0

def can_approve_level(level: int) -> bool:
    """审批权限纯由 approvers 表配置（不设 role 体系）；admin 作为系统管理员可审批任意级别"""
    if current_user.role == "admin":
        return True
    db = get_db()
    row = db.execute("SELECT COUNT(*) as c FROM approvers WHERE level=? AND username=?",
                     (level, current_user.username)).fetchone()
    return row["c"] > 0

def row_to_dict(row) -> dict:
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}

def rows_to_list(rows) -> list:
    return [row_to_dict(r) for r in rows]

def get_client_ip() -> str:
    return request.remote_addr or "unknown"

def _ip_in_cidrs(ip: str, cidrs: str) -> bool:
    """判断 IP 是否命中任一内网 CIDR（单网卡模式按网段识别内外网）。"""
    if not cidrs:
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for cidr in cidrs.split(","):
        cidr = cidr.strip()
        if not cidr:
            continue
        try:
            if addr in ipaddress.ip_network(cidr, strict=False):
                return True
        except ValueError:
            continue
    return False


def get_network_zone() -> str:
    """识别当前请求来自内网(管理面)还是外网(下载面)。
    优先级：
      1) Nginx 注入的 X-Network-Zone 请求头（生产权威，双网卡/单网卡 Nginx 均注入）；
      2) 未注入且配置了 INTERNAL_CIDRS 时，按客户端 IP 网段识别（直连/单网卡无代理场景）；
      3) 均无 → internal（本地测试模式默认）。"""
    zone = request.headers.get("X-Network-Zone", "").strip().lower()
    if zone in ("internal", "external"):
        return zone
    if INTERNAL_CIDRS:
        client_ip = request.remote_addr or ""
        # loopback(127.0.0.0/8, ::1) 恒为本机管理面，视同内网（本机健康检查/本地直连）
        try:
            if ipaddress.ip_address(client_ip).is_loopback:
                return "internal"
        except ValueError:
            pass
        return "internal" if _ip_in_cidrs(client_ip, INTERNAL_CIDRS) else "external"
    return "internal"

# 外网面(下载面)允许访问的路径前缀；其余接口一律拒绝，防止绕过前端直接调用管理API
EXTERNAL_ALLOW_PREFIXES = (
    "/login",
    "/static/",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/me",
    "/api/health",
    "/api/external/",
)

@app.before_request
def enforce_network_zone():
    """双网卡隔离的应用层兜底：外网面仅开放登录+下载，管理接口拒绝访问。"""
    if get_network_zone() != "external":
        return None
    path = request.path
    if path == "/":
        return None
    for p in EXTERNAL_ALLOW_PREFIXES:
        if path == p or path.startswith(p):
            return None
    return jsonify({"error": "外网面仅提供文件下载服务，管理操作请从内网访问"}), 403

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())

# ============================================================
# 文件移动（os.rename 0拷贝）
# ============================================================
def safe_rename(src: Path, dst: Path, retries: int = 5, delay: float = 0.5):
    """
    安全移动目录：os.rename 同文件系统内 0拷贝。
    如果目标已存在，先删除目标（应该不会发生，因为ID唯一）。
    Windows 上 Defender/句柄瞬时占用会抛 PermissionError（WinError 5），做短暂重试；
    Linux/NAS（生产）同文件系统 rename 原子，重试不影响行为。
    """
    if dst.exists():
        logger.warning("目标已存在，先删除: %s", dst)
        shutil.rmtree(dst)
    for _attempt in range(1, retries + 1):
        try:
            os.rename(str(src), str(dst))
            logger.info("os.rename 0拷贝移动: %s -> %s", src, dst)
            return
        except PermissionError as _e:
            if _attempt >= retries:
                logger.error("os.rename 多次被占用仍失败（%d次）: %s -> %s", retries, src, dst)
                raise
            logger.warning("os.rename 被占用（第%d次重试）: %s -> %s", _attempt, src, dst)
            time.sleep(delay)

def move_to_external(sub_id: str):
    """审核通过：staging -> external（0拷贝摆渡）"""
    src = STAGING_DIR / sub_id
    dst = EXTERNAL_DIR / sub_id
    if src.exists():
        safe_rename(src, dst)
    return str(dst)

def move_to_archive(sub_id: str, from_dir: str = "external"):
    """过期/驳回：staging或external -> archive（0拷贝归档）"""
    if from_dir == "staging":
        src = STAGING_DIR / sub_id
    else:
        src = EXTERNAL_DIR / sub_id
    dst = ARCHIVE_DIR / sub_id
    if src.exists():
        safe_rename(src, dst)
    return str(dst)

def get_submission_path(sub_id: str, status: str) -> Path:
    """根据状态获取文件当前物理路径"""
    if status in ("pending",):
        return STAGING_DIR / sub_id
    elif status in ("approved", "downloaded"):
        return EXTERNAL_DIR / sub_id
    else:  # rejected, archived
        return ARCHIVE_DIR / sub_id

# ============================================================
# 特征码匹配
# ============================================================
def match_feature_rules(filename: str, file_path: Path = None) -> tuple:
    """检查文件是否匹配特征码规则，返回 (是否匹配, 匹配的规则名列表)

    支持三种规则类型：
    - extension: 按扩展名匹配（pattern 为逗号分隔的扩展名列表）
    - filename:  按文件名正则匹配（pattern 为正则表达式）
    - binary:    按二进制特征码匹配
                 pattern 以 "hex:" 开头表示十六进制特征码，如 "hex:1F8B"
                 否则为文本子串匹配
                 读取文件前 4096 字节进行匹配
    """
    db = get_db()
    rules = db.execute("SELECT * FROM feature_rules WHERE enabled=1").fetchall()
    matched = []
    ext = Path(filename).suffix.lower()

    # 预读文件头部（4KB，覆盖大多数特征码位置，包括 tar 的 ustar offset 257）
    file_header = None
    if file_path and file_path.exists():
        try:
            with open(file_path, "rb") as f:
                file_header = f.read(4096)
        except Exception:
            pass

    for rule in rules:
        if rule["rule_type"] == "extension":
            exts = [e.strip().lower() for e in rule["pattern"].split(",")]
            if ext in exts:
                matched.append(rule["name"])
        elif rule["rule_type"] == "filename":
            if re.search(rule["pattern"], filename, re.IGNORECASE):
                matched.append(rule["name"])
        elif rule["rule_type"] == "binary" and file_header:
            pattern = rule["pattern"]
            # v2.4.0 组合规则：ext_pattern 非空时，特征码命中 AND 后缀匹配才命中（如 tar.gz = hex:1F8B + .tar.gz,.tgz）
            # 后缀用文件名 endswith 匹配（支持多段后缀 .tar.gz；Path.suffix 只取最后一段 .gz）
            ext_pattern = (rule["ext_pattern"] or "").strip()
            if ext_pattern:
                exts = [e.strip().lower() for e in ext_pattern.split(",") if e.strip()]
                _fn_lower = filename.lower()
                if not any(_fn_lower.endswith(e) for e in exts):
                    continue  # 后缀不匹配 → 该组合规则不命中（不进入特征码判断）
            if pattern.startswith("hex:"):
                # 十六进制特征码：hex:1F8B / hex:504B0304 / hex:FD377A585A00
                # v2.5.0: 支持分号分隔多候选（如双字节序 hex:AA995566;665599AA，任一命中即匹配）
                for _cand in pattern[4:].split(";"):
                    _cand = _cand.replace(" ", "").replace(",", "").replace("-", "")
                    if not _cand:
                        continue
                    try:
                        sig_bytes = bytes.fromhex(_cand)
                        if sig_bytes in file_header:
                            matched.append(rule["name"])
                            break
                    except ValueError:
                        continue
            else:
                # 文本特征码（原有方式）
                if pattern.encode("utf-8", errors="ignore") in file_header:
                    matched.append(rule["name"])
    return (len(matched) > 0, matched)

def check_auto_approval(files: list) -> dict:
    """检查是否可以免审批：开关开启 + 所有文件都匹配特征码"""
    db = get_db()
    row = db.execute("SELECT value FROM system_config WHERE key='auto_approval_enabled'").fetchone()
    if not row or row["value"] != "true":
        return {"canAutoApprove": False, "reason": "免审批总开关已关闭", "matchedRules": [], "unmatchedFiles": []}
    if not files:
        return {"canAutoApprove": False, "reason": "没有文件", "matchedRules": [], "unmatchedFiles": []}
    all_matched = True
    all_rules = set()
    unmatched = []
    for f in files:
        # v2.6.0 修复：必须传入真实文件路径，binary/组合规则（特征码+后缀）才能重读文件头匹配；
        # 旧版仅传文件名 → file_header=None → binary 规则在免审批判定中永不命中，
        # 表现为"上传显示已匹配特征码，但提交后仍要求人工审批"。
        _p = f.get("path") or ""
        matched, rules = match_feature_rules(f["name"], Path(_p) if _p else None)
        if matched:
            all_rules.update(rules)
        else:
            all_matched = False
            unmatched.append(f["name"])
    if all_matched:
        return {"canAutoApprove": True, "reason": "", "matchedRules": list(all_rules), "unmatchedFiles": []}
    return {"canAutoApprove": False, "reason": f"{len(unmatched)} 个文件不匹配特征码", "matchedRules": list(all_rules), "unmatchedFiles": unmatched}

# ============================================================
# 用户认证（Flask-Login）
# ============================================================
class User(UserMixin):
    def __init__(self, user_id, username, display_name, role, source, email=""):
        self.id = user_id
        self.username = username
        self.display_name = display_name
        self.role = role
        self.source = source  # local / ad
        # 工作邮箱（AD 登录时取 mail 属性；本地用户取 local_users.email）。
        # 用于飞书通知收件人解析（ADR-051），缺失不影响登录与业务。
        self.email = email or ""

    def to_dict(self):
        return {
            "id": self.id, "username": self.username,
            "displayName": self.display_name, "role": self.role, "source": self.source,
            "email": self.email
        }

@login_manager.user_loader
def load_user(user_id):
    """从 session 加载用户"""
    user_data = session.get("user_data")
    if not user_data:
        return None
    return User(
        user_id=user_data["id"],
        username=user_data["username"],
        display_name=user_data.get("displayName", user_data.get("display_name", "")),
        role=user_data["role"],
        source=user_data["source"],
        email=user_data.get("email", "")
    )

def authenticate_local(username: str, password: str):
    """本地用户认证（enabled=1 且 status='active' 才允许登录）"""
    db = get_db()
    row = db.execute("SELECT * FROM local_users WHERE username=? AND status='active' AND enabled=1", (username,)).fetchone()
    if row and verify_password(password, row["password_hash"]):
        return row_to_dict(row)
    return None


# ------------------------------------------------------------
# AD 模拟目录（ADR-016，12-Factor 三环境一体化）
#   AD_MOCK_MODE=true 时 authenticate_ad / api_search_ad 走本目录（不触网），
#   用于开发/测试环境全量自动化回归；字段与生产典型 AD（脱敏）一致：
#   与测试环境假想目录树完全对应，密码统一 MOCK_AD_PASSWORD。
#   生产环境 AD_MOCK_MODE=false，直连真实 AD（SSSD/LDAP 同源兼容）。
# ------------------------------------------------------------
MOCK_AD_USERS = [
    {"username": "zhangsan", "displayName": "张三", "email": "zhangsan@nexskysemi.com", "department": "研发部"},
    {"username": "lisi", "displayName": "李四", "email": "lisi@nexskysemi.com", "department": "研发部"},
    {"username": "wangzong", "displayName": "王总", "email": "wangzong@nexskysemi.com", "department": "公司高管"},
    {"username": "zhaoliu", "displayName": "赵六", "email": "zhaoliu@nexskysemi.com", "department": "市场部"},
    {"username": "qianqi", "displayName": "钱七", "email": "qianqi@nexskysemi.com", "department": "财务部"},
    {"username": "sunba", "displayName": "孙八", "email": "sunba@nexskysemi.com", "department": "质量部"},
]
MOCK_AD_PASSWORD = "Mock@123456"


def _ad_mock_enabled() -> bool:
    """AD 模拟开关：AD_MOCK_MODE=true（默认 false，生产零影响）"""
    return os.getenv("AD_MOCK_MODE", "false").strip().lower() == "true"


def _mock_ad_authenticate(username: str, password: str):
    """模拟 AD 认证：与真实路径返回相同结构（user dict / error str）"""
    for u in MOCK_AD_USERS:
        if u["username"].lower() == username.lower():
            if password == MOCK_AD_PASSWORD:
                return {"display_name": u["displayName"], "email": u.get("email", ""),
                        "groups": [], "department": u.get("department", "")}, ""
            return None, "LDAP 绑定失败（模拟）：用户名或密码错误"
    return None, "LDAP 绑定失败（模拟）：用户不存在"


def authenticate_ad(username: str, password: str):
    """
    AD 认证：直接 LDAP 绑定，与 sssd 完全兼容（sssd 也是用 LDAP 连 AD）。

    两种绑定方式：
    1. 用户直接绑定（推荐）：用 username@AD_DOMAIN (UPN) 绑定，不需要 bind DN
    2. 服务账户绑定查询：先用 AD_BIND_DN 绑定查询用户 DN，再用用户 DN 绑定

    配置项（.env）：
    - AD_ENABLED=true
    - AD_HOST=ldap://dc01.company.com:389  (或 ldaps://dc01.company.com:636)
    - AD_DOMAIN=company.com                  (用于构造 UPN)
    - AD_BASE_DN=DC=company,DC=com           (用户搜索基准)
    - AD_BIND_DN=CN=svc-securetrans,OU=Service,DC=company,DC=com  (可选，服务账户)
    - AD_BIND_PASSWORD=xxxxxx                 (可选，服务账户密码)
    """
    ad_enabled = get_ad_config_value("ad_enabled", "false").lower() == "true"
    # AD 模拟模式（ADR-016）：AD_MOCK_MODE=true 时走内置模拟目录，不触网
    if _ad_mock_enabled():
        return _mock_ad_authenticate(username, password)
    if not ad_enabled:
        return None, "AD_ENABLED=false（未启用AD认证，可在系统管理-AD配置开启）"
    if not password:
        return None, "密码为空"
    try:
        import ldap3
    except ImportError:
        logger.warning("ldap3 未安装，AD认证不可用。请 pip install ldap3")
        return None, "ldap3 未安装（pip install ldap3）"

    try:
        # 解析 AD_HOST（运行期以 DB 配置优先，fallback .env），支持 ldap:// / ldaps:// 前缀
        host = get_ad_config_value("ad_host", AD_HOST)
        use_ssl = host.startswith("ldaps://")
        if "://" in host:
            host = host.split("://", 1)[1]
        # 分离端口
        if ":" in host:
            host, port_str = host.rsplit(":", 1)
            port = int(port_str)
        else:
            port = 636 if use_ssl else 389

        server = ldap3.Server(host, port=port, use_ssl=use_ssl, get_info=ldap3.NONE, connect_timeout=5)

        # 方式1：用户直接绑定（UPN 格式，AD_DOMAIN 运行期读取）
        ad_domain = get_ad_config_value("ad_domain", AD_DOMAIN)
        if ad_domain:
            user_upn = f"{username}@{ad_domain}"
        else:
            user_upn = username

        conn = ldap3.Connection(server, user=user_upn, password=password,
                                 auto_bind=ldap3.AUTO_BIND_NO_TLS, receive_timeout=5,
                                 raise_exceptions=True)
        if not conn.bound:
            return None, "LDAP 绑定未成功（返回未绑定状态）"

        # 绑定成功，查询用户信息（属性字段可配置，默认 AD 标准属性）
        display_name = username
        email = ""
        groups = []
        ad_base_dn = get_ad_config_value("ad_base_dn", AD_BASE_DN)
        ad_user_field = get_ad_config_value("ad_user_field", AD_USER_FIELD)
        ad_display_field = get_ad_config_value("ad_display_field", AD_DISPLAY_FIELD)
        ad_mail_field = get_ad_config_value("ad_mail_field", AD_MAIL_FIELD)
        ad_group_field = get_ad_config_value("ad_group_field", AD_GROUP_FIELD)
        if ad_base_dn:
            try:
                conn.search(ad_base_dn, f"({ad_user_field}={username})",
                             attributes=[ad_display_field, ad_mail_field, ad_group_field, "department", "userPrincipalName"])
                if conn.entries:
                    entry = conn.entries[0]
                    if hasattr(entry, ad_display_field) and getattr(entry, ad_display_field):
                        display_name = str(getattr(entry, ad_display_field))
                    if hasattr(entry, ad_mail_field) and getattr(entry, ad_mail_field):
                        email = str(getattr(entry, ad_mail_field))
                    if hasattr(entry, ad_group_field) and getattr(entry, ad_group_field):
                        groups = [str(g) for g in getattr(entry, ad_group_field)]
            except Exception as e:
                logger.warning("AD用户信息查询失败 %s: %s", username, e)

        conn.unbind()
        logger.info("AD认证成功: %s", username)
        return {
            "username": username,
            "display_name": display_name,
            "email": email,
            "groups": groups,
        }, None
    except ldap3.core.exceptions.LDAPBindError:
        logger.info("AD认证失败(密码错误): %s", username)
        return None, "AD 账号或密码错误（LDAP 绑定被拒）"
    except ldap3.core.exceptions.LDAPException as e:
        logger.warning("AD连接异常 %s: %s", username, e)
        return None, f"AD 连接异常: {e}"
    except Exception as e:
        logger.warning("AD认证异常 %s: %s", username, e)
        return None, f"AD 认证异常: {e}"

def get_user_role(username: str, source: str) -> str:
    """获取用户角色：本地用户从 local_users 取，AD 用户从 role_mappings 查，默认普通用户"""
    db = get_db()
    if source == "local":
        row = db.execute("SELECT role FROM local_users WHERE username=?", (username,)).fetchone()
        if row:
            return row["role"]
    # AD 用户：查角色映射
    rows = db.execute(
        "SELECT role FROM role_mappings WHERE principal_type='user' AND principal_value=?",
        (username,)
    ).fetchall()
    roles = [r["role"] for r in rows]
    # TODO: 查用户所属 AD 组的组级映射
    if roles:
        return roles[0]  # 多角色取第一个，PMF 阶段简化
    return "internal-user"

def role_required(*roles):
    """角色权限装饰器"""
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if current_user.role not in roles:
                return jsonify({"error": "权限不足"}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ============================================================
# 定时任务：过期文件清理
# ============================================================
def cleanup_expired_files():
    """清理超时的提交单，os.rename 到 archive（0拷贝）。

    统一有效期口径（ADR-034）：提交未审批（pending）与审批未下载（approved/downloaded）
    都用提交单自身的有效期（提交时取自系统配置 default_expiry_days）：
    - pending：从 submit_time 起算，超期未审批 → 自动归档
    - approved/downloaded：从 approved_time 起算，超期未下载/未处理 → 自动归档
    归档为终态，逐单写审计（system_archive_expired，说明超时原因）。
    （上传未提交的临时文件清理走 cleanup_abandoned_temp，TEMP_FILE_HOURS=24h，不属本函数）
    """
    db = get_db()
    now = datetime.datetime.now()
    rows = db.execute("SELECT id, status, submit_time, approved_time, expiry_days FROM submissions "
                      "WHERE status IN ('pending','approved','downloaded')").fetchall()
    cleaned = 0
    for row in rows:
        try:
            if row["status"] == "pending":
                if not row["submit_time"]:
                    continue
                base_dt = datetime.datetime.strptime(row["submit_time"], TS_FMT)
                phase = "提交后"
                from_dir = "staging"
            else:
                if not row["approved_time"]:
                    continue
                base_dt = datetime.datetime.strptime(row["approved_time"], TS_FMT)
                phase = "审批通过后"
                from_dir = "external"
            try:
                _cfg_expiry = int(float(get_config_value("default_expiry_days", str(EXTERNAL_EXPIRY_DAYS)) or 0))
            except (ValueError, TypeError):
                _cfg_expiry = EXTERNAL_EXPIRY_DAYS
            expiry_days = row["expiry_days"] if row["expiry_days"] is not None else _cfg_expiry
            if (now - base_dt).days >= expiry_days:
                sub_id = row["id"]
                elapsed_days = (now - base_dt).days
                move_to_archive(sub_id, from_dir=from_dir)
                db.execute("UPDATE submissions SET status='archived', archived_time=? WHERE id=?", (now_str(), sub_id))
                db.commit()
                cleaned += 1
                logger.info("超时清理: %s 已归档（%s %d 天）", sub_id, phase, elapsed_days)
                # 审计留痕（定时系统动作也必须可审计）：说明超时原因（审批未下载 / 提交未审批）
                add_audit_log(
                    "system", "system_archive_expired", target=sub_id,
                    detail=f"超时归档：{phase} {elapsed_days} 天未{'审批' if row['status']=='pending' else '下载/处理'}，"
                           f"达到有效期 {expiry_days} 天，文件自动移至 archive（定时系统动作）"
                )
        except Exception as e:
            logger.error("超时清理失败 %s: %s", row["id"], e)
    if cleaned:
        logger.info("超时清理完成，共处理 %d 个提交单", cleaned)
    return cleaned

# 未提交临时文件保留时长（小时）：上传后未提交（无 submissions 记录）的 staging 临时目录超时直接删除。
# 无状态上传（前端刷新即弃）不产生提交单、不正式归档；删除不记审计（从未入库、无业务动作，纯存储清理，审计策略见 docs/ADR.md）。
TEMP_FILE_HOURS = int(os.environ.get("TEMP_FILE_HOURS", "24") or 24)

def cleanup_abandoned_temp():
    """清理未提交的临时上传目录（staging/<temp_id> 且无对应提交单），超时直接删除，不归档。

    - 已提交单：提交创建时临时目录已被 shutil.rmtree 移除，staging 下仅剩提交单目录（有 submissions 记录）→ 跳过
    - 未提交残留：无 submissions 记录 → 超时（TEMP_FILE_HOURS，默认 24h）删除，不记审计（从未入库、无业务动作）
    """
    if not STAGING_DIR.exists():
        return 0
    db = get_db()
    now = datetime.datetime.now()
    cleaned = 0
    for sub in STAGING_DIR.iterdir():
        if not sub.is_dir():
            continue
        try:
            exists = db.execute("SELECT COUNT(*) as c FROM submissions WHERE id=?", (sub.name,)).fetchone()["c"]
        except Exception:
            exists = 0
        if exists > 0:
            continue  # 已提交单目录，交给过期归档流程
        try:
            mtime = datetime.datetime.fromtimestamp(sub.stat().st_mtime)
        except OSError:
            continue
        if (now - mtime).total_seconds() >= TEMP_FILE_HOURS * 3600:
            try:
                shutil.rmtree(sub, ignore_errors=True)
                cleaned += 1
                logger.info("未提交临时目录清理: %s（超时 %dh）", sub.name, TEMP_FILE_HOURS)
                # 审计边界（ADR 审计策略）：临时文件从未入库、未产生业务动作（无提交单），
                # 纯存储清理不写审计日志（审计只覆盖：用户/管理员动作 + 涉及业务数据的定时系统动作，
                # 如已审批未下载的超时归档 system_archive_expired）
            except Exception as e:
                logger.error("未提交临时目录清理失败 %s: %s", sub.name, e)
    if cleaned:
        logger.info("未提交临时目录清理完成，共 %d 个", cleaned)
    return cleaned

def start_scheduler():
    """启动定时任务（APScheduler），每天凌晨清理过期文件 + 未提交临时文件"""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        scheduler = BackgroundScheduler()
        scheduler.add_job(cleanup_expired_files, "cron", hour=2, minute=0)
        scheduler.add_job(cleanup_abandoned_temp, "cron", hour=2, minute=10)
        scheduler.start()
        logger.info("定时任务已启动：每天凌晨 2 点清理过期文件与未提交临时文件")
        return scheduler
    except ImportError:
        logger.warning("APScheduler 未安装，过期清理需手动调用或配置系统 Cron")
        return None

# ============================================================
# 路由：页面
# ============================================================
@app.route("/")
def index():
    """首页：如果已登录显示主界面，否则显示登录页"""
    if current_user.is_authenticated:
        return send_file(str(STATIC_DIR / "index.html")) if (STATIC_DIR / "index.html").exists() else redirect(url_for("login_page"))
    return redirect(url_for("login_page"))

@app.route("/login")
def login_page():
    """登录页"""
    if (STATIC_DIR / "login.html").exists():
        return send_file(str(STATIC_DIR / "login.html"))
    # 简单登录页（如果没有前端文件）
    return """
    <!DOCTYPE html><html><head><meta charset="UTF-8"><title>SecureTrans 登录</title>
    <style>body{font-family:sans-serif;background:#f0f4f8;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
    .box{background:#fff;padding:40px;border-radius:12px;box-shadow:0 4px 20px rgba(0,0,0,0.1);width:360px}
    h1{text-align:center;color:#1e40af;margin:0 0 24px}input{width:100%;padding:10px;margin:8px 0;border:1px solid #ddd;border-radius:6px;box-sizing:border-box}
    button{width:100%;padding:12px;background:#2563eb;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:16px;margin-top:12px}
    .hint{font-size:12px;color:#666;margin-top:16px;line-height:1.6}</style></head>
    <body><div class="box"><h1>🔐 SecureTrans</h1>
    <form method="POST" action="/api/auth/login"><input name="username" placeholder="用户名" required><input type="password" name="password" placeholder="密码" required><button type="submit">登 录</button></form>
    <div class="hint">管理员初始密码 = __RESET_PWD__（每次部署重置为 .env RESET_PASSWORD，登录后建议尽快修改）<br>AD用户请输入 域\\用户名 格式<br>版本：__VER__</div></div></body></html>
    """.replace("__RESET_PWD__", RESET_PASSWORD).replace("__VER__", f"{APP_VERSION}-{APP_STAGE}")

# ============================================================
# 路由：认证 API
# ============================================================
@app.route("/api/auth/login", methods=["POST"])
def api_login():
    """登录 API"""
    if request.is_json:
        data = request.get_json()
        username = data.get("username", "").strip()
        password = data.get("password", "")
    else:
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

    if not username or not password:
        return jsonify({"error": "请输入用户名和密码"}), 400

    # 支持 域\用户名 格式
    source = "auto"
    if "\\" in username:
        username = username.split("\\", 1)[1]
        source = "ad"
    elif "@" in username:
        _ad_domain = get_ad_config_value("ad_domain", AD_DOMAIN)
        if _ad_domain and username.endswith("@" + _ad_domain):
            username = username.split("@", 1)[0]
            source = "ad"

    ip = get_client_ip()

    # 先尝试本地
    user = authenticate_local(username, password)
    if user:
        role = get_user_role(username, "local")
        user_obj = User(user["id"], username, user["display_name"] or username, role, "local",
                        email=user.get("email") or "")
        login_user(user_obj)
        session["user_data"] = user_obj.to_dict()
        add_audit_log(username, "login", "", "本地用户登录成功", ip)
        if request.is_json:
            return jsonify({"message": "登录成功", "user": user_obj.to_dict()})
        return redirect(url_for("index"))

    # 再尝试 AD
    ad_reason = ""
    if source in ("ad", "auto"):
        user, ad_reason = authenticate_ad(username, password)
        if user:
            role = get_user_role(username, "ad")
            user_obj = User(str(uuid.uuid4()), username, user.get("display_name", username), role, "ad",
                            email=user.get("email") or "")
            login_user(user_obj)
            session["user_data"] = user_obj.to_dict()
            add_audit_log(username, "login", "",
                          f"AD用户登录成功 display={user.get('display_name', username)} groups={len(user.get('groups') or [])}", ip)
            if request.is_json:
                return jsonify({"message": "登录成功", "user": user_obj.to_dict()})
            return redirect(url_for("index"))

    add_audit_log(username, "login_failed", "ad", ad_reason or "用户名或密码错误", ip)
    if request.is_json:
        return jsonify({"error": "用户名或密码错误"}), 401
    return redirect(url_for("login_page"))

@app.route("/api/auth/logout", methods=["POST", "GET"])
@login_required
def api_logout():
    """退出登录"""
    username = current_user.username
    logout_user()
    session.clear()
    add_audit_log(username, "logout", "", "退出登录", get_client_ip())
    if request.is_json:
        return jsonify({"message": "已退出登录"})
    return redirect(url_for("login_page"))

@app.route("/api/auth/me")
@login_required
def api_me():
    """获取当前用户信息（含网络面标识+审批权限，供前端自适应显示）"""
    data = current_user.to_dict()
    data["networkZone"] = get_network_zone()
    # 审批权限：角色判定 或 approvers 表显式配置（与后端 can_approve_level 完全一致）
    data["canApproveLevel1"] = can_approve_level(1)
    data["canApproveLevel2"] = can_approve_level(2)
    # 强制改密标记（本地用户；admin 初始/重置密码后置 1）
    data["mustChangePassword"] = False
    if current_user.source == "local":
        _r = get_db().execute("SELECT must_change_password FROM local_users WHERE username=?", (current_user.username,)).fetchone()
        data["mustChangePassword"] = bool(_r and _r["must_change_password"])
    return jsonify(data)

@app.route("/api/auth/change-password", methods=["POST"])
@login_required
def api_change_password():
    """修改密码（仅本地用户）"""
    if current_user.source != "local":
        return jsonify({"error": "AD用户请在域控制器修改密码"}), 400
    data = request.get_json() if request.is_json else request.form
    old_password = data.get("old_password", "")
    new_password = data.get("new_password", "")
    if not old_password or not new_password:
        return jsonify({"error": "请输入原密码和新密码"}), 400
    if len(new_password) < 6:
        return jsonify({"error": "新密码至少6位"}), 400
    db = get_db()
    row = db.execute("SELECT * FROM local_users WHERE username=?", (current_user.username,)).fetchone()
    if not row or not verify_password(old_password, row["password_hash"]):
        return jsonify({"error": "原密码错误"}), 400
    db.execute("UPDATE local_users SET password_hash=?, must_change_password=0 WHERE username=?",
               (hash_password(new_password), current_user.username))
    db.commit()
    add_audit_log(current_user.username, "change_password", "", "修改密码成功", get_client_ip())
    return jsonify({"message": "密码修改成功"})

# ============================================================
# 路由：文件上传与提交
# ============================================================
@app.route("/api/submissions/upload", methods=["POST"])
@login_required
@role_required("internal-user", "admin")
def api_upload_file():
    """
    上传单个文件到 staging 临时目录，流式计算 MD5。
    大文件（500MB）也能处理，Werkzeug 自动流式写入磁盘。
    """
    if "file" not in request.files:
        return jsonify({"error": "请选择文件"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "文件名不能为空"}), 400
    # v2.3.7 文件名安全清理：webkitdirectory 等场景 File.name 可能携带相对路径（sub/a.txt）
    # 或含反斜杠/路径穿越；统一取 basename（防目录缺失 500 + 防路径穿越）
    raw_name = file.filename.replace("\\", "/").strip()
    safe_name = raw_name.rsplit("/", 1)[-1].strip()
    if not safe_name or safe_name in (".", ".."):
        return jsonify({"error": "非法文件名"}), 400
    file.filename = safe_name

    # 检查文件大小：单一来源 system_config max_file_size_mb（与界面一致，运行时生效）
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    try:
        max_mb = int(float(get_config_value("max_file_size_mb", str(MAX_FILE_SIZE_MB)) or 0))
    except (ValueError, TypeError):
        max_mb = MAX_FILE_SIZE_MB
    if max_mb <= 0:
        max_mb = MAX_FILE_SIZE_MB
    if size > max_mb * 1024 * 1024:
        return jsonify({"error": f"文件过大，最大支持 {max_mb}MB"}), 400

    # 创建临时提交目录（staging）
    temp_id = gen_submission_id()
    temp_dir = STAGING_DIR / temp_id / "files"
    temp_dir.mkdir(parents=True, exist_ok=True)
    file_path = temp_dir / file.filename

    # 流式保存并计算 MD5
    md5 = hashlib.md5()
    with open(file_path, "wb") as f:
        while True:
            chunk = file.stream.read(65536)
            if not chunk:
                break
            f.write(chunk)
            md5.update(chunk)
    file_md5 = md5.hexdigest()
    actual_size = file_path.stat().st_size
    ftype = get_file_type(file.filename)
    matched, rules = match_feature_rules(file.filename, file_path)
    # v2.2.31：特征码匹配仅用于免审批，须核对免审批总开关开启；开关关闭时不显示匹配（避免误导）
    if matched:
        _auto_on = str(get_config_value("auto_approval_enabled", "false")).strip().lower() == "true"
        if not _auto_on:
            matched = False
            rules = []

    # 压缩包自动解包列清单（Linux 默认支持：zip + tar 系列）
    inner_files = []
    fname_lower = file.filename.lower()
    archive_exts = (".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2",
                     ".tar.xz", ".txz", ".tar.zst", ".gz", ".bz2", ".xz", ".zst")
    is_archive = any(fname_lower.endswith(ext) for ext in archive_exts)
    if is_archive:
        try:
            if fname_lower.endswith(".zip"):
                import zipfile
                with zipfile.ZipFile(file_path, "r") as zf:
                    for info in zf.infolist():
                        if not info.is_dir():
                            inner_files.append({"name": info.filename, "size": info.file_size, "type": get_file_type(info.filename)})
            elif any(fname_lower.endswith(ext) for ext in (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz", ".tar.zst")):
                # tar 系列：tarfile 自动识别压缩格式（r:* 模式）
                import tarfile
                with tarfile.open(file_path, "r:*") as tf:
                    for member in tf.getmembers():
                        if member.isfile():
                            inner_files.append({"name": member.name, "size": member.size, "type": get_file_type(member.name)})
            # 单文件压缩（.gz/.bz2/.xz/.zst）：只有一个文件，不列内部清单
        except Exception as e:
            logger.warning("压缩包解析失败 %s: %s", file.filename, e)

    add_audit_log(current_user.username, "upload", temp_id, f"上传文件: {file.filename} ({actual_size} bytes)", get_client_ip())

    return jsonify({
        "tempId": temp_id, "name": file.filename, "size": actual_size, "type": ftype,
        "md5": file_md5, "matched": matched, "matchedRules": rules,
        "isArchive": is_archive, "innerFiles": inner_files,
    })

@app.route("/api/submissions", methods=["POST"])
@login_required
@role_required("internal-user", "admin")
def api_create_submission():
    """创建提交单：将 staging 临时文件正式归档，生成 manifest，进入审批流"""
    data = request.get_json()
    temp_ids = data.get("tempIds", [])
    receiver_name = data.get("receiverName", "")
    receiver_email = data.get("receiverEmail", "")
    receiver_org = data.get("receiverOrg", "")
    # receiverType: internal(公司内部)/partner(合作方)/non-partner(非合作方)/auto(按白名单自动判定)
    receiver_type = data.get("receiverType", "auto")
    if receiver_type == "auto":
        receiver_type = "partner" if is_partner(receiver_org) else "non-partner"
    security_level = data.get("securityLevel", "internal")
    reason = data.get("reason", "")
    # 有效期统一由系统配置控制（唯一设置处：系统配置→默认有效期），提交时不允许指定
    cfg_expiry = get_config_value("default_expiry_days", "7")
    try:
        expiry_days = int(cfg_expiry)
    except (TypeError, ValueError):
        expiry_days = 7

    if not temp_ids:
        return jsonify({"error": "请先上传文件"}), 400
    if not receiver_name:
        return jsonify({"error": "请填写接收方姓名"}), 400
    # 公司内部（internal）：仅需接收人，单位可空；合作方/非合作方必须填写单位（信任模式自填也需单位）
    if receiver_type != "internal" and not receiver_org:
        return jsonify({"error": "请填写接收方单位"}), 400

    # 信任模式：普通用户选中"合作方"但单位不在清单时，以接收方单位自动加入合作方清单（去重：名称不区分大小写）
    if receiver_type == "partner" and not is_partner(receiver_org):
        db = get_db()
        exists = db.execute(
            "SELECT COUNT(*) as c FROM partners WHERE name=? COLLATE NOCASE",
            (receiver_org.strip(),)
        ).fetchone()["c"]
        if not exists:
            db.execute(
                "INSERT INTO partners (id,name,contact,email,enabled,created_at) VALUES (?,?,?,?,1,?)",
                (str(uuid.uuid4()), receiver_org.strip(), receiver_name, receiver_email, now_str())
            )
            db.commit()
            add_audit_log(current_user.username, "create_partner", receiver_org, "提交时自动加入合作方清单", get_client_ip())

    sub_id = gen_submission_id()
    final_dir = STAGING_DIR / sub_id
    final_files_dir = final_dir / "files"
    final_files_dir.mkdir(parents=True, exist_ok=True)

    files_info = []
    total_size = 0
    for tid in temp_ids:
        temp_dir = STAGING_DIR / tid
        if not temp_dir.exists():
            continue
        temp_files_dir = temp_dir / "files"
        if temp_files_dir.exists():
            for f in temp_files_dir.iterdir():
                if f.is_file():
                    dest = final_files_dir / f.name
                    if dest.exists():
                        dest.unlink()
                    os.rename(str(f), str(dest))  # 0拷贝移动
                    md5 = md5_file(dest)
                    ftype = get_file_type(f.name)
                    matched, _ = match_feature_rules(f.name, dest)
                    files_info.append({"name": f.name, "size": dest.stat().st_size, "type": ftype, "md5": md5, "matched": matched,
                                       "path": str(dest)})  # v2.6.0: 供免审批判定重读文件头做 binary/组合规则匹配
                    total_size += dest.stat().st_size
        # 清理临时目录
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass

    if not files_info:
        shutil.rmtree(final_dir, ignore_errors=True)
        return jsonify({"error": "没有有效文件"}), 400

    # 生成 manifest.json
    manifest = {"submissionId": sub_id, "submitTime": now_str(), "submitter": current_user.username, "files": files_info}
    with open(final_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    # 免审批判定
    auto_result = check_auto_approval(files_info)
    auto_approved = 1 if auto_result["canAutoApprove"] else 0

    # v2.2.31（ADR-015）：非免审批提交前校验审批人配置，缺失则提交失败提示（逻辑闭环，不产生无法审批的死单）
    if not auto_approved:
        _need1, _need2 = True, False
        if receiver_type == "non-partner":
            _need2 = True
        if _need1 and not _has_approver(1):
            shutil.rmtree(final_dir, ignore_errors=True)
            return jsonify({"error": "未配置一级审批人，请联系管理员配置后提交（公司内部/合作方必须有一级审批人）",
                            "message_en": "No level-1 approver configured. Please ask admin to configure one before submitting."}), 400
        if _need2 and not _has_approver(2):
            shutil.rmtree(final_dir, ignore_errors=True)
            return jsonify({"error": "未配置二级审批人，非合作方提交必须有一级和二级审批人",
                            "message_en": "No level-2 approver configured. Non-partner submissions require both level-1 and level-2 approvers."}), 400

    db = get_db()
    if auto_approved:
        status = "approved"
        approved_time = now_str()
    else:
        status = "pending"
        approved_time = None

    # 先插入 submissions 记录（外键依赖）
    db.execute(
        """INSERT INTO submissions (id,submitter,submitter_name,receiver_name,receiver_email,receiver_type,receiver_org,security_level,reason,expiry_days,status,auto_approved,current_path,submit_time,approved_time,file_count,total_size)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (sub_id, current_user.username, current_user.display_name, receiver_name, receiver_email, receiver_type,
         receiver_org, security_level, reason, expiry_days, status, auto_approved, str(final_dir),
         now_str(), approved_time, len(files_info), total_size)
    )
    for fi in files_info:
        db.execute(
            "INSERT INTO submission_files (id,submission_id,path,name,size,type,md5,matched,is_archive) VALUES (?,?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), sub_id, f"files/{fi['name']}", fi["name"], fi["size"], fi["type"], fi["md5"], 1 if fi["matched"] else 0, 0)
        )
    # 免审批：插入审批记录后再 os.rename 摆渡到 external
    if auto_approved:
        db.execute(
            "INSERT INTO approvals (id,submission_id,level,approver,approver_name,action,comment,time) VALUES (?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), sub_id, 0, "system", "系统", "approve", "免审批自动通过", now_str())
        )
        move_to_external(sub_id)
        db.execute("UPDATE submissions SET current_path=? WHERE id=?", (str(EXTERNAL_DIR / sub_id), sub_id))
    db.commit()

    add_audit_log(current_user.username, "create_submission", sub_id,
                  f"提交{len(files_info)}个文件，{'免审批自动通过' if auto_approved else '待审批'}", get_client_ip())

    # ---- 飞书通知（ADR-051）：旁路异步，任何通知故障不影响提交结果 ----
    try:
        app_url = _notify_app_url()
        if auto_approved:
            # 免审批直通：跳过所有审批人，只通知提交人
            notify_event(sub_id, "submission_auto_approved", [current_user.username],
                         {"operator": "系统", "status_text": "免审批自动通过，文件已摆渡至外网下载区",
                          "app_url": app_url})
        else:
            # 通知提交人：已受理
            notify_event(sub_id, "submission_status", [current_user.username],
                         {"status_text": "已提交，待一级审批", "app_url": app_url, "operator": "系统"})
            # 通知当前节点审批人（一级）；非合作方需二级，待一级通过后再通知二级
            approvers1 = [r["username"] for r in db.execute(
                "SELECT username FROM approvers WHERE level=1").fetchall()]
            if approvers1:
                notify_event(sub_id, "submission_pending_l1", approvers1,
                             {"level": "一级", "status_text": "待一级审批", "app_url": app_url})
            else:
                logger.warning(f"提交单 {sub_id} 未解析到一级审批人邮箱（approvers level=1 为空）")
    except Exception as ex:
        logger.warning(f"提交单 {sub_id} 通知派发失败（不影响业务）: {ex}")

    return jsonify({"id": sub_id, "status": status, "autoApproved": bool(auto_approved), "fileCount": len(files_info),
                    "expiry_days": expiry_days, "receiver_type": receiver_type})

# ============================================================
# 路由：提交单查询
# ============================================================
@app.route("/api/submissions")
@login_required
def api_list_submissions():
    """提交单列表（"我的提交"：任何用户——含 admin——只返回自己的提交单）
    admin 查看全局提交记录走 /api/admin/submissions/all（只读历史视图）"""
    status = request.args.get("status", "")
    db = get_db()
    query = "SELECT * FROM submissions WHERE submitter=?"
    params = [current_user.username]
    if status:
        query += " AND status=?"
        params.append(status)
    query += " ORDER BY submit_time DESC LIMIT 200"
    rows = db.execute(query, params).fetchall()
    data = rows_to_list(rows)
    # 附最近一次飞书通知状态（界面展示"飞书通知"列，便于发现网关/开放平台异常）
    nmap = get_notify_map([r["id"] for r in data])
    for d in data:
        d["notify"] = nmap.get(d["id"])
    return jsonify(data)

@app.route("/api/admin/submissions/all")
@login_required
def api_admin_all_submissions():
    """所有提交文件记录（仅 admin，只读历史视图，不提供删除）"""
    if current_user.role != "admin":
        return jsonify({"error": "权限不足"}), 403
    status = request.args.get("status", "")
    db = get_db()
    query = "SELECT * FROM submissions WHERE 1=1"
    params = []
    if status:
        query += " AND status=?"
        params.append(status)
    query += " ORDER BY submit_time DESC LIMIT 500"
    rows = db.execute(query, params).fetchall()
    data = rows_to_list(rows)
    nmap = get_notify_map([r["id"] for r in data])
    for d in data:
        d["notify"] = nmap.get(d["id"])
    return jsonify(data)

@app.route("/api/submissions/<sub_id>")
@login_required
def api_get_submission(sub_id):
    """提交单详情
    可见性：提交者本人、审批人（可查看待审/已审提交以完成审批）、admin 可查看；
    无审批权限的普通用户只能查看自己的提交单"""
    db = get_db()
    sub = db.execute("SELECT * FROM submissions WHERE id=?", (sub_id,)).fetchone()
    if not sub:
        return jsonify({"error": "提交单不存在"}), 404
    if current_user.role != "admin" and sub["submitter"] != current_user.username:
        if not (can_approve_level(1) or can_approve_level(2)):
            return jsonify({"error": "权限不足"}), 403
    files = db.execute("SELECT * FROM submission_files WHERE submission_id=?", (sub_id,)).fetchall()
    approvals = db.execute("SELECT * FROM approvals WHERE submission_id=? ORDER BY level,time", (sub_id,)).fetchall()
    # 飞书通知投递记录（近 20 条，供界面对账；不含完整邮箱，已脱敏）
    notifies = db.execute(
        "SELECT event,recipients,status,detail,created_at FROM notification_logs "
        "WHERE submission_id=? ORDER BY rowid DESC LIMIT 20", (sub_id,)
    ).fetchall()
    return jsonify({**row_to_dict(sub), "files": rows_to_list(files), "approvals": rows_to_list(approvals),
                    "notifications": rows_to_list(notifies)})

@app.route("/api/submissions/pending/my")
@login_required
def api_my_pending():
    """待我审批的列表（权限：admin 或 approvers 表配置的审批人，不设角色体系）"""
    db = get_db()
    can1 = can_approve_level(1)
    can2 = can_approve_level(2)
    if not (can1 or can2):
        return jsonify({"error": "权限不足"}), 403
    conds = []
    if can1:
        conds.append("status='pending'")
    if can2:
        conds.append("status='pending_approval_2'")
    rows = db.execute("SELECT * FROM submissions WHERE " + " OR ".join(conds) + " ORDER BY submit_time DESC").fetchall()
    data = rows_to_list(rows)
    nmap = get_notify_map([r["id"] for r in data])
    for d in data:
        d["notify"] = nmap.get(d["id"])
    return jsonify(data)

# ============================================================
# 路由：审批
# ============================================================
@app.route("/api/submissions/<sub_id>/approve", methods=["POST"])
@login_required
def api_approve(sub_id):
    """审批：通过/驳回。通过后 os.rename 到 external（0拷贝摆渡）
    权限：角色（dept-manager/executive/admin）或 approvers 表配置的审批人"""
    data = request.get_json()
    action = data.get("action", "")  # approve / reject
    comment = data.get("comment", "")

    if action not in ("approve", "reject"):
        return jsonify({"error": "无效的操作"}), 400

    db = get_db()
    sub = db.execute("SELECT * FROM submissions WHERE id=?", (sub_id,)).fetchone()
    if not sub:
        return jsonify({"error": "提交单不存在"}), 404

    # 判断审批级别（角色或 approvers 表配置校验）
    if sub["status"] == "pending":
        level = 1
        if not can_approve_level(1):
            return jsonify({"error": "需要部门主管一级审批"}), 403
    elif sub["status"] == "pending_approval_2":
        level = 2
        if not can_approve_level(2):
            return jsonify({"error": "需要公司高管二级审批"}), 403
    else:
        return jsonify({"error": "当前状态不需要审批"}), 400

    db.execute(
        "INSERT INTO approvals (id,submission_id,level,approver,approver_name,action,comment,time) VALUES (?,?,?,?,?,?,?,?)",
        (str(uuid.uuid4()), sub_id, level, current_user.username, current_user.display_name, action, comment, now_str())
    )

    if action == "reject":
        # 驳回：os.rename 到 archive
        move_to_archive(sub_id, from_dir="staging")
        new_status = "rejected"
        db.execute("UPDATE submissions SET status=?, archived_time=?, current_path=? WHERE id=?",
                   (new_status, now_str(), str(ARCHIVE_DIR / sub_id), sub_id))
    elif level == 1:
        # 一级通过：公司内部/合作方直接摆渡（仅一级流程，不涉及二级）；
        # 非合作方进入二级审批。
        if sub["receiver_type"] in ("partner", "internal"):
            move_to_external(sub_id)
            new_status = "approved"
            db.execute("UPDATE submissions SET status=?, approved_time=?, current_path=? WHERE id=?",
                       (new_status, now_str(), str(EXTERNAL_DIR / sub_id), sub_id))
        elif can_approve_level(2):
            # 语义B（仅非合作方）：当前一级审批人同时具备二级审批权限（如二级审批人被配置为一级审批人），
            # 一级已由同一人把关，自动跳过二级审批，直接摆渡。避免同人重复审批。
            move_to_external(sub_id)
            new_status = "approved"
            db.execute("UPDATE submissions SET status=?, approved_time=?, current_path=? WHERE id=?",
                       (new_status, now_str(), str(EXTERNAL_DIR / sub_id), sub_id))
            # 审计链补充：记录二级自动跳过
            db.execute(
                "INSERT INTO approvals (id,submission_id,level,approver,approver_name,action,comment,time) VALUES (?,?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), sub_id, 2, current_user.username, current_user.display_name,
                 "approve", "自动跳过二级：审批人同时具备一级和二级审批权限", now_str())
            )
        else:
            new_status = "pending_approval_2"
            db.execute("UPDATE submissions SET status=? WHERE id=?", (new_status, sub_id))
    else:
        # 二级通过：os.rename 摆渡到 external
        move_to_external(sub_id)
        new_status = "approved"
        db.execute("UPDATE submissions SET status=?, approved_time=?, current_path=? WHERE id=?",
                   (new_status, now_str(), str(EXTERNAL_DIR / sub_id), sub_id))

    db.commit()
    add_audit_log(current_user.username, f"approval_{action}", sub_id,
                  f"{'通过' if action=='approve' else '驳回'}，级别{level}，备注：{comment}", get_client_ip())

    # ---- 飞书通知（ADR-051）：按节点通知提交人与下一级审批人（旁路异步）----
    try:
        app_url = _notify_app_url()
        submitter = sub["submitter"]
        operator = current_user.display_name or current_user.username
        if action == "reject":
            notify_event(sub_id, "submission_rejected", [submitter],
                         {"status_text": "已驳回", "reason": comment or "未填写驳回原因",
                          "operator": operator, "level": f"{level}级", "app_url": app_url})
        elif level == 1 and new_status == "pending_approval_2":
            # 一级通过 → 进入二级：通知提交人（中间过程实时可见）+ 二级审批人
            notify_event(sub_id, "submission_status", [submitter],
                         {"status_text": "一级审批通过，待二级审批", "operator": operator,
                          "level": "一级", "app_url": app_url})
            approvers2 = [r["username"] for r in db.execute(
                "SELECT username FROM approvers WHERE level=2").fetchall()]
            if approvers2:
                notify_event(sub_id, "submission_pending_l2", approvers2,
                             {"level": "二级", "status_text": "待二级审批", "app_url": app_url})
        elif level == 1 and new_status == "approved" and sub["receiver_type"] not in ("partner", "internal"):
            # 语义B：一级审批人同时具备二级权限，二级自动跳过（只在非合作方场景）
            notify_event(sub_id, "approval_level_skipped", [submitter],
                         {"status_text": "一级审批通过，二级自动跳过（审批人同时具备一二级权限）",
                          "operator": operator, "level": "二级", "app_url": app_url})
        else:
            # 终审通过（一级直通 / 二级通过）
            notify_event(sub_id, "submission_approved", [submitter],
                         {"status_text": "审批通过，文件已摆渡至外网下载区",
                          "operator": operator, "level": f"{level}级", "app_url": app_url})
    except Exception as ex:
        logger.warning(f"审批通知派发失败 sub={sub_id}（不影响业务）: {ex}")

    return jsonify({"status": new_status, "message": "审批完成"})

# ============================================================
# 路由：外网下载
# ============================================================
@app.route("/api/external/files")
@login_required
def api_external_files():
    """已摆渡到 external 的文件列表"""
    db = get_db()
    rows = db.execute("SELECT * FROM submissions WHERE status IN ('approved','downloaded') AND submitter=? ORDER BY approved_time DESC LIMIT 200",
                      (current_user.username,)).fetchall()
    return jsonify(rows_to_list(rows))

@app.route("/api/external/submissions/<sub_id>")
@login_required
def api_external_submission_detail(sub_id):
    """外网下载详情（下载弹窗用）：仅 approved/downloaded 状态可见，含文件明细；
    替代原前端直接调 /api/submissions/<id>（不在外网白名单 → 403，导致外网无法下载）。"""
    db = get_db()
    sub = db.execute("SELECT * FROM submissions WHERE id=?", (sub_id,)).fetchone()
    if not sub or sub["status"] not in ("approved", "downloaded"):
        return jsonify({"error": "文件不可下载"}), 404
    if sub["submitter"] != current_user.username:
        return jsonify({"error": "无权查看他人提交的文件"}), 404
    files = db.execute("SELECT * FROM submission_files WHERE submission_id=?", (sub_id,)).fetchall()
    return jsonify({**row_to_dict(sub), "files": rows_to_list(files)})

@app.route("/api/external/<sub_id>/download/<path:filename>")
@login_required
def api_download_file(sub_id, filename):
    """
    下载文件：从 external 目录流式读取。
    记录下载时间，物理文件不动。
    """
    db = get_db()
    sub = db.execute("SELECT * FROM submissions WHERE id=?", (sub_id,)).fetchone()
    if not sub or sub["status"] not in ("approved", "downloaded"):
        return jsonify({"error": "文件不可下载"}), 404
    if sub["submitter"] != current_user.username:
        return jsonify({"error": "无权下载他人提交的文件"}), 404

    file_path = EXTERNAL_DIR / sub_id / "files" / filename
    if not file_path.exists():
        # fallback: 从当前路径找
        current_path = sub["current_path"] or str(EXTERNAL_DIR / sub_id)
        file_path = Path(current_path) / "files" / filename
        if not file_path.exists():
            return jsonify({"error": "文件不存在"}), 404

    # 查文件 MD5（端到端完整性：上传时计算并存储，下载时随响应头返回供客户端比对）
    md5 = None
    frow = db.execute("SELECT md5 FROM submission_files WHERE submission_id=? AND name=?", (sub_id, filename)).fetchone()
    if frow:
        md5 = frow["md5"] or None

    # 记录下载（含 MD5）
    db.execute(
        "INSERT INTO download_records (id,submission_id,filename,downloader,download_time,ip,md5) VALUES (?,?,?,?,?,?,?)",
        (str(uuid.uuid4()), sub_id, filename, current_user.username, now_str(), get_client_ip(), md5)
    )
    # 更新状态为 downloaded（如果还是 approved）
    if sub["status"] == "approved":
        db.execute("UPDATE submissions SET status='downloaded' WHERE id=?", (sub_id,))
    db.commit()

    add_audit_log(current_user.username, "download", sub_id,
                  f"下载文件: {filename}" + (f"（MD5: {md5}）" if md5 else ""), get_client_ip())

    resp = send_file(str(file_path), as_attachment=True, download_name=filename)
    if md5:
        resp.headers["X-File-MD5"] = md5
    return resp

# ============================================================
# 路由：管理员附件审查下载（仅内网）
# ============================================================
@app.route("/api/admin/submissions/<sub_id>/download/<path:filename>")
@login_required
@role_required("admin")
def api_admin_download_file(sub_id, filename):
    """管理员审查附件下载（v2.6.6，ADR-035）。
    用途：'所有提交记录'详情中对任意状态提交单的附件做查看/下载审查
          （pending→staging / approved·downloaded→external / rejected·archived→archive）。
    安全：外网面白名单不含 /api/admin/ → before_request 已 403（外网绝不允许，ADR-008 网络面隔离）；
          仅 admin 角色可调（role_required）；文件名取 basename 防路径穿越。
    留痕：audit_log 记 admin_download（管理员审查下载），下载记录不入 download_records（非接收方下载）。"""
    db = get_db()
    sub = db.execute("SELECT * FROM submissions WHERE id=?", (sub_id,)).fetchone()
    if not sub:
        return jsonify({"error": "提交单不存在"}), 404
    if ".." in filename or "/" in filename.replace("\\", "/"):
        return jsonify({"error": "非法文件名"}), 400
    fname = os.path.basename(filename)
    if not fname or fname in (".", ".."):
        return jsonify({"error": "非法文件名"}), 400
    # 定位文件：优先 current_path（已 resolve），fallback staging/external/archive
    candidates = []
    cp = sub["current_path"]
    if cp:
        candidates.append(Path(cp) / "files" / fname)
    for d in (STAGING_DIR, EXTERNAL_DIR, ARCHIVE_DIR):
        candidates.append(d / sub_id / "files" / fname)
    file_path = next((p for p in candidates if p.exists()), None)
    if not file_path:
        return jsonify({"error": "文件不存在"}), 404
    md5 = None
    frow = db.execute("SELECT md5 FROM submission_files WHERE submission_id=? AND name=?", (sub_id, fname)).fetchone()
    if frow:
        md5 = frow["md5"] or None
    add_audit_log(current_user.username, "admin_download", sub_id,
                  f"管理员审查下载附件: {fname}" + (f"（MD5: {md5}）" if md5 else ""), get_client_ip())
    db.commit()
    resp = send_file(str(file_path), as_attachment=True, download_name=fname)
    if md5:
        resp.headers["X-File-MD5"] = md5
    return resp

# ============================================================
# 路由：用户管理（admin）
# ============================================================
@app.route("/api/admin/local-users")
@login_required
@role_required("admin")
def api_list_local_users():
    db = get_db()
    rows = db.execute("SELECT id,username,display_name,email,role,status,enabled,created_at FROM local_users ORDER BY created_at").fetchall()
    return jsonify(rows_to_list(rows))

@app.route("/api/admin/local-users", methods=["POST"])
@login_required
@role_required("admin")
def api_create_local_user():
    data = request.get_json()
    username = data.get("username", "").strip()
    password = data.get("password", "")
    display_name = data.get("displayName", "")
    email = data.get("email", "")
    # 不设 role 体系：所有非 admin 用户统一为普通用户，审批权由 approvers 表配置
    role = "internal-user"
    if not username:
        return jsonify({"error": "用户名不能为空"}), 400
    random_pwd = False
    if not password:
        password = secrets.token_urlsafe(9)  # 留空自动生成初始密码
        random_pwd = True
    if len(password) < 6:
        return jsonify({"error": "密码至少6位"}), 400
    db = get_db()
    exists = db.execute("SELECT COUNT(*) as c FROM local_users WHERE username=?", (username,)).fetchone()["c"]
    if exists:
        return jsonify({"error": "用户名已存在"}), 400
    db.execute(
        "INSERT INTO local_users (id,username,password_hash,display_name,email,role,status,enabled,must_change_password,created_at) VALUES (?,?,?,?,?,?,?,1,?,?)",
        (str(uuid.uuid4()), username, hash_password(password), display_name, email, role, "active", 1 if random_pwd else 0, now_str())
    )
    db.commit()
    add_audit_log(current_user.username, "create_local_user", username, f"创建本地用户，角色{role}（默认使能）", get_client_ip())
    msg = "创建成功" + (f"，初始密码：{password}（请安全告知用户，首次登录后可自行修改）" if random_pwd else "")
    return jsonify({"message": msg, "initialPassword": password if random_pwd else None})

@app.route("/api/admin/local-users/<username>", methods=["DELETE"])
@login_required
@role_required("admin")
def api_delete_local_user(username):
    if username == "admin":
        return jsonify({"error": "不能删除admin"}), 400
    db = get_db()
    db.execute("DELETE FROM local_users WHERE username=?", (username,))
    db.commit()
    add_audit_log(current_user.username, "delete_local_user", username, "删除本地用户", get_client_ip())
    return jsonify({"message": "删除成功"})

@app.route("/api/admin/local-users/<username>/reset-password", methods=["POST"])
@login_required
@role_required("admin")
def api_reset_local_password(username):
    new_pwd = os.getenv("RESET_PASSWORD", "Init@123456").strip()
    db = get_db()
    db.execute("UPDATE local_users SET password_hash=?, must_change_password=1 WHERE username=?",
               (hash_password(new_pwd), username))
    db.commit()
    add_audit_log(current_user.username, "reset_password", username, "重置密码", get_client_ip())
    return jsonify({"message": f"密码已重置为 {new_pwd}，用户首次登录需修改"})

@app.route("/api/admin/local-users/<username>/enabled", methods=["PUT"])
@login_required
@role_required("admin")
def api_toggle_local_user_enabled(username):
    """启用/禁用用户。admin 永久使能，不可禁用（防止锁死自己）。"""
    data = request.get_json(silent=True) or {}
    enabled = 1 if data.get("enabled", True) else 0
    if username == "admin" and not enabled:
        return jsonify({"error": "admin 为系统内置管理员，永久使能，不可禁用"}), 400
    db = get_db()
    exists = db.execute("SELECT COUNT(*) as c FROM local_users WHERE username=?", (username,)).fetchone()["c"]
    if not exists:
        return jsonify({"error": "用户不存在"}), 404
    db.execute("UPDATE local_users SET enabled=? WHERE username=?", (enabled, username))
    db.commit()
    state = "启用" if enabled else "禁用"
    add_audit_log(current_user.username, "toggle_user_enabled", username, f"{state}用户", get_client_ip())
    return jsonify({"message": f"用户已{state}", "enabled": bool(enabled)})

# ============================================================
# 路由：AD 角色映射（admin）
# ============================================================
@app.route("/api/admin/role-mappings")
@login_required
@role_required("admin")
def api_list_role_mappings():
    db = get_db()
    rows = db.execute("SELECT * FROM role_mappings ORDER BY granted_at DESC").fetchall()
    return jsonify(rows_to_list(rows))

@app.route("/api/admin/role-mappings", methods=["POST"])
@login_required
@role_required("admin")
def api_create_role_mapping():
    data = request.get_json()
    principal_type = data.get("principalType", "user")
    principal_value = data.get("principalValue", "").strip()
    display_name = data.get("displayName", "")
    role = data.get("role", "internal-user")
    note = data.get("note", "")
    # 不设 role 体系：角色仅 admin / internal-user（普通），审批权由 approvers 表配置
    if role not in ("admin", "internal-user"):
        return jsonify({"error": "角色仅支持 admin / internal-user（审批权限请在审批人配置中设置）"}), 400
    if not principal_value or not role:
        return jsonify({"error": "参数不完整"}), 400
    db = get_db()
    db.execute(
        "INSERT INTO role_mappings (id,principal_type,principal_value,display_name,role,granted_by,granted_at,note) VALUES (?,?,?,?,?,?,?,?)",
        (str(uuid.uuid4()), principal_type, principal_value, display_name, role, current_user.username, now_str(), note)
    )
    db.commit()
    add_audit_log(current_user.username, "create_role_mapping", principal_value,
                  f"授予角色{role}，类型{principal_type}", get_client_ip())
    return jsonify({"message": "角色映射创建成功"})

@app.route("/api/admin/role-mappings/<mapping_id>", methods=["DELETE"])
@login_required
@role_required("admin")
def api_delete_role_mapping(mapping_id):
    db = get_db()
    db.execute("DELETE FROM role_mappings WHERE id=?", (mapping_id,))
    db.commit()
    add_audit_log(current_user.username, "delete_role_mapping", mapping_id, "删除角色映射", get_client_ip())
    return jsonify({"message": "删除成功"})

def _ad_err(ex):
    """把 ldap3/网络异常翻译成可读原因（供界面/审计展示）"""
    s = str(ex)
    if "InvalidCredentials" in s or "49" in s or "52e" in s.lower():
        return "bind 凭据错误（LDAP 49 / data 52e）：AD_BIND_DN 或 AD_BIND_PASSWORD 不正确"
    if any(k in s for k in ("socket", "timeout", "timed out", "ServerPool", "unreachable", "Name or service")):
        return "无法连接 AD 服务器：请检查 AD_HOST 地址/端口、网络连通性与防火墙"
    if "NoSuchObject" in s:
        return "AD 搜索基准(base_dn)不存在：请检查 AD_BASE_DN"
    if "invalidDN" in s:
        return "bind DN 格式无效：请检查 AD_BIND_DN"
    return s[:200]

def _ad_connection():
    """创建并 bind AD 连接（ldap3，同源读取 ad_config/.env）"""
    from ldap3 import Server, Connection, ALL
    ad_host = get_ad_config_value("ad_host", os.getenv("AD_HOST", ""))
    ad_bind_dn = get_ad_config_value("ad_bind_dn", os.getenv("AD_BIND_DN", ""))
    ad_bind_password = get_ad_config_value("ad_bind_password", os.getenv("AD_BIND_PASSWORD", ""))
    server = Server(ad_host, get_info=ALL)
    conn = Connection(server, user=ad_bind_dn or None, password=ad_bind_password or None,
                      auto_bind=True, raise_exceptions=True)
    return conn

def _ad_fields():
    return {
        "ad_user_field": get_ad_config_value("ad_user_field", os.getenv("AD_USER_FIELD", "sAMAccountName")) or "sAMAccountName",
        "ad_display_field": get_ad_config_value("ad_display_field", os.getenv("AD_DISPLAY_FIELD", "displayName")) or "displayName",
        "ad_mail_field": get_ad_config_value("ad_mail_field", os.getenv("AD_MAIL_FIELD", "mail")) or "mail",
        "ad_base_dn": get_ad_config_value("ad_base_dn", os.getenv("AD_BASE_DN", "")),
    }

def _ad_search_users(keyword, limit=20):
    """真实 LDAP 精确搜索用户（ldap3）；keyword 为空返回空（不 dump 全量）。返回 (users, error)"""
    f = _ad_fields()
    conn = _ad_connection()
    try:
        if keyword:
            flt = f"(&(objectClass=user)({f['ad_user_field']}={keyword}))"  # 精确匹配：有就是有，没有就是没有
        else:
            return [], "请输入用户名关键字（精确匹配，不返回全量用户）"
        conn.search(f["ad_base_dn"], flt, attributes=[f["ad_user_field"], f["ad_display_field"], f["ad_mail_field"], "department"],
                    size_limit=limit)
        users = []
        for e in conn.entries:
            users.append({
                "username": str(getattr(e, f["ad_user_field"], "") or ""),
                "displayName": str(getattr(e, f["ad_display_field"], "") or ""),
                "email": str(getattr(e, f["ad_mail_field"], "") or ""),
                "department": str(getattr(e, "department", "") or ""),
            })
        return users, ""
    finally:
        try:
            conn.unbind()
        except Exception:
            pass

# ============================================================
# 飞书通知（ADR-051 旁路通道 / ADR-052 网关边界）
#   链路：本机 → 通知网关（唯一出网口）→ 飞书开放平台；本机不直连飞书
#   纪律：异步旁路，失败绝不阻塞提交/审批；每次投递落 notification_logs，
#         失败额外落审计 notify_failed，界面据此定位网关/开放平台/网络问题
# ============================================================

NOTIFY_EVENTS = (
    "submission_pending_l1", "submission_pending_l2", "submission_status",
    "submission_approved", "submission_rejected", "submission_auto_approved",
    "approval_level_skipped",
)


def _mask_email(email: str) -> str:
    """收件人脱敏（t***@n***）：入库与审计不留完整工作邮箱"""
    email = (email or "").strip()
    if "@" not in email:
        return (email[:1] + "***") if email else "-"
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain[:1]}***"


def _local_email_of(username: str) -> str:
    """本地用户邮箱（local_users.email）"""
    db = get_db()
    row = db.execute("SELECT email FROM local_users WHERE username=?", (username,)).fetchone()
    return (row["email"] or "").strip() if row and row["email"] else ""


def resolve_email(username: str, fallback: str = "") -> tuple:
    """AD 账号 → 工作邮箱：local_users 优先，其次 AD 精确查询（同源 ad_config）。
    返回 (email, source)；找不到返回 (fallback, "")。
    设计意图：用户登录名=AD 姓名全拼，mail 属性为唯一工作邮箱，飞书按邮箱解析人员。"""
    username = (username or "").strip()
    if not username:
        return fallback or "", ""
    email = _local_email_of(username)
    if email:
        return email, "local_users"
    ad_enabled = (get_ad_config_value("ad_enabled", os.getenv("AD_ENABLED", "false")) or "").lower()
    if ad_enabled in ("true", "1", "yes"):
        try:
            users, _err = _ad_search_users(username, limit=1)
            for u in users or []:
                if (u.get("username") or "").lower() == username.lower() and u.get("email"):
                    return u["email"].strip(), "ad"
        except Exception as ex:  # AD 不可用不应影响通知链路本身
            logger.warning(f"resolve_email AD 查询失败 username={username}: {ex}")
    return fallback or "", ""


def _notify_record(sub_id: str, event: str, recipients: str, status: str, detail: str):
    """落通知投递记录（独立于业务状态，业务不回滚）"""
    db = get_db()
    db.execute(
        "INSERT INTO notification_logs (id,submission_id,event,recipients,status,detail,created_at) VALUES (?,?,?,?,?,?,?)",
        (str(uuid.uuid4()), sub_id, event, recipients, status, (detail or "")[:500], now_str())
    )
    db.commit()


def notify_event(sub_id: str, event: str, recipients: list, extra: dict = None):
    """通知入口：异步派发，永不抛异常、永不阻塞请求线程。
    recipients 为用户名列表（AD 账号/本地用户名），邮箱在后台线程解析。"""
    try:
        if event not in NOTIFY_EVENTS:
            logger.warning(f"忽略未知通知事件: {event}")
            return
        names = [n for n in (recipients or []) if n]
        if not names or not sub_id:
            return
        threading.Thread(
            target=_notify_worker,
            args=(app, sub_id, event, names, dict(extra or {})),
            daemon=True,
            name=f"notify-{event}",
        ).start()
    except Exception as ex:  # 兜底：通知故障不得影响业务主流程
        logger.warning(f"notify_event 派发失败 {event}/{sub_id}: {ex}")


def _notify_worker(app_obj, sub_id: str, event: str, names: list, extra: dict):
    """后台线程：解析邮箱 → 调网关 → 落记录（全程自吞异常）"""
    status, detail, masked = "failed", "", "-"
    with app_obj.app_context():
        try:
            db = get_db()
            sub = db.execute("SELECT * FROM submissions WHERE id=?", (sub_id,)).fetchone()
            files = db.execute("SELECT name FROM submission_files WHERE submission_id=? ORDER BY rowid",
                               (sub_id,)).fetchall()
            filenames = [f["name"] for f in files]
            filename_text = (filenames[0] + (f" 等{len(filenames)}个文件" if len(filenames) > 1 else "")) if filenames else ""
            base = {
                "submission_id": sub_id,
                "filename": filename_text,
                "submitter": sub["submitter"] if sub else "",
                "note": (sub["reason"] if sub and sub["reason"] else ""),
                "reason": "",
                "approver": "",
                "level": "",
                "status_text": "",
                "app_url": extra.get("app_url") or FEISHU_NOTIFY_APP_URL or "",
                "external_url": extra.get("external_url") or "",
                "operator": extra.get("operator") or "",
                "time": now_str(),
            }
            extra_vars = {k: v for k, v in (extra or {}).items() if k in base and v}
            base.update(extra_vars)

            emails, missing = [], []
            for name in names:
                email, _src = resolve_email(name)
                if email:
                    emails.append((name, email))
                else:
                    missing.append(name)
            if emails:
                masked = ",".join(_mask_email(e) for _, e in emails)

            if not emails:
                status, detail = "skipped", "收件人无可用工作邮箱：" + ",".join(missing)
            elif not FEISHU_NOTIFY_ENABLED or not FEISHU_NOTIFY_URL:
                status, detail = "skipped", "飞书通知未启用或未配置网关地址（FEISHU_NOTIFY_ENABLED / FEISHU_NOTIFY_URL）"
            else:
                payload = {
                    "event": event,
                    "recipients": [e for _, e in emails],
                    # 幂等键：同一提交单 + 同一事件 + 同一节点状态，网关重复投递只发一次
                    "request_id": f"{sub_id}:{event}:{base.get('status_text') or ''}",
                    "vars": base,
                }
                req = urllib.request.Request(
                    FEISHU_NOTIFY_URL,
                    data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                    headers={"Content-Type": "application/json", "X-Notify-Token": FEISHU_NOTIFY_TOKEN},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=FEISHU_NOTIFY_TIMEOUT) as resp:
                    body = resp.read().decode("utf-8", errors="ignore")
                result = json.loads(body or "{}")
                sent = int(result.get("sent") or 0)
                failed = int(result.get("failed") or 0)
                if sent and not failed:
                    status, detail = "sent", f"sent={sent}"
                elif sent:
                    status, detail = "partial", f"sent={sent} failed={failed}"
                else:
                    status, detail = "failed", f"网关返回失败 code={result.get('code')} msg={result.get('msg') or ''}"
                if missing:
                    detail += f"；缺邮箱跳过：{','.join(missing)}"
        except Exception as ex:
            status, detail = "failed", f"通知调用异常：{type(ex).__name__}: {ex}"
        finally:
            try:
                _notify_record(sub_id, event, masked, status, detail)
                if status in ("failed", "partial"):
                    add_audit_log("system", "notify_failed", sub_id, f"{event} {status} {detail}")
                logger.info(f"notify {event} {sub_id} -> {status} {detail}")
            except Exception as ex:
                logger.warning(f"通知记录落库失败 {event}/{sub_id}: {ex}")


def _notify_app_url() -> str:
    """消息里的系统入口地址：显式配置优先，否则按当前请求推导（请求线程内调用）"""
    if FEISHU_NOTIFY_APP_URL:
        return FEISHU_NOTIFY_APP_URL
    try:
        return request.host_url.rstrip("/")
    except Exception:
        return ""


def get_notify_map(sub_ids: list) -> dict:
    """批量取每个提交单最近一条通知记录（列表页展示，避免 N+1 查询）"""
    ids = [s for s in (sub_ids or []) if s]
    if not ids:
        return {}
    db = get_db()
    ph = ",".join("?" for _ in ids)
    rows = db.execute(
        f"SELECT submission_id,event,status,detail,created_at FROM notification_logs "
        f"WHERE submission_id IN ({ph}) ORDER BY rowid", ids
    ).fetchall()
    result = {}
    for r in rows:  # 按写入顺序覆盖，最后一条即最新
        result[r["submission_id"]] = {
            "status": r["status"], "event": r["event"],
            "detail": r["detail"], "time": r["created_at"]
        }
    return result


@app.route("/api/admin/ad/search", methods=["POST"])
@login_required
@role_required("admin")
def api_search_ad():
    """搜索 AD 用户（真实 LDAP 查询，ldap3；ad_enabled=false 时为打桩模拟）
    同时返回 verifyCommand：可直接在服务器/AD 管理机手工执行的 ldapsearch 验证命令
    （与程序同源读取 ad_config/.env，避免界面配置与手工验证不一致；bind 密码不回显明文，用 **** 占位提示替换）。
    精确匹配（用户名后无通配符 *）：有就是有，没有就是没有。"""
    keyword = request.form.get("keyword", "") if request.form else (request.get_json() or {}).get("keyword", "")
    keyword = (keyword or "").strip()
    ad_enabled = get_ad_config_value("ad_enabled", "false").lower()
    ad_host = get_ad_config_value("ad_host", os.getenv("AD_HOST", ""))
    ad_bind_dn = get_ad_config_value("ad_bind_dn", os.getenv("AD_BIND_DN", ""))
    ad_base_dn = get_ad_config_value("ad_base_dn", os.getenv("AD_BASE_DN", ""))
    ad_user_field = get_ad_config_value("ad_user_field", os.getenv("AD_USER_FIELD", "sAMAccountName")) or "sAMAccountName"
    ad_display_field = get_ad_config_value("ad_display_field", os.getenv("AD_DISPLAY_FIELD", "displayName")) or "displayName"
    ad_mail_field = get_ad_config_value("ad_mail_field", os.getenv("AD_MAIL_FIELD", "mail")) or "mail"
    verify_cmd = ""
    if ad_host and ad_base_dn:
        secure_flag = "-Z" if ad_host.startswith("ldaps://") else "-x"
        bind_part = f"-D '{ad_bind_dn}' -w '****'" if ad_bind_dn else ""
        flt_cmd = f"(&(objectClass=user)({ad_user_field}={keyword}))" if keyword else "(&(objectClass=user))"
        verify_cmd = (f"ldapsearch {secure_flag} -H {ad_host} {bind_part} -b '{ad_base_dn}' "
                      f"'{flt_cmd}' {ad_display_field} {ad_mail_field}"
                      + ("\n# 注：将 **** 替换为 AD 绑定密码（AD_BIND_PASSWORD）；服务器无 ldapsearch 时先安装: "
                         f"sudo dnf install -y openldap-clients" if bind_part else ""))
    if _ad_mock_enabled() or ad_enabled != "true":
        # 模拟目录（ADR-016）：AD_MOCK_MODE=true 或 AD 未启用时走 MOCK_AD_USERS（不触网）
        result = [u for u in MOCK_AD_USERS
                  if keyword.lower() in u["username"].lower() or keyword in u["displayName"]]
        return jsonify({"mode": "mock", "users": result, "verifyCommand": verify_cmd, "error": ""})
    # 真实 LDAP 精确查询（ldap3；ad_enabled=true）
    if not ad_host or not ad_base_dn:
        return jsonify({"mode": "ldap", "users": [], "verifyCommand": verify_cmd,
                        "error": "AD 未完整配置：请先在「系统配置 → AD 配置」填写 AD_HOST / AD_BASE_DN 并保存"})
    if not keyword:
        return jsonify({"mode": "ldap", "users": [], "verifyCommand": verify_cmd,
                        "error": "请输入用户名关键字（精确匹配，不返回全量用户）"})
    try:
        users, err = _ad_search_users(keyword)
        return jsonify({"mode": "ldap", "users": users, "verifyCommand": verify_cmd, "error": err})
    except Exception as ex:
        return jsonify({"mode": "ldap", "users": [], "verifyCommand": verify_cmd, "error": f"AD 查询失败：{_ad_err(ex)}"})

@app.route("/api/admin/ad/test", methods=["POST"])
@login_required
@role_required("admin")
def api_ad_test():
    """AD 连接测试：用当前配置的 bind 凭据实测连通；可选指定用户名做精确查询验证（有就是有，没有就是没有）"""
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    try:
        conn = _ad_connection()
        msg = "AD 连接成功（bind 认证通过）"
        if username:
            f = _ad_fields()
            conn.search(f["ad_base_dn"], f"(&(objectClass=user)({f['ad_user_field']}={username}))",
                        attributes=[f["ad_user_field"], f["ad_display_field"]], size_limit=1)
            if conn.entries:
                e = conn.entries[0]
                disp = str(getattr(e, f["ad_display_field"], "") or "")
                msg = f"AD 连接成功；用户「{username}」存在（显示名：{disp or '-'}）"
            else:
                msg = f"AD 连接成功；未找到用户「{username}」（精确匹配，有就是有，没有就是没有）"
        conn.unbind()
        add_audit_log(current_user.username, "ad_test", f"username={username or '(bind only)'}", msg, get_client_ip())
        return jsonify({"ok": True, "message": msg})
    except Exception as ex:
        emsg = f"AD 连接失败：{_ad_err(ex)}"
        add_audit_log(current_user.username, "ad_test", f"username={username or '(bind only)'}", emsg, get_client_ip())
        return jsonify({"ok": False, "message": emsg})

# ============================================================
# 路由：AD 配置管理 + 配置总览（ADR-010，仅 admin）
# ============================================================
@app.route("/api/admin/ad-config")
@login_required
@role_required("admin")
def api_get_ad_config():
    """返回 DB 中 AD 配置（含来源/时间）+ .env 当前值（只读展示 / 导入源）"""
    db = get_db()
    rows = db.execute("SELECT key,value,source,updated_at FROM ad_config").fetchall()
    db_map = {r["key"]: {"value": r["value"], "source": r["source"], "updated_at": r["updated_at"]} for r in rows}
    env_map = {envk: os.getenv(envk, "") for envk in AD_ENV_MAP.values()}
    return jsonify({"db": db_map, "env": env_map})

@app.route("/api/admin/ad-config/import", methods=["POST"])
@login_required
@role_required("admin")
def api_import_ad_config():
    """将 .env 当前 AD 值导入 DB（source=env）；用于首次查看 .env 配置导入到页面"""
    db = get_db()
    now = now_str()
    for k, envk in AD_ENV_MAP.items():
        envv = os.getenv(envk, "")
        db.execute("INSERT OR REPLACE INTO ad_config (key,value,source,updated_at) VALUES (?,?,?,?)",
                   (k, envv.strip(), "env", now))
    db.commit()
    add_audit_log(current_user.username, "import_ad_config", "", "从 .env 导入 AD 配置", get_client_ip())
    return jsonify({"message": "已从 .env 导入 AD 配置（source=env）"})

@app.route("/api/admin/ad-config", methods=["PUT"])
@login_required
@role_required("admin")
def api_update_ad_config():
    """保存 AD 配置到 DB（source=db，即时生效）；空值写入后读取时回退 .env/默认"""
    data = request.get_json() or {}
    db = get_db()
    now = now_str()
    for k, v in data.items():
        if k not in AD_ENV_MAP:
            continue
        db.execute("INSERT OR REPLACE INTO ad_config (key,value,source,updated_at) VALUES (?,?,?,?)",
                   (k, str(v).strip(), "db", now))
    db.commit()
    audit_detail = json.dumps(
        {k: (mask_secret(str(v)) if k == "ad_bind_password" else v) for k, v in data.items() if k in AD_ENV_MAP},
        ensure_ascii=False)
    add_audit_log(current_user.username, "update_ad_config", "", audit_detail, get_client_ip())
    return jsonify({"message": "AD 配置已保存（数据库权威，即时生效）"})

@app.route("/api/admin/config-overview")
@login_required
@role_required("admin")
def api_config_overview():
    """配置总览：部署级 .env（只读）+ 运行时 DB（可编辑），来源标记，防遗忘"""
    db = get_db()
    deploy_env = {
        "DEPLOY_MODE": os.getenv("DEPLOY_MODE", ""),
        "HOST": os.getenv("HOST", ""),
        "PORT": os.getenv("PORT", ""),
        "INTERNAL_CIDRS": os.getenv("INTERNAL_CIDRS", ""),
        "NAS_ROOT": os.getenv("NAS_ROOT", ""),
        "SECURETRANS_DATA": os.getenv("SECURETRANS_DATA", ""),
        "SECRET_KEY": mask_secret(os.getenv("SECRET_KEY", "")),
        "RESET_PASSWORD": mask_secret(os.getenv("RESET_PASSWORD", "")),
    }
    sys_rows = db.execute("SELECT key,value FROM system_config").fetchall()
    sys_cfg = {r["key"]: r["value"] for r in sys_rows}
    ad_rows = db.execute("SELECT key,value,source,updated_at FROM ad_config").fetchall()
    ad_cfg = {r["key"]: {"value": r["value"], "source": r["source"], "updated_at": r["updated_at"]} for r in ad_rows}
    return jsonify({"deploy_env": deploy_env, "runtime_db": {"system_config": sys_cfg, "ad_config": ad_cfg}})

# ============================================================
# 路由：合作方白名单（admin）
# ============================================================
@app.route("/api/admin/partners")
@login_required
@role_required("admin")
def api_list_partners():
    db = get_db()
    enabled_filter = request.args.get("enabled")
    if enabled_filter is not None:
        rows = db.execute("SELECT * FROM partners WHERE enabled=? ORDER BY created_at DESC", (1 if enabled_filter in ("1", "true") else 0,)).fetchall()
    else:
        rows = db.execute("SELECT * FROM partners ORDER BY created_at DESC").fetchall()
    return jsonify(rows_to_list(rows))

@app.route("/api/admin/partners", methods=["POST"])
@login_required
@role_required("admin")
def api_create_partner():
    data = request.get_json()
    name = data.get("name", "").strip()
    contact = data.get("contact", "").strip()
    email = data.get("email", "")
    enabled = 1 if data.get("enabled", True) else 0
    if not name:
        return jsonify({"error": "合作方名称不能为空"}), 400
    if not contact:
        return jsonify({"error": "联系人不能为空"}), 400
    db = get_db()
    exists = db.execute("SELECT COUNT(*) as c FROM partners WHERE name=?", (name,)).fetchone()["c"]
    if exists:
        return jsonify({"error": "合作方已存在"}), 400
    db.execute(
        "INSERT INTO partners (id,name,contact,email,enabled,created_at) VALUES (?,?,?,?,?,?)",
        (str(uuid.uuid4()), name, contact, email, enabled, now_str())
    )
    db.commit()
    partner_id = db.execute("SELECT id FROM partners WHERE name=?", (name,)).fetchone()["id"]
    add_audit_log(current_user.username, "create_partner", name, "添加合作方白名单", get_client_ip())
    return jsonify({"message": "合作方添加成功", "id": partner_id})

@app.route("/api/admin/partners/<partner_id>", methods=["PUT"])
@login_required
@role_required("admin")
def api_update_partner(partner_id):
    """编辑合作方（名称/联系人/邮箱）。名称去重检查排除自身（COLLATE NOCASE 与提交自动加入一致）。"""
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    contact = data.get("contact", "").strip()
    email = data.get("email", "")
    if not name:
        return jsonify({"error": "合作方名称不能为空"}), 400
    if not contact:
        return jsonify({"error": "联系人不能为空"}), 400
    db = get_db()
    row = db.execute("SELECT * FROM partners WHERE id=?", (partner_id,)).fetchone()
    if not row:
        return jsonify({"error": "合作方不存在"}), 404
    dup = db.execute(
        "SELECT COUNT(*) as c FROM partners WHERE name=? COLLATE NOCASE AND id<>?", (name, partner_id)
    ).fetchone()["c"]
    if dup:
        return jsonify({"error": "合作方已存在"}), 400
    db.execute("UPDATE partners SET name=?, contact=?, email=? WHERE id=?", (name, contact, email, partner_id))
    db.commit()
    add_audit_log(current_user.username, "update_partner", name, "编辑合作方", get_client_ip())
    return jsonify({"message": "合作方更新成功", "id": partner_id})

@app.route("/api/admin/partners/<partner_id>", methods=["DELETE"])
@login_required
@role_required("admin")
def api_delete_partner(partner_id):
    db = get_db()
    db.execute("DELETE FROM partners WHERE id=?", (partner_id,))
    db.commit()
    add_audit_log(current_user.username, "delete_partner", partner_id, "删除合作方", get_client_ip())
    return jsonify({"message": "删除成功"})

@app.route("/api/admin/partners/<partner_id>/enabled", methods=["PUT"])
@login_required
@role_required("admin")
def api_toggle_partner_enabled(partner_id):
    """启用/禁用合作方。禁用后不再参与白名单自动判定，也不出现在提交下拉选项。"""
    data = request.get_json(silent=True) or {}
    enabled = 1 if data.get("enabled", True) else 0
    db = get_db()
    row = db.execute("SELECT * FROM partners WHERE id=?", (partner_id,)).fetchone()
    if not row:
        return jsonify({"error": "合作方不存在"}), 404
    db.execute("UPDATE partners SET enabled=? WHERE id=?", (enabled, partner_id))
    db.commit()
    state = "启用" if enabled else "禁用"
    add_audit_log(current_user.username, "toggle_partner_enabled", row["name"], f"{state}合作方", get_client_ip())
    return jsonify({"message": f"合作方已{state}", "enabled": bool(enabled)})

# 合作方选项（登录即可访问，仅返回 enabled=1，供提交表单下拉选择）
@app.route("/api/partners")
@login_required
def api_partner_options():
    db = get_db()
    rows = db.execute("SELECT id,name,email FROM partners WHERE enabled=1 ORDER BY name").fetchall()
    return jsonify(rows_to_list(rows))

# ============================================================
# 路由：审批人配置（admin）
# ============================================================
@app.route("/api/admin/approvers")
@login_required
@role_required("admin")
def api_list_approvers():
    db = get_db()
    rows = db.execute("SELECT * FROM approvers ORDER BY level,display_name").fetchall()
    return jsonify(rows_to_list(rows))

@app.route("/api/admin/approvers", methods=["POST"])
@login_required
@role_required("admin")
def api_create_approver():
    data = request.get_json()
    level = int(data.get("level", 1))
    username = data.get("username", "").strip()
    display_name = data.get("displayName", username)
    scope = data.get("scope", "all")
    if level not in (1, 2):
        return jsonify({"error": "审批级别只能为1或2"}), 400
    if not username:
        return jsonify({"error": "审批人用户名不能为空"}), 400
    db = get_db()
    exists = db.execute("SELECT COUNT(*) as c FROM approvers WHERE level=? AND username=?",
                        (level, username)).fetchone()["c"]
    if exists:
        return jsonify({"error": "该审批人已配置在此级别"}), 400
    db.execute(
        "INSERT INTO approvers (id,level,username,display_name,scope) VALUES (?,?,?,?,?)",
        (str(uuid.uuid4()), level, username, display_name, scope)
    )
    db.commit()
    approver_id = db.execute("SELECT id FROM approvers WHERE level=? AND username=?", (level, username)).fetchone()["id"]
    add_audit_log(current_user.username, "create_approver", username,
                  f"配置为{level}级审批人", get_client_ip())
    return jsonify({"message": "审批人配置成功", "id": approver_id})

@app.route("/api/admin/approvers/<approver_id>", methods=["DELETE"])
@login_required
@role_required("admin")
def api_delete_approver(approver_id):
    db = get_db()
    db.execute("DELETE FROM approvers WHERE id=?", (approver_id,))
    db.commit()
    add_audit_log(current_user.username, "delete_approver", approver_id, "删除审批人配置", get_client_ip())
    return jsonify({"message": "删除成功"})

# ============================================================
# 路由：系统配置
# ============================================================
@app.route("/api/config/feature-rules")
@login_required
def api_feature_rules():
    db = get_db()
    rows = db.execute("SELECT * FROM feature_rules ORDER BY created_at").fetchall()
    return jsonify(rows_to_list(rows))

# 特征码规则管理（admin）
@app.route("/api/admin/feature-rules", methods=["POST"])
@login_required
@role_required("admin")
def api_create_feature_rule():
    """创建特征码规则"""
    data = request.get_json()
    name = data.get("name", "").strip()
    rule_type = data.get("ruleType", "extension")  # extension / filename / binary
    pattern = data.get("pattern", "").strip()
    enabled = 1 if data.get("enabled", True) else 0
    # v2.4.0 组合规则：binary 类型可带 extPattern（特征码 AND 后缀），其他类型忽略
    ext_pattern = (data.get("extPattern") or "").strip() if rule_type == "binary" else ""
    if not name or not pattern:
        return jsonify({"error": "规则名称和匹配模式不能为空"}), 400
    if rule_type not in ("extension", "filename", "binary"):
        return jsonify({"error": "规则类型只能为 extension/filename/binary"}), 400
    db = get_db()
    rule_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO feature_rules (id,name,rule_type,pattern,enabled,created_at,ext_pattern) VALUES (?,?,?,?,?,?,?)",
        (rule_id, name, rule_type, pattern, enabled, now_str(), ext_pattern or None)
    )
    db.commit()
    add_audit_log(current_user.username, "create_feature_rule", rule_id,
                  f"创建特征码规则: {name} ({rule_type}: {pattern}{' + 后缀 ' + ext_pattern if ext_pattern else ''})", get_client_ip())
    return jsonify({"message": "规则创建成功", "id": rule_id})

@app.route("/api/admin/feature-rules/<rule_id>", methods=["PUT"])
@login_required
@role_required("admin")
def api_update_feature_rule(rule_id):
    """修改特征码规则"""
    data = request.get_json()
    db = get_db()
    rule = db.execute("SELECT * FROM feature_rules WHERE id=?", (rule_id,)).fetchone()
    if not rule:
        return jsonify({"error": "规则不存在"}), 404
    name = data.get("name", rule["name"])
    rule_type = data.get("ruleType", rule["rule_type"])
    pattern = data.get("pattern", rule["pattern"])
    enabled = 1 if data.get("enabled", bool(rule["enabled"])) else 0
    if rule_type not in ("extension", "filename", "binary"):
        return jsonify({"error": "规则类型只能为 extension/filename/binary"}), 400
    # v2.4.0：仅 binary 类型允许 extPattern；未传时保持原值
    if "extPattern" in data:
        ext_pattern = (data.get("extPattern") or "").strip() if rule_type == "binary" else ""
    else:
        ext_pattern = rule["ext_pattern"] or ""
    db.execute(
        "UPDATE feature_rules SET name=?, rule_type=?, pattern=?, enabled=?, ext_pattern=? WHERE id=?",
        (name, rule_type, pattern, enabled, ext_pattern or None, rule_id)
    )
    db.commit()
    add_audit_log(current_user.username, "update_feature_rule", rule_id,
                  f"修改特征码规则: {name}", get_client_ip())
    return jsonify({"message": "规则已更新"})

@app.route("/api/admin/feature-rules/<rule_id>", methods=["DELETE"])
@login_required
@role_required("admin")
def api_delete_feature_rule(rule_id):
    """删除特征码规则"""
    db = get_db()
    rule = db.execute("SELECT * FROM feature_rules WHERE id=?", (rule_id,)).fetchone()
    if not rule:
        return jsonify({"error": "规则不存在"}), 404
    db.execute("DELETE FROM feature_rules WHERE id=?", (rule_id,))
    db.commit()
    add_audit_log(current_user.username, "delete_feature_rule", rule_id,
                  f"删除特征码规则: {rule['name']}", get_client_ip())
    return jsonify({"message": "规则已删除"})

@app.route("/api/admin/feature-rules/<rule_id>/toggle", methods=["POST"])
@login_required
@role_required("admin")
def api_toggle_feature_rule(rule_id):
    """开关切换特征码规则（启用/禁用）"""
    db = get_db()
    rule = db.execute("SELECT * FROM feature_rules WHERE id=?", (rule_id,)).fetchone()
    if not rule:
        return jsonify({"error": "规则不存在"}), 404
    new_enabled = 0 if rule["enabled"] else 1
    db.execute("UPDATE feature_rules SET enabled=? WHERE id=?", (new_enabled, rule_id))
    db.commit()
    status_text = "启用" if new_enabled else "禁用"
    add_audit_log(current_user.username, "toggle_feature_rule", rule_id,
                  f"{status_text}特征码规则: {rule['name']}", get_client_ip())
    return jsonify({"message": f"规则已{status_text}", "enabled": bool(new_enabled)})

@app.route("/api/config/system")
@login_required
def api_get_system_config():
    db = get_db()
    rows = db.execute("SELECT key,value FROM system_config").fetchall()
    return jsonify({r["key"]: r["value"] for r in rows})

@app.route("/api/config/system", methods=["PUT"])
@login_required
@role_required("admin")
def api_update_system_config():
    config = request.get_json()
    db = get_db()
    for k, v in config.items():
        db.execute("INSERT OR REPLACE INTO system_config (key,value) VALUES (?,?)", (k, str(v)))
    db.commit()
    add_audit_log(current_user.username, "update_system_config", "", json.dumps(config, ensure_ascii=False), get_client_ip())
    # ADR-010：运行时配置以 SQLite 为唯一权威（.env 仅部署级与首次播种），不再回写 .env
    return jsonify({"message": "配置已保存（数据库权威，即时生效）"})

# ============================================================
# 路由：审计日志与统计
# ============================================================
@app.route("/api/audit-logs")
@login_required
@role_required("admin")
def api_audit_logs():
    action = request.args.get("action", "")
    user = request.args.get("user", "")
    limit = int(request.args.get("limit", "200"))
    db = get_db()
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
    rows = db.execute(query, params).fetchall()
    return jsonify(rows_to_list(rows))

@app.route("/api/audit-logs/stats")
@login_required
@role_required("admin")
def api_audit_stats():
    """审计统计：人员 × 类型 × 每日。类型 = 提交文件类型（upload 按文件名去重）+ 审批 + 下载 + 管理操作"""
    import re
    from_d = request.args.get("from", "")
    to_d = request.args.get("to", "")
    try:
        today = datetime.date.today()
        if not from_d:
            from_d = (today - datetime.timedelta(days=29)).isoformat()
        if not to_d:
            to_d = today.isoformat()
        datetime.datetime.strptime(from_d, "%Y-%m-%d")
        datetime.datetime.strptime(to_d, "%Y-%m-%d")
        from_ts = from_d + " 00:00:00"
        to_ts = to_d + " 23:59:59"
    except Exception:
        return jsonify({"error": "日期格式错误，应为 YYYY-MM-DD"}), 400
    db = get_db()
    rows = db.execute(
        "SELECT time,user,action,detail FROM audit_logs WHERE time>=? AND time<=?",
        (from_ts, to_ts)
    ).fetchall()
    # 文件类型映射（与特征码规则类型一致，含 FPGA bit/bin/ltx）
    ext_map = {
        "pdf": "PDF文档", "doc": "Word文档", "docx": "Word文档",
        "xls": "Excel表格", "xlsx": "Excel表格", "csv": "Excel表格",
        "ppt": "PPT演示", "pptx": "PPT演示",
        "png": "图片", "jpg": "图片", "jpeg": "图片", "gif": "图片", "bmp": "图片", "svg": "图片",
        "zip": "压缩包", "tar": "压缩包", "gz": "压缩包", "tgz": "压缩包",
        "bz2": "压缩包", "tbz2": "压缩包", "xz": "压缩包", "txz": "压缩包", "zst": "压缩包",
        "bit": "FPGA文件", "bin": "FPGA文件", "ltx": "FPGA文件",
    }
    # 白名单后缀正则（仅认已知扩展名，防 IP/日期等误匹配；长后缀优先）
    exts = sorted(ext_map.keys(), key=len, reverse=True)
    file_re = re.compile(r'([\w\u4e00-\u9fff.\-]+\.(?:' + '|'.join(re.escape(e) for e in exts) + r'))\b', re.I)
    # 上传=文件数（按 用户+文件名+日 去重，重传/重复动作只计 1）；下载/管理审查下载=下载次数
    # 审批=approval_* 动作数；管理操作=admin/system 的非文件/非登录/非审批/非提交动作
    excl_actions = {"login", "login_failed", "logout", "change_password", "create_submission"}
    FILE_TYPES_ORDER = ["PDF文档", "Word文档", "Excel表格", "PPT演示", "图片", "压缩包", "FPGA文件", "其他文件"]
    STAT_TYPES = FILE_TYPES_ORDER + ["审批", "下载", "管理操作"]
    users, ftypes, by_type, by_day = set(), set(), {}, {}
    seen_file = set()  # (user, fname_lower, day) 上传去重
    for r in rows:
        u = r["user"] or "unknown"
        day = r["time"][:10] if r["time"] else ""
        action = r["action"] or ""
        detail = r["detail"] or ""
        if action == "upload":
            m = file_re.search(detail)
            if not m:
                continue
            fname = m.group(1).lower()
            key = (u, fname, day)
            if key in seen_file:
                continue
            seen_file.add(key)
            ext = fname.rsplit(".", 1)[-1]
            ftype = ext_map.get(ext, "其他文件")
            users.add(u); ftypes.add(ftype)
            by_type[(u, ftype)] = by_type.get((u, ftype), 0) + 1
            if day:
                by_day[(u, day)] = by_day.get((u, day), 0) + 1
        elif action in ("download", "admin_download"):
            ftype = "下载"
            users.add(u); ftypes.add(ftype)
            by_type[(u, ftype)] = by_type.get((u, ftype), 0) + 1
            if day:
                by_day[(u, day)] = by_day.get((u, day), 0) + 1
        elif action.startswith("approval_"):
            ftype = "审批"
            users.add(u); ftypes.add(ftype)
            by_type[(u, ftype)] = by_type.get((u, ftype), 0) + 1
            if day:
                by_day[(u, day)] = by_day.get((u, day), 0) + 1
        elif u in ("admin", "system") and action not in excl_actions:
            # 管理/系统动作（admin 配置、清理、system 归档等）；普通用户的非文件动作不计入统计
            ftype = "管理操作"
            users.add(u); ftypes.add(ftype)
            by_type[(u, ftype)] = by_type.get((u, ftype), 0) + 1
            if day:
                by_day[(u, day)] = by_day.get((u, day), 0) + 1
    # 日期连续填充（含0值），默认近30天
    day_list = []
    d = datetime.datetime.strptime(from_d, "%Y-%m-%d").date()
    end = datetime.datetime.strptime(to_d, "%Y-%m-%d").date()
    while d <= end:
        day_list.append(d.isoformat())
        d += datetime.timedelta(days=1)
    users = sorted(users)
    ftypes = [t for t in STAT_TYPES if t in ftypes]
    return jsonify({
        "from": from_d, "to": to_d,
        "users": users, "types": ftypes, "days": day_list,
        "byType": {u: {t: by_type.get((u, t), 0) for t in ftypes} for u in users},
        "byDay": {u: {day: by_day.get((u, day), 0) for day in day_list} for u in users},
    })

@app.route("/api/stats")
@login_required
@role_required("admin")
def api_stats():
    db = get_db()
    today = datetime.date.today().strftime("%Y-%m-%d")
    today_count = db.execute("SELECT COUNT(*) as c FROM submissions WHERE submit_time LIKE ?", (f"{today}%",)).fetchone()["c"]
    pending = db.execute("SELECT COUNT(*) as c FROM submissions WHERE status LIKE 'pending%'").fetchone()["c"]
    approved = db.execute("SELECT COUNT(*) as c FROM submissions WHERE status IN ('approved','downloaded')").fetchone()["c"]
    auto = db.execute("SELECT COUNT(*) as c FROM submissions WHERE auto_approved=1").fetchone()["c"]
    total = db.execute("SELECT COUNT(*) as c FROM submissions").fetchone()["c"]
    files = db.execute("SELECT COUNT(*) as c FROM submission_files").fetchone()["c"]
    return jsonify({
        "todaySubmitted": today_count, "pendingApproval": pending, "ready": approved,
        "autoApprovalRate": round(auto / total * 100, 1) if total else 0,
        "archivedFiles": files, "avgFerryTime": "~0.1s",
    })

@app.route("/api/health")
def api_health():
    return jsonify({"status": "ok", "time": now_str(), "version": APP_VERSION, "stage": APP_STAGE,
                    "deployMode": DEPLOY_MODE, "resetPassword": RESET_PASSWORD,
                    "envRole": ENV_ROLE})

# ============================================================
# 手动触发过期清理（admin）
# ============================================================
@app.route("/api/admin/cleanup-expired", methods=["POST"])
@login_required
@role_required("admin")
def api_cleanup_expired():
    count = cleanup_expired_files()
    temp_cleaned = cleanup_abandoned_temp()
    msg = f"清理完成：过期文件 {count} 个，未提交临时文件 {temp_cleaned} 个"
    msg_en = (f"Cleanup completed: {count} expired file{'s' if count != 1 else ''}, "
              f"{temp_cleaned} abandoned temp file{'s' if temp_cleaned != 1 else ''}")
    # 审计留痕：管理员手动触发清理（合并两类），明细（逐单超时归档）由 system_archive_expired 记录
    add_audit_log(
        (session.get("user_data") or {}).get("username", "admin"), "admin_cleanup_manual", target="",
        detail=f"手动触发清理：过期归档 {count} 个，未提交临时文件清理 {temp_cleaned} 个"
    )
    return jsonify({"message": msg, "message_en": msg_en, "cleaned": count, "tempCleaned": temp_cleaned})

# ============================================================
# 路由：系统运维（数据生命周期，ADR-011）
# 在线运维（admin 网页 + TDD 可调用）；离线场景（服务停止时）用 infra/ops-*.sh 文件级脚本
# 覆盖：备份 / 恢复 / 出厂重置（自动先备份）/ 模拟数据（仅 testing 模式）
# ============================================================
BACKUP_DIR = DATA_DIR / "backups"

def _backup_now(scope="all"):
    """在线备份 → DATA_DIR/backups/backup-<ts>
    scope: all=DB+NAS 业务目录（默认，兼容旧版） / system=仅系统（DB：含 system_config/ad_config/local_users 等配置与数据）
           / business=仅业务数据（NAS staging/external/archive 文件，用于更换存储目录/历史归档）
    系统备份用于升级前后保证系统可回退；业务备份用于业务文件历史归档与存储迁移（ADR-011 拆分）。"""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    # 备份名区分类型：backup-system-<ts> / backup-business-<ts> / backup-all-<ts>
    # （系统备份与业务数据备份完全独立，名字即类型，普通人可识别，避免混用）
    dest = BACKUP_DIR / f"backup-{scope}-{ts}"
    (dest / "db").mkdir(parents=True, exist_ok=True)
    (dest / "nas").mkdir(parents=True, exist_ok=True)
    if scope in ("all", "system"):
        src_conn = sqlite3.connect(str(DB_PATH))
        dst_conn = sqlite3.connect(str(dest / "db" / "securetrans.db"))
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
            src_conn.close()
    if scope in ("all", "business"):
        for sub in ["staging", "external", "archive"]:
            src = NAS_ROOT / sub
            if src.exists():
                try:
                    # v2.2.31 健壮化：dirs_exist_ok 目标已存在不报错；不跟随 symlink（NAS 挂载点常见）；
                    # 忽略临时/锁文件（.nfs*/.DS_Store/*.tmp 等），避免特殊文件名导致 500（生产 NAS 场景实测）
                    # symlinks=True：复制符号链接本身而非跟随（NAS 挂载点常见，避免越权/死链报错）
                    shutil.copytree(str(src), str(dest / "nas" / sub),
                                    dirs_exist_ok=True, symlinks=True,
                                    ignore=shutil.ignore_patterns(".nfs*", ".DS_Store", "Thumbs.db", "*.tmp", "*.lock"))
                except Exception as e:
                    logger.error("业务备份 copytree 失败 %s/%s: %s", NAS_ROOT, sub, e)
                    shutil.rmtree(str(dest), ignore_errors=True)  # 清理半成品
                    raise
    return dest

def _backup_type(name: str) -> str:
    """从备份名推导类型：backup-system-* → system；backup-business-* → business；其余（backup-all-*/旧版 backup-*）→ all"""
    n = name or ""
    if n.startswith("backup-system-"):
        return "system"
    if n.startswith("backup-business-"):
        return "business"
    return "all"

def _list_backups():
    out = []
    if BACKUP_DIR.exists():
        for d in sorted(BACKUP_DIR.iterdir(), reverse=True):
            if d.is_dir() and d.name.startswith("backup-"):
                size = 0
                for f in d.rglob("*"):
                    if f.is_file():
                        size += f.stat().st_size
                out.append({
                    "name": d.name,
                    "time": d.name[len("backup-"):].replace("_", " "),
                    "size": size,
                    "type": _backup_type(d.name),
                    "hasDb": (d / "db" / "securetrans.db").exists(),
                    "hasNas": any((d / "nas" / sub).exists() and any((d / "nas" / sub).iterdir()) for sub in ["staging", "external", "archive"]),
                })
    return out

def _restore_backup(name, scope=None):
    """从备份恢复（scope 缺省自动按备份名推导，普通人无需知道内部类型；回退 = 再恢复之前的备份）
    system：仅替换 DB（配置+数据），不动业务文件；business：仅替换 NAS 业务目录，不动 DB"""
    if scope is None or scope not in ("all", "system", "business"):
        scope = _backup_type(name)
    src = BACKUP_DIR / name
    if not src.exists():
        return False, "备份不存在"
    if scope in ("all", "system") and not (src / "db" / "securetrans.db").exists():
        return False, f"备份 {name} 不包含系统数据（db），无法按 system/all 恢复"
    if scope in ("all", "business") and not (src / "nas").exists():
        return False, f"备份 {name} 不包含业务数据（nas），无法按 business/all 恢复"
    if scope in ("all", "system"):
        if "db" in g:
            try:
                g.db.close()
            except Exception:
                pass
            g.pop("db", None)
        for suffix in ["", "-wal", "-shm"]:
            p = Path(str(DB_PATH) + suffix)
            if p.exists():
                try:
                    p.unlink()
                except Exception:
                    pass
        shutil.copy2(str(src / "db" / "securetrans.db"), str(DB_PATH))
    if scope in ("all", "business"):
        for sub in ["staging", "external", "archive"]:
            dst = NAS_ROOT / sub
            if dst.exists():
                shutil.rmtree(str(dst), ignore_errors=True)
            src_nas = src / "nas" / sub
            if src_nas.exists():
                shutil.copytree(str(src_nas), str(dst))
            else:
                dst.mkdir(parents=True, exist_ok=True)
    scope_zh = {"all": "系统+业务", "system": "系统", "business": "业务数据"}.get(scope, scope)
    return True, f"恢复完成：{name}（{scope_zh}）；已回滚至备份时点（{name[len('backup-'):].replace('_', ' ')}），请刷新页面"

def _reset_factory():
    """出厂重置（ADR-011）：先自动备份 → 清空业务库与 NAS → init_db 重建 → admin 密码重置为 .env RESET_PASSWORD"""
    _backup_now()
    if "db" in g:
        try:
            g.db.close()
        except Exception:
            pass
        g.pop("db", None)
    for suffix in ["", "-wal", "-shm"]:
        p = Path(str(DB_PATH) + suffix)
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass
    for sub in ["staging", "external", "archive"]:
        dst = NAS_ROOT / sub
        if dst.exists():
            shutil.rmtree(str(dst), ignore_errors=True)
        dst.mkdir(parents=True, exist_ok=True)
    init_db()
    pwd = os.getenv("RESET_PASSWORD", "Init@123456").strip()
    db = get_db()
    db.execute("UPDATE local_users SET password_hash=?, must_change_password=1 WHERE username='admin'",
               (hash_password(pwd),))
    db.commit()
    return True, "已重置出厂状态：业务数据已清空（原数据已自动备份），admin 密码已重置为 .env RESET_PASSWORD，请刷新页面"

def _generate_mock_data():
    """测试/开发环境模拟数据（与 verify.sh 自动化验证闭环）；生产/预生产拒绝"""
    if DEPLOY_MODE != "testing":
        return False, "生产/预生产环境禁止生成模拟数据（ADR-011）"
    db = get_db()
    now = now_str()
    created = 0
    for uname, disp, pwd in [("testuser01", "测试用户一", "Test@123456"),
                             ("approver1", "一级审批人", "Test@123456"),
                             ("approver2", "二级审批人", "Test@123456")]:
        if not db.execute("SELECT id FROM local_users WHERE username=?", (uname,)).fetchone():
            db.execute(
                "INSERT INTO local_users (id,username,password_hash,display_name,email,role,status,must_change_password,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), uname, hash_password(pwd), disp, f"{uname}@mock.local", "internal-user", "active", 0, now))
            created += 1
    for lvl, uname, disp in [(1, "approver1", "一级审批人"), (2, "approver2", "二级审批人")]:
        if not db.execute("SELECT id FROM approvers WHERE username=? AND level=?", (uname, lvl)).fetchone():
            db.execute("INSERT INTO approvers (id,level,username,display_name,scope) VALUES (?,?,?,?,?)",
                       (str(uuid.uuid4()), lvl, uname, disp, "all"))
            created += 1
    for name, contact, email in [("示例合作方A", "张三", "a@partner.com"), ("示例合作方B", "李四", "b@partner.com")]:
        if not db.execute("SELECT id FROM partners WHERE name=?", (name,)).fetchone():
            db.execute("INSERT INTO partners (id,name,contact,email,enabled,created_at) VALUES (?,?,?,?,1,?)",
                       (str(uuid.uuid4()), name, contact, email, now))
            created += 1
    for status, auto, rtype, reason in [("pending", 0, "non-partner", "模拟：待审批提交单"),
                                        ("approved", 1, "partner", "模拟：合作方自动通过"),
                                        ("archived", 1, "partner", "模拟：已归档提交单")]:
        sub_id = gen_submission_id()
        db.execute(
            "INSERT INTO submissions (id,submitter,submitter_name,receiver_name,receiver_email,receiver_type,receiver_org,security_level,reason,expiry_days,status,auto_approved,current_path,submit_time,approved_time,file_count,total_size) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (sub_id, "admin", "系统管理员", "模拟接收人", "", rtype, "示例合作方A" if rtype == "partner" else "模拟外部单位",
             "internal", reason, 7, status, auto, str(ARCHIVE_DIR / sub_id) if status == "archived" else str(EXTERNAL_DIR / sub_id),
             now, now if status != "pending" else None, 1, 1024))
        db.execute("INSERT INTO submission_files (id,submission_id,path,name,size,type,md5,matched,is_archive) VALUES (?,?,?,?,?,?,?,?,?)",
                   (str(uuid.uuid4()), sub_id, "files/mock.pdf", "mock.pdf", 1024, "PDF", "mock-md5", 0, 1 if status == "archived" else 0))
        created += 1
    add_audit_log("admin", "mock_data", "system", "生成模拟数据（测试环境，界面演示用）", get_client_ip())
    db.commit()
    return True, f"模拟数据生成完成（{created} 条）：测试用户/审批人/合作方/各状态提交单，仅界面演示，请勿用于生产"

@app.route("/api/admin/ops/backups")
@login_required
@role_required("admin")
def api_ops_backups():
    return jsonify(_list_backups())

@app.route("/api/admin/ops/backup", methods=["POST"])
@login_required
@role_required("admin")
def api_ops_backup():
    data = request.get_json() or {}
    scope = data.get("scope", "all")
    if scope not in ("all", "system", "business"):
        return jsonify({"error": "scope 仅支持 all/system/business"}), 400
    try:
        dest = _backup_now(scope)
    except Exception as e:
        logger.error("创建备份失败 scope=%s: %s", scope, e)
        return jsonify({"error": f"备份创建失败：{e}", "message_en": f"Backup failed: {e}"}), 500
    add_audit_log(current_user.username, "ops_backup", f"{dest.name}({scope})", f"系统运维：创建{ {'all':'系统+业务','system':'系统','business':'业务数据'}.get(scope,scope) }备份", get_client_ip())
    return jsonify({"message": "备份创建成功", "name": dest.name, "scope": scope})

@app.route("/api/admin/ops/restore", methods=["POST"])
@login_required
@role_required("admin")
def api_ops_restore():
    data = request.get_json() or {}
    name = data.get("backupName", "")
    scope = data.get("scope")  # 缺省自动按备份名推导（_restore_backup 内处理）
    if data.get("confirm") != "RESTORE":
        return jsonify({"error": "请输入确认码 RESTORE"}), 400
    ok, msg = _restore_backup(name, scope)
    if not ok:
        return jsonify({"error": msg}), 400
    add_audit_log(current_user.username, "ops_restore", f"{name}({scope})", "系统运维：从备份恢复数据", get_client_ip())
    return jsonify({"message": msg})

@app.route("/api/admin/ops/backups/<name>", methods=["DELETE"])
@login_required
@role_required("admin")
def api_ops_delete_backup(name):
    """删除备份（不永久保留，运维可清理）；仅允许删除 data/backups/ 下的 backup-* 目录（防路径穿越）"""
    if not name or not name.startswith("backup-"):
        return jsonify({"error": "备份名必须以 backup- 开头"}), 400
    if "/" in name or "\\" in name or name in (".", ".."):
        return jsonify({"error": "非法备份名"}), 400
    target = BACKUP_DIR / name
    if not target.exists() or not target.is_dir():
        return jsonify({"error": f"备份 {name} 不存在"}), 404
    shutil.rmtree(str(target), ignore_errors=True)
    add_audit_log(current_user.username, "ops_delete_backup", name, f"系统运维：删除备份 {name}", get_client_ip())
    return jsonify({"message": f"备份 {name} 已删除"})

@app.route("/api/admin/ops/reset-factory", methods=["POST"])
@login_required
@role_required("admin")
def api_ops_reset_factory():
    data = request.get_json() or {}
    if data.get("confirm") != "RESET":
        return jsonify({"error": "请输入确认码 RESET"}), 400
    ok, msg = _reset_factory()
    if not ok:
        return jsonify({"error": msg}), 400
    add_audit_log("admin", "ops_reset_factory", "system", "系统运维：出厂重置（原数据已自动备份）", get_client_ip())
    return jsonify({"message": msg})

@app.route("/api/admin/ops/mock-data", methods=["POST"])
@login_required
@role_required("admin")
def api_ops_mock_data():
    data = request.get_json() or {}
    if data.get("confirm") != "MOCK":
        return jsonify({"error": "请输入确认码 MOCK"}), 400
    ok, msg = _generate_mock_data()
    if not ok:
        return jsonify({"error": msg}), 403
    return jsonify({"message": msg})

@app.route("/api/admin/submissions/<sub_id>", methods=["DELETE"])
@login_required
@role_required("admin")
def api_delete_submission(sub_id):
    """删除提交单（admin，确认码 DEL 防误触）：
    DB 记录（submissions/submission_files/approvals/download_records）+
    磁盘目录（staging/external/archive 三处对应路径）一并清理。
    用于清理测试数据/误提交；不可恢复，请谨慎（先备份再删）。"""
    data = request.get_json(silent=True) or {}
    if data.get("confirm") != "DEL":
        return jsonify({"error": "删除需确认码 DEL"}), 400
    db = get_db()
    sub = db.execute("SELECT * FROM submissions WHERE id=?", (sub_id,)).fetchone()
    if not sub:
        return jsonify({"error": "提交单不存在"}), 404
    # 磁盘清理（三处目录）
    removed = []
    for d in (STAGING_DIR, EXTERNAL_DIR, ARCHIVE_DIR):
        p = d / sub_id
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)
            removed.append(d.name)
    # DB 清理（submissions 级联删除关联表；download_records 无外键，显式删除）
    db.execute("DELETE FROM download_records WHERE submission_id=?", (sub_id,))
    db.execute("DELETE FROM submissions WHERE id=?", (sub_id,))
    db.commit()
    add_audit_log(current_user.username, "delete_submission", sub_id,
                  f"删除提交单（清理目录: {', '.join(removed) if removed else '无'}）", get_client_ip())
    return jsonify({"message": "提交单已删除"})

# ============================================================
# 错误处理
# ============================================================
@app.errorhandler(413)
def too_large(e):
    return jsonify({"error": f"文件过大，最大支持 {MAX_FILE_SIZE_MB}MB"}), 413

@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "接口不存在"}), 404
    return redirect(url_for("login_page"))

# ============================================================
# 模块级初始化（gunicorn 导入时也会执行，确保数据库表已创建）
# ============================================================
init_db()
scheduler = start_scheduler()

logger.info("=" * 60)
logger.info("SecureTrans 模块初始化完成")
logger.info("  部署模式: %s", DEPLOY_MODE)
logger.info("  存储目录: %s", NAS_ROOT)
logger.info("  数据库: %s", DB_PATH)
if DEPLOY_MODE == "testing":
    logger.info("  [测试模式] 使用本地文件系统，启动方式: python app.py (Flask自带服务器)")
else:
    logger.info("  [生产模式] 使用NAS存储，启动方式: gunicorn app:app (WSGI服务器)")
logger.info("=" * 60)

# ============================================================
# 启动（仅 python app.py 时执行；gunicorn 不执行此块）
# ============================================================
if __name__ == "__main__":
    # CLI: 重置 admin 密码为 .env RESET_PASSWORD（每次部署调用，保证 verify 与首次登录凭据一致）
    if "--reset-admin-password" in sys.argv:
        new_pwd = os.getenv("RESET_PASSWORD", "Init@123456").strip()
        with app.app_context():
            db = get_db()
            row = db.execute("SELECT id FROM local_users WHERE username=?", ("admin",)).fetchone()
            if row:
                db.execute("UPDATE local_users SET password_hash=?, must_change_password=1 WHERE username=?",
                           (hash_password(new_pwd), "admin"))
                db.commit()
                print(f"[SecureTrans] admin 密码已重置为: {new_pwd}（.env RESET_PASSWORD），首次登录需修改")
                sys.exit(0)
            else:
                print("[SecureTrans] admin 用户不存在，跳过重置（首次部署 init_db 已用 RESET_PASSWORD 创建）")
                sys.exit(0)
    # CLI: 出厂重置（ADR-011，离线脚本 ops-reset.sh 调用；含自动备份 + init_db 重建 + admin 密码重置）
    if "--reset-factory" in sys.argv:
        with app.app_context():
            ok, msg = _reset_factory()
            print(f"[SecureTrans] {msg}")
            sys.exit(0 if ok else 1)
    # CLI: 生成模拟数据（ADR-011，测试/开发环境；离线脚本 ops-mock.sh 调用；生产模式拒绝）
    if "--mock-data" in sys.argv:
        with app.app_context():
            ok, msg = _generate_mock_data()
            print(f"[SecureTrans] {msg}")
            sys.exit(0 if ok else 1)
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    logger.info("SecureTrans 启动: http://%s:%s", host, port)
    # 测试模式用 Flask 自带服务器；生产模式应用 gunicorn 启动
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host=host, port=port, debug=debug)

