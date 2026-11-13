#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
设备面板优化：改用 QGraphicsItem 代替 QPushButton/QWidget，支持脏矩形更新
解决大规模端口（50+）状态刷新时的卡顿问题

原稿由并行会话提供（.temp/device_panel_graphics.py），集成时补齐业务接口：
  - 真实端口名/短标签（原为 Gi{id} 占位）
  - port_clicked 携带端口全名（原 int 索引）
  - unknown 状态（采集读不到链路时的灰态，与原 PortCell 语义对齐）
  - 选中态/圆角/VLAN 色条（视觉与 gui/dialogs/device_panel.PortCell 对齐，不降级）
  - info 原始端口字典挂载（兼容旧面板 _by_name[n].info 的取数路径）

集成方式（gui/dialogs/device_panel.py 中使用）：
    from gui.widgets.device_panel_graphics import DevicePanelView

    view = DevicePanelView(ports=cells)          # cells = 端口 info 列表
    view.port_clicked.connect(self._on_cell_clicked)
    view.batch_update_ports(state_map)           # 增量刷新（只重绘变化格）
"""

from PyQt5.QtWidgets import (QGraphicsView, QGraphicsScene, QGraphicsObject)
from PyQt5.QtCore import Qt, QRectF, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPainterPath

# 状态 → (填充, 描边)；走 theme token 双主题自适应（与 device_panel._state_palette 同源）
def _state_palette(state):
    from gui import theme
    t = theme.t
    return {
        "up":       (t("port_up_bg"), t("port_up_border")),
        "down":     (t("port_down_bg"), t("port_down_border")),
        "trunk":    (t("port_trunk_bg"), t("port_trunk_border")),
        "shutdown": (t("danger_light"), t("danger")),
        "unknown":  (t("card"), t("border")),
    }.get(state, (t("card"), t("border")))

CELL_W, CELL_H = 56, 52
CELL_GAP = 6
CORNER_R = 8


class PortItem(QGraphicsObject):
    """单个端口方块（自绘 QGraphicsObject——必须继承 QObject 才能带 pyqtSignal）"""

    clicked = pyqtSignal(str)      # 端口全名

    def __init__(self, info: dict, x: float, y: float,
                 w: float = CELL_W, h: float = CELL_H):
        super().__init__()
        self._rect = QRectF(0, 0, w, h)
        self.setPos(x, y)
        self.info = dict(info or {})
        self.port_name = self.info.get("name") or "?"
        self.port_label = str(self.info.get("label") or self.port_name)
        self.state = (self.info.get("state") or "unknown").lower()
        self.vlan_id = str(self.info.get("vlan") or "").strip()
        self.terminal_connected = bool(self.info.get("hosts"))
        self.neighbor_connected = bool(self.info.get("neighbor"))
        self._hovered = False
        self._selected = False
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(self._tooltip())

    # ---- 几何 ----
    def boundingRect(self):
        return self._rect

    # ---- 状态 ----
    def _tooltip(self) -> str:
        i = self.info
        parts = [self.port_name,
                 f"状态: {'UP' if self.state == 'up' else self.state}"]
        if i.get("vlan"):
            parts.append(f"VLAN: {i['vlan']}")
        if i.get("desc"):
            parts.append(f"描述: {i['desc']}")
        if i.get("hosts"):
            parts.append("下挂: " + "、".join(str(h) for h in i["hosts"][:3]))
        if i.get("neighbor"):
            parts.append(f"LLDP 邻居: {i['neighbor']}")
        return "\n".join(parts)

    def set_state(self, state: str = None, vlan_id=None,
                  terminal=None, neighbor=None):
        """仅更新变化的端口状态（脏矩形更新：无变化直接返回，不重绘）"""
        changed = False
        if state is not None and state.lower() != self.state:
            self.state = state.lower()
            changed = True
        if vlan_id is not None and str(vlan_id) != self.vlan_id:
            self.vlan_id = str(vlan_id)
            changed = True
        if terminal is not None and bool(terminal) != self.terminal_connected:
            self.terminal_connected = bool(terminal)
            changed = True
        if neighbor is not None and bool(neighbor) != self.neighbor_connected:
            self.neighbor_connected = bool(neighbor)
            changed = True
        if changed:
            self.setToolTip(self._tooltip())
            self.update()      # 仅刷新本项，不影响其他

    def set_selected(self, on: bool):
        if bool(on) != self._selected:
            self._selected = bool(on)
            self.update()

    # ---- 绘制 ----
    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        from gui import theme
        bg, border = _state_palette(self.state)
        r = self._rect

        path = QPainterPath()
        path.addRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), CORNER_R, CORNER_R)
        painter.setBrush(QBrush(QColor(bg)))
        # 选中：主题蓝加粗描边；hover：略粗；常态 1px
        if self._selected:
            pen = QPen(QColor(theme.t("accent")), 2.5)
        elif self._hovered:
            pen = QPen(QColor(border), 2)
        else:
            pen = QPen(QColor(border), 1)
        painter.setPen(pen)
        painter.drawPath(path)

        # 端口短名（居中，等宽字体）
        painter.setFont(QFont("Consolas", 9))
        painter.setPen(QColor(theme.t("text")))
        painter.drawText(QRectF(r.x(), r.y() + 2, r.width(), r.height() - 12),
                         Qt.AlignCenter, self.port_label)

        # VLAN 标签（左下角小字）
        if self.vlan_id:
            painter.setFont(QFont("Consolas", 7))
            painter.setPen(QColor(theme.t("text_sub")))
            painter.drawText(QRectF(r.x() + 3, r.bottom() - 12, r.width() - 6, 10),
                             Qt.AlignLeft | Qt.AlignVCenter, f"V{self.vlan_id}")

        # 状态指示点（左上）
        if self.terminal_connected or self.neighbor_connected:
            dot = (QColor(theme.t("accent")) if self.neighbor_connected
                   else QColor(theme.t("success")))
            painter.setBrush(QBrush(dot))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QRectF(r.x() + 3, r.y() + 3, 5, 5))

    # ---- 交互 ----
    def mousePressEvent(self, event):
        self.clicked.emit(self.port_name)
        event.accept()

    def hoverEnterEvent(self, event):
        self._hovered = True
        self.update()

    def hoverLeaveEvent(self, event):
        self._hovered = False
        self.update()


class DevicePanelScene(QGraphicsScene):
    """设备面板画布（QGraphicsScene：大规模端口渲染 + 脏矩形批量更新）"""

    port_clicked = pyqtSignal(str)

    def __init__(self, ports: list = None, num_ports: int = 48,
                 cols: int = 10, parent=None):
        super().__init__(parent)
        self.cols = cols
        self.cell_w = CELL_W
        self.cell_h = CELL_H
        self.spacing = CELL_GAP
        self.port_items = {}       # 端口全名 -> PortItem
        ports = ports or [{"name": f"Gi{i}", "label": str(i), "state": "down"}
                          for i in range(num_ports)]
        self._create_ports(ports)

    def _create_ports(self, ports: list):
        for i, info in enumerate(ports):
            row, col = divmod(i, self.cols)
            x = col * (self.cell_w + self.spacing)
            y = row * (self.cell_h + self.spacing)
            item = PortItem(info, x, y)
            item.clicked.connect(self.port_clicked.emit)
            self.addItem(item)
            self.port_items[item.port_name] = item

        rows = (len(ports) + self.cols - 1) // self.cols
        self.setSceneRect(
            0, 0,
            self.cols * (self.cell_w + self.spacing),
            max(1, rows) * (self.cell_h + self.spacing))

    # ---- 增量更新 ----
    def update_port_state(self, port_name: str, state: str = None, vlan_id=None,
                          terminal=None, neighbor=None):
        item = self.port_items.get(port_name)
        if item is not None:
            item.set_state(state, vlan_id, terminal, neighbor)

    def batch_update_ports(self, state_map: dict):
        """批量更新：{端口全名: {"state","vlan","terminal","neighbor"}}（只重绘变化格）"""
        for name, attrs in (state_map or {}).items():
            item = self.port_items.get(name)
            if item is None:
                continue
            item.set_state(state=attrs.get("state"),
                           vlan_id=attrs.get("vlan"),
                           terminal=attrs.get("terminal"),
                           neighbor=attrs.get("neighbor"))

    def set_selected(self, names):
        names = set(names or [])
        for name, item in self.port_items.items():
            item.set_selected(name in names)


class DevicePanelView(QGraphicsView):
    """设备面板视图（自适应宽度、无滚动条干扰、保留滚轮缩放）"""

    port_clicked = pyqtSignal(str)

    def __init__(self, ports: list = None, num_ports: int = 48,
                 cols: int = 10, parent=None):
        super().__init__(parent)
        self.panel_scene = DevicePanelScene(ports, num_ports, cols, self)
        self.panel_scene.port_clicked.connect(self.port_clicked.emit)
        self.setScene(self.panel_scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setFrameShape(QGraphicsView.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # 背景跟主题：QGraphics 自绘不吃 QSS 重映射，切主题时需整景重绘
        from gui import theme as _theme
        self.setBackgroundBrush(QBrush(QColor(_theme.t("canvas_bg"))))
        _theme.on_change(self._on_theme_change)

    def _on_theme_change(self):
        from gui import theme as _theme
        self.setBackgroundBrush(QBrush(QColor(_theme.t("canvas_bg"))))
        self.panel_scene.update()

    # 代理到 scene
    def update_port_state(self, port_name, state=None, vlan_id=None,
                          terminal=None, neighbor=None):
        self.panel_scene.update_port_state(port_name, state, vlan_id, terminal, neighbor)

    def batch_update_ports(self, state_map):
        self.panel_scene.batch_update_ports(state_map)

    def set_selected(self, names):
        self.panel_scene.set_selected(names)

    def fit_height(self):
        """按场景高度调整视图高度（宽度随布局拉伸，不出现滚动条）"""
        rect = self.panel_scene.sceneRect()
        self.setMinimumHeight(int(rect.height()) + 4)
        self.setMaximumHeight(int(rect.height()) + 4)

    def wheelEvent(self, event):
        """滚轮缩放（Ctrl+滚轮？不必：面板本身很小，直接缩放易误触——改为忽略，
        保留父级滚动）。性能组件不承担缩放交互。"""
        event.ignore()