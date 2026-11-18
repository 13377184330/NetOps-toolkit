#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
左侧竖向导航容器（二开新增）
QListWidget 导航 + QStackedWidget 内容页，替代顶部横排 QTabBar：
- 文字永远横排（West QTabWidget 会旋转文字，观感差）
- 数量自适应（7 个页面竖排不裁切）
- 接口兼容 QTabWidget：addTab / count / currentIndex / setCurrentIndex / tabText / currentChanged
"""

from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QListWidget,
                             QListWidgetItem, QStackedWidget, QLabel, QPushButton)
from PyQt5.QtCore import pyqtSignal, Qt, QRectF
from PyQt5.QtGui import QPainter, QColor

from gui.styles import ACCENT, BORDER, TEXT, TEXT_SUB, BG, CARD
from gui import theme

# 注意：全局 QSS 里 QListWidget::item 带 border-bottom + 圆角，导航项会因此
# 显出一圈"幽灵描边"（实测截图每项像套了个浅灰小方框），这里必须显式清零。
NAV_QSS = f"""
#sideNav {{
    background: #FFFFFF;
    border: 1px solid {BORDER};
    border-radius: 14px;
    padding: 8px 6px;
    outline: none;
}}
#sideNav::item {{
    color: {TEXT_SUB};
    padding: 12px 14px;
    margin: 3px 2px;
    border: none;
    border-radius: 10px;
    font-weight: bold;
    font-size: 13px;
}}
#sideNav::item:selected {{
    background: {ACCENT};
    color: #FFFFFF;
}}
#sideNav::item:hover:!selected {{
    background: #E2E9F3;
    color: {TEXT};
}}
"""


class NavStatusCard(QWidget):
    """导航底部的工作状态卡片：填充侧栏下半截留白，同时展示有用信息。

    只做展示 + 发信号，不直接读 DeviceStore/主窗口状态，避免循环依赖；
    数据由 MainWindow 通过 set_status()/set_device_count() 推过来。
    """

    tools_clicked = pyqtSignal()

    _QSS = f"""
        QLabel#navStatusTitle {{
            font-size: 12px;
            font-weight: bold;
            color: {TEXT};
            background: transparent;
            border: none;
        }}
        QLabel#navStatusKey {{
            font-size: 11px;
            color: {TEXT_SUB};
            background: transparent;
            border: none;
        }}
        QLabel#navStatusValue {{
            font-size: 12px;
            font-weight: bold;
            color: {TEXT};
            background: transparent;
            border: none;
        }}
        QPushButton#navToolsBtn {{
            background: {ACCENT};
            color: #FFFFFF;
            border: none;
            border-radius: 9px;
            padding: 8px 4px;
            font-size: 12px;
            font-weight: bold;
        }}
        QPushButton#navToolsBtn:hover {{ background: #0077E6; }}
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("navStatusCard")
        self.setStyleSheet(self._QSS)
        self.setFixedWidth(160)
        self.setFixedHeight(176)   # 紧凑卡片：内容约 160px，不让 stretch 撑出大块空白

        # 卡片底自绘：QSS 在控件级 stylesheet 上画 #navStatusCard 的底/边框
        # 实测不生效（主题重映射 + 控件级选择器优先级，截图实锤文字浮在灰底上），
        # paintEvent 画圆角矩形最稳，两主题都读 theme token。
        self.setAttribute(Qt.WA_StyledBackground, False)

        v = QVBoxLayout(self)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(6)

        title = QLabel("当前环境")
        title.setObjectName("navStatusTitle")
        v.addWidget(title)

        v.addSpacing(2)

        self.vendor_label = QLabel("厂商")
        self.vendor_label.setObjectName("navStatusKey")
        v.addWidget(self.vendor_label)
        self.vendor_value = QLabel("华为 Huawei")
        self.vendor_value.setObjectName("navStatusValue")
        v.addWidget(self.vendor_value)

        self.device_label = QLabel("已登记设备")
        self.device_label.setObjectName("navStatusKey")
        v.addWidget(self.device_label)
        self.device_value = QLabel("0 台")
        self.device_value.setObjectName("navStatusValue")
        v.addWidget(self.device_value)

        v.addStretch(1)

        tools_btn = QPushButton("网络工具箱 →")
        tools_btn.setObjectName("navToolsBtn")
        tools_btn.setCursor(Qt.PointingHandCursor)
        tools_btn.setToolTip("打开全部网络工具（子网计算 / Ping / 端口扫描等）")
        tools_btn.clicked.connect(self.tools_clicked.emit)
        v.addWidget(tools_btn)

    def paintEvent(self, event):
        """自绘卡片底（QSS 在控件级 setStyleSheet 上画不透，见 __init__ 注释）"""
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.t("border")))
        p.drawRoundedRect(QRectF(self.rect()), 14, 14)
        p.setBrush(theme.qcolor("card"))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 13, 13)

    def set_vendor(self, text):
        self.vendor_value.setText(text)

    def set_device_count(self, n):
        self.device_value.setText(f"{n} 台")


class _SideNavWidget(QWidget):
    """左侧导航 + 内容堆栈（对 MainWindow 暴露类 QTabWidget 接口）"""

    currentChanged = pyqtSignal(int)
    tools_clicked = pyqtSignal()  # 转发状态卡片的工具箱入口

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        # 导航列：列表 + 底部状态卡片（状态卡片把导航下半截空白利用起来）
        nav_col = QVBoxLayout()
        nav_col.setContentsMargins(0, 0, 0, 0)
        nav_col.setSpacing(10)

        self._nav = QListWidget()
        self._nav.setObjectName("sideNav")
        self._nav.setStyleSheet(NAV_QSS)
        self._nav.setFixedWidth(160)
        self._nav.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # 单列菜单，永不出横向拖动条
        self._nav.setHorizontalScrollMode(QListWidget.ScrollPerPixel)
        self._nav.setTextElideMode(Qt.ElideNone)  # 保证文字完整不省略
        nav_col.addWidget(self._nav, 1)

        self.status_card = NavStatusCard()
        self.status_card.tools_clicked.connect(self.tools_clicked.emit)
        nav_col.addWidget(self.status_card)

        lay.addLayout(nav_col)

        self._stack = QStackedWidget()
        lay.addWidget(self._stack, 1)

        # 惰性页签：row -> 工厂函数（首次切到该页才实例化，省启动时间）
        self._lazy = {}

        self._nav.currentRowChanged.connect(self._on_row_changed)

    def set_status(self, vendor=None, device_count=None):
        """主窗口推送状态到导航卡片（展示用，不反向依赖业务逻辑）"""
        if vendor is not None:
            self.status_card.set_vendor(vendor)
        if device_count is not None:
            self.status_card.set_device_count(device_count)

    def select_first(self):
        """初始选中第一项（QListWidget 默认 -1 无选中，导航无高亮）"""
        if self._nav.count() > 0 and self._nav.currentRow() < 0:
            self._nav.setCurrentRow(0)

    # ---------------- 兼容 QTabWidget 接口 ----------------
    def addTab(self, widget, title):
        self._nav.addItem(QListWidgetItem(title))
        self._stack.addWidget(widget)
        return self._stack.count() - 1

    def addLazyTab(self, factory, title):
        """惰性页签：先放占位 QWidget，首次切到该页时才调用 factory() 实例化替换。
        用于构造耗时的页面（如拓扑页，构造含本机网卡扫描），避免拖慢启动。"""
        placeholder = QWidget()
        idx = self.addTab(placeholder, title)
        self._lazy[idx] = factory
        return idx

    def count(self):
        return self._stack.count()

    def currentIndex(self):
        return self._nav.currentRow()

    def setCurrentIndex(self, idx):
        self._nav.setCurrentRow(idx)

    def setCurrentWidget(self, widget):
        idx = self._stack.indexOf(widget)
        if idx >= 0:
            self.setCurrentIndex(idx)

    def tabText(self, idx):
        item = self._nav.item(idx)
        return item.text() if item else ""

    def widget(self, idx):
        return self._stack.widget(idx)

    # ---------------- 内部 ----------------
    def _on_row_changed(self, row):
        if row >= 0:
            factory = self._lazy.pop(row, None)
            if factory is not None:
                placeholder = self._stack.widget(row)
                real = factory()
                self._stack.removeWidget(placeholder)
                self._stack.insertWidget(row, real)
                placeholder.deleteLater()
            self._stack.setCurrentIndex(row)
        self.currentChanged.emit(row)
