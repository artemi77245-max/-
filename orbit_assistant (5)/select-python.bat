@echo off
rem Choose an interpreter that really has PyQt6, ignoring partial venvs.
set "ORBIT_PY="
if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" -c "import PyQt6" >nul 2>nul
  if not errorlevel 1 set "ORBIT_PY=%~dp0.venv\Scripts\python.exe"
)
if not defined ORBIT_PY if exist "%LOCALAPPDATA%\OrbitAssistant\venv\Scripts\python.exe" (
  "%LOCALAPPDATA%\OrbitAssistant\venv\Scripts\python.exe" -c "import PyQt6" >nul 2>nul
  if not errorlevel 1 set "ORBIT_PY=%LOCALAPPDATA%\OrbitAssistant\venv\Scripts\python.exe"
)
if not defined ORBIT_PY (
  python -c "import PyQt6" >nul 2>nul
  if not errorlevel 1 set "ORBIT_PY=python"
)
if not defined ORBIT_PY (
  echo Dependencies are missing. Run: python -m pip install --user -r requirements.txt
  exit /b 1
)
exit /b 0
