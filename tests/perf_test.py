#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SecureTrans 性能压力测试：大文件 上传→摆渡→下载 全链路 + MD5 端到端完整性

模拟生产场景（800MB 默认）：
  1. 流式生成测试文件并计算 MD5（不占用大量内存）
  2. 上传（计时：总耗时 / 上传速率 MB/s）
  3. 审批通过（计时：审批+os.rename 0拷贝摆渡，期望毫秒级）
  4. 轮询确认摆渡完成（external 可见）
  5. 下载（计时：总耗时 / 下载速率 MB/s），校验响应头 X-File-MD5
  6. 本地计算下载内容 MD5 与原始 MD5 比对（端到端完整性）
  7. 输出报告 + 阈值断言 + 清理（删除提交单/临时文件）

用法:
  python tests/perf_test.py                        # 默认 http://127.0.0.1:8000
  python tests/perf_test.py http://10.10.30.8:8000  # 指定服务器

环境变量:
  PERF_SIZE_MB        文件大小（MB），默认 800
  PERF_ADMIN_USER     admin 用户名（默认 admin）
  PERF_ADMIN_PASS     admin 密码（默认 Admin@123；生产用 VERIFY_ADMIN_PASS 同源）
  PERF_MAX_UPLOAD_S   上传最长允许秒数（默认 600）
  PERF_MAX_DOWNLOAD_S 下载最长允许秒数（默认 600）
  PERF_MAX_TOTAL_S    全链路最长允许秒数（默认 900）
  PERF_KEEP=1         保留数据不清理（默认自动清理）
  PERF_CONCURRENCY    多用户并发用户数（默认 0=关闭；3-5 模拟 beta 多用户并发）
  PERF_CONC_SIZE_MB   每个并发用户的文件大小 MB（默认 10，避免测试数据过大）
  PERF_CONC_MAX_S     并发全链路最长允许秒数（默认 120）

依赖：仅 Python 标准库（urllib / http.client / hashlib / threading）。
"""
import hashlib
import http.client
import json
import os
import random
import shutil
import sys
import tempfile
import threading
import time
import urllib.request
import uuid

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
SIZE_MB = int(os.getenv("PERF_SIZE_MB", "800"))
ADMIN_USER = os.getenv("PERF_ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("PERF_ADMIN_PASS", os.getenv("VERIFY_ADMIN_PASS", "Admin@123"))
MAX_UPLOAD_S = int(os.getenv("PERF_MAX_UPLOAD_S", "600"))
MAX_DOWNLOAD_S = int(os.getenv("PERF_MAX_DOWNLOAD_S", "600"))
MAX_TOTAL_S = int(os.getenv("PERF_MAX_TOTAL_S", "900"))
KEEP = os.getenv("PERF_KEEP", "0") == "1"
CONCURRENCY = int(os.getenv("PERF_CONCURRENCY", "0"))
CONC_SIZE_MB = int(os.getenv("PERF_CONC_SIZE_MB", "10"))
CONC_MAX_S = int(os.getenv("PERF_CONC_MAX_S", "120"))

# ---- HTTP 工具（复用 cookie 会话）----
def _parse_base(url):
    u = url.replace("http://", "").replace("https://", "")
    if ":" in u:
        host, port = u.split(":", 1)
        return host, int(port)
    return u, 80

HOST, PORT = _parse_base(BASE_URL)
cookie_jar = {}

def api(method, path, json_data=None, headers=None, timeout=120, ck=None):
    """JSON API（urllib，带 cookie）；ck 为独立会话 cookie dict（并发测试用）"""
    jar = ck if ck is not None else cookie_jar
    req_headers = dict(headers or {})
    body = None
    if json_data is not None:
        body = json.dumps(json_data).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    req_headers.update(jar)
    req = urllib.request.Request(BASE_URL + path, data=body, headers=req_headers, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        content = resp.read().decode("utf-8")
        data = json.loads(content) if content else {}
        return resp.status, data
    except urllib.error.HTTPError as e:
        content = e.read().decode("utf-8")
        try:
            return e.code, json.loads(content)
        except Exception:
            return e.code, {"error": content[:200]}

def login():
    cookie_jar["Cookie"] = _grab_cookie()
    print(f"[OK] 登录成功: {ADMIN_USER}")

# ---- 多用户并发（v2.5.1，story：3-5 用户并发，保证当前正常性能）----
def _concurrent_worker(uid, size_mb, results):
    """单个并发用户：独立会话完成 生成→上传→提交→审批→下载→MD5 校验"""
    try:
        ck = {"Cookie": _grab_cookie()}
        tmp_dir = tempfile.mkdtemp(prefix=f"securetrans_conc_{uid}_")
        filepath = os.path.join(tmp_dir, f"conc_{uid}_{int(time.time())}.bin")
        total_bytes = size_mb * 1024 * 1024
        seed = random.randbytes(512)
        md5_orig = hashlib.md5()
        with open(filepath, "wb") as f:
            chunk = (seed * (4096 // len(seed) + 1))[:4096]
            written = 0
            while written < total_bytes:
                w = min(len(chunk), total_bytes - written)
                f.write(chunk[:w])
                md5_orig.update(chunk[:w])
                written += w
        t0 = time.time()
        code, data = stream_upload(filepath, os.path.basename(filepath), ck=ck)
        if code != 200:
            raise RuntimeError(f"upload {code}: {data}")
        temp_id = data.get("tempId")
        code, data = api("POST", "/api/submissions", json_data={
            "tempIds": [temp_id], "receiverName": f"并发用户{uid}",
            "receiverEmail": f"conc{uid}@test.local", "receiverOrg": f"并发测试合作方-{uid}",
            "receiverType": "partner", "securityLevel": "internal", "reason": "并发性能测试",
        }, ck=ck)
        if code != 200:
            raise RuntimeError(f"submit {code}: {data}")
        sub_id = data.get("id")
        code, data = api("POST", f"/api/submissions/{sub_id}/approve",
                         json_data={"action": "approve", "comment": "并发性能通过"}, ck=ck)
        if code != 200 or data.get("status") != "approved":
            raise RuntimeError(f"approve {code}: {data}")
        dl_path = os.path.join(tmp_dir, "dl.bin")
        with open(dl_path, "wb") as f:
            dl_s, md5_dl, x_md5, _ = stream_download(
                f"/api/external/{sub_id}/download/{os.path.basename(filepath)}", f,
                max_wait=60, ck=ck)
        ok = (md5_orig.hexdigest() == md5_dl == (x_md5 or ""))
        results[uid] = {"ok": ok, "elapsed": time.time() - t0, "size_mb": size_mb,
                        "upload_code": code, "sub_id": sub_id}
        if not KEEP:
            try:
                api("DELETE", f"/api/admin/submissions/{sub_id}", json_data={"confirm": "DEL"}, ck=ck)
            except Exception:
                pass
        shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception as e:
        results[uid] = {"ok": False, "error": str(e)}


def concurrent_test(users, size_mb, max_s):
    """并发主流程：N 用户同时全链路，断言全部成功且不超时"""
    print(f"\n[7/7] 多用户并发测试（{users} 用户 × {size_mb}MB/用户，max {max_s}s）...")
    results, threads = {}, []
    t0 = time.time()
    for i in range(users):
        t = threading.Thread(target=_concurrent_worker, args=(i, size_mb, results))
        threads.append(t)
        t.start()
    for t in threads:
        t.join()
    wall = time.time() - t0
    print(f"    并发全链路总耗时（墙钟）: {wall:.2f}s")
    for i in sorted(results):
        r = results[i]
        if r.get("ok"):
            print(f"    用户{i+1}: OK  耗时 {r['elapsed']:.2f}s（含独立会话+全链路）")
        else:
            print(f"    用户{i+1}: FAIL {r.get('error', 'unknown')}")
    ok_all = all(r.get("ok") for r in results.values()) and len(results) == users
    ok_time = wall <= max_s
    print(f"    并发结果: {'全部成功 ✓' if ok_all else '存在失败 ✗'} | "
          f"耗时{'达标 ✓' if ok_time else f'超阈值 ✗ ({wall:.1f}s > {max_s}s)'}")
    return ok_all and ok_time

def _grab_cookie():
    # 登录响应中的 Set-Cookie（用 http.client 拿原始头）
    conn = http.client.HTTPConnection(HOST, PORT, timeout=30)
    body = json.dumps({"username": ADMIN_USER, "password": ADMIN_PASS}).encode()
    conn.request("POST", "/api/auth/login", body=body,
                 headers={"Content-Type": "application/json"})
    resp = conn.getresponse()
    conn.close()
    if resp.status != 200:
        print(f"[错误] 登录失败 code={resp.status}")
        sys.exit(1)
    for k, v in resp.getheaders():
        if k.lower() == "set-cookie":
            return v.split(";")[0]
    return ""

def stream_upload(filepath, filename, ck=None):
    """流式 multipart 上传（http.client，不把文件读入内存）；ck 为独立会话 cookie"""
    jar = ck if ck is not None else cookie_jar
    boundary = "----SecureTransPerf" + uuid.uuid4().hex
    head = (f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n").encode("utf-8")
    tail = f"\r\n--{boundary}--\r\n".encode("utf-8")
    size = os.path.getsize(filepath)
    content_length = len(head) + size + len(tail)

    conn = http.client.HTTPConnection(HOST, PORT, timeout=MAX_UPLOAD_S + 60)
    conn.putrequest("POST", "/api/submissions/upload")
    conn.putheader("Content-Type", f"multipart/form-data; boundary={boundary}")
    conn.putheader("Content-Length", str(content_length))
    if "Cookie" in jar:
        conn.putheader("Cookie", jar["Cookie"])
    conn.endheaders()
    conn.send(head)
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            conn.send(chunk)
    conn.send(tail)
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8")
    conn.close()
    try:
        return resp.status, json.loads(raw)
    except Exception:
        return resp.status, {"error": raw[:200]}

def stream_download(path, dest_fp, max_wait=600, ck=None):
    """流式下载到文件并计算 MD5，返回 (耗时秒, md5, x_header)；ck 为独立会话 cookie"""
    jar = ck if ck is not None else cookie_jar
    conn = http.client.HTTPConnection(HOST, PORT, timeout=max_wait + 60)
    conn.putrequest("GET", path)
    if "Cookie" in jar:
        conn.putheader("Cookie", jar["Cookie"])
    conn.endheaders()
    resp = conn.getresponse()
    x_md5 = resp.getheader("X-File-MD5")
    h = hashlib.md5()
    t0 = time.time()
    total = 0
    while True:
        chunk = resp.read(1024 * 1024)
        if not chunk:
            break
        h.update(chunk)
        total += len(chunk)
        dest_fp.write(chunk)
    elapsed = time.time() - t0
    conn.close()
    return elapsed, h.hexdigest(), x_md5, total

def main():
    print("=" * 72)
    print(f"SecureTrans 性能压力测试 | 目标 {BASE_URL} | 文件 {SIZE_MB}MB | 模式: 上传→审批→摆渡→下载")
    print("=" * 72)

    login()

    # 1. 生成测试文件（流式写 + 边算 MD5）
    print(f"\n[1/6] 生成 {SIZE_MB}MB 测试文件（流式）...")
    tmp_dir = tempfile.mkdtemp(prefix="securetrans_perf_")
    filepath = os.path.join(tmp_dir, f"perf_test_{int(time.time())}.bin")
    total_bytes = SIZE_MB * 1024 * 1024
    seed = random.randbytes(1024)  # 伪随机种子（确定性内容，MD5 有效）
    t0 = time.time()
    md5_orig = hashlib.md5()
    with open(filepath, "wb") as f:
        chunk = (seed * (8192 // len(seed) + 1))[:8192]
        written = 0
        while written < total_bytes:
            w = min(len(chunk), total_bytes - written)
            f.write(chunk[:w])
            md5_orig.update(chunk[:w])
            written += w
    gen_s = time.time() - t0
    print(f"    生成完成: {SIZE_MB}MB，{gen_s:.1f}s（{SIZE_MB / max(gen_s, 0.01):.0f} MB/s 写盘）")
    print(f"    原始 MD5: {md5_orig.hexdigest()}")

    # 2. 上传（计时）
    print(f"\n[2/6] 上传（流式 multipart）...")
    t0 = time.time()
    code, data = stream_upload(filepath, os.path.basename(filepath))
    up_s = time.time() - t0
    print(f"    上传响应: code={code}")
    if code != 200:
        print(f"    [错误] 上传失败: {data}")
        sys.exit(1)
    temp_id = data.get("tempId")
    print(f"    上传耗时: {up_s:.2f}s | 速率: {SIZE_MB / max(up_s, 0.001):.1f} MB/s")
    print(f"    服务端 MD5: {data.get('md5', '')}")

    # 3. 创建提交单（合作方 → 一级审批即摆渡）
    print(f"\n[3/6] 创建提交单（合作方类型）...")
    code, data = api("POST", "/api/submissions", json_data={
        "tempIds": [temp_id],
        "receiverName": "性能测试接收人",
        "receiverEmail": "perf@test.local",
        "receiverOrg": f"性能测试合作方-{int(time.time())}",
        "receiverType": "partner",
        "securityLevel": "internal",
        "reason": "性能压力测试",
    })
    if code != 200:
        print(f"    [错误] 创建提交单失败: {data}")
        sys.exit(1)
    sub_id = data.get("id")
    print(f"    提交单: {sub_id} status={data.get('status')}")

    # 4. 审批 + 摆渡（计时）
    print(f"\n[4/6] 一级审批（os.rename 0拷贝摆渡）...")
    t0 = time.time()
    code, data = api("POST", f"/api/submissions/{sub_id}/approve",
                     json_data={"action": "approve", "comment": "性能测试通过"})
    appr_s = time.time() - t0
    if code != 200 or data.get("status") != "approved":
        print(f"    [错误] 审批失败: {data}")
        sys.exit(1)
    print(f"    审批+摆渡耗时: {appr_s * 1000:.0f}ms（含 API 往返；os.rename 本身毫秒级）")
    print(f"    状态: {data.get('status')}")

    # 5. 下载（计时 + X-File-MD5 + 本地比对）
    print(f"\n[5/6] 下载（流式）+ 完整性校验...")
    dl_path = os.path.join(tmp_dir, "downloaded.bin")
    t0 = time.time()
    with open(dl_path, "wb") as f:
        dl_s, md5_dl, x_md5, dl_bytes = stream_download(
            f"/api/external/{sub_id}/download/{os.path.basename(filepath)}", f, max_wait=MAX_DOWNLOAD_S)
    print(f"    下载耗时: {dl_s:.2f}s | 速率: {SIZE_MB / max(dl_s, 0.001):.1f} MB/s")
    print(f"    下载字节: {dl_bytes} | 响应头 X-File-MD5: {x_md5}")

    # 详情 MD5（DB 中记录）
    code, detail = api("GET", f"/api/submissions/{sub_id}")
    db_md5 = ""
    files = detail.get("files", []) if isinstance(detail, dict) else []
    if files:
        db_md5 = files[0].get("md5", "")
    print(f"    数据库 MD5: {db_md5}")

    # 完整性比对（四个来源一致）
    ok_md5 = (md5_orig.hexdigest() == md5_dl == (x_md5 or "") == db_md5)
    print(f"    MD5 一致性: 原始={md5_orig.hexdigest()[:16]}... 下载={md5_dl[:16]}... "
          f"头={str(x_md5)[:16]}... DB={db_md5[:16]}... → {'一致 ✓' if ok_md5 else '不一致 ✗'}")

    # 6. 报告 + 断言
    total_s = gen_s + up_s + appr_s + dl_s
    print("\n" + "=" * 72)
    print("性能测试报告")
    print("=" * 72)
    report = {
        "target": BASE_URL,
        "size_mb": SIZE_MB,
        "generate_s": round(gen_s, 2),
        "upload_s": round(up_s, 2),
        "upload_mbps": round(SIZE_MB / max(up_s, 0.001), 1),
        "approve_ms": round(appr_s * 1000, 1),
        "download_s": round(dl_s, 2),
        "download_mbps": round(SIZE_MB / max(dl_s, 0.001), 1),
        "total_s": round(total_s, 2),
        "md5_match": ok_md5,
        "md5": md5_orig.hexdigest(),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

    passed = True
    if not ok_md5:
        print("[失败] MD5 端到端不一致！")
        passed = False
    if up_s > MAX_UPLOAD_S:
        print(f"[失败] 上传耗时 {up_s:.1f}s 超过阈值 {MAX_UPLOAD_S}s")
        passed = False
    if dl_s > MAX_DOWNLOAD_S:
        print(f"[失败] 下载耗时 {dl_s:.1f}s 超过阈值 {MAX_DOWNLOAD_S}s")
        passed = False
    if total_s > MAX_TOTAL_S:
        print(f"[失败] 全链路耗时 {total_s:.1f}s 超过阈值 {MAX_TOTAL_S}s")
        passed = False

    # 多用户并发阶段（v2.5.1）：PERF_CONCURRENCY>1 时执行，纳入总结果
    conc_passed = True
    if CONCURRENCY > 1:
        conc_passed = concurrent_test(CONCURRENCY, CONC_SIZE_MB, CONC_MAX_S)
        if not conc_passed:
            print("[失败] 多用户并发测试未通过")
            passed = False

    print(f"\n结果: {'全部通过 ✓' if passed else '存在失败 ✗'}")

    # 清理
    if KEEP:
        print(f"\n[提示] PERF_KEEP=1：保留数据（提交单 {sub_id}、临时文件 {tmp_dir}）")
    else:
        print("\n[清理] 删除提交单 + 临时文件...")
        code, data = api("DELETE", f"/api/admin/submissions/{sub_id}", json_data={"confirm": "DEL"})
        print(f"    删除提交单: code={code} {data.get('message', data.get('error', ''))}")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        print("    临时文件已清理")

    sys.exit(0 if passed else 2)


if __name__ == "__main__":
    main()
