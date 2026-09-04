# ============================================================
# SecureTrans 一键部署脚本 (Windows) — v2.2.0
# 适用：Windows 10/11 / Windows Server 2019+，Python 3.10+
# 用法：powershell -ExecutionPolicy Bypass -File infra/deploy.ps1 [-InstallDir C:\SecureTrans] [-Start]
# 一键完成：Python 3.10+ 自动获取 → venv → 依赖(离线/在线) → .env → (可选)启动
#
# Python 获取优先级：
#   1. 系统已有 python 3.10+ → 直接使用
#   2. 部署包根目录 offline-python-win/python-*.exe（官方安装器）→ 静默安装
#   3. 提示下载 URL（https://www.python.org/downloads/）
# 离线依赖：部署包内置 offline-deps-win/（win_amd64 wheel），自动离线优先
# 网络：在线安装需放行 python.org / pypi.org（或内网 PyPI 镜像）
# ============================================================
param(
    [string]$InstallDir = "C:\SecureTrans",
    [switch]$Start
)
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projRoot = Split-Path -Parent $scriptDir
$srcDir = Join-Path $projRoot "src"
# 离线 wheel：发布包根目录 offline-deps-win/wheelhouse；开发仓库 fallback packages/offline-deps-win/wheelhouse
$offlineDir = Join-Path $projRoot "offline-deps-win\wheelhouse"
if (-not (Test-Path $offlineDir)) { $offlineDir = Join-Path $projRoot "packages\offline-deps-win\wheelhouse" }
$offlinePyDir = Join-Path $projRoot "offline-python-win"

Write-Host "============================================================"
Write-Host "  SecureTrans Windows 一键部署"
Write-Host "  安装目录: $InstallDir"
Write-Host "============================================================"

# 0. Python 3.10+ 自动获取
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    # 尝试内置离线安装器（offline-python-win/python-*.exe）
    $installer = Get-ChildItem $offlinePyDir -Filter "python-*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($installer) {
        Write-Host "[0/5] [离线] 静默安装内置 Python 安装器: $($installer.Name) ..."
        Start-Process -FilePath $installer.FullName -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_pip=1 Include_tcltk=1" -Wait -NoNewWindow
        # 刷新 PATH（Machine + User）
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
        Start-Sleep -Seconds 3
        $py = Get-Command python -ErrorAction SilentlyContinue
    }
}
if (-not $py) {
    Write-Host "[错误] 未找到 python。请二选一："
    Write-Host "   A) 下载 Python 3.10+ 安装器并安装（勾选 Add python.exe to PATH）:"
    Write-Host "      https://www.python.org/downloads/"
    Write-Host "   B) 下载 python-3.12.x-amd64.exe 放入 offline-python-win/ 目录后重跑本脚本（离线自动安装）"
    exit 1
}
$pyVer = (& python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
if ([int]($pyVer.Split('.')[0]) -lt 3 -or ([int]($pyVer.Split('.')[0]) -eq 3 -and [int]($pyVer.Split('.')[1]) -lt 10)) {
    Write-Host "[错误] Python 版本过低 ($pyVer)，需要 3.10+"
    exit 1
}
Write-Host "[0/5] Python: $pyVer OK"
# 版本匹配强化：离线 wheel 按 cp312 打包，若当前 Python 非 3.12 且存在离线 3.12 安装器，
# 优先静默安装 3.12（保证与离线依赖一致），而不是降级用非 3.12
$is312cur = (& python -c "import sys; print(1 if sys.version_info[:2]==(3,12) else 0)").Trim()
if ($is312cur -eq "0" -and (Test-Path $offlinePyDir)) {
    $installer312 = Get-ChildItem $offlinePyDir -Filter "python-3.12*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($installer312) {
        Write-Host "[0/5] 当前 Python 为 $pyVer，检测到离线 Python 3.12 安装器 $($installer312.Name)，切换安装 3.12 以匹配离线 wheel (cp312)..."
        Start-Process -FilePath $installer312.FullName -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_pip=1 Include_tcltk=1" -Wait -NoNewWindow
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
        Start-Sleep -Seconds 3
        $pyVer = (& python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
        Write-Host "[0/5] Python 已切换: $pyVer"
    }
}
# 离线 wheel 按 cp312 打包，Python 需 3.12；非 3.12 且走离线时预警
if (Test-Path $offlineDir) {
    $is312 = (& python -c "import sys; print(1 if sys.version_info[:2]==(3,12) else 0)").Trim()
    if ($is312 -eq "0") {
        Write-Host "      [警告] 离线 wheel 按 Python 3.12 (cp312) 打包，当前 Python 为 $pyVer，离线安装可能失败"
        Write-Host "      建议安装 Python 3.12（python-3.12.x-amd64.exe 放入 offline-python-win/ 后重跑自动静默安装）"
    }
}

# 1. 复制源码
if (-not (Test-Path $srcDir)) {
    Write-Host "[错误] 未找到源码目录 $srcDir，请在项目根目录运行本脚本"
    exit 1
}
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item (Join-Path $srcDir "*") $InstallDir -Recurse -Force
Write-Host "[1/5] 程序文件已复制 -> $InstallDir"

# 2. 创建虚拟环境 + 安装依赖（离线优先）
if (-not (Test-Path (Join-Path $InstallDir "venv\Scripts\python.exe"))) {
    Write-Host "[2/5] 创建虚拟环境（--copies 与系统完全隔离）..."
    & python -m venv --copies (Join-Path $InstallDir "venv")
}
$pip = Join-Path $InstallDir "venv\Scripts\pip.exe"
if (Test-Path $offlineDir) {
    Write-Host "[2/5] [离线] 使用本地离线依赖安装（$offlineDir）..."
    & $pip install --no-index --find-links=$offlineDir -r (Join-Path $InstallDir "requirements.txt")
} else {
    Write-Host "[2/5] [在线] 从网络安装依赖..."
    & $pip install -r (Join-Path $InstallDir "requirements.txt")
}
if ($LASTEXITCODE -ne 0) { Write-Host "[错误] 依赖安装失败"; exit 1 }
Write-Host "      依赖安装完成"
# 校验 venv 内 Python 版本（离线 wheel 按 cp312 打包，须为 3.12）
$venvPy = Join-Path $InstallDir "venv\Scripts\python.exe"
if (Test-Path $venvPy) {
    $vver = (& $venvPy -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
    if ($vver -ne "3.12") { Write-Host "      [警告] venv Python 为 $vver，与离线 wheel (cp312) 不一致；如离线安装失败请删除 venv 并用 Python 3.12 重建" }
    else { Write-Host "      venv Python: $vver（匹配 cp312） OK" }
}

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
    Write-Host "[3/5] .env 已创建（SECRET_KEY 已随机生成），请检查 NAS_ROOT / INTERNAL_CIDRS"
} else {
    Write-Host "[3/5] .env 已存在，保留原有配置"
}

# 4. 启动（可选）
if ($Start) {
    Write-Host "[4/5] 启动服务（Flask 内置服务器）..."
    Start-Process -FilePath (Join-Path $InstallDir "venv\Scripts\python.exe") -ArgumentList "app.py" -WorkingDirectory $InstallDir
    Start-Sleep -Seconds 5
    try {
        $health = (Invoke-WebRequest -Uri "http://localhost:8000/api/health" -UseBasicParsing -TimeoutSec 5).Content
        Write-Host "      健康检查: $health"
    } catch {
        Write-Host "      [警告] 健康检查未通过，请检查服务日志"
    }
} else {
    Write-Host "[4/5] 跳过启动（-Start 可自动启动）"
}

# 5. 验证说明
Write-Host "[5/5] 验证指引："
Write-Host "  1) 访问 http://localhost:8000，admin / Admin@123 登录（首次强制改密）"
Write-Host "  2) 运行全量测试（另一终端）: cd tests; python test_api.py  (172项)"
Write-Host "  3) 生产 waitress: cd $InstallDir; .\venv\Scripts\waitress-serve.exe --host=0.0.0.0 --port=8000 app:app"
Write-Host "  4) 服务化(开机自启): nssm install SecureTrans 指向 venv\Scripts\python.exe + app.py，或用计划任务"

Write-Host ""
Write-Host "============================================================"
Write-Host "  部署完成！"
Write-Host "  安装目录: $InstallDir"
Write-Host "  单网卡隔离: INTERNAL_CIDRS 内网段=全功能；非内网段=仅登录+下载（管理接口403）"
Write-Host "============================================================"
