#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""配置语法纠错页（工具箱）：粘贴配置 → 按厂商语法与基线体检"""

from PyQt5.QtGui import QBrush, QColor
from PyQt5.QtWidgets import (QAbstractItemView, QComboBox, QGroupBox, QHBoxLayout,
                              QHeaderView, QLabel, QPushButton, QTableWidget,
                              QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget)

from modules.config_lint import LEVEL_COLOR, lint, lint_score

DEMO = """
 sysname Access-01
#
vlan batch 10
#
telnet server enable
#
interface GigabitEthernet1/0/1
 port link-type access
 port access vlan 20
#
interface GigabitEthernet1/0/2
 port link-type trunk
#
interface Vlan-interface10
 ip address 192.168.10.1 255.255.255.1
#
user-interface vty 0 4
"""


class LintWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(12)

        bar = QHBoxLayout()
        bar.setSpacing(10)
        bar.addWidget(QLabel("配置厂商:"))
        self.vendor_combo = QComboBox()
        self.vendor_combo.addItems(["华为 Huawei", "华三 H3C", "锐捷 Ruijie",
                                    "迈普 Maipu", "思科 Cisco"])
        bar.addWidget(self.vendor_combo)

        demo_btn = QPushButton("载入示例（含错误）")
        demo_btn.setObjectName("ghostButton")
        demo_btn.clicked.connect(lambda: self.input_view.setPlainText(DEMO.strip()))
        bar.addWidget(demo_btn)

        check_btn = QPushButton("🔍 开始检查")
        check_btn.setObjectName("primaryButton")
        check_btn.clicked.connect(self.check)
        bar.addWidget(check_btn)
        bar.addStretch(1)
        layout.addLayout(bar)

        in_group = QGroupBox("粘贴配置（running-config / 生成结果均可）")
        in_lay = QVBoxLayout(in_group)
        in_lay.setContentsMargins(14, 24, 14, 12)
        self.input_view = QTextEdit()
        self.input_view.setMinimumHeight(160)
        self.input_view.setPlaceholderText("把要体检的配置粘进来……支持任何来源：手写的、工具生成的、设备上抄下来的")
        in_lay.addWidget(self.input_view)
        layout.addWidget(in_group, 2)

        self.summary_label = QLabel("检查结果会显示在这里")
        self.summary_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #7A8699;")
        layout.addWidget(self.summary_label)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["行号", "等级", "问题", "修复建议"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        layout.addWidget(self.table, 3)

        tip = QLabel("💡 严重=功能失效/登录不上；警告=安全隐患或大概率配错；提示=基线规范建议。纯规则检查，不上传配置。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #9AA7B8; font-size: 12px;")
        layout.addWidget(tip)

    def check(self):
        text = self.input_view.toPlainText().strip()
        if not text:
            self.summary_label.setText("请先粘贴配置")
            return
        vendor = ("huawei", "h3c", "ruijie", "maipu", "cisco")[self.vendor_combo.currentIndex()]
        r = lint(text, vendor)
        st = r["stats"]
        if not r["items"]:
            self.summary_label.setText("✔ 未发现问题，配置很规范")
            self.summary_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #34C759;")
        else:
            self.summary_label.setText(
                f"体检 {lint_score(st)} ｜ 严重 {st['严重']} · 警告 {st['警告']} · 提示 {st['提示']}")
            color = "#FA5151" if st["严重"] else ("#FA9D3B" if st["警告"] else "#0089FF")
            self.summary_label.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {color};")

        self.table.setRowCount(0)
        for it in r["items"]:
            row = self.table.rowCount()
            self.table.insertRow(row)
            no = QTableWidgetItem(str(it["line_no"]) if it["line_no"] else "全局")
            issue = QTableWidgetItem(it["issue"])
            no.setForeground(QBrush(QColor(LEVEL_COLOR.get(it["level"], "#7A8699"))))
            self.table.setItem(row, 0, no)
            self.table.setItem(row, 1, QTableWidgetItem(it["level"]))
            self.table.setItem(row, 2, issue)
            self.table.setItem(row, 3, QTableWidgetItem(it["advice"]))
            self.table.item(row, 1).setForeground(QBrush(QColor(LEVEL_COLOR.get(it["level"], "#7A8699"))))
