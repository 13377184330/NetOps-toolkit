#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
设置对话框
"""

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QGroupBox, QComboBox, QSpinBox,
                             QCheckBox, QTabWidget, QWidget, QLineEdit,
                             QListWidget, QApplication, QSizePolicy)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from gui.styles import (MODERN_STYLE, TOOLTIP_STYLE, DIALOG_STYLE,
                        BORDER, CARD, TEXT)
from gui.dialogs.base import BaseDialog, info_box, question_box, error_box
from utils.settings import Settings
from modules import ai_ops
from utils.credential_crypto import encrypt

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


class _AIConnTestWorker(QThread):
    """连通测试放子线程（同步测试会冻结 UI，全局铁律禁止）"""
    done = pyqtSignal(bool, str)

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self._cfg = cfg

    def run(self):
        ok, msg = ai_ops.test_connection(self._cfg)
        self.done.emit(ok, msg)


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
        self.tabs_widget = tabs  # 供 go_ai_tab() 跳页

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

        # ---------------- SNMP 配置组 ----------------
        from modules import snmp_collector as sc
        snmp_group, snmp_layout = self._make_group("SNMP 采集（端口状态/CPU/内存 · 只读）")

        cur_snmp = self.settings.get("snmp", {}) or {}
        self.snmp_community_edit = QLineEdit(cur_snmp.get("community", "public"))
        self.snmp_community_edit.setMinimumHeight(_FIELD_MIN_H)
        self.snmp_community_edit.setPlaceholderText("SNMP community（v1/v2c 只读团体字）")
        snmp_layout.addWidget(self._labeled_row("Community:", self.snmp_community_edit))

        self.snmp_version_combo = self._combo(["v2c", "v1"], 0 if cur_snmp.get("version", 2) == 2 else 1)

        def _vkey(i):
            return 2 if i == 0 else 1
        self.snmp_version_combo.currentIndexChanged.connect(
            lambda i: self.settings.data.setdefault("snmp", {}).__setitem__("version", _vkey(i)))
        snmp_layout.addWidget(self._labeled_row("版本:", self.snmp_version_combo))

        snmp_state = ("✅ 已安装 pysnmp（SNMP 采集可用）" if sc.snmp_available()
                      else "⚠ 未安装 pysnmp——命令行执行 pip install pysnmp 后重启软件即可启用")
        snmp_hint = QLabel(snmp_state + "\nSNMP 仅只读采集（get/walk），软件架构层面禁止 set 写入。")
        snmp_hint.setWordWrap(True)
        snmp_hint.setStyleSheet("color: #5F6B7A; font-size: 12px;")
        snmp_layout.addWidget(snmp_hint)

        network_layout.addWidget(snmp_group)
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

        # ---------------- AI 页 ----------------
        ai_widget = QWidget()
        ai_layout = QVBoxLayout(ai_widget)
        ai_layout.setSpacing(12)

        llm_group, llm_layout = self._make_group("大模型服务（自然语言运维）")

        # 服务商：预设自动带出地址与模型名，均可手改
        self._ai_provider_keys = list(ai_ops.PROVIDERS.keys())
        cur_ai = self.settings.get("ai", {}) or {}
        cur_pid = cur_ai.get("provider", "deepseek")
        pid_index = (self._ai_provider_keys.index(cur_pid)
                     if cur_pid in self._ai_provider_keys else 0)
        self.ai_provider_combo = self._combo(
            [ai_ops.PROVIDERS[k][0] for k in self._ai_provider_keys], pid_index)
        self.ai_provider_combo.currentIndexChanged.connect(self._fill_ai_defaults)
        llm_layout.addWidget(self._labeled_row("服务商:", self.ai_provider_combo))

        self.ai_base_edit = QLineEdit(cur_ai.get("base_url", ""))
        self.ai_base_edit.setPlaceholderText("OpenAI 兼容地址，如 https://api.deepseek.com/v1")
        self.ai_base_edit.setMinimumHeight(_FIELD_MIN_H)
        self._base_saved = self.ai_base_edit.text()
        llm_layout.addWidget(self._labeled_row("API 地址:", self.ai_base_edit))

        self.ai_model_edit = QLineEdit(cur_ai.get("model", ""))
        self.ai_model_edit.setPlaceholderText("模型名，如 deepseek-chat / glm-4-flash")
        self.ai_model_edit.setMinimumHeight(_FIELD_MIN_H)
        self._model_saved = self.ai_model_edit.text()
        llm_layout.addWidget(self._labeled_row("模型名称:", self.ai_model_edit))

        self.ai_key_edit = QLineEdit("")
        self.ai_key_edit.setEchoMode(QLineEdit.Password)
        has_key = bool(cur_ai.get("api_key_enc"))
        self.ai_key_edit.setPlaceholderText("已加密保存（留空 = 保持不变）" if has_key
                                            else "sk-…（仅存本机，Fernet 加密）")
        self.ai_key_edit.setMinimumHeight(_FIELD_MIN_H)
        llm_layout.addWidget(self._labeled_row("API Key:", self.ai_key_edit))

        test_row = QHBoxLayout()
        self.ai_test_btn = QPushButton("测试连接")
        self.ai_test_btn.setObjectName("secondaryButton")
        self.ai_test_btn.clicked.connect(self.test_ai_connection)
        test_row.addWidget(self.ai_test_btn)
        self.ai_test_label = QLabel("")
        self.ai_test_label.setStyleSheet("color: #5F6B7A; font-size: 12px;")
        self.ai_test_label.setWordWrap(True)
        test_row.addWidget(self.ai_test_label, 1)
        llm_layout.addLayout(test_row)

        # 未手填时带预设默认值（provider 预设优先，用户改过的以用户为准）
        if not self.ai_base_edit.text().strip():
            self._fill_ai_defaults()

        ai_layout.addWidget(llm_group)

        # 安全说明：与设备凭据同一套本机加密体系
        sec_group, sec_layout = self._make_group("安全说明")
        sec_text = QLabel(
            "• API Key 用本机密钥加密存储，不进 Git、不随配置导出。\n"
            "• 工具只直连你填写的 API 地址；本地 Ollama/vLLM 可完全离线。\n"
            "• AI 只生成命令草稿：所有命令必须经你逐条勾选 + 二次确认才会下发到设备，"
            "且默认不存盘。")
        sec_text.setWordWrap(True)
        sec_text.setStyleSheet("color: #5F6B7A; font-size: 12px;")
        sec_layout.addWidget(sec_text)
        ai_layout.addWidget(sec_group)
        ai_layout.addStretch()

        tabs.addTab(ai_widget, "AI")

        layout.addWidget(tabs)

        # 按钮行（BaseDialog 统一行：主操作自然落在最右）
        self.add_button("恢复默认", "ghost", self.reset_settings, close_on_click=False)
        self.add_close_button("取消", "ghost")
        self.add_button("保存", "primary", self.save_settings, close_on_click=False)

    def _labeled_row(self, label_text, field):
        row = QHBoxLayout()
        lab = QLabel(label_text)
        lab.setStyleSheet("font-weight: bold;")
        lab.setFixedWidth(76)
        row.addWidget(lab)
        row.addWidget(field, 1)
        wrap = QWidget()
        wrap.setLayout(row)
        return wrap

    def _fill_ai_defaults(self):
        """切换服务商：地址/模型带出预设默认（用户可再手改）"""
        idx = self.ai_provider_combo.currentIndex()
        if 0 <= idx < len(self._ai_provider_keys):
            _, def_url, def_model = ai_ops.PROVIDERS[self._ai_provider_keys[idx]]
            self.ai_base_edit.setText(def_url)
            self.ai_model_edit.setText(def_model)

    def go_ai_tab(self):
        """供 AI 运维页「⚙ AI 设置」直接跳到本页"""
        for i in range(self.tabs_widget.count()):
            if self.tabs_widget.tabText(i) == "AI":
                self.tabs_widget.setCurrentIndex(i)
                return

    def test_ai_connection(self):
        """用表单当前值直测（无需先保存）；子线程执行不冻结 UI"""
        cfg = {
            "base_url": self.ai_base_edit.text().strip(),
            "model": self.ai_model_edit.text().strip(),
            "api_key": self.ai_key_edit.text().strip(),
            "configured": True,
        }
        # Key 留空 = 用已存 Key 测试
        if not cfg["api_key"]:
            saved = self.settings.get("ai", {}) or {}
            from utils.credential_crypto import decrypt
            cfg["api_key"] = decrypt(saved.get("api_key_enc", ""))
        if not cfg["base_url"] or not cfg["model"]:
            error_box(self, "无法测试", "请先填写 API 地址与模型名称")
            return
        self.ai_test_btn.setEnabled(False)
        self.ai_test_label.setText("测试中…")
        self._ai_test_worker = _AIConnTestWorker(cfg)
        self._ai_test_worker.done.connect(self._on_ai_test_done)
        self._ai_test_worker.start()

    def _on_ai_test_done(self, ok, msg):
        self.ai_test_btn.setEnabled(True)
        self.ai_test_label.setText(msg)
        self.ai_test_label.setStyleSheet(
            f"color: {'#34C759' if ok else '#FA5151'}; font-size: 12px;")

    def _save_ai_config(self):
        idx = self.ai_provider_combo.currentIndex()
        pid = (self._ai_provider_keys[idx]
               if 0 <= idx < len(self._ai_provider_keys) else "custom")
        old = self.settings.get("ai", {}) or {}
        api_key = self.ai_key_edit.text().strip()
        enc = old.get("api_key_enc", "")
        if api_key:
            enc = encrypt(api_key)   # 空 = 保持原 Key
        self.settings.set("ai", {
            "provider": pid,
            "base_url": self.ai_base_edit.text().strip(),
            "model": self.ai_model_edit.text().strip(),
            "api_key_enc": enc,
        })

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
        # SNMP（community 不加密存本机 settings——它是共享读口令，非个人凭据）
        self.settings.set('snmp', {
            "community": self.snmp_community_edit.text().strip() or "public",
            "version": 2 if self.snmp_version_combo.currentIndex() == 0 else 1,
        })
        self._save_ai_config()

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