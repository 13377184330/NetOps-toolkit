#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
网络工具箱主窗口（二开：与主窗口一致的现代化无边框样式）
"""

from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
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
        # 按屏幕可用区自适应（占 65%/72%），与主窗口同一套适配策略
        from PyQt5.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            w = min(int(avail.width() * 0.65), 1100)
            h = min(int(avail.height() * 0.72), 760)
            self.resize(w, h)
            self.move(avail.center().x() - w // 2, avail.center().y() - h // 2)
        else:
            self.resize(1000, 720)
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

        header = QLabel("🧰 网络工具箱")
        header.setStyleSheet("""
            font-size: 24px;
            font-weight: bold;
            color: #1F2A37;
            padding: 4px;
            background: transparent;
        """)
        header.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(header)

        tabs = QTabWidget()
        tabs.setTabPosition(QTabWidget.North)

        tabs.addTab(SubnetCalculatorWidget(), "🧮 子网计算器")
        tabs.addTab(PingTestWidget(), "🔔 Ping 测试")
        tabs.addTab(PortScanWidget(), "🔍 端口扫描")
        tabs.addTab(TraceRouteWidget(), "🛤️ 路由跟踪")
        tabs.addTab(DNSToolWidget(), "🌐 DNS/Whois")
        tabs.addTab(HTTPStatusWidget(), "🌐 HTTP检测")
        tabs.addTab(MACToolWidget(), "📀 MAC查询")
        tabs.addTab(PasswordGeneratorWidget(), "🔐 密码生成")
        tabs.addTab(EncoderToolWidget(), "🔄 编码转换")
        tabs.addTab(NetworkInfoWidget(), "🖥️ 网络信息")
        tabs.addTab(IPConverterWidget(), "🔄 IP 转换")

        main_layout.addWidget(tabs, 1)

        self.statusBar().showMessage("就绪")
        self.statusBar().setStyleSheet("color: #7A8699; font-size: 12px;")

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
