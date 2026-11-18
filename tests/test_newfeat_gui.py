# -*- coding: utf-8 -*-
"""GUI 黑盒 · 新功能全链路（模拟用户，纯 UI 操作）
覆盖：工具箱两新工具入口 / IPAM UI / 备份中心 UI（含操作人列/摘要）/ SNMP 设置页 /
设备运维 SNMP 按钮 / 拓扑实时刷新按钮与节点进 CLI 入口
纪律：只点按钮/填输入/读界面；测试数据一律走临时目录注入，测完还原。"""
import io
import os
import sys
import tempfile
import shutil
import time
import getpass

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, ".temp", "realtest")

from PyQt5.QtWidgets import (QApplication, QPushButton, QComboBox, QLineEdit,
                             QTableWidget, QCheckBox, QListWidget, QWidget, QLabel)
from PyQt5.QtGui import QFont

results = []
def case(name, ok, note=""):
    results.append((name, ok, note))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" —— {note}" if note else ""))

def wait_until(cond, timeout_s=60, tick=0.2):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        if cond():
            return True
        app.processEvents()
        time.sleep(tick)
    return False

app = QApplication([])
app.setFont(QFont("Microsoft YaHei UI", 9))

# ---------- 弹窗代答（记录软件弹了什么 = 用户视角） ----------
import gui.dialogs.base as db
popups = []
def _user(parent, kind, title, text, buttons, default_role=None):
    popups.append({"kind": kind, "title": title, "text": text})
    print(f"    💬 [{kind}] {title}: {text[:60].replace(chr(10), ' ')}")
    for label, role in buttons:
        if role in ("accept", "yes"):
            return label
    return buttons[0][0]
db._styled_box = _user
from PyQt5.QtWidgets import QFileDialog, QInputDialog
QFileDialog.exec_ = lambda self, *a, **k: None   # 文件对话框不弹（导出用例时直接验证方法层）

from gui import theme as _theme
_theme.install()
_theme.set_theme("light", app)
from gui.main_window import MainWindow

print("=" * 70)
print("GUI 黑盒 · 新功能全链路（9 项新功能模拟用户验证）")
print("=" * 70)
win = MainWindow()
win.resize(1360, 850)
win.show()
app.processEvents()
titles = [win.tab_widget.tabText(i) for i in range(win.tab_widget.count())]

# =========================== ① 工具箱新工具可见性 ===========================
print("\n[① 工具箱] 菜单打开工具箱，检查 2 个新工具卡片")
mb = win.menuBar()
toolbox_action = None
for m in mb.actions():
    if m.menu():
        for a in m.menu().actions():
            if "工具箱" in a.text():
                toolbox_action = a
assert toolbox_action, "菜单里应有工具箱入口"
case("①-1 菜单工具箱入口存在", toolbox_action is not None)
toolbox_action.trigger()
app.processEvents()
from gui.tools_window import NetworkToolsWindow
tws = [w for w in QApplication.topLevelWidgets() if isinstance(w, NetworkToolsWindow)]
case("①-2 工具箱窗口打开", len(tws) == 1)
tw = tws[0]
case("①-3 工具页 20 个（17 网络 + IPAM + 备份中心 + 首页）", tw.stack.count() == 20,
     f"{tw.stack.count()} 页")
# 卡片名在 QLabel 上（卡片是 QPushButton 包图标/名称 QLabel）
home = tw.stack.widget(0)
home_labels = [l.text() for l in home.findChildren(QLabel) if l.text().strip()]
case("①-4 IPAM 卡片可见", any("IPAM" in t for t in home_labels))
case("①-5 备份中心卡片可见", any("备份中心" in t for t in home_labels))

# =========================== ② IPAM 模拟用户 ===========================
print("\n[② IPAM] 点卡片进入，登记网段→标记→建议")
# 点 IPAM 功能卡（外层按钮可点，名称在其子 QLabel）
ipam_card = None
for b in home.findChildren(QPushButton):
    sub = [l.text() for l in b.findChildren(QLabel)]
    if any("IPAM" in t for t in sub):
        ipam_card = b
        break
case("②-1 找到 IPAM 功能卡片", ipam_card is not None)
if ipam_card:
    ipam_card.click()
    app.processEvents()
    # 工具页外层是 page(QWidget) 包 scroll_wrap(工具实例)——取内层判型
    from PyQt5.QtWidgets import QScrollArea
    _cur = tw.stack.currentWidget()
    _sa = _cur.findChild(QScrollArea)
    ipam_page = _sa.widget() if _sa else _cur
    is_ipam = type(ipam_page).__name__ == "IPAMWidget"
    case("②-2 点击进入 IPAM 工具页", is_ipam, type(ipam_page).__name__)
    # 测试数据隔离：注入临时 IPAM 文件
    import modules.ipam as ipam_mod
    real_file = ipam_mod.IPAM_FILE
    tmpdir = tempfile.mkdtemp(prefix="ipam_gui2_")
    ipam_mod.IPAM_FILE = os.path.join(tmpdir, "ipam.json")
    # 用户操作：登记
    edits = ipam_page.findChildren(QLineEdit)
    for e in edits:
        if "网段" in (e.placeholderText() or ""):
            e.setText("172.20.8.1/24")
        elif "名称" in (e.placeholderText() or ""):
            e.setText("实验楼")
        elif "用途" in (e.placeholderText() or ""):
            e.setText("实验室接入")
    for b in ipam_page.findChildren(QPushButton):
        if b.text() == "登记网段":
            b.click()
            break
    app.processEvents()
    tbl = ipam_page.findChildren(QTableWidget)[0]
    case("②-3 登记网段出现在表格", tbl.rowCount() == 1 and tbl.item(0, 0).text() == "172.20.8.0/24",
         f"{tbl.rowCount()} 行")
    # 建议可用 + 标记
    ops_btns = {}
    for r in range(tbl.rowCount()):
        cw = tbl.cellWidget(r, 4)
        if cw:
            for b in cw.findChildren(QPushButton):
                ops_btns[b.text()] = b
    case("②-4 每行有建议/删除按钮", set(ops_btns) >= {"建议可用", "删除"})
    if "建议可用" in ops_btns:
        ops_btns["建议可用"].click()
        app.processEvents()
        ip_edit = next((e for e in ipam_page.findChildren(QLineEdit)
                        if "IP" in (e.placeholderText() or "")), None)
        case("②-5 建议可用自动填 IP", ip_edit is not None and ip_edit.text().endswith(".2"),
             ip_edit.text() if ip_edit else "无")
        # 补用途点标记
        note_edit = next((e for e in ipam_page.findChildren(QLineEdit)
                          if "用途备注" in (e.placeholderText() or "")), None)
        if note_edit:
            note_edit.setText("AP-实验301")
        mark_btn = next((b for b in ipam_page.findChildren(QPushButton) if b.text() == "标记已用"), None)
        if mark_btn:
            mark_btn.click()
            app.processEvents()
        case("②-6 标记后已用/容量更新", tbl.item(0, 2).text() == "1/254",
             tbl.item(0, 2).text())
        case("②-7 状态提示含建议信息", "建议" in ipam_page.hint.text() or "已标记" in ipam_page.hint.text(),
             ipam_page.hint.text()[:40])
    # 还原
    ipam_mod.IPAM_FILE = real_file
    shutil.rmtree(tmpdir, ignore_errors=True)
win.grab().save(os.path.join(OUT, "shot_newfeat_ipam.png"))
tw.close()
app.processEvents()

# =========================== ③ 备份中心模拟用户 ===========================
print("\n[③ 备份中心] 临时仓库 → 设备聚合/操作人/勾选对比提示")
from gui.tools.backup_center_tool import BackupCenterWidget
import utils.backup_manager as bm
mw = win
bc = BackupCenterWidget()
# 隔离注入（组件读默认目录，模拟用户场景改为注入测试数据）
tmpdir2 = tempfile.mkdtemp(prefix="bc_gui2_")
mgr = bm.ConfigBackupManager(backup_dir=tmpdir2)
mgr.create_backup("sysname X\nvlan 10\n", "JX-Core", "H3C", description="巡检备份", is_auto=True)
mgr.create_backup("sysname X\nvlan 10\nvlan 20\n", "JX-Core", "H3C", description="变更前快照", operator="zhangfc")
bc._mgr = mgr
bc._hist_map = {}
bc._refresh_devices()
bc.show()
app.processEvents()
case("③-1 设备下拉聚合 1 台", bc.device_combo.count() == 1)
i0 = next((i for i in range(bc.device_combo.count())
           if bc.device_combo.itemData(i) == ("JX-Core", "H3C")), -1)
bc.device_combo.setCurrentIndex(i0)
bc._load_device()
app.processEvents()
case("③-2 备份列表 2 份", bc.table.rowCount() == 2)
ops_col = [bc.table.item(r, 3).text() for r in range(2)]
case("③-3 操作人列（最新在上：指定+自动）", ops_col == ["zhangfc", getpass.getuser()], str(ops_col))
git_col = [bc.table.item(r, 6).text() for r in range(2)]
case("③-4 Git 列显示 commit 短哈希（至少最新一版）", any(len(g) >= 7 for g in git_col), str(git_col))
case("③-5 Git 变更链 2 条", bc.git_view.rowCount() == 2, f"{bc.git_view.rowCount()} 条")
# 用户勾选两行 → 提示出现
chks = []
for r in range(2):
    cw = bc.table.cellWidget(r, 0)
    q = cw.findChild(QCheckBox) if cw else None
    if q:
        chks.append(q)
if len(chks) == 2:
    chks[0].setChecked(True)
    app.processEvents()
    case("③-6 勾 1 行提示 1/2", "1/2" in bc.hint.text(), bc.hint.text()[:30])
    chks[1].setChecked(True)
    app.processEvents()
    case("③-7 勾 2 行提示可对比", "2/2" in bc.hint.text(), bc.hint.text()[:40])
# 变更摘要（engine 层产物，UI 弹窗走 compare 路径——这里验证摘要文案生成）
diff_v = mgr.compare_backups(chks and mgr.records[0].id, mgr.records[1].id)
sums = bm.ConfigBackupManager.summarize_diff(diff_v["diff"])
case("③-8 变更摘要生成", "VLAN" in sums, sums)
bc.grab().save(os.path.join(OUT, "shot_newfeat_backup.png"))
bc.close()
shutil.rmtree(tmpdir2, ignore_errors=True)

# =========================== ④ SNMP 设置页 ===========================
print("\n[④ SNMP 设置] 设置→网络 → SNMP 组")
from gui.dialogs.settings_dialog import SettingsDialog
dlg = SettingsDialog()
tabs_names = [dlg.tabs_widget.tabText(i) for i in range(dlg.tabs_widget.count())]
net_idx = tabs_names.index("网络")
dlg.tabs_widget.setCurrentIndex(net_idx)
app.processEvents()
case("④-1 网络页有 SNMP 组输入", hasattr(dlg, "snmp_community_edit") and hasattr(dlg, "snmp_version_combo"))
case("④-2 SNMP 版本选项 v2c/v1", [dlg.snmp_version_combo.itemText(i) for i in range(dlg.snmp_version_combo.count())] == ["v2c", "v1"])
from modules import snmp_collector as sc
case("④-3 pysnmp 状态提示正确（已装）", sc.snmp_available())
# 用户改 community 保存回读
from utils.settings import Settings
backup_snmp = Settings().get("snmp", {}) or {}
dlg.snmp_community_edit.setText("campus-read")
dlg.save_settings()
app.processEvents()
after = Settings().get("snmp", {})
case("④-4 SNMP 配置保存回读", after.get("community") == "campus-read", str(after))
Settings().set("snmp", backup_snmp)   # 还原用户配置

# =========================== ⑤ 设备运维 SNMP 按钮 ===========================
print("\n[⑤ 设备运维] SNMP 巡检按钮与交互")
win.tab_widget.setCurrentIndex(titles.index("设备运维"))
app.processEvents()
ops_tab = win.tabs["device_ops"]
case("⑤-1 SNMP 巡检按钮在", ops_tab.snmp_btn is not None and ops_tab.snmp_btn.isVisible(),
     ops_tab.snmp_btn.text())
popups.clear()
ops_tab.snmp_btn.click()
app.processEvents()
last = popups[-1] if popups else {}
case("⑤-2 空清单友好提示", "清单为空" in last.get("text", "") or "pysnmp" in last.get("text", ""),
     last.get("text", "无弹窗")[:40])

# =========================== ⑥ 拓扑（实时刷新/进CLI入口）===========================
print("\n[⑥ 拓扑] 实时按钮与「进入终端 CLI」")
win.tab_widget.setCurrentIndex(titles.index("网络拓扑"))
app.processEvents()
page = win.topology_page
case("⑥-1 拓扑页有实时刷新按钮", page.live_btn is not None and "实时" in page.live_btn.text())
case("⑥-2 初始状态为关闭", not page.live_btn.isChecked())
# 有 _data 但无 port（手动加过节点的场景）→ 开启应被拦
page._data = {"port": "", "vendor": "H3C", "name": "X"}
popups.clear()
page.live_btn.click()
app.processEvents()
case("⑥-3 无串口记录开启被拦截", not page.live_btn.isChecked() and popups and "采集" in popups[-1]["text"])
# 设备面板按钮集里有「进入终端 CLI」
rows, buttons = page._panel_actions(type("N", (), {"kind": "switch", "meta": {}, "device_name": "SW", "subtitle": ""})())
btn_texts = [t for t, _, _ in buttons]
case("⑥-4 设备面板含「进入终端 CLI」", "进入终端 CLI" in btn_texts, str(btn_texts[:4]))

win.grab().save(os.path.join(OUT, "shot_newfeat_topology.png"))

n_pass = sum(1 for _, ok, _ in results if ok)
print("\n" + "=" * 70)
print(f"新功能 GUI 黑盒: PASS {n_pass} / FAIL {len(results) - n_pass}")
for name, ok, note in results:
    if not ok:
        print(f"  ❌ {name} —— {note}")
win.close(); app.processEvents(); win.deleteLater(); app.processEvents()
with open(os.path.join(OUT, "newfeat_gui_result.json"), "w", encoding="utf-8") as f:
    import json
    json.dump(results, f, ensure_ascii=False, indent=2)
