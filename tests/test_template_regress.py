# -*- coding: utf-8 -*-
"""模板与厂商切换回归（今日两个真实缺陷的防复发资产）：
1. 全部页签满足 clear_config 契约（曾因 AI 页缺失致切品牌/加载模板/清空配置抛 AttributeError）
2. 五厂商切换走真实 device_combo 信号链路，无异常
3. 各厂商加载「接入交换机标准配置」回填本厂商模板值（曾因非华为一律误用 H3C 模板致锐捷/迈普/思科错配）
4. 模板对话框列表与加载路径同源（get_vendor_templates）
"""
import json
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

results = []
def case(name, ok, note=""):
    results.append((name, ok, note))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" —— {note}" if note else ""))

app = QApplication([])
app.setFont(QFont("Microsoft YaHei UI", 9))

from gui import theme as _theme
_theme.install()
_theme.set_theme("light", app)
import gui.main_window as mw

# 确认框放行（patch 打桩层，业务代码不变）
mw.question_box = lambda *a, **k: True
mw.info_box = lambda *a, **k: None
mw.warn_box = lambda *a, **k: None

win = mw.MainWindow()

print("=" * 68)
print("模板与厂商切换回归（clear_config 契约 / 五厂商模板回填 / 对话框同源）")
print("=" * 68)

# ---- 1. clear_config 契约：所有页签必须有 ----
missing = [k for k, t in win.tabs.items() if not hasattr(t, "clear_config")]
case("T1 全部页签满足 clear_config 契约", not missing, f"缺失: {missing}" if missing else f"{len(win.tabs)} 个页签")

# ---- 2. 五厂商真实切换（device_combo 信号链路）----
for idx, vendor, nm in [(0, "huawei", "华为"), (1, "h3c", "H3C"), (2, "ruijie", "锐捷"),
                        (3, "maipu", "迈普"), (4, "cisco", "思科")]:
    try:
        win.device_combo.setCurrentIndex(idx)
        app.processEvents()
        case(f"T2.{vendor} 切换到{nm}模式无异常", win.current_device_type == vendor)
    except Exception as e:
        case(f"T2.{vendor} 切换到{nm}模式无异常", False, repr(e))

# ---- 3. 各厂商模板回填本厂商值 ----
for vendor, nm in [("h3c", "H3C"), ("ruijie", "锐捷"), ("maipu", "迈普"), ("cisco", "思科")]:
    tpl = mw.get_vendor_templates(vendor)["接入交换机标准配置"]["config"]["basic"]
    win.device_combo.setCurrentIndex(["huawei", "h3c", "ruijie", "maipu", "cisco"].index(vendor))
    app.processEvents()
    win.load_template("接入交换机标准配置")
    app.processEvents()
    b = win.tabs["basic"]
    got_if, got_lv = b.mgmt_interface.text(), b.privilege_level.value()
    want_if, want_lv = tpl["mgmt_interface"]["interface"], tpl["user"]["level"]
    ok = (got_if == want_if and got_lv == want_lv)
    case(f"T3.{vendor} {nm}模板回填本厂商值", ok,
         f"管理接口 {got_if!r} vs {want_if!r} | 权限 {got_lv} vs {want_lv}" if not ok
         else f"接口 {got_if} 权限 {got_lv}")

# ---- 4. 模板对话框与加载路径同源 ----
from gui.main_window import TemplateDialog
for vendor in ("huawei", "h3c", "ruijie", "maipu", "cisco"):
    dlg = TemplateDialog(vendor)
    names_dlg = [dlg.template_list.item(i).text() for i in range(dlg.template_list.count())]
    names_src = list(mw.get_vendor_templates(vendor).keys())
    case(f"T4.{vendor} 对话框列表与加载源同源", names_dlg == names_src,
         f"{names_dlg[:3]}..." if names_dlg == names_src else f"对话框{names_dlg} vs 源{names_src}")
    dlg.close(); dlg.deleteLater()
    app.processEvents()

# ---- 5. 菜单「应用XX模板」同步主窗口厂商（防语法混搭回归） ----
# 曾缺陷：锐捷模式应用华为模板 → 主窗口仍锐捷 → 生成「hostname + interface Vlanif1」混搭
from gui.dialogs.template_dialog import TemplateManagerDialog
def _fill_exec(self):
    """真模态 exec_ 脚手架：show + 选首项 + 使用模板（emit + accept）"""
    self.show()
    app.processEvents()
    if self.template_list.count() > 0:
        self.template_list.setCurrentRow(0)
        app.processEvents()
        self.use_template()
    return 1
TemplateManagerDialog.exec_ = _fill_exec

win.device_combo.setCurrentIndex(2)   # 先切锐捷
app.processEvents()
win.quick_apply_template("huawei")   # 再应用华为模板
app.processEvents()
b = win.tabs["basic"]
ok = win.current_device_type == "huawei" and b.mgmt_interface.text() == "Vlanif1"
case("T5a 应用华为模板同步主窗口厂商", ok,
     f"厂商={win.current_device_type} 接口={b.mgmt_interface.text()}" if not ok else "厂商=huawei 接口=Vlanif1")

win.quick_apply_template("ruijie")    # 再应用锐捷模板
app.processEvents()
b = win.tabs["basic"]
# 接口值以模板管理器数据源为准（内置锐捷模板为小写 vlan 1），厂商同步是核心断言
ok = win.current_device_type == "ruijie" and b.mgmt_interface.text().lower() == "vlan 1"
case("T5b 应用锐捷模板同步主窗口厂商", ok,
     f"厂商={win.current_device_type} 接口={b.mgmt_interface.text()}" if not ok else f"厂商=ruijie 接口={b.mgmt_interface.text()}")

n_pass = sum(1 for _, ok, _ in results if ok)
print("\n" + "=" * 68)
print(f"模板与厂商切换回归: PASS {n_pass} / FAIL {len(results) - n_pass}")
for name, ok, note in results:
    if not ok:
        print(f"  ❌ {name} —— {note}")
win.close(); app.processEvents(); win.deleteLater(); app.processEvents()
os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT, "template_regress_result.json"), "w", encoding="utf-8") as f:
    json.dump({"results": results}, f, ensure_ascii=False, indent=2)
sys.exit(0 if all(ok for _, ok, _ in results) else 1)
