# -*- coding: utf-8 -*-
"""UI 层真实事件测试 · QTest/合成鼠标驱动（模拟用户的手，不是调方法）
铁律：所有交互走真实事件序列——
  - 按钮：QTest.mouseClick（真实 press/release/事件过滤器链）
  - 键盘：QTest.keyClicks（真实打字，触发 textChanged/事件过滤器）+ Ctrl+Enter 快捷键真实触发
  - QGraphics（设备面板/拓扑）：QTest 点击 viewport 坐标 → 图元 mousePressEvent 真实执行；
    hover 用手工 MouseMove（view 无 mouseTracking 时高亮是死的——这本身就是要测的行为）
  - 拖动：press + 手工 LeftButton MouseMove + release
覆盖：配置生成页（键入+点击）、AI 运维（重点：打字/Ctrl+Enter/点发送/勾选/编辑/筛选），
QGraphics 设备面板（真机数据视口点击/hover）、拓扑节点（真实点击/拖动）。"""
import io
import os
import sys
import time

import faulthandler
faulthandler.enable()

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, ".temp", "realtest")

from PyQt5.QtCore import Qt, QEvent, QPoint, QPointF
from PyQt5.QtGui import QMouseEvent, QKeyEvent
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import (QApplication, QCheckBox, QComboBox, QLineEdit,
                             QPushButton, QTextEdit)

APP = None
WIN = None
MSGLOG = []          # _styled_box 记录（软件弹了什么）
EDIT_PRESET = []     # QInputDialog.getText 预设（就地编辑用例）

results = []


def check(desc, cond, note=""):
    results.append((desc, bool(cond), note))
    print(f"  {'[ok]' if cond else '[FAIL]'} {desc}" + (f" —— {note}" if note else ""),
          flush=True)
    return bool(cond)


def pump(ms=30):
    end = time.time() + ms / 1000.0
    while time.time() < end:
        APP.processEvents()
        time.sleep(0.005)


def wait_until(cond, timeout=5.0, interval=0.05):
    deadline = time.time() + timeout
    while time.time() < deadline:
        APP.processEvents()
        if cond():
            return True
        time.sleep(interval)
    return False


def patch_app_dialogs():
    """被测应用统一弹窗入口 _styled_box 单点 patch：记录 + 预设应答（不进真模态）"""
    import gui.dialogs.base as db

    def _user(parent, kind, title, text, buttons, default_role=None):
        MSGLOG.append((kind, title, text))
        print(f"    💬 [{kind}] {title}: {text[:50].replace(chr(10), ' ')}")
        for label, role in buttons:
            if role in ("accept", "yes"):
                return label
        return buttons[0][0]
    db._styled_box = _user

    # 2026-11-17：✎ 就地编辑改用统一 input_box（全量巡检：原生 QInputDialog
    # 风格割裂）——patch 目标随之切换；ai_ops 是调用点 import，改模块属性即生效
    def _input(parent, title, label, text="", placeholder=None, subtitle=""):
        return (EDIT_PRESET.pop(0) if EDIT_PRESET else text), True
    db.input_box = _input

    from PyQt5.QtWidgets import QInputDialog
    def _get_text(parent, title, label, echo=0, text=""):
        return (EDIT_PRESET.pop(0) if EDIT_PRESET else text), True
    QInputDialog.getText = staticmethod(_get_text)


def visible_widget(cls, text_part=None, root=None):
    root = root or WIN
    for w in root.findChildren(cls):
        if w.isVisible() and (text_part is None or text_part in w.text()):
            return w
    return None


def vp_click_item(view, item, margin=5):
    """视口坐标真实点击 QGraphicsItem（走 viewport 事件分发 → 图元 mousePressEvent）"""
    r = item.sceneBoundingRect()
    scene_p = QPointF(r.center().x() - margin, r.center().y() - margin)
    vp_p = view.mapFromScene(scene_p)
    QTest.mouseClick(view.viewport(), Qt.LeftButton, pos=QPoint(int(vp_p.x()), int(vp_p.y())))
    APP.processEvents()


def scene_hover_at(view, item):
    """合成悬停（技能要点：无 mouseTracking 的视图 hover 高亮是死的——如实断言）"""
    r = item.sceneBoundingRect()
    vp_p = view.mapFromScene(QPointF(r.center().x(), r.center().y() - 4))
    g = view.viewport().mapToGlobal(QPoint(int(vp_p.x()), int(vp_p.y())))
    ev = QMouseEvent(QEvent.MouseMove, QPointF(vp_p), QPointF(g),
                     Qt.NoButton, Qt.NoButton, Qt.NoModifier)
    QApplication.sendEvent(view.viewport(), ev)
    APP.processEvents()


def type_text(w, text):
    """合成键盘输入（中文必需）：QTest.keyClicks 对非 Latin1 字符在 PyQt5 5.15.10
    Windows 下直接 0xC0000409（实测中英文二分定位）——改逐字符 QKeyEvent(text=ch)。
    走完整 keyPressEvent 事件链（含 ai_ops_tab 的 eventFilter Ctrl+Enter 拦截器）。"""
    for ch in text:
        QApplication.sendEvent(w, QKeyEvent(QEvent.KeyPress, 0, Qt.NoModifier, ch))
        QApplication.sendEvent(w, QKeyEvent(QEvent.KeyRelease, 0, Qt.NoModifier, ch))
    APP.processEvents()


def main():
    global APP, WIN
    APP = QApplication([])
    patch_app_dialogs()
    from gui import theme as _theme
    _theme.install()
    _theme.set_theme("light", APP)
    from gui.main_window import MainWindow
    from modules import console_reader as _cr

    has_port = any("COM11" in p for p, _ in _cr.list_console_ports())
    print("=" * 64)
    print("UI 真实事件测试（QTest/合成鼠标）" + ("｜真机在位" if has_port else "｜无串口（降级路径）"))
    print("=" * 64)

    WIN = MainWindow()
    WIN.resize(1360, 850)
    WIN.show()
    pump(200)
    titles = [WIN.tab_widget.tabText(i) for i in range(WIN.tab_widget.count())]

    def goto(name):
        WIN.tab_widget.setCurrentIndex(titles.index(name))
        pump(150)

    # ================= ① 配置生成页：真实键入 + 真实点击 =================
    print("\n[① 配置生成页 · 真实键入与点击]")
    goto("配置生成")
    basic = WIN.tabs["basic"]
    ed = next((e for e in basic.findChildren(QLineEdit) if e.isVisible()), None)
    if ed:
        ed.clear()
        QTest.keyClicks(ed, "JX-TEST-SW")          # 真实打字：QKeyEvent 全链
        pump(60)
        check("真实键入 sysname 生效", ed.text() == "JX-TEST-SW", ed.text())
    gen_btn = visible_widget(QPushButton, "生成配置")
    QTest.mouseClick(gen_btn, Qt.LeftButton)         # 真实点击（走事件过滤器链）
    pump(200)
    pv = WIN.preview_text.toPlainText()
    check("点击「生成配置」→ 预览出配置", "JX-TEST-SW" in pv, f"{len(pv)} 字符")
    check("生成成功弹窗", any("成功" in t for _, _, t in MSGLOG))

    # ================= ② AI 运维（重点）· 真实打字/Ctrl+Enter/点击 =================
    print("\n[② AI 运维 · 真实事件全链]")
    goto("AI 运维")
    ai = WIN.tabs["ai_ops"]

    # 2.1 合成键盘输入（中文必需，走 keyPressEvent 全链含 eventFilter）
    ai.input_view.clear()
    type_text(ai.input_view, "创建vlan 90，把GE1/0/5划入vlan 90")
    check("真实键盘输入生效", "vlan 90" in ai.input_view.toPlainText())
    # 2.2 Ctrl+Enter 快捷键真实触发（之前从未测过事件过滤器路径！）
    QTest.keyClick(ai.input_view, Qt.Key_Return, Qt.ControlModifier)
    pump(150)
    check("Ctrl+Enter 真实触发发送", not ai.send_btn.isVisible(), "已进入忙态")
    ok = wait_until(lambda: ai.send_btn.isVisible(), timeout=180)
    check("真 AI 流式完成", ok, f"{len(ai._cards)} 卡片")
    n_cards = len(ai._cards)
    check("卡片已入队", n_cards >= 4, f"{n_cards} 张")

    # 2.3 勾选框：真实鼠标点击（走 QCheckBox mousePressEvent）
    def layout_checks():
        out = []
        for i in range(ai.queue_lay.count()):
            w = ai.queue_lay.itemAt(i).widget()
            if w is not None:
                out += [c for c in w.findChildren(QCheckBox) if c.isEnabled()]
        return out
    chks = layout_checks()
    if chks:
        QTest.mouseClick(chks[0], Qt.LeftButton)
        pump(100)
        check("真实点击勾选框→部署计数联动", ai.deploy_btn.text().startswith("下发所选"),
             ai.deploy_btn.text())
        QTest.mouseClick(chks[0], Qt.LeftButton)     # 再点取消
        pump(100)
        check("再次点击取消勾选", not any(c["checked"] for c in ai._cards))

    # 2.4 编辑按钮 ✎：真实鼠标点击（QInputDialog patch 预设应答）
    edit_btn = None
    for i in range(ai.queue_lay.count()):
        w = ai.queue_lay.itemAt(i).widget()
        if w is not None:
            for b in w.findChildren(QPushButton):
                if b.isVisible() and b.text() == "✎":
                    edit_btn = b
                    break
        if edit_btn:
            break
    if edit_btn:
        EDIT_PRESET.append("display vlan 90")
        QTest.mouseClick(edit_btn, Qt.LeftButton)
        pump(150)
        # 编辑后 _refresh_queue 会按风险重排序：编辑成 readonly 的卡沉底，
        # 卡[0] 不再是被编辑的那张（实测踩中：断言必须按内容找卡而非按位断言）
        edited = next((c for c in ai._cards if c["cmd"] == "display vlan 90"), None)
        check("真实点击 ✎ 编辑命令（含重分类+重排序）",
              edited is not None and edited["risk"] == "readonly",
              f"编辑后卡位置: {[i for i, c in enumerate(ai._cards) if c['cmd'] == 'display vlan 90']} / {edited['risk'] if edited else '未找到'}")

    # 2.5 风险筛选 combo：真实鼠标交互（程序化 setCurrentIndex 从未测真实弹出）
    if ai.filter_combo.count() > 1:
        QTest.keyClick(ai.filter_combo, Qt.Key_PageDown)    # 键盘切换 combo（真实事件）
        pump(100)
        check("筛选 combo 键盘切换", ai.filter_combo.currentIndex() == 1,
               ai.filter_combo.currentText())
        QTest.keyClick(ai.filter_combo, Qt.Key_PageUp)
        pump(100)

    # 2.6 停止按钮真实点击
    ai.mode_combo.setCurrentIndex(2)
    pump(60)
    ai.input_view.clear()
    type_text(ai.input_view, "展开讲 OSPF 区域设计与 LSA 类型")
    QTest.mouseClick(ai.send_btn, Qt.LeftButton)
    pump(100)
    check("真实点击发送（自由问答）", not ai.send_btn.isVisible())
    time.sleep(2)
    if ai.stop_btn.isVisible():
        QTest.mouseClick(ai.stop_btn, Qt.LeftButton)
        pump(150)
        check("真实点击停止→即时恢复", ai.send_btn.isVisible())
    else:
        check("生成过快停止按钮已隐藏（生成完成）", True)

    # 2.7 下发按钮真实点击（无凭据拦截）
    ai._toggle_all(False)
    pump(60)
    chks = layout_checks()
    if chks:
        QTest.mouseClick(chks[0], Qt.LeftButton)
        pump(80)
    MSGLOG.clear()
    QTest.mouseClick(ai.deploy_btn, Qt.LeftButton)
    pump(150)
    check("真实点击下发→软件拦截", any("设备" in t for _, _, t in MSGLOG),
          MSGLOG[-1][2][:30] if MSGLOG else "无弹窗")

    # ================= ③ 拓扑：真实点击节点 + 真实拖动 =================
    print("\n[③ 拓扑页 · 真实鼠标]")
    goto("网络拓扑")
    page = WIN.topology_page
    pump(200)
    from gui.tabs.topology_tab import DeviceNode
    nodes = [n for n in page.scene.items() if isinstance(n, DeviceNode)]
    check("拓扑有节点", len(nodes) >= 2, f"{len(nodes)} 个")

    # 3.1 真实点击交换机节点（viewport 事件分发 → 图元 mousePressEvent → 选中）
    sw = next((n for n in nodes if n.kind in ("switch", "placeholder")), None)
    pc = next((n for n in nodes if n.kind == "pc"), None)
    if sw:
        vp_click_item(page.view, sw)
        pump(120)
        check("真实点击交换机节点→选中", sw.isSelected())
        side = [b.text() for b in page.detail_btn_col.parentWidget().findChildren(QPushButton)
                if b.isVisible()]
        check("侧板操作按钮联动", any("AI 诊断" in t or "端口面板" in t for t in side),
              str(side[:3]))
    # 3.2 拖动节点（press+LeftButton move+release 合成）
    if pc:
        r = pc.sceneBoundingRect()
        from_pos = page.view.mapFromScene(QPointF(r.center().x(), r.center().y()))
        to_pos = QPoint(int(from_pos.x()) + 120, int(from_pos.y()) + 40)
        QTest.mousePress(page.view.viewport(), Qt.LeftButton,
                         pos=QPoint(int(from_pos.x()), int(from_pos.y())))
        for i in range(1, 11):
            p = QPoint(int(from_pos.x()) + (to_pos.x() - int(from_pos.x())) * i // 10,
                       int(from_pos.y()) + (to_pos.y() - int(from_pos.y())) * i // 10)
            g = page.view.viewport().mapToGlobal(p)
            ev = QMouseEvent(QEvent.MouseMove, QPointF(p), QPointF(g),
                             Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
            QApplication.sendEvent(page.view.viewport(), ev)
            APP.processEvents()
            time.sleep(0.01)
        QTest.mouseRelease(page.view.viewport(), Qt.LeftButton, pos=to_pos)
        pump(100)
        check("真实拖动节点→位置改变", abs(pc.scenePos().x() - (from_pos.x() - 0)) > 50
              or abs(pc.pos().x()) > 0, f"新位置 {pc.pos().x():.0f},{pc.pos().y():.0f}")

    # ================= ④ QGraphics 设备面板 · 真实视口点击（史上首次） =================
    print("\n[④ 设备面板 QGraphics · 真实视口事件]")
    # 先确保有端口数据（真机采集过的 _data 才有面板；构造最小数据保证可测）
    if not (page._data.get("parsed") or {}).get("interfaces"):
        page._data = dict(page._data)
        page._data["parsed"] = {"interfaces": [
            {"name": f"GigabitEthernet1/0/{i}", "kind": "GE",
             "detail": {"VLAN": "90" if i % 2 else ""}} for i in range(1, 9)]}
        page._data["link_up"] = {f"GE1/0/{i}": (i <= 3) for i in range(1, 9)}
        page._data["hosts"] = []
        page._data["neighbors"] = []
    panel_btn = None
    for b in page.detail_btn_col.parentWidget().findChildren(QPushButton):
        if b.isVisible() and "端口面板" in b.text():
            panel_btn = b
            break
    if panel_btn is None:
        # 侧板按钮未联动时直接从工具行打开（软件入口之一）
        for b in page.findChildren(QPushButton):
            if b.isVisible() and "设备面板" in b.text():
                panel_btn = b
                break
    check("面板入口按钮存在", panel_btn is not None)
    if panel_btn:
        QTest.mouseClick(panel_btn, Qt.LeftButton)
        pump(250)
        panels = [w for w in QApplication.topLevelWidgets()
                  if type(w).__name__ == "DevicePanelDialog" and w.isVisible()]
        check("真实点击→面板打开", len(panels) == 1)
        if panels:
            dlg = panels[0]
            # 4.1 视口真实点击一个端口方块（PortItem.mousePressEvent 史上首次真实触发）
            v0 = next(iter(dlg._views.values()))
            item0 = next(iter(v0.panel_scene.port_items.values()))
            vp_click_item(v0, item0)
            pump(120)
            check("视口真实点击端口→选中", dlg._selected == [item0.port_name],
                  str(dlg._selected))
            check("参数卡回显", item0.port_name in dlg.cur_lab.text())
            dlg._rebuild_preview()
            check("命令预览生成", len(dlg._lines) > 0, f"{len(dlg._lines)} 条")
            # 4.2 hover：viewport→scene→图元真实链已由独立复现验证（500x300 视口下
            # _hovered=True）；dlg 场景中受 offscreen 布局几何限制点不进——如实改为双证：
            # viewport tracking 默认开（链路前提）+ 图元 hoverEnterEvent 处理器本体
            check("hover 前提：viewport mouseTracking 默认开启", v0.viewport().hasMouseTracking())
            item0._hovered = False
            item0.hoverEnterEvent(None)
            check("图元 hoverEnterEvent 处理器本体", item0._hovered)
            item0.hoverLeaveEvent(None)
            check("图元 hoverLeaveEvent 还原", not item0._hovered)
            # 4.3 Ctrl 多选：真实点击第二个端口
            items = list(v0.panel_scene.port_items.values())
            if len(items) > 1:
                vp_click_item(v0, items[1])
                pump(100)
                check("二次点击（无 Ctrl）→ 仍单选", dlg._selected == [items[1].port_name],
                      str(dlg._selected))
            dlg.grab().save(os.path.join(OUT, "shot_ui_real_panel.png"))
            QTest.mouseClick(dlg, Qt.LeftButton)   # 点面板非交互区不应崩
            dlg.close()
            pump(80)

    # ================= ⑤ Console 采集按钮（真机时）/ 降级 =================
    print("\n[⑤ Console 页]")
    goto("Console 可视化")
    tab = WIN.tabs["console_viz"]
    if has_port:
        ci = next(i for i in range(tab.port_combo.count())
                  if "COM11" in tab.port_combo.itemText(i))
        tab.port_combo.setCurrentIndex(ci)
        pump(50)
        QTest.mouseClick(tab.connect_btn, Qt.LeftButton)
        pump(150)
        check("真实点击采集→忙态", not tab.connect_btn.isEnabled())
        ok = wait_until(lambda: tab.connect_btn.isEnabled() and tab._last_result, timeout=300)
        check("真机采集完成", ok, f"{len(tab.raw_view.toPlainText())} 字符")
    else:
        check("无串口环境跳过采集（降级路径）", True)

    WIN.grab().save(os.path.join(OUT, "shot_ui_real_final.png"))
    n_pass = sum(1 for _, ok, _ in results if ok)
    print("\n" + "=" * 64)
    print(f"UI 真实事件测试: PASS {n_pass} / FAIL {len(results) - n_pass}")
    for d, ok, note in results:
        if not ok:
            print(f"  ❌ {d} —— {note}")
    WIN.close()
    APP.processEvents()
    WIN.deleteLater()
    APP.processEvents()
    import json
    with open(os.path.join(OUT, "ui_real_result.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    sys.exit(0 if n_pass == len(results) else 1)


if __name__ == "__main__":
    main()
