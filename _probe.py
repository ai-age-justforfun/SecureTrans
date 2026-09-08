# -*- coding: utf-8 -*-
import io, re

s = io.open("src/app.py", encoding="utf-8", newline="").read()
lines = s.split("\n")

def show(a, b, label):
    print(f"===== {label} (L{a}-{b}) =====")
    for i in range(a - 1, min(b, len(lines))):
        print(f"{i+1}: {lines[i]}")
    print()

# 创建用户
for i, l in enumerate(lines, 1):
    if 'methods=["POST"]' in l and "local-users" in l:
        show(i, i + 48, "创建用户 POST /api/admin/local-users")
        break

# 系统配置 GET/PUT
for i, l in enumerate(lines, 1):
    if '"/api/config/system"' in l:
        show(i, i + 75, "系统配置 GET/PUT")
        break

# 特征码规则
for i, l in enumerate(lines, 1):
    if '"/api/config/feature-rules"' in l and "methods" not in l:
        show(i, i + 55, "特征码规则 GET")
        break
