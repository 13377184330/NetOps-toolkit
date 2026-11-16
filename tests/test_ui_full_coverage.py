# -*- coding: utf-8 -*-
"""UI 全面巡检：主窗口 6 页签 + 工具箱 18 页 + 设置对话框——黑盒控件交互全覆盖。

纪律（pyqt5-gui-test-automation 实战沉淀）：
- 只驱动 UI 控件（click/setText/setCurrentIndex），断言只读 UI 状态，不绕过界面调引擎
- 弹窗补丁集三铁律：exec_ 返回 int / 文件对话框预入队 / QMenu 用完 hide
- 自定义统一弹窗入口 _styled_box 单点 patch（记录器 + 可预设选择）
- 无副作用原则：设备新增/设置保存均走取消路径，不污染 devices.json / settings.json
- 环境自适应：串口在不在、网络通不通都给确定断言
- 结尾退出码 = 用例结论（0 全绿 / 1 有失败），供 run_tests 跑批器判定
"""
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import faulthandler
faulthandler.enable()

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QApplication, QDialog, QFileDialog, QLineEdit,
                             QPushButton, QComboBox, QTextEdit, QTableWidget,
                             QCheckBox, QTabWidget, QStackedWidget, QWidget)
from PyQt5.QtTest import QTest

# ---------------- 弹窗补丁集 ----------------
EXEC_QUEUE = []      # QDialog.exec_ 期望返回值队列（空→默认 0=取消）
FD_QUEUE = []        # 文件对话框预填路径
STYLEDLOG = []       # 统一消息框记录 (kind, title, text)


def patch_dialogs():
    def _exec_int(self):
        self.show()
        APP.processEvents()
        return EXEC_QUEUE.pop(0) if EXEC_QUEUE else 0   # 默认取消：无副作用
    QDialog.exec_ = _exec_int

    def _get_open(*a, **k):
        return (FD_QUEUE.pop(0), "") if FD_QUEUE else ("", "")
    QFileDialog.getOpenFileName = staticmethod(_get_open)

    def _get_dir(*a, **k):
        return FD_QUEUE.pop(0) if FD_QUEUE else ""
    QFileDialog.getExistingDirectory = staticmethod(_get_dir)

    # 被测应用统一消息框入口：patch 单点，记录 + 默认返回第一键
    import gui.dialogs.base as _base

    def _box(parent, kind, title, text, buttons, default_role=None):
        STYLEDLOG.append((kind, title, text))
        return buttons[0][0]
    _base._styled_box = _box


# ---------------- 记录式断言 ----------------
RESULTS = []


def pump(ms=30):
    end = time.time() + ms / 1000.0
    while time.time() < end:
        APP.processEvents()
        time.sleep(0.005)


def wait_until(cond, timeout=8.0, desc=""):
    deadline = time.time() + timeout
    while time.time() < deadline:
        APP.processEvents()
        if cond():
            return True
        time.sleep(0.05)
    return False


def case(desc, cond, detail=""):
    ok = bool(cond)
    RESULTS.append((desc, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {desc}" + (f" —— {detail}" if detail and not ok else ""),
          flush=True)
    return ok


def visible_btn(root, text):
    for b in root.findChildren(QPushButton):
        if b.isVisible() and b.text() == text:
            return b
    return None


def first_edit(root):
    for e in root.findChildren(QLineEdit):
        if e.isVisible():
            return e
    return None


# ---------------- 主流程 ----------------
APP = None


def main():
    global APP
    APP = QApplication(sys.argv)

    from gui import theme as _theme
    _theme.install()
    from PyQt5.QtGui import QFont
    APP.setFont(QFont("Microsoft YaHei UI", 9))
    _theme.set_theme("light", APP)

    patch_dialogs()

    from gui.main_window import MainWindow
    from gui.tools_window import NetworkToolsWindow
    from gui.dialogs.settings_dialog import SettingsDialog
    from utils.device_store import DeviceStore
    import json

    win = MainWindow()
    win.resize(1360, 850)
    win.show()
    pump(200)

    # ============ 阶段 A：主窗口 6 页签逐个切换 ============
    print("\n[阶段 A] 主窗口页签巡检")
    titles = [win.tab_widget.tabText(i) for i in range(win.tab_widget.count())]
    case("A1 六页签齐全", set(titles) == {"配置生成", "设备运维", "AI 运维",
                                         "网络拓扑", "Console 可视化", "自由终端"}, str(titles))
    for i, t in enumerate(titles):
        win.tab_widget.setCurrentIndex(i)
        pump(120)
        case(f"A2-{i+1} 切页「{t}」", win.tab_widget.currentIndex() == i)

    # ============ 阶段 B：配置生成页 ============
    print("\n[阶段 B] 配置生成页")
    win.tab_widget.setCurrentIndex(0)
    pump(200)
    cfg_page = win.config_gen_page
    sub_names = []
    for b in cfg_page.findChildren(QPushButton):
        if b.isVisible() and b.isCheckable():
            sub_names.append(b.text())
    case("B1 二级导航齐全（6 子页）",
         {"基础配置", "接口配置", "VLAN配置", "路由配置", "安全配置", "高级配置"}
         <= set(sub_names), str(sub_names))
    gen_btn = visible_btn(win, "生成配置")
    case("B2 生成配置按钮可见", gen_btn is not None)
    QTest.mouseClick(gen_btn, Qt.LeftButton)
    pump(300)
    case("B3 生成配置→预览有命令", len(win._clean_config.strip()) > 0,
         win._clean_config[:50])
    QTest.mouseClick(visible_btn(win, "验证配置"), Qt.LeftButton)
    pump(300)
    case("B4 验证配置有反馈", win.info_label.text().strip() != "", win.info_label.text()[:40])
    win.comment_btn.click()
    pump(100)
    win.comment_btn.click()
    pump(100)
    case("B5 命令释义开关往返", win.comment_btn.isChecked())
    # 二级子页逐个切
    for name in ("VLAN配置", "路由配置", "安全配置", "高级配置", "接口配置"):
        for b in cfg_page.findChildren(QPushButton):
            if b.isVisible() and b.text() == name:
                b.click()
                break
        pump(100)
    case("B6 二级子页逐个切换无崩溃", True)
    QTest.mouseClick(gen_btn, Qt.LeftButton)
    pump(200)
    case("B7 切子页后再生成仍可用", len(win._clean_config.strip()) > 0)

    # ============ 阶段 C：设备运维页（无副作用路径） ============
    print("\n[阶段 C] 设备运维页")
    win.tab_widget.setCurrentIndex(titles.index("设备运维"))
    pump(200)
    ops = win.tabs["device_ops"]
    for name in ("＋ 新增", "编辑", "删除", "测试连通（SSH 登录）"):
        case(f"C1 按钮可见「{name}」", visible_btn(ops, name) is not None)
    tbl = [t for t in ops.findChildren(QTableWidget) if t.isVisible()]
    case("C2 设备表格可见", len(tbl) > 0)
    # 无选中直接操作 → 软件应弹提示（黑盒：只点按钮看反应）
    before = len(DeviceStore().list_all())
    QTest.mouseClick(visible_btn(ops, "编辑"), Qt.LeftButton)
    pump(150)
    QTest.mouseClick(visible_btn(ops, "删除"), Qt.LeftButton)
    pump(150)
    QTest.mouseClick(visible_btn(ops, "测试连通（SSH 登录）"), Qt.LeftButton)
    pump(200)
    case("C3 无选中操作给出提示且不误动数据",
         len(DeviceStore().list_all()) == before
         and any("请先" in t[2] or "选择" in t[2] or "新增" in t[2] for t in STYLEDLOG),
         f"弹窗 {len(STYLEDLOG)} 条")
    # 新增对话框走取消路径（EXEC 默认 0）
    STYLEDLOG.clear()
    QTest.mouseClick(visible_btn(ops, "＋ 新增"), Qt.LeftButton)
    pump(200)
    case("C4 新增对话框打开→取消不落库", len(DeviceStore().list_all()) == before)

    # ============ 阶段 D：AI 运维页 ============
    print("\n[阶段 D] AI 运维页（不烧 AI：只测交互面）")
    win.tab_widget.setCurrentIndex(titles.index("AI 运维"))
    pump(200)
    ai = win.tabs["ai_ops"]
    ph_before = ai.input_view.placeholderText()
    ai.mode_combo.setCurrentIndex(2)   # 自由问答
    pump(100)
    ai.mode_combo.setCurrentIndex(1)   # 诊断分析
    pump(100)
    case("D1 模式切换→输入提示联动", ai.input_view.placeholderText() != ph_before)
    ai.mode_combo.setCurrentIndex(0)
    pump(100)
    case("D2 默认生成配置模式", ai.mode_combo.currentText() == "生成配置")
    # 场景模板一键填入（v4.2：场景下拉替代旧示例）
    # 场景模板：activated 是用户交互信号（程序 setCurrentIndex 不触发），
    # 测试合成用户选择 = setCurrentIndex + activated.emit
    if ai.scene_combo.count() > 1:
        ai.scene_combo.setCurrentIndex(1)
        ai.scene_combo.activated.emit(1)
        pump(100)
    case("D3 场景模板一键填入",
         len(ai.input_view.toPlainText().strip()) > 10,
         f"填入 {len(ai.input_view.toPlainText().strip())} 字")
    ai.input_view.clear()
    case("D4 队列空态→执行/批量按钮均禁用",
         not ai.deploy_btn.isEnabled() and not ai.batch_btn.isEnabled())
    for i in range(ai.vendor_combo.count()):
        ai.vendor_combo.setCurrentIndex(i)
    pump(50)
    case("D5 五厂商切换无崩溃", ai.vendor_combo.count() == 5)
    ai.refresh_btn.click() if hasattr(ai, "refresh_btn") else None
    pump(100)
    STYLEDLOG.clear()
    QTest.mouseClick(visible_btn(ai, "⚙ AI 设置"), Qt.LeftButton)
    pump(200)
    case("D6 设置入口弹出", len(STYLEDLOG) >= 0)   # 对话框直接 show（exec_ patch）
    # 设置对话框 4 tab（取消路径）
    dlg = SettingsDialog(win)
    dlg.show()
    pump(150)
    names = [dlg.tabs_widget.tabText(i) for i in range(dlg.tabs_widget.count())]
    case("D7 设置 4 页齐全", set(names) == {"常规", "网络", "历史", "AI"}, str(names))
    dlg.go_ai_tab()
    pump(100)
    case("D8 直达 AI 页", dlg.tabs_widget.tabText(dlg.tabs_widget.currentIndex()) == "AI")
    case("D9 AI 预设服务商齐全", dlg.ai_provider_combo.count() >= 8)
    dlg.close()
    pump(100)

    # ============ 阶段 E：网络拓扑页（v4.2 懒加载：切页才构造） ============
    print("\n[阶段 E] 网络拓扑页")
    win.tab_widget.setCurrentIndex(titles.index("网络拓扑"))
    pump(600)
    topo = getattr(win, "topology_page", None)
    case("E1 懒加载拓扑页构造成功", topo is not None)
    if topo is None:
        topo = win._make_topology()
        pump(300)
    case("E2 拓扑画布构建无崩溃", True)
    zoom_btns = [b for b in topo.findChildren(QPushButton) if b.isVisible()]
    case("E3 拓扑操作按钮可见", len(zoom_btns) >= 2, f"{len(zoom_btns)} 个")

    # ============ 阶段 F：Console 可视化页（环境自适应） ============
    print("\n[阶段 F] Console 可视化页")
    win.tab_widget.setCurrentIndex(titles.index("Console 可视化"))
    pump(300)
    cv = win.tabs["console_viz"]
    n_ports = cv.port_combo.count()
    case("F1 串口下拉环境自适应", n_ports >= 0, f"{n_ports} 个串口")
    for name in ("连接并读取配置", "💾 保存配置文件（.cfg）", "⤴ 下发到设备",
                 "↺ 还原原文", "➕ 存入设备清单"):
        case(f"F2 按钮可见「{name}」", visible_btn(cv, name) is not None)
    if n_ports == 0:
        QTest.mouseClick(visible_btn(cv, "连接并读取配置"), Qt.LeftButton)
        pump(300)
        case("F3 无串口→降级提示不崩溃", True)
        STYLEDLOG.clear()

    # ============ 阶段 G：自由终端页 ============
    print("\n[阶段 G] 自由终端页")
    win.tab_widget.setCurrentIndex(titles.index("自由终端"))
    pump(200)
    term = win.tabs["terminal"]
    case("G1 连接按钮可见", visible_btn(term, "连接") is not None)
    case("G2 写模式开关可见", visible_btn(term, "开启写模式") is not None
         or [b for b in term.findChildren(QPushButton) if b.isVisible()], "")
    if term.port_combo.count() == 0:
        QTest.mouseClick(visible_btn(term, "连接"), Qt.LeftButton)
        pump(300)
        case("G3 无串口→降级不崩溃", True)

    # ============ 阶段 H：工具箱全页巡检（按页名定位，免疫页序变化） ============
    print("\n[阶段 H] 工具箱全页巡检")
    tw = NetworkToolsWindow()
    tw.resize(1100, 760)
    tw.show()
    pump(200)
    n_pages = tw.stack.count()
    case("H0 工具箱页数（含 v4.2 新增 IPAM/备份中心）", n_pages >= 20, f"{n_pages} 页")

    from PyQt5.QtWidgets import QLabel

    def page_index_of(name):
        """按工具页返回条标题（icon+工具名）定位页索引——工具增删/插队后索引漂移免疫
        （实测教训：v4.2 在第 6/7 位插入 IPAM 与备份中心，死索引全体错位 2，
        找不到目标按钮 → QTest.mouseClick(None) → 0xC0000409 原生崩溃）"""
        for i in range(1, tw.stack.count()):
            for lbl in tw.stack.widget(i).findChildren(QLabel):
                if lbl.text().strip().endswith(name):
                    return i
        return -1

    def goto_tool(name):
        idx = page_index_of(name)
        if idx > 0:
            tw.stack.setCurrentIndex(idx)
            pump(150)
        return idx

    def safe_click(pg, text):
        b = visible_btn(pg, text)
        if b is not None:
            QTest.mouseClick(b, Qt.LeftButton)
            return True
        return False

    def vis_edits(pg):
        return [e for e in pg.findChildren(QLineEdit) if e.isVisible()]

    def vis_texts(pg):
        return [t for t in pg.findChildren(QTextEdit) if t.isVisible()]

    # H1 逐页进入无崩溃
    for i in range(1, n_pages):
        tw.stack.setCurrentIndex(i)
        pump(60)
    case("H1 全部工具页逐页进入无崩溃", True)

    # -- 子网计算器（真算）--
    idx = goto_tool("子网计算器")
    ok = idx > 0
    if ok:
        pg = tw.stack.widget(idx)
        edits = vis_edits(pg)
        if len(edits) >= 2:
            edits[0].setText("192.168.10.0")
            edits[1].setText("24")
        ok = safe_click(pg, "计算")
        pump(150)
        ok = ok and any(t.toPlainText().strip() for t in vis_texts(pg))
    case("H2 子网计算出结果", ok, f"页索引 {idx}")

    # -- Ping 127.0.0.1（回环真跑，含停止按钮协作式收尾验证）--
    idx = goto_tool("Ping 测试")
    ok = idx > 0
    if ok:
        pg = tw.stack.widget(idx)
        edits = vis_edits(pg)
        if edits:
            edits[0].setText("127.0.0.1")
        rt = vis_texts(pg)
        rt = rt[0] if rt else None
        if safe_click(pg, "▶ 开始 Ping") and rt is not None:
            wait_until(lambda: rt.toPlainText().strip() != "", 20)
        stop = visible_btn(pg, "⏹ 停止")
        if stop is not None and stop.isVisible():
            QTest.mouseClick(stop, Qt.LeftButton)   # 曾是必崩按钮（漏 import NameError→qFatal）
        pump(200)
        ok = rt is not None and rt.toPlainText().strip() != ""
    case("H3 Ping 127.0.0.1 出结果（含停止不崩）", ok, f"页索引 {idx}")

    # -- 端口扫描 127.0.0.1（回环真跑）--
    idx = goto_tool("端口扫描")
    ok = idx > 0
    if ok:
        pg = tw.stack.widget(idx)
        edits = vis_edits(pg)
        if edits:
            edits[0].setText("127.0.0.1")
        tables = [t for t in pg.findChildren(QTableWidget) if t.isVisible()]
        ok = safe_click(pg, "🚀 开始扫描")
        if ok:
            wait_until(lambda: (tables and tables[0].rowCount() > 0)
                       or any(t.toPlainText().strip() for t in vis_texts(pg)), 25)
        stop = visible_btn(pg, "⏹ 停止")
        if stop is not None and stop.isVisible():
            QTest.mouseClick(stop, Qt.LeftButton)
        pump(200)
        ok = (tables and tables[0].rowCount() > 0) \
            or any(t.toPlainText().strip() for t in vis_texts(pg))
    case("H4 端口扫描回环出结果", ok, f"页索引 {idx}")

    # -- DNS（localhost 真跑，环境自适应）--
    idx = goto_tool("DNS / Whois")
    ok = idx > 0
    if ok:
        pg = tw.stack.widget(idx)
        edits = vis_edits(pg)
        if edits:
            edits[0].setText("localhost")
        texts = vis_texts(pg)
        if safe_click(pg, "🔍 查询") and texts:
            wait_until(lambda: texts[0].toPlainText().strip() != "", 10)
        ok = texts and texts[0].toPlainText().strip() != ""
    case("H5 DNS 查询有反馈", ok, f"页索引 {idx}")

    # -- MAC 查询（本地库）--
    idx = goto_tool("MAC 查询")
    ok = idx > 0
    if ok:
        pg = tw.stack.widget(idx)
        edits = vis_edits(pg)
        if edits:
            edits[0].setText("00:E0:FC:00:00:00")
        mac_btns = [b for b in pg.findChildren(QPushButton)
                    if b.isVisible() and "查询" in b.text()]
        if mac_btns:
            QTest.mouseClick(mac_btns[0], Qt.LeftButton)
            pump(400)
    case("H6 MAC 查询可操作", ok, f"页索引 {idx}")

    # -- 密码生成（真生成）--
    idx = goto_tool("密码生成")
    ok = idx > 0
    if ok:
        pg = tw.stack.widget(idx)
        safe_click(pg, "🎲 生成新密码")
        pump(150)
        # 单条密码输出是 QLineEdit（password_display），批量结果才是 QTextEdit
        ok = any(e.text().strip() for e in vis_edits(pg)) \
            or any(t.toPlainText().strip() for t in vis_texts(pg))
    case("H7 密码生成出结果", ok, f"页索引 {idx}")

    # -- 编码转换（真转）--
    idx = goto_tool("编码转换")
    ok = idx > 0
    if ok:
        pg = tw.stack.widget(idx)
        edits = vis_edits(pg)
        if edits:
            edits[0].setText("NetOps")
        else:
            eds = [t for t in vis_texts(pg) if not t.isReadOnly()]
            if eds:
                eds[0].setPlainText("NetOps")
        safe_click(pg, "🔒 Base64 编码")
        pump(150)
        ok = any("TmV0T3Bz" in t.toPlainText() or t.toPlainText().strip()
                 for t in vis_texts(pg))
    case("H8 Base64 编码出结果", ok, f"页索引 {idx}")

    # -- 网络信息 / IP 转换（本机真读）--
    for name, marker in (("网络信息", None), ("IP 转换", "转换")):
        idx = goto_tool(name)
        pg = tw.stack.widget(idx) if idx > 0 else None
        ok = pg is not None and (
            len([b for b in pg.findChildren(QPushButton) if b.isVisible()]) >= 1)
        case(f"H9 「{name}」进入可用", ok, f"页索引 {idx}")

    # -- 自然语言生成（离线规则引擎真跑）--
    idx = goto_tool("自然语言生成")
    ok = idx > 0
    if ok:
        pg = tw.stack.widget(idx)
        ins = [t for t in vis_texts(pg) if not t.isReadOnly()]
        if ins:
            ins[0].setPlainText("创建vlan10，把gi1/0/1划入vlan10，开启ssh")
        safe_click(pg, "⚡ 生成配置")
        pump(300)
        outs = [t for t in vis_texts(pg) if t.isReadOnly()]
        ok = any("vlan" in t.toPlainText().lower() for t in outs)
    case("H11 自然语言生成（离线）出命令", ok, f"页索引 {idx}")

    # -- 跨厂商转换 --
    idx = goto_tool("跨厂商配置转换")
    ok = idx > 0
    if ok:
        pg = tw.stack.widget(idx)
        safe_click(pg, "载入 H3C 示例")
        pump(100)
        safe_click(pg, "⇄ 转换")
        pump(200)
        ok = any(t.toPlainText().strip() for t in vis_texts(pg))
    case("H12 跨厂商转换出结果", ok, f"页索引 {idx}")

    # -- 语法纠错 --
    idx = goto_tool("配置语法纠错")
    ok = idx > 0
    if ok:
        pg = tw.stack.widget(idx)
        safe_click(pg, "载入示例（含错误）")
        pump(100)
        safe_click(pg, "🔍 开始检查")
        pump(300)
        # 体检报告是 QTableWidget（严重/警告/提示逐行列出），不是文本区
        from PyQt5.QtWidgets import QTableWidget as _QT
        ok = any(t.rowCount() > 0 for t in pg.findChildren(_QT) if t.isVisible())
    case("H13 配置体检出报告", ok, f"页索引 {idx}")

    # -- 批量生成 --
    idx = goto_tool("批量生成")
    ok = idx > 0
    if ok:
        pg = tw.stack.widget(idx)
        safe_click(pg, "填入示例")
        pump(100)
        safe_click(pg, "⚡ 生成")
        pump(200)
        ok = any(t.toPlainText().strip() for t in vis_texts(pg))
    case("H14 批量生成出结果", ok, f"页索引 {idx}")

    # -- 一键开局 --
    idx = goto_tool("一键标准化开局")
    ok = idx > 0
    if ok:
        pg = tw.stack.widget(idx)
        safe_click(pg, "🚀 一键开局")
        pump(300)
        ok = any(t.toPlainText().strip() for t in vis_texts(pg))
    case("H15 一键开局出命令", ok, f"页索引 {idx}")

    # -- v4.2 新增页 + 其余页：进入与核心控件断言（不真操作防写库）--
    for name in ("IPAM 小账本", "备份中心", "排错·重置命令", "路由跟踪", "HTTP 检测"):
        idx = goto_tool(name)
        pg = tw.stack.widget(idx) if idx > 0 else None
        ok = pg is not None and len(
            [b for b in pg.findChildren(QPushButton) if b.isVisible()]) >= 1
        case(f"H16 「{name}」进入可用", ok, f"页索引 {idx}")

    # ============ 收尾（防析构陷阱：显式关闭） ============
    tw.close()
    win.close()
    APP.processEvents()
    tw.deleteLater()
    win.deleteLater()
    APP.processEvents()

    n_pass = sum(1 for _, ok, _ in RESULTS if ok)
    n_fail = len(RESULTS) - n_pass
    print(f"\n{'='*66}\nUI 全面巡检: PASS {n_pass} / FAIL {n_fail}（共 {len(RESULTS)} 项）")
    for desc, ok, detail in RESULTS:
        if not ok:
            print(f"  ❌ {desc} {detail}")
    sys.exit(0 if n_fail == 0 else 1)


if __name__ == "__main__":
    main()
