#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
NetOps Toolkit - 设备运维标签页（二开新增）
设备清单管理 + 真机连通测试 + 命令执行 + 配置下发 + 配置备份
SSH 层复用 modules.device_connector（Netmiko），备份落盘复用 utils.backup_manager
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
                             QGroupBox, QComboBox, QTextEdit, QLineEdit,
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QHeaderView, QDialog, QDialogButtonBox,
                             QSpinBox, QMessageBox, QSplitter, QInputDialog)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from utils.device_store import DeviceStore
from utils.credential_crypto import decrypt
from modules import device_connector as dc
from modules.device_connector import VENDOR_LABELS


# ---------------------------------------------------------------- 设备编辑对话框
class DeviceDialog(QDialog):
    """新增/编辑设备表单"""

    VENDORS = [("huawei", "华为"), ("h3c", "H3C"), ("ruijie", "锐捷"), ("maipu", "迈普"), ("cisco", "思科")]
    ROLES = [("access", "接入"), ("core", "核心"), ("exit", "出口"), ("dc", "数据中心")]

    def __init__(self, device=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑设备" if device else "新增设备")
        self.setMinimumWidth(380)
        self._device = device or {}

        layout = QFormLayout(self)
        layout.setSpacing(10)

        self.name_input = QLineEdit(self._device.get("name", ""))
        self.name_input.setPlaceholderText("如：核心-S9306")
        layout.addRow("设备名称:", self.name_input)

        self.ip_input = QLineEdit(self._device.get("ip", ""))
        self.ip_input.setPlaceholderText("192.168.1.1")
        layout.addRow("管理 IP:", self.ip_input)

        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(int(self._device.get("ssh_port", 22)))
        layout.addRow("SSH 端口:", self.port_input)

        self.vendor_input = QComboBox()
        for value, label in self.VENDORS:
            self.vendor_input.addItem(label, value)
        if device:
            idx = self.vendor_input.findData(device.get("vendor", "huawei"))
            self.vendor_input.setCurrentIndex(max(idx, 0))
        layout.addRow("厂商:", self.vendor_input)

        self.model_input = QLineEdit(self._device.get("model", ""))
        self.model_input.setPlaceholderText("S5735 / S6520（可选）")
        layout.addRow("型号:", self.model_input)

        self.role_input = QComboBox()
        for value, label in self.ROLES:
            self.role_input.addItem(label, value)
        if device:
            idx = self.role_input.findData(device.get("role", "access"))
            self.role_input.setCurrentIndex(max(idx, 0))
        layout.addRow("角色:", self.role_input)

        self.user_input = QLineEdit(self._device.get("username", ""))
        layout.addRow("用户名:", self.user_input)

        self.pwd_input = QLineEdit()
        self.pwd_input.setEchoMode(QLineEdit.Password)
        self.pwd_input.setPlaceholderText("编辑时留空=不修改")
        layout.addRow("密码:", self.pwd_input)

        self.notes_input = QLineEdit(self._device.get("notes", ""))
        layout.addRow("备注:", self.notes_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def data(self):
        return {
            "name": self.name_input.text().strip(),
            "ip": self.ip_input.text().strip(),
            "ssh_port": self.port_input.value(),
            "vendor": self.vendor_input.currentData(),
            "model": self.model_input.text().strip(),
            "role": self.role_input.currentData(),
            "username": self.user_input.text().strip(),
            "password": self.pwd_input.text(),
            "notes": self.notes_input.text().strip(),
        }


# ---------------------------------------------------------------- 后台线程
class _Worker(QThread):
    """把阻塞的 SSH 操作放后台线程，避免卡死 GUI"""
    log = pyqtSignal(str)
    finished_all = pyqtSignal()

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            self._fn(self.log.emit)
        finally:
            self.finished_all.emit()


# ---------------------------------------------------------------- 主面板
class DeviceOpsTab(QWidget):
    """设备运维标签页"""

    def __init__(self):
        super().__init__()
        self.store = DeviceStore()
        self._worker = None
        self.initUI()
        self.refresh_table()

    # ---------------- UI ----------------
    def initUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        splitter = QSplitter(Qt.Vertical)
        layout.addWidget(splitter)

        # 上半：设备清单
        top_group = QGroupBox("设备清单（凭据本地加密存储于 config/devices.json）")
        top_layout = QVBoxLayout(top_group)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["ID", "名称", "管理IP", "端口", "厂商", "型号", "备注"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.resizeSection(0, 40)
        header.resizeSection(1, 130)
        header.resizeSection(2, 120)
        header.resizeSection(3, 50)
        header.resizeSection(4, 60)
        header.resizeSection(5, 110)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        top_layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        self.add_btn = QPushButton("＋ 新增")
        self.edit_btn = QPushButton("编辑")
        self.del_btn = QPushButton("删除")
        self.test_btn = QPushButton("测试连通（SSH 登录）")
        self.probe_btn = QPushButton("批量探测（TCP）")
        for b in (self.add_btn, self.edit_btn, self.del_btn, self.test_btn, self.probe_btn):
            btn_row.addWidget(b)
        btn_row.addStretch()
        top_layout.addLayout(btn_row)

        self.add_btn.clicked.connect(self.add_device)
        self.edit_btn.clicked.connect(self.edit_device)
        self.del_btn.clicked.connect(self.del_device)
        self.test_btn.clicked.connect(self.test_selected)
        self.probe_btn.clicked.connect(self.probe_all)

        splitter.addWidget(top_group)

        # 下半：命令执行 / 配置下发 / 备份
        ops_group = QGroupBox("真机操作")
        ops_layout = QVBoxLayout(ops_group)

        cmd_row = QHBoxLayout()
        self.cmd_input = QLineEdit()
        self.cmd_input.setPlaceholderText("输入回显命令，如 display version / show ip interface brief")
        self.cmd_btn = QPushButton("执行命令")
        cmd_row = QHBoxLayout()
        cmd_row.addWidget(self.cmd_input, 3)
        cmd_row.addWidget(self.cmd_btn, 1)
        ops_layout.addLayout(cmd_row)
        self.cmd_btn.clicked.connect(self.run_command)

        deploy_row = QHBoxLayout()
        self.deploy_btn = QPushButton("下发配置到选中设备")
        self.backup_btn = QPushButton("备份选中设备配置")
        deploy_row.addWidget(self.deploy_btn)
        deploy_row.addWidget(self.backup_btn)
        deploy_row.addStretch()
        ops_layout.addLayout(deploy_row)

        self.deploy_input = QTextEdit()
        self.deploy_input.setPlaceholderText(
            "粘贴要下发的配置命令（每行一条，# 开头的注释行自动忽略）——可以直接用上方各配置页「生成」出的配置")
        self.deploy_input.setMaximumHeight(120)
        ops_layout.addWidget(self.deploy_input)

        self.deploy_btn.clicked.connect(self.deploy_config)
        self.backup_btn.clicked.connect(self.backup_config)

        splitter.addWidget(ops_group)

        # 输出日志
        log_group = QGroupBox("执行结果")
        log_layout = QVBoxLayout(log_group)
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        log_layout.addWidget(self.output)
        splitter.addWidget(log_group)

        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 4)

    # ---------------- 工具方法 ----------------
    def log(self, text):
        self.output.append(text)

    def _selected_device(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "提示", "请先在表格中选中一台设备")
            return None
        device_id = int(self.table.item(row, 0).text())
        device = self.store.get(device_id)
        if not device:
            QMessageBox.warning(self, "提示", "设备不存在（可能已被删除）")
            return None
        return device

    def _password_of(self, device):
        """解密取回设备密码"""
        return decrypt(device.get("password_enc", ""))

    def _busy(self, busy):
        for b in (self.add_btn, self.edit_btn, self.del_btn, self.test_btn,
                  self.probe_btn, self.cmd_btn, self.deploy_btn, self.backup_btn):
            b.setEnabled(not busy)

    def _run_async(self, fn):
        """把阻塞操作丢进后台线程"""
        self._busy(True)
        self._worker = _Worker(fn, self)
        self._worker.log.connect(self.log)
        self._worker.finished_all.connect(lambda: self._busy(False))
        self._worker.start()

    # ---------------- 设备管理 ----------------
    def refresh_table(self):
        devices = self.store.list_all()
        self.table.setRowCount(len(devices))
        for r, d in enumerate(devices):
            vals = [str(d["id"]), d["name"], d["ip"], str(d.get("ssh_port", 22)),
                    VENDOR_LABELS.get(d.get("vendor"), d.get("vendor", "")),
                    d.get("model", ""), d.get("notes", "")]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(v)
                if c in (0, 3):
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(r, c, item)

    def add_device(self):
        dlg = DeviceDialog(parent=self)
        if dlg.exec_():
            data = dlg.data()
            if not data["name"] or not data["ip"]:
                QMessageBox.warning(self, "提示", "设备名称和管理 IP 必填")
                return
            self.store.add(data)
            self.refresh_table()
            self.log(f"[设备] 已新增：{data['name']} ({data['ip']})")

    def edit_device(self):
        device = self._selected_device()
        if not device:
            return
        dlg = DeviceDialog(device, parent=self)
        if dlg.exec_():
            data = dlg.data()
            if not data["name"] or not data["ip"]:
                QMessageBox.warning(self, "提示", "设备名称和管理 IP 必填")
                return
            self.store.update(device["id"], data)
            self.refresh_table()
            pwd_note = "（密码已更新）" if data["password"] else "（密码未修改）"
            self.log(f"[设备] 已更新：{data['name']} ({data['ip']}) {pwd_note}")

    def del_device(self):
        device = self._selected_device()
        if not device:
            return
        ret = QMessageBox.question(self, "删除确认",
                                   f"确定删除设备「{device['name']}」({device['ip']})？",
                                   QMessageBox.Yes | QMessageBox.No)
        if ret == QMessageBox.Yes:
            self.store.delete(device["id"])
            self.refresh_table()
            self.log(f"[设备] 已删除：{device['name']} ({device['ip']})")

    # ---------------- 真机操作 ----------------
    def test_selected(self):
        device = self._selected_device()
        if not device:
            return
        if not self._password_of(device):
            QMessageBox.warning(self, "提示", "该设备未保存密码，无法做 SSH 登录测试")
            return

        def job(log):
            log(f"[测试] {device['name']} ({device['ip']}) SSH 登录测试中…")
            ok, msg, latency = dc.test_ssh_login(device, self._password_of(device))
            log(f"[测试] {device['name']}: {'✅' if ok else '❌'} {msg}")

        self._run_async(job)

    def probe_all(self):
        devices = self.store.list_all()
        if not devices:
            QMessageBox.information(self, "提示", "设备清单为空，请先新增设备")
            return

        def job(log):
            log(f"[探测] 开始批量 TCP 探测 {len(devices)} 台设备…")
            plain = {d["id"]: d for d in [self.store.get(x["id"]) for x in devices]}
            results = dc.batch_execute(
                list(plain.values()),
                lambda dev, _pwd: dc.tcp_probe(dev["ip"], dev.get("ssh_port", 22)),
                lambda _id: "",
                progress_cb=lambda done, total: log(f"[探测] 进度 {done}/{total}") if done % 5 == 0 or done == total else None,
            )
            for dev in plain.values():
                ok, msg, _ = results.get(dev["id"], (False, "未执行", None))
                log(f"[探测] {dev['name']} ({dev['ip']}): {'✅' if ok else '❌'} {msg}")
            log(f"[探测] 完成，共 {len(devices)} 台")

        self._run_async(job)

    def run_command(self):
        device = self._selected_device()
        if not device:
            return
        command = self.cmd_input.text().strip()
        if not command:
            QMessageBox.warning(self, "提示", "请输入要执行的命令")
            return

        def job(log):
            log(f"[命令] {device['name']} > {command}")
            ok, output = dc.run_command(device, self._password_of(device), command)
            log(f"[命令] {'✅ 执行成功' if ok else '❌ 执行失败'}，输出：\n{output}")

        self._run_async(job)

    def deploy_config(self):
        device = self._selected_device()
        if not device:
            return
        config_text = self.deploy_input.toPlainText().strip()
        if not config_text:
            QMessageBox.warning(self, "提示", "请粘贴要下发的配置命令")
            return
        ret = QMessageBox.question(
            self, "下发确认",
            f"即将向「{device['name']}」({device['ip']}) 下发 {len([l for l in config_text.splitlines() if l.strip() and not l.strip().startswith('#')])} 条配置命令。\n\n请确认已在测试环境验证，继续？",
            QMessageBox.Yes | QMessageBox.No)
        if ret != QMessageBox.Yes:
            return

        def job(log):
            log(f"[下发] {device['name']} ({device['ip']}) 配置下发中…")
            ok, output = dc.send_config(device, self._password_of(device), config_text)
            log(f"[下发] {'✅ 下发完成' if ok else '❌ 下发失败'}，设备回显：\n{output}")

        self._run_async(job)

    def backup_config(self):
        device = self._selected_device()
        if not device:
            return

        def job(log):
            log(f"[备份] {device['name']} ({device['ip']}) 抓取 running-config…")
            ok, config = dc.fetch_running_config(device, self._password_of(device))
            if not ok:
                log(f"[备份] ❌ 抓取失败：{config}")
                return
            from utils.backup_manager import ConfigBackupManager
            manager = ConfigBackupManager()
            backup_id = manager.create_backup(
                config_content=config,
                device_name=device["name"],
                device_type=VENDOR_LABELS.get(device.get("vendor"), device.get("vendor")),
                ip_address=device["ip"],
                description=f"由设备运维面板备份，共 {len(config.splitlines())} 行",
            )
            if backup_id:
                log(f"[备份] ✅ 已存档，备份 ID：{backup_id}（可在 backups/ 目录查看，历史备份支持 Diff 对比）")
            else:
                log("[备份] ❌ 存档失败（详见控制台输出）")

        self._run_async(job)
