# ============================================================
# SecureTrans 一键部署脚本 (Windows)
# 适用：Windows 10/11 / Windows Server 2019+，Python 3.10+
# 用法：powershell -ExecutionPolicy Bypass -File infra/deploy.ps1 [-InstallDir C:\SecureTrans] [-Start]
# 前置：安装 Python 3.10+（https://www.python.org/downloads/，安装时勾选 Add python.exe to PATH）
# 离线：默认优先使用本地 packages/offline-deps-win 离线包；不存在则在线安装
# 单网卡：Windows 直连(无 Nginx)场景下，.env 的 INTERNAL_CIDRS 按网段识别内外网，
#         外网面仅登录+下载，管理接口 403（应用层隔离，与 Linux 双网卡行为一致）
# ============================================================
param(
    [string]$InstallDir = "C:\SecureTrans",
    [switch]$Start
)
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projRoot = Split-Path -Parent $scriptDir
$srcDir = Join-Path $projRoot "src"
$offlineDir = Join-Path $projRoot "packages\offline-deps-win"

Write-Host "============================================================"
Write-Host "  SecureTrans Windows 部署"
Write-Host "  安装目录: $InstallDir"
Write-Host "============================================================"

# 0. Python 检查
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Host "[错误] 未找到 python。请先安装 Python 3.10+ : https://www.python.org/downloads/"
    Write-Host "       安装时勾选 'Add python.exe to PATH'，然后重新运行本脚本。"
    exit 1
}
$pyVer = (& python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
Write-Host "Python 版本: $pyVer"

# 1. 复制源码
if (-not (Test-Path $srcDir)) {
    Write-Host "[错误] 未找到源码目录 $srcDir，请在项目根目录运行本脚本"
    exit 1
}
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item (Join-Path $srcDir "*") $InstallDir -Recurse -Force
Write-Host "[1/4] 程序文件已复制 -> $InstallDir"

# 2. 创建虚拟环境 + 安装依赖
if (-not (Test-Path (Join-Path $InstallDir "venv\Scripts\python.exe"))) {
    Write-Host "[2/4] 创建虚拟环境..."
    & python -m venv (Join-Path $InstallDir "venv")
}
$pip = Join-Path $InstallDir "venv\Scripts\pip.exe"
if (Test-Path $offlineDir) {
    Write-Host "[2/4] [离线] 使用本地离线依赖安装（$offlineDir）..."
    & $pip install --no-index --find-links=$offlineDir -r (Join-Path $InstallDir "requirements.txt")
} else {
    Write-Host "[2/4] [在线] 从网络安装依赖..."
    & $pip install -r (Join-Path $InstallDir "requirements.txt")
}
if ($LASTEXITCODE -ne 0) { Write-Host "[错误] 依赖安装失败"; exit 1 }
Write-Host "      依赖安装完成"

# 3. 创建 .env（首次）
$envFile = Join-Path $InstallDir ".env"
if (-not (Test-Path $envFile)) {
    $key = (& python -c "import secrets; print(secrets.token_hex(32))").Trim()
    @"
DEPLOY_MODE=testing
NAS_ROOT=$InstallDir\nas
SECRET_KEY=$key
MAX_CONTENT_LENGTH=838860800
HOST=0.0.0.0
PORT=8000
FLASK_DEBUG=false
EXTERNAL_EXPIRY_DAYS=7
NETWORK_MODE=single
INTERNAL_CIDRS=10.0.0.0/8,172.16.0.0/12,192.168.0.0/16
AD_ENABLED=false
AD_HOST=
AD_DOMAIN=
AD_BASE_DN=
AD_BIND_DN=
AD_BIND_PASSWORD=
"@ | Out-File -FilePath $envFile -Encoding utf8
    Write-Host "[3/4] .env 已创建（SECRET_KEY 已随机生成）"
    Write-Host "      请检查/修改 NAS_ROOT 与 INTERNAL_CIDRS"
} else {
    Write-Host "[3/4] .env 已存在，保留原有配置"
}

# 4. 启动（可选）
if ($Start) {
    Write-Host "[4/4] 启动服务（Flask 内置服务器）..."
    Start-Process -FilePath (Join-Path $InstallDir "venv\Scripts\python.exe") -ArgumentList "app.py" -WorkingDirectory $InstallDir
    Write-Host "      服务已启动: http://localhost:8000  (admin / Admin@123)"
} else {
    Write-Host "[4/4] 跳过启动（-Start 可自动启动）"
}

Write-Host ""
Write-Host "============================================================"
Write-Host "  部署完成！"
Write-Host "============================================================"
Write-Host "  安装目录: $InstallDir"
Write-Host "  开发/测试启动 : cd $InstallDir; .\venv\Scripts\python.exe app.py"
Write-Host "  生产 waitress  : .\venv\Scripts\waitress-serve.exe --host=0.0.0.0 --port=8000 app:app"
Write-Host "  验证          : 启动后运行 tests\test_api.py 全量回归"
Write-Host "  单网卡隔离    : 内网段访问=全功能；非内网段=仅登录+下载（管理接口 403）"
Write-Host ""
