@echo off
rem Awaaz Desktop: double-click to start. First run installs what it needs (a few minutes).
cd /d "%~dp0"
where py 1>NUL 2>NUL
if errorlevel 1 (
  echo Installing Python from the official winget package...
  winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
  echo.
  echo Python installed. Double-click Run-Awaaz.cmd once more to continue.
  pause
  exit /b 0
)
if not exist .venv\Scripts\python.exe (
  echo Creating a private Python environment for Awaaz...
  py -3 -m venv .venv || (echo Could not create the environment. & pause & exit /b 1)
)
echo Checking Awaaz components...
.venv\Scripts\python.exe -m pip install --disable-pip-version-check -q -r requirements.txt || (echo Install failed. Check your internet connection and try again. & pause & exit /b 1)
start "" .venv\Scripts\pythonw.exe app.py
