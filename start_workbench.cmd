@echo off
rem 本地机会工作台 — Windows 一键启动（双击即可；不依赖 DSH/MCP；仅本机 127.0.0.1）
setlocal
cd /d "%~dp0"

set "PYTHONUTF8=1"
set "PYTHONDONTWRITEBYTECODE=1"

if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
  echo [提示] 未找到 .venv\Scripts\python.exe，改用系统 python。需要 Flask。
)

echo 正在启动本地机会工作台...
"%PY%" "tools\workbench\run.py" %*

set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo [退出码 %RC%] 启动失败。常见原因：端口被占用 —— 换端口： start_workbench.cmd --port 5016
  pause
)
endlocal
