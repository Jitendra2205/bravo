@echo off
rem Double-click to run the Windows setup. Keeps the window open so you can read the result.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows-setup.ps1"
echo.
pause
