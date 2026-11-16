# -*- coding: utf-8 -*-
"""验证：切到拓扑页后，走真实关闭流程（close + 显式析构）是否崩溃"""
import io
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from gui import theme as _theme
_theme.install()
QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
app = QApplication(sys.argv)
app.setFont(QFont("Microsoft YaHei UI", 9))
_theme.set_theme("light", app)

from gui.main_window import MainWindow
win = MainWindow()
win.show()
app.processEvents()

titles = [win.tab_widget.tabText(i) for i in range(win.tab_widget.count())]
topo_idx = titles.index("网络拓扑")
win.tab_widget.setCurrentIndex(topo_idx)   # 触发懒加载
app.processEvents()
page = win.topology_page
page.clear_config()
app.processEvents()

# 真实关闭流程
win.close()
app.processEvents()
win.deleteLater()
app.processEvents()
print("CLOSE_OK")
sys.exit(0)
