#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
网络拓扑可视化页（二开重构 v2：可交互的运维驾驶舱）

数据源（全部只读采集）：
  1) LLDP 邻居  —— 只能发现"开了 LLDP 的网管设备"（交换机/路由器）
  2) MAC 地址表 —— 发现接在端口上的终端（PC/打印机/摄像头），终端不应答 LLDP
  3) ARP 表     —— 给终端补 IP，便于 Ping / 定位
  4) 本机信息   —— 始终绘制「本机 PC」节点，并把 Console 线画成一条链路

交互：
  - 单击选中、拖动移动、滚轮缩放、空白处拖动平移
  - 双击 / 右键 → 设备面板：端口配置 / 查看配置 / 健康度 / 端口表 / Ping / 备份 / 复制
  - 「一键采集」：不离开本页直接发起 Console 采集
Qt 原生图形框架实现，不重复造绘图轮子
"""

import math

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import (QBrush, QColor, QFont, QFontMetrics, QPainter,
                         QPainterPath, QPen)
from PyQt5.QtWidgets import (QApplication, QAbstractItemView, QCheckBox, QComboBox,
                              QDialog, QDialogButtonBox, QFormLayout,
                              QGraphicsItem, QGraphicsObject, QGraphicsScene,
                              QGraphicsTextItem, QGraphicsView, QGroupBox,
                              QHBoxLayout, QLabel, QLineEdit, QListWidget,
                              QListWidgetItem, QMenu, QMessageBox,
                              QPushButton, QSpinBox, QTableWidget,
                              QTableWidgetItem, QTextEdit,
                              QVBoxLayout, QWidget, QHeaderView)

from gui.styles import MODERN_STYLE, TOOLTIP_STYLE, DIALOG_STYLE
from modules.config_visualizer import expand_vlan_body
from modules.nl_engine import e_port_access, e_port_trunk

# ---------------------------------------------------------------- 视觉规范
KIND_STYLE = {
    #          填充        描边        主文字     副文字
    "switch":      ("#0089FF", "#0072D6", "#FFFFFF", "#D9ECFF"),
    "placeholder": ("#F7F9FC", "#C9D4E3", "#7A8699", "#9AA7B8"),
    "neighbor":    ("#FFFFFF", "#0089FF", "#1F2A37", "#7A8699"),
    "pc":          ("#34C759", "#2BA84E", "#FFFFFF", "#DDF6E4"),
    "host":        ("#FFFFFF", "#8E9AAF", "#1F2A37", "#7A8699"),
    "unknown":     ("#F7F9FC", "#C9D4E3", "#5A6B82", "#9AA7B8"),
}
NODE_ICON_W, NODE_ICON_H = 88, 58


def _short_port(port: str) -> str:
    """长端口名缩写：GigabitEthernet1/0/12 → GE1/0/12（节点下方标签用）"""
    p = port or ""
    for full, abbr in (("Ten-GigabitEthernet", "XGE"),
                      ("FortyGigE", "FGE"),
                      ("GigabitEthernet", "GE"),
                      ("FastEthernet", "Fa"),
                      ("Ethernet", "Eth"),
                      ("Bridge-Aggregation", "BAGG"),
                      ("Port-channel", "Po")):
        p = p.replace(full, abbr)
    return p


def _norm_port(p: str) -> str:
    """端口名归一化（大小写/全称与缩写/空格差异 → 可比对）"""
    s = (p or "").strip().lower().replace(" ", "")
    for full, abbr in (("ten-gigabitethernet", "xge"), ("fortygige", "fge"),
                       ("m-gigabitethernet", "mge"), ("gigabitethernet", "ge"),
                       ("fastethernet", "fa"), ("ethernet", "eth")):
        s = s.replace(full, abbr)
    return s


def _usable_ip(v: str) -> str:
    """可用 IP 提取：占位值（未获取/—/空）不算 IP
    （真机实测：终端无 ARP 数据时 meta 存“未获取”，若不拦会生成「Ping 未获取」菜单项）"""
    v = (v or "").split()[0] if (v or "").strip() else ""
    return "" if v in ("", "未获取", "—", "-") else v


# ---------------------------------------------------------------- 连线
class LinkItem(QGraphicsItem):
    """两端节点之间的连线（位置实时跟随节点，无需重建）"""

    def __init__(self, a, b, label="", dashed=False):
        super().__init__()
        self.a, self.b = a, b
        self.label = label or ""
        self.dashed = dashed
        self.setZValue(-1)
        a.links.append(self)
        b.links.append(self)
        scene = a.scene() or b.scene()
        if scene is not None:
            scene.addItem(self)   # 必须入场景，否则画不出来

    def boundingRect(self):
        pa, pb = self.a.scenePos(), self.b.scenePos()
        return QRectF(pa, pb).normalized().adjusted(-110, -50, 110, 50)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        pa, pb = self.a.scenePos(), self.b.scenePos()
        pen = QPen(QColor("#AEBACB"), 2)
        if self.dashed:
            pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        painter.drawLine(pa, pb)
        if not self.label:
            return
        mid = (pa + pb) / 2
        font = QFont("Microsoft YaHei UI", 9)
        fm = QFontMetrics(font)
        tw = fm.horizontalAdvance(self.label) + 14
        th = fm.height() + 4
        rect = QRectF(mid.x() - tw / 2, mid.y() - th - 10, tw, th)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 232))
        painter.drawRoundedRect(rect, 7, 7)
        painter.setPen(QColor("#7A8699"))
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignCenter, self.label)

    def refresh(self):
        self.prepareGeometryChange()
        self.update()


# ---------------------------------------------------------------- 节点
class DeviceNode(QGraphicsObject):
    """可拖动设备节点（交换机 / PC / 邻居 / 终端），带矢量图标与悬停反馈"""

    def __init__(self, name, kind="switch", meta=None, subtitle=""):
        super().__init__()
        self.device_name = name or "设备"
        self.kind = kind
        self.meta = meta or {}
        self.subtitle = subtitle or ""
        self.links = []
        self._hover = False
        self._active = False

        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setZValue(2)
        self.setToolTip(self._tooltip())

        f_name = QFont("Microsoft YaHei UI", 10)
        f_name.setBold(True)
        fm = QFontMetrics(f_name)
        fm2 = QFontMetrics(QFont("Microsoft YaHei UI", 9))
        self._w = max(NODE_ICON_W, fm.horizontalAdvance(self.device_name) + 8,
                      fm2.horizontalAdvance(self.subtitle) + 8 if self.subtitle else 0)

    # ---- 几何 ----
    def boundingRect(self):
        half = self._w / 2 + 12
        return QRectF(-half, -NODE_ICON_H / 2 - 14, half * 2, NODE_ICON_H + 76)

    def _tooltip(self):
        lines = [f"{self.device_name}"]
        if self.subtitle:
            lines.append(self.subtitle)
        lines += [f"{k}: {v}" for k, v in self.meta.items() if v]
        lines.append("双击/右键 → 设备面板")
        return "\n".join(lines)

    # ---- 绘制 ----
    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        fill, border = KIND_STYLE.get(self.kind, KIND_STYLE["host"])[:2]
        fill, border = QColor(fill), QColor(border)
        if self.kind in ("placeholder", "unknown"):
            pen = QPen(border, 2, Qt.DashLine)
        elif self._hover or self._active:
            pen = QPen(QColor("#0089FF") if self.kind != "host" else QColor("#5A6B82"), 3)
        else:
            pen = QPen(border, 2)

        painter.setPen(pen)
        painter.setBrush(QBrush(fill))
        self._draw_icon(painter, fill, border)

        # 名称（在图标下方，始终用深色，避免白字画在白底上不可见）
        f = QFont("Microsoft YaHei UI", 10)
        f.setBold(True)
        painter.setFont(f)
        painter.setPen(QColor("#1F2A37"))
        painter.drawText(QRectF(-self._w / 2, NODE_ICON_H / 2 + 2, self._w, 20),
                         Qt.AlignHCenter | Qt.AlignVCenter, self.device_name)

        # 副标题（端口 / 型号 / 说明）
        if self.subtitle:
            painter.setFont(QFont("Microsoft YaHei UI", 9))
            painter.setPen(QColor("#7A8699"))
            painter.drawText(QRectF(-self._w / 2, NODE_ICON_H / 2 + 22, self._w, 18),
                             Qt.AlignHCenter | Qt.AlignVCenter, self.subtitle)

        # 选中环
        if self.isSelected():
            painter.setPen(QPen(QColor("#0089FF"), 2, Qt.DotLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(
                QRectF(-self._w / 2 - 8, -NODE_ICON_H / 2 - 12,
                       self._w + 16, NODE_ICON_H + 22), 14, 14)

    def _draw_icon(self, painter, fill, border):
        """按设备类型画矢量图标（不依赖任何图片资源）"""
        if self.kind == "pc":
            # 显示器 + 支架
            screen = QRectF(-34, -26, 68, 46)
            painter.drawRoundedRect(screen, 7, 7)
            painter.setBrush(QBrush(fill))
            painter.drawRect(QRectF(-7, 20, 14, 7))
            painter.drawRoundedRect(QRectF(-20, 26, 40, 6), 3, 3)
            # 屏幕内容线
            painter.setPen(QPen(QColor(255, 255, 255, 150), 2))
            for i, y in enumerate((-15, -6, 3)):
                painter.drawLine(QPointF(-24, y), QPointF(-24 + (40 if i != 1 else 26), y))
        elif self.kind == "host":
            # 终端小方盒
            body = QRectF(-30, -22, 60, 40)
            painter.drawRoundedRect(body, 8, 8)
            painter.setPen(QPen(QColor("#8E9AAF"), 2))
            painter.drawLine(QPointF(-18, 8), QPointF(18, 8))
        else:
            # 交换机：圆角机身 + 端口指示灯
            body = QRectF(-40, -26, 80, 50)
            painter.drawRoundedRect(body, 12, 12)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(255, 255, 255, 210) if self.kind == "switch"
                                    else QColor("#C9D4E3")))
            for row in range(2):
                for i in range(6):
                    painter.drawRoundedRect(
                        QRectF(-34 + i * 11.5, 2 + row * 9, 7, 6), 1.5, 1.5)
            if self.kind == "switch":
                painter.setBrush(QBrush(QColor("#7CF29B")))
                painter.drawEllipse(QRectF(26, -20, 7, 7))

    # ---- 交互 ----
    def hoverEnterEvent(self, event):
        self._hover = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hover = False
        self.update()
        super().hoverLeaveEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            for link in self.links:
                link.refresh()
        return super().itemChange(change, value)

    def mouseDoubleClickEvent(self, event):
        cb = getattr(self.scene(), "on_node_activated", None)
        if cb:
            cb(self)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        cb = getattr(self.scene(), "on_node_menu", None)
        if cb:
            cb(self, event.screenPos())
            event.accept()
            return
        super().contextMenuEvent(event)


# ---------------------------------------------------------------- 场景
class TopologyScene(QGraphicsScene):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.on_node_activated = None   # 双击回调
        self.on_node_menu = None        # 右键回调

    def nodes(self):
        return [i for i in self.items() if isinstance(i, DeviceNode)]

    def auto_layout(self):
        """自动布局：交换机居中，本机 PC 在左，邻居在右，终端在下方一行"""
        nodes = self.nodes()
        if not nodes:
            return
        sw = next((n for n in nodes if n.kind in ("switch", "placeholder")), None)
        pc = next((n for n in nodes if n.kind == "pc"), None)
        # 未识别设备与 LLDP 邻居同属下游设备，统一排到右侧
        # （若不处理，unknown 节点会停留在 (0,0) 与交换机重叠，遮住悬停/拖动手势）
        nbs = [n for n in nodes if n.kind in ("neighbor", "unknown")]
        hosts = [n for n in nodes if n.kind == "host"]

        if sw:
            sw.setPos(0, 0)
        if pc:
            pc.setPos(-300, -10)

        if nbs:
            n = len(nbs)
            radius = 240
            for i, node in enumerate(nbs):
                if n == 1:
                    ang = 0.0
                else:
                    ang = math.radians(-62 + 124 * i / (n - 1))
                node.setPos(140 + radius * math.cos(ang),
                            radius * math.sin(ang) * 0.85)

        if hosts:
            m = len(hosts)
            per_row = 4
            for i, node in enumerate(hosts):
                row, col = divmod(i, per_row)
                in_row = min(per_row, m - row * per_row)
                x = (col - (in_row - 1) / 2) * 196
                node.setPos(x, 200 + row * 124)

        views = self.views()
        if views:
            views[0].centerOn(0, 20)


# ---------------------------------------------------------------- 画布视图（点阵背景）
class TopologyView(QGraphicsView):
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        # 不开鼠标跟踪时 hover 事件只在按住按键时才产生，悬停高亮会是死的（真机实测发现）
        self.setMouseTracking(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet("QGraphicsView { background: #F7F9FC; border: 1px dashed #D3DBE7;"
                           " border-radius: 12px; }")
        self.setSceneRect(QRectF(-900, -600, 1800, 1200))

    def drawBackground(self, painter, rect):
        painter.fillRect(rect, QColor("#F7F9FC"))
        painter.setPen(QPen(QColor("#E4EAF3"), 1))
        step = 28
        left = int(rect.left()) - int(rect.left()) % step
        top = int(rect.top()) - int(rect.top()) % step
        x = left
        while x < rect.right():
            y = top
            while y < rect.bottom():
                painter.drawPoint(QPointF(x, y))
                y += step
            x += step

    def wheelEvent(self, event):
        factor = 1.12 if event.angleDelta().y() > 0 else 1 / 1.12
        cur = self.transform().m11()
        if 0.45 <= cur * factor <= 2.6:
            self.scale(factor, factor)

    def fit_content(self):
        """缩放到刚好装下全部节点（留边距），文字仍可读"""
        scene = self.scene()
        rect = scene.itemsBoundingRect()
        if rect.isNull() or rect.isEmpty():
            return
        self.fitInView(rect.adjusted(-70, -50, 70, 50), Qt.KeepAspectRatio)
        s = self.transform().m11()
        if s > 1.15:      # 内容很少时不要放太大（放大会跑到左上角）
            self.resetTransform()
        elif s < 0.72:    # 太小就看不清文字了，保证可读性（用户可拖动/缩放）
            f = 0.72 / s
            self.scale(f, f)
        self.centerOn(rect.center())


# ---------------------------------------------------------------- 通用对话框
class DeviceDetailDialog(QDialog):
    """设备面板：信息 + 操作按钮（把运维动作聚合到一处）"""

    def __init__(self, title, subtitle, rows, buttons, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(520)
        self.setStyleSheet(MODERN_STYLE + TOOLTIP_STYLE + DIALOG_STYLE)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.setSpacing(14)

        t = QLabel(title)
        t.setStyleSheet("font-size: 18px; font-weight: bold; color: #1F2A37;")
        lay.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setWordWrap(True)
            s.setStyleSheet("font-size: 13px; color: #7A8699;")
            lay.addWidget(s)

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(9)
        for label, value in rows:
            k = QLabel(f"{label}")
            k.setStyleSheet("color: #7A8699; font-size: 13px;")
            v = QLabel(str(value) if value not in (None, "") else "—")
            v.setWordWrap(True)
            v.setTextInteractionFlags(Qt.TextSelectableByMouse)
            v.setStyleSheet("color: #1F2A37; font-size: 13px;")
            form.addRow(k, v)
        lay.addLayout(form)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        for text, cb, obj in buttons:
            b = QPushButton(text)
            b.setObjectName(obj or "secondaryButton")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, f=cb: (self.accept(), f()))
            btn_row.addWidget(b)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.setObjectName("ghostButton")
        close_btn.clicked.connect(self.reject)
        close_row.addWidget(close_btn)
        lay.addLayout(close_row)


class PortTableDialog(QDialog):
    """端口表：每个口的配置 + 下挂终端（定位"哪个口接了什么东西"）"""

    def __init__(self, rows, parent=None):
        super().__init__(parent)
        self.setWindowTitle("端口一览")
        self.setMinimumSize(760, 520)
        self.setStyleSheet(MODERN_STYLE + TOOLTIP_STYLE + DIALOG_STYLE)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)

        tip = QLabel("按接口列出配置/链路状态/下挂终端（running-config + MAC/ARP 表 + 端口链路状态，只读）")
        tip.setStyleSheet("color: #7A8699; font-size: 12px;")
        lay.addWidget(tip)

        table = QTableWidget(len(rows), 5)
        table.setHorizontalHeaderLabels(["接口", "状态", "描述", "VLAN", "下挂终端"])
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                item = QTableWidgetItem(str(val))
                if c == 1:
                    color = "#34C759" if val == "up" else ("#FA5151" if val == "down" else "#7A8699")
                    item.setForeground(QBrush(QColor(color)))
                table.setItem(r, c, item)
        lay.addWidget(table, 1)

        btn = QPushButton("关闭")
        btn.setObjectName("ghostButton")
        btn.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(btn)
        lay.addLayout(row)


class PortConfigDialog(QDialog):
    """端口级配置生成器（Access/Trunk）——交换机最基础的操作。
    端口列表来自最近一次采集的真实接口（多选），按当前设备厂商语法生成命令；
    只生成不自动下发：命令送 Console「配置原文」框，由用户点「下发到设备」并确认后才写入设备
    （保持只读红线：写入永远走显式确认的下发闭环）。
    布局：左端口右表单底部预览——长文本/长列表左右并列，不上下堆叠压高度。"""

    def __init__(self, ports, vendor, parent=None):
        super().__init__(parent)
        self.setWindowTitle("端口配置（Access / Trunk）")
        self.setMinimumSize(880, 560)
        self.setStyleSheet(MODERN_STYLE + TOOLTIP_STYLE + DIALOG_STYLE)
        self._vendor = vendor or "huawei"
        self._lines = []          # [(cmd, 中文释义)]

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)

        tip = QLabel(f"多选左侧端口 → 按当前设备厂商（{self._vendor}）语法生成命令；"
                     "「送往下发」会填入 Console 页，点「下发到设备」确认后才写入设备")
        tip.setStyleSheet("color: #7A8699; font-size: 12px;")
        tip.setWordWrap(True)
        lay.addWidget(tip)

        body = QHBoxLayout()
        body.setSpacing(14)

        # ---- 左：真实端口列表（多选；短行长列表适合窄栏） ----
        left = QVBoxLayout()
        left.setSpacing(6)
        left_lab = QLabel("端口（可多选 · 来自最近一次采集）")
        left_lab.setStyleSheet("font-weight: bold;")
        left.addWidget(left_lab)
        self.port_list = QListWidget()
        self.port_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.port_list.setAlternatingRowColors(True)
        self.port_list.setStyleSheet("QListWidget::item { padding: 6px 4px; }")
        for name, hint in ports:
            it = QListWidgetItem(name if not hint else f"{name}  ·  {hint}")
            it.setData(Qt.UserRole, name)
            it.setToolTip(hint)
            self.port_list.addItem(it)
        left.addWidget(self.port_list, 1)
        sel_row = QHBoxLayout()
        sel_all = QPushButton("全选")
        sel_all.setObjectName("ghostButton")
        sel_all.clicked.connect(self.port_list.selectAll)
        sel_none = QPushButton("清空")
        sel_none.setObjectName("ghostButton")
        sel_none.clicked.connect(self.port_list.clearSelection)
        sel_row.addWidget(sel_all)
        sel_row.addWidget(sel_none)
        sel_row.addStretch()
        left.addLayout(sel_row)
        body.addLayout(left, 2)

        # ---- 右：配置表单 ----
        right = QVBoxLayout()
        right.setSpacing(10)
        form = QFormLayout()
        form.setSpacing(8)

        self.type_combo = QComboBox()
        self.type_combo.addItems(["Access（接入口）", "Trunk（干道口）"])
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        form.addRow("链路类型:", self.type_combo)

        self.access_vlan = QSpinBox()
        self.access_vlan.setRange(1, 4094)
        self.access_vlan.setValue(1)
        form.addRow("Access VLAN:", self.access_vlan)

        self.trunk_vlans = QLineEdit()
        self.trunk_vlans.setPlaceholderText("放行 VLAN，空格分隔，支持 to，例：1 5 999 to 1048")
        self.trunk_vlans.setEnabled(False)
        form.addRow("Trunk 放行:", self.trunk_vlans)

        self.desc_edit = QLineEdit()
        self.desc_edit.setPlaceholderText("可选，例：dT:打印机")
        form.addRow("接口描述:", self.desc_edit)

        self.shut_check = QCheckBox("同时关闭端口（生成的命令里带 shutdown）")
        form.addRow("", self.shut_check)

        right.addLayout(form)

        gen_btn = QPushButton("⚙ 生成命令")
        gen_btn.setObjectName("primaryButton")
        gen_btn.clicked.connect(self.generate)
        right.addWidget(gen_btn)

        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("生成的命令（带中文释义）显示在这里")
        right.addWidget(self.preview, 1)
        body.addLayout(right, 3)

        lay.addLayout(body, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.copy_btn = QPushButton("📋 复制纯命令")
        self.copy_btn.setObjectName("secondaryButton")
        self.copy_btn.clicked.connect(self.copy_commands)
        self.send_btn = QPushButton("⤴ 送往下发（Console 页）")
        self.send_btn.setObjectName("primaryButton")
        self.send_btn.clicked.connect(self.send_to_deploy)
        close_btn = QPushButton("关闭")
        close_btn.setObjectName("ghostButton")
        close_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(self.copy_btn)
        btn_row.addWidget(self.send_btn)
        btn_row.addWidget(close_btn)
        lay.addLayout(btn_row)

    def _on_type_changed(self, idx):
        self.access_vlan.setEnabled(idx == 0)
        self.trunk_vlans.setEnabled(idx != 0)

    def _plain(self):
        return "\n".join(cmd for cmd, _ in self._lines)

    def generate(self):
        ports = [it.data(Qt.UserRole) for it in self.port_list.selectedItems()]
        if not ports:
            QMessageBox.warning(self, "端口配置", "请先在左侧选择端口（按住 Ctrl/Shift 可多选）")
            return
        mode = "access" if self.type_combo.currentIndex() == 0 else "trunk"
        desc = self.desc_edit.text().strip()
        lines = []
        for p in ports:
            if mode == "access":
                lines += e_port_access(self._vendor, p, str(self.access_vlan.value()))
            else:
                raw = self.trunk_vlans.text().strip()
                if not raw:
                    QMessageBox.warning(self, "端口配置", "Trunk 需要填写放行 VLAN（如：1 5 999 to 1048）")
                    return
                vids = [str(v) for v in expand_vlan_body(raw)]
                lines += e_port_trunk(self._vendor, p, vids)
            if desc:
                lines.append((f" description {desc}", "接口描述（便于运维识别）"))
            if self.shut_check.isChecked():
                lines.append((" shutdown", "手工关闭端口"))
        self._lines = lines
        self.preview.setPlainText("\n".join(f"{c}   # {n}" for c, n in lines))

    def copy_commands(self):
        if not self._lines:
            QMessageBox.warning(self, "端口配置", "请先点「生成命令」")
            return
        QApplication.clipboard().setText(self._plain())
        QMessageBox.information(self, "端口配置", f"已复制 {len(self._lines)} 行纯命令（无注释），可直接粘贴")

    def send_to_deploy(self):
        """把生成的命令填入 Console 页「配置原文」框并跳转；真正的写入仍需用户点「下发到设备」确认"""
        if not self._lines:
            QMessageBox.warning(self, "端口配置", "请先点「生成命令」")
            return
        page = self.parent()          # NetworkTopologyPage
        main = page.window() if page else None
        cv = getattr(main, "tabs", {}).get("console_viz") if main else None
        if cv is None:
            QMessageBox.information(self, "端口配置", "未找到 Console 页（主窗口未就绪）")
            return
        if QMessageBox.question(
                self, "送往下发",
                f"将把 {len(self._lines)} 行命令填入 Console 页「配置原文」框（替换当前内容），\n"
                "随后请在该页点「下发到设备」并确认——是否继续？") != QMessageBox.Yes:
            return
        cv.raw_view.setPlainText(self._plain())
        page._goto("Console 可视化")
        self.accept()


class AddDeviceDialog(QDialog):
    """手工添加设备（没有 LLDP 时也能把真实网络画出来）"""

    TYPES = ["交换机", "PC / 服务器", "路由器", "防火墙", "AP / 其他"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("添加设备")
        self.setMinimumWidth(460)
        self.setStyleSheet(MODERN_STYLE + TOOLTIP_STYLE + DIALOG_STYLE)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("例如：办公区接入交换机 / 前台PC")
        self.type_combo = QComboBox()
        self.type_combo.addItems(self.TYPES)
        self.ip_edit = QLineEdit()
        self.ip_edit.setPlaceholderText("可选，用于 Ping / SSH")
        self.port_edit = QLineEdit()
        self.port_edit.setPlaceholderText("可选，例如 GE1/0/8")
        self.note_edit = QLineEdit()
        self.note_edit.setPlaceholderText("可选，备注")
        form.addRow("名称", self.name_edit)
        form.addRow("类型", self.type_combo)
        form.addRow("管理 IP", self.ip_edit)
        form.addRow("接入端口", self.port_edit)
        form.addRow("备注", self.note_edit)
        lay.addLayout(form)

        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.button(QDialogButtonBox.Ok).setText("添加")
        box.button(QDialogButtonBox.Cancel).setText("取消")
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)
        self.name_edit.setFocus()

    def data(self):
        return {
            "name": self.name_edit.text().strip() or "新设备",
            "type": self.type_combo.currentText(),
            "ip": self.ip_edit.text().strip(),
            "port": self.port_edit.text().strip(),
            "note": self.note_edit.text().strip(),
        }


# ---------------------------------------------------------------- 主页面
class NetworkTopologyPage(QWidget):
    """网络拓扑（可视化运维入口）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = {}          # 最近一次采集结果
        self._sw_node = None
        self._pc_node = None
        self._manual = []        # 手工添加的节点
        self.initUI()
        self.clear_config()

    # ---------------- UI ----------------
    def initUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        bar.addStretch(1)

        collect_btn = QPushButton("🔌 一键采集")
        collect_btn.setObjectName("primaryButton")
        collect_btn.setToolTip("在当前页直接通过 Console 线采集交换机信息")
        collect_btn.clicked.connect(self.collect_now)

        help_btn = QPushButton("为什么只有自己？")
        help_btn.setObjectName("ghostButton")
        help_btn.setToolTip("说明拓扑的数据来源与发现不到设备的原因")
        help_btn.clicked.connect(self.show_why)

        add_btn = QPushButton("＋ 添加设备")
        add_btn.setObjectName("secondaryButton")
        add_btn.clicked.connect(self.add_manual_node)

        ports_btn = QPushButton("端口一览")
        ports_btn.setObjectName("secondaryButton")
        ports_btn.setToolTip("查看每个接口的配置和下挂终端")
        ports_btn.clicked.connect(self.show_port_table)

        layout_btn = QPushButton("自动布局")
        layout_btn.setObjectName("secondaryButton")
        layout_btn.clicked.connect(lambda: self.scene.auto_layout())

        fit_btn = QPushButton("适应窗口")
        fit_btn.setObjectName("ghostButton")
        fit_btn.clicked.connect(lambda: self.view.fit_content())

        for w in (collect_btn, help_btn, add_btn, ports_btn, layout_btn, fit_btn):
            bar.addWidget(w)
        layout.addLayout(bar)

        canvas_group = QGroupBox("拓扑视图")
        canvas_lay = QVBoxLayout(canvas_group)
        canvas_lay.setContentsMargins(10, 26, 10, 10)
        self.scene = TopologyScene(self)
        self.view = TopologyView(self.scene)
        canvas_lay.addWidget(self.view)
        layout.addWidget(canvas_group, 1)

        self.status_label = QLabel("尚未连接交换机 —— 点「🔌 一键采集」开始")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #5A6B82; font-size: 13px; font-weight: bold;")
        layout.addWidget(self.status_label)

        self.hint_label = QLabel(
            "💡 双击节点打开设备面板 ｜ 右键节点选择操作 ｜ 拖动节点移动 ｜ 滚轮缩放 ｜ 空白处拖动平移")
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet("color: #9AA7B8; font-size: 12px;")
        layout.addWidget(self.hint_label)

        self.scene.on_node_activated = self.open_device_panel
        self.scene.on_node_menu = self._show_node_menu

    # ---------------- 契约方法（主窗口切换品牌时会调用） ----------------
    def clear_config(self):
        """清空拓扑，回到空状态（不报错、不残留）"""
        self._data = {}
        self._sw_node = None
        self._pc_node = None
        self._manual = []
        self.scene.clear()
        self._build_empty_state()

    def _build_empty_state(self):
        from modules.host_info import local_host
        host = local_host()
        ips = [i for i in host["ips"] if not i.startswith("169.254.")] or host["ips"]
        self._pc_node = DeviceNode(host["name"], "pc",
                                   meta={"IP": (ips[0] if ips else "未获取"),
                                         "角色": "运维终端（本机）"},
                                   subtitle="本机 PC")
        self._sw_node = DeviceNode("交换机（未采集）", "placeholder",
                                   meta={"说明": "点右上角「一键采集」读取设备"},
                                   subtitle="等待连接")
        self.scene.addItem(self._pc_node)
        self.scene.addItem(self._sw_node)
        LinkItem(self._pc_node, self._sw_node, "Console 线", dashed=True)
        self._pc_node.setPos(-300, -10)
        self._sw_node.setPos(0, 0)
        self.status_label.setText("尚未连接交换机 —— 点「🔌 一键采集」开始")
        self.view.fit_content()

    # ---------------- 采集入口 ----------------
    def collect_now(self):
        """不离开本页直接采集：调用 Console 页的采集流程（复用同一套逻辑）"""
        main = self.window()
        tab_widget = getattr(main, "tab_widget", None)
        console = getattr(main, "tabs", {}).get("console_viz") if hasattr(main, "tabs") else None
        if tab_widget is None or console is None:
            QMessageBox.information(self, "提示", "未找到 Console 采集页")
            return
        # 切到 Console 页，让用户看到进度与日志
        for i in range(tab_widget.count()):
            if tab_widget.tabText(i) == "Console 可视化":
                tab_widget.setCurrentIndex(i)
                break
        console.start_read()
        self.status_label.setText("正在采集…（进度见 Console 可视化页）")

    # ---------------- 数据填充 ----------------
    def load_topology(self, local_name="", local_meta=None, neighbors=None,
                      end_hosts=None, parsed=None, raw_config="",
                      console_port="", vendor="", health=None, link_up=None):
        """Console/SSH 采集完成后调用，重绘整张拓扑"""
        neighbors = neighbors or []
        end_hosts = end_hosts or []
        local_meta = dict(local_meta or {})
        parsed = parsed or {}
        link_up = link_up or {}
        self._data = {
            "name": local_name, "meta": local_meta, "neighbors": neighbors,
            "hosts": end_hosts, "parsed": parsed, "raw": raw_config,
            "port": console_port, "vendor": vendor, "health": health,
            "link_up": link_up,
        }

        self.scene.clear()
        self._manual = []

        from modules.host_info import local_host, normalize_mac
        me = local_host()
        my_macs = {normalize_mac(m) for m in me["macs"]}

        # 本机 PC（始终存在）；IP 取首个非链路本地地址——右键 Ping 要直接可用
        pc_name = me["name"] or "本机 PC"
        pc_ips = [i for i in me["ips"] if not i.startswith("169.254.")] or me["ips"]
        self._pc_node = DeviceNode(pc_name, "pc",
                                   meta={"IP": (pc_ips[0] if pc_ips else "未获取"),
                                         "角色": "运维终端（本机）",
                                         "Console": console_port or "—"},
                                   subtitle="本机 PC")
        self.scene.addItem(self._pc_node)

        # 交换机
        meta = dict(local_meta)
        if console_port:
            meta["管理通道"] = f"Console {console_port}"
        n_if = len(parsed.get("interfaces") or [])
        sw_sub = f"{vendor} · {n_if} 个接口" if (vendor and n_if) else (vendor or "")
        sw = DeviceNode(local_name or "交换机", "switch", meta=meta, subtitle=sw_sub)
        self.scene.addItem(sw)
        self._sw_node = sw

        pc_link_label = f"Console {console_port}" if console_port else "Console 线"
        LinkItem(self._pc_node, sw, pc_link_label)

        # LLDP 邻居
        for nb in neighbors:
            name = nb.get("name") or nb.get("peer", "邻居设备")
            node = DeviceNode(name, "neighbor",
                              meta={"对端端口": nb.get("peer_port", ""),
                                    "本地端口": nb.get("port", "")},
                              subtitle=f"经 {nb.get('port', '')}")
            self.scene.addItem(node)
            LinkItem(sw, node, nb.get("port", ""))

        # 终端（来自 MAC/ARP 表）——本机 MAC 的那个就是"本机 PC"
        port_hosts = {}
        for h in end_hosts:
            mac = normalize_mac(h.get("mac", ""))
            is_me = bool(mac) and mac in my_macs
            port = h.get("port", "")
            port_hosts.setdefault(port, []).append(h)
            if is_me:
                self._pc_node.subtitle = f"接入 {_short_port(port)}" if port else "本机 PC"
                self._pc_node.meta["接入端口"] = port
                self._pc_node.meta["MAC"] = h.get("mac_display", "")
                if h.get("ip"):
                    self._pc_node.meta["IP"] = h["ip"]
                # 本机其实是这样连的：撤掉 Console 线，改画接入端口链路
                for item in list(self.scene.items()):
                    if isinstance(item, LinkItem) and item.a is self._pc_node:
                        self.scene.removeItem(item)
                        self._pc_node.links.clear()
                LinkItem(self._pc_node, sw, f"接入 {_short_port(port)}" if port else "直连")
                self._pc_node.setToolTip(self._pc_node._tooltip())
                continue
            label = h.get("ip") or h.get("mac_display", "终端")
            node = DeviceNode(label, "host",
                              meta={"MAC": h.get("mac_display", ""),
                                    "IP": h.get("ip", "") or "未获取",
                                    "接入端口": port,
                                    "VLAN": h.get("vlan", "")},
                              subtitle=f"{_short_port(port)} · VLAN {h.get('vlan') or '-'}")
            self.scene.addItem(node)
            LinkItem(sw, node, "")   # 节点下方已标端口，连线不再重复写

        # 有链路但没有任何发现数据的端口 → 「未识别设备」
        # 真实场景：对端交换机未启用 LLDP（思科等出厂默认关）或哑交换机；
        # 不标出来用户会以为软件坏了，标出来才是“看得见”的运维
        known = set()
        pc_port = self._pc_node.meta.get("接入端口", "")
        if pc_port:
            known.add(_norm_port(pc_port))
        for nb in neighbors:
            known.add(_norm_port(nb.get("port", "")))
        for h in end_hosts:
            known.add(_norm_port(h.get("port", "")))
        skip_kw = ("vlan", "null", "inloop", "reg", "mge", "m-gigabit", "mgigabit",
                   "loopback", "tunnel", "bridge-aggregation", "bagg")
        unknown_ports = [n for n, up in link_up.items()
                         if up and _norm_port(n) not in known
                         and not n.lower().startswith(skip_kw)]
        for i, port in enumerate(unknown_ports, 1):
            label = "未识别设备" if len(unknown_ports) == 1 else f"未识别设备 {i}"
            node = DeviceNode(label, "unknown",
                              meta={"接入端口": port,
                                    "说明": "端口有链路，但对端未响应 LLDP、也没有 MAC/ARP 数据"
                                            "（对端未启用 LLDP 或为非管理型交换机）"},
                              subtitle=f"{_short_port(port)} · 有链路")
            self.scene.addItem(node)
            LinkItem(sw, node, f"{_short_port(port)} · 有链路")

        self.scene.auto_layout()
        self.view.fit_content()
        self._update_status(sw, neighbors, end_hosts, unknown_ports)

    def _update_status(self, sw, neighbors, end_hosts, unknown_ports=None):
        parsed = self._data.get("parsed") or {}
        n_if = len(parsed.get("interfaces") or [])
        n_hosts = len(end_hosts)
        unknown_ports = unknown_ports or []
        parts = [f"交换机：{self._data.get('name') or '未命名'}"]
        if n_if:
            parts.append(f"接口 {n_if}")
        parts.append(f"LLDP 邻居 {len(neighbors)}")
        parts.append(f"发现终端 {n_hosts}")
        if unknown_ports:
            parts.append(f"未识别链路 {len(unknown_ports)} 个")
        if not neighbors:
            parts.append("（终端不会应答 LLDP，靠 MAC 表发现）")
        self.status_label.setText(" ｜ ".join(parts))

        if unknown_ports:
            ports_txt = "、".join(_short_port(p) for p in unknown_ports[:3])
            self.hint_label.setText(
                f"💡 {ports_txt} 有链路但对端未响应 LLDP——对端交换机可能没开 LLDP（思科等出厂默认关），"
                "在对端执行 lldp run / lldp global enable 后再采集即可看到它的型号与端口")
        elif n_hosts == 0:
            self.hint_label.setText(
                "💡 没有发现终端：设备端口上可能没接设备，或终端长期空闲导致 MAC 表项老化。"
                "换台在用的电脑接入后再采集即可看到它。")
        else:
            self.hint_label.setText(
                "💡 双击节点打开设备面板 ｜ 右键节点选择操作 ｜ 拖动节点移动 ｜ 滚轮缩放 ｜ 空白处拖动平移")

    # ---------------- 交互：设备面板 ----------------
    def open_device_panel(self, node):
        rows, buttons = [], []
        kind = node.kind
        rows.append(("设备类型", {"switch": "交换机（本机采集）", "pc": "本机 PC",
                                  "neighbor": "邻居设备", "host": "终端设备",
                                  "unknown": "未识别设备（端口有链路，对端无 LLDP 信息）"}.get(kind, "未知")))
        for k, v in node.meta.items():
            if v not in (None, ""):
                rows.append((k, v))

        if kind in ("switch", "placeholder"):
            buttons = [
                ("端口配置（Access/Trunk）", self.show_port_config, "primaryButton"),
                ("查看完整配置", lambda: self._goto("Console 可视化"), "secondaryButton"),
                ("配置健康度", self._show_health, "secondaryButton"),
                ("端口一览", self.show_port_table, "secondaryButton"),
                ("备份配置", self._backup_config, "secondaryButton"),
            ]
            ip = self._switch_mgmt_ip()
            if ip:
                buttons.append((f"Ping {ip}", lambda: self._ping(ip, node.device_name), "ghostButton"))
        elif kind == "pc":
            buttons = [("Ping 本机", lambda: self._ping(_usable_ip(node.meta.get("IP", "")), node.device_name),
                        "secondaryButton"),
                       ("重新采集", self.collect_now, "primaryButton")]
        else:
            ip = _usable_ip(node.meta.get("IP", ""))
            if ip:
                buttons.append((f"Ping {ip}", lambda: self._ping(ip, node.device_name), "secondaryButton"))
            buttons.append(("复制信息", lambda: self._copy_node(node), "ghostButton"))
            buttons.append(("删除节点", lambda: self._remove_node(node), "ghostButton"))

        DeviceDetailDialog(node.device_name, node.subtitle, rows, buttons, self).exec_()

    def _show_node_menu(self, node, screen_pos):
        menu = QMenu(self)
        menu.addAction("设备面板", lambda: self.open_device_panel(node))
        menu.addSeparator()
        if node.kind in ("switch", "placeholder"):
            menu.addAction("端口配置（Access/Trunk）", self.show_port_config)
            menu.addAction("查看完整配置", lambda: self._goto("Console 可视化"))
            menu.addAction("配置健康度体检", self._show_health)
            menu.addAction("端口一览", self.show_port_table)
            menu.addAction("备份配置到文件", self._backup_config)
            ip = self._switch_mgmt_ip()
            if ip:
                menu.addAction(f"Ping 管理地址 {ip}", lambda: self._ping(ip, node.device_name))
            menu.addSeparator()
            menu.addAction("重新采集", self.collect_now)
        elif node.kind == "pc":
            ip = _usable_ip(node.meta.get("IP", ""))
            if ip:
                menu.addAction(f"Ping {ip}", lambda: self._ping(ip, node.device_name))
            menu.addAction("重新采集", self.collect_now)
            menu.addAction("复制本机信息", lambda: self._copy_node(node))
        else:
            ip = _usable_ip(node.meta.get("IP", ""))
            if ip:
                menu.addAction(f"Ping {ip}", lambda: self._ping(ip, node.device_name))
            menu.addAction("复制设备信息", lambda: self._copy_node(node))
            menu.addAction("删除该节点", lambda: self._remove_node(node))
        menu.exec_(screen_pos)

    # ---------------- 动作 ----------------
    def _goto(self, title):
        main = self.window()
        tw = getattr(main, "tab_widget", None)
        if tw is None:
            return
        for i in range(tw.count()):
            if tw.tabText(i) == title:
                tw.setCurrentIndex(i)
                return

    def _switch_mgmt_ip(self):
        """管理 IP：优先配置里的 Vlan-interface IP"""
        for itf in (self._data.get("parsed") or {}).get("interfaces") or []:
            if itf["name"].lower().startswith(("vlan", "vlanif")):
                ip = (itf.get("detail") or {}).get("IP", "")
                if ip:
                    return ip.split()[0]
        return ""

    def _show_health(self):
        health = self._data.get("health")
        if not health:
            QMessageBox.information(
                self, "配置健康度",
                "还没有体检数据。\n\n请先点「🔌 一键采集」读取交换机配置，"
                "系统会按等保/基线自动打分。")
            return
        rows = [("健康度评分", f"{health.get('score')} 分（{health.get('level')}）")]
        st = health.get("stats", {})
        rows.append(("统计", f"严重 {st.get('严重', 0)} · 警告 {st.get('警告', 0)} · "
                             f"提示 {st.get('提示', 0)} · 通过 {st.get('通过', 0)}"))
        for it in health.get("items", []):
            if it.get("level") in ("严重", "警告"):
                rows.append((it.get("level"), f"{it.get('domain')} · {it.get('item')}"))
        DeviceDetailDialog("配置健康度体检", "按等保与厂商基线对当前运行配置打分（只读分析）",
                           rows, [("查看完整配置", lambda: self._goto("Console 可视化"),
                                   "primaryButton")], self).exec_()

    def show_port_table(self):
        parsed = (self._data.get("parsed") or {})
        ifaces = parsed.get("interfaces") or []
        if not ifaces:
            QMessageBox.information(self, "端口一览",
                                    "还没有接口数据。\n\n请先点「🔌 一键采集」。")
            return
        # 端口 → 下挂终端
        by_port = {}
        for h in self._data.get("hosts") or []:
            by_port.setdefault(h.get("port", ""), []).append(h)

        # 真实链路状态（display interface brief，采集时一并抓取）——有实时值优先用实时值
        link_up = self._data.get("link_up") or {}
        live_map = {_norm_port(k): v for k, v in link_up.items()}

        def norm(p):
            return (p or "").lower().replace("gigabitethernet", "ge").replace(" ", "")

        rows = []
        for itf in ifaces:
            d = itf.get("detail") or {}
            live = live_map.get(_norm_port(itf["name"]))
            if live is True:
                status = "up"
            elif live is False:
                status = "down"
            else:
                status = "down" if d.get("状态") else ("up" if d.get("描述") or d.get("IP")
                                                       or d.get("VLAN") else "—")
            hosts = by_port.get(itf["name"], [])
            rows.append([
                itf["name"], status, d.get("描述", ""),
                d.get("VLAN", "") or d.get("IP", ""),
                "、".join((h.get("ip") or h.get("mac_display", "")) for h in hosts) or "—",
            ])
        # 端口名大小写/别名不一致时，补一遍宽松匹配
        for r, itf in zip(rows, ifaces):
            if r[4] == "—":
                for p, hs in by_port.items():
                    if norm(p) == norm(itf["name"]):
                        r[4] = "、".join((h.get("ip") or h.get("mac_display", "")) for h in hs)
                        break
        PortTableDialog(rows, self).exec_()

    def show_port_config(self):
        """端口级配置（Access/Trunk）：交换机最基础的操作。
        用采集到的真实端口列表 + 当前厂商语法生成命令，经 Console 下发闭环写回设备"""
        parsed = (self._data.get("parsed") or {})
        ifaces = parsed.get("interfaces") or []
        if not ifaces:
            QMessageBox.information(
                self, "端口配置",
                "还没有接口数据。\n\n请先点「🔌 一键采集」，端口列表会自动带出。")
            return
        # 只列物理/聚合端口（SVI、NULL、管理口不参与 access/trunk 划分）
        skip = ("vlan", "vlanif", "null", "m-gigabit", "mgigabit", "loopback", "inloop")
        ports = []
        for itf in ifaces:
            name = itf["name"]
            if name.lower().startswith(skip):
                continue
            d = itf.get("detail") or {}
            bits = []
            if d.get("VLAN"):
                bits.append(f"VLAN {d['VLAN']}")
            if d.get("IP"):
                bits.append(d["IP"])
            if d.get("描述"):
                bits.append(d["描述"])
            ports.append((name, " · ".join(bits)))
        if not ports:
            QMessageBox.information(self, "端口配置", "未解析出可配置的物理端口。")
            return
        # 注意：_data["vendor"] 存的是显示标签（如 "H3C"），发射器按小写厂商键匹配，
        # 必须小写化——否则语法分支全部落空、误走思科兜底
        vendor = (self._data.get("vendor") or "huawei").lower()
        PortConfigDialog(ports, vendor, self).exec_()

    def _backup_config(self):
        raw = self._data.get("raw") or ""
        if not raw:
            QMessageBox.information(self, "备份配置", "还没有采集到配置，请先「🔌 一键采集」。")
            return
        from PyQt5.QtWidgets import QFileDialog
        import time as _t
        name = (self._data.get("name") or "switch").replace(" ", "_")
        default = f"{name}_running_{_t.strftime('%Y%m%d_%H%M%S')}.cfg"
        path, _ = QFileDialog.getSaveFileName(self, "备份配置", default,
                                              "配置文件 (*.cfg);;文本 (*.txt);;所有文件 (*)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(raw)
            QMessageBox.information(self, "备份完成", f"已保存到：\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "备份失败", f"{type(e).__name__}: {e}")

    def _ping(self, ip, name="设备"):
        ip = _usable_ip(ip)
        if not ip:
            QMessageBox.information(self, "Ping", "该设备没有可用的 IP 地址")
            return
        try:
            from gui.tools.ping_tool import PingTestWidget
        except Exception as e:
            QMessageBox.warning(self, "Ping", f"Ping 工具不可用：{e}")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Ping {name}（{ip}）")
        dlg.setMinimumSize(780, 560)
        dlg.setStyleSheet(MODERN_STYLE + TOOLTIP_STYLE + DIALOG_STYLE)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(14, 14, 14, 14)
        w = PingTestWidget()
        if hasattr(w, "host_input"):
            w.host_input.setText(ip)
        lay.addWidget(w)
        dlg.exec_()

    def _copy_node(self, node):
        from PyQt5.QtWidgets import QApplication
        text = node.device_name + "\n" + "\n".join(
            f"{k}: {v}" for k, v in node.meta.items() if v)
        QApplication.clipboard().setText(text)
        self.status_label.setText(f"已复制「{node.device_name}」的信息到剪贴板")

    def _remove_node(self, node):
        if node is self._sw_node or node is self._pc_node:
            QMessageBox.information(self, "提示", "交换机与本机节点是采集结果，不能删除")
            return
        for link in list(node.links):
            if link.scene() is not None:
                link.scene().removeItem(link)
            for other in (link.a, link.b):
                if link in getattr(other, "links", []):
                    other.links.remove(link)
        if node.scene() is not None:
            node.scene().removeItem(node)

    # ---------------- 手工添加 ----------------
    def add_manual_node(self):
        dlg = AddDeviceDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        d = dlg.data()
        kind = "pc" if "PC" in d["type"] or "服务器" in d["type"] else "host"
        meta = {"管理 IP": d["ip"], "接入端口": d["port"], "类型": d["type"], "备注": d["note"]}
        node = DeviceNode(d["name"], kind, meta=meta,
                          subtitle=d["port"] or d["ip"] or d["type"])
        self.scene.addItem(node)
        self._manual.append(node)
        anchor = self._sw_node or self._pc_node
        if anchor is not None:
            LinkItem(anchor, node, d["port"])
        node.setPos(160, 200 + 110 * (len(self._manual) - 1))
        self.view.fit_content()

    # ---------------- 说明 ----------------
    def show_why(self):
        DeviceDetailDialog(
            "为什么图上设备这么少？",
            "拓扑不是「扫描」出来的，而是从设备上「读」出来的——读不到的就画不出来。",
            [
                ("LLDP 邻居", "只能发现开启并运行 LLDP 的网管设备（交换机/路由器/AP）。"
                             "Windows 电脑、打印机、手机不应答 LLDP，所以永远不会以邻居身份出现。"),
                ("终端设备", "改用 MAC 地址表发现：只要终端在端口上发过帧，交换机就会学到它的 MAC，"
                            "本工具据此把它画成「终端」节点，并可用 ARP 表补上 IP。"),
                ("本机 PC", "始终会画出来（绿色），并用一条线连到交换机：如果你就是通过网线接在这台"
                           "交换机上，会自动标注真实接入端口；只有 Console 线时标注 Console。"),
                ("还是很少？", "端口空着 / 终端长时间空闲导致 MAC 表项老化 / 交换机之间没配 LLDP。"
                             "可以用「＋ 添加设备」把真实存在的设备先画上去。"),
            ],
            [("一键采集", self.collect_now, "primaryButton")], self).exec_()
