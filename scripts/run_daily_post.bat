@echo off
REM Entry point invoked by Windows Task Scheduler. Comments in this file are
REM ASCII-only on purpose (cmd.exe can mis-parse non-ASCII comments under
REM some codepages).
setlocal
set "REPO_ROOT=%~dp0.."
cd /d "%REPO_ROOT%"
if not exist logs mkdir logs
forfiles /p "%REPO_ROOT%\logs" /m "daily_post_console_*.log" /d -30 /c "cmd /c del @path" 2>nul
for /f %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd"') do set TODAY=%%d
call "%REPO_ROOT%\.venv\Scripts\activate.bat"
python -m scripts.generate_daily_post >> "%REPO_ROOT%\logs\daily_post_console_%TODAY%.log" 2>&1
endlocal
