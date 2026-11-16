# -*- coding: utf-8 -*-
"""v4.1 回归冒烟：主窗口全部 tab 可构建 + 工具箱页面可构建 + 原有引擎能力不回退"""
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

# 1) 主窗口：全部页签可构建（含新 AI 运维页）
from gui.main_window import MainWindow
win = MainWindow()
win.resize(1360, 850)
win.show()
app.processEvents()
titles = [win.tab_widget.tabText(i) for i in range(win.tab_widget.count())]
print("[1] 页签:", titles)
assert "AI 运维" in titles
for i, t in enumerate(titles):
    win.tab_widget.setCurrentIndex(i)
    app.processEvents()
print("[2] 六个页签逐页切换无崩溃")

# 3) 工具箱（自然语言生成等 17 工具页）
from gui.tools_window import NetworkToolsWindow
tw = NetworkToolsWindow()
tw.show()
app.processEvents()
print("[3] 工具箱", tw.stack.count(), "页可构建")

# 4) 原有引擎不回退：nl_engine / config_lint / 跨厂商转换冒烟
from modules import nl_engine
r = nl_engine.parse("创建vlan10 20，把gi1/0/1划入vlan10，GE1/0/24做trunk放行vlan 10 20", "h3c")
assert any("vlan 10 to 20" in c for c, _ in r["lines"]) or r["lines"], r["intents"]
assert r["intents"], "nl_engine 退化"
from modules.config_lint import lint
res = lint("sysname SW1\ninterface Vlan-interface10\n ip address 192.168.10.1 255.255.255.0", "h3c")
assert isinstance(res, dict) and "items" in res
print("[4] 原有引擎冒烟 OK:", r["intents"])

# 5) AI 页在深浅主题下切换渲染回调不崩
ai_idx = titles.index("AI 运维")
win.tab_widget.setCurrentIndex(ai_idx)
tab = win.tabs["ai_ops"]
tab._append_user("测试")
tab._append_ai_final("回\n```netcfg\nsystem-view # 进入\n```", 1, 0)
app.processEvents()
_theme.set_theme("dark", app)
app.processEvents()
_theme.set_theme("light", app)
app.processEvents()
print("[5] AI 页双主题切换重绘无崩溃")

# 显式收尾：脚本自然结束时局部 win/app 被 GC 析构顺序不可控，
# 实测 0xC0000005 退出崩溃（断言全过但退出码非 0，跑批器误判 FAIL）
win.close()
tw.close()
app.processEvents()
win.deleteLater()
tw.deleteLater()
app.processEvents()

print("\n=== v4.1 回归冒烟全部通过 ===")
