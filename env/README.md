# SecureTrans 环境配置（12-Factor · ADR-016）

单一仓库、一套代码，环境差异只体现在 `env/` 配置与数据目录。

## 三环境矩阵

| 文件 | 环境 | 用途 | 数据目录 | AD |
|---|---|---|---|---|
| `env/dev.env` | 开发（Windows 本地） | AI 开发 + TDD 全量回归 | `./data`（相对） | `AD_MOCK_MODE=true`（模拟） |
| `env/test.env` | 测试（WSL rocky10-st） | verify.sh 全量回归 + CI runner | `/opt/securetrans/data` | `AD_MOCK_MODE=true`（模拟） |
| `env/prod.env.template` | 生产（Rocky 8.10） | deploy.sh 据此生成 `.env` | `/mnt/nas/securetrans` | `AD_MOCK_MODE=false`（真实 AD） |

## 使用方式

- **开发/测试**：把对应模板复制为运行目录的 `.env`（Windows: `src/.env`；WSL: `/opt/securetrans/.env`）。
  示例：`cp env/dev.env src/.env`（Windows）、`cp env/test.env /opt/securetrans/.env`（WSL）。
- **生产**：发布包自带 `env/prod.env.template`，`deploy.sh` 首次部署时自动复制生成 `.env` + 随机 SECRET_KEY；
  已有 `.env` 时自动保留（deploybak 保护，不覆盖）。

## 纪律（ADR-016）

1. **生产 `.env` / 生产数据 / 密钥永不入 git**——只提交模板，真实值人工填。
2. `AD_MOCK_MODE=true` 时 AD 搜索/登录走内置模拟目录（`src/app.py` 的 `MOCK_AD_USERS`），
   与生产典型 AD 数据（脱敏）一致，不触网；生产必须 `false`。
3. 版本阶段 `APP_STAGE`：alpha → **beta** → rtm → release（页面显示 `vX.Y.Z-stage`）。
4. 修改模板后，需同步 `src/.env`（本地实际运行）与文档（README/AGENTS/DEPLOY 三处）。
