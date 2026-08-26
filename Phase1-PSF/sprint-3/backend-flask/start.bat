@echo off
chcp 65001 >nul
echo ========================================
echo   SecureTrans 启动脚本 (Windows)
echo   Flask + Flask-Login + SQLite
echo ========================================

cd /d "%~dp0"

REM 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)

REM 检查虚拟环境
if not exist "venv" (
    echo [信息] 首次启动，创建虚拟环境...
    python -m venv venv
    call venv\Scripts\activate.bat
    echo [信息] 安装依赖...
    pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
) else (
    call venv\Scripts\activate.bat
)

REM 加载环境变量
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
        if not "%%a"=="" if not "%%a:~0,1%"=="#" set "%%a=%%b"
    )
)

echo [信息] 存储目录: %NAS_ROOT%
echo [信息] 数据库: %SECURETRANS_DATA%\securetrans.db
echo [信息] 启动 SecureTrans 服务...
echo [信息] 访问地址: http://localhost:%PORT%
echo [信息] 初始管理员: admin / Admin@123
echo [信息] 按 Ctrl+C 停止服务
echo.

python app.py

pause
