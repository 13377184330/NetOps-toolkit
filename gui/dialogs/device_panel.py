#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
设备面板（Device Panel）—— 把交换机画成一块真实面板的傻瓜式配置视图
================================================================
设计对标市面网管产品的「设备面板视图」（华为 eSight / iMaster NCE-Campus、
H3C IMC、Cisco Prime 的 device physical view 同款心智模型）：
把物理端口画成一格一格的状态方块，颜色即状态、点击即参数、改完即命令。

本工具的差异化（离线桌面工具 vs 商用网管平台）：
  - eSight/IMC/Prime 要先建网管平面（装服务器、配 IP/SNMP、纳管设备）；
    本面板插 Console 线 + 一次采集即可用，内网/新出厂/无管理 IP 的设备也能看。
  - 市面产品改配置走"模板提交"，用户看不到设备将执行什么；本面板参数一变
    底部命令实时刷新（所见即所得），复制或一键应用（经确认走 Console 下发闭环）。

交互契约（傻瓜式三步）：
  1. 点端口方块 → 右侧回显该口当前值（状态/模式/VLAN/描述/下挂终端）
  2. 改参数 → 命令预览实时生成（不用懂命令语法，看着改就行）
  3. 「应用到设备」→ 填入 Console 原文 → 弹确认 → 下发 → 自动重采（闭环兜底）

只读红线不变：本面板只生成文本；写入永远经 deploy_to_device 的显式确认。
非模态窗口：可与拓扑页同时观察（面板选中端口 ↔ 拓扑端口格联动高亮）。
"""

from PyQt5.QtCore import Qt, QRectF, pyqtSignal
from PyQt5.QtGui import (QBrush, QColor, QFont, QFontMetrics, QPainter,
                          QPainterPath, QPen)
from PyQt5.QtWidgets import (QApplication, QCheckBox, QComboBox, QFormLayout,
                              QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                              QPushButton, QScrollArea, QSizePolicy, QTextEdit,
                              QVBoxLayout, QWidget)

from gui.dialogs.base import BaseDialog, warn_box
from gui import theme

from modules.nl_engine import e_port_access, e_port_trunk
from modules.config_visualizer import expand_vlan_body

# ---------------------------------------------------------------- 端口方块
CELL_W, CELL_H = 60, 56
_PER_ROW = 10          # 电口每行格数（保证左区完整展示不被裁切，视觉审查实测）


def _state_palette(state):
    """状态 → (底色, 边框色)——统一走 theme token：浅色淡底深边，深色暗底亮边，
    两个主题下状态色都一眼可辨（深色不再残留刺眼浅色块）"""
    t = theme.t
    return {
        "up":       (t("port_up_bg"), t("port_up_border")),
        "down":     (t("port_down_bg"), t("port_down_border")),
        "trunk":    (t("port_trunk_bg"), t("port_trunk_border")),
        "shutdown": (t("danger_light"), t("danger")),
        "unknown":  (t("card"), t("border")),
    }.get(state, (t("card"), t("border")))


class PortCell(QWidget):
    """单个端口方块：状态底色 + 端口号 + VLAN/模式小字 + 下挂/邻居角标。
    点击选中（发信号，Ctrl+点击加入/移出多选）。"""

    clicked = pyqtSignal(str, bool)     # (端口全名, ctrl按下?)

    def __init__(self, info, parent=None):
        super().__init__(parent)
        self.info = info                  # {name,label,state,vlan,desc,hosts,neighbor}
        self.selected = False
        self.setFixedSize(CELL_W, CELL_H)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(self._tip())

    def set_selected(self, on):
        if self.selected != on:
            self.selected = on
            self.update()

    def _tip(self):
        i = self.info
        state_txt = {"up": "链路 UP", "down": "链路 DOWN", "trunk": "Trunk 干道",
                     "shutdown": "已手工关闭(shutdown)", "unknown": "链路状态未知"}[i["state"]]
        bits = [i["name"], state_txt]
        if i["vlan"]:
            bits.append(f"VLAN {i['vlan']}")
        if i["desc"]:
            bits.append(i["desc"])
        if i["hosts"]:
            bits.append("下挂: " + "、".join(i["hosts"]))
        if i["neighbor"]:
            bits.append(f"LLDP 邻居: {i['neighbor']}")
        bits.append("（点击选中 · Ctrl+点击多选）")
        return "\n".join(bits)

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.LeftButton and ev.pos() in self.rect():
            self.clicked.emit(self.info["name"], ev.modifiers() & Qt.ControlModifier)
        super().mouseReleaseEvent(ev)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        i = self.info
        bg, border = _state_palette(i["state"])
        if self.selected:
            bg, border = theme.t("accent_light"), theme.t("accent")
        r = 9
        path = QPainterPath()
        path.addRoundedRect(0.5, 0.5, CELL_W - 1, CELL_H - 1, r, r)
        p.fillPath(path, QBrush(QColor(bg)))
        pen = QPen(QColor(border))
        pen.setWidth(3 if self.selected else 1)
        pen.setStyle(Qt.DashLine if i["state"] == "unknown" else Qt.SolidLine)
        p.setPen(pen)
        p.drawPath(path)

        # 上半区：端口号（大字）；下半区：状态小字（VLAN/trunk/已关）——两区分离不重叠
        f = QFont("Microsoft YaHei UI", 13)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(theme.t("text")))          # 主题感知：深色下方块变暗，文字同步提亮
        p.drawText(self.rect().adjusted(0, 0, 0, -18), Qt.AlignCenter, i["label"])

        # VLAN 可视化：Access 口且知道 VLAN 时，格子底部画 VLAN 色条 + 小字同色，
        # 跨口扫读一眼对上「哪些口在同一个 VLAN」（与拓扑页同色源）
        vlan_id = i["vlan"] if (i["vlan"] or "").isdigit() else ""
        if vlan_id:
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(theme.vlan_color(vlan_id))))
            p.drawRect(3, CELL_H - 5, CELL_W - 6, 3)

        small = {"up": f"V{i['vlan']}" if i["vlan"] else "up",
                 "down": f"V{i['vlan']}" if i["vlan"] else "—",
                 "trunk": "trunk", "shutdown": "已关",
                 "unknown": "无数据"}.get(i["state"], "")
        f2 = QFont("Microsoft YaHei UI", 8)
        p.setFont(f2)
        # VLAN 小字同色源不变（色条+文字同色便于扫读）；无 VLAN 的口用 text_sub，
        # 比边框色深一档（视觉审查两轮指出对比不足）
        p.setPen(QColor(theme.vlan_color(vlan_id)) if vlan_id
                 else QColor(theme.t("text_sub")))
        p.drawText(QRectF(2, CELL_H - 17, CELL_W - 4, 14), Qt.AlignCenter, small)

        # 角标：蓝点=下挂终端 / 紫点=LLDP 邻居
        dot_x = CELL_W - 11
        if i["hosts"]:
            p.setBrush(QBrush(QColor(theme.t("accent"))))
            p.setPen(Qt.NoPen)
            p.drawEllipse(dot_x, 5, 6, 6)
            dot_x -= 8
        if i["neighbor"]:
            p.setBrush(QBrush(QColor(theme.t("port_trunk_border"))))
            p.setPen(Qt.NoPen)
            p.drawEllipse(dot_x, 5, 6, 6)
        p.end()


# ---------------------------------------------------------------- 端口数据聚合
def _aggregate_ports(data):
    """_data（拓扑页最近一次采集）→ 端口方块数据列表。
    复用拓扑端口格的状态判定（_port_state），保证大面板与节点小格口径一致。"""
    from gui.tabs.topology_tab import _port_state, _norm_port   # 函数内 import 防循环

    parsed = data.get("parsed") or {}
    link_up = data.get("link_up") or {}
    hosts_by_port, nbs_by_port = {}, {}
    for h in data.get("hosts") or []:
        hosts_by_port.setdefault(_norm_port(h.get("port", "")), []).append(
            (h.get("ip") or h.get("mac_display") or h.get("mac") or "?"))
    for nb in data.get("neighbors") or []:
        nbs_by_port[_norm_port(nb.get("port", ""))] = nb.get("name", "")

    cells = []
    for itf in parsed.get("interfaces") or []:
        name = itf["name"]
        if name.lower().startswith(("vlan", "vlanif", "null", "m-gigabit",
                                    "mgigabit", "loopback", "inloop", "tunnel")):
            continue
        d = itf.get("detail") or {}
        cells.append({
            "name": name,
            "label": _port_label_of(name),
            "state": _port_state(itf, link_up),
            "group": itf.get("kind") or "其他",
            "vlan": str(d.get("VLAN", "") or "").strip(),
            "desc": str(d.get("描述", "") or "").strip(),
            "hosts": hosts_by_port.get(_norm_port(name), []),
            "neighbor": nbs_by_port.get(_norm_port(name), ""),
        })
    return cells


def _port_label_of(name):
    import re
    nums = re.findall(r"\d+", name or "")
    return nums[-1] if nums else "?"


# ---------------------------------------------------------------- 主面板
class DevicePanelDialog(BaseDialog):
    """设备面板：大号端口矩阵 + 参数卡 + 实时命令预览 + 一键应用。
    非模态（show 而非 exec_）：可与拓扑页同屏观察、无模态副作用。"""

    def __init__(self, page, parent=None):
        self.page = page                      # NetworkTopologyPage（数据源 + 联动）
        data = page._data
        vendor = (data.get("vendor") or "huawei").lower()
        name = data.get("name") or "交换机"
        meta = data.get("meta") or {}
        model = str(meta.get("型号") or meta.get("接口数") or "")
        super().__init__(
            "🖥 设备面板 · " + name,
            "傻瓜式三步：① 点端口看参数  ② 改参数（下面命令实时生成）  "
            "③ 应用到设备（会弹确认，下发后自动重新采集）",
            parent or page, min_width=1280, min_height=620, scrollable=True)
        self._vendor = vendor
        self._cells = []                       # [PortCell]
        self._by_name = {}
        self._selected = []                    # 选中端口全名（有序）
        self._lines = []                       # [(cmd, 释义)]
        self._activated_nodes = []              # 拓扑联动高亮过的节点（用于还原）

        lay = self.content_layout()
        body = QHBoxLayout()
        body.setSpacing(14)

        # ---- 左：端口矩阵（滚动区，组内按列排布） ----
        self._cells = []
        for info in _aggregate_ports(data):
            c = PortCell(info)
            c.clicked.connect(self._on_cell_clicked)
            self._cells.append(c)
            self._by_name[info["name"]] = c
        groups = []
        for c in self._cells:
            if groups and groups[-1][0] == c.info["group"]:
                groups[-1][1].append(c)
            else:
                groups.append((c.info["group"], [c]))

        matrix_host = QWidget()
        ml = QVBoxLayout(matrix_host)
        ml.setContentsMargins(2, 2, 2, 2)
        ml.setSpacing(10)
        for gname, cells in groups:
            gl = QLabel(gname)
            gl.setStyleSheet("font-weight: bold; font-size: 12px; color: #5F6B7A;"
                              "background: transparent;")
            ml.addWidget(gl)
            grid = QGridLayout()
            grid.setSpacing(6)
            for idx, c in enumerate(cells):
                grid.addWidget(c, idx // _PER_ROW, idx % _PER_ROW)
            # 尾部空列吃掉全部富余宽度：否则 QGridLayout 会把宽度摊进各列间隙，
            # 造成组间首列错位、少格的组（如光口 4 格）间距异常偏大
            grid.setColumnStretch(_PER_ROW, 1)
            ml.addLayout(grid)
        _lg = theme.t
        _lg_colors = {s: _state_palette(s)[1] for s in ("up", "down", "trunk", "shutdown")}
        legend = QLabel(
            "图例："
            " <span style='color:%s'>■</span> 链路UP" % _lg_colors["up"]
            + "　<span style='color:%s'>■</span> DOWN" % _lg_colors["down"]
            + "　<span style='color:%s'>■</span> Trunk" % _lg_colors["trunk"]
            + "　<span style='color:%s'>■</span> 手工关闭" % _lg_colors["shutdown"]
            + " · <span style='color:%s'>●</span> 下挂终端" % _lg("accent")
            + "　<span style='color:%s'>●</span> LLDP邻居" % _lg_colors["trunk"]
            + " · 底部色条/小字同色=同一VLAN")
        legend.setStyleSheet("color: #5F6B7A; font-size: 12px; background: transparent;")
        legend.setWordWrap(True)
        ml.addWidget(legend)
        ml.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(matrix_host)
        scroll.setStyleSheet("QScrollArea { border: 1px solid #E5EAF2;"
                              " border-radius: 12px; background: #FFFFFF; }")
        body.addWidget(scroll, 5)

        # ---- 右：参数卡（当前值 + 修改区 + 实时预览） ----
        right = QVBoxLayout()
        right.setSpacing(8)
        self.cur_lab = QLabel("👆 点击左侧端口开始")
        self.cur_lab.setWordWrap(True)
        self.cur_lab.setStyleSheet("color: #5F6B7A; font-size: 12px;"
                                   "background: #F7F9FC; border-radius: 10px;"
                                   "padding: 10px;")
        right.addWidget(self.cur_lab)

        form_host = QWidget()
        form = QFormLayout(form_host)
        form.setSpacing(9)
        # 无效参数的红边反馈样式（vlan_combo 常驻去掉内嵌输入框的重复边框）
        self._vlan_ss_normal = (
            "QComboBox QLineEdit { border: none; background: transparent;"
            " padding: 0 8px; }")
        self._line_ss_invalid = "QLineEdit { border: 1.5px solid %s; }" % theme.t("danger")
        self._vlan_ss_invalid = (
            self._vlan_ss_normal
            + " QComboBox { border: 1.5px solid %s; }" % theme.t("danger"))

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Access 接入口", "Trunk 干道"])
        form.addRow("端口模式:", self.mode_combo)
        self.vlan_combo = QComboBox()
        self.vlan_combo.setEditable(True)
        self.vlan_combo.setToolTip("下拉列出设备上已有的 VLAN，也可直接输入数字")
        self.vlan_combo.setStyleSheet(self._vlan_ss_normal)
        form.addRow("Access VLAN:", self.vlan_combo)
        self.trunk_edit = QLineEdit()
        self.trunk_edit.setPlaceholderText("例: 10 20 30 或 999 to 1048")
        self.trunk_edit.setEnabled(False)
        form.addRow("Trunk 放行:", self.trunk_edit)
        self.desc_edit = QLineEdit()
        self.desc_edit.setPlaceholderText("选填，如 dT:财务-301")
        form.addRow("描述:", self.desc_edit)
        self.shut_chk = QCheckBox("关闭端口（shutdown）")
        self.unshut_chk = QCheckBox("恢复链路（undo shutdown）")
        form.addRow("", self.shut_chk)
        form.addRow("", self.unshut_chk)
        right.addWidget(form_host)

        # VLAN 快选：采集到的 VLAN 列表
        for v in (data.get("parsed") or {}).get("vlans") or []:
            self.vlan_combo.addItem(f"{v['id']}  ·  {v.get('name', '')}", v["id"])
        self.vlan_combo.setCurrentText("1")

        pv_lab = QLabel("命令预览（实时生成，改动即刷新）")
        pv_lab.setStyleSheet("font-weight: bold; font-size: 12px; background: transparent;")
        right.addWidget(pv_lab)
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("选中端口并设置参数后，这里实时显示将要下发的命令")
        self.preview.setStyleSheet("QTextEdit { background: #1E2430; color: #D7E1EE;"
                                   "border-radius: 10px; font-family: Consolas;"
                                   "font-size: 12px; padding: 10px 12px; }")
        right.addWidget(self.preview, 1)
        body.addLayout(right, 3)

        lay.addLayout(body, 1)

        # 参数联动 → 实时预览
        self.mode_combo.currentIndexChanged.connect(self._rebuild_preview)
        self.vlan_combo.editTextChanged.connect(self._rebuild_preview)
        self.trunk_edit.textChanged.connect(self._rebuild_preview)
        self.desc_edit.textChanged.connect(self._rebuild_preview)
        self.shut_chk.toggled.connect(self._rebuild_preview)
        self.unshut_chk.toggled.connect(self._rebuild_preview)
        # 模式切换时字段联动
        self.mode_combo.currentIndexChanged.connect(
            lambda i: (self.vlan_combo.setEnabled(i == 0),
                       self.trunk_edit.setEnabled(i != 0)))

        self.add_button("复制纯命令", "secondary", self._copy_cmds,
                        close_on_click=False, tip="无注释，可直接粘贴")
        # close_on_click=False：用户在 Console 确认框点「否」后面板保留，可继续调整参数
        self.add_button("⤴ 应用到设备", "primary", self._apply_to_device,
                        close_on_click=False,
                        tip="填入 Console 原文 → 弹确认 → 下发 → 自动重采")
        self.add_close_button()

    # ---------------- 选择与联动 ----------------
    def _on_cell_clicked(self, name, ctrl):
        if ctrl:
            if name in self._selected:
                self._selected.remove(name)
            else:
                self._selected.append(name)
        else:
            was = name in self._selected
            self._selected = [] if (was and len(self._selected) == 1) else [name]
        for n, c in self._by_name.items():
            c.set_selected(n in self._selected)
        self._refresh_current()
        self._rebuild_preview()
        self._link_topology()

    def _refresh_current(self):
        """参数卡顶部：选中端口的当前值回显（多选时显示共同值，不一致如实标注）"""
        sel = [self._by_name[n].info for n in self._selected if n in self._by_name]
        if not sel:
            self.cur_lab.setText("👆 点击左侧端口开始")
            return
        if len(sel) == 1:
            i = sel[0]
            lines = [f"<b>{i['name']}</b>"]
            state_txt = {"up": "链路 UP", "down": "链路 DOWN", "trunk": "Trunk",
                         "shutdown": "已手工关闭", "unknown": "状态未知"}[i["state"]]
            lines.append(f"当前: {state_txt}" + (f" · Access V{i['vlan']}" if i["state"] != "trunk" and i["vlan"] else ""))
            if i["state"] == "trunk":
                lines.append(f"当前放行: {i['vlan']}")
            if i["desc"]:
                lines.append(f"描述: {i['desc']}")
            if i["hosts"]:
                lines.append("下挂: " + "、".join(i["hosts"]))
            if i["neighbor"]:
                lines.append(f"对端交换机: {i['neighbor']}")
            self.cur_lab.setText("<br>".join(lines))
        else:
            vlans = {i["vlan"] for i in sel}
            states = {i["state"] for i in sel}
            common = []
            common.append(f"已选 <b>{len(sel)}</b> 个端口（批量）")
            common.append("状态: " + ("、".join(sorted(states)) if len(states) > 1
                                       else f"全部 {sorted(states)[0]}"))
            common.append("当前 VLAN: " + ("多口不一致，改后统一覆盖" if len(vlans) > 1
                                            else f"全部 V{sorted(vlans)[0]}" if list(vlans)[0] else "无"))
            self.cur_lab.setText("<br>".join(common))

    def _link_topology(self):
        """面板选中端口 ↔ 拓扑页联动高亮：交换机节点端口格亮起，对端节点描边"""
        try:
            scene = self.page.scene
            self._clear_topology_link()
            if not self._selected:
                return
            sw = next((n for n in scene.nodes() if n.kind == "switch"), None)
            if sw:
                sw._hover_port = self._selected[0]
                sw.update()
            sel_norm = set()
            for p in self._selected:
                s = (p or "").lower().replace("ten-gigabitethernet", "xge") \
                             .replace("gigabitethernet", "ge").replace(" ", "")
                sel_norm.add(s)
            for n in scene.nodes():
                if n.kind in ("pc", "neighbor", "host", "unknown"):
                    for v in list(n.meta.values()) + [n.subtitle]:
                        s = str(v or "").lower().replace("gigabitethernet", "ge")
                        s = s.replace("ten-gigabitethernet", "xge").replace(" ", "")
                        if s and s in sel_norm:
                            n._active = True
                            n.update()
                            self._activated_nodes.append(n)
                            break
        except RuntimeError:
            pass                                   # 拓扑已重建（重采后节点已销毁）

    def _clear_topology_link(self):
        """还原拓扑联动高亮（面板关闭/重新选择时调用，不留陈旧状态）"""
        try:
            scene = self.page.scene
            for n in self._activated_nodes:
                n._active = False
                n.update()
            self._activated_nodes = []
            sw = next((n for n in scene.nodes() if n.kind == "switch"), None)
            if sw:
                sw._hover_port = ""
                sw.update()
        except RuntimeError:
            pass                                   # 拓扑已重建（节点销毁后 C++ 对象失效）

    def done(self, r):
        self._clear_topology_link()
        super().done(r)

    def closeEvent(self, ev):
        # QDialog 关闭路径与 reject/accept 路径互不重叠，两处都还原高亮
        self._clear_topology_link()
        super().closeEvent(ev)

    # ---------------- 命令生成 ----------------
    def _rebuild_preview(self):
        self._lines = []
        sel = [self._by_name[n].info for n in self._selected if n in self._by_name] \
            if self._by_name else [c.info for c in self._cells
                                   if c.info["name"] in self._selected]
        # 字段有效性红边（无论是否已选端口，填错即时给视觉反馈）
        is_access = self.mode_combo.currentIndex() == 0
        vid = self.vlan_combo.currentText().strip()
        vlan_ok = vid.isdigit() and (1 <= int(vid) <= 4094)
        raw = self.trunk_edit.text().strip()
        try:
            vids = [str(v) for v in expand_vlan_body(raw)] if raw else []
        except Exception:
            vids = []
        self.vlan_combo.setStyleSheet(
            self._vlan_ss_invalid if (is_access and not vlan_ok) else self._vlan_ss_normal)
        self.trunk_edit.setStyleSheet(
            self._line_ss_invalid if (not is_access and not vids) else "")
        if not sel:
            self.preview.setPlainText("")
            return
        vendor = self._vendor
        desc = self.desc_edit.text().strip()
        if self.shut_chk.isChecked() and self.unshut_chk.isChecked():
            self.preview.setPlainText("⚠ 同时勾选了「关闭」与「恢复」，二者互斥，请只选一个")
            self._lines = []
            return
        if is_access:                                 # Access
            if not vlan_ok:
                self.preview.setPlainText("⚠ 请填写有效的 Access VLAN（1-4094）")
                self._lines = []
                return
            for i in sel:
                self._lines += e_port_access(vendor, i["name"], vid)
                self._lines += self._extra_lines(vendor, i["name"], desc)
        else:                                         # Trunk
            if not vids:
                self.preview.setPlainText("⚠ 请填写 Trunk 放行 VLAN，例: 10 20 30 或 999 to 1048")
                self._lines = []
                return
            for i in sel:
                self._lines += e_port_trunk(vendor, i["name"], vids)
                self._lines += self._extra_lines(vendor, i["name"], desc)
        self.preview.setPlainText(
            "\n".join(f"{c}   # {n}" for c, n in self._lines) or "")

    def _extra_lines(self, vendor, port, desc):
        """描述 / shutdown / undo shutdown（跟随接口视图的收尾行）"""
        out = []
        if desc:
            out.append((f" description {desc}", "接口描述（便于运维识别）"))
        if self.shut_chk.isChecked():
            out.append((" shutdown" if vendor in ("huawei", "h3c") else " shutdown",
                        "手工关闭端口"))
        if self.unshut_chk.isChecked():
            out.append((" undo shutdown" if vendor in ("huawei", "h3c") else " no shutdown",
                         "恢复链路"))
        return out

    def _plain_cmds(self):
        return "\n".join(c for c, _ in self._lines)

    # ---------------- 动作 ----------------
    def _copy_cmds(self):
        if not self._lines:
            warn_box(self, "复制命令", "还没有可复制的命令——请先选中端口并填好参数")
            return
        QApplication.clipboard().setText(self._plain_cmds())

    def _apply_to_device(self):
        """一键应用：命令填入 Console 原文 → 跳 Console 页 → deploy_to_device
        （自带二次确认 + 下发 + 自动重采闭环）；确认下发后关闭面板（避免陈旧数据
        误导，重采后重新打开即最新状态）；用户取消则面板保留可继续调整"""
        if not self._lines:
            warn_box(self, "应用到设备", "还没有可应用的命令——请先选中端口并填好参数")
            return
        main = self.page.window()
        cv = getattr(main, "tabs", {}).get("console_viz") if main else None
        if cv is None:
            warn_box(self, "应用到设备", "找不到 Console 页")
            return
        cv.raw_view.setPlainText(self._plain_cmds())
        self.page._goto("Console 可视化")
        cv.deploy_to_device()          # 弹确认；用户取消则什么都不会发生
        worker = getattr(cv, "_worker", None)
        if worker is not None and worker.isRunning():
            self.close()               # 已确认下发：面板即将被重采刷新，关掉避免陈旧误导
