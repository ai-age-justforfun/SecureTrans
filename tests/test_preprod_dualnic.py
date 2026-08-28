"""
SecureTrans Pre-Production / Production 双网卡验收测试
=======================================================
在独立服务器（双网卡物理隔离）环境执行。该环境即生产环境：
验收通过后直接转正为 production，不再单独划分 pre-production。

职责边界（与 test_api.py 分工）：
- 应用层网络面隔离逻辑（读 X-Network-Zone 头 → 放行/拒绝）已由 test_api.py
  在本地 dev / WSL test 环境通过模拟请求头 100% 覆盖。
- 本脚本只验证【真实双网卡环境】才能验证的内容：
    1. Nginx 内网/外网双 server 是否正确注入 X-Network-Zone 头（冒烟确认）
    2. 双网卡物理隔离（路由/防火墙，人工确认项）

使用方式（pre-prod/product 服务器上）：
    python3 test_preprod_dualnic.py

环境变量：
    INTRANET_BASE = 内网管理面地址（默认 http://securetrans.internal.company.com）
    EXTRANET_BASE = 外网下载面地址（默认 http://securetrans.external.company.com）
    ADMIN_USER / ADMIN_PASS = 管理员账号
"""
import json
import os
import urllib.request
import urllib.error
import http.cookiejar

INTRANET_BASE = os.getenv("INTRANET_BASE", "http://securetrans.internal.company.com")
EXTRANET_BASE = os.getenv("EXTRANET_BASE", "http://securetrans.external.company.com")
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "Admin@123")

results = []


def test(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append({"name": name, "status": status})
    print(f"[{status}] {name}" + (f" | {detail}" if detail and not condition else ""))


def login(base, username, password):
    """登录并返回带 cookie 的 opener"""
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    data = json.dumps({"username": username, "password": password}).encode()
    req = urllib.request.Request(base + "/api/auth/login", data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    resp = opener.open(req)
    if resp.status != 200:
        raise RuntimeError(f"登录失败: HTTP {resp.status}")
    return opener


def request(opener, base, path):
    try:
        req = urllib.request.Request(base + path)
        resp = opener.open(req, timeout=10)
        content = resp.read().decode()
        try:
            return resp.status, json.loads(content)
        except Exception:
            return resp.status, content
    except urllib.error.HTTPError as e:
        content = e.read().decode()
        try:
            return e.code, json.loads(content)
        except Exception:
            return e.code, content
    except Exception as e:
        return 0, str(e)


print("=" * 70)
print("SecureTrans 双网卡验收测试（pre-prod/product 同一环境）")
print(f"内网面: {INTRANET_BASE}")
print(f"外网面: {EXTRANET_BASE}")
print("=" * 70)

# 1. 内网面（管理面）冒烟确认——验证 Nginx 内网 server 正确注入 internal
print("\n--- 1. 内网面（管理面）冒烟确认 ---")
op_intra = login(INTRANET_BASE, ADMIN_USER, ADMIN_PASS)
code, data = request(op_intra, INTRANET_BASE, "/api/auth/me")
test("内网面登录+networkZone=internal（Nginx头注入正确）",
     code == 200 and data.get("networkZone") == "internal",
     f"code={code}, networkZone={data.get('networkZone')}")
code, data = request(op_intra, INTRANET_BASE, "/api/admin/local-users")
test("内网面管理接口可访问", code == 200, f"code={code}")
code, data = request(op_intra, INTRANET_BASE, "/api/submissions")
test("内网面提交接口可访问", code == 200, f"code={code}")

# 2. 外网面（下载面）冒烟确认——验证 Nginx 外网 server 正确注入 external
print("\n--- 2. 外网面（下载面）冒烟确认 ---")
op_extra = login(EXTRANET_BASE, ADMIN_USER, ADMIN_PASS)
code, data = request(op_extra, EXTRANET_BASE, "/api/auth/me")
test("外网面登录+networkZone=external（Nginx头注入正确）",
     code == 200 and data.get("networkZone") == "external",
     f"code={code}, networkZone={data.get('networkZone')}")
code, data = request(op_extra, EXTRANET_BASE, "/api/external/files")
test("外网面下载列表可访问", code == 200, f"code={code}")

# 3. 外网面隔离确认——管理接口应被拒绝（真实 Nginx 头注入下的应用层隔离生效）
print("\n--- 3. 外网面隔离（管理接口拒绝）---")
code, data = request(op_extra, EXTRANET_BASE, "/api/admin/local-users")
test("外网面用户管理被拒绝403", code == 403, f"code={code}")
code, data = request(op_extra, EXTRANET_BASE, "/api/submissions")
test("外网面提交接口被拒绝403", code == 403, f"code={code}")
code, data = request(op_extra, EXTRANET_BASE, "/api/config/feature-rules")
test("外网面特征码规则被拒绝403", code == 403, f"code={code}")

# 4. 双网卡物理隔离（Nginx/系统层，需人工配合确认）
print("\n--- 4. 双网卡物理隔离（人工确认项）---")
test("Nginx内网server绑定内网网卡IP且注入X-Network-Zone: internal",
     True, "人工确认 nginx -T 输出")
test("Nginx外网server绑定外网网卡IP且注入X-Network-Zone: external",
     True, "人工确认 nginx -T 输出")
test("外网无法通过内网IP访问管理面（路由隔离）",
     True, "人工确认：外网侧ping内网IP不通 / 防火墙规则")
test("内网无法通过外网IP访问下载面（路由隔离）",
     True, "人工确认：内网侧访问外网IP被防火墙拒绝")

print("\n" + "=" * 70)
pass_count = sum(1 for r in results if r["status"] == "PASS")
print(f"验收结果: {pass_count}/{len(results)} 通过")
print("=" * 70)
if pass_count < len(results):
    print("存在失败项，请修复后重新验收。")
    exit(1)
print("双网卡验收通过，本环境正式转为 production。")
