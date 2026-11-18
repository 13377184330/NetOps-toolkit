# -*- coding: utf-8 -*-
"""五厂商配置生成端到端黑盒：切换品牌 → 填表单 → 点「生成配置」→ 断言预览输出。
纪律：只点按钮/填输入/读界面。断言以「用户感知正确」为准——
选了锐捷模式，粘到锐捷设备上的就必须是锐捷语法；头部标题也必须与所选品牌一致。
"""
import io
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, ".temp", "realtest")

from PyQt5.QtWidgets import QApplication, QPushButton, QLineEdit
from PyQt5.QtGui import QFont

results = []
def case(name, ok, note=""):
    results.append((name, ok, note))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" —— {note}" if note else ""))

app = QApplication([])
app.setFont(QFont("Microsoft YaHei UI", 9))

# 统一弹窗入口单点 patch：记录 + 全部接受（生成成功/警告照常记录）
import gui.dialogs.base as dlg_base
popups = []
def _rec(parent, kind, title, text, buttons, default_role=None):
    popups.append({"kind": kind, "title": title, "text": text})
    for label, role in buttons:
        if role in ("accept", "yes"):
            return label
    return buttons[0][0]
dlg_base._styled_box = _rec

from gui import theme as _theme
_theme.install()
_theme.set_theme("light", app)
from gui.main_window import MainWindow

print("=" * 68)
print("五厂商配置生成端到端黑盒（品牌下拉 → 填表 → 生成 → 输出语法断言）")
print("=" * 68)
win = MainWindow()
win.resize(1360, 850)
win.show()
app.processEvents()

titles = [win.tab_widget.tabText(i) for i in range(win.tab_widget.count())]
win.tab_widget.setCurrentIndex(titles.index("配置生成"))
app.processEvents()
basic = win.tabs["basic"]
vlan = win.tabs["vlan"]

# VLAN「添加」按钮是局部变量，黑盒定位：文本精确匹配
add_vlan_btn = None
for b in vlan.findChildren(QPushButton):
    if b.text() == "添加":
        add_vlan_btn = b
        break
case("T1 找到 VLAN「添加」按钮", add_vlan_btn is not None)

gen_btn = None
for b in win.findChildren(QPushButton):
    if b.text() == "生成配置":
        gen_btn = b
        break
case("T0 找到「生成配置」按钮", gen_btn is not None)

# 每个厂商的期望：主机名命令、VLAN 创建语法、管理接口名、头部标题，
# 以及接口VLAN/VLANIF/静态路由/DHCP Snooping 的厂商化语法关键词
EXPECT = {
    0: dict(vendor="huawei",  name="华为",  host="sysname SW-TEST",    vlan_kw="vlan 10",  ifname="Vlanif1",         iface_default="Vlanif1",         header="华为交换机配置脚本",
            iface_kw="port link-type access", vlanif_kw="interface Vlanif10\n ip address 192.168.10.1", route_kw="ip route-static 192.168.20.0 255.255.255.0 192.168.1.254", ds_kw="dhcp snooping enable", arp_kw="arp anti-attack check user-bind enable"),
    1: dict(vendor="h3c",     name="H3C",   host="sysname SW-TEST",    vlan_kw="Vlan-interface", ifname="Vlan-interface1", iface_default="Vlan-interface1", header="H3C华三交换机配置脚本",
            iface_kw="port link-type access", vlanif_kw="interface Vlan-interface10\n ip address 192.168.10.1", route_kw="ip route-static 192.168.20.0 255.255.255.0 192.168.1.254", ds_kw="dhcp snooping enable", arp_kw="arp detection enable"),
    2: dict(vendor="ruijie",  name="锐捷",  host="hostname SW-TEST",   vlan_kw="vlan 10",        ifname="interface VLAN 1\n ip address 192.168.1.10", iface_default="VLAN 1",          header="锐捷交换机配置脚本",
            iface_kw="switchport mode access", vlanif_kw="interface vlan 10\n ip address 192.168.10.1", route_kw="ip route 192.168.20.0 255.255.255.0 192.168.1.254", ds_kw="ip dhcp snooping", arp_kw="ip arp inspection vlan 10"),
    3: dict(vendor="maipu",   name="迈普",  host="hostname SW-TEST",   vlan_kw="vlan 10",        ifname="Vlan1",            iface_default="Vlan1",            header="迈普交换机配置脚本",
            iface_kw="switchport mode access", vlanif_kw="interface vlan 10\n ip address 192.168.10.1", route_kw="ip route 192.168.20.0 255.255.255.0 192.168.1.254", ds_kw="dhcp-snooping", arp_kw="arp-check enable"),
    4: dict(vendor="cisco",   name="思科",  host="hostname SW-TEST",   vlan_kw="vlan 10",        ifname="interface vlan 1\n ip address 192.168.1.10", iface_default="vlan 1",            header="思科交换机配置脚本",
            iface_kw="switchport mode access", vlanif_kw="interface vlan 10\n ip address 192.168.10.1", route_kw="ip route 192.168.20.0 255.255.255.0 192.168.1.254", ds_kw="ip dhcp snooping", arp_kw="ip arp inspection vlan 10"),
}

def _click_btn(widget, text):
    """黑盒定位局部变量按钮：按文本精确匹配点击"""
    for b in widget.findChildren(QPushButton):
        if b.text() == text:
            b.click()
            return True
    return False

for idx, exp in EXPECT.items():
    v, nm = exp["vendor"], exp["name"]
    print(f"\n[{v}] {nm}模式")
    popups.clear()
    win.device_combo.setCurrentIndex(idx)
    app.processEvents()
    case(f"{v}0 切换到{nm}模式无异常", True)
    # 用户填表：主机名 + 管理 IP + VLAN 10
    basic.hostname_input.setText("SW-TEST")
    basic.mgmt_ip.setText("192.168.1.10")
    vlan.vlan_id_input.setValue(10)
    vlan.vlan_name_input.setText("TEST")
    if add_vlan_btn is not None:
        add_vlan_btn.click()
    case(f"{v}0a VLAN 已加入列表", vlan.vlan_list.count() == 1,
         vlan.vlan_list.item(0).text() if vlan.vlan_list.count() else "列表为空")
    if exp["ifname"]:
        case(f"{v}0b 管理接口默认值符合{nm}", basic.mgmt_interface.text() == exp["iface_default"],
             f"输入框默认: {basic.mgmt_interface.text()}")
    # 接口 VLAN + VLANIF + 静态路由 + DHCP Snooping（厂商聚合覆盖）
    vlan.interface_input.setText("GigabitEthernet0/1")
    vlan.port_vlan_id.setValue(10)
    _click_btn(vlan, "添加接口")
    vlan.vlanif_vlan_id.setValue(10)
    vlan.vlanif_ip.setText("192.168.10.1")
    _click_btn(vlan, "添加VLANIF")
    case(f"{v}0c 接口/VLANIF 已加入列表",
         vlan.interface_list.count() == 1 and vlan.vlanif_list.count() == 1,
         f"接口{vlan.interface_list.count()} VLANIF{vlan.vlanif_list.count()}")
    routing = win.tabs["routing"]
    routing.route_dest.setText("192.168.20.0")
    routing.route_mask.setText("255.255.255.0")
    routing.route_nexthop.setText("192.168.1.254")
    _click_btn(routing, "添加静态路由")
    case(f"{v}0d 静态路由已加入列表", routing.route_list.count() == 1,
         f"{routing.route_list.count()} 条")
    sec = win.tabs["security"]
    if not sec.dhcp_snoop_enable.isChecked():
        sec.dhcp_snoop_enable.setChecked(True)
    sec.arp_inspect_vlans.setText("10")
    app.processEvents()
    gen_btn.click()
    app.processEvents()
    out = win._clean_config or win.preview_text.toPlainText()
    case(f"{v}1 生成有输出", len(out) > 0, f"{len(out)} 字符")
    if not out:
        continue
    if exp["host"] is None:
        # 已知缺口保留钩子：若某厂商再出现无生成器状态，须在生成时弹警告
        pass
    else:
        case(f"{v}2 主机名命令符合{nm}语法", exp["host"] in out,
             "" if exp["host"] in out else f"期望「{exp['host']}」实际输出:\n" + "\n".join(out.splitlines()[:8]))
    if exp["vlan_kw"] is not None:
        case(f"{v}3 VLAN 语法符合{nm}", exp["vlan_kw"] in out,
             "" if exp["vlan_kw"] in out else f"期望「{exp['vlan_kw']}」实际输出:\n" + "\n".join(out.splitlines()[:14]))
    if exp["ifname"] is not None:
        case(f"{v}4 管理接口名符合{nm}", exp["ifname"].lower() in out.lower(),
             "" if exp["ifname"].lower() in out.lower() else f"期望含「{exp['ifname']}」实际:\n" + "\n".join(out.splitlines()[:14]))
    case(f"{v}5 头部标题为{nm}脚本", exp["header"] in win.preview_text.toPlainText(),
         "" if exp["header"] in win.preview_text.toPlainText()
         else f"期望「{exp['header']}」，实际头部: " + (win.preview_text.toPlainText().splitlines()[1] if len(win.preview_text.toPlainText().splitlines()) > 1 else ""))
    # 原断言 `... or True` 恒真。弹窗入口已 patch 但完整记录到 popups，
    # 可直接断言生成成功确实产生了「成功」反馈。
    _has_success = any(p["title"] == "成功" for p in popups)
    case(f"{v}6 成功弹窗/状态栏反馈", _has_success,
         "生成完成有弹窗反馈" if _has_success else f"popups={popups}")
    if exp.get("iface_kw"):
        case(f"{v}7 接口VLAN语法符合{nm}", exp["iface_kw"] in out,
             "" if exp["iface_kw"] in out else f"期望「{exp['iface_kw']}」未命中")
        case(f"{v}8 VLANIF语法符合{nm}", exp["vlanif_kw"].lower() in out.lower(),
             "" if exp["vlanif_kw"].lower() in out.lower() else f"期望「{exp['vlanif_kw']}」未命中")
        case(f"{v}9 静态路由语法符合{nm}", exp["route_kw"] in out,
             "" if exp["route_kw"] in out else f"期望「{exp['route_kw']}」未命中")
        case(f"{v}10 DHCP Snooping语法符合{nm}", exp["ds_kw"] in out,
             "" if exp["ds_kw"] in out else f"期望「{exp['ds_kw']}」未命中")
        case(f"{v}11 ARP检测语法符合{nm}", exp["arp_kw"] in out,
             "" if exp["arp_kw"] in out else f"期望「{exp['arp_kw']}」未命中")

n_pass = sum(1 for _, ok, _ in results if ok)
print("\n" + "=" * 68)
print(f"五厂商生成黑盒: PASS {n_pass} / FAIL {len(results) - n_pass}")
for name, ok, note in results:
    if not ok:
        print(f"  ❌ {name} —— {note[:120]}")
win.close(); app.processEvents(); win.deleteLater(); app.processEvents()
os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT, "vendor_gen_result.json"), "w", encoding="utf-8") as f:
    json.dump({"results": results}, f, ensure_ascii=False, indent=2)
sys.exit(0 if all(ok for _, ok, _ in results) else 1)
