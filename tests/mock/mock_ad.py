#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SecureTrans AD 模拟目录校验器（ADR-016）
解析 src/app.py 的 MOCK_AD_USERS / MOCK_AD_PASSWORD，与 tests/mock/mock_expected.json 期望基线对比，
防止实现与期望漂移。用法：python tests/mock/mock_ad.py
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
APP = os.path.join(ROOT, 'src', 'app.py')
EXPECT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mock_expected.json')


def extract_app_mock():
    src = open(APP, encoding='utf-8').read()
    m = re.search(r'MOCK_AD_USERS = (\[.*?\n\])\nMOCK_AD_PASSWORD = "([^"]+)"', src, re.S)
    if not m:
        sys.exit('FAIL: 未在 src/app.py 找到 MOCK_AD_USERS / MOCK_AD_PASSWORD')
    users = json.loads(re.sub(r',\s*\n\s*\]', '\n]', m.group(1)))
    pwd = m.group(2)
    return users, pwd


def main():
    app_users, app_pwd = extract_app_mock()
    exp = json.load(open(EXPECT, encoding='utf-8'))
    ok = True
    if app_pwd != exp['MOCK_AD_PASSWORD']:
        ok = False
        print('FAIL: 密码不一致 app=%s expect=%s' % (app_pwd, exp['MOCK_AD_PASSWORD']))
    if len(app_users) != len(exp['users']):
        ok = False
        print('FAIL: 用户数不一致 app=%d expect=%d' % (len(app_users), len(exp['users'])))
    for i, u in enumerate(exp['users']):
        if i >= len(app_users) or app_users[i] != u:
            ok = False
            print('FAIL: 第%d条用户不一致\n  app=%s\n  exp=%s' % (i, app_users[i] if i < len(app_users) else None, u))
    if ok:
        print('PASS: AD 模拟目录与期望基线一致（%d 用户, 密码 %s）' % (len(app_users), app_pwd))
        return 0
    return 1


if __name__ == '__main__':
    sys.exit(main())
