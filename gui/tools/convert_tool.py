#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""跨厂商配置转换页（工具箱）：贴源厂商配置 → 选目标厂商 → 出对应语法初稿"""

from PyQt5.QtWidgets import (QComboBox, QGroupBox, QHBoxLayout, QLabel,
                             QPushButton, QTextEdit, QVBoxLayout, QWidget)
from PyQt5.QtCore import Qt

from modules import config_converter as cc
from modules.nl_engine import VENDOR_CN
import html as _html

SRC_VENDORS = ["auto", "huawei", "h3c", "ruijie", "maipu", "cisco"]

DEMO = """
 sysname Core-SW-01
#
vlan batch 10 20
#
telnet server enable
#
local-user admin
#
interface GigabitEthernet1/0/1
 port link-type access
 port access vlan 10
#
interface GigabitEthernet1/0/24
 port link-type trunk
 port trunk permit vlan 10 20
#
interface Vlan-interface10
 ip address 192.168.10.1 255.255.255.0
#
 ip route-static 0.0.0.0 0.0.0.0 192.168.10.254
""".strip()


class ConvertWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._plain = ""
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(12)

        bar = QHBoxLayout()
        bar.setSpacing(10)
        bar.addWidget(QLabel("源厂商:"))
        self.src_combo = QComboBox()
        self.src_combo.addItem("自动检测", "auto")
        for v in SRC_VENDORS[1:]:
            self.src_combo.addItem(f"{VENDOR_CN[v]} {v.capitalize()}", v)
        bar.addWidget(self.src_combo)

        bar.addWidget(QLabel("目标厂商:"))
        self.dst_combo = QComboBox()
        for v in ("huawei", "h3c", "ruijie", "maipu", "cisco"):
            self.dst_combo.addItem(f"{VENDOR_CN[v]} {v.capitalize()}", v)
        self.dst_combo.setCurrentIndex(1)   # 默认 H3C → 常见迁移方向
        bar.addWidget(self.dst_combo)

        demo_btn = QPushButton("载入 H3C 示例")
        demo_btn.setObjectName("ghostButton")
        demo_btn.clicked.connect(lambda: self.input_view.setPlainText(DEMO))
        bar.addWidget(demo_btn)

        conv_btn = QPushButton("⇄ 转换")
        conv_btn.setObjectName("primaryButton")
        conv_btn.clicked.connect(self.do_convert)
        copy_btn = QPushButton("复制纯命令")
        copy_btn.setObjectName("secondaryButton")
        copy_btn.clicked.connect(self.copy_plain)
        bar.addWidget(conv_btn)
        bar.addWidget(copy_btn)
        bar.addStretch(1)
        layout.addLayout(bar)

        in_group = QGroupBox("源配置（粘贴 running-config）")
        in_lay = QVBoxLayout(in_group)
        in_lay.setContentsMargins(14, 24, 14, 12)
        self.input_view = QTextEdit()
        self.input_view.setMinimumHeight(180)
        self.input_view.setPlaceholderText("贴入源厂商的配置……支持华为/H3C（缩进式）与锐捷/迈普/思科（块式）两种风格")
        in_lay.addWidget(self.input_view)
        self.detect_label = QLabel("")
        self.detect_label.setStyleSheet("color: #7A8699; font-size: 12px;")
        in_lay.addWidget(self.detect_label)
        layout.addWidget(in_group, 2)

        self.report_label = QLabel("转换结果说明显示在这里")
        self.report_label.setWordWrap(True)
        self.report_label.setStyleSheet("color: #34C759; font-size: 12px;")
        layout.addWidget(self.report_label)

        out_group = QGroupBox("目标厂商配置（# 为中文释义，仅阅读用）")
        out_lay = QVBoxLayout(out_group)
        out_lay.setContentsMargins(14, 24, 14, 12)
        self.output_view = QTextEdit()
        self.output_view.setReadOnly(True)
        self.output_view.setMinimumHeight(220)
        self.output_view.setStyleSheet("""
            font-family: 'JetBrains Mono', 'Consolas', monospace;
            font-size: 13px; line-height: 1.6;
            background: #1E2430; border: 1px solid #2C3444; border-radius: 12px;
            padding: 12px; color: #C8D3E8;
        """)
        out_lay.addWidget(self.output_view)
        layout.addWidget(out_group, 3)

        tip = QLabel("💡 覆盖：主机名 / VLAN / Access口 / Trunk口 / SVI IP / 静态路由 / SSH 登录。"
                     "堆叠、ACL 细则、NAT 等复杂特性不自动转换，输出为初稿，务必人工复核后上设备。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #9AA7B8; font-size: 12px;")
        layout.addWidget(tip)

    def do_convert(self):
        text = self.input_view.toPlainText().strip()
        if not text:
            self.report_label.setText("请先粘贴源配置")
            return
        src = self.src_combo.currentData()
        dst = self.dst_combo.currentData()
        r = cc.convert(text, src, dst)
        self.detect_label.setText(
            f"源厂商识别：{VENDOR_CN.get(r['src_detected'], r['src_detected'])}"
            + ("" if src != "auto" else "（自动检测，可手动纠正）"))
        self._plain = "\n".join(cmd for cmd, _ in r["lines"])
        self.report_label.setText("✔ 已转换：" + " ｜ ".join(r["report"]) if r["report"]
                                  else "（源配置里没有可转换的内容）")
        html_lines = []
        for cmd, note in r["lines"]:
            span = f'<span style="color:#7C93B8">  # {_html.escape(note)}</span>' if note else ""
            html_lines.append(f'<div style="color:#C8D3E8">{_html.escape(cmd)}{span}</div>')
        self.output_view.setHtml("".join(html_lines) or "<div>（无输出）</div>")

    def copy_plain(self):
        if not self._plain:
            return
        from PyQt5.QtWidgets import QApplication
        QApplication.clipboard().setText(self._plain)
        self.report_label.setText("已复制纯命令（注释不包含，可粘贴设备）")
