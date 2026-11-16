# -*- coding: utf-8 -*-
"""渲染升级验证：视图缩进 + 注释分层 + 高危红行"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, r"C:\Users\30525\.local\share\TeleAgent\TeleAgent的工作空间\NetOps-toolkit")

from PyQt5.QtWidgets import QApplication
app = QApplication([])
from gui import theme as _theme
_theme.install()
_theme.set_theme("light", app)
from gui.tabs.ai_ops_tab import _render_ai_content, _line_indent_level

# ① 缩进层级
assert _line_indent_level("system-view") == 1
assert _line_indent_level("interface GigabitEthernet1/0/9") == 1
assert _line_indent_level("vlan 10") == 1
assert _line_indent_level("port access vlan 10") == 0
assert _line_indent_level("quit") == -1
assert _line_indent_level("return") == -1
print("PASS: 缩进层级判定")

# ② 真实渲染
fence_open = "```netcfg\n"
fence_close = "\n```"
body = ("system-view # 进系统视图\n"
        "vlan 10 # 创建 VLAN\n"
        " quit\n"
        "interface GigabitEthernet1/0/1\n"
        " port link-type access # 设为 access\n"
        " port access vlan 10 # 划入\n"
        " quit\n"
        "undo stp enable # 高危示例\n"
        "display vlan # 核对\n"
        "return")
reply = "说明文字\n" + fence_open + body + fence_close + "\n尾注"
html = _render_ai_content(reply)

# 注释分层：# 前后带空格转义
assert html.count("&nbsp;#&nbsp;") == 6, f"注释分层样式数 {html.count('&nbsp;#&nbsp;')} != 6"
# 高危红行
assert "undo stp enable" in html
# 缩进：interface 后的子命令应有 margin-left 结构化缩进
# （真机用户实测教训：全角/半角空格缩进会被 QTextBrowser 空白折叠吞掉，
#   函数层 HTML 正确 ≠ 显示层正确——必须同时验渲染后文档层）
import re as _re
m = _re.search(r'<div style="color:[^"]*;margin-left:(\d+)px;">\s*port link-type access', html)
assert m and int(m.group(1)) >= 14, f"interface 子命令应有 ≥1 级 margin 缩进，实际 {m.group(0)[:60] if m else '未匹配'}"
print("PASS: 注释分层 6 处 / 高危保留 / 子命令 margin 缩进")
print(f"  port link-type access 缩进: margin-left:{m.group(1)}px")
