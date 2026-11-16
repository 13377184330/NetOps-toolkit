# -*- coding: utf-8 -*-
"""AI 运维新布局 + 跨模块联动验证（截图对比 + 断言）"""
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
win.resize(1360, 850)
win.show()
app.processEvents()

titles = [win.tab_widget.tabText(i) for i in range(win.tab_widget.count())]

# 1) 布局：聊天区与队列左右分栏
ai_idx = titles.index("AI 运维")
win.tab_widget.setCurrentIndex(ai_idx)
app.processEvents()
ai = win.tabs["ai_ops"]
assert hasattr(ai, "splitter"), "新分栏布局未生效"
assert ai.splitter.count() == 2, "分栏应为左右两块"
assert ai.splitter.widget(0) is ai.chat_view, "左栏应为聊天区"
assert ai.chat_view.width() > ai.queue_scroll.width(), \
    f"聊天区({ai.chat_view.width()}) 应比队列({ai.queue_scroll.width()})宽"
print(f"[1] 左右分栏 OK：聊天区宽 {ai.chat_view.width()} / 队列栏宽 {ai._queue_group.width()}")

# 队列加卡片，截图看整体
cards = [{"cmd": "system-view", "note": "进入系统视图", "risk": "write", "lint": []},
         {"cmd": "vlan batch 10 20", "note": "批量建 VLAN", "risk": "write", "lint": []},
         {"cmd": "undo stp enable", "note": "关生成树", "risk": "dangerous", "lint": []}]
ai._queue_cards(cards, source="AI")
app.processEvents()
win.grab().save(os.path.join(ROOT, ".temp", "shot_ai_layout.png"))
print("[2] 新布局截图已保存 shot_ai_layout.png")

# 2) 联动：队列命令 → 配置生成页
ai._on_card_checked(0, True)
ai._on_card_checked(1, True)
ai._send_to_config_gen()
app.processEvents()
assert "system-view" in win.preview_text.toPlainText(), "命令应转入配置生成页预览"
assert win.tab_widget.tabText(win.tab_widget.currentIndex()) == "配置生成", "应切到配置生成页"
print("[3] 联动（队列→配置生成）OK：预览含转入命令，页面已切换")

# 3) 联动：拓扑页 → AI 诊断
win.tab_widget.setCurrentIndex(titles.index("网络拓扑"))
app.processEvents()
page = win.topology_page
page._data = {"name": "SW-01", "vendor": "华为",
              "raw": "sysname SW1\nvlan batch 10"}
page._goto_ai_diagnosis()
app.processEvents()
assert ai._mode() == "analyze", "应切到诊断分析模式"
assert len(ai._external_context) > 0, "拓扑采集配置应作为一次性上下文带入"
assert win.tab_widget.tabText(win.tab_widget.currentIndex()) == "AI 运维", "应切回 AI 运维页"
print(f"[4] 联动（拓扑→AI 诊断）OK：模式=诊断分析，带入上下文 {len(ai._external_context)} 字符")

win.close(); app.processEvents(); win.deleteLater(); app.processEvents()
print("\n=== AI 运维新布局 + 联动验证通过 ===")
