#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
批量配置生成对话框
"""

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QHeaderView, QTextEdit, QComboBox, QSpinBox,
                             QProgressBar, QFileDialog, QWidget)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from gui.styles import MODERN_STYLE, TOOLTIP_STYLE, DIALOG_STYLE
from gui.dialogs.base import (BaseDialog, make_button, info_box, warn_box,
                             error_box)
from modules.basic_config import BasicConfigGenerator


class BatchGenerateWorker(QThread):
    """批量配置生成工作线程"""
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(list)
    
    def __init__(self, devices):
        super().__init__()
        self.devices = devices
    
    def run(self):
        results = []
        total = len(self.devices)
        
        for i, device in enumerate(self.devices):
            self.progress.emit(int((i / total) * 100), f"正在生成 {device['hostname']}...")
            
            config = self._generate_config(device)
            results.append({
                "hostname": device['hostname'],
                "ip": device.get('ip', ''),
                "config": config
            })
        
        self.progress.emit(100, "生成完成")
        self.finished.emit(results)
    
    def _generate_config(self, device):
        device_type = device.get('device_type', 'huawei')
        hostname = device.get('hostname', 'Switch')
        mgmt_ip = device.get('ip', '192.168.1.1')
        mask = device.get('mask', '24')
        vlans = device.get('vlans', [])
        
        from datetime import datetime
        import ipaddress
        
        config_lines = [
            f"{'!' * 50}",
            f"# 配置生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"# 设备名称: {hostname}",
            f"# 设备类型: {device_type.upper()}",
            f"{'!' * 50}",
            ""
        ]
        
        try:
            mask_bits = int(mask)
            subnet = ipaddress.IPv4Network(f"0.0.0.0/{mask_bits}", strict=False)
            mask_str = str(subnet.netmask)
        except:
            mask_str = "255.255.255.0"
        
        if device_type == 'huawei':
            config_lines.extend([
                f"sysname {hostname}",
                "",
                "interface Vlanif1",
                f" ip address {mgmt_ip} {mask_str}",
                " quit",
                "",
                "ssh server enable",
                "stelnet server enable",
                "user-interface vty 0 4",
                " authentication-mode aaa",
                " protocol inbound ssh",
                " quit",
                "",
            ])
            
            for vlan in vlans:
                config_lines.extend([
                    f"vlan {vlan['id']}",
                    f" description {vlan['name']}",
                    " quit",
                    ""
                ])
        else:
            config_lines.extend([
                f"sysname {hostname}",
                "",
                "interface Vlan-interface1",
                f" ip address {mgmt_ip} {mask_str}",
                " quit",
                "",
                "ssh server enable",
                "telnet server enable",
                "user-interface vty 0 4",
                " authentication-mode scheme",
                " protocol inbound ssh",
                " quit",
                "",
            ])
            
            for vlan in vlans:
                config_lines.extend([
                    f"vlan {vlan['id']}",
                    f" name {vlan['name']}",
                    " quit",
                    ""
                ])
        
        config_lines.extend([
            "return",
            "",
            f"{'!' * 50}",
        ])
        
        return '\n'.join(config_lines)


class BatchConfigDialog(BaseDialog):
    """批量配置生成对话框（统一无边框子窗口骨架）"""
    
    def __init__(self, parent=None, device_type='huawei'):
        self.device_type = device_type
        self.worker = None
        self.results = []
        super().__init__("批量配置生成", "", parent, min_width=900, min_height=600)
        self.initUI()
    
    def initUI(self):
        layout = self.content_layout()
        layout.setSpacing(12)
        
        settings_layout = QHBoxLayout()
        settings_layout.setSpacing(10)
        
        type_label = QLabel("设备类型:")
        type_label.setStyleSheet("font-weight: bold;")
        settings_layout.addWidget(type_label)
        
        self.device_combo = QComboBox()
        self.device_combo.addItems(["华为 (Huawei)", "H3C (华三)"])
        self.device_combo.setCurrentIndex(0 if self.device_type == 'huawei' else 1)
        self.device_combo.setMinimumHeight(40)
        self.device_combo.setMinimumWidth(160)
        settings_layout.addWidget(self.device_combo)
        
        settings_layout.addStretch()
        
        add_row_btn = make_button("添加设备", "secondary")
        add_row_btn.clicked.connect(self.add_device_row)
        settings_layout.addWidget(add_row_btn)
        
        del_row_btn = make_button("删除选中", "ghost")
        del_row_btn.clicked.connect(self.remove_selected_row)
        settings_layout.addWidget(del_row_btn)
        
        clear_btn = make_button("清空列表", "ghost")
        clear_btn.clicked.connect(self.clear_devices)
        settings_layout.addWidget(clear_btn)
        
        layout.addLayout(settings_layout)
        
        self.device_table = QTableWidget()
        from gui.widget_utils import polish_table
        polish_table(self.device_table)
        self.device_table.setColumnCount(5)
        self.device_table.setHorizontalHeaderLabels(["主机名", "管理IP", "掩码", "VLAN列表", "备注"])
        self.device_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.device_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.device_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.device_table.setMinimumHeight(160)
        layout.addWidget(self.device_table, 1)
        
        tip_label = QLabel("VLAN列表格式: 10:Sales,20:Engineering,30:HR (ID:名称)")
        tip_label.setStyleSheet("color: #5F6B7A; font-size: 11px;")
        layout.addWidget(tip_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        preview_header = QHBoxLayout()
        preview_label = QLabel("配置预览:")
        preview_label.setStyleSheet("font-weight: bold;")
        preview_header.addWidget(preview_label)
        
        preview_header.addStretch()
        
        self.hostname_label = QLabel("")
        self.hostname_label.setStyleSheet("color: #0089FF; font-weight: bold;")
        preview_header.addWidget(self.hostname_label)
        
        layout.addLayout(preview_header)
        
        self.preview_text = QTextEdit()
        self.preview_text.setFont(QFont("Consolas", 10))
        self.preview_text.setReadOnly(True)
        self.preview_text.setMinimumHeight(140)
        layout.addWidget(self.preview_text, 1)
        
        # ---------- 全局动作按钮（BaseDialog 统一行） ----------
        self.import_btn = self.add_button("导入CSV", "secondary", self.import_csv,
                                          close_on_click=False)
        self.generate_btn = self.add_button("批量生成", "primary", self.generate_configs,
                                            close_on_click=False)
        self.export_btn = self.add_button("导出全部", "secondary", self.export_all,
                                          close_on_click=False)
        self.close_btn = self.add_close_button("关闭", "ghost")
        
        for i in range(3):
            self.add_device_row()
    
    def add_device_row(self):
        row = self.device_table.rowCount()
        self.device_table.insertRow(row)
        
        self.device_table.setItem(row, 0, QTableWidgetItem(f"SW-{row+1:02d}"))
        self.device_table.setItem(row, 1, QTableWidgetItem(f"192.168.1.{row+1}"))
        self.device_table.setItem(row, 2, QTableWidgetItem("24"))
        self.device_table.setItem(row, 3, QTableWidgetItem("1:Management"))
        self.device_table.setItem(row, 4, QTableWidgetItem(""))
    
    def remove_selected_row(self):
        rows = self.device_table.selectionModel().selectedRows()
        for row in sorted([r.row() for r in rows], reverse=True):
            self.device_table.removeRow(row.row())
    
    def clear_devices(self):
        self.device_table.setRowCount(0)
    
    def get_devices(self):
        devices = []
        for row in range(self.device_table.rowCount()):
            hostname = self.device_table.item(row, 0).text() if self.device_table.item(row, 0) else ""
            ip = self.device_table.item(row, 1).text() if self.device_table.item(row, 1) else ""
            mask = self.device_table.item(row, 2).text() if self.device_table.item(row, 2) else "24"
            vlan_text = self.device_table.item(row, 3).text() if self.device_table.item(row, 3) else ""
            
            vlans = []
            if vlan_text:
                try:
                    for v in vlan_text.split(','):
                        parts = v.strip().split(':')
                        if len(parts) == 2:
                            vlans.append({'id': int(parts[0]), 'name': parts[1]})
                except:
                    pass
            
            devices.append({
                'hostname': hostname,
                'ip': ip,
                'mask': mask,
                'vlans': vlans,
                'device_type': 'huawei' if self.device_combo.currentIndex() == 0 else 'h3c'
            })
        
        return devices
    
    def generate_configs(self):
        devices = self.get_devices()
        if not devices:
            warn_box(self, "提示", "请先添加设备")
            return
        
        self.worker = BatchGenerateWorker(devices)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()
    
    def on_progress(self, percent, msg):
        self.progress_bar.setValue(percent)
    
    def on_finished(self, results):
        self.results = results
        if results:
            self.show_preview(0)
        info_box(self, "完成", f"已生成 {len(results)} 个设备配置")
    
    def show_preview(self, index):
        if 0 <= index < len(self.results):
            result = self.results[index]
            self.hostname_label.setText(f"设备: {result['hostname']} ({result['ip']})")
            self.preview_text.setPlainText(result['config'])
    
    def import_csv(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "导入CSV", "", "CSV文件 (*.csv)")
        if filepath:
            try:
                import csv
                with open(filepath, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    self.device_table.setRowCount(0)
                    for row in reader:
                        self.add_device_row()
                        r = self.device_table.rowCount() - 1
                        self.device_table.setItem(r, 0, QTableWidgetItem(row.get('hostname', '')))
                        self.device_table.setItem(r, 1, QTableWidgetItem(row.get('ip', '')))
                        self.device_table.setItem(r, 2, QTableWidgetItem(row.get('mask', '24')))
                        self.device_table.setItem(r, 3, QTableWidgetItem(row.get('vlans', '')))
                        self.device_table.setItem(r, 4, QTableWidgetItem(row.get('note', '')))
                info_box(self, "成功", f"已导入 {self.device_table.rowCount()} 个设备")
            except Exception as e:
                error_box(self, "错误", f"导入失败: {str(e)}")
    
    def export_all(self):
        if not self.results:
            warn_box(self, "提示", "请先生成配置")
            return
        
        dir_path = QFileDialog.getExistingDirectory(self, "选择导出目录")
        if dir_path:
            import os
            for result in self.results:
                filename = f"{result['hostname']}_config.txt"
                filepath = os.path.join(dir_path, filename)
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(result['config'])
            info_box(self, "成功", f"已导出 {len(self.results)} 个配置文件")
