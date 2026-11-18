# -*- coding: utf-8 -*-
"""思科生成器 5 处语法 bug + 设备对话框回车 bug 的定向回归。

来源：2026-11-17 两次 bug 审查确认并修复的 6 处缺陷，此前 test_vendor_gen
只覆盖主机名/VLAN/接口/静态路由/DHCP Snooping，未能发现这些问题。
本套件直接对生成器函数做语义断言（无需真机），并模拟 GUI 回车行为。
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

results = []
def case(name, ok, note=""):
    results.append((name, ok, note))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" —— {note}" if note else ""))

from modules.cisco_config import (
    CiscoSecurityGenerator, CiscoVLANGenerator,
    CiscoBasicGenerator, CiscoInterfaceGenerator,
)

print("=" * 68)
print("思科生成器语法修复 + 设备对话框回车 定向回归")
print("=" * 68)

# ---- Bug 1: 标准 ACL 不得输出协议/目的 --------------------------------
std = CiscoSecurityGenerator.generate_acl(
    2000,
    [{"action": "permit", "protocol": None, "source": "1.1.1.1",
      "src_wildcard": "0.0.0.0", "dest": None}],
    "std", acl_type="standard")
case("B1 标准ACL只按源过滤", "permit 1.1.1.1 0.0.0.0" in std and "permit ip" not in std and " any" not in std,
     std.replace("\n", " | "))
std_any = CiscoSecurityGenerator.generate_acl(
    2001, [{"action": "deny", "source": None}], None, acl_type="standard")
case("B1b 标准ACL源为空→deny any", "deny any" in std_any, std_any.replace("\n", " | "))
ext = CiscoSecurityGenerator.generate_acl(
    3000, [{"action": "permit", "protocol": "tcp", "source": "1.1.1.1",
            "src_wildcard": "0.0.0.0", "dest": "2.2.2.2",
            "dst_wildcard": "0.0.0.0", "port": "80"}], None, acl_type="extended")
case("B1c 扩展ACL保持完整语法",
     "permit tcp 1.1.1.1 0.0.0.0 2.2.2.2 0.0.0.0 eq 80" in ext)

# ---- Bug 2: hybrid 接口不得输出 None ----------------------------------
hy = CiscoVLANGenerator.generate_interface("Gi0/1", "hybrid", None)
case("B2 hybrid接口无 None 字面量",
     "None" not in hy and "switchport mode trunk" in hy and "no shutdown" in hy,
     hy.replace("\n", " | "))
hy2 = CiscoVLANGenerator.generate_interface("Gi0/1", "hybrid", None, [10, 20], pvid=10)
case("B2b hybrid带VLAN→allowed+native",
     "allowed vlan 10 20" in hy2 and "native vlan 10" in hy2)

# ---- Bug 3: storm-control 用 pps；rate-limit kbps→bps ------------------
sc = CiscoSecurityGenerator.generate_storm_control("Gi0/1", broadcast=5000, multicast=10000)
case("B3 风暴抑制用 level pps",
     "storm-control broadcast level pps 5000" in sc
     and "storm-control multicast level pps 10000" in sc
     and "level 5000" not in sc, sc.replace("\n", " | "))
rl = CiscoInterfaceGenerator.generate_rate_limit("Gi0/1", rate_in=10000, rate_out=10000)
case("B3b 限速kbps换算bps的CAR",
     "rate-limit input 10000000 " in rl and "rate-limit output 10000000 " in rl
     and "storm-control" not in rl, rl.replace("\n", " | "))

# ---- Bug 4: SNMP 版本分流 ----------------------------------------------
v3 = CiscoBasicGenerator.generate_snmp(version="v3", community_read="public")
case("B4 SNMPv3不输出v2c community",
     "community" not in v3 and "snmp-server user" in v3, v3.replace("\n", " | "))
allv = CiscoBasicGenerator.generate_snmp(version="all", community_read="public")
case("B4b SNMP all 仍输出community", "snmp-server community public ro" in allv)
v2c = CiscoBasicGenerator.generate_snmp(version="v2c", community_read="public")
case("B4c SNMPv2c 输出community", "snmp-server community public ro" in v2c)

# ---- Bug 5: NTP 时区解析 ------------------------------------------------
for tz, expect in [("UTC+8", "clock timezone UTC 8"),
                   ("UTC-5", "clock timezone UTC -5"),
                   ("UTC+0", "clock timezone UTC 0")]:
    ntp = CiscoBasicGenerator.generate_ntp([{"ip": "1.1.1.1"}], timezone=tz)
    case(f"B5 NTP时区 {tz}", expect in ntp, ntp.replace("\n", " | "))

# ---- Bug 6: 设备对话框回车应提交而非取消 -------------------------------
from PyQt5.QtWidgets import QApplication, QPushButton
from PyQt5.QtTest import QTest
from PyQt5.QtCore import Qt
from gui.tabs.device_ops_tab import DeviceDialog

app = QApplication.instance() or QApplication([])
for editing, label in [(False, "添加"), (True, "保存")]:
    device = {"name": "old", "ip": "1.1.1.1"} if editing else None
    d = DeviceDialog(device, parent=None)
    d.show()
    app.processEvents()
    btns = {b.text(): b for b in d.findChildren(QPushButton) if b.text()}
    clicked = []
    for text, btn in btns.items():
        btn.clicked.connect(lambda _=False, t=text: clicked.append(t))
    case(f"B6 {'编辑' if editing else '新增'}保存按钮是默认按钮",
         btns.get(label) is not None and btns[label].isDefault()
         and not btns["取消"].isDefault(),
         f"默认={[t for t,b in btns.items() if b.isDefault()]}")
    d.name_input.setFocus()
    d.name_input.setText("核心-S9306")
    QTest.keyClick(d.name_input, Qt.Key_Return)
    app.processEvents()
    case(f"B6b {'编辑' if editing else '新增'}输入框回车触发{label}",
         clicked == [label] or (label in clicked and "取消" not in clicked),
         f"触发={clicked}")
    d.close()
    app.processEvents()

n_pass = sum(1 for _, ok, _ in results if ok)
print("\n" + "=" * 68)
print(f"思科修复定向回归: PASS {n_pass} / FAIL {len(results) - n_pass}")
for name, ok, note in results:
    if not ok:
        print(f"  ❌ {name} —— {note[:140]}")
sys.exit(0 if all(ok for _, ok, _ in results) else 1)
