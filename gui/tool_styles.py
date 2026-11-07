#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
网络工具箱样式 v5（二开重做）

与主窗口共用同一套设计 Token（gui/styles.py），只是工具箱偏"紧凑密度"：
字号 13px、控件内边距略小。原来这里是一套独立的 Material 蓝（#1976D2 /
#0077E6 / #4DA8FF / #BBDEFB…），从主窗口点进任一工具就像换了个软件。

所有常量名保持与旧版一致，工具代码无需改动。
"""

from gui.styles import (
    ACCENT, ACCENT_HOVER, ACCENT_LIGHT, BORDER, BORDER_STRONG,
    TEXT, TEXT_SUB, CARD, BG, DISABLED_BG, DISABLED_TEXT,
    SUCCESS, DANGER, WARNING,
    URL_CHEVRON_DOWN, URL_CHEVRON_UP, URL_CHECK_WHITE,
)

# ---------------- 文本 ----------------
# 旧版标签是 #0077E6 加粗（满屏蓝字）。主窗口表单标签是深色加粗，这里对齐。
TOOL_LABEL_STYLE = f"color: {TEXT}; font-weight: bold;"
TOOL_LABEL_SECONDARY = f"color: {TEXT_SUB};"

# ---------------- 容器 ----------------
TOOL_GROUP_STYLE = f"""
QGroupBox {{
    font-weight: bold;
    font-size: 13px;
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 14px;
    margin-top: 12px;
    padding: 14px 14px 12px 14px;
    background: {CARD};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 8px;
    color: {TEXT};
}}
"""

# ---------------- 输入 ----------------
TOOL_INPUT_STYLE = f"""
QLineEdit {{
    padding: 7px 11px;
    border: 1px solid {BORDER};
    border-radius: 10px;
    background: {CARD};
    color: {TEXT};
    font-size: 13px;
    selection-background-color: {ACCENT};
    selection-color: #FFFFFF;
}}
QLineEdit:hover {{
    border: 1px solid {BORDER_STRONG};
}}
QLineEdit:focus {{
    border: 2px solid {ACCENT};
    padding: 6px 10px;
}}
QLineEdit:disabled {{
    background: {DISABLED_BG};
    color: {DISABLED_TEXT};
}}
"""

TOOL_SPINBOX_STYLE = f"""
QSpinBox, QDoubleSpinBox {{
    padding: 6px 8px;
    border: 1px solid {BORDER};
    border-radius: 10px;
    background: {CARD};
    color: {TEXT};
    font-size: 13px;
}}
QSpinBox:hover, QDoubleSpinBox:hover {{
    border: 1px solid {BORDER_STRONG};
}}
QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 2px solid {ACCENT};
    padding: 5px 7px;
}}
/* 旧版把上下按钮刷成 #0089FF 实心方块（截图里就是两块蓝），且不给箭头图，
   看起来像坏掉的控件。改成透明按钮 + 箭头图标 + 悬浮浅蓝。 */
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    background: transparent;
    border: none;
    width: 18px;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{
    background: {ACCENT_LIGHT};
    border-radius: 6px;
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: {URL_CHEVRON_UP or "none"};
    width: 9px;
    height: 6px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: {URL_CHEVRON_DOWN or "none"};
    width: 9px;
    height: 6px;
}}
"""

TOOL_COMBO_STYLE = f"""
QComboBox {{
    padding: 7px 11px;
    border: 1px solid {BORDER};
    border-radius: 10px;
    background: {CARD};
    color: {TEXT};
    font-size: 13px;
}}
QComboBox:hover {{
    border: 1px solid {BORDER_STRONG};
}}
QComboBox:focus {{
    border: 2px solid {ACCENT};
    padding: 6px 10px;
}}
QComboBox::drop-down {{
    border: none;
    width: 26px;
    background: transparent;
}}
/* 旧版这里用 border 拼三角形，Qt 不认，实际渲染成一根竖条 */
QComboBox::down-arrow {{
    image: {URL_CHEVRON_DOWN or "none"};
    width: 12px;
    height: 8px;
    margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 6px;
    outline: none;
    selection-background-color: {ACCENT_LIGHT};
    selection-color: {ACCENT};
    color: {TEXT};
}}
"""

TOOL_TEXTEDIT_STYLE = f"""
QTextEdit, QPlainTextEdit {{
    border: 1px solid {BORDER};
    border-radius: 12px;
    background: {CARD};
    color: {TEXT};
    padding: 10px;
    font-size: 13px;
    selection-background-color: {ACCENT};
    selection-color: #FFFFFF;
}}
QTextEdit:hover, QPlainTextEdit:hover {{
    border: 1px solid {BORDER_STRONG};
}}
QTextEdit:focus, QPlainTextEdit:focus {{
    border: 2px solid {ACCENT};
    padding: 9px;
}}
"""

# ---------------- 数据展示 ----------------
TOOL_TABLE_STYLE = f"""
QTableWidget, QTableView {{
    gridline-color: {BG};
    border: 1px solid {BORDER};
    border-radius: 12px;
    background: {CARD};
    alternate-background-color: #FAFBFD;
    selection-background-color: {ACCENT_LIGHT};
    selection-color: {ACCENT};
    color: {TEXT};
    font-size: 13px;
}}
QTableWidget::item, QTableView::item {{
    padding: 7px 8px;
    border: none;
}}
QTableWidget::item:selected, QTableView::item:selected {{
    background: {ACCENT_LIGHT};
    color: {ACCENT};
}}
QTableWidget::item:hover, QTableView::item:hover {{
    background: #F3F8FF;
}}
QHeaderView {{
    background: {CARD};
    border: none;
}}
QHeaderView::section {{
    background: #F7F9FC;
    color: {TEXT_SUB};
    padding: 9px 8px;
    border: none;
    border-bottom: 1px solid {BORDER};
    border-right: 1px solid {BG};
    font-weight: bold;
    font-size: 12px;
}}
"""

TOOL_LIST_STYLE = f"""
QListWidget {{
    border: 1px solid {BORDER};
    border-radius: 12px;
    background: {CARD};
    outline: none;
}}
QListWidget::item {{
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid {BG};
    color: {TEXT};
    border-radius: 8px;
    margin: 2px 4px;
}}
QListWidget::item:selected {{
    background: {ACCENT_LIGHT};
    color: {ACCENT};
    font-weight: bold;
}}
QListWidget::item:hover:!selected {{
    background: #F7F9FC;
}}
"""

TOOL_TREE_STYLE = f"""
QTreeWidget {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 12px;
    color: {TEXT};
    font-size: 13px;
}}
QTreeWidget::item {{
    padding: 5px;
    border: none;
    border-radius: 6px;
}}
QTreeWidget::item:selected {{
    background: {ACCENT_LIGHT};
    color: {ACCENT};
}}
QTreeWidget::item:hover {{
    background: #F3F8FF;
}}
QTreeWidget::branch {{
    background: transparent;
}}
"""

# ---------------- 选择控件 ----------------
_CHECK_IMG = f"image: {URL_CHECK_WHITE};" if URL_CHECK_WHITE else ""

TOOL_CHECKBOX_STYLE = f"""
QCheckBox {{
    spacing: 8px;
    color: {TEXT};
    font-size: 13px;
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 6px;
    border: 1px solid {BORDER_STRONG};
    background: {CARD};
}}
QCheckBox::indicator:hover {{
    border: 1px solid {ACCENT};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
    {_CHECK_IMG}
}}
"""

TOOL_RADIO_STYLE = f"""
QRadioButton {{
    spacing: 8px;
    color: {TEXT};
    font-size: 13px;
}}
QRadioButton::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 9px;
    border: 1px solid {BORDER_STRONG};
    background: {CARD};
}}
QRadioButton::indicator:hover {{
    border: 1px solid {ACCENT};
}}
QRadioButton::indicator:checked {{
    border: 5px solid {ACCENT};
    background: {CARD};
}}
"""

# ---------------- 导航 / 进度 ----------------
TOOL_TAB_STYLE = f"""
QTabWidget::pane {{
    border: none;
    border-radius: 12px;
    background: transparent;
}}
QTabBar {{
    background: transparent;
}}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_SUB};
    padding: 9px 18px;
    margin: 2px 3px;
    border-radius: 10px;
    font-weight: bold;
    font-size: 13px;
}}
QTabBar::tab:selected {{
    background: {ACCENT};
    color: #FFFFFF;
}}
QTabBar::tab:hover:!selected {{
    background: #E2E9F3;
    color: {TEXT};
}}
"""

TOOL_PROGRESS_STYLE = f"""
QProgressBar {{
    border: none;
    border-radius: 8px;
    background: #E8EDF5;
    text-align: center;
    color: {TEXT};
    font-weight: bold;
    min-height: 14px;
    max-height: 14px;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 8px;
}}
"""

TOOL_SLIDER_STYLE = f"""
QSlider::groove:horizontal {{
    height: 6px;
    background: #E8EDF5;
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: {CARD};
    border: 2px solid {ACCENT};
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 9px;
}}
QSlider::handle:horizontal:hover {{
    background: {ACCENT};
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 3px;
}}
"""

TOOL_SCROLL_STYLE = f"""
QScrollBar:vertical {{
    border: none;
    background: transparent;
    width: 12px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #D3DBE7;
    min-height: 36px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical:hover {{
    background: #B7C3D4;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar:horizontal {{
    border: none;
    background: transparent;
    height: 12px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: #D3DBE7;
    min-width: 36px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal:hover {{
    background: #B7C3D4;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}
"""

TOOL_TOOLTIP_STYLE = f"""
QToolTip {{
    background: {TEXT};
    color: #FFFFFF;
    border: none;
    border-radius: 8px;
    padding: 7px 12px;
    font-size: 12px;
}}
"""

TOOL_TOOLBUTTON_STYLE = f"""
QToolButton {{
    padding: 8px 12px;
    border-radius: 10px;
    background: transparent;
    color: {TEXT};
    border: 1px solid {BORDER};
}}
QToolButton:hover {{
    background: {ACCENT_LIGHT};
    border-color: {ACCENT};
    color: {ACCENT};
}}
QToolButton:pressed {{
    background: #D8EAFF;
}}
"""

# ---------------- 按钮 ----------------
TOOL_BUTTON_PRIMARY = f"""
QPushButton {{
    padding: 9px 22px;
    border-radius: 10px;
    font-weight: bold;
    font-size: 13px;
    border: none;
    background: {ACCENT};
    color: #FFFFFF;
}}
QPushButton:hover {{
    background: {ACCENT_HOVER};
}}
QPushButton:pressed {{
    background: {ACCENT_HOVER};
}}
QPushButton:disabled {{
    background: #A8CDF5;
    color: #FFFFFF;
}}
"""

TOOL_BUTTON_SECONDARY = f"""
QPushButton {{
    padding: 9px 22px;
    border-radius: 10px;
    font-weight: bold;
    font-size: 13px;
    border: 1px solid rgba(0, 137, 255, 0.25);
    background: {ACCENT_LIGHT};
    color: {ACCENT};
}}
QPushButton:hover {{
    background: #D8EAFF;
}}
QPushButton:disabled {{
    background: {DISABLED_BG};
    color: {DISABLED_TEXT};
    border-color: {BORDER};
}}
"""

TOOL_BUTTON_DANGER = f"""
QPushButton {{
    padding: 9px 22px;
    border-radius: 10px;
    font-weight: bold;
    font-size: 13px;
    border: none;
    background: {DANGER};
    color: #FFFFFF;
}}
QPushButton:hover {{
    background: #E64646;
}}
QPushButton:disabled {{
    background: {DISABLED_BG};
    color: {DISABLED_TEXT};
}}
"""

TOOL_BUTTON_GHOST = f"""
QPushButton {{
    padding: 9px 22px;
    border-radius: 10px;
    font-weight: bold;
    font-size: 13px;
    background: transparent;
    border: 1px solid {BORDER};
    color: {TEXT};
}}
QPushButton:hover {{
    border: 1px solid {ACCENT};
    color: {ACCENT};
    background: {ACCENT_LIGHT};
}}
QPushButton:disabled {{
    color: {DISABLED_TEXT};
    border-color: {BORDER};
}}
"""

# ---------------- 状态文字 ----------------
TOOL_STATUS_SUCCESS = f"color: {SUCCESS}; font-weight: bold;"
TOOL_STATUS_ERROR = f"color: {DANGER}; font-weight: bold;"
TOOL_STATUS_WARNING = f"color: {WARNING}; font-weight: bold;"
TOOL_STATUS_INFO = f"color: {ACCENT};"

RESULT_HEADER = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

RESULT_FOOTER = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""


def apply_tool_style(widget):
    """为工具窗口应用统一基础样式"""
    widget.setStyleSheet(f"""
        QWidget {{
            font-size: 13px;
            color: {TEXT};
            background: {BG};
        }}
        QLabel {{
            color: {TEXT};
            font-size: 13px;
            background: transparent;
        }}
        {TOOL_GROUP_STYLE}
        {TOOL_INPUT_STYLE}
        {TOOL_SPINBOX_STYLE}
        {TOOL_COMBO_STYLE}
        {TOOL_TEXTEDIT_STYLE}
        {TOOL_TABLE_STYLE}
        {TOOL_LIST_STYLE}
        {TOOL_CHECKBOX_STYLE}
        {TOOL_RADIO_STYLE}
        {TOOL_TAB_STYLE}
        {TOOL_TREE_STYLE}
        {TOOL_PROGRESS_STYLE}
        {TOOL_SLIDER_STYLE}
        {TOOL_SCROLL_STYLE}
        {TOOL_TOOLTIP_STYLE}
        {TOOL_TOOLBUTTON_STYLE}
    """)
