#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
模板管理对话框（统一无边框子窗口骨架）

v2（真机截图反馈）：此前仍是系统原生蓝标题栏 + 自绘蓝色大标题 + 一排
原生灰白按钮，与主窗口/设置页的「红点标题栏 + 圆角卡片 + 四档语义按钮」
完全脱节。本次迁移到 BaseDialog 统一骨架：
- 去掉原生标题栏与冗余的「📚 模板管理器」大字标题（标题栏已承担）
- 顶部过滤行与主内容进 content_layout；全局动作按钮进 BaseDialog 统一
  按钮行（导入/导出/复制 = secondary，使用模板 = primary，关闭 = ghost）
- 列表侧的 新建/删除 属于「列表语境动作」，留在列表下方，用 make_button
  四档语义（新建 secondary、删除 dangerGhost）
- 内部控件名/文本保持兼容：template_list / name_input / "使用模板" / "保存"…
  （全量测试 A7-A10、C8 依赖）
"""

from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QLabel,
                              QPushButton, QListWidget, QListWidgetItem,
                              QTextEdit, QLineEdit, QComboBox, QTabWidget,
                              QWidget, QFileDialog, QInputDialog, QSplitter,
                              QSizePolicy)
from PyQt5.QtCore import Qt, pyqtSignal

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from gui.dialogs.base import (BaseDialog, make_button, info_box, warn_box,
                              question_box)
from utils.template_manager import TemplateManager, Template


class TemplateManagerDialog(BaseDialog):
    """模板管理对话框（统一无边框子窗口骨架）"""

    template_selected = pyqtSignal(dict)

    def __init__(self, parent=None, device_type: str = "huawei"):
        self.device_type = device_type
        self.template_manager = TemplateManager()
        self.current_template = None
        super().__init__("模板管理器", "", parent, min_width=900, min_height=600)
        self.initUI()
        self.load_templates()

    def initUI(self):
        layout = self.content_layout()
        layout.setSpacing(14)

        # ---------- 过滤行 ----------
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(10)

        filter_layout.addWidget(QLabel("设备类型:"))
        self.device_combo = QComboBox()
        # 全量测试修复：过滤器补齐五厂商（原来只有 全部/华为/H3C，
        # 锐捷/迈普/思科菜单入口打开的是未过滤的全部列表，选首项会套错厂商模板）
        self._vendor_cn = {"huawei": "华为", "h3c": "H3C", "ruijie": "锐捷",
                           "maipu": "迈普", "cisco": "思科"}
        self._cn_list = ["全部"] + list(self._vendor_cn.values())
        self.device_combo.addItems(self._cn_list)
        self.device_combo.setCurrentIndex(
            self._cn_list.index(self._vendor_cn.get(self.device_type, "全部")))
        self.device_combo.setMinimumHeight(40)
        self.device_combo.setMinimumWidth(130)
        self.device_combo.currentIndexChanged.connect(self.on_device_filter_changed)
        filter_layout.addWidget(self.device_combo)

        filter_layout.addSpacing(6)
        filter_layout.addWidget(QLabel("搜索:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入关键词搜索模板...")
        self.search_input.setMinimumHeight(40)
        self.search_input.textChanged.connect(self.on_search_changed)
        filter_layout.addWidget(self.search_input, 1)

        layout.addLayout(filter_layout)

        # ---------- 左：列表 / 右：详情+编辑 ----------
        splitter = QSplitter(Qt.Horizontal)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)
        left_widget.setMinimumWidth(240)

        list_header = QLabel("模板列表")
        list_header.setStyleSheet("font-weight: bold;")
        left_layout.addWidget(list_header)

        self.template_list = QListWidget()
        self.template_list.setAlternatingRowColors(True)
        self.template_list.currentItemChanged.connect(self.on_template_selected)
        self.template_list.itemDoubleClicked.connect(self.on_template_double_clicked)
        left_layout.addWidget(self.template_list, 1)

        list_btn_layout = QHBoxLayout()
        list_btn_layout.setSpacing(8)
        self.new_btn = make_button("新建", "secondary")
        self.new_btn.clicked.connect(self.create_template)
        list_btn_layout.addWidget(self.new_btn)

        self.delete_btn = make_button("删除", "dangerGhost")
        self.delete_btn.clicked.connect(self.delete_template)
        self.delete_btn.setEnabled(False)
        list_btn_layout.addWidget(self.delete_btn)
        list_btn_layout.addStretch()

        left_layout.addLayout(list_btn_layout)
        splitter.addWidget(left_widget)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        tabs = QTabWidget()

        # ---- 详情页 ----
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setSpacing(10)

        form_layout = QHBoxLayout()
        form_layout.setSpacing(10)
        form_layout.addWidget(QLabel("名称:"))
        self.name_input = QLineEdit()
        self.name_input.setReadOnly(True)
        self.name_input.setMinimumHeight(40)
        form_layout.addWidget(self.name_input, 1)

        form_layout.addSpacing(6)
        form_layout.addWidget(QLabel("设备:"))
        self.device_label = QLabel()
        self.device_label.setStyleSheet("color: #0089FF; font-weight: bold;")
        form_layout.addWidget(self.device_label)
        info_layout.addLayout(form_layout)

        info_layout.addWidget(QLabel("描述:"))
        self.desc_input = QTextEdit()
        self.desc_input.setReadOnly(True)
        self.desc_input.setMaximumHeight(80)
        info_layout.addWidget(self.desc_input)

        info_layout.addWidget(QLabel("标签:"))
        self.tags_label = QLabel()
        self.tags_label.setStyleSheet("color: #5F6B7A;")
        info_layout.addWidget(self.tags_label)

        info_layout.addWidget(QLabel("配置预览:"))
        self.config_preview = QTextEdit()
        self.config_preview.setReadOnly(True)
        self.config_preview.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 11px;")
        info_layout.addWidget(self.config_preview, 1)

        meta_layout = QHBoxLayout()
        self.author_label = QLabel()
        self.author_label.setStyleSheet("color: #8A95A6;")
        meta_layout.addWidget(self.author_label)
        meta_layout.addStretch()
        self.time_label = QLabel()
        self.time_label.setStyleSheet("color: #8A95A6;")
        meta_layout.addWidget(self.time_label)
        info_layout.addLayout(meta_layout)

        tabs.addTab(info_widget, "详情")

        # ---- 编辑页 ----
        edit_widget = QWidget()
        edit_layout = QVBoxLayout(edit_widget)
        edit_layout.setSpacing(10)

        edit_form = QHBoxLayout()
        edit_form.setSpacing(10)
        edit_form.addWidget(QLabel("名称:"))
        self.edit_name = QLineEdit()
        self.edit_name.setMinimumHeight(40)
        edit_form.addWidget(self.edit_name, 1)
        edit_layout.addLayout(edit_form)

        edit_layout.addWidget(QLabel("描述:"))
        self.edit_desc = QTextEdit()
        self.edit_desc.setMaximumHeight(80)
        edit_layout.addWidget(self.edit_desc)

        edit_layout.addWidget(QLabel("作者:"))
        self.edit_author = QLineEdit()
        self.edit_author.setMinimumHeight(40)
        edit_layout.addWidget(self.edit_author)

        edit_layout.addWidget(QLabel("标签 (逗号分隔):"))
        self.edit_tags = QLineEdit()
        self.edit_tags.setMinimumHeight(40)
        edit_layout.addWidget(self.edit_tags)

        edit_layout.addWidget(QLabel("配置 (JSON):"))
        self.edit_config = QTextEdit()
        self.edit_config.setStyleSheet("font-family: Consolas, monospace;")
        edit_layout.addWidget(self.edit_config, 1)

        edit_btn_layout = QHBoxLayout()
        edit_btn_layout.setSpacing(8)
        self.save_edit_btn = make_button("保存", "primary")
        self.save_edit_btn.clicked.connect(self.save_edited_template)
        edit_btn_layout.addWidget(self.save_edit_btn)

        self.cancel_edit_btn = make_button("取消", "ghost")
        self.cancel_edit_btn.clicked.connect(self.cancel_edit)
        edit_btn_layout.addWidget(self.cancel_edit_btn)
        edit_btn_layout.addStretch()
        edit_layout.addLayout(edit_btn_layout)

        tabs.addTab(edit_widget, "编辑")

        right_layout.addWidget(tabs)

        splitter.addWidget(right_widget)
        splitter.setSizes([280, 620])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter, 1)

        # ---------- 全局动作按钮（BaseDialog 统一行） ----------
        self.import_btn = self.add_button("导入", "secondary", self.import_template)
        self.export_btn = self.add_button("导出", "secondary", self.export_template)
        self.duplicate_btn = self.add_button("复制", "secondary", self.duplicate_template)
        # 使用模板：无选中时只弹提示、不关闭对话框（close_on_click=False）
        self.use_btn = self.add_button("使用模板", "primary", self.use_template,
                                       close_on_click=False)
        self.close_btn = self.add_close_button("关闭", "ghost")

    def load_templates(self):
        self.template_list.clear()

        device_type = None
        if self.device_combo.currentText() != "全部":
            device_map = {"华为": "huawei", "H3C": "h3c", "锐捷": "ruijie",
                          "迈普": "maipu", "思科": "cisco"}
            device_type = device_map.get(self.device_combo.currentText())

        keyword = self.search_input.text().strip()

        if keyword:
            templates = self.template_manager.search_templates(keyword, device_type)
        else:
            templates = self.template_manager.get_templates(device_type)

        for template in templates:
            item = QListWidgetItem(f"{'🔒 ' if template.is_builtin else '📝 '}{template.name}")
            item.setData(Qt.UserRole, f"{template.device_type}_{template.name}")

            if template.device_type == "huawei":
                item.setForeground(Qt.darkBlue)
            else:
                item.setForeground(Qt.darkGreen)

            self.template_list.addItem(item)

    def on_device_filter_changed(self):
        self.load_templates()

    def on_search_changed(self):
        self.load_templates()

    def on_template_selected(self, current, previous):
        if not current:
            return

        key = current.data(Qt.UserRole)
        device_type, name = key.split("_", 1)

        self.current_template = self.template_manager.get_template(name, device_type)

        if self.current_template:
            self.name_input.setText(self.current_template.name)
            self.device_label.setText({"huawei": "华为", "h3c": "H3C", "ruijie": "锐捷",
                                        "maipu": "迈普", "cisco": "思科"}.get(
                self.current_template.device_type, self.current_template.device_type))
            self.desc_input.setPlainText(self.current_template.description)
            self.tags_label.setText(", ".join(self.current_template.tags))

            import json
            self.config_preview.setPlainText(json.dumps(self.current_template.config, ensure_ascii=False, indent=2))

            self.author_label.setText(f"作者: {self.current_template.author or '未知'}")
            self.time_label.setText(f"创建: {self.current_template.created_time}")

            self.delete_btn.setEnabled(not self.current_template.is_builtin)

    def on_template_double_clicked(self, item):
        self.use_template()

    def create_template(self):
        name, ok = QInputDialog.getText(self, "新建模板", "请输入模板名称:")
        if ok and name:
            template = Template(
                name=name,
                device_type=self.device_type,
                description="新建模板",
                config={"basic": {}},
                tags=["自定义"]
            )

            if self.template_manager.save_template(template):
                info_box(self, "成功", f"模板 '{name}' 创建成功！")
                self.load_templates()
            else:
                warn_box(self, "失败", "创建模板失败，名称可能已存在。")

    def delete_template(self):
        if not self.current_template:
            return

        if self.current_template.is_builtin:
            warn_box(self, "无法删除", "内置模板不能删除！")
            return

        if question_box(
            self, "确认删除",
            f"确定要删除模板 '{self.current_template.name}' 吗？",
            ok="是", cancel="否"
        ):
            if self.template_manager.delete_template(self.current_template.name, self.current_template.device_type):
                info_box(self, "成功", "模板已删除！")
                self.load_templates()

    def duplicate_template(self):
        if not self.current_template:
            return

        new_name, ok = QInputDialog.getText(
            self, "复制模板",
            "请输入新模板名称:",
            text=f"{self.current_template.name}_副本"
        )

        if ok and new_name:
            if self.template_manager.duplicate_template(
                self.current_template.name, self.current_template.device_type, new_name
            ):
                info_box(self, "成功", f"模板已复制为 '{new_name}'！")
                self.load_templates()

    def import_template(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "导入模板", "", "JSON文件 (*.json)"
        )

        if file_path:
            if self.template_manager.import_template(file_path):
                info_box(self, "成功", "模板导入成功！")
                self.load_templates()
            else:
                warn_box(self, "失败", "导入模板失败，请检查文件格式。")

    def export_template(self):
        if not self.current_template:
            warn_box(self, "提示", "请先选择一个模板！")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出模板",
            f"{self.current_template.name}.json",
            "JSON文件 (*.json)"
        )

        if file_path:
            if self.template_manager.export_template(
                self.current_template.name, self.current_template.device_type, file_path
            ):
                info_box(self, "成功", "模板导出成功！")

    def save_edited_template(self):
        if not self.current_template:
            return

        import json

        try:
            config = json.loads(self.edit_config.toPlainText())
        except json.JSONDecodeError:
            warn_box(self, "错误", "配置JSON格式错误！")
            return

        new_name = self.edit_name.text().strip()
        if new_name and new_name != self.current_template.name:
            self.template_manager.rename_template(
                self.current_template.name, new_name, self.current_template.device_type
            )
            self.current_template.name = new_name

        self.current_template.description = self.edit_desc.toPlainText()
        self.current_template.author = self.edit_author.text()
        self.current_template.config = config
        self.current_template.tags = [t.strip() for t in self.edit_tags.text().split(",") if t.strip()]

        if self.template_manager.save_template(self.current_template):
            info_box(self, "成功", "模板保存成功！")
            self.load_templates()

    def cancel_edit(self):
        if self.current_template:
            self.edit_name.setText(self.current_template.name)
            self.edit_desc.setPlainText(self.current_template.description)
            self.edit_author.setText(self.current_template.author)
            self.edit_tags.setText(", ".join(self.current_template.tags))
            import json
            self.edit_config.setPlainText(json.dumps(self.current_template.config, ensure_ascii=False, indent=2))

    def use_template(self):
        if not self.current_template:
            warn_box(self, "提示", "请先选择一个模板！")
            return

        self.template_selected.emit({
            "name": self.current_template.name,
            "device_type": self.current_template.device_type,
            "config": self.current_template.config
        })
        self.close()


class SaveTemplateDialog(BaseDialog):
    """保存配置为模板对话框（统一无边框子窗口骨架）"""

    def __init__(self, parent=None, config: dict = None, device_type: str = "huawei"):
        self.config = config or {}
        self.device_type = device_type
        self.template_manager = TemplateManager()
        super().__init__("保存为模板", "", parent, min_width=460)
        self.initUI()

    def initUI(self):
        layout = self.content_layout()
        layout.setSpacing(12)

        name_layout = QHBoxLayout()
        name_layout.setSpacing(10)
        name_layout.addWidget(QLabel("模板名称:"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("输入模板名称")
        self.name_input.setMinimumHeight(40)
        name_layout.addWidget(self.name_input, 1)
        layout.addLayout(name_layout)

        layout.addWidget(QLabel("描述:"))
        self.desc_input = QTextEdit()
        self.desc_input.setPlaceholderText("输入模板描述...")
        self.desc_input.setMaximumHeight(80)
        layout.addWidget(self.desc_input)

        author_layout = QHBoxLayout()
        author_layout.setSpacing(10)
        author_layout.addWidget(QLabel("作者:"))
        self.author_input = QLineEdit()
        self.author_input.setPlaceholderText("可选")
        self.author_input.setMinimumHeight(40)
        author_layout.addWidget(self.author_input, 1)
        layout.addLayout(author_layout)

        tags_layout = QHBoxLayout()
        tags_layout.setSpacing(10)
        tags_layout.addWidget(QLabel("标签:"))
        self.tags_input = QLineEdit()
        self.tags_input.setPlaceholderText("标签1, 标签2, ...")
        self.tags_input.setMinimumHeight(40)
        tags_layout.addWidget(self.tags_input, 1)
        layout.addLayout(tags_layout)

        self.save_btn = self.add_button("保存", "primary", self.save_template,
                                        close_on_click=False)
        self.cancel_btn = self.add_close_button("取消", "ghost")

    def save_template(self):
        name = self.name_input.text().strip()
        if not name:
            warn_box(self, "错误", "请输入模板名称！")
            return

        template = Template(
            name=name,
            device_type=self.device_type,
            description=self.desc_input.toPlainText(),
            config=self.config,
            author=self.author_input.text(),
            tags=[t.strip() for t in self.tags_input.text().split(",") if t.strip()]
        )

        if self.template_manager.save_template(template):
            info_box(self, "成功", f"模板 '{name}' 保存成功！")
            self.accept()
        else:
            warn_box(self, "失败", "保存模板失败，名称可能已存在。")