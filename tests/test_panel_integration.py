# -*- coding: utf-8 -*-
"""设备面板新模块集成验证：QGraphics 端口矩阵 + 点击闭环 + 批量脏更新 + 主题"""
import io
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, ".temp", "realtest")

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont
app = QApplication([])
app.setFont(QFont("Microsoft YaHei UI", 9))
import gui.dialogs.base as db
db._styled_box = lambda p, k, t, x, b, d=None: b[0][0]
from gui import theme as _theme
_theme.install()
_theme.set_theme("light", app)

from gui.main_window import MainWindow
win = MainWindow()
win.show()
app.processEvents()
titles = [win.tab_widget.tabText(i) for i in range(win.tab_widget.count())]
win.tab_widget.setCurrentIndex(titles.index("网络拓扑"))
app.processEvents()
page = win.topology_page

# 构造真实形态的采集数据（6 端口：4 GE + 2 XGE，含终端/邻居）
page._data = {
    "name": "TEST-SW", "vendor": "H3C", "meta": {"型号": "S5528S"},
    "parsed": {"interfaces": [
        {"name": "GigabitEthernet1/0/1", "kind": "GE", "detail": {"VLAN": "10", "描述": "教室A"}},
        {"name": "GigabitEthernet1/0/2", "kind": "GE", "detail": {"VLAN": "10", "描述": "教室B"}},
        {"name": "GigabitEthernet1/0/3", "kind": "GE", "detail": {"VLAN": "20"}},
        {"name": "GigabitEthernet1/0/4", "kind": "GE", "detail": {}},
        {"name": "Ten-GigabitEthernet1/0/25", "kind": "10GE", "detail": {"VLAN": "trunk 1 to 4094"}},
        {"name": "Ten-GigabitEthernet1/0/26", "kind": "10GE", "detail": {}},
    ]},
    "link_up": {"GE1/0/1": True, "GE1/0/2": True, "GE1/0/3": False,
                "GE1/0/4": False, "XGE1/0/25": True, "XGE1/0/26": False},
    "hosts": [{"port": "GigabitEthernet1/0/2", "ip": "192.168.10.5"}],
    "neighbors": [{"port": "Ten-GigabitEthernet1/0/25", "name": "CORE-SW"}],
    "raw": "sysname TEST-SW\n",
}

from gui.dialogs.device_panel import DevicePanelDialog
dlg = DevicePanelDialog(page)
dlg.show()
app.processEvents()

results = []
def case(name, ok, note=""):
    results.append((name, ok, note))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" —— {note}" if note else ""))

print("=" * 62)
print("设备面板新模块（QGraphics）集成验证")
print("=" * 62)

# 1) 视图与端口
case("1 分组视图已创建", len(dlg._views) == 2, f"{list(dlg._views.keys())}")
total_items = sum(len(v.panel_scene.port_items) for v in dlg._views.values())
case("2 端口总数 6（4GE+2XGE）", total_items == 6, f"{total_items} 个")
ge_view = dlg._views.get("GE")
case("3 端口项是 QGraphicsItem 且带真实名",
     ge_view is not None and "GigabitEthernet1/0/1" in ge_view.panel_scene.port_items)

# 4) 状态映射（UP/DOWN/trunk）
st = {n: i.state for n, i in ge_view.panel_scene.port_items.items()}
case("4 状态映射（up/down）", st.get("GigabitEthernet1/0/1") == "up"
     and st.get("GigabitEthernet1/0/3") == "down", str(st))
xge = dlg._views.get("10GE")
xst = {n: i.state for n, i in xge.panel_scene.port_items.items()}
case("5 Trunk 状态识别", xst.get("Ten-GigabitEthernet1/0/25") == "trunk", str(xst))
case("6 终端/邻居角标数据", 
     ge_view.panel_scene.port_items["GigabitEthernet1/0/2"].terminal_connected
     and xge.panel_scene.port_items["Ten-GigabitEthernet1/0/25"].neighbor_connected)

# 7) 点击闭环：选中 + 参数卡 + 命令预览
dlg._on_view_port_clicked("GigabitEthernet1/0/1")
app.processEvents()
case("7 点击选中端口", dlg._selected == ["GigabitEthernet1/0/1"], str(dlg._selected))
case("8 参数卡回显端口", "GigabitEthernet1/0/1" in dlg.cur_lab.text(), dlg.cur_lab.text()[:50])
case("9 命令预览已生成", len(dlg._lines) > 0, f"{len(dlg._lines)} 条")

# 10) 选中态下发到各视图
item = ge_view.panel_scene.port_items["GigabitEthernet1/0/1"]
case("10 选中态标记到图元", item._selected)

# 11) 批量脏更新：模拟链路状态变化（3 号口 UP，1 号口 DOWN）
old_sig = dlg._last_link_sig
page._data["link_up"]["GE1/0/3"] = True
page._data["link_up"]["GE1/0/1"] = False
dlg._poll_port_states()
app.processEvents()
case("11 状态指纹变化触发更新", dlg._last_link_sig != old_sig)
case("12 3 号口 变 UP", ge_view.panel_scene.port_items["GigabitEthernet1/0/3"].state == "up",
     ge_view.panel_scene.port_items["GigabitEthernet1/0/3"].state)
case("13 1 号口 变 DOWN", ge_view.panel_scene.port_items["GigabitEthernet1/0/1"].state == "down")

# 14) 无变化时零重绘（指纹不变，_poll 直接返回）
sig_before = dlg._last_link_sig
dlg._poll_port_states()
case("14 无变化零更新", dlg._last_link_sig == sig_before)

# 15) 主题切换重绘不崩
_theme.set_theme("dark", app)
app.processEvents()
_theme.set_theme("light", app)
app.processEvents()
case("15 双主题切换重绘无异常", True)

dlg.grab().save(os.path.join(OUT, "shot_panel_graphics.png"))
n_pass = sum(1 for _, ok, _ in results if ok)
print("\n" + "=" * 62)
print(f"集成验证: PASS {n_pass} / FAIL {len(results) - n_pass}")
for n, ok, note in results:
    if not ok:
        print(f"  ❌ {n} —— {note}")
dlg.close()
win.close(); app.processEvents(); win.deleteLater(); app.processEvents()
sys.exit(0 if all(ok for _, ok, _ in results) else 1)