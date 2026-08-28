# SecureTrans 双网卡验收指南（pre-prod = product）

> 版本：v1.1 | 日期：2026-08-28 | 阶段：PSF → production
> 说明：**pre-production 不再与 production 分两个环境**。独立服务器部署、双网卡验收通过后即正式转为 production。
> 应用层网络面隔离逻辑（读 `X-Network-Zone` 头 → 放行/拒绝）已由 `test_api.py` 在本地 test 环境通过**模拟请求头 100% 覆盖**；
> 本环境只验证**真实双网卡才可验证的内容**（Nginx 头注入 + 物理隔离）。

---

## 一、环境策略（v1.1 更新）

| 环境 | 网卡 | 用途 | 网络面测试方式 |
|------|------|------|--------------|
| 本地 dev | 单网卡（Windows） | 开发 | `test_api.py` 模拟 `X-Network-Zone` 头，覆盖应用层全部逻辑 |
| 本地 test | 单网卡（WSL Rocky） | 功能/自动化回归 | `test_api.py` 模拟 `X-Network-Zone` 头，覆盖应用层全部逻辑 |
| **pre-prod/product（同一环境）** | **双网卡（独立服务器）** | **先验收，通过即转正为 production** | `test_preprod_dualnic.py` 真实头注入确认 + 物理层人工验收 |

**关键认知**：应用层隔离 = 读取 `X-Network-Zone` 请求头，**与物理网卡无关**。只要请求头正确，行为完全一致。
因此"内外网无法测试的测试项"**可以在 test 环境全部模拟**（test_api.py 22d 节：external 面放行矩阵 + 拒绝矩阵 + 非法值回退）。
真实双网卡只影响 **Nginx 层如何注入该头**（内网 server 注入 internal、外网 server 注入 external），这是 test 环境无法验证的，必须在 pre-prod/product 环境做。

---

## 二、部署架构

```
                    ┌──────────────────────────────────────┐
                    │   pre-prod/product 服务器（双网卡）      │
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
2. **应用层**：`before_request` 钩子按 `X-Network-Zone` 头强制隔离（即使绕过 Nginx 也拦得住）——**test 环境已 100% 覆盖**
3. **前端层**：外网面灰掉非下载菜单，防误操作

---

## 三、验收前置条件

- [ ] 独立服务器已分配内网/外网两个网卡 IP
- [ ] Python 3.10+ / Nginx / gunicorn / systemd 已安装
- [ ] `infra/deploy.sh` 一键部署成功（生产模式 DEPLOY_MODE=production）
- [ ] Nginx 双 server 块已配置（`infra/nginx-securetrans.conf`）
- [ ] 内网地址 `http://securetrans.internal.company.com` 可访问
- [ ] 外网地址 `http://securetrans.external.company.com` 可访问
- [ ] 本地已跑通 `test_api.py` 全量（含 22d 网络面扩展矩阵），应用层无缺陷

---

## 四、验收步骤

### 4.1 自动化冒烟（真实双网卡头注入确认）

在 pre-prod/product 服务器上执行：

```bash
cd /opt/securetrans/tests

# 配置环境变量（如域名不同）
export INTRANET_BASE="http://securetrans.internal.company.com"
export EXTRANET_BASE="http://securetrans.external.company.com"
export ADMIN_USER="admin"
export ADMIN_PASS="Admin@123"

# 执行双网卡验收（冒烟 + 人工项）
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

## 五、验收通过标准（转正条件）

- [ ] 本地 `test_api.py` 全量通过（120 项，含 22d 网络面扩展矩阵）
- [ ] `test_preprod_dualnic.py` 全部 PASS（真实头注入 + 人工项）
- [ ] 外网面所有管理接口返回 403
- [ ] 外网面下载接口正常
- [ ] 内网面完整功能正常
- [ ] Nginx/防火墙人工验收项全部通过

**验收通过后，本环境即正式转为 production**（更新域名/HTTPS 证书即可，不再单独划分环境）。

---

*文档结束 | SecureTrans 双网卡验收指南 v1.1 | 2026-08-28*
