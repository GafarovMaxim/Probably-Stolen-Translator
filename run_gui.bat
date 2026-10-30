@echo off
chcp 65001 >nul
title ProbablyTranslator - Launcher
cd /d "%~dp0"
python ProbablyTranslator.py --gui
if errorlevel 1 (
    echo.
    echo Ошибка запуска интерфейса. Убедитесь, что установлен Python 3.
    pause
)
