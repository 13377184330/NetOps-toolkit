#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
NetOps Toolkit - 现代圆角主题 v5.0（二开重做）
设计语言对标腾讯电脑管家：浅色 + 中性细边框 + 反馈式聚焦 + 明显圆角
所有 objectName 接口（primaryButton/ghostButton/secondaryButton/...）与上游保持兼容
"""

# ---------------- 设计 Token ----------------
ACCENT = "#0089FF"        # 主蓝（hover 深一档 #0077E6，pressed #006AD5）
ACCENT_HOVER = "#0077E6"
ACCENT_PRESSED = "#006AD5"
ACCENT_LIGHT = "#EAF4FF"  # 主蓝浅底（选中/悬浮高亮）
SUCCESS = "#34C759"
SUCCESS_HOVER = "#2EB350"
DANGER = "#FA5151"
DANGER_HOVER = "#E64646"
WARNING = "#FA9D3B"
WARNING_HOVER = "#E88E2F"
BG = "#ECF0F6"            # 窗口底（略深一档，衬托白卡片）
CARD = "#FFFFFF"          # 卡片底
BORDER = "#DFE6F0"        # 中性细边
BORDER_STRONG = "#C9D4E3"  # hover 边
TEXT = "#1F2A37"          # 主文字
TEXT_SUB = "#5F6B7A"      # 次文字（#7A8699 在 #ECF0F6 上仅 3.2:1，不达 4.5:1）
TEXT_MUTED = "#8A95A6"    # 装饰性弱文字（不承载信息时用）
DISABLED_BG = "#F5F7FA"
DISABLED_TEXT = "#B3BCCB"

# 图标：QSS 画不出三角形/对勾，用运行时生成的 PNG（见 gui/ui_assets.py）
from gui.ui_assets import URL_CHEVRON_DOWN, URL_CHEVRON_UP, URL_CHECK_WHITE

# 取不到图标时退化为无图标规则，避免 QSS 出现 url("") 这种空值
_ARROW_RULE = (
    f'image: {URL_CHEVRON_DOWN}; width: 12px; height: 8px; margin-right: 10px;'
    if URL_CHEVRON_DOWN else "image: none;"
)
_CHECK_RULE = f'image: {URL_CHECK_WHITE};' if URL_CHECK_WHITE else ""

MODERN_STYLE = f"""
* {{
    font-family: "Microsoft YaHei UI", "Segoe UI", Arial, sans-serif;
}}

QMainWindow {{
    background: transparent;
}}

QWidget {{
    font-size: 14px;
    color: {TEXT};
    background: transparent;
}}

QLabel {{
    color: {TEXT};
    font-size: 14px;
    background: transparent;
}}

/* ---------- 卡片分组 ---------- */
QGroupBox {{
    font-weight: bold;
    font-size: 15px;
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 16px;
    padding: 36px 20px 20px 20px;
    background: {CARD};
}}

QGroupBox::title {{
    subcontrol-origin: padding;
    subcontrol-position: top left;
    left: 20px;
    top: 13px;
    padding: 0;
    background: transparent;
    color: {TEXT};
    font-size: 16px;
}}

/* ---------- 输入控件：中性默认边 + 聚焦变蓝 ---------- */
QLineEdit {{
    padding: 10px 14px;
    border: 1px solid {BORDER};
    border-radius: 11px;
    background: {CARD};
    color: {TEXT};
    font-size: 14px;
    selection-background-color: {ACCENT};
    selection-color: #ffffff;
}}

QLineEdit:hover {{
    border: 1px solid #C9D4E3;
}}

QLineEdit:focus {{
    border: 2px solid {ACCENT};
    padding: 9px 13px;
    background: {CARD};
}}

QLineEdit:disabled {{
    background: {DISABLED_BG};
    border-color: {BORDER};
    color: {DISABLED_TEXT};
}}

QSpinBox, QDoubleSpinBox {{
    padding: 6px 10px 6px 12px;
    border: 1px solid {BORDER};
    border-radius: 10px;
    background: {CARD};
    color: {TEXT};
    font-size: 13px;
}}

QSpinBox:hover, QDoubleSpinBox:hover {{
    border: 1px solid #C9D4E3;
}}

QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 2px solid {ACCENT};
    padding: 5px 9px 5px 11px;
}}

QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    background: transparent;
    border: none;
    width: 22px;
    color: {TEXT_SUB};
}}

QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background: {ACCENT_LIGHT};
    border-radius: 6px;
}}

/* 上下箭头：样式化按钮后 Qt 不再画原生箭头，必须显式给图，否则按钮是空白块 */
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: {URL_CHEVRON_UP or "none"};
    width: 10px;
    height: 7px;
}}

QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: {URL_CHEVRON_DOWN or "none"};
    width: 10px;
    height: 7px;
}}

QComboBox {{
    padding: 10px 14px;
    border: 1px solid {BORDER};
    border-radius: 11px;
    background: {CARD};
    color: {TEXT};
    font-size: 14px;
    min-width: 6em;
}}

QComboBox:hover {{
    border: 1px solid #C9D4E3;
}}

QComboBox:focus {{
    border: 2px solid {ACCENT};
    padding: 9px 13px;
}}

QComboBox:disabled {{
    background: {DISABLED_BG};
    border-color: {BORDER};
    color: {DISABLED_TEXT};
}}

QComboBox::drop-down {{
    border: none;
    width: 28px;
    background: transparent;
}}

QComboBox::down-arrow {{
    {_ARROW_RULE}
}}

QComboBox QAbstractItemView {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 6px;
    outline: none;
    selection-background-color: {ACCENT_LIGHT};
    selection-color: {ACCENT};
}}

/* ---------- 按钮 ---------- */
QPushButton {{
    padding: 11px 30px;
    border-radius: 11px;
    font-weight: bold;
    font-size: 14px;
    border: 1px solid {BORDER};
    color: {TEXT};
    background: {CARD};
}}

QPushButton:hover {{
    background: #F7F9FC;
    border: 1px solid #C9D4E3;
}}

QPushButton:pressed {{
    background: {ACCENT_LIGHT};
}}

QPushButton:disabled {{
    color: {DISABLED_TEXT};
    background: {DISABLED_BG};
    border: 1px solid {BORDER};
}}

QPushButton#primaryButton {{
    background: {ACCENT};
    color: #ffffff;
    border: none;
}}

QPushButton#primaryButton:hover {{
    background: {ACCENT_HOVER};
}}

QPushButton#primaryButton:pressed {{
    background: {ACCENT_PRESSED};
}}

QPushButton#primaryButton:disabled {{
    background: #A8CDF5;
    color: #ffffff;
}}

QPushButton#secondaryButton {{
    background: {ACCENT_LIGHT};
    color: {ACCENT};
    border: 1px solid rgba(0, 137, 255, 0.25);
}}

QPushButton#secondaryButton:hover {{
    background: #D8EAFF;
}}

QPushButton#warningButton {{
    background: {WARNING};
    color: #ffffff;
    border: none;
}}

QPushButton#warningButton:hover {{
    background: {WARNING_HOVER};
}}

QPushButton#dangerButton {{
    background: {DANGER};
    color: #ffffff;
    border: none;
}}

QPushButton#dangerButton:hover {{
    background: {DANGER_HOVER};
}}

QPushButton#ghostButton {{
    background: transparent;
    border: 1px solid {BORDER};
    color: {TEXT};
}}

QPushButton#ghostButton:hover {{
    border: 1px solid {ACCENT};
    color: {ACCENT};
    background: {ACCENT_LIGHT};
}}

QPushButton#dangerGhostButton {{
    background: {CARD};
    border: 1px solid {BORDER};
    color: {DANGER};
}}

QPushButton#dangerGhostButton:hover {{
    background: #FDEEEE;
    border: 1px solid {DANGER};
    color: {DANGER_HOVER};
}}

/* ---------- 列表 / 文本区 ---------- */
QListWidget {{
    border: 1px solid {BORDER};
    border-radius: 12px;
    background: {CARD};
    outline: none;
}}

QListWidget::item {{
    padding: 11px 14px;
    border-bottom: 1px solid {BG};
    color: {TEXT};
    border-radius: 9px;
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

QTextEdit, QPlainTextEdit {{
    border: 1px solid {BORDER};
    border-radius: 12px;
    background: {CARD};
    color: {TEXT};
    padding: 12px;
    font-family: "Consolas", "Microsoft YaHei UI", monospace;
    font-size: 14px;
    line-height: 1.6;
    selection-background-color: {ACCENT};
    selection-color: #ffffff;
}}

QTextEdit:hover, QPlainTextEdit:hover {{
    border: 1px solid #C9D4E3;
}}

QTextEdit:focus, QPlainTextEdit:focus {{
    border: 2px solid {ACCENT};
    padding: 9px;
}}

/* ---------- 复选 / 单选 ---------- */
QCheckBox {{
    spacing: 9px;
    color: {TEXT};
    background: transparent;
}}

QCheckBox::indicator {{
    width: 19px;
    height: 19px;
    border-radius: 6px;
    border: 1px solid #C9D4E3;
    background: {CARD};
}}

QCheckBox::indicator:hover {{
    border: 1px solid {ACCENT};
}}

QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
    {_CHECK_RULE}
}}

QCheckBox::indicator:checked:hover {{
    background: {ACCENT_HOVER};
    border-color: {ACCENT_HOVER};
}}

QCheckBox::indicator:indeterminate {{
    background: {ACCENT};
    border-color: {ACCENT};
}}

QRadioButton {{
    spacing: 9px;
    color: {TEXT};
    background: transparent;
}}

QRadioButton::indicator {{
    width: 19px;
    height: 19px;
    border-radius: 10px;
    border: 1px solid #C9D4E3;
    background: {CARD};
}}

QRadioButton::indicator:hover {{
    border: 1px solid {ACCENT};
}}

QRadioButton::indicator:checked {{
    border: 5px solid {ACCENT};
    background: {CARD};
}}

/* ---------- 标签页：胶囊式 ---------- */
QTabWidget::pane {{
    border: none;
    border-radius: 12px;
    background: {CARD};
}}

QTabBar {{
    background: transparent;
}}

QTabBar::tab {{
    background: transparent;
    color: #5A6B7B;
    padding: 11px 26px;
    margin: 3px 2px;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    border-bottom-left-radius: 10px;
    border-bottom-right-radius: 10px;
    font-weight: bold;
    font-size: 14px;
}}

QTabBar::tab:selected {{
    background: {ACCENT};
    color: #ffffff;
}}

QTabBar::tab:hover:!selected {{
    background: #E8EDF5;
    color: {TEXT};
}}

QTabBar::tab:!selected {{
    margin-top: 4px;
}}

/* ---------- 分割器 / 滚动条 ---------- */
QSplitter::handle {{
    background: transparent;
}}

QSplitter::handle:hover {{
    background: rgba(0, 137, 255, 0.15);
}}

QSplitter::handle:horizontal {{
    width: 3px;
}}

QSplitter::handle:vertical {{
    height: 3px;
}}

QScrollBar:vertical {{
    border: none;
    background: transparent;
    width: 10px;
    margin: 2px 4px 2px 0;
}}

QScrollBar::handle:vertical {{
    background: #CBD5E3;
    min-height: 36px;
    border-radius: 3px;
}}

QScrollBar::handle:vertical:hover {{
    background: #AEBACB;
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

/* ---------- 表格 ---------- */
QTableWidget, QTableView {{
    gridline-color: {BG};
    border: 1px solid {BORDER};
    border-radius: 12px;
    background: {CARD};
    alternate-background-color: #FAFBFD;
    selection-background-color: {ACCENT_LIGHT};
    selection-color: {TEXT};
    color: {TEXT};
}}

QTableWidget::item, QTableView::item {{
    padding: 11px 10px;
    border: none;
}}

QTableWidget::item:selected, QTableView::item:selected {{
    background: {ACCENT_LIGHT};
    color: {ACCENT};
    font-weight: bold;
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
    padding: 12px 10px;
    border: none;
    border-bottom: 1px solid {BORDER};
    border-right: 1px solid {BG};
    font-weight: bold;
    font-size: 13px;
}}

QHeaderView::section:hover {{
    color: {TEXT};
}}

QHeaderView::section:first {{
    border-top-left-radius: 12px;
}}

QHeaderView::section:last {{
    border-top-right-radius: 12px;
}}

/* ---------- 进度条 / 状态栏 ---------- */
QProgressBar {{
    border: none;
    border-radius: 8px;
    text-align: center;
    background: #E8EDF5;
    color: {TEXT};
    font-weight: bold;
    min-height: 14px;
    max-height: 14px;
}}

QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 8px;
}}

QStatusBar {{
    /* 原白底会把窗口 12px 圆角切出一个直角（左下角实测），改为透明让圆角透出来 */
    background: transparent;
    color: {TEXT_SUB};
    font-size: 12px;
    padding: 0 8px 4px 8px;
    border: none;
}}

QStatusBar::item {{
    border: none;
}}

/* ---------- 菜单栏 / 菜单（融合无边框窗口）---------- */
QMenuBar {{
    background: transparent;
    color: {TEXT};
    font-weight: bold;
    border-bottom: none;
    border-radius: 9px;
    padding-left: 14px;
}}

QMenuBar::item {{
    padding: 8px 12px;
    background: transparent;
    border-radius: 9px;
    margin: 2px 0;
}}

QMenuBar::item:selected {{
    background: {ACCENT_LIGHT};
    color: {ACCENT};
}}

QMenuBar::item:hover:!selected {{
    background: #E8EDF5;
    color: {TEXT};
}}

QMenu {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 12px;
    padding: 6px;
}}

QMenu::item {{
    padding: 11px 34px 11px 16px;
    border-radius: 9px;
    font-size: 14px;
}}

QMenu::item:selected {{
    background: {ACCENT_LIGHT};
    color: {ACCENT};
}}

QMenu::separator {{
    height: 1px;
    background: {BORDER};
    margin: 5px 10px;
}}

/* ---------- 滑块 ---------- */
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

/* ---------- 提示 ---------- */
QToolTip {{
    background: {TEXT};
    color: #ffffff;
    border: none;
    border-radius: 8px;
    padding: 7px 12px;
    font-size: 12px;
}}
"""

TOOLTIP_STYLE = """
QToolTip {
    background: #1F2A37;
    color: #ffffff;
    border: none;
    border-radius: 8px;
    padding: 7px 12px;
    font-size: 12px;
}
"""

DIALOG_STYLE = f"""
QDialog {{
    background: {BG};
    border-radius: 14px;
}}

/* ---------- 对话框标题/副标题（BaseDialog 统一骨架）---------- */
QLabel#dlgTitle {{
    font-size: 17px;
    font-weight: bold;
    color: {TEXT};
    background: transparent;
}}

QLabel#dlgSubtitle {{
    font-size: 13px;
    color: {TEXT_SUB};
    background: transparent;
}}

/* ---------- 统一消息框（base.py 的 info/warn/error/question 走这里）---------- */
QMessageBox {{
    background: {BG};
}}

QMessageBox QLabel {{
    color: {TEXT};
    font-size: 14px;
    background: transparent;
    border: none;
}}

QMessageBox QPushButton {{
    min-width: 96px;
}}

QMessageBox QLabel#qt_msgbox_label {{
    min-width: 240px;
}}
"""

# 兼容上游导出的颜色常量（更新为新主题色）
LABEL_STYLE = f"color: {TEXT}; font-weight: bold;"
SECONDARY_LABEL_STYLE = f"color: {TEXT_SUB};"
SUCCESS_STYLE = f"color: {SUCCESS}; font-weight: bold;"
ERROR_STYLE = f"color: {DANGER}; font-weight: bold;"
WARNING_STYLE = f"color: {WARNING}; font-weight: bold;"
INFO_STYLE = f"color: {ACCENT};"
