#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
统一对话框基建（二开新增）

目的：终结「弹窗风格各自为政」——此前 6 个自定义 QDialog 的边距、标题字号、
按钮排布、样式拼装方式各写各的（MODERN+DIALOG / MODERN+TOOLTIP+DIALOG 混用，
内联硬编码色），原生 QMessageBox 更是完全脱离主题。

约定：
- 所有对话框样式统一 = MODERN_STYLE + TOOLTIP_STYLE + DIALOG_STYLE（一份 QSS）；
- 内联 QSS 一律写「浅色词汇」（theme.py 的声明级重映射才能在深色主题下翻译），
  Python 手绘色一律走 theme.t()；
- 按钮四档语义：primary（主操作，蓝实心）/ secondary（次操作，浅蓝底）/
  ghost（弱操作，透明+细边）/ danger（危险操作，红实心）；
- 按钮行：左侧 stretch，按钮按传入顺序从左到右（主操作自然落在最右，Win11 习惯）；
- 标题 17px bold / 副标题 13px text_sub / 边距 22-20-22-18 / 竖向间距 14。
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QDialog, QHBoxLayout, QLabel, QMessageBox,
                              QPushButton, QVBoxLayout, QWidget)

from gui.styles import MODERN_STYLE, TOOLTIP_STYLE, DIALOG_STYLE

# 按钮语义档位 → QSS objectName（styles.py 已有全套四档样式）
ROLE_OBJECT = {
    "primary":   "primaryButton",
    "secondary": "secondaryButton",
    "ghost":     "ghostButton",
    "danger":    "dangerButton",
}

# 兼容旧代码里直接传 objectName 的写法
_OBJECT_ALIASES = {
    "primaryButton":   "primaryButton",
    "secondaryButton": "secondaryButton",
    "ghostButton":     "ghostButton",
    "dangerButton":    "dangerButton",
    "warningButton":   "warningButton",
    "dangerGhostButton": "dangerGhostButton",
}


def make_button(text, role="secondary", parent=None, tip=None):
    """按语义档位造一个统一样式的按钮（对话框外也可复用）"""
    btn = QPushButton(text, parent)
    obj = ROLE_OBJECT.get(role) or _OBJECT_ALIASES.get(role, "secondaryButton")
    btn.setObjectName(obj)
    btn.setCursor(Qt.PointingHandCursor)
    if tip:
        btn.setToolTip(tip)
    return btn


class BaseDialog(QDialog):
    """统一对话框骨架：标题 + 副标题 + 内容区 + 按钮行。

    子类典型用法：
        dlg = BaseDialog("标题", "副标题说明", self, min_width=520)
        lay = dlg.content_layout()
        lay.addWidget(...)                     # 往内容区放东西
        dlg.add_button("复制", "secondary", self.copy)
        dlg.add_button("生成", "primary", self.generate)
        dlg.exec_()
    也可以直接用（show_xxx 类场景）：内容区空着，只放按钮。
    """

    def __init__(self, title, subtitle="", parent=None, min_width=520,
                 min_height=None, window_title=None):
        super().__init__(parent)
        self.setWindowTitle(window_title or title or "对话框")
        self.setMinimumWidth(min_width)
        if min_height:
            self.setMinimumHeight(min_height)
        # 一份统一 QSS：所有对话框（含 QMessageBox 段）都吃这套
        self.setStyleSheet(MODERN_STYLE + TOOLTIP_STYLE + DIALOG_STYLE)

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(22, 20, 22, 18)
        self._root.setSpacing(14)

        # ---- 标题区 ----
        if title:
            t = QLabel(title)
            t.setObjectName("dlgTitle")
            t.setStyleSheet(
                "font-size: 17px; font-weight: bold; color: #1F2A37;"
                "background: transparent;")
            self._root.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setObjectName("dlgSubtitle")
            s.setWordWrap(True)
            s.setStyleSheet(
                "font-size: 13px; color: #5F6B7A; background: transparent;"
                "line-height: 1.5;")
            self._root.addWidget(s)

        # ---- 内容区（子类填充） ----
        self._content = QVBoxLayout()
        self._content.setSpacing(10)
        self._root.addLayout(self._content, 1)

        # ---- 按钮行 ----
        self._btn_row = QHBoxLayout()
        self._btn_row.setSpacing(10)
        self._btn_row.addStretch()
        self._root.addLayout(self._btn_row)

    def content_layout(self):
        """内容区布局：子类往这里 addWidget / addLayout"""
        return self._content

    def add_content(self, widget, stretch=0):
        self._content.addWidget(widget, stretch)
        return widget

    def add_button(self, text, role="secondary", callback=None,
                   close_on_click=True, tip=None):
        """加一个按钮。callback 为 None 时仅关闭不做事。
        close_on_click=False：点了不关对话框（如表单校验失败后再试）"""
        btn = make_button(text, role, self, tip)
        if callback is None and not close_on_click:
            raise ValueError("无回调且不关闭的按钮没有行为，别加")
        btn.clicked.connect(lambda _=False, f=callback: self._on_btn(f, close_on_click))
        self._btn_row.addWidget(btn)
        return btn

    def _on_btn(self, callback, close_on_click):
        if close_on_click:
            self.accept()
        if callback:
            callback()

    def add_close_button(self, text="关闭", role="ghost"):
        """信息型对话框统一的收尾按钮（永远只是关闭）"""
        btn = make_button(text, role, self)
        btn.clicked.connect(self.reject)
        self._btn_row.addWidget(btn)
        return btn


# ---------------------------------------------------------------- 消息框
def _styled_box(parent, icon, title, text, buttons, default_role=None):
    """QMessageBox 统一样式封装（info/warn/error/question 全走这里）。
    default_role：按钮元组里的角色值，命中者设为默认按钮（回车行为）"""
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(icon)
    box.setStyleSheet(MODERN_STYLE + TOOLTIP_STYLE + DIALOG_STYLE)
    for text_, role in buttons:
        b = box.addButton(text_, role)
        if default_role is not None and role == default_role:
            box.setDefaultButton(b)
    box.exec_()
    return box.clickedButton()


def info_box(parent, title, text, ok="知道了"):
    _styled_box(parent, QMessageBox.Information, title, text,
                [(ok, QMessageBox.AcceptRole)], None)


def warn_box(parent, title, text, ok="知道了"):
    _styled_box(parent, QMessageBox.Warning, title, text,
                [(ok, QMessageBox.AcceptRole)], None)


def error_box(parent, title, text, ok="知道了"):
    _styled_box(parent, QMessageBox.Critical, title, text,
                [(ok, QMessageBox.AcceptRole)], None)


def question_box(parent, title, text, ok="确定", cancel="取消", default="cancel"):
    """两键确认框，返回 True=用户点了 ok。

    default: 回车默认按钮——cancel（安全，危险确认的回车保护）或 ok
    """
    roles = [(ok, QMessageBox.YesRole), (cancel, QMessageBox.NoRole)]
    role = (QMessageBox.YesRole if str(default).lower() == "ok"
            else QMessageBox.NoRole)
    clicked = _styled_box(parent, QMessageBox.Question, title, text, roles, role)
    return clicked is not None and clicked.text() == ok


def confirm_box(parent, title, text, danger=False, ok="确定", cancel="取消"):
    """危险操作确认（与 question_box 的区别：文案视觉上更醒目）"""
    return question_box(parent, title, text, ok=ok, cancel=cancel)
