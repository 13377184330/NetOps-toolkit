# -*- coding: utf-8 -*-
"""Console 采集 → 拓扑页联动修复验证：采集完成后拓扑页被幂等实例化并填充数据"""
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

# 启动时拓扑页未实例化
assert not hasattr(win, "topology_page"), "启动时拓扑页应未实例化"
console = win.tabs["console_viz"]

# 模拟一次 Console 采集完成 → _sync_topology
result = {
    "vendor": "huawei", "version": "V200R020",
    "config": "sysname SW1\n vlan batch 10 20",
    "parsed": {"basic": {"主机名": "SW1", "软件版本": "V200R020"},
               "stats": {"接口数": 4, "VLAN 数": 2},
               "interfaces": [], "vlans": [], "routes": [], "security": []},
    "lldp": "", "mac": "", "arp": "", "link_up": {}, "health": None,
}
console._sync_topology(result)
app.processEvents()

assert hasattr(win, "topology_page"), "采集后拓扑页应被实例化"
page = win.topology_page
assert page._data.get("name") == "SW1", f"拓扑数据应填充主机名 SW1，实际 {page._data.get('name')}"
print("[1] Console 采集后拓扑页幂等实例化 + 数据填充 OK:", page._data.get("name"))

# 再次采集（拓扑页已实例化），不应重复创建
page2 = win.topology_page
console._sync_topology(result)
app.processEvents()
assert win.topology_page is page2, "再次采集不应重复实例化拓扑页"
print("[2] 拓扑页已实例化后再次采集复用同一实例 OK")

# 显式关闭，避免脚本自然结束时的 Qt 析构陷阱（0xC0000005）
win.close()
app.processEvents()
win.deleteLater()
app.processEvents()

print("\n=== Console→拓扑联动修复验证通过 ===")
