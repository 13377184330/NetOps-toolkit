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

from gui.widget_utils import scroll_wrap


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

        # 胶囊式二级导航（分段控件观感）
        # 原来这里是一排"白底/选中蓝底"的按钮，和左侧一级导航的蓝底选中态一模一样，
        # 两级看起来是同级的。改成浅灰轨道 + 白色选中块，一眼看出是"页内分段"。
        from gui.styles import ACCENT, TEXT_SUB, TEXT

        nav_bar = QHBoxLayout()
        nav_bar.setSpacing(0)
        nav_bar.setContentsMargins(2, 2, 2, 0)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._stack = QStackedWidget()

        seg_bar = QWidget()
        seg_bar.setObjectName("segBar")
        seg_row = QHBoxLayout(seg_bar)
        seg_row.setContentsMargins(3, 3, 3, 3)
        seg_row.setSpacing(2)
        seg_bar.setStyleSheet(f"""
            #segBar {{
                background: #E4EAF3;
                border-radius: 12px;
            }}
            QPushButton {{
                padding: 8px 18px;
                border-radius: 9px;
                border: none;
                background: transparent;
                color: {TEXT_SUB};
                font-weight: bold;
                font-size: 13px;
            }}
            QPushButton:hover {{
                color: {TEXT};
            }}
            QPushButton:checked {{
                background: #FFFFFF;
                color: {ACCENT};
            }}
        """)

        titles = list(self._pages.keys())
        for i, title in enumerate(titles):
            btn = QPushButton(title)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            self._group.addButton(btn, i)
            seg_row.addWidget(btn)
            # 每个子页各自包滚动区（防止切页后横向需求变化导致外层裁切）
            self._stack.addWidget(scroll_wrap(self._pages[title]))

        nav_bar.addWidget(seg_bar)
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
