@echo off
chcp 65001 >nul
title NetOps Toolkit v4.1 - 网络运维工具集

echo ========================================
echo NetOps Toolkit v4.1
echo 网络运维工具集
echo ========================================
echo.

cd /d "%~dp0"

rem PyQt5 (Qt 5.15.2) 在含中文的路径下无法加载平台插件，提前检测给出明确提示
echo %CD%| findstr /r "[^ -~]" >nul
if %errorlevel% equ 0 (
    echo [警告] 当前路径含非英文字符，PyQt5 可能无法启动！
    echo [建议] 将项目移动到纯英文路径，例如 D:\NetOps-toolkit
    echo.
)

python main.py

if %errorlevel% neq 0 (
    echo.
    echo 启动失败，请检查Python环境。
    echo 确保已安装: pip install PyQt5 netmiko cryptography requests
    echo.
    pause
)
