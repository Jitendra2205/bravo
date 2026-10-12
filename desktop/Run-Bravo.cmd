@echo off
rem Bravo Desktop: double-click to start. First run installs what it needs (a few minutes).
cd /d "%~dp0"
where py 1>NUL 2>NUL
if errorlevel 1 (
  echo Installing Python from the official winget package...
  winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
  echo.
  echo Python installed. Double-click Run-Bravo.cmd once more to continue.
  pause
  exit /b 0
)
if not exist .venv\Scripts\python.exe (
  echo Creating a private Python environment for Bravo...
  py -3 -m venv .venv || (echo Could not create the environment. & pause & exit /b 1)
)
rem A venv created without pip (seen on some Windows Python installs) gets pip added here.
.venv\Scripts\python.exe -m pip --version 1>NUL 2>NUL || .venv\Scripts\python.exe -m ensurepip --upgrade 1>NUL 2>NUL
.venv\Scripts\python.exe -m pip --version 1>NUL 2>NUL || (
  echo Adding pip from the official PyPA bootstrap...
  powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing https://bootstrap.pypa.io/get-pip.py -OutFile $env:TEMP\get-pip.py" || (echo Could not download pip. Check your internet connection. & pause & exit /b 1)
  .venv\Scripts\python.exe "%TEMP%\get-pip.py" --no-warn-script-location || (echo Could not install pip. & pause & exit /b 1)
)
echo Checking Bravo components (first run downloads about 300 MB)...
.venv\Scripts\python.exe -m pip install --disable-pip-version-check -q -r requirements.txt || (echo Install failed. Check your internet connection and try again. & pause & exit /b 1)
echo Starting Bravo...
start "" .venv\Scripts\pythonw.exe app.py
