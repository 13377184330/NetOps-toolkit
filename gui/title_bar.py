#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
无边框窗口自定义标题栏（二开新增）
红黄绿圆点控制按钮 + 拖动移动 + 双击最大化，配合主窗口的圆角绘制
"""

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtGui import QCursor

from gui.styles import DANGER, WARNING, SUCCESS


class DotButton(QPushButton):
    """红/黄/绿圆点按钮"""

    def __init__(self, color, color_hover, tip, parent=None):
        super().__init__(parent)
        self.setFixedSize(13, 13)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setToolTip(tip)
        self.setStyleSheet(f"""
            QPushButton {{
                border: none;
                border-radius: 7px;
                background: {color};
            }}
            QPushButton:hover {{
                background: {color_hover};
            }}
        """)


class FramelessTitleBar(QWidget):
    """自定义标题栏：左侧红黄绿圆点 + 标题，可拖动窗口、双击最大化"""

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self._parent_window = parent
        self._drag_start = None
        self._drag_start_pos = None
        self.setFixedHeight(44)
        self.setStyleSheet("background: #FFFFFF; border-bottom: 1px solid #DFE6F0; border-top-left-radius: 12px; border-top-right-radius: 12px;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(8)

        # 红黄绿圆点：关闭 / 最小化 / 最大化
        self.close_dot = DotButton("#FA5151", "#E64646", "关闭")
        self.min_dot = DotButton("#FFC300", "#EBB000", "最小化")
        self.max_dot = DotButton("#34C759", "#2EB350", "最大化 / 还原")
        layout.addWidget(self.close_dot)
        layout.addWidget(self.min_dot)
        layout.addWidget(self.max_dot)

        # 标题
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #1F2A37; border: none; background: transparent;")
        layout.addSpacing(12)
        layout.addWidget(self.title_label)
        layout.addStretch()

        # 右侧：宿主可放置的扩展槽（如设备品牌下拉），与拖动区共用标题行
        self.trailing_layout = QHBoxLayout()
        self.trailing_layout.setSpacing(8)
        layout.addLayout(self.trailing_layout)

        # 事件绑定
        self.close_dot.clicked.connect(self._do_close)
        self.min_dot.clicked.connect(self._do_min)
        self.max_dot.clicked.connect(self._do_max)

    def add_trailing(self, widget):
        """在标题栏右侧追加控件（不参与拖动）"""
        self.trailing_layout.addWidget(widget)

    # ---------------- 窗口操作 ----------------
    def _win(self):
        return self.window()

    def _do_close(self):
        self._win().close()

    def _do_min(self):
        self._win().showMinimized()

    def _do_max(self):
        win = self._win()
        if win.isMaximized():
            win.showNormal()
        else:
            win.showMaximized()

    # ---------------- 拖动移动 ----------------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            win = self._win()
            if win.isMaximized():
                return  # 最大化状态不拖动，避免坐标跳变
            self._drag_start = event.globalPos()
            self._drag_start_pos = win.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start is not None and event.buttons() & Qt.LeftButton:
            self._win().move(self._drag_start_pos + event.globalPos() - self._drag_start)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_start = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._do_max()
        super().mouseDoubleClickEvent(event)
