#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
网络工具箱主窗口（二开：与主窗口一致的现代化无边框样式）
"""

from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QStackedWidget, QScrollArea, QFrame, QPushButton,
                             QTabWidget, QLabel, QMessageBox, QStatusBar)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QPainter, QColor, QCursor

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from gui.tools.subnet_tool import SubnetCalculatorWidget
from gui.tools.ping_tool import PingTestWidget
from gui.tools.port_tool import PortScanWidget
from gui.tools.trace_tool import TraceRouteWidget
from gui.tools.dns_tool import DNSToolWidget, NetworkInfoWidget, IPConverterWidget
from gui.tools.http_tool import HTTPStatusWidget
from gui.tools.password_tool import PasswordGeneratorWidget
from gui.tools.encoder_tool import EncoderToolWidget
from gui.tools.mac_tool import MACToolWidget
from gui.styles import MODERN_STYLE, BG
from gui.title_bar import FramelessTitleBar


class NetworkToolsWindow(QMainWindow):
    """网络工具箱主窗口（无边框 + 圆点标题栏，样式与主窗口统一）"""

    _RESIZE_MARGIN = 8
    _resize_edge = None
    _resize_start = None
    _resize_geo = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()

    def initUI(self):
        self.setWindowTitle("NetOps Toolkit - 网络工具箱")
        self.setMinimumSize(820, 600)
        # 固定尺寸 + 固定位置（不依赖 availableGeometry：DPI 感知模式下它返回物理/逻辑像素
        # 不一致，按比例计算会把窗口推出屏幕）
        self.setMinimumSize(760, 520)   # 明确最小尺寸，防内容把窗口撑超出屏幕
        self.resize(980, 660)
        self.move(90, 70)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window | Qt.WindowSystemMenuHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setStyleSheet(MODERN_STYLE)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(16)

        # 自定义标题栏（与主窗口一致的红黄绿圆点）
        self.title_bar = FramelessTitleBar("网络工具箱", self)
        main_layout.addWidget(self.title_bar)

        # 注：“网络工具箱”大标题已移入首页（工具子页不再占用标题行）

        # ===== 两级结构：首页功能卡片网格 → 点击进入具体工具 =====
        self.stack = QStackedWidget()
        self._tool_pages = []

        # 一级：功能卡片首页
        TOOLS = [
            ("🧮", "子网计算器", "IP 子网划分、掩码换算、CIDR 计算", SubnetCalculatorWidget),
            ("🔔", "Ping 测试", "连通性检测、批量 Ping、Ping 扫描", PingTestWidget),
            ("🔍", "端口扫描", "TCP 端口开放检测、常见端口速查", PortScanWidget),
            ("🛤️", "路由跟踪", "Traceroute 路径追踪与逐跳延迟", TraceRouteWidget),
            ("🌐", "DNS / Whois", "域名解析、反向 DNS、备案信息", DNSToolWidget),
            ("🌐", "HTTP 检测", "网站状态码、响应头检测", HTTPStatusWidget),
            ("📀", "MAC 查询", "MAC 地址厂商归属查询", MACToolWidget),
            ("🔐", "密码生成", "强密码随机生成与强度评估", PasswordGeneratorWidget),
            ("🔄", "编码转换", "Base64 / URL / Hex 编解码", EncoderToolWidget),
            ("🖥️", "网络信息", "本机 IP、公网 IP、网卡信息", NetworkInfoWidget),
            ("🔄", "IP 转换", "十进制 / 十六进制 / 二进制互转", IPConverterWidget),
        ]

        home = QWidget()
        home_lay = QVBoxLayout(home)
        home_lay.setContentsMargins(0, 0, 0, 0)
        home_lay.setSpacing(12)

        # 大标题只在首页展示（子页不占标题行）
        home_header = QLabel("🧰 网络工具箱")
        home_header.setStyleSheet("""
            font-size: 24px; font-weight: bold; color: #1F2A37;
            padding: 4px; background: transparent;
        """)
        home_header.setAlignment(Qt.AlignCenter)
        home_lay.addWidget(home_header)

        hint = QLabel("选择一个工具开始使用")
        hint.setStyleSheet("color: #7A8699; font-size: 13px; padding-left: 2px;")
        home_lay.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(12)

        # 先把首页放进 stack（index 0），工具页依次 1..N
        self.stack.addWidget(home)

        for idx, (icon, name, desc, widget_cls) in enumerate(TOOLS):
            card = self._make_tool_card(icon, name, desc, idx)
            grid.addWidget(card, idx // 3, idx % 3)
            # 工具页（带返回条）
            page = QWidget()
            p_lay = QVBoxLayout(page)
            p_lay.setContentsMargins(0, 0, 0, 0)
            p_lay.setSpacing(8)

            bar = QHBoxLayout()
            back_btn = QPushButton("← 返回工具箱")
            back_btn.setObjectName("ghostButton")
            back_btn.setCursor(Qt.PointingHandCursor)
            back_btn.clicked.connect(lambda: self.stack.setCurrentIndex(0))
            bar.addWidget(back_btn)
            title = QLabel(f"{icon}  {name}")
            title.setStyleSheet("font-size: 17px; font-weight: bold; color: #1F2A37;")
            bar.addWidget(title)
            bar.addStretch()
            p_lay.addLayout(bar)

            # 工具内容包滚动区：内容高时滚动，不被压缩（各工具内部布局保持原尺寸）
            from gui.widget_utils import scroll_wrap
            p_lay.addWidget(scroll_wrap(widget_cls()), 1)
            self.stack.addWidget(page)
            self._tool_pages.append(page)

        # 网格最后一列自适应
        for c in range(3):
            grid.setColumnStretch(c, 1)
        scroll.setWidget(grid_host)
        home_lay.addWidget(scroll, 1)

        self.stack.setCurrentIndex(0)   # 首页（index 0 已在循环前加入）
        main_layout.addWidget(self.stack, 1)

        self.statusBar().showMessage("就绪 · 点击功能卡片进入工具")
        self.statusBar().setStyleSheet("color: #7A8699; font-size: 12px;")

    def _make_tool_card(self, icon, name, desc, index):
        """功能卡片：图标 + 名称 + 简介，整卡可点"""
        card = QPushButton()
        card.setCursor(Qt.PointingHandCursor)
        card.setMinimumHeight(88)
        card.setMaximumHeight(104)   # 固定卡高，描述不折行撑爆布局
        card.setStyleSheet("""
            QPushButton {
                background: #FFFFFF; border: 1px solid #E5EAF2;
                border-radius: 14px; text-align: left; padding: 14px 16px;
            }
            QPushButton:hover { border: 1px solid #0089FF; background: #F5FAFF; }
            QPushButton:pressed { background: #EAF4FF; }
        """)
        lay = QHBoxLayout(card)
        lay.setContentsMargins(14, 10, 12, 10)
        lay.setSpacing(12)
        ic = QLabel(icon)
        ic.setStyleSheet("font-size: 26px; background: transparent;")
        ic.setFixedWidth(40)
        lay.addWidget(ic)
        col = QVBoxLayout()
        col.setSpacing(2)
        n = QLabel(name)
        n.setStyleSheet("font-size: 14px; font-weight: bold; color: #1F2A37; background: transparent;")
        d = QLabel(desc)
        d.setStyleSheet("font-size: 12px; color: #7A8699; background: transparent;")
        d.setWordWrap(False)   # 单行不折行（防小窗口下高度膨胀）
        col.addWidget(n)
        col.addWidget(d)
        lay.addLayout(col, 1)
        arrow = QLabel("›")
        arrow.setStyleSheet("font-size: 20px; color: #B7C3D4; background: transparent;")
        lay.addWidget(arrow)
        # 点击气泡内的子控件不会吞事件（QLabel 默认透明）
        for w in (ic, n, d, arrow):
            w.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        card.clicked.connect(lambda: self.stack.setCurrentIndex(index + 1))
        return card

    # ---------------- 无边框窗口支持 ----------------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(BG))
        radius = 12 if not self.isMaximized() else 0
        painter.drawRoundedRect(0, 0, self.width(), self.height(), radius, radius)

    def _edge_at(self, pos):
        right = pos.x() >= self.width() - self._RESIZE_MARGIN
        bottom = pos.y() >= self.height() - self._RESIZE_MARGIN
        if right and bottom:
            return "rb"
        if right:
            return "r"
        if bottom:
            return "b"
        return ""

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self.isMaximized():
            edge = self._edge_at(event.pos())
            if edge:
                self._resize_edge = edge
                self._resize_start = event.globalPos()
                self._resize_geo = self.geometry()
                return
        self._resize_edge = None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resize_edge:
            diff = event.globalPos() - self._resize_start
            geo = self._resize_geo
            if "r" in self._resize_edge:
                geo.setWidth(max(self.minimumSize().width(), geo.width() + diff.x()))
            if "b" in self._resize_edge:
                geo.setHeight(max(self.minimumSize().height(), geo.height() + diff.y()))
            self.setGeometry(geo)
            return
        if not self.isMaximized():
            edge = self._edge_at(event.pos())
            cursors = {"rb": Qt.SizeFDiagCursor, "r": Qt.SizeHorCursor, "b": Qt.SizeVerCursor}
            self.setCursor(QCursor(cursors[edge]) if edge else Qt.ArrowCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._resize_edge = None
        super().mouseReleaseEvent(event)
