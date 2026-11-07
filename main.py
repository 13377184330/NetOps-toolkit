#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
NetOps Toolkit v4.0
网络运维工具集 - 交换机配置生成 + 11个网络工具
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QT_VERSION_STR
from PyQt5.QtGui import QFont, QPalette, QColor

# 主题引擎：必须在创建任何控件之前打补丁（把浅色词汇的样式串按当前主题翻译）
from gui import theme as _theme
_theme.install()

# 高分屏适配：让系统 DPI 缩放接管，避免 Qt 内部两次换算导致文字发糊/挤压（150% DPI 环境实测）
if hasattr(Qt, "AA_EnableHighDpiScaling"):
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
if hasattr(Qt, "AA_UseHighDpiPixmaps"):
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

from gui.main_window import MainWindow
from gui.tools_window import NetworkToolsWindow
from gui.splash import SplashManager

APP_NAME = "NetOps Toolkit"
APP_VERSION = "4.0"


def _startup_theme(app):
    """启动时应用主题：浅色 / 深色 / 跟随系统（存的是偏好，这里归一化成实际主题）"""
    pref = "light"
    try:
        from utils.settings import Settings
        pref = Settings().get("theme", "light") or "light"
    except Exception:
        pass
    if pref == "system":
        pref = _theme.system_theme()
    _theme.set_theme(pref if pref in ("light", "dark") else "light", app)


def main():
    """主函数"""
    app = QApplication(sys.argv)

    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)

    font = QFont("Microsoft YaHei UI", 9)
    app.setFont(font)

    _startup_theme(app)

    splash_manager = SplashManager(app)
    
    def on_splash_complete():
        window = MainWindow()
        window.show()
    
    splash_manager.start_loading(on_splash_complete)
    
    sys.exit(app.exec_())


def run_tools():
    """运行网络工具箱"""
    app = QApplication(sys.argv)

    app.setApplicationName("网络工具箱")
    app.setApplicationVersion("1.0")

    font = QFont("Microsoft YaHei UI", 9)
    app.setFont(font)

    _startup_theme(app)

    splash_manager = SplashManager(app)
    
    def on_splash_complete():
        window = NetworkToolsWindow()
        window.show()
    
    splash_manager.start_loading(on_splash_complete)
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
