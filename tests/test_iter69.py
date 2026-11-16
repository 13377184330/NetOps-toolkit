# -*- coding: utf-8 -*-
"""迭代 6-9 综合验证：SNMP 引擎 / 操作人 / 变更摘要 / SNMP 设置页"""
import io
import json
import os
import sys
import tempfile
import shutil

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
sys.path.insert(0, r"C:\Users\30525\.local\share\TeleAgent\TeleAgent的工作空间\NetOps-toolkit")

from PyQt5.QtWidgets import QApplication
app = QApplication([])
from gui import theme as _theme
_theme.install()
_theme.set_theme("light", app)
import gui.dialogs.base as db
db._styled_box = lambda p, k, t, x, b, d=None: b[0][0]

# ---------- ⑥ SNMP 引擎（无真设备→降级路径验证）----------
from modules import snmp_collector as sc
assert sc.snmp_available(), "pysnmp 应已安装"
r = sc.probe("192.0.2.1", timeout=0.5)   # TEST-NET 地址（RFC5737，不可能有设备）
assert r["ok"] is False and "无响应" in r["error"], r
print("PASS 6a: SNMP 引擎导入+无设备优雅失败")
ifs = sc.collect_interfaces("192.0.2.1", timeout=0.5)
assert ifs["ok"] is False
cfg = sc.get_config()
assert cfg["community"] and cfg["version"] in (1, 2)
print(f"PASS 6b: 配置读取 OK（community={cfg['community']}, v{cfg['version']}）")

# ---------- ⑦ SNMP 设置页 + 设备运维按钮 ----------
from gui.dialogs.settings_dialog import SettingsDialog
dlg = SettingsDialog()
titles = [dlg.tabs_widget.tabText(i) for i in range(dlg.tabs_widget.count())]
assert "网络" in titles
assert hasattr(dlg, "snmp_community_edit") and hasattr(dlg, "snmp_version_combo")
dlg.snmp_community_edit.setText("school-ro")
dlg.snmp_version_combo.setCurrentIndex(0)
dlg.save_settings()
from utils.settings import Settings
s2 = Settings().get("snmp", {})
assert s2.get("community") == "school-ro" and s2.get("version") == 2, s2
print("PASS 7a: 设置页 SNMP 组保存回读 OK")
# 还原默认，别污染用户设置
Settings().set("snmp", {"community": "public", "version": 2})

from gui.main_window import MainWindow
win = MainWindow()
win.show()
app.processEvents()
titles = [win.tab_widget.tabText(i) for i in range(win.tab_widget.count())]
win.tab_widget.setCurrentIndex(titles.index("设备运维"))
app.processEvents()
ops = win.tabs["device_ops"]
assert ops.snmp_btn is not None and "SNMP" in ops.snmp_btn.text()
print("PASS 7b: 设备运维页 SNMP 巡检按钮存在")
# 空清单场景（真实 devices.json 为空——之前看过 devices.json 是 2 字节）
popup_txt = []
db._styled_box = lambda p, k, t, x, b, d=None: (popup_txt.append(x), b[0][0])[1]
ops.snmp_survey()
app.processEvents()
assert popup_txt and ("pysnmp" in popup_txt[0] or "设备清单为空" in popup_txt[0]), popup_txt
print(f"PASS 7c: SNMP 巡检空清单提示正确（{popup_txt[0][:30]}）")

# ---------- ⑧ 操作人 ----------
tmp = tempfile.mkdtemp(prefix="op8_")
from utils.backup_manager import ConfigBackupManager
mgr = ConfigBackupManager(backup_dir=tmp)
mgr.create_backup("sysname A\n", "SW-01", "H3C")
rec = mgr.records[-1]
assert rec.operator, f"操作人应自动填 Windows 用户名，实际 {rec.operator!r}"
print(f"PASS 8a: 备份记录自动记操作人（{rec.operator}）")
mgr.create_backup("sysname A\nx\n", "SW-01", "H3C", operator="张三")
assert mgr.records[-1].operator == "张三"
hist = mgr.git_history("SW-01", "H3C")
assert any("张三" in h["message"] for h in hist), "git commit 应含操作人"
print("PASS 8b: 指定操作人 + git commit 信息含操作人")

# 老记录兼容（无 operator 字段的 json 可加载）
old_json = os.path.join(tmp, "old", "backup_records.json")
os.makedirs(os.path.dirname(old_json), exist_ok=True)
with open(old_json, "w", encoding="utf-8") as f:
    json.dump([{"id": "1", "filename": "x.cfg", "device_name": "D", "device_type": "H",
                "ip_address": "", "backup_time": "2026-01-01 00:00:00", "file_size": 1,
                "md5_hash": "", "description": "", "is_auto": False, "tags": []}], f)
mgr2 = ConfigBackupManager(backup_dir=os.path.dirname(old_json))
assert mgr2.records[0].operator == ""      # 默认空，不崩
print("PASS 8c: 老记录（无 operator 字段）兼容加载")

# ---------- ⑨ 变更摘要 ----------
from utils.backup_manager import ConfigBackupManager as M
diff = """--- a
+++ b
@@ 
 sysname SW-01
-vlan 10
+vlan 10
+vlan 20
@@ 
 interface GigabitEthernet1/0/1
- port link-type trunk
+ port link-type access
+ port access vlan 20
+ ip route-static 0.0.0.0 0 10.1.1.1
"""
s = M.summarize_diff(diff)
print(f"  摘要输出: {s}")
assert "VLAN" in s and "端口" in s and "路由" in s, s
assert "涉及 1 个端口" in s
print("PASS 9: 变更摘要（端口数/VLAN/路由 域统计 + 增删行数）")

# ---------- 备份中心操作人列 ----------
from gui.tools.backup_center_tool import BackupCenterWidget
w = BackupCenterWidget()
w._mgr = mgr
w._hist_map = {}
w._refresh_devices()
i01 = next((i for i in range(w.device_combo.count())
            if w.device_combo.itemData(i) == ("SW-01", "H3C")), -1)
w.device_combo.setCurrentIndex(i01)
w._load_device()
app.processEvents()
assert w.table.rowCount() == 2
ops_col_seen = [w.table.item(r, 3).text() for r in range(w.table.rowCount())]
assert any(t == "张三" for t in ops_col_seen), ops_col_seen
assert all(t != "" for t in ops_col_seen)
print(f"PASS 10: 备份中心操作人列（{ops_col_seen}）")

win.close(); app.processEvents(); win.deleteLater(); app.processEvents()
shutil.rmtree(tmp, ignore_errors=True)
print("\n=== 迭代 6-9 综合验证全部通过 ===")
