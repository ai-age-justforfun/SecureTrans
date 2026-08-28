# SecureTrans Pre-Production 双网卡验收指南

> 版本：v1.0 | 日期：2026-08-28 | 阶段：PSF → production 前置
> 说明：本文档验收项**仅在 pre-production（独立服务器、双网卡物理隔离）环境执行**。
> 本地 dev（Windows）和本地 test（WSL）单网卡环境**不执行**本验收。

---

## 一、为什么需要 pre-production

| 环境 | 网卡 | 用途 | 是否执行双网卡验收 |
|------|------|------|------------------|
| 本地 dev | 单网卡（Windows） | 开发 | ❌ 不执行 |
| 本地 test | 单网卡（WSL Rocky） | 功能/自动化测试 | ❌ 不执行 |
| **pre-production** | **双网卡（独立服务器）** | **双网卡隔离验收** | ✅ 执行 |
| production | 双网卡（正式） | 正式运行 | 仅切换配置 |

双网卡隔离是**部署架构层面**的能力（Nginx 绑定内网/外网两个网卡），单网卡环境无法验证物理隔离，必须在独立的 pre-production 服务器上验收。

---

## 二、部署架构

```
                    ┌──────────────────────────────────────┐
                    │   pre-production 服务器（双网卡）        │
                    │                                      │
  内网用户 ──► 内网网卡(NIC1) ──► Nginx internal server      │
                    │       X-Network-Zone: internal        │
                    │              │                        │
                    │              ▼                        │
                    │       Flask (gunicorn :8000)          │
                    │              ▲                        │
  外网用户 ──► 外网网卡(NIC2) ──► Nginx external server      │
                            X-Network-Zone: external       │
                    └──────────────────────────────────────┘
```

- **内网面**（管理面）：提交、审批、用户管理、系统配置、审计
- **外网面**（下载面）：仅文件下载（`/api/external/*`），其余接口应用层拒绝（403）

**三层隔离**：
1. **Nginx 层**：外网 server 仅代理 `/api/external/` 等下载路径，其余返回 403
2. **应用层**：`before_request` 钩子按 `X-Network-Zone` 头强制隔离（即使绕过 Nginx 也拦得住）
3. **前端层**：外网面灰掉非下载菜单，防误操作

---

## 三、验收前置条件

- [ ] 独立服务器已分配内网/外网两个网卡 IP
- [ ] Python 3.10+ / Nginx / gunicorn / systemd 已安装
- [ ] `infra/deploy.sh` 一键部署成功（生产模式 DEPLOY_MODE=production）
- [ ] Nginx 双 server 块已配置（`infra/nginx-securetrans.conf`）
- [ ] 内网地址 `http://securetrans.internal.company.com` 可访问
- [ ] 外网地址 `http://securetrans.external.company.com` 可访问

---

## 四、验收步骤

### 4.1 自动化验收（应用层隔离）

在 pre-production 服务器上执行：

```bash
cd /opt/securetrans/tests

# 配置环境变量（如域名不同）
export INTRANET_BASE="http://securetrans.internal.company.com"
export EXTRANET_BASE="http://securetrans.external.company.com"
export ADMIN_USER="admin"
export ADMIN_PASS="Admin@123"

# 执行双网卡验收
python3 test_preprod_dualnic.py
```

### 4.2 人工验收项（Nginx/系统层）

| # | 验收项 | 方法 |
|---|--------|------|
| 1 | Nginx 内网 server 绑定内网网卡 | `nginx -T \| grep -A5 'server_name securetrans.internal'` |
| 2 | Nginx 外网 server 绑定外网网卡 | `nginx -T \| grep -A5 'server_name securetrans.external'` |
| 3 | 内网 server 注入 `X-Network-Zone: internal` | `nginx -T` 查看 proxy_set_header |
| 4 | 外网 server 注入 `X-Network-Zone: external` | `nginx -T` 查看 proxy_set_header |
| 5 | 外网无法访问内网管理面（路由隔离） | 外网侧 `curl http://<内网IP>/api/admin/` 应失败 |
| 6 | 内网无法访问外网下载面（反向隔离） | 内网侧访问外网IP下载面应被防火墙拒绝 |
| 7 | 防火墙规则 | `firewall-cmd --list-all` 确认两网卡规则 |

---

## 五、验收通过标准

- [ ] `test_preprod_dualnic.py` 全部 PASS
- [ ] 外网面所有管理接口返回 403
- [ ] 外网面下载接口正常
- [ ] 内网面完整功能正常
- [ ] Nginx/防火墙人工验收项全部通过

---

## 六、验收通过后转 production

1. 将 `.env` 中 `DEPLOY_MODE=production` 确认
2. 将 Nginx 域名/IP 切换为正式域名
3. 配置正式 HTTPS 证书（`infra/nginx-securetrans.conf` 注释部分）
4. 更新 `docs/DEPLOY.md` 中生产环境清单
5. 生产环境运行 `infra/verify.sh`（88+项全量回归）

---

*文档结束 | SecureTrans Pre-Production 双网卡验收指南 v1.0 | 2026-08-28*
