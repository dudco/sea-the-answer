@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" %*
set "HAEDAP_EXIT=%ERRORLEVEL%"
if not "%HAEDAP_EXIT%"=="0" if /I not "%HAEDAP_NO_PAUSE%"=="1" pause
exit /b %HAEDAP_EXIT%
