@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -3.12 -m venv .venv
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto fail
echo 安装完成。双击 run.bat 启动。
pause
exit /b 0
:fail
echo 安装失败。请检查 Python 3.12 和网络，日志显示在上方。
pause
exit /b 1
