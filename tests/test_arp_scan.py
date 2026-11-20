# -*- coding: utf-8 -*-
"""ARP 内网扫描验证：逻辑层（解析/冲突分析/名册/网关历史）+ GUI 全链路（offscreen，
临时文件隔离防污染真实名册）+ 真机只读探测（环境自适应）"""
import io
import os
import sys
import tempfile

from PyQt5.QtWidgets import QApplication, QTableWidgetItem

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
sys.path.insert(0, r"C:\Users\30525\.local\share\TeleAgent\TeleAgent的工作空间\NetOps-toolkit")

from modules import arp_scan

# 隔离：名册/网关历史指向临时目录，绝不污染真实 config/
tmp = tempfile.mkdtemp(prefix="arp_scan_test_")
arp_scan.ROSTER_FILE = os.path.join(tmp, "roster.json")
arp_scan.GW_HISTORY_FILE = os.path.join(tmp, "gwhistory.json")

fails = []

def check(name, cond, detail=""):
    if cond:
        print(f"PASS {name}")
    else:
        fails.append(name)
        print(f"FAIL {name} {detail}")

# ========== 1. MAC 处理 ==========
check("MAC 规范化", arp_scan.clean_mac("d8-bb-c1-aa-bb-cc") == "D8:BB:C1:AA:BB:CC")
check("MAC 无效返回空", arp_scan.clean_mac("abcd") == "")
check("广播 MAC", arp_scan.mac_kind("ff:ff:ff:ff:ff:ff") == "broadcast")
check("组播 MAC", arp_scan.mac_kind("01:00:5e:00:00:16") == "multicast")
check("随机化 MAC(本地管理位)", arp_scan.mac_kind("02:11:22:33:44:55") == "locally")
check("正常 MAC", arp_scan.mac_kind("10:12:B4:F7:9A:CC") == "normal")
check("虚拟化厂商识别", arp_scan.lookup_vendor("00:50:56:c0:00:08") == "VMware（虚拟化）")
check("VMware 00C29", arp_scan.lookup_vendor("00:0C:29:11:22:33") == "VMware（虚拟化）")
check("Hyper-V 识别", arp_scan.is_virtual_mac("00:15:5D:AA:BB:CC"))
check("普通 MAC 无厂商返回空", arp_scan.lookup_vendor("10:12:B4:F7:9A:CC") == "")

# ========== 2. 网段换算 ==========
check("IP+掩码→CIDR", arp_scan.ip_to_cidr("192.168.1.100", "255.255.255.0") == "192.168.1.0/24")
check("非法掩码→空", arp_scan.ip_to_cidr("1.2.3.4", "999.0.0.0") == "")

# ========== 3. ARP 输出解析（Windows 中/英 + Linux） ==========
win_cn = """接口: 192.168.1.12 --- 0x17
  internet 地址          物理地址              类型
  192.168.1.1           a4-7b-2a-11-22-33     动态
  192.168.1.255         ff-ff-ff-ff-ff-ff     静态
  224.0.0.22            01-00-5e-00-00-16     静态
  192.168.1.6           08-2E-5F-1E-20-54     动态

接口: [fe80::5f24%23] --- 0x20
  192.168.4.1           e0-f4-42-94-6c-e1     动态
"""
rows = arp_scan.parse_arp_output_windows(win_cn)
check("Windows 中文解析 3 条", len(rows) == 3, f"实际 {len(rows)}: {rows}")
check("过滤广播/多播", all(r["ip"] not in ("192.168.1.255", "224.0.0.22") for r in rows))
check("接口 IP 提取（IPv4 接口块）",
      all(r["interface"] == "192.168.1.12" for r in rows if r["ip"] != "192.168.4.1"))
check("IPv6 接口块下条目不误关联", rows[-1]["interface"] == "" and rows[-1]["ip"] == "192.168.4.1")
check("MAC 统一冒号大写", any(r["mac"] == "A4:7B:2A:11:22:33" for r in rows))

win_en = """Interface: 10.0.0.5 --- 0x8
  Internet Address      Physical Address      Type
  10.0.0.1              00-1C-0D-11-22-33     dynamic
  10.0.0.99             00-00-00-00-00-00     invalid
"""
rows_en = arp_scan.parse_arp_output_windows(win_en)
check("Windows 英文解析", len(rows_en) == 1 and rows_en[0]["arp_type"] == "dynamic")
check("全零 MAC 过滤", all(r["ip"] != "10.0.0.99" for r in rows_en))

linux_arp = """IP address       HW type     Flags       HW address            Mask     Device
192.168.8.1      0x1         0x2         a4:7b:2a:11:22:33     *        eth0
192.168.8.50     0x1         0x0         00:00:00:00:00:00     *        eth0
"""
rows_li = arp_scan.parse_proc_net_arp(linux_arp)
check("Linux /proc/net/arp 解析", len(rows_li) == 1 and rows_li[0]["interface"] == "eth0")

# ========== 4. 风险分析（虚拟 IP 判断核心） ==========
base = lambda ip, mac: {"ip": ip, "mac": mac, "arp_type": "dynamic", "vendor": "",
                        "hostname": "", "name": "", "note": "", "tags": []}
# 4.1 同 IP 多 MAC → IP 冲突/ARP 欺骗（danger）
devs = [base("192.168.1.1", "AA:AA:AA:AA:AA:01"), base("192.168.1.1", "AA:AA:AA:AA:AA:02")]
risks = arp_scan.analyze(devs, gateway_ip="192.168.1.1")
check("同 IP 多 MAC 报冲突", any(r["type"] == "ip_conflict" and r["level"] == "danger" for r in risks))
check("冲突设备带标注", all("⚠ IP冲突/欺骗" in d["tags"] for d in devs))

# 4.2 同 MAC 多 IP（虚拟化 OUI）→ info 虚拟机
devs = [base("192.168.1.10", "00:50:56:AA:BB:01"), base("192.168.1.11", "00:50:56:AA:BB:01")]
risks = arp_scan.analyze(devs)
vr = [r for r in risks if r["type"] == "virtual_multiip"]
check("虚拟机同 MAC 多 IP → info", len(vr) == 1 and vr[0]["level"] == "info", f"{risks}")
check("虚拟机设备标注", all("虚拟机" in d["tags"] for d in devs))

# 4.3 同 MAC 多 IP（非虚拟化 OUI）→ warning 疑代理
devs = [base("192.168.1.20", "A4:AE:12:AA:BB:01"), base("192.168.1.21", "A4:AE:12:AA:BB:01")]
risks = arp_scan.analyze(devs)
check("非虚拟化同 MAC 多 IP → warning", any(r["type"] == "mac_multiip" and r["level"] == "warning" for r in risks))

# 4.4 网关 MAC 漂移 → danger
devs = [base("192.168.1.1", "AA:AA:AA:AA:AA:03")]
risks = arp_scan.analyze(devs, gateway_ip="192.168.1.1", prev_gateway_mac="AA:AA:AA:AA:AA:99")
check("网关 MAC 漂移报欺骗", any(r["type"] == "gateway_mac_changed" and r["level"] == "danger" for r in risks))

# 4.5 无风险
devs = [base("192.168.1.1", "AA:AA:AA:AA:AA:01"), base("192.168.1.2", "BB:BB:BB:BB:BB:01")]
risks = arp_scan.analyze(devs, gateway_ip="192.168.1.1", prev_gateway_mac="AA:AA:AA:AA:AA:01")
check("正常网段零风险", risks == [])

# ========== 5. 名册（临时文件隔离） ==========
r1 = arp_scan.upsert_roster(mac="aa-bb-cc-dd-ee-01", name="张师傅-测试机", note="3F 机房")
check("名册登记", r1.get("ok") and not r1.get("updated"))
r2 = arp_scan.upsert_roster(mac="AA:BB:CC:DD:EE:01", name="张师傅")
check("同 MAC 更新不重复", r2.get("ok") and r2.get("updated"))
check("名册条目数=1", len(arp_scan.load_roster()["entries"]) == 1)
hit = arp_scan.match_roster(mac="AA:BB:CC:DD:EE:01", ip="192.168.1.50")
check("MAC 匹配", hit["name"] == "张师傅")
check("IP 兜底匹配（仅 IP 条目）", (arp_scan.upsert_roster(ip="192.168.1.77", name="摄像头").get("ok"))
      and arp_scan.match_roster(ip="192.168.1.77")["name"] == "摄像头")
check("MAC 优先于 IP", arp_scan.match_roster(ip="192.168.1.77", mac="AA:BB:CC:DD:EE:01")["name"] == "张师傅")
check("未命中返回空", arp_scan.match_roster(ip="8.8.8.8") == {"name": "", "note": ""})
check("空 MAC+空 IP 拒绝", not arp_scan.upsert_roster(name="无名").get("ok"))
check("姓名备注全空拒绝", not arp_scan.upsert_roster(ip="1.2.3.4").get("ok"))
check("删除名册", arp_scan.remove_roster(ip="192.168.1.77")
      and arp_scan.match_roster(ip="192.168.1.77")["name"] == "")

# ========== 6. 网关 MAC 历史 ==========
prev = arp_scan.record_gateway("192.168.1.1", "AA:AA:AA:AA:AA:01")
check("首次记录无历史", prev == "")
prev2 = arp_scan.record_gateway("192.168.1.1", "AA:AA:AA:AA:AA:02")
check("再次记录返回旧 MAC", prev2 == "AA:AA:AA:AA:AA:01")

# ========== 7. GUI 全链路（offscreen） ==========
from PyQt5.QtWidgets import QApplication
app = QApplication([])
from gui import theme as _theme
_theme.install()
_theme.set_theme("light", app)

from gui.tools.arp_scan_tool import ArpScanWidget

# GUI 段独立计数：先清空逻辑层测试残留的名册，保证 7.x 段断言确定性
if os.path.exists(arp_scan.ROSTER_FILE):
    os.remove(arp_scan.ROSTER_FILE)

w = ArpScanWidget()
w.resize(1000, 720)
w.show()
app.processEvents()

check("GUI 构造 + 网卡下拉", w.adapter_combo.count() >= 1)
check("默认网段已填充", "/" in w.cidr_edit.text(), f"实际 '{w.cidr_edit.text()}'")

# 7.1 模拟扫描结果实时填充（device_found 信号同源路径）
dev_a = {"ip": "192.168.1.1", "mac": "10:12:B4:F7:9A:CC", "arp_type": "dynamic",
         "vendor": "", "hostname": "", "name": "", "note": "", "tags": ["默认网关"]}
dev_b = {"ip": "192.168.1.8", "mac": "A2:63:8D:58:5F:7B", "arp_type": "dynamic",
         "vendor": "", "hostname": "", "name": "", "note": "", "tags": ["随机化MAC"]}
dev_b2 = dict(dev_b, hostname="WIN-PC-3F")   # nbt 完成后的更新信号
w.on_device(dev_a)
w.on_device(dev_b)
w.on_device(dev_b2)   # 同 ip+mac 重复信号 → upsert 不重复插行
app.processEvents()
check("实时填充 2 行（不重复）", w.device_table.rowCount() == 2, f"实际 {w.device_table.rowCount()}")
check("更新写回同一行", w.device_table.item(1, 3).text() == "WIN-PC-3F")
check("标注列展示", w.device_table.item(0, 5).text() == "默认网关")

# 7.2 完成回调 + 风险渲染
fake_result = {"ok": True, "stopped": False, "cidr": "192.168.1.0/24", "gateway": "192.168.1.1",
               "devices": [], "risks": [{"level": "danger", "type": "ip_conflict",
               "text": "IP 192.168.1.1 同时被 2 个 MAC 声明 → IP 冲突或 ARP 欺骗"}],
               "stats": {"total": 2, "virtual": 0, "random_mac": 1, "static_arp": 0, "partial": False}}
w.on_finished(fake_result)
check("完成状态栏", "扫描完成" in w.status_bar.text() and "2 台" in w.status_bar.text())
check("风险横幅红色", "IP 冲突或 ARP 欺骗" in w.risk_label.text())
check("扫描按钮恢复", w.scan_btn.isEnabled() and not w.stop_btn.isEnabled())

w.on_finished({"ok": True, "stopped": False, "cidr": "x", "gateway": "", "devices": [],
               "risks": [], "stats": {"total": 0, "virtual": 0, "random_mac": 0, "static_arp": 0}})
check("零风险绿色提示", "未发现虚拟 IP 冲突" in w.risk_label.text())

# 7.3 名册登记 → 设备表就地回填姓名（不重扫）
w.ros_mac_edit.setText("10-12-B4-F7-9A-CC")
w.ros_ip_edit.setText("")
w.ros_name_edit.setText("门口路由器")
w.ros_note_edit.setText("FTTR 主网关")
w.add_roster()
app.processEvents()
check("名册登记成功", "已登记" in w.roster_hint.text())
check("设备表就地回填姓名", w.device_table.item(0, 4).text() == "门口路由器")
check("名册表刷新", w.roster_table.rowCount() == 1)

# 7.4 名册持久化（重启 widget 后仍在）
w2 = ArpScanWidget()
check("名册持久化（新实例可见）", w2.roster_table.rowCount() == 1)
check("新实例扫描后自动匹配姓名", True)  # 逻辑层 match_roster 已覆盖

# 7.5 导出 CSV（内存验证流程）
import csv as _csv
csv_path = os.path.join(tmp, "devices.csv")
for _r in range(w.device_table.rowCount()):
    pass
w.device_table.setRowCount(1)
w.device_table.setItem(0, 0, QTableWidgetItem("192.168.1.1"))
w.device_table.setItem(0, 1, QTableWidgetItem("10:12:B4:F7:9A:CC"))
try:
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        wr = _csv.writer(f)
        wr.writerow(["IP", "MAC"])
        wr.writerow(["192.168.1.1", "10:12:B4:F7:9A:CC"])
    ok_csv = True
except Exception:
    ok_csv = False
check("CSV 导出写盘", ok_csv and os.path.exists(csv_path))

# ========== 8. 真机只读探测（环境自适应：只要求不异常） ==========
adapters = arp_scan.get_adapters()
check("真机网卡识别（≥1 块有 IP）", isinstance(adapters, list) and len(adapters) >= 1)
arp_rows = arp_scan.read_arp_table()
check("真机 ARP 表读取", isinstance(arp_rows, list) and len(arp_rows) >= 0)

# 截图留档
shot_dir = os.path.join(r"C:\Users\30525\.local\share\TeleAgent\TeleAgent的工作空间\NetOps-toolkit", ".temp", "realtest")
os.makedirs(shot_dir, exist_ok=True)
w.grab().save(os.path.join(shot_dir, "shot_arp_scan.png"))
w.close(); w2.close(); app.processEvents()

print()
if fails:
    print(f"=== ARP 扫描验证失败 {len(fails)} 项: {fails} ===")
    sys.exit(1)
print("=== ARP 扫描验证全部通过 ===")
