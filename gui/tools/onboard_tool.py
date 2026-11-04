#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""一键标准化开局页（工具箱）：填几个值 → 出全套上线配置（命名/管理/登录/时间/日志/生成树/保存）"""

import html as _html

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QComboBox, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                             QMessageBox, QPushButton, QTextEdit, QVBoxLayout, QWidget)

from modules import onboard


class OnboardWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._lines = []
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(12)

        bar = QHBoxLayout()
        bar.setSpacing(10)
        bar.addWidget(QLabel("厂商:"))
        self.vendor_combo = QComboBox()
        self.vendor_combo.addItems(["华为 Huawei", "华三 H3C", "锐捷 Ruijie",
                                    "迈普 Maipu", "思科 Cisco"])
        bar.addWidget(self.vendor_combo)

        gen_btn = QPushButton("🚀 一键开局")
        gen_btn.setObjectName("primaryButton")
        gen_btn.clicked.connect(self.generate)
        bar.addWidget(gen_btn)

        copy_btn = QPushButton("复制纯命令")
        copy_btn.setObjectName("secondaryButton")
        copy_btn.clicked.connect(self.copy_plain)
        bar.addWidget(copy_btn)

        export_btn = QPushButton("导出 .cfg")
        export_btn.setObjectName("secondaryButton")
        export_btn.clicked.connect(self.export)
        bar.addWidget(export_btn)
        bar.addStretch(1)
        layout.addLayout(bar)

        form_group = QGroupBox("开局参数（已预填示例，按现场改）")
        form_lay = QVBoxLayout(form_group)
        form_lay.setContentsMargins(16, 24, 16, 14)
        grid = QHBoxLayout()
        grid.setSpacing(16)
        left = QVBoxLayout()
        left.setSpacing(10)
        right = QVBoxLayout()
        right.setSpacing(10)
        self._edits = {}
        for i, (key, label, default) in enumerate(onboard.FIELDS):
            row = QHBoxLayout()
            lab = QLabel(label + ":")
            lab.setFixedWidth(130)
            edit = QLineEdit(default)
            edit.setMinimumWidth(220)
            row.addWidget(lab)
            row.addWidget(edit, 1)
            self._edits[key] = edit
            (left if i % 2 == 0 else right).addLayout(row)
        grid.addLayout(left, 1)
        grid.addLayout(right, 1)
        form_lay.addLayout(grid)
        layout.addWidget(form_group)

        self.stat_label = QLabel("开局配置生成后会显示在下方")
        self.stat_label.setStyleSheet("color: #7A8699; font-size: 13px; font-weight: bold;")
        layout.addWidget(self.stat_label)

        out_group = QGroupBox("开局配置（# 为中文释义，仅阅读用）")
        out_lay = QVBoxLayout(out_group)
        out_lay.setContentsMargins(14, 24, 14, 12)
        self.output_view = QTextEdit()
        self.output_view.setReadOnly(True)
        self.output_view.setMinimumHeight(240)
        self.output_view.setStyleSheet("""
            font-family: 'JetBrains Mono', 'Consolas', monospace;
            font-size: 13px; line-height: 1.6;
            background: #1E2430; border: 1px solid #2C3444; border-radius: 12px;
            padding: 12px; color: #C8D3E8;
        """)
        out_lay.addWidget(self.output_view)
        layout.addWidget(out_group, 1)

        tip = QLabel("💡 顺序：命名 → 管理 VLAN/SVI → 默认路由 → SSH 账号 → NTP → 日志 → MSTP 加固 → 保存。"
                     "生成的密码是示例值，上设备前务必改掉。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #9AA7B8; font-size: 12px;")
        layout.addWidget(tip)

        self.generate()

    def _vendor(self):
        return ("huawei", "h3c", "ruijie", "maipu", "cisco")[self.vendor_combo.currentIndex()]

    def generate(self):
        params = {k: e.text() for k, e in self._edits.items()}
        self._lines = onboard.build(self._vendor(), params)
        self.stat_label.setText(f"✔ 已生成 {len(self._lines)} 行开局配置（{self.vendor_combo.currentText()}）")
        self.stat_label.setStyleSheet("color: #34C759; font-size: 13px; font-weight: bold;")
        html_lines = []
        for cmd, note in self._lines:
            span = f'<span style="color:#7C93B8">  # {_html.escape(note)}</span>' if note else ""
            color = "#7EE0A3" if cmd.strip() in ("system-view", "configure terminal") else "#C8D3E8"
            html_lines.append(f'<div style="color:{color}">{_html.escape(cmd)}{span}</div>')
        self.output_view.setHtml("".join(html_lines) or "<div>（无输出）</div>")

    def copy_plain(self):
        if not self._lines:
            return
        from PyQt5.QtWidgets import QApplication
        QApplication.clipboard().setText("\n".join(c for c, _ in self._lines))
        self.stat_label.setText("已复制纯命令（注释不包含，可直接粘贴设备）")

    def export(self):
        if not self._lines:
            QMessageBox.information(self, "导出", "请先生成配置")
            return
        from PyQt5.QtWidgets import QFileDialog
        safe = "".join(ch for ch in (self._edits["name"].text() or "switch")
                       if ch not in r'\/:*?"<>|') or "switch"
        path, _ = QFileDialog.getSaveFileName(self, "导出开局配置", f"{safe}.cfg",
                                              "配置文件 (*.cfg);;文本 (*.txt)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(c for c, _ in self._lines))
            QMessageBox.information(self, "导出完成", f"已保存到：\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"{type(e).__name__}: {e}")