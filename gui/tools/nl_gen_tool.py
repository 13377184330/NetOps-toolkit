#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
自然语言生成配置页（工具箱）
大白话描述需求 → 五厂商配置命令（离线规则引擎，借鉴 NetCMD 的交互模式自行实现）
- 屏幕显示带中文释义；复制永远给纯命令（注释不进设备）
"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (QComboBox, QGroupBox, QHBoxLayout, QLabel,
                              QPushButton, QTextEdit, QVBoxLayout, QWidget)

from modules import nl_engine
from modules.cmd_notes import annotate_config, strip_notes

EXAMPLES = [
    ("示例 1：开局三件套",
     "设备命名为 Access-01，创建vlan10 20，"
     "把gi1/0/1设为access口划入vlan10，开启ssh，账号admin密码Admin@123，保存配置"),
    ("示例 2：上联与网关",
     "GE1/0/24做trunk放行vlan 10 20，vlanif10配ip 192.168.10.1/24，"
     "默认路由指向192.168.10.254"),
    ("示例 3：安全加固",
     "gi1/0/1开启端口安全最多2个mac，禁止192.168.20.0 255.255.255.0访问，"
     "时间同步10.1.1.1，日志发送到10.1.1.2"),
]


class NLGenWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._plain = ""
        self._lines = []
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(12)

        # 操作行
        bar = QHBoxLayout()
        bar.setSpacing(10)
        bar.addWidget(QLabel("目标厂商:"))
        self.vendor_combo = QComboBox()
        self.vendor_combo.addItems(["华为 Huawei", "华三 H3C", "锐捷 Ruijie",
                                    "迈普 Maipu", "思科 Cisco"])
        bar.addWidget(self.vendor_combo)

        self.example_combo = QComboBox()
        self.example_combo.addItem("填入示例…", "")
        for name, text in EXAMPLES:
            self.example_combo.addItem(name, text)
        self.example_combo.currentIndexChanged.connect(self._fill_example)
        bar.addWidget(self.example_combo, 1)

        gen_btn = QPushButton("⚡ 生成配置")
        gen_btn.setObjectName("primaryButton")
        gen_btn.clicked.connect(self.generate)

        copy_btn = QPushButton("复制纯命令")
        copy_btn.setObjectName("secondaryButton")
        copy_btn.clicked.connect(self.copy_plain)

        copy_anno_btn = QPushButton("复制(带注释)")
        copy_anno_btn.setObjectName("ghostButton")
        copy_anno_btn.setToolTip("命令 + # 中文说明（供变更单/文档引用，注释不进设备）")
        copy_anno_btn.clicked.connect(self.copy_annotated)

        clear_btn = QPushButton("清空")
        clear_btn.setObjectName("dangerButton")
        clear_btn.clicked.connect(self.clear_all)

        for w in (gen_btn, copy_btn, copy_anno_btn, clear_btn):
            bar.addWidget(w)
        layout.addLayout(bar)

        # 输入区
        in_group = QGroupBox("用大白话描述你的需求（多个需求用逗号/换行分开）")
        in_lay = QVBoxLayout(in_group)
        in_lay.setContentsMargins(14, 24, 14, 12)
        self.input_view = QTextEdit()
        self.input_view.setMinimumHeight(110)
        self.input_view.setPlaceholderText(
            "例如：创建vlan10 20，把gi1/0/1设为access口划入vlan10，GE1/0/24做trunk放行vlan 10 20，"
            "开启ssh，账号admin密码Admin@123，保存配置")
        in_lay.addWidget(self.input_view)
        layout.addWidget(in_group)

        # 意图提示行
        self.intent_label = QLabel("识别到的需求会显示在这里")
        self.intent_label.setWordWrap(True)
        self.intent_label.setStyleSheet("color: #7A8699; font-size: 12px;")
        layout.addWidget(self.intent_label)

        # 输出区
        out_group = QGroupBox("生成的配置命令（# 后为中文释义，仅阅读用）")
        out_lay = QVBoxLayout(out_group)
        out_lay.setContentsMargins(14, 24, 14, 12)
        self.output_view = QTextEdit()
        self.output_view.setReadOnly(True)
        self.output_view.setMinimumHeight(260)
        self.output_view.setStyleSheet("""
            font-family: 'JetBrains Mono', 'Consolas', monospace;
            font-size: 13px; line-height: 1.6;
            background: #1E2430; border: 1px solid #2C3444; border-radius: 12px;
            padding: 12px; color: #C8D3E8;
        """)
        out_lay.addWidget(self.output_view)
        layout.addWidget(out_group, 1)

        tip = QLabel("💡 完全离线、规则解析。识别不了的说法请按「厂商黑话」写：vlan/接口名/掩码/下一跳。"
                     "生成后建议先在 Console 可视化页连真机核验再下发。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #9AA7B8; font-size: 12px;")
        layout.addWidget(tip)

    # ---------------- 逻辑 ----------------
    def _vendor(self):
        return ("huawei", "h3c", "ruijie", "maipu", "cisco")[self.vendor_combo.currentIndex()]

    def _fill_example(self, index):
        text = self.example_combo.itemData(index)
        if text:
            self.input_view.setPlainText(text)
        self.example_combo.setCurrentIndex(0)

    def generate(self):
        text = self.input_view.toPlainText().strip()
        if not text:
            self.intent_label.setText("请先在上方输入需求")
            return
        result = nl_engine.parse(text, self._vendor())
        self._lines = result["lines"]
        self._plain = nl_engine.to_plain(self._lines)

        # 意图提示
        parts = []
        if result["intents"]:
            parts.append("✔ " + " ｜ ".join(result["intents"]))
        if result["unknown"]:
            parts.append("⚠ 没看懂：" + "、".join(f"「{u}」" for u in result["unknown"]))
        self.intent_label.setText(parts[0] if parts else "未识别到任何需求")
        if result["unknown"]:
            self.intent_label.setStyleSheet("color: #FA9D3B; font-size: 12px;")
        else:
            self.intent_label.setStyleSheet("color: #34C759; font-size: 12px;")

        if self._plain:
            # 屏幕上带注释展示；行级注释优先用引擎给出的（含参数语义）
            html_lines = []
            from modules.cmd_notes import note_of, is_view_line, _COMMENT_LINE_RE
            import html as _h
            for cmd, note in result["lines"]:
                color = "#7EE0A3" if is_view_line(cmd) else "#C8D3E8"
                span = f'<span style="color:#7C93B8">  # {_h.escape(note)}</span>' if note else ""
                html_lines.append(f'<div style="color:{color}">{_h.escape(cmd)}{span}</div>')
            self.output_view.setHtml("".join(html_lines))
        else:
            self.output_view.setPlainText("（没有生成任何命令）")
            self._plain = ""

    def copy_plain(self):
        if not self._plain:
            return
        from PyQt5.QtWidgets import QApplication
        QApplication.clipboard().setText(self._plain)
        self.intent_label.setText("已复制纯命令到剪贴板（注释不包含，可直接粘贴设备）")

    def copy_annotated(self):
        if not self._plain:
            return
        from PyQt5.QtWidgets import QApplication
        text = "\n".join(f"{cmd}  # {note}" for cmd, note in self._lines)
        QApplication.clipboard().setText(text)
        self.intent_label.setText("已复制带注释版本（文档/变更单用，粘贴设备前请去掉注释）")

    def clear_all(self):
        self.input_view.clear()
        self.output_view.clear()
        self._plain = ""
        self._lines = []
        self.intent_label.setText("识别到的需求会显示在这里")
        self.intent_label.setStyleSheet("color: #7A8699; font-size: 12px;")
