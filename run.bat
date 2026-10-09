@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe -m app.main gui %*
) else (
  py -3.12 -m app.main gui %*
)
if errorlevel 1 pause
