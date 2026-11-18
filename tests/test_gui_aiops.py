# -*- coding: utf-8 -*-
"""GUI 级功能测试 · AI 运维页（黑盒：只点按钮/填输入/读界面，不碰引擎）
用户纪律：一切操作靠软件——脚本只模拟用户点击与输入，断言全部从 UI 控件状态读取。
弹窗：patch 统一入口 _styled_box，记录软件弹了什么 + 模拟用户按键（不弹真窗防阻塞）。"""
import io
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, ".temp", "realtest")

from PyQt5.QtWidgets import QApplication, QCheckBox, QComboBox
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

results = []
def case(name, ok, note=""):
    results.append((name, ok, note))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" —— {note}" if note else ""))

def wait_until(cond, timeout_s=180, tick=0.2):
    import time
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        if cond():
            return True
        app.processEvents()
        time.sleep(tick)
    return False

app = QApplication([])
app.setFont(QFont("Microsoft YaHei UI", 9))

# ---------- 弹窗脚手架：记录 + 模拟用户按键 ----------
import gui.dialogs.base as dlg_base
popups = []
_orig_styled = dlg_base._styled_box
def _rec_styled(parent, kind, title, text, buttons, default_role=None):
    popups.append({"kind": kind, "title": title, "text": text,
                   "buttons": [b[0] for b in buttons], "default": default_role})
    print(f"  [弹窗] {kind}/{title}: {text[:80]}")
    # 模拟用户：单键框点确认；question 默认点「取消」之外首选按钮语义由按钮序决定
    for label, role in buttons:
        if role in ("accept", "yes"):
            return label
    return buttons[0][0]
dlg_base._styled_box = _rec_styled

from gui import theme as _theme
_theme.install()
_theme.set_theme("light", app)
from gui.main_window import MainWindow

print("=" * 68)
print("GUI 黑盒测试 · AI 运维页（一切操作走界面，真 AI 网关）")
print("=" * 68)
win = MainWindow()
win.resize(1360, 850)
win.show()
app.processEvents()

titles = [win.tab_widget.tabText(i) for i in range(win.tab_widget.count())]
win.tab_widget.setCurrentIndex(titles.index("AI 运维"))
app.processEvents()
ai = win.tabs["ai_ops"]

print("\n[Stage A] 界面基础操作")
case("A1 AI 运维页可打开", "AI 运维" in titles)
case("A2 三模式齐全", ai.mode_combo.count() == 3,
     "/".join(ai.mode_combo.itemText(i) for i in range(ai.mode_combo.count())))
ai.mode_combo.setCurrentIndex(1)
app.processEvents()
case("A3 切诊断分析→placeholder 联动", "厂商" in ai.input_view.placeholderText() or "粘贴" in ai.input_view.placeholderText(),
     ai.input_view.placeholderText().splitlines()[0][:30])
ai.mode_combo.setCurrentIndex(0)
app.processEvents()

ai.scene_combo.setCurrentIndex(2)
ai.scene_combo.activated.emit(2)
app.processEvents()
filled = ai.input_view.toPlainText()
case("A4 场景模板点选填充输入框", "VLAN" in filled, filled[:40])
case("A5 填充后模板复位占位", ai.scene_combo.currentIndex() == 0)

print("\n[Stage B] 生成配置模式（真 AI 流式全链路）")
ai.input_view.setPlainText("创建vlan10 20，把GE1/0/1划入vlan10")
popups.clear()
ai.send_btn.click()
app.processEvents()
case("B1 点击发送→进入忙态", not ai.send_btn.isVisible() and ai.stop_btn.isVisible())
case("B2 状态行提示生成中", "生成中" in ai.status_label.text(), ai.status_label.text())
done = wait_until(lambda: ai.send_btn.isVisible(), timeout_s=240)
case("B3 流式生成完成（按钮恢复）", done)
chat_html = ai.chat_view.toHtml()
n_user = 1 if "创建vlan10" in chat_html else 0
case("B4 用户气泡已渲染", n_user == 1)
case("B5 AI 回复已渲染（含代码块样式）", "preview_bg" in chat_html or "netcfg" in chat_html or "vlan" in chat_html.lower())
cards_n = len(ai._cards)
case("B6 命令卡片入队", cards_n >= 3, f"{cards_n} 张卡片")
if cards_n:
    risks = [c["risk"] for c in ai._cards]
    case("B7 风险分级已标注", set(risks) <= {"readonly", "write", "dangerous"}, str(set(risks)))
    # v4.2 队列标题精简（2026-11-17 用户改动）：GroupBox 标题只留「待确认命令队列 ⚠N」，
    # 总条数/只读数统计挪到筛选行 shown_label（「显示 x/y」）
    queue_label = ai._queue_group.title()
    n_danger = sum(1 for c in ai._cards if c["risk"] == "dangerous")
    if n_danger:
        title_ok = f"⚠{n_danger}" in queue_label
    else:
        title_ok = f"（{cards_n}）" in queue_label
    shown_text = ai.shown_label.text()
    shown_ok = f"共 {cards_n} 条" in shown_text
    case("B8 队列标题统计联动", title_ok and shown_ok,
         f"标题「{queue_label}」（n_danger={n_danger}）· 计数行「{shown_text}」")

print("\n[Stage C] 卡片审阅操作")
if cards_n:
    chks = [c for c in ai.queue_host.findChildren(QCheckBox) if c.isEnabled()]
    case("C1 卡片勾选框可用", len(chks) > 0, f"{len(chks)} 个")
    if chks:
        chks[0].click()
        app.processEvents()
        case("C2 勾选→下发按钮计数联动", ai.deploy_btn.text().startswith("下发所选（"),
             ai.deploy_btn.text())
    ai.select_all_btn.click()
    app.processEvents()
    n_checked = sum(1 for c in ai._cards if c["checked"])
    case("C3 全选（含只读验证命令）", n_checked == len(ai._cards),
         f"{n_checked} 勾选")
    n_ro = sum(1 for c in ai._cards if c["checked"] and c["risk"] == "readonly")
    case("C4 混合批次按钮分档", ai.deploy_btn.text().startswith("执行所选（") if n_ro
         else ai.deploy_btn.text().startswith("下发所选（"),
         ai.deploy_btn.text())
    ai.none_btn.click()
    app.processEvents()
    case("C5 全部取消", not any(c["checked"] for c in ai._cards))

def visible_card_checkboxes():
    """只取 queue_lay 当前卡片行里的勾选框（用户视角的可见卡）——
    deleteLater 的旧卡在 processEvents 下不销毁，findChildren 会混入隐形旧卡"""
    out = []
    for i in range(ai.queue_lay.count()):
        w = ai.queue_lay.itemAt(i).widget()
        if w is not None:
            for c in w.findChildren(QCheckBox):
                if c.isEnabled():
                    out.append(c)
    return out

print("\n[Stage D] 下发闸门（无目标设备，软件应提示）")
popups.clear()
if ai._cards:
    chks = visible_card_checkboxes()
    print(f"  [debug] 卡片 {len(ai._cards)} 张，可见勾选框 {len(chks)} 个，"
          f"deploy_btn enabled={ai.deploy_btn.isEnabled()}")
    if chks:
        chks[0].click()
        app.processEvents()
        print(f"  [debug] 勾选后 deploy_btn enabled={ai.deploy_btn.isEnabled()} "
              f"text={ai.deploy_btn.text()}")
    ai.deploy_btn.click()
    app.processEvents()
    print(f"  [debug] 点击后 popups={len(popups)} 条")
    case("D1 无设备→软件弹提示", any("目标设备" in p["text"] or "设备" in p["text"] for p in popups),
         popups[0]["text"][:60] if popups else "未弹任何提示")
    chks2 = visible_card_checkboxes()
    if chks2:
        chks2[0].click()
        app.processEvents()

print("\n[Stage E] 诊断分析模式（真 AI）")
ai.mode_combo.setCurrentIndex(1)
app.processEvents()
ai.input_view.setPlainText("display interface brief 显示 GE1/0/1 是 up，但接的电脑不通，从配置层面看可能是什么原因？")
popups.clear()
ai.send_btn.click()
app.processEvents()
done2 = wait_until(lambda: ai.send_btn.isVisible(), timeout_s=240)
case("E1 诊断流式完成", done2)
diag_html = ai.chat_view.toHtml()
case("E2 诊断回复渲染", len(diag_html) > len(chat_html), f"新增 {len(diag_html)-len(chat_html)} 字符")

win.grab().save(os.path.join(OUT, "shot_gui_aiops.png"))
n_pass = sum(1 for _, ok, _ in results if ok)
print("\n" + "=" * 68)
print(f"AI 运维页 GUI 黑盒测试: PASS {n_pass} / FAIL {len(results) - n_pass}")
for name, ok, note in results:
    if not ok:
        print(f"  ❌ {name} —— {note}")
win.close(); app.processEvents(); win.deleteLater(); app.processEvents()
with open(os.path.join(OUT, "gui_aiops_result.json"), "w", encoding="utf-8") as f:
    json.dump({"results": results, "popups": popups}, f, ensure_ascii=False, indent=2)
sys.exit(0 if all(ok for _, ok, _ in results) else 1)
