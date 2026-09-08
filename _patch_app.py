# -*- coding: utf-8 -*-
"""v2.2.14 后端改造：密码可配置 + 配置单一来源(.env<->DB) + 上传大小统一"""
import io

p = "src/app.py"
b = io.open(p, "rb").read()
nl = "\r\n" if b"\r\n" in b else "\n"
s = io.open(p, encoding="utf-8", newline="").read()


def rep(old, new, cnt=1, label=""):
    global s
    old = old.replace("\n", nl)
    new = new.replace("\n", nl)
    n = s.count(old)
    assert n == cnt, f"[{label}] 匹配数={n} 期望={cnt}\n{old[:100]}"
    s = s.replace(old, new, cnt)


# 1. import secrets
rep("import hashlib\n", "import hashlib\nimport secrets\n", label="import secrets")

# 2. 新增可配置常量（EXTERNAL_EXPIRY_DAYS 后）
rep(
    'EXTERNAL_EXPIRY_DAYS = int(os.getenv("EXTERNAL_EXPIRY_DAYS", "7"))  # external 文件默认 7 天过期\n',
    'EXTERNAL_EXPIRY_DAYS = int(os.getenv("EXTERNAL_EXPIRY_DAYS", "7"))  # external 文件默认 7 天过期\n'
    'RESET_PASSWORD = os.getenv("RESET_PASSWORD", "Init@123456").strip()  # 重置密码默认值，可配置(.env)\n'
    'AUTO_APPROVAL_ENABLED = os.getenv("AUTO_APPROVAL_ENABLED", "false").strip().lower()  # 免审批总开关默认关闭\n',
    label="配置常量")

# 3. init_db 种子：从 .env 读（单一来源），旧默认自动迁移
rep(
    '    # 初始系统配置\n'
    '    defaults = {\n'
    '        "auto_approval_enabled": "true",\n'
    '        "default_expiry_days": "7",\n'
    '        "max_file_size_mb": "800",\n'
    '        "app_name": "SecureTrans",\n'
    '    }\n'
    '    for k, v in defaults.items():\n'
    '        conn.execute("INSERT OR IGNORE INTO system_config (key,value) VALUES (?,?)", (k, v))\n',
    '    # 初始系统配置：单一来源 = .env（AUTO_APPROVAL_ENABLED / EXTERNAL_EXPIRY_DAYS / MAX_CONTENT_LENGTH）\n'
    '    defaults = {\n'
    '        "auto_approval_enabled": os.getenv("AUTO_APPROVAL_ENABLED", "false").strip().lower(),\n'
    '        "default_expiry_days": os.getenv("EXTERNAL_EXPIRY_DAYS", "7").strip(),\n'
    '        "max_file_size_mb": str(MAX_CONTENT_LENGTH // 1024 // 1024),\n'
    '        "app_name": "SecureTrans",\n'
    '    }\n'
    '    for k, v in defaults.items():\n'
    '        conn.execute("INSERT OR IGNORE INTO system_config (key,value) VALUES (?,?)", (k, v))\n'
    '    # 旧库迁移：免审批开关旧默认 true（硬编码）→ 与 .env 默认 false 对齐（仅当 env 未显式设置时）\n'
    '    if "AUTO_APPROVAL_ENABLED" not in os.environ:\n'
    '        _row = conn.execute("SELECT value FROM system_config WHERE key=\'auto_approval_enabled\'").fetchone()\n'
    '        if _row and _row["value"] == "true":\n'
    '            conn.execute("UPDATE system_config SET value=\'false\' WHERE key=\'auto_approval_enabled\'")\n',
    label="init_db 种子")

# 4. 新增 write_env_config（放在 get_config_value 后）
rep(
    'def get_config_value(key: str, default: str = None) -> str:\n'
    '    """读取系统配置项，不存在返回 default"""\n'
    '    db = get_db()\n'
    '    row = db.execute("SELECT value FROM system_config WHERE key=?", (key,)).fetchone()\n'
    '    return row["value"] if row else default\n',
    'def get_config_value(key: str, default: str = None) -> str:\n'
    '    """读取系统配置项，不存在返回 default"""\n'
    '    db = get_db()\n'
    '    row = db.execute("SELECT value FROM system_config WHERE key=?", (key,)).fetchone()\n'
    '    return row["value"] if row else default\n'
    '\n'
    'ENV_FILE = BASE_DIR / ".env"\n'
    '\n'
    'def write_env_config(updates: dict) -> bool:\n'
    '    """系统配置变更写回 .env（单一配置源持久化）。.env 不存在时跳过（配置已存 DB）。"""\n'
    '    if not ENV_FILE.exists():\n'
    '        return False\n'
    '    text = ENV_FILE.read_text(encoding="utf-8", errors="ignore")\n'
    '    for k, v in updates.items():\n'
    '        line = f"{k}={v}"\n'
    '        pat = re.compile(rf"^{re.escape(k)}=.*$", re.MULTILINE)\n'
    '        if pat.search(text):\n'
    '            text = pat.sub(line, text, count=1)\n'
    '        else:\n'
    '            text = text.rstrip("\\n") + "\\n" + line + "\\n"\n'
    '    ENV_FILE.write_text(text, encoding="utf-8")\n'
    '    return True\n',
    label="write_env_config")

# 5. 上传大小校验：统一读 system_config（与界面一致，运行时生效）
rep(
    '    # 检查文件大小\n'
    '    file.seek(0, 2)\n'
    '    size = file.tell()\n'
    '    file.seek(0)\n'
    '    if size > MAX_CONTENT_LENGTH:\n'
    '        return jsonify({"error": f"文件过大，最大支持 {MAX_CONTENT_LENGTH//1024//1024}MB"}), 400\n',
    '    # 检查文件大小：单一来源 system_config max_file_size_mb（与界面一致，运行时生效）\n'
    '    file.seek(0, 2)\n'
    '    size = file.tell()\n'
    '    file.seek(0)\n'
    '    try:\n'
    '        max_mb = int(float(get_config_value("max_file_size_mb", str(MAX_CONTENT_LENGTH // 1024 // 1024)) or 0))\n'
    '    except (ValueError, TypeError):\n'
    '        max_mb = MAX_CONTENT_LENGTH // 1024 // 1024\n'
    '    if max_mb <= 0:\n'
    '        max_mb = MAX_CONTENT_LENGTH // 1024 // 1024\n'
    '    if size > max_mb * 1024 * 1024:\n'
    '        return jsonify({"error": f"文件过大，最大支持 {max_mb}MB"}), 400\n',
    label="上传大小校验")

# 6. 过期归档兜底：读 system_config（DB 为主，env 为 fallback）
rep(
    '    expiry_days = row["expiry_days"] if row["expiry_days"] is not None else EXTERNAL_EXPIRY_DAYS\n',
    '    try:\n'
    '        _cfg_expiry = int(float(get_config_value("default_expiry_days", str(EXTERNAL_EXPIRY_DAYS)) or 0))\n'
    '    except (ValueError, TypeError):\n'
    '        _cfg_expiry = EXTERNAL_EXPIRY_DAYS\n'
    '    expiry_days = row["expiry_days"] if row["expiry_days"] is not None else _cfg_expiry\n',
    label="过期兜底")

# 7. reset-password：可配置
rep(
    '    new_pwd = "Init@123456"\n',
    '    new_pwd = os.getenv("RESET_PASSWORD", "Init@123456").strip()\n',
    label="reset 密码")

# 8. 创建用户：密码可选（留空随机生成 + must_change）
rep(
    '    username = data.get("username", "").strip()\n'
    '    password = data.get("password", "")\n'
    '    display_name = data.get("displayName", "")\n'
    '    email = data.get("email", "")\n'
    '    # 不设 role 体系：所有非 admin 用户统一为普通用户，审批权由 approvers 表配置\n'
    '    role = "internal-user"\n'
    '    if not username or not password:\n'
    '        return jsonify({"error": "用户名和密码不能为空"}), 400\n'
    '    if len(password) < 6:\n'
    '        return jsonify({"error": "密码至少6位"}), 400\n'
    '    db = get_db()\n'
    '    exists = db.execute("SELECT COUNT(*) as c FROM local_users WHERE username=?", (username,)).fetchone()["c"]\n'
    '    if exists:\n'
    '        return jsonify({"error": "用户名已存在"}), 400\n'
    '    db.execute(\n'
    '        "INSERT INTO local_users (id,username,password_hash,display_name,email,role,status,enabled,created_at) VALUES (?,?,?,?,?,?,?,1,?)",\n'
    '        (str(uuid.uuid4()), username, hash_password(password), display_name, email, role, "active", now_str())\n'
    '    )\n'
    '    db.commit()\n'
    '    add_audit_log(current_user.username, "create_local_user", username, f"创建本地用户，角色{role}（默认使能）", get_client_ip())\n'
    '    return jsonify({"message": "创建成功"})\n',
    '    username = data.get("username", "").strip()\n'
    '    password = data.get("password", "")\n'
    '    display_name = data.get("displayName", "")\n'
    '    email = data.get("email", "")\n'
    '    # 不设 role 体系：所有非 admin 用户统一为普通用户，审批权由 approvers 表配置\n'
    '    role = "internal-user"\n'
    '    if not username:\n'
    '        return jsonify({"error": "用户名不能为空"}), 400\n'
    '    random_pwd = False\n'
    '    if not password:\n'
    '        password = secrets.token_urlsafe(9)  # 留空自动生成初始密码\n'
    '        random_pwd = True\n'
    '    if len(password) < 6:\n'
    '        return jsonify({"error": "密码至少6位"}), 400\n'
    '    db = get_db()\n'
    '    exists = db.execute("SELECT COUNT(*) as c FROM local_users WHERE username=?", (username,)).fetchone()["c"]\n'
    '    if exists:\n'
    '        return jsonify({"error": "用户名已存在"}), 400\n'
    '    db.execute(\n'
    '        "INSERT INTO local_users (id,username,password_hash,display_name,email,role,status,enabled,must_change_password,created_at) VALUES (?,?,?,?,?,?,?,1,?,?)",\n'
    '        (str(uuid.uuid4()), username, hash_password(password), display_name, email, role, "active", 1 if random_pwd else 0, now_str())\n'
    '    )\n'
    '    db.commit()\n'
    '    add_audit_log(current_user.username, "create_local_user", username, f"创建本地用户，角色{role}（默认使能）", get_client_ip())\n'
    '    msg = "创建成功" + (f"，初始密码：{password}（请安全告知用户，首次登录后可自行修改）" if random_pwd else "")\n'
    '    return jsonify({"message": msg, "initialPassword": password if random_pwd else None})\n',
    label="创建用户")

# 9. PUT /api/config/system：写 DB + 写回 .env + 运行时更新 Flask 上限
rep(
    '    config = request.get_json()\n'
    '    db = get_db()\n'
    '    for k, v in config.items():\n'
    '        db.execute("INSERT OR REPLACE INTO system_config (key,value) VALUES (?,?)", (k, str(v)))\n'
    '    db.commit()\n'
    '    add_audit_log(current_user.username, "update_system_config", "", json.dumps(config, ensure_ascii=False), get_client_ip())\n'
    '    return jsonify({"message": "配置已保存"})\n',
    '    config = request.get_json()\n'
    '    db = get_db()\n'
    '    env_updates = {}\n'
    '    for k, v in config.items():\n'
    '        db.execute("INSERT OR REPLACE INTO system_config (key,value) VALUES (?,?)", (k, str(v)))\n'
    '        # 同步映射回 .env（单一配置源）：max_file_size_mb→MAX_CONTENT_LENGTH 等\n'
    '        if k == "max_file_size_mb":\n'
    '            try:\n'
    '                env_updates["MAX_CONTENT_LENGTH"] = str(int(float(v)) * 1024 * 1024)\n'
    '            except (ValueError, TypeError):\n'
    '                pass\n'
    '        elif k == "default_expiry_days":\n'
    '            try:\n'
    '                env_updates["EXTERNAL_EXPIRY_DAYS"] = str(int(float(v)))\n'
    '            except (ValueError, TypeError):\n'
    '                pass\n'
    '        elif k == "auto_approval_enabled":\n'
    '            env_updates["AUTO_APPROVAL_ENABLED"] = "true" if str(v).lower() == "true" else "false"\n'
    '    db.commit()\n'
    '    synced = False\n'
    '    if env_updates:\n'
    '        synced = write_env_config(env_updates)\n'
    '        if "MAX_CONTENT_LENGTH" in env_updates:\n'
    '            try:\n'
    '                app.config["MAX_CONTENT_LENGTH"] = int(env_updates["MAX_CONTENT_LENGTH"])\n'
    '            except (ValueError, TypeError):\n'
    '                pass\n'
    '    add_audit_log(current_user.username, "update_system_config", "", json.dumps(config, ensure_ascii=False), get_client_ip())\n'
    '    msg = "配置已保存" + ("，并同步到 .env（重启后由 systemd 加载）" if synced else "（未同步 .env，仅存数据库）")\n'
    '    return jsonify({"message": msg})\n',
    label="PUT 系统配置")

io.open(p, "w", encoding="utf-8", newline="").write(s)
print("app.py 补丁完成")
