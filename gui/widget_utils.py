#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""通用 UI 小工具（二开）"""

from PyQt5.QtWidgets import QTableWidgetItem
from PyQt5.QtCore import Qt

_SORT_ROLE = Qt.UserRole + 1


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


def polish_table(table, sortable=False, stretch_last=False, zebra=True):
    """表格统一观感（二开）：斑马纹 + 隐藏竖表头 + 去网格线 + 末列伸缩

    - zebra：隔行底色（QSS 里已配 alternate-background-color，两主题各自有色）
    - 去网格线 + 斑马纹是现代表格的标准搭配，比满屏细线干净
    - sortable：允许点表头排序。注意：程序化填表的代码必须在填之前
      setSortingEnabled(False)、填完再 True，否则行会边填边跳
      （本函数只在创建时调用一次，填表守卫由调用方负责）
    """
    from PyQt5.QtWidgets import QHeaderView
    table.setAlternatingRowColors(zebra)
    table.setShowGrid(False)
    table.verticalHeader().setVisible(False)
    if stretch_last:
        table.horizontalHeader().setStretchLastSection(True)
    if sortable:
        table.setSortingEnabled(True)
    return table


class NumericItemMixin:
    """按数值排序、按原样显示的表格项（"62" / "1,024" / "/26" 这类字符串
    按字符串排会得到 10 < 2、/8 > /24 的错序）"""

    def __lt__(self, other):
        a, b = self.data(_SORT_ROLE), other.data(_SORT_ROLE)
        if a is not None and b is not None:
            try:
                return a < b
            except TypeError:
                pass
        return super().__lt__(other)


def numeric_item(text, value):
    """显示 text、按 value 排序的表格项"""
    return _NumericItem(text, value)


class _NumericItem(NumericItemMixin, QTableWidgetItem):
    def __init__(self, text, value):
        super().__init__(str(text))
        self.setData(_SORT_ROLE, value)
