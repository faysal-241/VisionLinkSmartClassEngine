@echo off
title VisionLink Smart Class Engine
cd /d "%~dp0"
echo ==========================================
echo Starting VisionLink Smart Class Engine...
echo ==========================================
python main.py
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Application exited with error code %errorlevel%
    pause
)
