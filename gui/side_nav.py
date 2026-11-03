#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
左侧竖向导航容器（二开新增）
QListWidget 导航 + QStackedWidget 内容页，替代顶部横排 QTabBar：
- 文字永远横排（West QTabWidget 会旋转文字，观感差）
- 数量自适应（7 个页面竖排不裁切）
- 接口兼容 QTabWidget：addTab / count / currentIndex / setCurrentIndex / tabText / currentChanged
"""

from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QListWidget,
                             QListWidgetItem, QStackedWidget)
from PyQt5.QtCore import pyqtSignal, Qt

NAV_QSS = """
#sideNav {
    background: #FFFFFF;
    border: 1px solid #E5EAF2;
    border-radius: 14px;
    padding: 8px 6px;
    outline: none;
}
#sideNav::item {
    color: #5A6B7B;
    padding: 12px 16px;
    margin: 3px 4px;
    border-radius: 10px;
    font-weight: bold;
    font-size: 13px;
}
#sideNav::item:selected {
    background: #0089FF;
    color: #ffffff;
}
#sideNav::item:hover:!selected {
    background: #E8EDF5;
    color: #1F2A37;
}
"""


class _SideNavWidget(QWidget):
    """左侧导航 + 内容堆栈（对 MainWindow 暴露类 QTabWidget 接口）"""

    currentChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        self._nav = QListWidget()
        self._nav.setObjectName("sideNav")
        self._nav.setStyleSheet(NAV_QSS)
        self._nav.setFixedWidth(160)
        self._nav.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # 单列菜单，永不出横向拖动条
        self._nav.setHorizontalScrollMode(QListWidget.ScrollPerPixel)
        self._nav.setTextElideMode(Qt.ElideNone)  # 保证文字完整不省略
        lay.addWidget(self._nav)

        self._stack = QStackedWidget()
        lay.addWidget(self._stack, 1)

        self._nav.currentRowChanged.connect(self._on_row_changed)

    def select_first(self):
        """初始选中第一项（QListWidget 默认 -1 无选中，导航无高亮）"""
        if self._nav.count() > 0 and self._nav.currentRow() < 0:
            self._nav.setCurrentRow(0)

    # ---------------- 兼容 QTabWidget 接口 ----------------
    def addTab(self, widget, title):
        self._nav.addItem(QListWidgetItem(title))
        self._stack.addWidget(widget)
        return self._stack.count() - 1

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
            self._stack.setCurrentIndex(row)
        self.currentChanged.emit(row)
