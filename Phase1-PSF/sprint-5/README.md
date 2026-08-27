# Sprint 5 — 特征码增强 + 压缩包格式扩展 + AD LDAP 认证

> Sprint：PSF-Sprint-5 | 阶段：PSF（问题-方案匹配验证）
> 核心交付：特征码引擎增强（hex二进制匹配）、Linux默认压缩包格式全支持、Vivado Bitstream识别、AD LDAP直连认证（兼容sssd）

---

## 一、本 Sprint 变更

### 1. 特征码引擎增强

**原实现**：binary 类型只读前16字节，仅支持文本子串匹配。

**新实现**：
- 读取前 **4096 字节**（覆盖 tar 的 ustar offset 257 等非头部特征码）
- 支持 **hex: 前缀**的十六进制特征码，如 `hex:1F8B`、`hex:504B0304`
- 兼容原有文本子串匹配（如 `ustar`）

### 2. 特征码规则从 5 条扩展到 20 条

| 类别 | 规则名 | 类型 | 匹配模式 |
|------|--------|------|---------|
| 文档 | PDF文档 | extension | .pdf |
| 文档 | Word文档 | extension | .doc,.docx |
| 文档 | Excel表格 | extension | .xls,.xlsx |
| 文档 | PPT演示 | extension | .ppt,.pptx |
| 文档 | 图片文件 | extension | .png,.jpg,.jpeg,.gif,.bmp,.svg |
| 文档 | 文本文件 | extension | .txt,.csv,.md,.log,.json,.xml,.yaml,.yml |
| 压缩包 | ZIP压缩包 | extension | .zip |
| 压缩包 | TAR归档 | extension | .tar |
| 压缩包 | GZIP压缩 | extension | .gz,.tgz |
| 压缩包 | BZIP2压缩 | extension | .bz2,.tbz2 |
| 压缩包 | XZ压缩 | extension | .xz,.txz |
| 压缩包 | ZSTD压缩 | extension | .zst |
| 压缩包 | ZIP特征码 | binary | hex:504B0304 |
| 压缩包 | GZIP特征码 | binary | hex:1F8B |
| 压缩包 | BZIP2特征码 | binary | hex:425A68 |
| 压缩包 | XZ特征码 | binary | hex:FD377A585A00 |
| 压缩包 | ZSTD特征码 | binary | hex:28B52FFD |
| 压缩包 | TAR特征码(ustar) | binary | ustar |
| FPGA | Vivado Bitstream(.bit) | extension | .bit |
| FPGA | Vivado Bit同步字 | binary | hex:5599AA66 |

### 3. 压缩包自动解包列清单扩展

**原实现**：仅支持 .zip。

**新实现**：支持 Linux 默认压缩格式：
- `.zip` — zipfile 模块
- `.tar` / `.tar.gz` / `.tgz` / `.tar.bz2` / `.tbz2` / `.tar.xz` / `.txz` / `.tar.zst` — tarfile 模块（`r:*` 自动识别压缩格式）
- `.gz` / `.bz2` / `.xz` / `.zst` — 单文件压缩，不列内部清单

### 4. AD LDAP 直连认证（替换 stub）

**原实现**：`authenticate_ad()` 是 stub，直接返回 None。

**新实现**：用 `ldap3` 库实现直接 LDAP 绑定认证。

**与 sssd 的兼容性**：
- **完全兼容，互不干扰**。sssd 是系统级认证守护进程，用 LDAP 连 AD；我们的程序也用 LDAP 连 AD，走相同协议和端口（389/636）。
- 两种模式可并行：系统登录走 sssd，应用登录走 SecureTrans 自己的 LDAP 绑定。

**认证方式**：用户直接绑定（UPN 格式 `username@AD_DOMAIN`），不需要服务账户 bind DN。

**新增配置项**（.env）：
```
AD_ENABLED=true
AD_HOST=ldap://dc01.company.com:389    # 支持 ldap:// / ldaps://
AD_DOMAIN=company.com                     # 用于构造 UPN
AD_BASE_DN=DC=company,DC=com             # 用户搜索基准
```

**认证流程**：
1. 本地用户认证失败后，自动尝试 AD 认证
2. 用 `username@AD_DOMAIN` + 密码直接 LDAP 绑定
3. 绑定成功后查询用户 displayName、mail、memberOf
4. 通过 role_mappings 表映射 AD 用户/组到应用角色

---

## 二、Vivado Bitstream 特征码说明

Xilinx Vivado 生成的 `.bit` 文件格式：
- 文件开头：`0x00 0x09`（2字节长度），后跟设计信息头（含 "xlnx"）
- Bitstream 数据同步字：原始 `0xAA995566`，在 .bit 文件中存储为 **bit-swapped** `0x5599AA66`
- 本实现用 `hex:5599AA66` 在文件前 4KB 中搜索同步字，可靠识别 .bit 文件

`.bin` 格式（原始 bitstream）：同步字通常为 `0xAA995566`（不 bit-swap），但 .bin 扩展名太通用，未加入免审批扩展名规则，仅靠 binary 特征码匹配。

---

## 三、Linux 默认压缩格式说明

Rocky Linux 8.10 最小安装默认支持：

| 格式 | 工具 | 特征码(Magic) |
|------|------|---------------|
| tar | tar | offset 257: "ustar" |
| gzip | gzip | 1F 8B |
| bzip2 | bzip2 | 42 5A 68 ("BZh") |
| xz | xz | FD 37 7A 58 5A 00 |
| zip | zip/unzip | 50 4B 03 04 ("PK..") |
| zstd | zstd（需 dnf install zstd） | 28 B5 2F FD |

7z/rar 默认不支持（需额外安装 p7zip/unrar），本 sprint 未加入。

---

## 四、测试结果

**总计 35 项测试，全部通过，通过率 100%。**

测试环境：Windows + Python 3.13 + Flask 3.0 + SQLite + ldap3 2.9.1

覆盖 13 大类，与 sprint-3 相同测试集全通过，新增功能（特征码引擎、压缩包解包、AD认证）向后兼容。

---

## 五、文件清单

```
backend-flask/
├── app.py              # 主程序（v1.5.0，特征码增强+AD认证）
├── requirements.txt    # 依赖（新增 ldap3==2.9.1）
├── test_api.py         # 35项全量测试
├── .env.example        # 环境变量示例（新增 AD_DOMAIN）
├── start.sh / start.bat
├── README.md
└── static/
    ├── index.html
    └── login.html
```

---

*Sprint 5 交付文档 | 2026-08-27*
