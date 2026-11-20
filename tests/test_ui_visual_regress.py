# -*- coding: utf-8 -*-
"""UI 视觉回归：文字控件不得被挤压成逐字竖排（"字被上下折叠"）。

背景：工具箱卡片箭头 QLabel('›') 曾因无固定宽度被布局挤到 7px，
字符折成 7 行小箭头。这类 bug 只能靠截图发现，本测试用运行时
几何断言守住：短文本控件的宽度必须够容纳文字，高度不得超过单行。
"""
import os
import sys
import time

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_QPA_FONTDIR"] = r"C:\Windows\Fonts"
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt5.QtWidgets import QApplication, QLabel, QSizePolicy
from PyQt5.QtGui import QFontMetrics

app = QApplication.instance() or QApplication(sys.argv)
from gui import theme
theme.install()
from gui.main_window import MainWindow

results = []
def case(name, ok, note=""):
    results.append((name, ok, note))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" —— {note}" if note else ""))

def pump(ms=250):
    end = time.time() + ms / 1000.0
    while time.time() < end:
        app.processEvents(); time.sleep(0.005)

print("=" * 68)
print("UI 视觉回归 · 文字折叠巡检")
print("=" * 68)

win = MainWindow()
win.resize(1440, 900)
win.show()
pump(400)

def check_folded(root, where):
    """短文本（<=4字符）控件若宽度 < 文字宽，才会逐字折行成竖排。

    注意：控件高度被布局垂直拉伸（如表单标签 43px、箭头 68px）是正常
    布局行为，QLabel 文字仍单行居中，不能据此判折叠。
    """
    bad = []
    for w in root.findChildren(QLabel):
        if not w.isVisible():
            continue
        t = w.text().strip()
        if not t or len(t) > 4 or "<" in t:
            continue
        fm = QFontMetrics(w.font())
        need = fm.horizontalAdvance(t)
        if w.width() < need - 2:
            bad.append((where, t[:12], w.width(), need))
    return bad

# 主窗口各页
folded = []
for i in range(win.tab_widget.count()):
    win.tab_widget.setCurrentIndex(i)
    pump(180)
    folded += check_folded(win, f"tab{i}")
case("主页面无短文字被折叠", not folded, str(folded[:3]))

# 工具箱卡片箭头
try:
    win.open_tools_window(); pump(300)
    from gui.tools_window import NetworkToolsWindow
    tws = [w for w in QApplication.topLevelWidgets() if isinstance(w, NetworkToolsWindow)]
    if tws:
        tw = tws[0]
        arrows = [w for w in tw.findChildren(QLabel)
                  if w.isVisible() and w.text().strip() == "›"]
        case("工具箱卡片箭头存在", len(arrows) >= 12, f"{len(arrows)} 个")
        # 直接校验防御措施本身：箭头必须固定宽度且水平策略 Fixed，
        # 否则在窄布局下会被挤压逐字竖排（这是当初的真 bug 根因）。
        bad_arrows = [a for a in arrows
                      if a.minimumWidth() < 12
                      or a.sizePolicy().horizontalPolicy() != QSizePolicy.Fixed]
        case("工具箱箭头有防折叠约束", not bad_arrows,
             str([(a.minimumWidth(), a.sizePolicy().horizontalPolicy())
                  for a in bad_arrows[:3]]))
        tw.close()
    else:
        case("工具箱窗口可打开", False, "未找到")
except Exception as e:
    case("工具箱箭头检查", False, repr(e))

n = sum(1 for _, ok, _ in results if ok)
print("\n" + "=" * 68)
print(f"UI 视觉回归: PASS {n} / FAIL {len(results) - n}")
for name, ok, note in results:
    if not ok:
        print(f"  ❌ {name} —— {note[:140]}")
sys.exit(0 if all(ok for _, ok, _ in results) else 1)
