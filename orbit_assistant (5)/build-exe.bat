@echo off
setlocal
cd /d "%~dp0"
python -m pip install --user -r requirements.txt pyinstaller
if errorlevel 1 (pause & exit /b 1)
python build_windows.py
if errorlevel 1 (pause & exit /b 1)
echo Build finished. See dist\
pause
