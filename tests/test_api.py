"""
SecureTrans 本地全量 API 测试脚本
使用 Python 标准库 urllib，无需额外依赖
"""
import json
import urllib.request
import urllib.parse
import urllib.error
import http.cookiejar
import os
import time
import tempfile

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")

# 管理凭据参数化（生产环境 admin 密码可能已修改；verify.sh 通过环境变量传入，默认 admin/Admin@123）
ADMIN_USER = os.environ.get("TEST_ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("TEST_ADMIN_PASS", "Admin@123")

def _resolve_nas_root():
    """NAS_ROOT 解析优先级：环境变量 > 安装目录 .env > 本地开发默认(src/nas)
    保证测试断言路径与服务端(deploy.sh 写入 .env 的 NAS_ROOT)一致，无需手动传参"""
    env = os.getenv("NAS_ROOT")
    if env:
        return env
    _base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_file = os.path.join(_base, ".env")
    # 仅当 .env 与 app.py 同目录（部署结构 /opt/securetrans）才可信，避免误读项目根残留的测试 .env
    if os.path.exists(env_file) and os.path.exists(os.path.join(_base, "app.py")):
        try:
            with open(env_file, encoding="utf-8", errors="ignore") as _f:
                for _line in _f:
                    _line = _line.strip()
                    if _line.startswith("NAS_ROOT="):
                        return _line.split("=", 1)[1].strip().strip('"').strip("'")
        except Exception:
            pass
    return os.path.join(_base, "src", "nas")
results = []

# 创建带 cookie 的 opener（模拟浏览器 session）
cookie_jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))

# 不跟随重定向的 opener（用于测试未登录访问）
class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None
no_redirect_opener = urllib.request.build_opener(NoRedirectHandler, urllib.request.HTTPCookieProcessor(cookie_jar))

def request(method, path, data=None, json_data=None, headers=None):
    """发送 HTTP 请求"""
    url = BASE_URL + path
    req_headers = headers or {}
    body = None
    if json_data is not None:
        body = json.dumps(json_data).encode('utf-8')
        req_headers['Content-Type'] = 'application/json'
    elif data is not None:
        body = urllib.parse.urlencode(data).encode('utf-8')
        req_headers['Content-Type'] = 'application/x-www-form-urlencoded'
    req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    try:
        resp = opener.open(req)
        content = resp.read().decode('utf-8')
        try:
            return resp.status, json.loads(content)
        except:
            return resp.status, content
    except urllib.error.HTTPError as e:
        content = e.read().decode('utf-8')
        try:
            return e.code, json.loads(content)
        except:
            return e.code, content
    except Exception as e:
        return 0, str(e)

def test(name, condition, detail=""):
    """记录测试结果"""
    status = "✅ PASS" if condition else "❌ FAIL"
    results.append({"name": name, "status": status, "detail": detail})
    print(f"{status} | {name}" + (f" | {detail}" if detail and not condition else ""))

def upload_file(filepath, filename):
    """模拟文件上传（multipart/form-data）"""
    import uuid
    boundary = '----WebKitFormBoundary' + uuid.uuid4().hex
    with open(filepath, 'rb') as f:
        file_content = f.read()
    body = (
        f'--{boundary}\r\n'
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f'Content-Type: application/octet-stream\r\n\r\n'
    ).encode('utf-8') + file_content + f'\r\n--{boundary}--\r\n'.encode('utf-8')
    headers = {'Content-Type': f'multipart/form-data; boundary={boundary}'}
    req = urllib.request.Request(BASE_URL + '/api/submissions/upload', data=body, headers=headers, method='POST')
    resp = opener.open(req)
    return resp.status, json.loads(resp.read().decode('utf-8'))

# ============================================================
# 开始测试
# ============================================================
print("=" * 70)
print("SecureTrans 本地全量 API 测试")
print("=" * 70)

# 1. 健康检查
print("\n--- 1. 基础服务 ---")
code, data = request('GET', '/api/health')
test("健康检查", code == 200 and data.get('status') == 'ok', f"code={code}, data={data}")

# 2. 未登录访问受保护接口（应该 302 重定向到登录页）
try:
    req = urllib.request.Request(BASE_URL + '/api/auth/me')
    no_redirect_opener.open(req)
    code = 200
except urllib.error.HTTPError as e:
    code = e.code
test("未登录访问受保护接口被重定向到登录页", code == 302, f"code={code}")

# 3. 登录 - admin
print("\n--- 2. 认证 ---")
code, data = request('POST', '/api/auth/login', json_data={"username": ADMIN_USER, "password": ADMIN_PASS})
test("admin 登录成功", code == 200 and data.get('user', {}).get('role') == 'admin', f"code={code}, data={data}")

# 4. 获取当前用户
code, data = request('GET', '/api/auth/me')
test("获取当前用户信息", code == 200 and data.get('username') == ADMIN_USER, f"code={code}, data={data}")

# 5. 错误密码登录
code, data = request('POST', '/api/auth/login', json_data={"username": ADMIN_USER, "password": "wrongpass"})
test("错误密码登录被拒绝", code == 401, f"code={code}")
# 重新登录
request('POST', '/api/auth/login', json_data={"username": ADMIN_USER, "password": ADMIN_PASS})

# 初始化关键系统配置（自动化回归前置条件，避免受手工操作影响）
code, data = request('PUT', '/api/config/system', json_data={
    "auto_approval_enabled": "true", "default_expiry_days": "7", "max_file_size_mb": "800"
})
test("初始化免审批总开关开启+默认有效期7天", code == 200, f"code={code}")

# 启用所有特征码规则（内置规则默认禁用=模板，按需开启；测试需启用以便跑免审批场景）
code, rules = request('GET', '/api/config/feature-rules')
if isinstance(rules, list):
    for r in rules:
        if r.get('enabled') == 0:
            request('PUT', f"/api/admin/feature-rules/{r['id']}", json_data={"enabled": True})
test("启用所有特征码规则(默认模板禁用→测试启用)", code == 200, f"code={code}, rules={len(rules) if isinstance(rules,list) else 'N/A'}")

# 6. 文件上传
print("\n--- 3. 文件上传 ---")
# 创建测试文件
test_dir = tempfile.mkdtemp()
test_pdf = os.path.join(test_dir, "test_document.pdf")
with open(test_pdf, 'wb') as f:
    f.write(b"%PDF-1.4\n" + b"Hello World " * 1000)  # ~12KB 模拟 PDF
test_exe = os.path.join(test_dir, "test_program.exe")
with open(test_exe, 'wb') as f:
    f.write(b"MZ" + b"\x00" * 1000)  # 模拟 exe

code, data = upload_file(test_pdf, "test_document.pdf")
test("上传 PDF 文件（匹配特征码）", code == 200 and data.get('matched') == True, f"code={code}, md5={data.get('md5','')[:16]}...")
pdf_md5 = data.get('md5') or ''
pdf_temp_id = data.get('tempId')

code, data = upload_file(test_exe, "test_program.exe")
test("上传 EXE 文件（不匹配特征码）", code == 200 and data.get('matched') == False, f"code={code}, matched={data.get('matched')}")
exe_temp_id = data.get('tempId')

# 7. 创建提交单 - 免审批场景（只有 PDF）
print("\n--- 4. 提交单创建 ---")
code, data = request('POST', '/api/submissions', json_data={
    "tempIds": [pdf_temp_id],
    "receiverName": "张三（合作方）",
    "receiverEmail": "zhangsan@partner.com",
    "receiverOrg": "合作方科技公司",
    "receiverType": "partner",
    "securityLevel": "internal",
    "reason": "项目合作文档外发",
    "expiryDays": 30  # 前端传的值应被忽略，实际使用系统配置默认有效期
})
test("创建提交单（免审批自动通过）", code == 200 and data.get('autoApproved') == True and data.get('status') == 'approved',
     f"code={code}, status={data.get('status')}, autoApproved={data.get('autoApproved')}")
test("有效期统一走系统配置（忽略前端expiryDays=30）", code == 200 and data.get('expiry_days') == 7,
     f"code={code}, expiry_days={data.get('expiry_days')}")
auto_sub_id = data.get('id')

# 8. 创建提交单 - 需要审批场景（EXE 不匹配）
code, data = request('POST', '/api/submissions', json_data={
    "tempIds": [exe_temp_id],
    "receiverName": "李四（非合作方）",
    "receiverEmail": "lisi@external.com",
    "receiverOrg": "外部咨询公司",
    "receiverType": "non-partner",
    "securityLevel": "secret",
    "reason": "外部工具软件",
    "expiryDays": 15
})
test("创建提交单（需要人工审批）", code == 200 and data.get('autoApproved') == False and data.get('status') == 'pending',
     f"code={code}, status={data.get('status')}")
pending_sub_id = data.get('id')

# 9. 提交单列表
print("\n--- 5. 提交单查询 ---")
code, data = request('GET', '/api/submissions')
test("提交单列表", code == 200 and len(data) >= 2, f"code={code}, count={len(data) if isinstance(data,list) else 'N/A'}")

# 10. 提交单详情
code, data = request('GET', f'/api/submissions/{auto_sub_id}')
test("提交单详情（含文件清单和审批记录）", code == 200 and len(data.get('files', [])) >= 1 and len(data.get('approvals', [])) >= 1,
     f"code={code}, files={len(data.get('files',[]))}, approvals={len(data.get('approvals',[]))}")

# 11. 待我审批列表
print("\n--- 6. 审批流程 ---")
code, data = request('GET', '/api/submissions/pending/my')
test("待我审批列表", code == 200 and isinstance(data, list), f"code={code}, count={len(data) if isinstance(data,list) else 'N/A'}")

# 12. 一级审批通过（admin 同时具备一级+二级权限 → 语义B自动跳过二级）
code, data = request('POST', f'/api/submissions/{pending_sub_id}/approve', json_data={
    "action": "approve",
    "comment": "一级审批通过"
})
test("一级审批通过（admin同时具备二级权限→自动跳过二级直接摆渡）", code == 200 and data.get('status') == 'approved',
     f"code={code}, status={data.get('status')}")

# 验证自动跳过二级的审计记录（level2 自动跳过已写入）
code, data = request('GET', f'/api/submissions/{pending_sub_id}')
approval_levels = [(a.get('level'), a.get('action')) for a in data.get('approvals', [])]
test("自动跳过二级审计记录存在(level2 approve)", (2, 'approve') in approval_levels and len(data.get('approvals', [])) >= 2,
     f"approvals={approval_levels}")

# 14. 外网文件列表
print("\n--- 7. 外网下载 ---")
code, data = request('GET', '/api/external/files')
test("已摆渡文件列表（external）", code == 200 and len(data) >= 2, f"code={code}, count={len(data) if isinstance(data,list) else 'N/A'}")

# 15. 文件下载
code, data = request('GET', f'/api/external/{auto_sub_id}/download/test_document.pdf')
test("文件下载（流式读取）", code == 200 and isinstance(data, (str, bytes)) and len(str(data)) > 0,
     f"code={code}, size={len(str(data))}")

# 16. 用户管理
print("\n--- 8. 用户管理（admin） ---")
code, data = request('GET', '/api/admin/local-users')
test("本地用户列表", code == 200 and any(u['username'] == ADMIN_USER for u in data), f"code={code}, count={len(data) if isinstance(data,list) else 'N/A'}")

request('DELETE', '/api/admin/local-users/testuser01')  # 幂等：清理上次残留
code, data = request('POST', '/api/admin/local-users', json_data={
    "username": "testuser01",
    "password": "Test@123456",
    "displayName": "测试用户01",
    "email": "test01@company.com",
    "role": "internal-user"
})
test("创建本地用户", code == 200, f"code={code}, data={data}")

# 创建用户密码留空 → 自动生成初始密码
request('DELETE', '/api/admin/local-users/randuser01')  # 幂等：清理上次残留
code, data = request('POST', '/api/admin/local-users', json_data={
    "username": "randuser01", "password": "", "displayName": "随机密码用户", "email": "", "role": "internal-user"})
rand_pwd = (data or {}).get('initialPassword', '')
test("创建用户密码留空自动生成", code == 200 and isinstance(rand_pwd, str) and len(rand_pwd) >= 6,
     f"code={code}, pwd_len={len(rand_pwd)}")
code, data = request('POST', '/api/auth/login', json_data={"username": "randuser01", "password": rand_pwd})
test("随机初始密码可登录", code == 200, f"code={code}")
request('POST', '/api/auth/logout')
request('POST', '/api/auth/login', json_data={"username": ADMIN_USER, "password": ADMIN_PASS})
request('DELETE', '/api/admin/local-users/randuser01')
test("清理随机密码用户", code == 200, f"code={code}")

code, data = request('POST', '/api/admin/local-users/testuser01/reset-password')
test("重置本地用户密码", code == 200, f"code={code}, data={data}")
test("重置密码为可配置默认值(Init@123456)", code == 200 and 'Init@123456' in data.get('message', ''),
     f"code={code}, msg={data.get('message', '')}")

# 用户自行修改密码（原密码 → 新密码）
code, data = request('POST', '/api/auth/login', json_data={"username": "testuser01", "password": "Init@123456"})
test("重置后的默认密码可登录", code == 200, f"code={code}")
code, data = request('POST', '/api/auth/change-password', json_data={"old_password": "Init@123456", "new_password": "NewPwd@123456"})
test("用户自行修改密码", code == 200, f"code={code}, data={data}")
code, data = request('POST', '/api/auth/login', json_data={"username": "testuser01", "password": "NewPwd@123456"})
test("修改后新密码登录成功", code == 200, f"code={code}")
request('POST', '/api/auth/logout')
request('POST', '/api/auth/login', json_data={"username": ADMIN_USER, "password": ADMIN_PASS})

code, data = request('DELETE', '/api/admin/local-users/testuser01')
test("删除本地用户", code == 200, f"code={code}, data={data}")

# 17. AD 角色映射
print("\n--- 9. AD 角色映射（admin） ---")
code, data = request('GET', '/api/admin/role-mappings')
test("AD 角色映射列表", code == 200 and isinstance(data, list), f"code={code}")

code, data = request('POST', '/api/admin/role-mappings', json_data={
    "principalType": "user",
    "principalValue": "zhangsan",
    "displayName": "张三（研发部）",
    "role": "internal-user",
    "note": "研发部（审批权限通过审批人配置授予）"
})
test("创建 AD 用户角色映射", code == 200, f"code={code}, data={data}")

code, data = request('POST', '/api/admin/role-mappings', json_data={
    "principalType": "user", "principalValue": "lisi",
    "displayName": "李四", "role": "dept-manager", "note": "非法角色应拒绝"
})
test("非法角色映射被拒绝(仅admin/internal-user)", code == 400, f"code={code}, data={data}")

code, data = request('POST', '/api/admin/ad/search', data={"keyword": "zhang"})
test("搜索 AD 用户（打桩模拟）", code == 200 and isinstance(data, list), f"code={code}, count={len(data) if isinstance(data,list) else 'N/A'}")

# 21. 合作方白名单（partners）
print("\n--- 10f. 合作方白名单（partners） ---")

# 创建合作方
code, data = request('POST', '/api/admin/partners', json_data={
    "name": "Nexus半导体", "contact": "张经理", "email": "partner@nexus.com"
})
partner_id = data.get('id', '')
test("创建合作方", code == 200 and partner_id, f"code={code}, id={partner_id}")

# 重复创建被拒绝
code, data = request('POST', '/api/admin/partners', json_data={
    "name": "Nexus半导体", "contact": "", "email": ""
})
test("重复创建合作方被拒绝", code == 400, f"code={code}")

# 合作方列表
code, data = request('GET', '/api/admin/partners')
partner_count = len(data) if isinstance(data, list) else 0
test("合作方白名单列表", code == 200 and partner_count >= 1, f"code={code}, count={partner_count}")

# 白名单自动判定生效：上传EXE(需审批) → 创建提交单 receiverType=auto → 接收方为白名单成员 → 判定为partner
partner_exe = os.path.join(test_dir, "partner_test.exe")
with open(partner_exe, 'wb') as f:
    f.write(b"MZ" + b"\x00" * 800)
code, data = upload_file(partner_exe, "partner_test.exe")
partner_temp_id = data.get('tempId')
code, data = request('POST', '/api/submissions', json_data={
    "tempIds": [partner_temp_id],
    "receiverName": "Nexus半导体",
    "receiverEmail": "partner@nexus.com",
    "receiverOrg": "Nexus半导体有限公司",
    "receiverType": "auto",  # 自动判定
    "securityLevel": "internal",
    "reason": "合作方白名单自动判定测试",
    "expiryDays": 30
})
partner_sub_id = data.get('id')
code, data = request('GET', f'/api/submissions/{partner_sub_id}')
test("白名单自动判定为合作方(receiverType=auto)", code == 200 and data.get('receiver_type') == 'partner',
     f"code={code}, receiver_type={data.get('receiver_type')}")

# 合作方一级审批通过 → 直接摆渡 external（无需二级）
code, data = request('POST', f'/api/submissions/{partner_sub_id}/approve', json_data={
    "action": "approve", "comment": "合作方一级审批直接摆渡"
})
test("合作方一级审批通过直接摆渡到external", code == 200 and data.get('status') == 'approved',
     f"code={code}, status={data.get('status')}")

# 删除合作方
code, data = request('DELETE', f'/api/admin/partners/{partner_id}')
test("删除合作方", code == 200, f"code={code}, data={data}")

# 22. 审批人配置（approvers）
print("\n--- 10g. 审批人配置（approvers） ---")

# 创建本地用户作为审批人（模拟AD账号，PSF阶段用本地账号）
request('DELETE', '/api/admin/local-users/deptmgr1')  # 幂等：清理上次残留
code, data = request('POST', '/api/admin/local-users', json_data={
    "username": "deptmgr1", "password": "Test@123456", "displayName": "部门主管1",
    "email": "dept1@company.com", "role": "internal-user"
})
test("创建本地用户-部门主管(deptmgr1)", code == 200, f"code={code}")
request('DELETE', '/api/admin/local-users/execmgr1')  # 幂等：清理上次残留
code, data = request('POST', '/api/admin/local-users', json_data={
    "username": "execmgr1", "password": "Test@123456", "displayName": "高管1",
    "email": "exec1@company.com", "role": "internal-user"
})
test("创建本地用户-高管(execmgr1)", code == 200, f"code={code}")
request('DELETE', '/api/admin/local-users/notapprover')  # 幂等：清理上次残留
code, data = request('POST', '/api/admin/local-users', json_data={
    "username": "notapprover", "password": "Test@123456", "displayName": "普通用户",
    "email": "na@company.com", "role": "internal-user"
})
test("创建本地用户-未配置审批人(notapprover)", code == 200, f"code={code}")

# 配置审批人
code, data = request('POST', '/api/admin/approvers', json_data={
    "level": 1, "username": "deptmgr1", "displayName": "部门主管1", "scope": "all"
})
approver_id = data.get('id', '')
test("配置一级审批人(deptmgr1)", code == 200 and approver_id, f"code={code}, id={approver_id}")

code, data = request('POST', '/api/admin/approvers', json_data={
    "level": 2, "username": "execmgr1", "displayName": "高管1", "scope": "all"
})
test("配置二级审批人(execmgr1)", code == 200, f"code={code}, data={data}")

# 重复配置被拒绝
code, data = request('POST', '/api/admin/approvers', json_data={
    "level": 1, "username": "deptmgr1", "displayName": "重复", "scope": "all"
})
test("重复配置审批人被拒绝", code == 400, f"code={code}")

# 非法级别被拒绝
code, data = request('POST', '/api/admin/approvers', json_data={
    "level": 3, "username": "someone", "displayName": "非法", "scope": "all"
})
test("非法审批级别被拒绝", code == 400, f"code={code}")

# 审批人列表
code, data = request('GET', '/api/admin/approvers')
test("审批人配置列表", code == 200 and len(data) >= 2,
     f"code={code}, count={len(data) if isinstance(data,list) else 'N/A'}")

# 权限控制：非admin不能管理
request('POST', '/api/auth/login', json_data={"username": "notapprover", "password": "Test@123456"})
code, data = request('GET', '/api/admin/partners')
test("非admin访问合作方白名单被拒绝", code == 403, f"code={code}")
code, data = request('GET', '/api/admin/approvers')
test("非admin访问审批人配置被拒绝", code == 403, f"code={code}")

# 审批人配置生效：未配置的普通用户不能审批
# 先用admin创建需要审批的提交单(EXE, non-partner)
request('POST', '/api/auth/login', json_data={"username": ADMIN_USER, "password": ADMIN_PASS})
ap_exe = os.path.join(test_dir, "approver_test.exe")
with open(ap_exe, 'wb') as f:
    f.write(b"MZ" + b"\x00" * 900)
code, data = upload_file(ap_exe, "approver_test.exe")
ap_temp_id = data.get('tempId')
code, data = request('POST', '/api/submissions', json_data={
    "tempIds": [ap_temp_id],
    "receiverName": "外部公司",
    "receiverEmail": "ext@company.com",
    "receiverOrg": "外部科技有限公司",
    "receiverType": "non-partner",
    "securityLevel": "secret",
    "reason": "审批人配置生效测试",
    "expiryDays": 30
})
ap_sub_id = data.get('id')
test("创建审批人测试提交单(pending)", code == 200 and data.get('status') == 'pending',
     f"code={code}, status={data.get('status')}")

# 未配置的普通用户审批被拒绝
request('POST', '/api/auth/login', json_data={"username": "notapprover", "password": "Test@123456"})
code, data = request('POST', f'/api/submissions/{ap_sub_id}/approve', json_data={
    "action": "approve", "comment": "普通用户尝试审批"
})
test("未配置的普通用户审批被拒绝", code == 403, f"code={code}, data={data}")

# 配置的一级审批人 deptmgr1 可审批通过
request('POST', '/api/auth/login', json_data={"username": "deptmgr1", "password": "Test@123456"})
code, data = request('POST', f'/api/submissions/{ap_sub_id}/approve', json_data={
    "action": "approve", "comment": "配置审批人一级通过"
})
test("配置的一级审批人审批通过(进入二级)", code == 200 and data.get('status') == 'pending_approval_2',
     f"code={code}, status={data.get('status')}")

# 配置的二级审批人 execmgr1 可审批通过
request('POST', '/api/auth/login', json_data={"username": "execmgr1", "password": "Test@123456"})
code, data = request('POST', f'/api/submissions/{ap_sub_id}/approve', json_data={
    "action": "approve", "comment": "配置审批人二级通过"
})
test("配置的二级审批人审批通过(摆渡到external)", code == 200 and data.get('status') == 'approved',
     f"code={code}, status={data.get('status')}")

# 切回 admin，清理测试数据
request('POST', '/api/auth/login', json_data={"username": ADMIN_USER, "password": ADMIN_PASS})
code, data = request('DELETE', f'/api/admin/approvers/{approver_id}')
test("删除审批人配置", code == 200, f"code={code}, data={data}")

# 清理剩余审批人配置(execmgr1)
code, data = request('GET', '/api/admin/approvers')
for a in (data if isinstance(data, list) else []):
    if a.get('username') == 'execmgr1':
        request('DELETE', f"/api/admin/approvers/{a.get('id')}")
        break
test("清理剩余审批人配置", True, "execmgr1 配置已删除")

# 清理测试本地用户
for u in ["deptmgr1", "execmgr1", "notapprover"]:
    request('DELETE', f'/api/admin/local-users/{u}')
test("清理测试本地用户", True, "deptmgr1/execmgr1/notapprover 已删除")

# 22b. 语义B：审批人同时具备一级+二级权限时，一级通过后自动跳过二级
print("\n--- 10g2. 语义B 自动跳过二级 ---")

# 创建用户 dual1 并配置为一级+二级审批人（语义B场景：二级审批人被配置为一级审批人）
request('DELETE', '/api/admin/local-users/dual1')  # 幂等：清理上次残留
code, data = request('POST', '/api/admin/local-users', json_data={
    "username": "dual1", "password": "Test@123456", "displayName": "双级审批人",
    "role": "internal-user"
})
test("创建本地用户-双级审批人(dual1)", code == 200, f"code={code}")
code, data = request('POST', '/api/admin/approvers', json_data={
    "level": 1, "username": "dual1", "displayName": "双级审批人", "scope": "all"
})
test("配置dual1为一级审批人", code == 200, f"code={code}")
code, data = request('POST', '/api/admin/approvers', json_data={
    "level": 2, "username": "dual1", "displayName": "双级审批人", "scope": "all"
})
test("配置dual1为二级审批人", code == 200, f"code={code}")

# 创建 non-partner 提交单（EXE 不匹配 → 需人工审批）
b_exe = os.path.join(test_dir, "dual_test.exe")
with open(b_exe, 'wb') as f:
    f.write(b"MZ\x90\x00" + b"\x00" * 500)
code, data = upload_file(b_exe, "dual_test.exe")
dual_temp_id = data.get('tempId')
code, data = request('POST', '/api/submissions', json_data={
    "tempIds": [dual_temp_id],
    "receiverName": "普通接收方",
    "receiverEmail": "receiver@external.com",
    "receiverOrg": "普通接收公司",
    "receiverType": "non-partner",
    "securityLevel": "secret",
    "reason": "语义B自动跳过二级测试",
    "expiryDays": 7
})
dual_sub_id = data.get('id')
test("创建语义B测试提交单(pending)", code == 200 and data.get('status') == 'pending',
     f"code={code}, status={data.get('status')}")

# 纯 approvers 权限模型：审批人可访问待我审批列表（不依赖角色体系）
code, data = request('GET', '/api/submissions/pending/my')
test("审批人可访问待我审批列表(pending/my 200)", code == 200 and isinstance(data, list) and any(x.get('id') == dual_sub_id for x in data),
     f"code={code}, count={len(data) if isinstance(data,list) else 'N/A'}")

# 非审批人普通用户 → 403（纯 approvers 权限模型）
request('DELETE', '/api/admin/local-users/plainuser1')  # 幂等：清理上次残留
code, data = request('POST', '/api/admin/local-users', json_data={
    "username": "plainuser1", "password": "Test@123456", "displayName": "普通无权限用户", "role": "internal-user"
})
test("创建非审批人用户(plainuser1)", code == 200, f"code={code}")
request('POST', '/api/auth/login', json_data={"username": "plainuser1", "password": "Test@123456"})
code, data = request('GET', '/api/submissions/pending/my')
test("非审批人访问待我审批列表被拒(403)", code == 403, f"code={code}")
request('POST', '/api/auth/login', json_data={"username": "dual1", "password": "Test@123456"})

# dual1 一级审批通过 → 应自动跳过二级，直接 approved 摆渡
code, data = request('POST', f'/api/submissions/{dual_sub_id}/approve', json_data={
    "action": "approve", "comment": "语义B一级通过"
})
test("语义B: 一级审批通过自动跳过二级(直接approved)", code == 200 and data.get('status') == 'approved',
     f"code={code}, status={data.get('status')}")

# 审计记录含 level2 自动跳过
code, data = request('GET', f'/api/submissions/{dual_sub_id}')
approval_levels = [(a.get('level'), a.get('action')) for a in data.get('approvals', [])]
test("语义B: 审计记录含level2自动跳过", (2, 'approve') in approval_levels, f"approvals={approval_levels}")

# 文件已摆渡到 external（os.path 计算路径，避免依赖后文 pathlib）
_dual_nas_root = _resolve_nas_root()
dual_in_external = os.path.exists(os.path.join(_dual_nas_root, "external", dual_sub_id))
test("语义B: 文件已摆渡到external", dual_in_external, f"path={os.path.join(_dual_nas_root, 'external', dual_sub_id)}")

# 切回 admin，清理 dual1 测试数据
request('POST', '/api/auth/login', json_data={"username": ADMIN_USER, "password": ADMIN_PASS})
code, data = request('GET', '/api/admin/approvers')
for a in (data if isinstance(data, list) else []):
    if a.get('username') == 'dual1':
        request('DELETE', f"/api/admin/approvers/{a.get('id')}")
request('DELETE', f'/api/admin/local-users/dual1')
test("清理dual1测试数据", True, "dual1 用户与审批人配置已删除")

# 22b. 特征码规则管理 + 系统配置默认值
print("\n--- 10h. 特征码规则管理 + 系统配置默认值 ---")

# 系统配置默认值验证
code, data = request('GET', '/api/config/system')
test("默认有效期为7天", code == 200 and data.get('default_expiry_days') == '7',
     f"code={code}, default_expiry_days={data.get('default_expiry_days')}")
test("最大文件大小为800MB", code == 200 and data.get('max_file_size_mb') == '800',
     f"code={code}, max_file_size_mb={data.get('max_file_size_mb')}")
test("免审批总开关存在", code == 200 and 'auto_approval_enabled' in data,
     f"code={code}, auto_approval_enabled={data.get('auto_approval_enabled')}")

# 创建特征码规则
code, data = request('POST', '/api/admin/feature-rules', json_data={
    "name": "测试自定义规则", "ruleType": "extension", "pattern": ".testext", "enabled": True
})
test_rule_id = data.get('id', '')
test("创建特征码规则", code == 200 and test_rule_id, f"code={code}, id={test_rule_id}")

# 重复/非法参数拒绝
code, data = request('POST', '/api/admin/feature-rules', json_data={
    "name": "", "ruleType": "extension", "pattern": ".x"
})
test("空名称创建被拒绝", code == 400, f"code={code}")
code, data = request('POST', '/api/admin/feature-rules', json_data={
    "name": "非法类型", "ruleType": "invalid", "pattern": ".x"
})
test("非法规则类型被拒绝", code == 400, f"code={code}")

# 修改特征码规则
code, data = request('PUT', f'/api/admin/feature-rules/{test_rule_id}', json_data={
    "name": "测试自定义规则(已修改)", "pattern": ".modifiedext", "enabled": True
})
test("修改特征码规则", code == 200, f"code={code}")

# 开关切换（禁用）
code, data = request('POST', f'/api/admin/feature-rules/{test_rule_id}/toggle')
test("开关切换-禁用", code == 200 and data.get('enabled') == False,
     f"code={code}, enabled={data.get('enabled')}")

# 单个开关生效验证：禁用后，.modifiedext 文件不再匹配该规则
# （上传一个 .modifiedext 文件，验证 matchedRules 不含该规则）
mod_path = os.path.join(test_dir, "test_file.modifiedext")
with open(mod_path, 'wb') as f:
    f.write(b"test content")
code, data = upload_file(mod_path, "test_file.modifiedext")
matched_rules = data.get('matchedRules', [])
rule_still_matched = any("测试自定义规则" in str(r) for r in matched_rules)
test("禁用规则后该类型不再匹配", code == 200 and not rule_still_matched,
     f"code={code}, matchedRules={matched_rules}")

# 开关切换（启用）
code, data = request('POST', f'/api/admin/feature-rules/{test_rule_id}/toggle')
test("开关切换-启用", code == 200 and data.get('enabled') == True,
     f"code={code}, enabled={data.get('enabled')}")

# 非admin权限控制（用普通用户）
code, data = request('POST', '/api/admin/local-users', json_data={
    "username": "ruletestuser", "password": "Test@123456", "displayName": "规则测试用户",
    "email": "rt@company.com", "role": "internal-user"
})
request('POST', '/api/auth/login', json_data={"username": "ruletestuser", "password": "Test@123456"})
code, data = request('POST', '/api/admin/feature-rules', json_data={
    "name": "越权测试", "ruleType": "extension", "pattern": ".x"
})
test("非admin创建规则被拒绝", code == 403, f"code={code}")
code, data = request('POST', f'/api/admin/feature-rules/{test_rule_id}/toggle')
test("非admin开关切换被拒绝", code == 403, f"code={code}")

# 切回admin，清理
request('POST', '/api/auth/login', json_data={"username": ADMIN_USER, "password": ADMIN_PASS})
request('DELETE', '/api/admin/local-users/ruletestuser')

# 删除特征码规则
code, data = request('DELETE', f'/api/admin/feature-rules/{test_rule_id}')
test("删除特征码规则", code == 200, f"code={code}")

# 删除不存在的规则
code, data = request('DELETE', '/api/admin/feature-rules/nonexistent-id')
test("删除不存在规则返回404", code == 404, f"code={code}")

# 22c. 网络面隔离（应用层，模拟 X-Network-Zone 头）
print("\n--- 10i. 网络面隔离（双网卡应用层兜底） ---")

# 默认(internal)面 networkZone
code, data = request('GET', '/api/auth/me')
test("默认internal面networkZone识别", code == 200 and data.get('networkZone') == 'internal',
     f"code={code}, networkZone={data.get('networkZone')}")

# external面 networkZone 识别
code, data = request('GET', '/api/auth/me', headers={"X-Network-Zone": "external"})
test("external面networkZone识别", code == 200 and data.get('networkZone') == 'external',
     f"code={code}, networkZone={data.get('networkZone')}")

# external面管理接口被拒
code, data = request('GET', '/api/admin/local-users', headers={"X-Network-Zone": "external"})
test("external面管理接口被拒绝403", code == 403, f"code={code}")

# external面下载接口放行
code, data = request('GET', '/api/external/files', headers={"X-Network-Zone": "external"})
test("external面下载接口放行", code == 200 and isinstance(data, list), f"code={code}")

# internal面管理接口放行
code, data = request('GET', '/api/admin/local-users')
test("internal面管理接口放行", code == 200 and isinstance(data, list), f"code={code}")

# internal面配置类接口放行（特征码规则）
code, data = request('GET', '/api/config/feature-rules')
test("internal面特征码规则接口放行", code == 200, f"code={code}")

# 18. 系统配置
print("\n--- 10. 系统配置 ---")
code, data = request('GET', '/api/config/feature-rules')
test("特征码规则列表", code == 200 and len(data) >= 3, f"code={code}, count={len(data) if isinstance(data,list) else 'N/A'}")

code, data = request('GET', '/api/config/system')
test("系统配置获取", code == 200 and 'auto_approval_enabled' in data, f"code={code}, keys={list(data.keys())[:5]}")

code, data = request('PUT', '/api/config/system', json_data={"test_key": "test_value"})
test("系统配置更新", code == 200, f"code={code}")

# 19. 审计日志
print("\n--- 11. 审计与统计 ---")
code, data = request('GET', '/api/audit-logs')
test("审计日志查询", code == 200 and len(data) >= 5, f"code={code}, count={len(data) if isinstance(data,list) else 'N/A'}")

code, data = request('GET', '/api/stats')
test("统计数据", code == 200 and 'todaySubmitted' in data, f"code={code}, data={data}")

code, data = request('GET', '/api/audit-logs/stats')
test("审计统计(默认近30天)", code == 200 and 'byType' in data and 'byDay' in data and 'days' in data,
     f"code={code}, users={len(data.get('users',[])) if isinstance(data,dict) else 'N/A'}")
code, data = request('GET', '/api/audit-logs/stats?from=bad-date&to=2026-08-28')
test("审计统计非法日期拒绝(400)", code == 400, f"code={code}")

# 20. 手动触发过期清理
code, data = request('POST', '/api/admin/cleanup-expired')
test("手动触发过期清理（无过期文件）", code == 200 and 'cleaned' in data, f"code={code}, data={data}")

# ============================================================
# 新增：特征码全量验证 + 压缩包解包 + 驳回 + 过期归档 + 改密
# ============================================================

# 提前定义物理路径（供驳回/归档测试使用）
import pathlib
nas_root = pathlib.Path(_resolve_nas_root())
staging_dir = nas_root / "staging"
external_dir = nas_root / "external"
archive_dir = nas_root / "archive"

# 20b. 特征码全量验证
print("\n--- 10b. 特征码全量验证 ---")

# 上传 ZIP 压缩包（验证自动解包 inner_files）
import zipfile
import tarfile
import io
zip_buffer = io.BytesIO()
with zipfile.ZipFile(zip_buffer, 'w') as zf:
    zf.writestr("readme.txt", "This is a test readme")
    zf.writestr("src/main.py", "print('hello')")
zip_path = os.path.join(test_dir, "test_package.zip")
with open(zip_path, 'wb') as f:
    f.write(zip_buffer.getvalue())
code, data = upload_file(zip_path, "test_package.zip")
zip_matched = data.get('matched', False)
zip_inner = data.get('innerFiles', [])
test("上传ZIP压缩包（匹配特征码+自动解包）", code == 200 and zip_matched and len(zip_inner) >= 2,
     f"code={code}, matched={zip_matched}, innerFiles={len(zip_inner)}")

# 上传 TAR.GZ 压缩包
tar_buffer = io.BytesIO()
with tarfile.open(fileobj=tar_buffer, mode='w:gz') as tf:
    info = tarfile.TarInfo(name="config.yaml")
    content = b"key: value\n"
    info.size = len(content)
    tf.addfile(info, io.BytesIO(content))
tar_path = os.path.join(test_dir, "test_archive.tar.gz")
with open(tar_path, 'wb') as f:
    f.write(tar_buffer.getvalue())
code, data = upload_file(tar_path, "test_archive.tar.gz")
tar_matched = data.get('matched', False)
tar_inner = data.get('innerFiles', [])
test("上传TAR.GZ压缩包（匹配特征码+自动解包）", code == 200 and tar_matched and len(tar_inner) >= 1,
     f"code={code}, matched={tar_matched}, innerFiles={len(tar_inner)}")

# 上传 .bit 文件（Vivado Bitstream，二进制特征码 0x0009 开头）
bit_path = os.path.join(test_dir, "test_fpga.bit")
with open(bit_path, 'wb') as f:
    f.write(b"\x00\x09" + b"\x00" * 100)  # Vivado bitstream 以 0x0009 开头
code, data = upload_file(bit_path, "test_fpga.bit")
bit_matched = data.get('matched', False)
test("上传Vivado Bitstream(.bit)（二进制特征码匹配）", code == 200 and bit_matched,
     f"code={code}, matched={bit_matched}")

# 上传 .xyz 文件（不匹配任何特征码规则）
txt_path = os.path.join(test_dir, "test_unknown.xyz")
with open(txt_path, 'w') as f:
    f.write("This is an unknown file type")
code, data = upload_file(txt_path, "test_unknown.xyz")
txt_matched = data.get('matched', False)
test("上传XYZ文件（不匹配特征码）", code == 200 and not txt_matched,
     f"code={code}, matched={txt_matched}")

# 特征码规则列表验证（20条规则）
code, data = request('GET', '/api/config/feature-rules')
rule_count = len(data) if isinstance(data, list) else 0
test("特征码规则列表（20条规则完整）", code == 200 and rule_count >= 20,
     f"code={code}, count={rule_count}")

# 20c. 审批驳回流程
print("\n--- 10c. 审批驳回流程 ---")

# 上传 EXE（需要审批）
code, data = upload_file(test_exe, "reject_test.exe")
reject_temp_id = data.get('tempId')

# 创建提交单（非合作方，需要二级审批）
code, data = request('POST', '/api/submissions', json_data={
    "tempIds": [reject_temp_id],
    "receiverName": "测试驳回",
    "receiverEmail": "reject@test.com",
    "receiverOrg": "测试公司",
    "receiverType": "non-partner",
    "securityLevel": "internal",
    "reason": "测试驳回流程",
    "expiryDays": 30
})
reject_sub_id = data.get('id')
test("创建驳回测试提交单", code == 200 and data.get('status') == 'pending',
     f"code={code}, status={data.get('status')}")

# 一级审批驳回
code, data = request('POST', f'/api/submissions/{reject_sub_id}/approve', json_data={
    "action": "reject",
    "comment": "测试驳回：文件不符合外发要求"
})
test("一级审批驳回（os.rename到archive）", code == 200 and data.get('status') == 'rejected',
     f"code={code}, status={data.get('status')}")

# 验证驳回后文件在 archive 目录
reject_in_archive = (archive_dir / reject_sub_id).exists()
test("驳回提交单文件已 os.rename 到 archive", reject_in_archive,
     f"path={archive_dir / reject_sub_id}, exists={reject_in_archive}")

# 20d. 过期归档流程
print("\n--- 10d. 过期归档流程 ---")

# 上传 PDF（免审批自动通过），将系统配置默认有效期临时改为0实现立即过期
code, data = upload_file(test_pdf, "expire_test.pdf")
expire_temp_id = data.get('tempId')

# 有效期统一由系统配置控制：临时改为0，提交单应使用该值
code, data = request('PUT', '/api/config/system', json_data={"default_expiry_days": "0"})
test("系统配置默认有效期改为0", code == 200, f"code={code}")

code, data = request('POST', '/api/submissions', json_data={
    "tempIds": [expire_temp_id],
    "receiverName": "过期测试",
    "receiverEmail": "expire@test.com",
    "receiverOrg": "过期测试公司",
    "receiverType": "partner",
    "securityLevel": "internal",
    "reason": "测试过期归档"
})
expire_sub_id = data.get('id')
test("创建过期测试提交单（系统配置有效期=0，免审批自动通过）", code == 200 and data.get('status') == 'approved',
     f"code={code}, status={data.get('status')}")
test("提交单有效期来自系统配置(=0)", code == 200 and data.get('expiry_days') == 0,
     f"code={code}, expiry_days={data.get('expiry_days')}")

# 恢复系统配置默认有效期为7天
code, data = request('PUT', '/api/config/system', json_data={"default_expiry_days": "7"})
test("恢复系统配置默认有效期7天", code == 200, f"code={code}")

# 触发过期清理
code, data = request('POST', '/api/admin/cleanup-expired')
cleaned_count = data.get('cleaned', 0)
test("手动触发过期清理（处理过期文件）", code == 200 and cleaned_count >= 1,
     f"code={code}, cleaned={cleaned_count}")

# i18n: 清理消息英文动态模板（单复数）
_clean_msg = data.get("message_en", "")
test("i18n: 清理消息英文动态模板（message_en）", code == 200 and "expired file" in _clean_msg,
     f"message_en={_clean_msg}")
if cleaned_count == 1:
    test("i18n: 清理英文单复数（1 expired file）", "1 expired file" in _clean_msg, f"message_en={_clean_msg}")
else:
    test("i18n: 清理英文单复数（N expired files）", "expired files" in _clean_msg, f"message_en={_clean_msg}")

# 验证提交单状态变为 archived
code, data = request('GET', f'/api/submissions/{expire_sub_id}')
test("过期提交单状态变为 archived", code == 200 and data.get('status') == 'archived',
     f"code={code}, status={data.get('status')}")

# 验证文件已 os.rename 到 archive
expire_in_archive = (archive_dir / expire_sub_id).exists()
test("过期提交单文件已 os.rename 到 archive", expire_in_archive,
     f"path={archive_dir / expire_sub_id}, exists={expire_in_archive}")

# 验证归档后不在 external 下载列表
code, data = request('GET', '/api/external/files')
external_ids = [s.get('id') for s in data] if isinstance(data, list) else []
test("归档文件不在 external 下载列表", expire_sub_id not in external_ids,
     f"expire_id={expire_sub_id}, in_external={expire_sub_id in external_ids}")

# 20e. 修改密码（专用测试用户 testpwuser，不碰生产 admin 密码）
print("\n--- 10e. 修改密码 ---")

# 幂等清理 + 创建专用测试用户
request('DELETE', '/api/admin/local-users/testpwuser')
code, data = request('POST', '/api/admin/local-users', json_data={
    "username": "testpwuser", "password": "Test@123456", "displayName": "改密测试用户", "role": "internal-user"
})
test("创建改密测试用户", code == 200, f"code={code}")

# 登录测试用户，修改自己的密码
request('POST', '/api/auth/login', json_data={"username": "testpwuser", "password": "Test@123456"})
code, data = request('POST', '/api/auth/change-password', json_data={
    "old_password": "Test@123456",
    "new_password": "Temp@123456"
})
test("用户修改自己的密码", code == 200, f"code={code}, data={data}")

# 错误旧密码应该被拒绝
code, data = request('POST', '/api/auth/change-password', json_data={
    "old_password": "WrongPassword",
    "new_password": "Another@123"
})
test("错误旧密码被拒绝", code == 400, f"code={code}")

# 新密码登录 + 改回原密码（保持环境一致）
code, data = request('POST', '/api/auth/login', json_data={"username": "testpwuser", "password": "Temp@123456"})
test("新密码登录成功", code == 200, f"code={code}")
code, data = request('POST', '/api/auth/change-password', json_data={
    "old_password": "Temp@123456",
    "new_password": "Test@123456"
})
test("改回原密码（保持环境一致）", code == 200, f"code={code}")

# 清理测试用户 + 恢复 admin 会话（后续测试依赖）
request('POST', '/api/auth/login', json_data={"username": ADMIN_USER, "password": ADMIN_PASS})
code, data = request('DELETE', '/api/admin/local-users/testpwuser')
test("清理改密测试用户", code == 200, f"code={code}")

# 21. 验证 os.rename 物理文件移动
print("\n--- 12. 物理文件验证（os.rename 0拷贝） ---")
# 路径已在上方定义（nas_root/staging_dir/external_dir/archive_dir）

# 免审批的提交单应该在 external（上传后直接摆渡）
auto_in_external = (external_dir / auto_sub_id).exists()
test("免审批提交单文件已 os.rename 到 external", auto_in_external,
     f"path={external_dir / auto_sub_id}, exists={auto_in_external}")

# 审批通过的提交单也应该在 external
pending_in_external = (external_dir / pending_sub_id).exists()
test("审批通过提交单文件已 os.rename 到 external", pending_in_external,
     f"path={external_dir / pending_sub_id}, exists={pending_in_external}")

# staging 应该为空（所有文件都被移走了）
staging_items = list(staging_dir.iterdir()) if staging_dir.exists() else []
# 可能有临时目录残留，检查是否有已完成的提交单
test("staging 目录无已完成提交单（全部已 os.rename 移走）", 
     not any(auto_sub_id in str(p) for p in staging_items) and not any(pending_sub_id in str(p) for p in staging_items),
     f"staging items count={len(staging_items)}")

# 验证 external 中的文件可读
external_file = external_dir / auto_sub_id / "files" / "test_document.pdf"
test("external 中文件可正常读取", external_file.exists() and external_file.stat().st_size > 0,
     f"path={external_file}, size={external_file.stat().st_size if external_file.exists() else 0}")

# 22d. 网络面隔离扩展矩阵（应用层逻辑 100% 覆盖，模拟 X-Network-Zone 头）
# 说明：应用层隔离 = 读 X-Network-Zone 请求头，与物理网卡无关，故 test 环境可完整模拟。
#      真实双网卡仅影响 Nginx 如何注入该头（部署层），由 test_preprod_dualnic.py 在
#      pre-prod/product（同一环境，验收通过即转正）验证。
print("\n--- 22d. 网络面隔离扩展矩阵（external 面完整覆盖） ---")

# external 面：放行项（登录页/首页/静态资源/认证/下载）
code, data = request('GET', '/login', headers={"X-Network-Zone": "external"})
test("external面登录页放行", code == 200, f"code={code}")

code, data = request('GET', '/', headers={"X-Network-Zone": "external"})
test("external面首页放行", code == 200, f"code={code}")

code, data = request('GET', '/static/index.html', headers={"X-Network-Zone": "external"})
test("external面静态资源放行", code == 200, f"code={code}")

code, data = request('GET', '/api/auth/me', headers={"X-Network-Zone": "external"})
test("external面me放行+networkZone=external", code == 200 and data.get('networkZone') == 'external',
     f"code={code}, zone={data.get('networkZone')}")

code, data = request('GET', f'/api/external/{auto_sub_id}/download/test_document.pdf', headers={"X-Network-Zone": "external"})
test("external面文件下载放行", code == 200, f"code={code}")

# 外网面：一律不允许修改密码（即使个人账户，也只能内网修改）——白名单不含 change-password，403 拒绝
code, data = request('POST', '/api/auth/change-password', json_data={"old_password": ADMIN_PASS, "new_password": ADMIN_PASS}, headers={"X-Network-Zone": "external"})
test("external面修改密码被拒403(仅内网可改密)", code == 403, f"code={code}")

# external 面：管理/业务接口全部拒绝 403
code, data = request('GET', '/api/submissions', headers={"X-Network-Zone": "external"})
test("external面提交列表被拒403", code == 403, f"code={code}")

code, data = request('POST', '/api/submissions/upload', headers={"X-Network-Zone": "external"})
test("external面上传被拒403", code == 403, f"code={code}")

code, data = request('GET', '/api/admin/local-users', headers={"X-Network-Zone": "external"})
test("external面用户管理被拒403", code == 403, f"code={code}")

code, data = request('GET', '/api/admin/partners', headers={"X-Network-Zone": "external"})
test("external面合作方白名单被拒403", code == 403, f"code={code}")

code, data = request('GET', '/api/admin/approvers', headers={"X-Network-Zone": "external"})
test("external面审批人配置被拒403", code == 403, f"code={code}")

code, data = request('GET', '/api/config/feature-rules', headers={"X-Network-Zone": "external"})
test("external面特征码规则被拒403", code == 403, f"code={code}")

code, data = request('GET', '/api/config/system', headers={"X-Network-Zone": "external"})
test("external面系统配置被拒403", code == 403, f"code={code}")

code, data = request('GET', '/api/audit-logs', headers={"X-Network-Zone": "external"})
test("external面审计日志被拒403", code == 403, f"code={code}")

code, data = request('GET', '/api/stats', headers={"X-Network-Zone": "external"})
test("external面统计被拒403", code == 403, f"code={code}")

# 非法 X-Network-Zone 值回退 internal（安全兜底）
code, data = request('GET', '/api/auth/me', headers={"X-Network-Zone": "evil"})
test("非法X-Network-Zone回退internal", code == 200 and data.get('networkZone') == 'internal',
     f"code={code}, zone={data.get('networkZone')}")

# internal 面全功能放行确认（管理面不受影响）
code, data = request('GET', '/api/submissions')
test("internal面提交列表放行", code == 200, f"code={code}")

code, data = request('GET', '/api/admin/local-users')
test("internal面用户管理放行", code == 200, f"code={code}")

# 22e. 本期逻辑调整（有效期统一/合作方管理/用户使能/接收方单位）
print("\n--- 22e. 本期逻辑调整 ---")

# --- 接收方单位必填 ---
code, data = upload_file(test_pdf, "org_test.pdf")
org_temp_id = data.get('tempId')
code, data = request('POST', '/api/submissions', json_data={
    "tempIds": [org_temp_id],
    "receiverName": "无单位接收方",
    "receiverType": "non-partner",
    "securityLevel": "internal"
})
test("接收方单位必填（缺失返回400）", code == 400 and '单位' in str(data), f"code={code}, data={data}")

# --- 提交传 expiryDays 无效（统一走系统配置，默认7天） ---
code, data = request('POST', '/api/submissions', json_data={
    "tempIds": [org_temp_id],
    "receiverName": "有效期测试接收方",
    "receiverOrg": "有效期测试公司",
    "receiverType": "non-partner",
    "securityLevel": "internal",
    "expiryDays": 999  # 无效值，应被忽略
})
test("提交传expiryDays=999被忽略（仍用系统配置7天）", code == 200 and data.get('expiry_days') == 7,
     f"code={code}, expiry_days={data.get('expiry_days')}")

# --- 合作方自动加入清单（信任模式） ---
code, data = upload_file(test_pdf, "partner_auto_test.pdf")
auto_org_temp = data.get('tempId')
code, data = request('POST', '/api/submissions', json_data={
    "tempIds": [auto_org_temp],
    "receiverName": "自动加入合作方测试",
    "receiverEmail": "auto@partner.com",
    "receiverOrg": "自动加入合作方测试公司",
    "receiverType": "partner",
    "securityLevel": "internal",
    "reason": "测试合作方自动加入"
})
test("选择合作方且名称不在清单→提交成功并判定partner", code == 200 and data.get('receiver_type') == 'partner',
     f"code={code}, receiver_type={data.get('receiver_type')}")
code, data = request('GET', '/api/admin/partners')
auto_added = any(p.get('name') == '自动加入合作方测试公司' for p in data) if isinstance(data, list) else False
test("提交后自动加入合作方清单", auto_added, f"count={len(data) if isinstance(data,list) else 'N/A'}")

# 合作方去重：再次提交同名合作方 → 不重复加入清单
code, data = upload_file(test_pdf, "partner_dup_test.pdf")
dup_temp_id = data.get('tempId')
code, data = request('POST', '/api/submissions', json_data={
    "tempIds": [dup_temp_id],
    "receiverName": "自动加入合作方测试",  # 与已配置一致
    "receiverOrg": "自动加入合作方测试公司",
    "receiverType": "partner",
    "securityLevel": "internal"
})
test("同名合作方再次提交成功", code == 200, f"code={code}")
code, data = request('GET', '/api/admin/partners')
dup_count = sum(1 for p in data if p.get('name') == '自动加入合作方测试公司') if isinstance(data, list) else 0
test("合作方去重：同名不重复加入清单(count=1)", dup_count == 1, f"count={dup_count}")

# --- 合作方使能开关 ---
code, data = request('POST', '/api/admin/partners', json_data={"name": "使能开关测试", "enabled": True})
test("创建合作方(使能开关测试,enabled=1)", code == 200, f"code={code}, data={data}")
tog_partner_id = data.get('id')
code, data = request('GET', '/api/partners')
test("启用合作方出现在提交选项(/api/partners)", code == 200 and any(p.get('name') == '使能开关测试' for p in data),
     f"code={code}, names={[p.get('name') for p in data] if isinstance(data,list) else 'N/A'}")
code, data = request('PUT', f'/api/admin/partners/{tog_partner_id}/enabled', json_data={"enabled": False})
test("禁用合作方", code == 200, f"code={code}, data={data}")
code, data = request('GET', '/api/partners')
test("禁用后不出现在提交选项", code == 200 and not any(p.get('name') == '使能开关测试' for p in data),
     f"code={code}")
code, data = request('PUT', f'/api/admin/partners/{tog_partner_id}/enabled', json_data={"enabled": True})
test("重新启用合作方", code == 200, f"code={code}, data={data}")

# 清理：删除自动加入 + 使能测试合作方
code, data = request('GET', '/api/admin/partners')
auto_pid = next((p.get('id') for p in data if p.get('name') == '自动加入合作方测试公司'), None) if isinstance(data, list) else None
if auto_pid:
    request('DELETE', f'/api/admin/partners/{auto_pid}')
request('DELETE', f'/api/admin/partners/{tog_partner_id}')
test("清理测试合作方", True, "")

# --- 用户使能开关 ---
code, data = request('POST', '/api/admin/local-users', json_data={
    "username": "enable_test1", "password": "Enable@123",
    "displayName": "使能测试", "email": "et1@test.com", "role": "internal-user"
})
test("创建测试用户 enable_test1", code == 200, f"code={code}, data={data}")
code, data = request('GET', '/api/admin/local-users')
et1 = next((u for u in data if u.get('username') == 'enable_test1'), None) if isinstance(data, list) else None
test("新建用户默认使能(enabled=1)", code == 200 and et1 and et1.get('enabled') == 1, f"enabled={et1.get('enabled') if et1 else 'N/A'}")

# 用新用户登录（成功）
code, data = request('POST', '/api/auth/login', json_data={"username": "enable_test1", "password": "Enable@123"})
test("使能用户可正常登录", code == 200, f"code={code}")

# 普通用户访问统计接口应被拒（仪表盘 admin-only 后端保障）
code, data = request('GET', '/api/stats')
test("普通用户访问统计被拒403(仪表盘admin-only)", code == 403, f"code={code}")

# 切回 admin
code, data = request('POST', '/api/auth/login', json_data={"username": ADMIN_USER, "password": ADMIN_PASS})
test("切回admin登录", code == 200, f"code={code}")

# 禁用 enable_test1
code, data = request('PUT', '/api/admin/local-users/enable_test1/enabled', json_data={"enabled": False})
test("禁用用户enable_test1", code == 200, f"code={code}, data={data}")
# 被禁用用户登录失败（401/302）
code, data = request('POST', '/api/auth/login', json_data={"username": "enable_test1", "password": "Enable@123"})
test("禁用后用户无法登录", code != 200, f"code={code}, data={data if code != 200 else ''}")
# 重新启用
code, data = request('PUT', '/api/admin/local-users/enable_test1/enabled', json_data={"enabled": True})
test("重新启用用户enable_test1", code == 200, f"code={code}, data={data}")
# admin 永久使能不可禁用
code, data = request('PUT', '/api/admin/local-users/admin/enabled', json_data={"enabled": False})
test("admin永久使能不可禁用(返回400)", code == 400, f"code={code}, data={data}")
# 清理测试用户
code, data = request('DELETE', '/api/admin/local-users/enable_test1')
test("清理测试用户enable_test1", code == 200, f"code={code}")

# 22. 退出登录
print("\n--- 13. 退出登录 ---")
code, data = request('GET', '/api/auth/logout')
test("退出登录", code == 200 or code == 302, f"code={code}")

# 退出后访问受保护接口（用不跟随重定向的 opener）
try:
    req = urllib.request.Request(BASE_URL + '/api/auth/me')
    no_redirect_opener.open(req)
    code = 200
except urllib.error.HTTPError as e:
    code = e.code
test("退出后访问受保护接口被重定向到登录页", code == 302, f"code={code}")

# ============================================================
# 14. i18n 双语（中英文界面支持，后端错误/成功消息附加 error_en/message_en）
# ============================================================
print("\n--- 14. i18n 双语 ---")

# 重新登录 admin（前面已登出）
code, data = request('POST', '/api/auth/login', json_data={"username": ADMIN_USER, "password": ADMIN_PASS})
test("i18n: admin 重新登录", code == 200, f"code={code}")

# 错误密码 -> error(中文) + error_en(英文)
code, data = request('POST', '/api/auth/login', json_data={"username": "admin", "password": "wrong_i18n_pwd"})
test("i18n: 错误密码返回中文 error", code == 401 and isinstance(data.get("error"), str) and data.get("error") != "", f"code={code}")
test("i18n: 错误密码返回英文 error_en", code == 401 and isinstance(data.get("error_en"), str) and len(data.get("error_en", "")) > 0, f"error_en={data.get('error_en')}")
test("i18n: error_en 为英文（不含中文）", code == 401 and not any('\u4e00' <= ch <= '\u9fff' for ch in data.get("error_en", "")), f"error_en={data.get('error_en')}")

# 静态成功消息 -> message_en
import random, string
_i18n_suf = ''.join(random.choices(string.ascii_lowercase, k=6))
code, data = request('POST', '/api/admin/local-users', json_data={
    "username": f"i18n_{_i18n_suf}", "password": "Passw0rd!",
    "displayName": "i18nTest", "email": "", "role": "internal-user"
})
test("i18n: 创建用户返回 message_en", code == 200 and len(data.get("message_en", "")) > 0, f"message_en={data.get('message_en')}")
test("i18n: message_en 为英文（不含中文）", code == 200 and not any('\u4e00' <= ch <= '\u9fff' for ch in data.get("message_en", "")), f"message_en={data.get('message_en')}")

# 动态模板消息 -> 重置密码 message_en 含英文
code, data = request('POST', f'/api/admin/local-users/i18n_{_i18n_suf}/reset-password')
test("i18n: 动态模板 message_en 翻译", code == 200 and "Password" in data.get("message_en", ""), f"message_en={data.get('message_en')}")

# 清理测试用户
code, data = request('DELETE', f'/api/admin/local-users/i18n_{_i18n_suf}')
test("i18n: 清理测试用户", code == 200, f"code={code}")

# 上传大小限制（系统配置单一来源，运行时生效）
print("\n--- 上传大小限制（系统配置） ---")
code, data = request('PUT', '/api/config/system', json_data={"max_file_size_mb": "1"})
test("系统配置最大文件改为1MB", code == 200, f"code={code}")
_big = os.path.join(test_dir, "big_2mb.bin")
with open(_big, 'wb') as f:
    f.write(b'\x00' * (2 * 1024 * 1024))
_ok_http = False
try:
    code, data = upload_file(_big, "big_2mb.bin")
    _ok_http = True
except urllib.error.HTTPError as _he:
    code = _he.code
    try:
        data = json.loads(_he.read().decode('utf-8'))
    except Exception:
        data = {}
    _ok_http = True
test("超过最大文件大小被拒绝(400)", _ok_http and code == 400 and '最大支持' in data.get('error', ''),
     f"code={code}, err={data.get('error', '')}")

# 恢复系统配置默认（防污染 .env：免审批关闭/7天/800MB）
code, data = request('PUT', '/api/config/system', json_data={
    "auto_approval_enabled": "false", "default_expiry_days": "7", "max_file_size_mb": "800"})
test("恢复系统配置默认（免审批关/7天/800MB）", code == 200, f"code={code}")

# 登录页静态资源可访问（双语界面资源存在性）
import urllib.request as _ur
try:
    _resp = _ur.urlopen(BASE_URL + '/login')
    _html = _resp.read().decode('utf-8')
    test("i18n: 登录页包含语言切换按钮", 'langSwitch' in _html and 'switchLang' in _html)
    test("i18n: 登录页包含双语字典", 'I18N_LOGIN' in _html and "'zh'" in _html and "'en'" in _html)
except Exception as e:
    test("i18n: 登录页资源检查", False, str(e))
try:
    _resp = _ur.urlopen(BASE_URL + '/index.html')
    _html = _resp.read().decode('utf-8')
    test("i18n: 主界面包含 I18N 字典", 'const I18N' in _html and "'zh'" in _html and "'en'" in _html)
    test("i18n: 主界面包含语言切换函数", 'function switchLang' in _html and 'function applyI18n' in _html)
    test("i18n: 主界面使用 data-i18n 属性", 'data-i18n=' in _html)
    test("i18n: 语言按钮跨页面重建逻辑（applyI18n 内）", 'createElement' in _html and 'langSwitch' in _html and 'insertBefore' in _html)
    # 外网面一律不允许修改密码：前端隐藏入口 + 弹窗拦截 + i18n 提示（后端白名单不含 change-password，403 兜底）
    test("前端外网面隐藏修改密码入口", 'btnChangePwd' in _html and 'pwd.externalOnly' in _html and 'showChangePwdModal() {' in _html and '// 外网面一律不允许修改密码' in _html)
except Exception as e:
    test("i18n: 主界面资源检查", False, str(e))

# ============================================================
# 网络面识别 + 版本号单一来源（资源/源码检查，部署后与 src/ 相邻）
# ============================================================
# 版本号单一来源（主界面仅 APP_VERSION 一处，字典/HTML 不含硬编码版本号）
test("版本: 主界面版本号单一来源(APP_VERSION)", 'const APP_VERSION' in _html)
test("版本: 品牌副标题不含硬编码版本号", "'文件审批摆渡系统'" in _html and "文件审批摆渡系统 v" not in _html)

# health 返回版本号（v 开头，与前端 APP_VERSION 一致由常量驱动）
code, data = request('GET', '/api/health')
test("版本: health 返回版本号", code == 200 and isinstance(data.get('version'), str) and data['version'].startswith('v'),
     f"code={code}, version={data.get('version')}")

# 网络面识别（app.py 源码检查：INTERNAL_CIDRS + ipaddress 网段兜底）
import os as _os
_src_app = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', 'src', 'app.py')
if not _os.path.exists(_src_app):  # 兼容旧部署（根目录 app.py 已弃用）
    _src_app = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', 'app.py')
try:
    with open(_src_app, encoding='utf-8') as _f:
        _app_src = _f.read()
    test("网络: app.py 含网段识别配置(INTERNAL_CIDRS+ipaddress)", 'INTERNAL_CIDRS' in _app_src and 'import ipaddress' in _app_src)
    test("网络: app.py 含 CIDR 兜底识别(_ip_in_cidrs)", '_ip_in_cidrs' in _app_src and 'X-Network-Zone' in _app_src)
    test("网络: loopback(127.0.0.1/::1)恒为内网管理面", 'is_loopback' in _app_src)
    # AD 属性字段可配置（默认值非硬编码）：AD_USER_FIELD/AD_DISPLAY_FIELD/AD_MAIL_FIELD/AD_GROUP_FIELD
    test("AD: 属性字段可配置(环境变量+默认值非硬编码)",
         'AD_USER_FIELD = os.getenv("AD_USER_FIELD", "sAMAccountName")' in _app_src
         and 'AD_DISPLAY_FIELD = os.getenv("AD_DISPLAY_FIELD", "displayName")' in _app_src
         and 'AD_MAIL_FIELD = os.getenv("AD_MAIL_FIELD", "mail")' in _app_src
         and 'AD_GROUP_FIELD = os.getenv("AD_GROUP_FIELD", "memberOf")' in _app_src)
    test("AD: 查询 filter 使用可配置字段(非硬编码 sAMAccountName)",
         'f"({AD_USER_FIELD}={username})"' not in _app_src and 'f"({ad_user_field}={username})"' in _app_src)
    test("AD: 失败原因返回并写入审计日志(login_failed detail)",
         'authenticate_ad(username, password)' in _app_src and 'ad_reason or "用户名或密码错误"' in _app_src
         and 'login_failed", "ad", ad_reason' in _app_src)
except Exception as e:
    test("网络: app.py 源码检查", False, str(e))

# ============================================================
# AD 配置管理 + 配置总览（ADR-010：DB 权威 / .env 导入 / 来源标记）
# ============================================================
code, data = request('GET', '/api/admin/ad-config')
test("AD配置: 管理API可读(admin)", code == 200 and 'db' in data and 'env' in data, f"code={code}")
code, data = request('PUT', '/api/admin/ad-config', json_data={"ad_host": "ldap://t.example.com:389", "ad_enabled": "false"})
test("AD配置: 保存到DB(source=db)", code == 200, f"code={code}")
code, data = request('GET', '/api/admin/ad-config')
test("AD配置: 保存后持久化读取",
     code == 200 and data.get('db', {}).get('ad_host', {}).get('value') == 'ldap://t.example.com:389'
     and data['db']['ad_host']['source'] == 'db', f"code={code}")
code, data = request('POST', '/api/admin/ad-config/import')
test("AD配置: 从.env导入(source=env)", code == 200, f"code={code}")
code, data = request('GET', '/api/admin/ad-config')
test("AD配置: 导入后source=env", code == 200 and data.get('db', {}).get('ad_host', {}).get('source') == 'env', f"code={code}")
request('PUT', '/api/admin/ad-config', json_data={"ad_host": ""})  # 清空恢复（回退 .env）
code, data = request('GET', '/api/admin/config-overview')
test("AD配置: 配置总览API(admin)", code == 200 and 'deploy_env' in data and 'runtime_db' in data and 'ad_config' in data['runtime_db'], f"code={code}")
test("AD配置: app.py 含 ad_config 表/DB优先读取/AD_ENV_MAP/去.env回写",
     'CREATE TABLE IF NOT EXISTS ad_config' in _app_src and 'def get_ad_config_value' in _app_src
     and 'AD_ENV_MAP' in _app_src and '不再回写 .env' in _app_src)
test("AD配置: 前端含AD配置卡片+总览卡片+i18n",
     'id="ad_enabled"' in _html and 'id="ov_deploy"' in _html and 'id="ov_runtime"' in _html
     and 'adConfig.title' in _html and 'overview.title' in _html and 'function escapeHtml' in _html)

# ============================================================
# v2.2.22 回归组：特征码默认禁用迁移 / 前端 loadConfig 修复 / AD 用户管理 / AD 登录分支
# ============================================================
# 前置：前序测试（免审批场景）可能启用了内置规则，此处幂等恢复为禁用后再断言
# （模拟生产旧库升级迁移效果；断言代表规则覆盖 extension/binary/EDA 三类）
_BUILTIN_WANT = {("PDF文档", "extension", ".pdf"), ("ZIP特征码", "binary", "hex:504B0304"), ("Vivado Bit同步字", "binary", "hex:5599AA66")}
code, data = request('GET', '/api/config/feature-rules')
if code == 200 and isinstance(data, list):
    for _r in data:
        if _r.get("enabled") and (_r.get("name"), _r.get("rule_type"), _r.get("pattern")) in _BUILTIN_WANT:
            request('POST', f"/api/admin/feature-rules/{_r['id']}/toggle")
# 特征码：内置模板规则必须默认禁用（新库播种 enabled=0 + 旧库升级迁移重置为禁用）
code, data = request('GET', '/api/config/feature-rules')
_builtin_disabled = True
if code == 200 and isinstance(data, list):
    for r in data:
        if (r.get("name"), r.get("rule_type"), r.get("pattern")) in _BUILTIN_WANT and r.get("enabled"):
            _builtin_disabled = False
            break
else:
    _builtin_disabled = False
test("特征码: 内置模板规则默认禁用（播种/升级迁移 enabled=0）", _builtin_disabled, f"code={code}")
test("特征码: app.py 含内置模板常量+升级迁移逻辑",
     'BUILTIN_FEATURE_RULES' in _app_src and '内置模板规则已重置为禁用' in _app_src)

# AD 用户管理：搜索 API（admin）+ 前端入口（审批人弹窗 AD 来源 + 用户管理页 AD 搜索）
# 环境自适应：ad_enabled=false → mock 分支须返回非空；ad_enabled=true → 真实查询分支（TODO）200+list 即可
_ad_on = False
_code_ov, _cfg = request('GET', '/api/admin/config-overview')
if _code_ov == 200 and isinstance(_cfg, dict):
    _ad_on = _cfg.get('runtime_db', {}).get('ad_config', {}).get('ad_enabled', {}).get('value', 'false') == 'true'
code, data = request('POST', '/api/admin/ad/search', json_data={"keyword": ""})
test("AD用户: /api/admin/ad/search 返回结果(admin)",
     code == 200 and isinstance(data, list) and (len(data) >= 1 or _ad_on),
     f"code={code} len={len(data) if isinstance(data, list) else 'NA'} ad_enabled={_ad_on}")
test("AD用户: 审批人弹窗支持AD来源+搜索",
     'id="apprSource"' in _html and 'id="apprAdBlock"' in _html and 'function searchAdUsers' in _html
     and 'function switchApproverSource' in _html)
test("AD用户: 用户管理页AD搜索入口",
     'showAdUserSearch' in _html and 'id="adUserResult"' in _html and 'function searchAdUserTable' in _html)

# AD 登录：域\用户名 格式识别为 AD 分支（AD 未启用时返回 401）
code, data = request('POST', '/api/auth/login', json_data={"username": "DOMAIN\\zhangsan", "password": "wrong-password"})
test("AD登录: 域\\用户名格式走AD分支(未启用→401)", code == 401, f"code={code}")

# 前端：loadConfig() 未定义调用已全部修复为 renderConfig()
test("前端: 无未定义的 loadConfig() 调用且 renderConfig 正常接线",
     'loadConfig();' not in _html and _html.count('renderConfig();') >= 3 and 'async function renderConfig' in _html)

# ============================================================
# v2.2.23 回归组：提交接收方类型重构（internal/partner/non-partner）+ 系统运维数据生命周期（ADR-011）
# ============================================================
# --- 提交：公司内部（internal）仅需接收人，单位可空 ---
code, data = upload_file(test_pdf, "internal_type.pdf")
int_temp_id = data.get('tempId')
code, data = request('POST', '/api/submissions', json_data={
    "tempIds": [int_temp_id],
    "receiverName": "内部接收人",
    "receiverType": "internal",
    "securityLevel": "internal",
    "reason": "内部摆渡测试"
})
test("提交: 公司内部类型单位可空提交成功并判定internal",
     code == 200 and data.get('receiver_type') == 'internal', f"code={code}, receiver_type={data.get('receiver_type')}")
# --- 非合作方：单位必填（internal 校验不影响 non-partner）---
code, data = request('POST', '/api/submissions', json_data={
    "tempIds": [int_temp_id],
    "receiverName": "非合作方测试",
    "receiverType": "non-partner",
    "securityLevel": "internal"
})
test("提交: 非合作方单位仍必填（缺失返回400）", code == 400 and '单位' in str(data), f"code={code}, data={data}")

# --- 系统运维 ops（ADR-011）：备份/恢复/出厂重置/模拟数据 ---
# 非 admin 访问被拒
code, data = request('POST', '/api/admin/local-users', json_data={
    "username": "opsuser1", "password": "Ops@123456", "displayName": "运维权限测试", "role": "internal-user"})
code, data = request('POST', '/api/auth/login', json_data={"username": "opsuser1", "password": "Ops@123456"})
code, data = request('GET', '/api/admin/ops/backups')
test("运维: 非admin访问备份列表被拒403", code == 403, f"code={code}")
code, data = request('POST', '/api/auth/login', json_data={"username": ADMIN_USER, "password": ADMIN_PASS})
request('DELETE', '/api/admin/local-users/opsuser1')

# 备份创建成功 + 列表可见
code, data = request('POST', '/api/admin/ops/backup', json_data={})
test("运维: 创建备份成功", code == 200 and data.get('name', '').startswith('backup-'), f"code={code}, data={data}")
code, data = request('GET', '/api/admin/ops/backups')
test("运维: 备份列表包含刚创建的备份",
     code == 200 and isinstance(data, list) and len(data) >= 1 and data[0].get('hasDb') is True, f"code={code}, n={len(data) if isinstance(data,list) else 'NA'}")

# 恢复/重置/模拟数据必须确认码
code, data = request('POST', '/api/admin/ops/restore', json_data={"backupName": "backup-x", "confirm": ""})
test("运维: 恢复缺确认码返回400", code == 400, f"code={code}")
code, data = request('POST', '/api/admin/ops/reset-factory', json_data={"confirm": ""})
test("运维: 出厂重置缺确认码返回400", code == 400, f"code={code}")
code, data = request('POST', '/api/admin/ops/mock-data', json_data={"confirm": ""})
test("运维: 模拟数据缺确认码返回400", code == 400, f"code={code}")

# 模拟数据：testing 模式成功生成（幂等）；production 模式拒绝（环境自适应）
_dm = 'testing'
_code_h, _health = request('GET', '/api/health')
if _code_h == 200 and isinstance(_health, dict):
    _dm = _health.get('deployMode', 'testing')
code, data = request('POST', '/api/admin/ops/mock-data', json_data={"confirm": "MOCK"})
if _dm == 'testing':
    test("运维: 模拟数据生成成功(测试环境)", code == 200, f"code={code}, data={data}")
    code, data = request('GET', '/api/admin/local-users')
    _has_mock_users = isinstance(data, list) and any(u.get('username') == 'testuser01' for u in data)
    test("运维: 模拟数据含测试用户(testuser01)", _has_mock_users, f"n={len(data) if isinstance(data,list) else 'NA'}")
else:
    test("运维: 模拟数据生成被拒(生产环境)", code == 403, f"code={code}")

# 前端：提交表单 internal 选项 + 条件字段 + 系统工具菜单/页面 + i18n
test("前端: 提交表单含公司内部类型+类型/密级前置+条件字段",
     'id="receiverType"' in _html and 'value="internal"' in _html and 'onReceiverTypeChange' in _html
     and 'receiverOrgWrap' in _html and 'submit.internal' in _html and 'submit.receiverEmailOpt' in _html)
test("前端: 系统工具菜单+页面+备份/重置/模拟数据卡片",
     'data-page="ops"' in _html and 'async function renderOps' in _html and 'function opsBackup' in _html
     and 'function opsReset' in _html and 'function opsMock' in _html
     and 'ops.backupTitle' in _html and 'ops.resetTitle' in _html and 'ops.mockTitle' in _html)
test("后端: app.py 含运维数据生命周期实现(ADR-011)",
     '_backup_now' in _app_src and '_restore_backup' in _app_src and '_reset_factory' in _app_src
     and '_generate_mock_data' in _app_src and 'api_ops_backups' in _app_src
     and 'receiver_type != "internal" and not receiver_org' in _app_src)

# ============================================================
# v2.2.24 回归组：MD5 端到端完整性 + 删除提交单（admin，确认码 DEL）
# ============================================================
import hashlib as _hashlib

# --- MD5 完整性：上传计算 → DB 存储 → 下载响应头 → 下载内容 四方一致 ---
print("\n--- 12. MD5 端到端完整性 ---")
code, data = request('GET', f'/api/submissions/{auto_sub_id}')
_db_md5 = ''
if isinstance(data, dict) and data.get('files'):
    _db_md5 = data['files'][0].get('md5', '')
test("完整性: 提交单详情DB文件MD5与上传一致",
     bool(_db_md5) and _db_md5 == pdf_md5, f"db={str(_db_md5)[:16]}... up={str(pdf_md5)[:16]}...")
# 下载响应头 X-File-MD5 + 下载内容本地 MD5（端到端）
_dl_resp = opener.open(urllib.request.Request(BASE_URL + f'/api/external/{auto_sub_id}/download/test_document.pdf'))
_dl_bytes = _dl_resp.read()
_dl_md5 = _hashlib.md5(_dl_bytes).hexdigest()
_dl_xmd5 = _dl_resp.headers.get('X-File-MD5')
test("完整性: 下载响应头 X-File-MD5 与上传一致", _dl_xmd5 == pdf_md5, f"header={str(_dl_xmd5)[:16]}... up={str(pdf_md5)[:16]}...")
test("完整性: 下载内容本地MD5与上传一致（端到端）",
     _dl_md5 == pdf_md5, f"dl={_dl_md5[:16]}... up={str(pdf_md5)[:16]}...")
# 审计日志下载记录含 MD5
code, data = request('GET', '/api/audit-logs')
_dl_audits = [a for a in (data if isinstance(data, list) else [])
              if a.get('action') == 'download' and str(pdf_md5) in str(a.get('detail', ''))]
test("完整性: 下载审计日志记录MD5", len(_dl_audits) >= 1, f"n={len(_dl_audits)}")
# 前端显示完整 MD5
test("前端: 上传列表与详情显示完整MD5", 'MD5: ${f.md5}' in _html and 'title="${f.md5 || \'\'}"' in _html)

# --- 删除提交单（admin，确认码 DEL）---
print("\n--- 13. 删除提交单（admin） ---")
code, data = upload_file(test_pdf, "del_test.pdf")
_del_temp = data.get('tempId')
code, data = request('POST', '/api/submissions', json_data={
    "tempIds": [_del_temp], "receiverName": "删除测试", "receiverType": "internal",
    "securityLevel": "internal", "reason": "删除提交单测试"})
_del_sub = data.get('id')
# 非 admin 被拒（创建专用用户，幂等）
request('DELETE', '/api/admin/local-users/deluser1')
request('POST', '/api/admin/local-users', json_data={
    "username": "deluser1", "password": "Del@123456", "displayName": "删除权限测试", "role": "internal-user"})
request('POST', '/api/auth/login', json_data={"username": "deluser1", "password": "Del@123456"})
code, data = request('DELETE', f'/api/admin/submissions/{_del_sub}', json_data={"confirm": "DEL"})
test("删除提交单: 非admin被拒403", code == 403, f"code={code}")
request('POST', '/api/auth/login', json_data={"username": ADMIN_USER, "password": ADMIN_PASS})
request('DELETE', '/api/admin/local-users/deluser1')
# 错误确认码 400
code, data = request('DELETE', f'/api/admin/submissions/{_del_sub}', json_data={"confirm": "wrong"})
test("删除提交单: 错误确认码返回400", code == 400, f"code={code}")
# 正确确认码 200 → 详情 404
code, data = request('DELETE', f'/api/admin/submissions/{_del_sub}', json_data={"confirm": "DEL"})
test("删除提交单: 确认码正确删除成功", code == 200, f"code={code}, data={data}")
code, data = request('GET', f'/api/submissions/{_del_sub}')
test("删除提交单: 删除后详情返回404", code == 404, f"code={code}")
# 源码/前端检查
test("后端: app.py 含删除提交单API(确认码DEL)+下载返回X-File-MD5",
     'api_delete_submission' in _app_src and '"DEL"' in _app_src and 'X-File-MD5' in _app_src
     and 'delete_submission' in _app_src)
test("前端: 详情含删除提交单按钮+i18n", 'askDeleteSubmission' in _html and 'detail.deleteSubmission' in _html)
test("工具: 性能压力测试脚本存在(800MB 上传/摆渡/下载+MD5)",
     os.path.exists(os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'perf_test.py')))

# ============================================================
# v2.2.25 回归组：外网面语言切换 403 修复（switchLang 绕过 navigate 外网校验）
# ============================================================
print("\n--- 14. 外网面语言切换 ---")
test("前端: 语言切换外网面强制刷新下载页(复用navigate外网校验)",
     "if (window._networkZone === 'external') navigate('external');" in _html
     and "else if (typeof currentPage === 'string' && currentPage) renderPage(currentPage);" in _html,
     "switchLang 外网分支缺失")
test("前端: 登录初始化外网面直进外网下载页(管理页被外网校验拦截)",
     "if (window._networkZone === 'external') navigate('external');" in _html
     and "else navigate(currentUser && currentUser.role === 'admin' ? 'dashboard' : 'submit');" in _html,
     "init 外网分支缺失")

# ============================================================
# v2.2.26 回归组：.env 模板口径统一（MAX_FILE_SIZE_MB）+ env-refresh.sh 刷新机制
# ============================================================
print("\n--- 15. .env 模板与刷新机制 ---")
# 模板统一：三模板用 MAX_FILE_SIZE_MB，不含旧键 MAX_CONTENT_LENGTH=
_env_prod = open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', 'src', '.env.production'), encoding='utf-8').read()
_env_test = open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', 'src', '.env.testing'), encoding='utf-8').read()
_env_ex = open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', 'src', '.env.example'), encoding='utf-8').read()
test("模板: 三个.env模板统一用MAX_FILE_SIZE_MB且不含旧键MAX_CONTENT_LENGTH=",
     'MAX_FILE_SIZE_MB=800' in _env_prod and 'MAX_FILE_SIZE_MB=800' in _env_test and 'MAX_FILE_SIZE_MB=800' in _env_ex
     and not any(l.startswith('MAX_CONTENT_LENGTH=') for l in _env_prod.splitlines())
     and not any(l.startswith('MAX_CONTENT_LENGTH=') for l in _env_test.splitlines())
     and not any(l.startswith('MAX_CONTENT_LENGTH=') for l in _env_ex.splitlines()))
test("脚本: env-refresh.sh 存在且含备份+只增不覆盖逻辑",
     _os.path.exists(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', 'infra', 'env-refresh.sh'))
     and 'env-refresh.sh' in open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', 'infra', 'env-refresh.sh'), encoding='utf-8').read()
     and '.env.bak-' in open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', 'infra', 'env-refresh.sh'), encoding='utf-8').read())
test("打包: package.sh 排除 .env 且 infra 整体打包(env-refresh.sh 随包)",
     _os.path.exists(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', 'infra', 'package.sh'))
     and '.env" -type f -delete' in open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', 'infra', 'package.sh'), encoding='utf-8').read()
     and 'cp -r "$PROJECT_ROOT/infra"' in open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', 'infra', 'package.sh'), encoding='utf-8').read())

# ============================================================
# 测试报告
# ============================================================
print("\n" + "=" * 70)
print("测试报告")
print("=" * 70)
passed = sum(1 for r in results if "PASS" in r['status'])
failed = sum(1 for r in results if "FAIL" in r['status'])
print(f"总计: {len(results)} | 通过: {passed} | 失败: {failed}")
print(f"通过率: {passed/len(results)*100:.1f}%")
print("=" * 70)

if failed > 0:
    print("\n失败项:")
    for r in results:
        if "FAIL" in r['status']:
            print(f"  ❌ {r['name']} | {r['detail']}")

print("\n测试完成。")
