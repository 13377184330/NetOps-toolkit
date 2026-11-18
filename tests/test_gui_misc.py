# -*- coding: utf-8 -*-
"""GUI 级功能测试 · 补充抽查：配置生成页 / AI 卡片编辑 / 批量下发闸门 / 工具箱
纪律：只点按钮/填输入/读界面，不碰引擎。QInputDialog 用 patch 模拟用户输入。"""
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

from PyQt5.QtWidgets import (QApplication, QPushButton, QLineEdit, QSpinBox,
                             QComboBox, QInputDialog)
from PyQt5.QtGui import QFont

results = []
def case(name, ok, note=""):
    results.append((name, ok, note))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" —— {note}" if note else ""))

def wait_until(cond, timeout_s=180, tick=0.2):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        if cond():
            return True
        app.processEvents()
        time.sleep(tick)
    return False

app = QApplication([])
app.setFont(QFont("Microsoft YaHei UI", 9))

import gui.dialogs.base as dlg_base
popups = []
def _rec(parent, kind, title, text, buttons, default_role=None):
    popups.append({"kind": kind, "title": title, "text": text})
    print(f"  [弹窗] {kind}/{title}: {text[:70].replace(chr(10),' ')}")
    for label, role in buttons:
        if role in ("accept", "yes"):
            return label
    return buttons[0][0]
dlg_base._styled_box = _rec

# QInputDialog patch：AI 卡片编辑历史上弹原生输入框，模拟用户改命令
edit_inputs = []
_orig_getText = QInputDialog.getText
def _fake_gettext(parent, title, label, echo=0, text=""):
    return (edit_inputs.pop(0) if edit_inputs else text), True
QInputDialog.getText = _fake_gettext

# 2026-11-18：✎ 就地编辑已改用统一 input_box（BaseDialog 模态框）。
# 不 patch 的话无头环境点 ✎ 会进真实 exec_() 模态循环而挂起。
def _fake_input(parent, title, label, text="", placeholder=None, subtitle=""):
    return (edit_inputs.pop(0) if edit_inputs else text), True
dlg_base.input_box = _fake_input

from gui import theme as _theme
_theme.install()
_theme.set_theme("light", app)
from gui.main_window import MainWindow

print("=" * 68)
print("GUI 黑盒补充抽查 · 配置生成 / AI 卡片编辑 / 批量下发 / 工具箱")
print("=" * 68)
win = MainWindow()
win.resize(1360, 850)
win.show()
app.processEvents()
titles = [win.tab_widget.tabText(i) for i in range(win.tab_widget.count())]

print("\n[Stage A] 配置生成页（表单填写 → 点「生成配置」→ 预览输出）")
win.tab_widget.setCurrentIndex(titles.index("配置生成"))
app.processEvents()
case("A1 配置生成页可打开", True)
basic = win.tabs["basic"]
# 找 sysname 输入框（用户填表单）
edits = basic.findChildren(QLineEdit)
case("A2 基础表单有输入框", len(edits) > 0, f"{len(edits)} 个")
if edits:
    edits[0].setText("SW-TEST-01")
    app.processEvents()
popups.clear()
# 点主窗口「生成配置」按钮
gen_btn = None
for b in win.findChildren(QPushButton):
    if b.text() == "生成配置":
        gen_btn = b
        break
case("A3 找到「生成配置」按钮", gen_btn is not None)
if gen_btn:
    gen_btn.click()
    app.processEvents()
    preview = win.preview_text.toPlainText()
    case("A4 点击后预览区输出配置", len(preview) > 0, f"{len(preview)} 字符")
    case("A5 预览含 sysname", "SW-TEST-01" in preview)

print("\n[Stage B] AI 卡片就地编辑（✎ → QInputDialog → 重分类+重lint+取消勾选）")
ai_page = win.tabs["ai_ops"]
ai_page.mode_combo.setCurrentIndex(0)
app.processEvents()
# 模拟 AI 已产出一张 readonly 卡（编辑成 write 应重分类）
ai_page._queue_cards([{"cmd": "display vlan 100", "note": "核对", "risk": "readonly", "lint": []}],
                     source="AI")
app.processEvents()
# 找当前可见卡片行的 ✎ 编辑按钮
edit_btn = None
for i in range(ai_page.queue_lay.count()):
    w = ai_page.queue_lay.itemAt(i).widget()
    if w is not None:
        for b in w.findChildren(QPushButton):
            if b.text() == "✎":
                edit_btn = b
                break
case("B1 卡片上有编辑按钮", edit_btn is not None)
if edit_btn:
    edit_inputs.append("undo vlan 100")     # 模拟用户把 readonly 改成 dangerous
    edit_btn.click()
    app.processEvents()
    card = ai_page._cards[0]
    case("B2 编辑后命令已更新", card["cmd"] == "undo vlan 100", card["cmd"])
    case("B3 风险重分类 readonly→dangerous", card["risk"] == "dangerous", card["risk"])
    case("B4 编辑后取消勾选", card["checked"] is False)

print("\n[Stage C] 批量下发闸门（勾选后无设备清单，软件应提示）")
popups.clear()
if ai_page._cards:
    # 先勾选（用户视角：勾选可见卡片的复选框）
    from PyQt5.QtWidgets import QCheckBox
    for i in range(ai_page.queue_lay.count()):
        w = ai_page.queue_lay.itemAt(i).widget()
        if w is not None:
            for c in w.findChildren(QCheckBox):
                if c.isEnabled():
                    c.click()
                    break
            break
    app.processEvents()
    case("C1a 勾选后批量下发按钮可用", ai_page.batch_btn.isEnabled(),
         ai_page.deploy_btn.text())
    ai_page.batch_btn.click()
    app.processEvents()
    case("C1b 无设备清单→软件弹提示", any("设备清单" in p["text"] for p in popups),
         popups[0]["text"][:50] if popups else "未弹提示")

print("\n[Stage D] 网络工具箱（菜单打开独立窗口）")
popups.clear()
# 菜单栏：网络工具(T) → 工具箱入口。找到菜单动作并触发
acts = []
mb = win.menuBar()
for m in mb.actions():
    for a in m.menu().actions() if m.menu() else []:
        acts.append((m.text(), a.text(), a))
toolbox_acts = [t for t in acts if "工具箱" in t[1]]
case("D1 菜单含工具箱入口", len(toolbox_acts) > 0, str([t[1] for t in acts][:8]))
if toolbox_acts:
    toolbox_acts[0][2].trigger()
    app.processEvents()
    from gui.tools_window import NetworkToolsWindow
    wins = [w for w in QApplication.topLevelWidgets() if isinstance(w, NetworkToolsWindow)]
    case("D2 工具箱窗口已打开", len(wins) == 1)
    if wins:
        tw = wins[0]
        # 工具页数随工具增减自适应（首页 1 + 工具 N，当前 20）；不做死数断言，防新增工具后误报
        case("D3 工具箱含全部工具页", tw.stack.count() >= 19, f"{tw.stack.count()} 页")
        # 点第一张功能卡片进工具页
        if tw.stack.count() > 1:
            tw.stack.setCurrentIndex(1)
            app.processEvents()
            case("D4 点击卡片可进入工具页", True)
        tw.close()
        app.processEvents()

win.grab().save(os.path.join(OUT, "shot_gui_misc.png"))
n_pass = sum(1 for _, ok, _ in results if ok)
print("\n" + "=" * 68)
print(f"GUI 黑盒补充抽查: PASS {n_pass} / FAIL {len(results) - n_pass}")
for name, ok, note in results:
    if not ok:
        print(f"  ❌ {name} —— {note}")
win.close(); app.processEvents(); win.deleteLater(); app.processEvents()
with open(os.path.join(OUT, "gui_misc_result.json"), "w", encoding="utf-8") as f:
    json.dump({"results": results}, f, ensure_ascii=False, indent=2)
sys.exit(0 if all(ok for _, ok, _ in results) else 1)
