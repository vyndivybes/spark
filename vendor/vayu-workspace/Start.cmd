@echo off
cd /d "%~dp0"
python "%~dp0start.py"
if errorlevel 1 pause
