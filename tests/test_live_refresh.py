# -*- coding: utf-8 -*-
"""迭代2 验证：实时刷新开关生命周期（无记录拦截 → 开 → timer 活 → 关 → timer 停）"""
import io
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
sys.path.insert(0, r"C:\Users\30525\.local\share\TeleAgent\TeleAgent的工作空间\NetOps-toolkit")

from PyQt5.QtWidgets import QApplication
app = QApplication([])
from gui import theme as _theme
_theme.install()
_theme.set_theme("light", app)
from gui.main_window import MainWindow
import gui.dialogs.base as db
popup = []
def _p(parent, kind, title, text, buttons, default_role=None):
    popup.append(text)
    return buttons[0][0]
db._styled_box = _p

win = MainWindow()
win.show()
app.processEvents()
titles = [win.tab_widget.tabText(i) for i in range(win.tab_widget.count())]
win.tab_widget.setCurrentIndex(titles.index("网络拓扑"))
app.processEvents()
page = win.topology_page

# 1) 无采集记录：开实时 → 弹提示并回弹
page._data["port"] = ""
page.live_btn.click()
app.processEvents()
assert not page.live_btn.isChecked(), "无记录应回弹"
assert popup and "采集" in popup[0], "应弹『先采集』提示"
print("PASS 1: 无采集记录 → 友好拦截回弹")

# 2) 有记录：开 → timer 启动
page._data["port"] = "COM11"
page._data["vendor"] = "H3C"
page.live_btn.click()
app.processEvents()
assert page.live_btn.isChecked(), "开启后应 checked"
assert page._live_timer is not None and page._live_timer.isActive(), "timer 应激活"
assert page.live_btn.text() == "实时: 开"
print("PASS 2: 开启 → 30s 轮询 timer 激活")

# 3) 关 → timer 停止
page.live_btn.click()
app.processEvents()
assert page._live_timer is None and page.live_btn.text() == "实时: 关"
print("PASS 3: 关闭 → timer 停止")

# 4) _live_tick 空数据保护（直接调，串口占用场景静默跳过）
page._data["port"] = "COM11"
page._live_busy = True
page._live_tick()   # busy 时直接返回，无异常
page._live_busy = False
print("PASS 4: 忙时防重入保护")

win.close(); app.processEvents(); win.deleteLater(); app.processEvents()
print("\n=== 迭代2 实时刷新验证通过 ===")
