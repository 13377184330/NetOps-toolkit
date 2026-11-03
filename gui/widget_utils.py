#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""通用 UI 小工具（二开）"""


def scroll_wrap(widget):
    """页面滚动包装：视口装不下时出滚动条（横纵皆可），绝不压缩表单卡片
    - 输入控件设最小宽，保证占位提示可读
    - 双栏页的左右面板设最小宽，每栏不被压扁
    """
    from PyQt5.QtWidgets import (QScrollArea, QFrame, QGroupBox, QWidget,
                                 QLineEdit, QSpinBox, QComboBox)
    from PyQt5.QtCore import Qt
    for editor in widget.findChildren(QLineEdit):
        editor.setMinimumWidth(150)
    for sp in widget.findChildren(QSpinBox):
        sp.setMinimumWidth(110)
    for cb in widget.findChildren(QComboBox):
        cb.setMinimumWidth(130)
    for panel in widget.findChildren(QWidget):
        lay = panel.layout()
        if lay is None:
            continue
        if lay.count() and any(lay.itemAt(i) and isinstance(lay.itemAt(i).widget(), QGroupBox)
                               for i in range(lay.count())):
            panel.setMinimumWidth(300)
    area = QScrollArea()
    area.setWidget(widget)
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    area.setStyleSheet("QScrollArea { background: transparent; border: none; }")
    return area
