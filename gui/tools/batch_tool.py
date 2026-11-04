#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""批量生成页（工具箱）：CSV 一次出几十条端口配置 / 多台设备开局配置"""

import html as _html
import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QComboBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel,
                             QMessageBox, QPushButton, QTextEdit, QVBoxLayout, QWidget)

from modules import batch_gen

DEMO_IFACE = """接口,模式,VLAN,描述
GE1/0/1,access,10,前台电脑
1/0/2,access,10,打印机
1/0/3,access,20,财务
GE1/0/24,trunk,,"上联核心"
"""
DEMO_DEVICE = """设备名,管理IP,掩码,网关,VLAN
Access-01F-03,10.10.3.2,255.255.255.0,10.10.3.1,30
Access-02F-03,10.10.3.3,255.255.255.0,10.10.3.1,30
Access-03F-03,10.10.3.4,255.255.255.0,10.10.3.1,30
"""


class BatchWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._lines = []      # [(cmd, note)]
        self._devices = []    # [{name, lines}]
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(12)

        bar = QHBoxLayout()
        bar.setSpacing(10)
        bar.addWidget(QLabel("批量类型:"))
        self.type_combo = QComboBox()
        self.type_combo.addItem("批量接口配置（一行一个端口）", "iface")
        self.type_combo.addItem("批量设备开局（一行一台设备）", "device")
        self.type_combo.currentIndexChanged.connect(lambda _: self._fill_demo())
        bar.addWidget(self.type_combo)

        bar.addWidget(QLabel("厂商:"))
        self.vendor_combo = QComboBox()
        self.vendor_combo.addItems(["华为 Huawei", "华三 H3C", "锐捷 Ruijie",
                                    "迈普 Maipu", "思科 Cisco"])
        bar.addWidget(self.vendor_combo)

        import_btn = QPushButton("导入 CSV")
        import_btn.setObjectName("ghostButton")
        import_btn.clicked.connect(self.import_csv)
        bar.addWidget(import_btn)

        demo_btn = QPushButton("填入示例")
        demo_btn.setObjectName("ghostButton")
        demo_btn.clicked.connect(self._fill_demo)
        bar.addWidget(demo_btn)

        gen_btn = QPushButton("⚡ 生成")
        gen_btn.setObjectName("primaryButton")
        gen_btn.clicked.connect(self.generate)
        bar.addWidget(gen_btn)

        copy_btn = QPushButton("复制纯命令")
        copy_btn.setObjectName("secondaryButton")
        copy_btn.clicked.connect(self.copy_plain)
        bar.addWidget(copy_btn)

        export_btn = QPushButton("导出文件")
        export_btn.setObjectName("secondaryButton")
        export_btn.clicked.connect(self.export)
        bar.addWidget(export_btn)
        bar.addStretch(1)
        layout.addLayout(bar)

        in_group = QGroupBox("CSV 数据（首行表头，可直接从 Excel 复制粘贴）")
        in_lay = QVBoxLayout(in_group)
        in_lay.setContentsMargins(14, 24, 14, 12)
        self.input_view = QTextEdit()
        self.input_view.setMinimumHeight(140)
        in_lay.addWidget(self.input_view)
        self.hint_label = QLabel("")
        self.hint_label.setStyleSheet("color: #7A8699; font-size: 12px;")
        in_lay.addWidget(self.hint_label)
        layout.addWidget(in_group, 2)

        self.stat_label = QLabel("生成结果会显示在这里")
        self.stat_label.setStyleSheet("color: #7A8699; font-size: 13px; font-weight: bold;")
        layout.addWidget(self.stat_label)

        out_group = QGroupBox("生成的命令（# 为中文释义，仅阅读用）")
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

        self.type_combo.setCurrentIndex(0)
        self._fill_demo()

    # ---------------- 逻辑 ----------------
    def _mode(self):
        return self.type_combo.currentData()

    def _vendor(self):
        return ("huawei", "h3c", "ruijie", "maipu", "cisco")[self.vendor_combo.currentIndex()]

    def _fill_demo(self):
        if self._mode() == "iface":
            self.input_view.setPlainText(DEMO_IFACE)
            self.hint_label.setText("表头：接口, 模式(access/trunk), VLAN, 描述 ｜ 端口写法：GE1/0/1 或 1/0/1")
        else:
            self.input_view.setPlainText(DEMO_DEVICE)
            self.hint_label.setText("表头：设备名, 管理IP, 掩码, 网关, VLAN ｜ 每台设备输出独立一份开局配置")

    def import_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入 CSV", "", "表格文件 (*.csv *.txt *.tsv);;所有文件 (*)")
        if not path:
            return
        try:
            for enc in ("utf-8-sig", "gbk", "utf-16"):
                try:
                    with open(path, "r", encoding=enc) as f:
                        self.input_view.setPlainText(f.read())
                    break
                except UnicodeDecodeError:
                    continue
            self.stat_label.setText(f"已导入：{os.path.basename(path)}")
        except Exception as e:
            QMessageBox.critical(self, "导入失败", f"{type(e).__name__}: {e}")

    def generate(self):
        text = self.input_view.toPlainText().strip()
        if not text:
            self.stat_label.setText("请先填入或导入 CSV 数据")
            return
        header, rows = batch_gen.parse_table(text)
        if not rows:
            self.stat_label.setText("没有解析到数据行（首行需要表头）")
            return

        if self._mode() == "iface":
            r = batch_gen.gen_interface_batch(self._vendor(), rows)
            self._lines = r["lines"]
            self._devices = []
            self.stat_label.setText(f"✔ 已生成 {r['count']} 个端口配置，共 {len(self._lines)} 行命令")
            self.stat_label.setStyleSheet("color: #34C759; font-size: 13px; font-weight: bold;")
            self._render(self._lines, None)
        else:
            devs = batch_gen.gen_device_batch(self._vendor(), rows)
            self._devices = devs
            self._lines = []
            total = sum(len(d["lines"]) for d in devs)
            self.stat_label.setText(f"✔ 已生成 {len(devs)} 台设备的开局配置，共 {total} 行命令"
                                    + ("" if devs else "（检查设备名列是否为空）"))
            self.stat_label.setStyleSheet("color: #34C759; font-size: 13px; font-weight: bold;")
            self._render(None, devs)

    def _render(self, lines, devices):
        html_lines = []
        if lines:
            for cmd, note in lines:
                span = f'<span style="color:#7C93B8">  # {_html.escape(note)}</span>' if note else ""
                html_lines.append(f'<div style="color:#C8D3E8">{_html.escape(cmd)}{span}</div>')
        elif devices:
            for d in devices:
                html_lines.append(f'<div style="color:#7EE0A3"># ======== {_html.escape(d["name"])} ========</div>')
                for cmd, note in d["lines"]:
                    span = f'<span style="color:#7C93B8">  # {_html.escape(note)}</span>' if note else ""
                    html_lines.append(f'<div style="color:#C8D3E8">{_html.escape(cmd)}{span}</div>')
                html_lines.append('<div>&nbsp;</div>')
        self.output_view.setHtml("".join(html_lines) or "<div>（无输出）</div>")

    def _plain_text(self):
        if self._lines:
            return batch_gen.to_plain(self._lines)
        if self._devices:
            parts = []
            for d in self._devices:
                parts.append(f"# ======== {d['name']} ========\n" + batch_gen.to_plain(d["lines"]))
            return "\n\n".join(parts)
        return ""

    def copy_plain(self):
        text = self._plain_text()
        if not text:
            return
        from PyQt5.QtWidgets import QApplication
        QApplication.clipboard().setText(text)
        self.stat_label.setText("已复制纯命令（注释不包含）")

    def export(self):
        text = self._plain_text()
        if not text:
            QMessageBox.information(self, "导出", "请先生成配置")
            return
        if self._devices:
            # 批量设备：每台一个 .cfg 文件
            folder = QFileDialog.getExistingDirectory(self, "选择导出目录（每台设备一个 .cfg）")
            if not folder:
                return
            try:
                for d in self._devices:
                    safe = "".join(ch for ch in d["name"] if ch not in r'\/:*?"<>|')
                    with open(os.path.join(folder, f"{safe}.cfg"), "w", encoding="utf-8") as f:
                        f.write(batch_gen.to_plain(d["lines"]))
                QMessageBox.information(self, "导出完成", f"已导出 {len(self._devices)} 个文件到：\n{folder}")
            except Exception as e:
                QMessageBox.critical(self, "导出失败", f"{type(e).__name__}: {e}")
        else:
            path, _ = QFileDialog.getSaveFileName(self, "导出配置", "batch_config.cfg",
                                                  "配置文件 (*.cfg);;文本 (*.txt)")
            if not path:
                return
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
                QMessageBox.information(self, "导出完成", f"已保存到：\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "导出失败", f"{type(e).__name__}: {e}")