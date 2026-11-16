# -*- coding: utf-8 -*-
"""拓扑页懒加载专项验证：首次切换实例化、空状态节点、反复切换稳定"""
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

# 未切到拓扑页时，不应实例化
assert not hasattr(win, "topology_page"), "拓扑页被提前实例化"
print("[1] 启动时拓扑页未实例化（懒加载生效）")

titles = [win.tab_widget.tabText(i) for i in range(win.tab_widget.count())]
topo_idx = titles.index("网络拓扑")

# 首次切换：触发实例化
win.tab_widget.setCurrentIndex(topo_idx)
app.processEvents()
assert hasattr(win, "topology_page"), "切换到拓扑页后未实例化"
page = win.topology_page
assert page.scene is not None
nodes = page.scene.items()
print(f"[2] 首次切换实例化成功，场景节点数: {len(nodes)}")
assert len(nodes) >= 2, "空状态应至少有本机PC+交换机两个节点"

# 反复切换（切走再切回），验证不重复实例化、不崩溃
win.tab_widget.setCurrentIndex(0)
app.processEvents()
win.tab_widget.setCurrentIndex(topo_idx)
app.processEvents()
assert win.topology_page is page, "反复切换时拓扑页被重复实例化"
print("[3] 反复切换稳定，未重复实例化")

# 清空/空状态重绘不崩
page.clear_config()
app.processEvents()
print("[4] 拓扑页 clear_config 正常")

# 显式关闭，避免脚本自然结束时的 Qt 析构陷阱（0xC0000005）
win.close()
app.processEvents()
win.deleteLater()
app.processEvents()

print("\n=== 拓扑页懒加载专项验证通过 ===")
