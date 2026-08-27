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

BASE_URL = "http://localhost:8000"
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
code, data = request('POST', '/api/auth/login', json_data={"username": "admin", "password": "Admin@123"})
test("admin 登录成功", code == 200 and data.get('user', {}).get('role') == 'admin', f"code={code}, data={data}")

# 4. 获取当前用户
code, data = request('GET', '/api/auth/me')
test("获取当前用户信息", code == 200 and data.get('username') == 'admin', f"code={code}, data={data}")

# 5. 错误密码登录
code, data = request('POST', '/api/auth/login', json_data={"username": "admin", "password": "wrongpass"})
test("错误密码登录被拒绝", code == 401, f"code={code}")
# 重新登录
request('POST', '/api/auth/login', json_data={"username": "admin", "password": "Admin@123"})

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
    "receiverType": "partner",
    "securityLevel": "internal",
    "reason": "项目合作文档外发",
    "expiryDays": 30
})
test("创建提交单（免审批自动通过）", code == 200 and data.get('autoApproved') == True and data.get('status') == 'approved',
     f"code={code}, status={data.get('status')}, autoApproved={data.get('autoApproved')}")
auto_sub_id = data.get('id')

# 8. 创建提交单 - 需要审批场景（EXE 不匹配）
code, data = request('POST', '/api/submissions', json_data={
    "tempIds": [exe_temp_id],
    "receiverName": "李四（非合作方）",
    "receiverEmail": "lisi@external.com",
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

# 12. 一级审批通过
code, data = request('POST', f'/api/submissions/{pending_sub_id}/approve', json_data={
    "action": "approve",
    "comment": "一级审批通过，进入二级审批"
})
test("一级审批通过（非合作方进入二级审批）", code == 200 and data.get('status') == 'pending_approval_2',
     f"code={code}, status={data.get('status')}")

# 13. 二级审批通过
code, data = request('POST', f'/api/submissions/{pending_sub_id}/approve', json_data={
    "action": "approve",
    "comment": "二级审批通过，同意外发"
})
test("二级审批通过（os.rename 摆渡到 external）", code == 200 and data.get('status') == 'approved',
     f"code={code}, status={data.get('status')}")

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
test("本地用户列表", code == 200 and any(u['username'] == 'admin' for u in data), f"code={code}, count={len(data) if isinstance(data,list) else 'N/A'}")

code, data = request('POST', '/api/admin/local-users', json_data={
    "username": "testuser01",
    "password": "Test@123456",
    "displayName": "测试用户01",
    "email": "test01@company.com",
    "role": "internal-user"
})
test("创建本地用户", code == 200, f"code={code}, data={data}")

code, data = request('POST', '/api/admin/local-users/testuser01/reset-password')
test("重置本地用户密码", code == 200, f"code={code}, data={data}")

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
    "role": "dept-manager",
    "note": "研发部一级审批人"
})
test("创建 AD 用户角色映射", code == 200, f"code={code}, data={data}")

code, data = request('POST', '/api/admin/ad/search', data={"keyword": "zhang"})
test("搜索 AD 用户（打桩模拟）", code == 200 and isinstance(data, list), f"code={code}, count={len(data) if isinstance(data,list) else 'N/A'}")

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

# 20. 手动触发过期清理
code, data = request('POST', '/api/admin/cleanup-expired')
test("手动触发过期清理（无过期文件）", code == 200 and 'cleaned' in data, f"code={code}, data={data}")

# 21. 验证 os.rename 物理文件移动
print("\n--- 12. 物理文件验证（os.rename 0拷贝） ---")
import pathlib
# NAS_ROOT 可通过环境变量覆盖；默认指向 src/nas（测试脚本在 tests/，服务在 src/）
nas_root = pathlib.Path(os.getenv("NAS_ROOT", str(pathlib.Path(__file__).parent.parent / "src" / "nas")))
staging_dir = nas_root / "staging"
external_dir = nas_root / "external"
archive_dir = nas_root / "archive"

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
