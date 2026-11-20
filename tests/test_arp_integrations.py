# -*- coding: utf-8 -*-
"""ARP 扫描项目内联动验证：IPAM 数据闭环 + 存入设备清单 + 交换机采集导入
（逻辑层全套 + GUI 链路，FakeMain 顶替主窗口、mock DeviceDialog，
临时文件隔离绝不触碰真实 config/）"""
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
sys.path.insert(0, r"C:\Users\30525\.local\share\TeleAgent\TeleAgent的工作空间\NetOps-toolkit")

from modules import arp_scan
from modules import ipam as ipam_mod

# 隔离：名册/网关历史/IPAM/设备清单全部指向临时目录
tmp = tempfile.mkdtemp(prefix="arp_link_test_")
arp_scan.ROSTER_FILE = os.path.join(tmp, "roster.json")
arp_scan.GW_HISTORY_FILE = os.path.join(tmp, "gwhistory.json")
ipam_mod.IPAM_FILE = os.path.join(tmp, "ipam.json")

import utils.device_store as ds_mod
ds_mod.DEVICES_FILE = os.path.join(tmp, "devices.json")
ds_mod.DeviceStore._instance = None   # 重置单例，指向隔离文件

# 非模态弹窗替身：offscreen 下 QMessageBox.exec_ 永远等不到点击会卡死测试，
# 全部换成记录器——断言弹窗文案（“已在清单中”类提示不许静默丢）
POPUPS = []


def _fake_popup(kind, parent, title, text, *a, **kw):
    POPUPS.append((kind, title, text))
    return True


import gui.tools.arp_scan_tool as tool_mod
tool_mod.info_box = lambda *a, **kw: _fake_popup("info", *a, **kw)
tool_mod.warn_box = lambda *a, **kw: _fake_popup("warn", *a, **kw)

fails = []

def check(name, cond, detail=""):
    if cond:
        print(f"PASS {name}")
    else:
        fails.append(name)
        print(f"FAIL {name} {detail}")


def mkdev(ip, mac, **kw):
    d = {"ip": ip, "mac": mac, "arp_type": "dynamic", "vendor": arp_scan.lookup_vendor(mac),
         "hostname": "", "name": "", "note": "", "tags": []}
    d.update(kw)
    return d


# ========== 1. 逻辑层：网络设备识别 ==========
check("H3C 识别为网络设备", arp_scan.network_vendor("00:1E:10:AA:BB:CC") == "H3C")
check("华为识别", arp_scan.network_vendor("00:E0:FC:11:22:33") == "Huawei")
check("Cisco 识别", arp_scan.network_vendor("00:00:0C:AA:BB:CC") == "Cisco")
check("虚拟机 MAC 不算网络设备", arp_scan.network_vendor("00:50:56:AA:BB:CC") == "")
check("随机化 MAC 不算", arp_scan.network_vendor("02:11:22:33:44:55") == "")
check("普通终端不识别", arp_scan.network_vendor("A4:AE:12:2E:17:33") == "")

# ========== 2. 逻辑层：交换机 ARP 合并 ==========
local = [
    mkdev("192.168.1.1", "10:12:B4:F7:9A:CC", tags=["默认网关"]),
    mkdev("192.168.1.8", "A2:63:8D:58:5F:7B", hostname="WIN-PC"),
]
# 交换机 ARP 行格式同 cv.parse_arp 输出（mac 12 位无分隔小写）
switch_rows = [
    {"ip": "192.168.1.1", "mac": "1012b4f79acc"},          # 同本机 → 交换机证实
    {"ip": "192.168.1.8", "mac": "a2deadbeef01"},           # 同 IP 不同 MAC → 合并后冲突
    {"ip": "10.20.30.40", "mac": "001e10aa9988"},           # 跨 VLAN 新设备 → 交换机视角
    {"ip": "192.168.1.50", "mac": "aabbccddee"},            # MAC 传少于 12 位 → 无效丢
    {"ip": "192.168.1.60", "mac": ""},                      # MAC 空 → 丢
]
stat = arp_scan.merge_switch_arp(local, switch_rows)
check("合并统计：新增 2", stat["added"] == 2, f"{stat}")
check("合并统计：背书 1", stat["updated"] == 1, f"{stat}")
check("总数 4 台", len(local) == 4, f"{len(local)}")
by_ip = {}
for d in local:
    by_ip.setdefault(d["ip"], []).append(d)
check("跨 VLAN 新设备标「交换机视角」", by_ip["10.20.30.40"][0]["tags"][:1] == ["交换机视角"],
      f"{by_ip['10.20.30.40'][0]['tags']}")
check("交换机视角新设备补厂商（H3C）", by_ip["10.20.30.40"][0]["vendor"] == "H3C")
check("交换机视角新设备标「疑似网络设备」", "疑似网络设备" in by_ip["10.20.30.40"][0]["tags"])
check("网关被背书", "交换机证实" in by_ip["192.168.1.1"][0]["tags"])
check("合并后按 IP 排序", [d["ip"] for d in local] == ["10.20.30.40", "192.168.1.1",
                                                        "192.168.1.8", "192.168.1.8"])
# 重算风险：同 IP 双侧 MAC 不一致 → 冲突
risks = arp_scan.analyze(local, gateway_ip="192.168.1.1", prev_gateway_mac="")
check("跨视角同 IP 多 MAC 报冲突",
      any(r["type"] == "ip_conflict" and r["ip"] == "192.168.1.8" for r in risks), f"{risks}")
# 幂等：再导一次不涨重复
stat2 = arp_scan.merge_switch_arp(local, switch_rows)
check("重复导入幂等", stat2["added"] == 0 and len(local) == 4, f"{stat2}")

# ========== 3. 逻辑层：IPAM 同步闭环 ==========
devices = [
    mkdev("192.168.10.2", "10:12:B4:F7:9A:CC", name="张师傅-测试机"),
    mkdev("192.168.10.3", "A2:63:8D:58:5F:7B", hostname="DESKTOP-3F"),
    mkdev("192.168.10.4", "00:1E:10:AA:BB:CC"),            # 厂商做备注
    mkdev("10.9.9.9", "00:1E:10:AA:BB:CD"),                # 跨段 → 不记
]
r = arp_scan.sync_to_ipam("192.168.10.0/24", devices)
check("同步 ok", r.get("ok"), f"{r}")
check("网段自动登记", r.get("subnet_created") is True, f"{r}")
check("新标记 3 条", r.get("marked") == 3, f"{r}")
subs = ipam_mod.list_subnets()
check("IPAM 有该网段", any(s["subnet"] == "192.168.10.0/24" for s in subs))
rec = next(s for s in subs if s["subnet"] == "192.168.10.0/24")
used_map = {u["ip"]: u.get("note", "") for u in rec["used"]}
check("姓名做备注", used_map.get("192.168.10.2") == "张师傅-测试机", f"{used_map}")
check("主机名做备注", used_map.get("192.168.10.3") == "DESKTOP-3F", f"{used_map}")
check("厂商做备注", used_map.get("192.168.10.4") == "H3C", f"{used_map}")
check("跨段 IP 不入账", "10.9.9.9" not in used_map)
# 二次同步：用户已手改一条备注 → 不覆盖（直接改内存数据回写，绕过 list_subnets 的只读拷贝陷阱）
data = ipam_mod._load()
for s in data["subnets"]:
    for u in s.get("used", []):
        if u.get("ip") == "192.168.10.2":
            u["note"] = "手写笔记勿覆盖"
ipam_mod._save(data)
devs2 = [
    mkdev("192.168.10.2", "10:12:B4:F7:9A:CC", name="张师傅-测试机"),   # 已有 → 跳过
    mkdev("192.168.10.9", "00:00:0C:11:22:33"),                         # 新增
]
r2 = arp_scan.sync_to_ipam("192.168.10.0/24", devs2)
check("二次同步跳过已有", r2.get("skipped") == 1 and r2.get("marked") == 1, f"{r2}")
rec2 = next(s for s in ipam_mod.list_subnets() if s["subnet"] == "192.168.10.0/24")
used2 = {u["ip"]: u.get("note", "") for u in rec2["used"]}
check("手写备注不被覆盖", used2.get("192.168.10.2") == "手写笔记勿覆盖", f"{used2}")
check("非法网段拒绝", not arp_scan.sync_to_ipam("abc", []).get("ok"))

# ========== 4. GUI 全链路（FakeMain 主窗口 + mock 弹窗） ==========
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QApplication, QWidget, QTableWidget)
from PyQt5.QtTest import QTest

app = QApplication.instance() or QApplication([])
from gui import theme as _theme
_theme.install()
_theme.set_theme("light", app)

from gui.tools.arp_scan_tool import ArpScanWidget

if os.path.exists(arp_scan.ROSTER_FILE):
    os.remove(arp_scan.ROSTER_FILE)

w = ArpScanWidget()
w.resize(1000, 720)
w.show()
app.processEvents()


class FakeDeviceOps(QWidget):
    """替身设备运维页：鸭子接口 store / refresh_table"""
    def __init__(self):
        super().__init__()
        self.store = ds_mod.DeviceStore()
        self.refresh_count = 0

    def refresh_table(self):
        self.refresh_count += 1


class FakeConsoleViz(QWidget):
    """替身 Console 可视化页：只有 _last_result 属性"""
    _last_result = {"vendor": "h3c", "arp": "192.168.1.9   a4-7b-2a-11-99-ff   20",
                    "mac": "", "lldp": "", "config": "", "parsed": None}


class FakeMain(QWidget):
    def __init__(self):
        super().__init__()
        self.tabs = {"device_ops": FakeDeviceOps(), "console_viz": FakeConsoleViz()}


fake_main = FakeMain()
fake_main.show()
app.processEvents()

w.on_device({"ip": "192.168.10.2", "mac": "10:12:B4:F7:9A:CC", "arp_type": "dynamic",
             "vendor": "", "hostname": "PC-3F", "name": "", "note": "",
             "tags": ["疑似网络设备"]})
w.on_device({"ip": "192.168.10.3", "mac": "A2:63:8D:58:5F:7B", "arp_type": "dynamic",
             "vendor": "", "hostname": "", "name": "", "note": "", "tags": []})
w.on_finished({"ok": True, "stopped": False, "cidr": "192.168.10.0/24",
               "gateway": "192.168.10.1", "devices": [],
               "risks": [], "stats": {"total": 2}})
app.processEvents()

check("_find_main_window 找到 FakeMain", w._find_main_window() is fake_main)

# 4.1 存入设备清单（mock DeviceDialog：自动保存）
import gui.tabs.device_ops_tab as ops_mod
class FakeDialog:
    calls = []
    def __init__(self, pre, parent=None):
        self.pre = pre
        FakeDialog.calls.append(pre)
    def exec_(self):
        return True
    def data(self):
        return dict(self.pre, ssh_port=22, username="admin", password="", )
ops_mod.DeviceDialog = FakeDialog
w._save_to_device_list("192.168.10.2", "10:12:B4:F7:9A:CC")
app.processEvents()
check("存入：预填名称=主机名", FakeDialog.calls and FakeDialog.calls[-1]["name"] == "PC-3F",
      f"{FakeDialog.calls[-1] if FakeDialog.calls else '无调用'}")
check("存入：预填 IP", FakeDialog.calls[-1]["ip"] == "192.168.10.2")
check("存入：备注带 MAC", "10:12:B4:F7:9A:CC" in FakeDialog.calls[-1]["notes"])
store = fake_main.tabs["device_ops"].store
check("设备已入 store", any(d["ip"] == "192.168.10.2" for d in store.list_all()))
check("store 持久化到隔离文件", os.path.exists(ds_mod.DEVICES_FILE))
w._save_to_device_list("192.168.10.2", "10:12:B4:F7:9A:CC")   # 重复 → 拦截（弹提示不重复入库）
check("重复存入被拦截", len(store.list_all()) == 1)
check("重复存入有弹窗提示", any("已在清单中" in t for _k, _t, t in POPUPS), f"{POPUPS}")
check("状态栏成功提示", "已存入设备清单" in w.status_bar.text())

# 4.2 交换机采集导入（FakeConsoleViz._last_result 的 ARP 表）
before_n = w.device_table.rowCount()
w.import_switch_arp()
app.processEvents()
check("交换机导入：新增 1 行", w.device_table.rowCount() == before_n + 1,
      f"{w.device_table.rowCount()} vs {before_n}")
tips = [w.device_table.item(r, 5).text() for r in range(w.device_table.rowCount())]
check("新设备标「交换机视角」", any("交换机视角" in t for t in tips), f"{tips}")
check("导入后状态提示", "已合并交换机 ARP 表" in w.status_bar.text())
# 幂等
w.import_switch_arp()
check("交换机导入幂等", w.device_table.rowCount() == before_n + 1)

# 4.3 同步到 IPAM（GUI 入口；换干净账本走全链路）
ipam_mod.IPAM_FILE = os.path.join(tmp, "ipam2.json")
w.sync_to_ipam()
app.processEvents()
subs3 = ipam_mod.list_subnets()
rec3 = next((s for s in subs3 if s["subnet"] == "192.168.10.0/24"), None)
check("GUI 同步：网段已登记", rec3 is not None, f"{[s['subnet'] for s in subs3]}")
# 注意：交换机导入的 192.168.1.9 属其他网段 → 跨段跳过不入账
check("GUI 同步：IP 已标记（跨段 IP 不入账）",
      rec3 and {u["ip"] for u in rec3["used"]} == {"192.168.10.2", "192.168.10.3"},
      f"{[u['ip'] for u in rec3['used']] if rec3 else None}")
check("状态栏同步统计", "新标记已用" in w.status_bar.text())

# 4.4 入口存在性（不真弹菜单：模态会阻塞；按钮与方法直接断言）
check("右键存入入口方法存在", hasattr(w, "_save_to_device_list"))
check("联动按钮存在", hasattr(w, "ipam_btn") and hasattr(w, "switch_btn"))
check("按钮可点击", w.ipam_btn.isEnabled() and w.switch_btn.isEnabled())

# 截图留档
shot_dir = os.path.join(r"C:\Users\30525\.local\share\TeleAgent\TeleAgent的工作空间\NetOps-toolkit",
                        ".temp", "realtest")
os.makedirs(shot_dir, exist_ok=True)
w.grab().save(os.path.join(shot_dir, "shot_arp_linked.png"))
fake_main.close()
w.close()
app.processEvents()

print()
if fails:
    print(f"=== ARP 联动验证失败 {len(fails)} 项: {fails} ===")
    sys.exit(1)
print("=== ARP 联动验证全部通过 ===")
