#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
配置生成聚合页（二开：功能归拢）
把原来 5 个独立导航项（基础/VLAN/路由/安全/接口配置）收进一个页面，
页内用胶囊式二级导航切换——一级导航只留 4 项，界面不再臃肿。
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget,
                             QPushButton, QButtonGroup)
from PyQt5.QtCore import Qt


class ConfigGenPage(QWidget):
    """配置生成聚合页：顶部胶囊二级导航 + 内容堆栈"""

    def __init__(self, pages: dict, parent=None):
        """
        pages: {标题: 页面widget}，按需要顺序传入
        """
        super().__init__(parent)
        self._pages = pages
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # 胶囊式二级导航
        nav_bar = QHBoxLayout()
        nav_bar.setSpacing(8)
        nav_bar.setContentsMargins(2, 2, 2, 0)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._stack = QStackedWidget()

        titles = list(self._pages.keys())
        for i, title in enumerate(titles):
            btn = QPushButton(title)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    padding: 9px 22px; border-radius: 10px;
                    border: 1px solid #E5EAF2; background: #FFFFFF;
                    color: #5A6B7B; font-weight: bold; font-size: 13px;
                }
                QPushButton:hover { background: #E8EDF5; color: #1F2A37; }
                QPushButton:checked {
                    background: #0089FF; color: #FFFFFF; border: 1px solid #0089FF;
                }
            """)
            self._group.addButton(btn, i)
            nav_bar.addWidget(btn)
            self._stack.addWidget(self._pages[title])
        nav_bar.addStretch()
        layout.addLayout(nav_bar)

        layout.addWidget(self._stack, 1)

        self._group.buttonClicked[int].connect(self._switch)
        if titles:
            self._group.button(0).setChecked(True)
            self._stack.setCurrentIndex(0)

    def _switch(self, idx):
        self._stack.setCurrentIndex(idx)

    # 供外部（模板/生成逻辑）访问原始 5 个 tab
    @property
    def sub_pages(self):
        return self._pages
