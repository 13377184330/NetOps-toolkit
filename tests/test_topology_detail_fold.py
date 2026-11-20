# -*- coding: utf-8 -*-
"""拓扑侧栏：小窗口下操作按钮不得被压扁（文字上下折叠回归）。

背景：窗口 1100x650 时右侧详情面板空间不足，按钮被压到 8px
（文字需 19px），看起来像字被上下裁切折叠。根因是参数区 scroll
占据 stretch、按钮区在主布局里被压缩。修法：按钮区移入 scroll，
空间不足滚动而非压缩。
"""
import os, sys, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_QPA_FONTDIR"] = r"C:\Windows\Fonts"
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt5.QtWidgets import QApplication, QPushButton
app = QApplication.instance() or QApplication(sys.argv)
from gui import theme
theme.install()
from gui.main_window import MainWindow

results = []
def case(name, ok, note=""):
    results.append((name, ok, note))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" —— {note}" if note else ""))

def pump(ms):
    end = time.time() + ms/1000.0
    while time.time() < end:
        app.processEvents(); time.sleep(0.005)

print("=" * 68)
print("拓扑侧栏 · 按钮折叠回归")
print("=" * 68)

# 关键：用小窗口复现（1440x900 下按钮正常，测不出来）
win = MainWindow()
win.resize(1100, 650)
win.show(); pump(400)

titles = [win.tab_widget.tabText(i) for i in range(win.tab_widget.count())]
win.tab_widget.setCurrentIndex(titles.index("网络拓扑")); pump(300)
topo = next((win.tab_widget.widget(i) for i in range(win.tab_widget.count())
             if hasattr(win.tab_widget.widget(i), "_show_detail")), None)
case("拓扑页可定位", topo is not None)

if topo:
    ifaces = [{"name": f"GE1/0/{i}", "detail": {"VLAN": "10", "状态": "UP"}}
              for i in range(1, 30)]
    topo.load_topology(local_name="H3C",
                       local_meta={"版本": "7.1.070", "厂商": "H3C"},
                       parsed={"interfaces": ifaces, "vlans": [{"id": 10}]},
                       vendor="H3C", console_port="COM3")
    pump(500)
    from gui.tabs.topology_tab import DeviceNode
    sw = [n for n in topo.scene.items()
          if isinstance(n, DeviceNode) and n.kind == "switch"]
    case("交换机节点存在", bool(sw))
    if sw:
        sw[0].setSelected(True)
        topo._on_selection_changed()
        pump(300)

        actions = ("端口面板（可视化配置）", "进入终端 CLI", "端口配置（Access/Trunk）",
                   "AI 诊断此设备", "查看完整配置", "配置健康度", "端口一览", "备份配置")
        btns = []
        for idx in range(topo.detail_btn_col.count()):
            bw = topo.detail_btn_col.itemAt(idx).widget()
            if isinstance(bw, QPushButton) and bw.isVisible():
                btns.append(bw)
        case("详情操作按钮已渲染", len(btns) >= 8, f"{len(btns)} 个")
        # 核心断言：按钮高度不得低于 sizeHint 的 80%（文字不被压扁）
        squashed = [(b.text(), b.height(), b.sizeHint().height())
                    for b in btns
                    if b.height() < b.sizeHint().height() * 0.8]
        case("小窗口下按钮未被压扁", not squashed, str(squashed[:3]))

n = sum(1 for _, ok, _ in results if ok)
print("\n" + "=" * 68)
print(f"拓扑侧栏按钮折叠回归: PASS {n} / FAIL {len(results) - n}")
for name, ok, note in results:
    if not ok:
        print(f"  ❌ {name} —— {note[:140]}")
sys.exit(0 if all(ok for _, ok, _ in results) else 1)
