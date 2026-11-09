#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
高级配置标签页：数据驱动的模块化配置生成（对标 NetCMD 的 22 模块广度）
- 下拉选模块 → 动态生成参数表单（带默认示例值）→ 生成并加入
- 可叠加多个模块（堆叠 + 镜像 + 风暴控制…），get_config() 汇入全局「生成配置」
- 输出带中文注释走预览区；复制/下发永远纯命令
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QComboBox, QFormLayout, QGroupBox, QHBoxLayout,
                             QLabel, QLineEdit, QListWidget, QPushButton,
                             QScrollArea, QVBoxLayout, QWidget)

from gui.dialogs.base import info_box, warn_box
from gui.widget_utils import page_header
from modules.adv_modules import MODULES
from modules.nl_engine import VENDOR_CN


class AdvConfigTab(QWidget):
    """高级配置：模块下拉 + 动态表单 + 配置块清单"""

    def __init__(self):
        super().__init__()
        self._blocks = []   # [(模块名, [(cmd, note), ...])]
        self.initUI()

    # ---------------- UI ----------------
    def initUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addWidget(page_header(
            "高级配置", "模块化进阶功能按需叠加，生成后并入总配置"))

        # 模块选择卡
        pick_group = QGroupBox("选择高级模块")
        pick_lay = QVBoxLayout(pick_group)
        pick_lay.setContentsMargins(16, 24, 16, 14)
        pick_lay.setSpacing(10)

        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(QLabel("模块:"))
        self.module_combo = QComboBox()
        self.module_combo.addItems(list(MODULES.keys()))
        self.module_combo.currentIndexChanged.connect(self._build_form)
        row.addWidget(self.module_combo, 1)
        pick_lay.addLayout(row)

        self.desc_label = QLabel("")
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet("color: #7A8699; font-size: 12px;")
        pick_lay.addWidget(self.desc_label)
        layout.addWidget(pick_group)

        # 参数表单卡（滚动包裹，防字段多时溢出）
        form_group = QGroupBox("参数（已预填示例值，按现场改）")
        form_host = QWidget()
        self.form_lay = QFormLayout(form_host)
        self.form_lay.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.form_lay.setHorizontalSpacing(14)
        self.form_lay.setVerticalSpacing(13)
        form_scroll = QScrollArea()
        form_scroll.setWidgetResizable(True)
        form_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        form_scroll.setWidget(form_host)
        inner = QVBoxLayout(form_group)
        inner.setContentsMargins(16, 24, 16, 14)
        inner.addWidget(form_scroll)
        layout.addWidget(form_group, 3)

        # 操作按钮行
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        add_btn = QPushButton("➕ 生成并加入")
        add_btn.setObjectName("primaryButton")
        add_btn.setToolTip("按当前设备品牌生成该模块配置，并加入下方清单")
        add_btn.clicked.connect(self.add_block)
        del_btn = QPushButton("移除选中")
        del_btn.setObjectName("secondaryButton")
        del_btn.clicked.connect(self.remove_block)
        clear_btn = QPushButton("清空")
        clear_btn.setObjectName("dangerButton")
        clear_btn.clicked.connect(self.clear_config)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(del_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(clear_btn)
        layout.addLayout(btn_row)

        # 配置块清单
        list_group = QGroupBox("已加入的配置块（随「生成配置」一起输出）")
        list_lay = QVBoxLayout(list_group)
        list_lay.setContentsMargins(16, 24, 16, 14)
        self.blocks_list = QListWidget()
        self.blocks_list.setStyleSheet("QListWidget::item { padding: 8px 6px; }")
        self.blocks_list.setToolTip("双击可展开查看该块的命令；选中后点「移除选中」删除")
        self.blocks_list.itemDoubleClicked.connect(self._peek_block)
        list_lay.addWidget(self.blocks_list)
        layout.addWidget(list_group, 2)

        self._edits = {}
        self._build_form(0)

    # ---------------- 逻辑 ----------------
    def _build_form(self, _index=0):
        name = self.module_combo.currentText()
        mod = MODULES.get(name)
        # 清旧表单
        while self.form_lay.count():
            item = self.form_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._edits = {}
        if not mod:
            return
        self.desc_label.setText(f"{mod['desc']}")
        for key, label, default in mod["fields"]:
            edit = QLineEdit(default)
            edit.setMinimumWidth(320)
            self._edits[key] = edit
            lab = QLabel(label + ":")
            lab.setFixedWidth(150)
            self.form_lay.addRow(lab, edit)

    def _current_vendor(self):
        main = self.window()
        return getattr(main, "current_device_type", "huawei") or "huawei"

    def _params(self):
        return {k: e.text().strip() for k, e in self._edits.items()}

    def add_block(self):
        name = self.module_combo.currentText()
        mod = MODULES.get(name)
        if mod is None:
            return
        vendor = self._current_vendor()
        try:
            lines = mod["gen"](vendor, self._params())
        except Exception as e:
            warn_box(self, "生成失败", f"{type(e).__name__}: {e}")
            return
        if not lines:
            return
        self._blocks.append((name, (vendor, lines)))
        self._refresh_list()
        main = self.window()
        if hasattr(main, "statusBar"):
            main.statusBar().showMessage(
                f"已加入「{name}」配置块（{VENDOR_CN.get(vendor, vendor)}），点「生成配置」输出完整配置", 5000)

    def remove_block(self):
        row = self.blocks_list.currentRow()
        if 0 <= row < len(self._blocks):
            self._blocks.pop(row)
            self._refresh_list()

    def _refresh_list(self):
        self.blocks_list.clear()
        for i, (name, (vendor, lines)) in enumerate(self._blocks):
            self.blocks_list.addItem(
                f"{i + 1}. {name} · {VENDOR_CN.get(vendor, vendor)} · {len(lines)} 条命令")

    def _peek_block(self, item):
        i = self.blocks_list.row(item)
        if 0 <= i < len(self._blocks):
            name, (vendor, lines) = self._blocks[i]
            text = "\n".join(f"{c}    # {n}" for c, n in lines)
            info_box(self, f"配置块：{name}",
                     f"厂商：{VENDOR_CN.get(vendor, vendor)}\n\n{text}")

    # ---------------- 契约方法 ----------------
    def get_config(self):
        """汇入全局生成：所有已加入配置块的命令拼起来"""
        if not self._blocks:
            return ""
        chunks = []
        for name, (vendor, lines) in self._blocks:
            chunk = "\n".join(cmd for cmd, _note in lines)
            chunks.append(f"# ---- {name}（{VENDOR_CN.get(vendor, vendor)}）----\n{chunk}")
        return "\n\n".join(chunks)

    def get_config_data(self):
        return {"blocks": [{"name": n, "vendor": v, "lines": l} for n, (v, l) in self._blocks]}

    def clear_config(self):
        self._blocks = []
        self._refresh_list()
