#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
设置对话框
"""

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QGroupBox, QComboBox, QSpinBox,
                             QCheckBox, QTabWidget, QWidget, QLineEdit,
                             QListWidget, QApplication, QSizePolicy)
from PyQt5.QtCore import Qt

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from gui.styles import (MODERN_STYLE, TOOLTIP_STYLE, DIALOG_STYLE,
                        BORDER, CARD, TEXT)
from gui.dialogs.base import BaseDialog, info_box, question_box
from utils.settings import Settings

# 分组框紧凑化（仅本对话框）：全局 QGroupBox 的 36px 标题留白是为工作区
# 大卡片调的；设置页三连组在 1280×800@200% 逻辑屏上会被 Qt 的「窗口自动
# 尺寸钳到屏幕 2/3」压碎（真机实测：内容需 601 高、实际只有 533，下拉框
# 被压到 8px）。缩到 30/18/14/18 后内容自然放得下，观感也更贴近现代设置页。
# 颜色一律用浅色词常量：theme.py 的 setStyleSheet 补丁会在深色主题下重映射。
_GROUP_QSS = f"""
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 14px;
    background: {CARD};
    padding: 30px 18px 14px 18px;
    font-weight: bold;
}}
QGroupBox::title {{
    subcontrol-origin: padding;
    subcontrol-position: top left;
    left: 18px;
    top: 10px;
    padding: 0;
    background: transparent;
    color: {TEXT};
    font-size: 15px;
}}
"""

# 输入控件最小高度：布局空间不足时绝不压碎（高 DPI 小屏实测下拉框可被压到 8px）
_FIELD_MIN_H = 40
_SPIN_MIN_H = 34


class SettingsDialog(BaseDialog):
    """系统设置对话框（统一无边框子窗口骨架）"""

    def __init__(self, parent=None):
        self.settings = Settings()
        super().__init__("系统设置", "", parent, min_width=500, min_height=450)
        self.initUI()

    # ---- 布局小工具：紧凑分组框 ----
    def _make_group(self, title):
        gb = QGroupBox(title)
        gb.setStyleSheet(_GROUP_QSS)
        lay = QVBoxLayout(gb)
        lay.setContentsMargins(0, 0, 0, 0)   # 间距由 QSS padding 统一控制
        lay.setSpacing(10)
        return gb, lay

    def _combo(self, items, current_index=0):
        combo = QComboBox()
        combo.addItems(items)
        combo.setCurrentIndex(current_index)
        combo.setMinimumHeight(_FIELD_MIN_H)
        combo.setMinimumWidth(200)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return combo

    def _spin(self, lo, hi, value):
        spin = QSpinBox()
        spin.setRange(lo, hi)
        spin.setValue(value)
        spin.setMinimumHeight(_SPIN_MIN_H)
        spin.setMinimumWidth(90)
        return spin

    def initUI(self):
        layout = self.content_layout()
        layout.setSpacing(15)

        tabs = QTabWidget()

        # ---------------- 常规页 ----------------
        general_widget = QWidget()
        general_layout = QVBoxLayout(general_widget)
        general_layout.setSpacing(12)

        theme_group, theme_layout = self._make_group("外观设置")

        theme_row = QHBoxLayout()
        theme_label = QLabel("界面主题:")
        theme_label.setStyleSheet("font-weight: bold;")
        theme_row.addWidget(theme_label)

        # 浅色 / 深色 / 跟随系统（保存的是偏好；system 在启动时归一化为实际主题）
        current_theme = self.settings.get('theme', 'light')
        theme_index = {'light': 0, 'dark': 1, 'system': 2}.get(current_theme, 0)
        self.theme_combo = self._combo(["浅色模式", "深色模式", "跟随系统"], theme_index)
        theme_row.addWidget(self.theme_combo, 1)   # 撑满行宽：不再挤在左侧留大片空白
        theme_layout.addLayout(theme_row)

        theme_hint = QLabel("保存后立即生效；「跟随系统」取 Windows 的应用亮/暗模式")
        theme_hint.setWordWrap(True)
        theme_hint.setMinimumHeight(18)
        theme_hint.setStyleSheet("color: #5F6B7A; font-size: 12px;")
        theme_layout.addWidget(theme_hint)

        toolbar_row = QHBoxLayout()
        self.show_toolbar_cb = QCheckBox("显示工具栏")
        self.show_toolbar_cb.setChecked(self.settings.get('show_toolbar', True))
        self.show_toolbar_cb.setMinimumHeight(24)
        toolbar_row.addWidget(self.show_toolbar_cb)
        toolbar_row.addStretch()
        theme_layout.addLayout(toolbar_row)

        general_layout.addWidget(theme_group)

        device_group, device_layout = self._make_group("默认设备")

        device_row = QHBoxLayout()
        device_label = QLabel("默认设备类型:")
        device_label.setStyleSheet("font-weight: bold;")
        device_row.addWidget(device_label)

        # 与标题栏的五厂商下拉保持一致（原来只有华为/H3C 两项）
        self._device_values = ["huawei", "h3c", "ruijie", "maipu", "cisco"]
        current_device = self.settings.get('default_device', 'huawei')
        device_index = (self._device_values.index(current_device)
                        if current_device in self._device_values else 0)
        self.device_combo = self._combo(["华为 (Huawei)", "H3C (华三)", "锐捷 (Ruijie)",
                                         "迈普 (Maipu)", "思科 (Cisco)"], device_index)
        device_row.addWidget(self.device_combo, 1)
        device_layout.addLayout(device_row)

        general_layout.addWidget(device_group)

        behavior_group, behavior_layout = self._make_group("行为")
        auto_save_row = QHBoxLayout()
        self.auto_save_cb = QCheckBox("自动保存配置")
        self.auto_save_cb.setChecked(self.settings.get('auto_save', True))
        self.auto_save_cb.setMinimumHeight(24)
        auto_save_row.addWidget(self.auto_save_cb)
        auto_save_row.addStretch()
        behavior_layout.addLayout(auto_save_row)
        general_layout.addWidget(behavior_group)

        general_layout.addStretch()
        tabs.addTab(general_widget, "常规")

        # ---------------- 网络页 ----------------
        network_widget = QWidget()
        network_layout = QVBoxLayout(network_widget)
        network_layout.setSpacing(12)

        timeout_group, timeout_layout = self._make_group("超时设置")

        ping_row = QHBoxLayout()
        ping_label = QLabel("Ping 次数:")
        ping_label.setStyleSheet("font-weight: bold;")
        ping_row.addWidget(ping_label)

        self.ping_count_spin = self._spin(1, 20, self.settings.get('default_ping_count', 4))
        ping_row.addWidget(self.ping_count_spin)
        ping_row.addStretch()
        timeout_layout.addLayout(ping_row)

        timeout_row = QHBoxLayout()
        timeout_label = QLabel("默认超时(秒):")
        timeout_label.setStyleSheet("font-weight: bold;")
        timeout_row.addWidget(timeout_label)

        self.timeout_spin = self._spin(1, 30, self.settings.get('default_timeout', 2))
        timeout_row.addWidget(self.timeout_spin)
        timeout_row.addStretch()
        timeout_layout.addLayout(timeout_row)

        port_row = QHBoxLayout()
        port_label = QLabel("端口扫描超时(秒):")
        port_label.setStyleSheet("font-weight: bold;")
        port_row.addWidget(port_label)

        self.port_timeout_spin = self._spin(1, 10, self.settings.get('default_port_timeout', 1))
        port_row.addWidget(self.port_timeout_spin)
        port_row.addStretch()
        timeout_layout.addLayout(port_row)

        network_layout.addWidget(timeout_group)
        network_layout.addStretch()

        tabs.addTab(network_widget, "网络")

        # ---------------- 历史页 ----------------
        history_widget = QWidget()
        history_layout = QVBoxLayout(history_widget)

        recent_group, recent_layout = self._make_group("最近主机")

        self.recent_list = QListWidget()
        self.recent_list.addItems(self.settings.get_recent_hosts())
        self.recent_list.setMinimumHeight(110)
        self.recent_list.setMaximumHeight(150)
        recent_layout.addWidget(self.recent_list)

        clear_recent_btn = QPushButton("清空历史")
        clear_recent_btn.clicked.connect(self.clear_recent_hosts)
        recent_layout.addWidget(clear_recent_btn)

        history_layout.addWidget(recent_group)
        history_layout.addStretch()

        tabs.addTab(history_widget, "历史")

        layout.addWidget(tabs)

        # 按钮行（BaseDialog 统一行：主操作自然落在最右）
        self.add_button("恢复默认", "ghost", self.reset_settings, close_on_click=False)
        self.add_close_button("取消", "ghost")
        self.add_button("保存", "primary", self.save_settings, close_on_click=False)

    def save_settings(self):
        theme_map = {0: 'light', 1: 'dark', 2: 'system'}
        new_pref = theme_map[self.theme_combo.currentIndex()]
        self.settings.set('theme', new_pref)
        # 主题即时生效（不用重启）：偏好 system 时归一化为当前系统主题
        try:
            from gui import theme as _theme
            actual = _theme.system_theme() if new_pref == 'system' else new_pref
            _theme.set_theme(actual, QApplication.instance())
        except Exception:
            pass
        self.settings.set('show_toolbar', self.show_toolbar_cb.isChecked())
        self.settings.set('default_device', self._device_values[self.device_combo.currentIndex()])
        self.settings.set('auto_save', self.auto_save_cb.isChecked())
        self.settings.set('default_ping_count', self.ping_count_spin.value())
        self.settings.set('default_timeout', self.timeout_spin.value())
        self.settings.set('default_port_timeout', self.port_timeout_spin.value())

        info_box(self, "成功", "设置已保存，部分设置需要重启生效")
        self.accept()

    def reset_settings(self):
        if question_box(self, "确认", "确定恢复默认设置？", ok="是", cancel="否"):
            self.settings.reset()
            # 恢复默认 = 浅色主题，同步把界面也切回去
            try:
                from gui import theme as _theme
                _theme.set_theme('light', QApplication.instance())
            except Exception:
                pass
            info_box(self, "成功", "已恢复默认设置")
            self.reject()

    def clear_recent_hosts(self):
        if question_box(self, "确认", "确定清空最近主机历史？", ok="是", cancel="否"):
            self.settings.set('recent_hosts', [])
            self.recent_list.clear()
            info_box(self, "成功", "历史已清空")