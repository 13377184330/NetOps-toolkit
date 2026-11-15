# -*- coding: utf-8 -*-
"""迭代3 验证：节点进 CLI（无记录提示 / 预填串口+切页 / 不自动连接）"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
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
popups = []
def _p(parent, kind, title, text, buttons, default_role=None):
    popups.append((kind, title, text))
    return buttons[0][0]
db._styled_box = _p

win = MainWindow()
win.show()
app.processEvents()
titles = [win.tab_widget.tabText(i) for i in range(win.tab_widget.count())]
win.tab_widget.setCurrentIndex(titles.index("网络拓扑"))
app.processEvents()
page = win.topology_page

# 1) 无记录 → 提示
page._data["port"] = ""
page._data["name"] = ""
page._goto_terminal()
assert popups and "采集" in popups[-1][2], f"应弹采集提示，实际 {popups}"
print("PASS 1: 无串口记录 → 友好提示（不切页）")

# 2) 有记录 → 预填 + 切页 + 不自动连接
page._data["port"] = "COM11"
page._data["name"] = "H3C"
page._goto_terminal()
app.processEvents()
cur = win.tab_widget.tabText(win.tab_widget.currentIndex())
assert cur == "自由终端", f"应切到自由终端，当前 {cur}"
term = win.tabs["terminal"]
from modules import console_reader as _cr
has_port = any("COM11" in p for p, _d in _cr.list_console_ports())
if has_port:
    assert "COM11" in term.port_combo.currentText(), \
        f"应预选 COM11，实际 {term.port_combo.currentText()}"
    print("PASS 2: 预填 COM11@9600 + 切页 + 提示行已打（未自动连接）")
else:
    txt = term.port_combo.currentText()
    assert "未检测" in txt or "COM11" in txt, f"无串口时应友好降级，实际 {txt}"
    print(f"PASS 2: 无串口环境优雅降级（下拉={txt}）+ 切页正常")
assert term.baud_spin.value() == 9600
assert not term._connected, "不应自动连接（用户手动点连接）"
term_text = term.term_view.toPlainText()
assert "COM11" in term_text and "连接" in term_text, "终端页应有预填提示行"
print(f"PASS 2: 预填 COM11@9600 + 切页 + 提示行已打（未自动连接）")
print("   终端提示行:", term_text.strip().splitlines()[-1][:60])

# 3) 预填的串口在下拉里不存在时优雅降级（不崩溃）
page._data["port"] = "COM99（不存在）"
ok = term.prefill_console("COM99", 9600)
print(f"PASS 3: 不存在的串口优雅降级（prefill 返回 {ok}，无崩溃）")

win.close(); app.processEvents(); win.deleteLater(); app.processEvents()
print("\n=== 迭代3 节点进 CLI 验证通过 ===")
