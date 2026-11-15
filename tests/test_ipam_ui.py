# -*- coding: utf-8 -*-
"""迭代4 IPAM 验证：工具页 UI 全链路（用临时 IPAM 文件防污染真实数据）
登记→重复拒绝→建议可用→标记（跨段拒绝）→表格刷新→删除"""
import io
import os
import sys
import tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
sys.path.insert(0, r"C:\Users\30525\.local\share\TeleAgent\TeleAgent的工作空间\NetOps-toolkit")

from PyQt5.QtWidgets import QApplication
app = QApplication([])
from gui import theme as _theme
_theme.install()
_theme.set_theme("light", app)

# 隔离：临时 IPAM 文件
tmp = tempfile.mkdtemp(prefix="ipam_ui_")
import modules.ipam as ipam
ipam.IPAM_FILE = os.path.join(tmp, "ipam.json")

from gui.tools.ipam_tool import IPAMWidget
w = IPAMWidget()
w.resize(980, 640)
w.show()
app.processEvents()

# 1) 登记
w.cidr_edit.setText("192.168.10.1/24")
w.name_edit.setText("高一教学楼")
w.usage_edit.setText("教学办公")
w._add()
app.processEvents()
assert w.table.rowCount() == 1, f"应 1 行，实际 {w.table.rowCount()}"
assert "192.168.10.0/24" == w.table.item(0, 0).text()
assert "标记行已同步网段下拉" and w.subnet_combo.count() == 1
assert "已登记" in w.hint.text()
print("PASS 1: 登记（1/24 规范化 → 0/24）+ 表格/下拉同步")

# 2) 重复拒绝
w.cidr_edit.setText("192.168.10.55/24")
w._add()
assert "已登记" in w.hint.text() and w.table.rowCount() == 1
print("PASS 2: 重复网段拒绝（不同写法同网段也拦）")

# 3) 建议可用 + 标记
w.subnet_combo.setCurrentIndex(0)
w._suggest("192.168.10.0/24")
suggested = w.ip_edit.text()
assert suggested == "192.168.10.2", f"应建议 .2（.1 留网关），实际 {suggested}"
w.note_edit.setText("SW-01 管理口")
w._mark()
app.processEvents()
assert w.table.item(0, 2).text() == "1/254"
assert w.table.item(0, 3).text() == "192.168.10.2"
print(f"PASS 3: 建议可用（留网关位）+ 标记已用（最近已用列可见）")

# 4) 跨网段拒绝
w.ip_edit.setText("10.0.0.5")
w._mark()
assert "不属于" in w.hint.text() or "⚠" in w.hint.text()
print("PASS 4: 跨网段 IP 拒绝")

# 5) 空 IP 自动建议 + 删除
w.ip_edit.clear()
w.note_edit.setText("AP-3F")
w._mark()
assert w.table.item(0, 2).text() == "2/254"
w._del("192.168.10.0/24")
app.processEvents()
assert w.table.rowCount() == 0
print("PASS 5: 空 IP 自动建议下一个 + 删除网段")

w.grab().save(os.path.join(r"C:\Users\30525\.local\share\TeleAgent\TeleAgent的工作空间\NetOps-toolkit",
                           ".temp", "realtest", "shot_ipam.png"))
w.close(); app.processEvents()
print("\n=== 迭代4 IPAM 验证通过 ===")
