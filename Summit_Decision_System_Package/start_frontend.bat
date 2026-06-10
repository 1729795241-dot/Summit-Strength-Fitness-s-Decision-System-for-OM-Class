@echo off
setlocal
cd /d "%~dp0"
set PYTHONDONTWRITEBYTECODE=1

where python >nul 2>nul
if %errorlevel%==0 (
  python app.py
  goto :end
)

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 app.py
  goto :end
)

echo Python was not found. Please install Python 3 or run app.py with the bundled Codex Python runtime.
pause

:end
endlocal
