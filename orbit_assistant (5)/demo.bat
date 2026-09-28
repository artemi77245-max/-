@echo off
setlocal
cd /d "%~dp0"
call "%~dp0select-python.bat"
if errorlevel 1 (pause & exit /b 1)
"%ORBIT_PY%" -m orbit.worker --demo
pause
