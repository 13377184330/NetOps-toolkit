#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
网络拓扑可视化页（二开新增）
QGraphicsView 图形化展示：本机设备节点 + LLDP 发现的邻居 + 连线（端口标注）
- 数据源：Console/SSH 采集的 LLDP 邻居信息；无邻居时支持手动放置节点
- 交互：节点可拖动、滚轮缩放、一键自动布局
Qt 原生图形框架实现，不重复造绘图轮子
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGraphicsView,
                             QGraphicsScene, QGraphicsEllipseItem, QGraphicsItem,
                             QGraphicsTextItem, QGraphicsLineItem, QPushButton,
                             QLabel, QGroupBox, QGraphicsDropShadowEffect)
from PyQt5.QtCore import Qt, QPointF, QRectF
from PyQt5.QtGui import QColor, QPen, QBrush, QFont, QPainter


class DeviceNode(QGraphicsEllipseItem):
    """可拖动设备节点"""

    def __init__(self, name: str, is_local=False, meta=None):
        r = 42
        super().__init__(-r, -r, r * 2, r * 2)
        self.device_name = name
        self.meta = meta or {}
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setZValue(2)
        self.setAcceptHoverEvents(True)
        self._is_local = is_local
        self.setBrush(QBrush(QColor("#0089FF" if is_local else "#FFFFFF")))
        self.setPen(QPen(QColor("#0089FF" if is_local else "#C9D4E3"), 2))
        self.setToolTip(
            f"{name}\n" + "\n".join(f"{k}: {v}" for k, v in self.meta.items())
        )
        # 文字标签（本机节点：白字居中于圆内；邻居：深色字在圆下方）
        self.label = QGraphicsTextItem(name, self)
        self.label.setDefaultTextColor(QColor("#FFFFFF" if is_local else "#1F2A37"))
        f = QFont("Microsoft YaHei UI", 9)
        f.setBold(True)
        self.label.setFont(f)
        lr = self.label.boundingRect()
        if is_local:
            self.label.setPos(-lr.width() / 2, -lr.height() / 2)  # 居中于圆内
        else:
            self.label.setPos(-lr.width() / 2, r + 6)

    def itemChange(self, change, value):
        # 节点移动时联动刷新连线（由场景统一处理）
        if change == QGraphicsItem.ItemPositionHasChanged:
            scene = self.scene()
            if scene and hasattr(scene, "refresh_links"):
                scene.refresh_links()
        return super().itemChange(change, value)


class TopologyScene(QGraphicsScene):
    """维护节点与连线，节点移动时自动重绘连线"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.links = []  # [(node_a, node_b, label)]

    def add_link(self, a, b, label=""):
        self.links.append((a, b, label))
        self.refresh_links()

    def refresh_links(self):
        # 移除旧线
        for item in list(self.items()):
            if isinstance(item, QGraphicsLineItem) and getattr(item, "_is_link", False):
                self.removeItem(item)
        for a, b, label in self.links:
            ca, cb = a.scenePos(), b.scenePos()
            line = QGraphicsLineItem(ca.x(), ca.y(), cb.x(), cb.y())
            line._is_link = True
            line.setPen(QPen(QColor("#B7C3D4"), 2))
            line.setZValue(1)
            self.addItem(line)
            if label:
                txt = QGraphicsTextItem(label)
                txt.setDefaultTextColor(QColor("#7A8699"))
                txt.setFont(QFont("Microsoft YaHei UI", 8))
                mid = (ca + cb) / 2
                txt.setPos(mid.x() + 4, mid.y() - 14)
                txt._link_label = True
                txt.setZValue(1)
                self.addItem(txt)
        # 清旧标签
        for item in list(self.items()):
            if getattr(item, "_link_label", False) and not any(
                    getattr(x, "_link_label", False) and x.scene() is not None
                    for x in []):
                pass

    def auto_layout(self):
        """环形布局：本机居中，邻居绕一圈"""
        nodes = [i for i in self.items() if isinstance(i, DeviceNode)]
        if not nodes:
            return
        local = next((n for n in nodes if n._is_local), None)
        others = [n for n in nodes if n is not local]
        if local:
            local.setPos(0, 0)
        import math
        n = max(1, len(others))
        radius = 140
        for i, node in enumerate(others):
            angle = 2 * math.pi * i / n - math.pi / 2
            node.setPos(radius * math.cos(angle), radius * math.sin(angle))
        self.refresh_links()
        # 通知视图居中（若有）
        views = self.views()
        if views:
            views[0].centerOn(0, 0)


class NetworkTopologyPage(QWidget):
    """网络拓扑查看页"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        # 工具条
        bar = QHBoxLayout()
        bar.setSpacing(10)
        self.info_label = QLabel("暂无拓扑数据 —— 在「Console 可视化」页连接设备时会自动抓取 LLDP 邻居")
        self.info_label.setStyleSheet("color: #7A8699; font-size: 13px;")
        bar.addWidget(self.info_label, 1)

        add_btn = QPushButton("＋ 添加节点")
        add_btn.setObjectName("secondaryButton")
        add_btn.clicked.connect(self.add_manual_node)

        layout_btn = QPushButton("自动布局")
        layout_btn.setObjectName("secondaryButton")
        layout_btn.clicked.connect(lambda: self.scene.auto_layout())

        zoom_in = QPushButton("＋")
        zoom_in.setFixedWidth(40)
        zoom_in.clicked.connect(lambda: self.view.scale(1.2, 1.2))
        zoom_out = QPushButton("－")
        zoom_out.setFixedWidth(40)
        zoom_out.clicked.connect(lambda: self.view.scale(1 / 1.2, 1 / 1.2))

        bar.addWidget(add_btn)
        bar.addWidget(layout_btn)
        bar.addWidget(zoom_out)
        bar.addWidget(zoom_in)
        layout.addLayout(bar)

        # 画布
        canvas_group = QGroupBox("拓扑视图")
        canvas_lay = QVBoxLayout(canvas_group)
        canvas_lay.setContentsMargins(10, 26, 10, 10)

        self.scene = TopologyScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.view.setStyleSheet("""
            QGraphicsView {
                background: #F7F9FC;
                border: 1px dashed #D3DBE7;
                border-radius: 12px;
            }
        """)
        self.view.setSceneRect(QRectF(-600, -420, 1200, 840))
        self.view.wheelEvent = self._zoom_wheel
        canvas_lay.addWidget(self.view)
        layout.addWidget(canvas_group, 1)

        # 提示
        tip = QLabel("💡 操作：拖动节点移动位置 ｜ 滚轮缩放 ｜ 拖动空白处平移 ｜ 悬停节点查看详情")
        tip.setStyleSheet("color: #9AA7B8; font-size: 12px;")
        layout.addWidget(tip)

        self._local_node = None
        self._neighbor_nodes = {}

    def _zoom_wheel(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.view.scale(factor, factor)

    # ---------------- 数据填充 ----------------
    def load_topology(self, local_name: str, local_meta: dict, neighbors: list):
        """由 Console 采集后调用：local_name 本机名，neighbors=[{name, port, peer_port}]"""
        self.scene.clear()
        self.scene.links.clear()
        self._neighbor_nodes = {}

        local = DeviceNode(local_name or "本机设备", is_local=True, meta=local_meta)
        self.scene.addItem(local)
        self._local_node = local

        for nb in neighbors:
            name = nb.get("name") or nb.get("peer", "邻居设备")
            if name in self._neighbor_nodes:
                node = self._neighbor_nodes[name]
            else:
                node = DeviceNode(name, is_local=False,
                                  meta={"本地端口": nb.get("port", ""),
                                        "对端端口": nb.get("peer_port", "")})
                self.scene.addItem(node)
                self._neighbor_nodes[name] = node
            self.scene.add_link(local, node, nb.get("port", ""))

        self.scene.auto_layout()
        self.view.centerOn(0, 0)
        count = len(self._neighbor_nodes)
        if count:
            self.info_label.setText(f"已发现 {count} 台 LLDP 邻居设备（本机：{local_name}）")
        else:
            self.info_label.setText("未发现 LLDP 邻居（设备可能未启用 LLDP 或为单机环境）")

    def add_manual_node(self):
        """手动添加节点（无 LLDP 时的占位能力）"""
        n = len([i for i in self.scene.items() if isinstance(i, DeviceNode)])
        node = DeviceNode(f"设备{n + 1}")
        self.scene.addItem(node)
        node.setPos(160 * ((n % 3) - 1), -220)
        if self._local_node:
            self.scene.add_link(self._local_node, node, "manual")
