@echo off
setlocal

set "PYTHON_EXE=C:\Users\cesar\.pyenv\pyenv-win\versions\3.10.5\python.exe"

if not exist "%PYTHON_EXE%" (
    echo Python no encontrado en:
    echo   %PYTHON_EXE%
    exit /b 1
)

cd /d "%~dp0"
"%PYTHON_EXE%" gui_app.py
