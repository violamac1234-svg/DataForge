@echo off
setlocal
title DataForge Launcher
cd /d "%~dp0"

set "DATAFORGE_PYTHON=D:\ana\envs\yolo\python.exe"

if not exist "%DATAFORGE_PYTHON%" (
    echo [DataForge] Python interpreter not found:
    echo %DATAFORGE_PYTHON%
    echo.
    echo Please update DATAFORGE_PYTHON in launch_dataforge.cmd.
    pause
    exit /b 1
)

"%DATAFORGE_PYTHON%" launcher.py
if errorlevel 1 (
    echo.
    echo [DataForge] Startup failed. Review the error above.
    pause
)

endlocal
