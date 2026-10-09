@echo off
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe -m pytest tests -q
) else (
  py -3.12 -m pytest tests -q
)
pause
