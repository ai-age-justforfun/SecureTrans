# SecureTrans 模拟数据（Mock）目录 · ADR-016

## 用途

开发（Windows）/ 测试（WSL）环境全量自动化回归所需的外部与业务模拟数据，
随仓库入 git，可重复生成、可断言，**与生产典型标准数据一致（脱敏）**。

## 组成

| 文件 | 内容 |
|---|---|
| `mock_ad.py` | AD 模拟目录校验器：解析 `src/app.py` 的 `MOCK_AD_USERS`，与 `mock_expected.json` 对比防漂移 |
| `mock_expected.json` | AD 模拟目录期望基线（与生产典型 AD 用户脱敏一致） |
| `README.md` | 本说明 |

## 模拟策略（12-Factor 三环境一体化）

1. **AD 模拟**：`AD_MOCK_MODE=true`（env/dev.env、env/test.env）时，
   `authenticate_ad` / `api_search_ad` 走 `src/app.py` 内置 `MOCK_AD_USERS`（不触网），
   返回结构与真实 LDAP 路径完全一致（user dict / error 字符串）；
   生产 `AD_MOCK_MODE=false` 直连真实 AD（SSSD/LDAP 同源兼容）。
2. **业务数据**：由 `tests/test_api.py` 通过真实 API 全链路生成（用户/审批人/提交/文件/审批/备份/日志），
   每次 `--reset-factory` 后可重建；断言基线见测试组。
3. **一致性**：`mock_expected.json` 与生产典型 AD 数据（脱敏）字段对齐：
   `username / displayName / email / department`，密码统一 `MOCK_AD_PASSWORD`（app.py 定义）。

## 校验

```bash
python tests/mock/mock_ad.py    # 输出 PASS/FAIL（app.py 与期望基线一致）
```

防漂移纪律：修改 app.py 的 MOCK_AD_USERS 时必须同步 mock_expected.json，否则校验失败。
