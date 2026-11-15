@echo off
chcp 65001 >nul
title NetOps Toolkit - 一键回归
cd /d "%~dp0"
echo ========================================
echo   NetOps Toolkit v4.2 - 一键回归测试
echo ========================================
echo.
python tests\run_tests.py %*
echo.
pause
