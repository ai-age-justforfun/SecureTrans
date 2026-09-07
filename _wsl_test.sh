#!/bin/bash
# WSL production 模式 172 全量测试
cd /opt/securetrans/tests
NAS_ROOT=/mnt/nas/securetrans python3 test_api.py 2>&1 | tail -6
