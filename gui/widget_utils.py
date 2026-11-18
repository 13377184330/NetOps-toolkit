#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""通用 UI 小工具（二开）"""

from PyQt5.QtWidgets import QTableWidgetItem, QLayout
from PyQt5.QtCore import Qt, QRect, QPoint, QSize

_SORT_ROLE = Qt.UserRole + 1


class FlowLayout(QLayout):
    """自动折行布局：一行放不下就把后续控件挪到下一行。

    用于"工具行"这类控件多、宽度不定的横排：窗口窄时自动折行，
    而不是把整页撑宽、让右栏和底部按钮被窗口边缘切掉。
    每个 item 保持自己的 sizeHint，不参与 stretch 瓜分。
    """

    def __init__(self, parent=None, spacing=8, margin=0):
        super().__init__(parent)
        self._items = []
        self._spacing = spacing
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Vertical)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        # 最窄 = 最宽单个控件的宽度；高度交给 heightForWidth
        m = self.contentsMargins()
        w = max((it.minimumSize().width() for it in self._items), default=0)
        return QSize(w + m.left() + m.right(),
                     self.heightForWidth(w) + m.top() + m.bottom())

    def _do_layout(self, rect, test):
        m = self.contentsMargins()
        x = rect.x() + m.left()
        y = rect.y() + m.top()
        line_h = 0
        right = rect.right() - m.right()
        for item in self._items:
            w = item.sizeHint().width()
            h = item.sizeHint().height()
            if x + w > right and x > rect.x() + m.left():
                x = rect.x() + m.left()
                y += line_h + self._spacing
                line_h = 0
            if not test:
                item.setGeometry(QRect(QPoint(x, y), QSize(w, h)))
            x += w + self._spacing
            line_h = max(line_h, h)
        return y + line_h - rect.y() + m.bottom()


def page_header(title, subtitle=""):
    """页面级标题（页内容区统一层级）。

    各内容页原本直接铺 QGroupBox 卡片，切页后只有导航知道自己在哪，
    内容区零上下文。统一加「标题 17px 加粗 + 副标题 13px 次要色」，
    层级与 BaseDialog 标题栏/消息框同语言。颜色用浅色词内联，
    深色主题由 theme.py 的 setStyleSheet 补丁声明级重映射翻译。
    """
    from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(4, 0, 4, 0)
    lay.setSpacing(3)
    t = QLabel(title)
    t.setStyleSheet(
        "font-size: 17px; font-weight: bold; color: #1F2A37; background: transparent;")
    lay.addWidget(t)
    if subtitle:
        s = QLabel(subtitle)
        s.setStyleSheet(
            "font-size: 13px; color: #5F6B7A; background: transparent;")
        lay.addWidget(s)
    return w


def scroll_wrap(widget):
    """页面滚动包装：视口装不下时出滚动条（横纵皆可），绝不压缩表单卡片
    - 输入控件设最小宽，保证占位提示可读
    - 双栏页的左右面板设最小宽，每栏不被压扁
    """
    from PyQt5.QtWidgets import (QScrollArea, QFrame, QGroupBox, QWidget,
                                 QLineEdit, QSpinBox, QComboBox)
    from PyQt5.QtCore import Qt
    for editor in widget.findChildren(QLineEdit):
        editor.setMinimumWidth(max(150, editor.minimumWidth()))
    for sp in widget.findChildren(QSpinBox):
        sp.setMinimumWidth(max(110, sp.minimumWidth()))
    for cb in widget.findChildren(QComboBox):
        # 取 max：尊重控件自己声明的更大下限（如 Console 串口下拉 260，
        # 曾被这里硬设 130 打回导致长描述被截断）
        cb.setMinimumWidth(max(130, cb.minimumWidth()))
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
