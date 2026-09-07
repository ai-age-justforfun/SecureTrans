#!/bin/bash
echo "=== gunicorn-error.log ==="
tail -30 /opt/securetrans/data/gunicorn-error.log 2>/dev/null
echo ""
echo "=== journalctl 最近 ==="
journalctl -u securetrans -n 15 --no-pager 2>/dev/null | tail -15
echo ""
echo "=== /opt/securetrans/venv/bin/gunicorn 前3行（是否 Windows 格式）==="
head -3 /opt/securetrans/venv/bin/gunicorn 2>/dev/null
echo ""
echo "=== venv python 软链 ==="
ls -la /opt/securetrans/venv/bin/python* 2>/dev/null | head -5
/opt/securetrans/venv/bin/python --version 2>&1
echo ""
echo "=== Windows 工作区 src 内容 ==="
ls /mnt/c/Users/jinta/.doubao/lark-chats/2026-08-25/new-chat/src/ | head -20
