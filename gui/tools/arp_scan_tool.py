#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ARP 内网扫描工具页（工具箱内）
活动设备发现：IP / MAC / 厂商 / 主机名 / 姓名（名册）+ 虚拟 IP 风险检测
原理：多线程 ping 全网段激发 ARP 解析（防火墙拦 ping 也能收到二层应答）
→ 读本机 ARP 缓存收集设备；同 IP 多 MAC 报冲突/欺骗，同 MAC 多 IP 报虚拟化。
"""

import threading

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFileDialog,
                             QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                             QMenu, QProgressBar, QPushButton, QSpinBox, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget, QAction)

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from modules import arp_scan
from utils.network_tools.ping_tool import PingTool
from gui.tool_styles import (
    TOOL_LABEL_STYLE, TOOL_LABEL_SECONDARY,
    TOOL_BUTTON_PRIMARY, TOOL_BUTTON_DANGER, TOOL_BUTTON_SECONDARY, TOOL_BUTTON_GHOST,
    TOOL_STATUS_SUCCESS, TOOL_STATUS_ERROR, TOOL_STATUS_INFO, TOOL_STATUS_WARNING,
    apply_tool_style,
)
from gui.dialogs.base import warn_box
from gui.widget_utils import polish_table


class ArpScanWorker(QThread):
    """ARP 扫描工作线程（协作式停止：stop_flag + PingTool 子进程注册表）"""
    progress = pyqtSignal(str, int, int)       # 阶段, 已完成, 总数
    device_found = pyqtSignal(dict)            # 每台设备就绪即发（实时填充，不冻结）
    finished_ok = pyqtSignal(dict)             # 全量结果（含 risks/stats）
    failed = pyqtSignal(str)

    def __init__(self, cidr="", workers=100, nbt_enabled=True, parent=None):
        super().__init__(parent)
        self.cidr = cidr
        self.workers = workers
        self.nbt_enabled = nbt_enabled
        self.stop_flag = threading.Event()

    def stop(self):
        self.stop_flag.set()
        PingTool.stop_all()   # kill 活跃 ping 子进程，线程自然收尾

    def run(self):
        try:
            result = arp_scan.scan(
                cidr=self.cidr, workers=self.workers, ping_timeout=1,
                nbt_enabled=self.nbt_enabled, stop_flag=self.stop_flag,
                progress_cb=lambda p, d, t: self.progress.emit(p, d, t),
                device_cb=lambda d: self.device_found.emit(d),
            )
            if self.stop_flag.is_set():
                result["stopped"] = True
            if result.get("ok"):
                self.finished_ok.emit(result)
            else:
                self.failed.emit(result.get("error") or "扫描失败")
        except Exception as e:
            self.failed.emit(f"扫描异常: {e}")


class ArpScanWidget(QWidget):
    """ARP 内网扫描：活动设备 + 虚拟 IP 风险"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self._devices = {}      # (ip, mac) -> device dict（本页当前展示集）
        self._row_index = {}    # (ip, mac) -> 行号（upsert 用，防重复插入）
        self.initUI()
        self.refresh_adapters()

    # ================= UI =================
    def initUI(self):
        apply_tool_style(self)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.setContentsMargins(15, 15, 15, 15)

        title = QLabel("📡 ARP 内网扫描")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #0089FF; padding: 5px 0;")
        lay.addWidget(title)

        desc = QLabel("先 ping 全网段激发 ARP 解析、再读本机 ARP 缓存收集活动设备——"
                      "防火墙拦 ping 的设备也能发现；同 IP 多 MAC = IP 冲突/ARP 欺骗，"
                      "同 MAC 多 IP = 虚拟机/多地址。只读探测，不发任何写操作。")
        desc.setStyleSheet(TOOL_LABEL_SECONDARY)
        desc.setWordWrap(True)
        lay.addWidget(desc)

        # ---- 扫描设置 ----
        set_group = QGroupBox("扫描设置")
        sg_lay = QVBoxLayout(set_group)
        sg_lay.setSpacing(8)

        row1 = QHBoxLayout()
        row1.setSpacing(8)
        row1.addWidget(QLabel("网卡:"))
        self.adapter_combo = QComboBox()
        self.adapter_combo.setMinimumWidth(300)
        self.adapter_combo.currentIndexChanged.connect(self._on_adapter_changed)
        row1.addWidget(self.adapter_combo, 2)
        self.refresh_btn = QPushButton("🔄 刷新网卡")
        self.refresh_btn.setStyleSheet(TOOL_BUTTON_GHOST)
        self.refresh_btn.clicked.connect(self.refresh_adapters)
        row1.addWidget(self.refresh_btn)
        self.nbt_check = QCheckBox("解析 NetBIOS 主机名（仅 Windows 设备有效）")
        self.nbt_check.setChecked(True)
        row1.addWidget(self.nbt_check)
        sg_lay.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addWidget(QLabel("网段:"))
        self.cidr_edit = QLineEdit()
        self.cidr_edit.setPlaceholderText("如 192.168.1.0/24（选择网卡自动填充，可手改）")
        row2.addWidget(self.cidr_edit, 2)
        row2.addWidget(QLabel("并发:"))
        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(16, 512)
        self.workers_spin.setValue(128)
        self.workers_spin.setToolTip("/24 建议默认 128；网段越大越快但占 CPU")
        row2.addWidget(self.workers_spin)
        self.scan_btn = QPushButton("▶ 开始扫描")
        self.scan_btn.setStyleSheet(TOOL_BUTTON_PRIMARY)
        self.scan_btn.clicked.connect(self.start_scan)
        row2.addWidget(self.scan_btn)
        self.stop_btn = QPushButton("⏹ 停止")
        self.stop_btn.setStyleSheet(TOOL_BUTTON_DANGER)
        self.stop_btn.clicked.connect(self.stop_scan)
        self.stop_btn.setEnabled(False)
        row2.addWidget(self.stop_btn)
        sg_lay.addLayout(row2)

        prog_row = QHBoxLayout()
        prog_row.setSpacing(8)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setFormat("")   # 未扫描不显示文字（避免与进度底色叠字）
        prog_row.addWidget(self.progress, 1)
        sg_lay.addLayout(prog_row)

        lay.addWidget(set_group)

        # ---- 设备表 ----
        dev_group = QGroupBox("活动设备（右键：登记姓名 / Ping / 复制 / 导出）")
        dev_lay = QVBoxLayout(dev_group)
        dev_lay.setSpacing(6)
        self.device_table = QTableWidget(0, 7)
        polish_table(self.device_table)
        self.device_table.setHorizontalHeaderLabels(
            ["IP 地址", "MAC 地址", "厂商", "主机名", "姓名(名册)", "标注", "ARP 类型"])
        _h = self.device_table.horizontalHeader()
        _h.setSectionResizeMode(QHeaderView.ResizeToContents)
        _h.setSectionResizeMode(0, QHeaderView.Stretch)
        _h.setSectionResizeMode(4, QHeaderView.Stretch)
        self.device_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.device_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.device_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.device_table.customContextMenuRequested.connect(self._ctx_menu)
        dev_lay.addWidget(self.device_table)
        self.risk_label = QLabel("未扫描")
        self.risk_label.setWordWrap(True)
        self.risk_label.setStyleSheet(TOOL_LABEL_SECONDARY)
        dev_lay.addWidget(self.risk_label)
        lay.addWidget(dev_group, 4)

        # ---- 设备名册 ----
        roster_group = QGroupBox("设备名册（MAC/IP → 姓名·备注；扫描时自动回填姓名列）")
        ros_lay = QVBoxLayout(roster_group)
        ros_lay.setSpacing(8)

        add_row = QHBoxLayout()
        add_row.setSpacing(8)
        self.ros_mac_edit = QLineEdit()
        self.ros_mac_edit.setPlaceholderText("MAC（如 10:12:B4:F7:9A:CC）")
        self.ros_mac_edit.setMinimumWidth(160)
        self.ros_ip_edit = QLineEdit()
        self.ros_ip_edit.setPlaceholderText("IP（MAC 留空时按 IP 匹配）")
        self.ros_ip_edit.setMinimumWidth(150)
        self.ros_name_edit = QLineEdit()
        self.ros_name_edit.setPlaceholderText("姓名（如：张师傅·测试机）")
        self.ros_name_edit.setMinimumWidth(150)
        self.ros_note_edit = QLineEdit()
        self.ros_note_edit.setPlaceholderText("备注（可选）")
        self.ros_note_edit.setMinimumWidth(130)
        self.ros_add_btn = QPushButton("登记")
        self.ros_add_btn.setStyleSheet(TOOL_BUTTON_SECONDARY)
        self.ros_add_btn.clicked.connect(self.add_roster)
        for w, s in ((self.ros_mac_edit, 2), (self.ros_ip_edit, 2),
                     (self.ros_name_edit, 2), (self.ros_note_edit, 2)):
            add_row.addWidget(w, s)
        add_row.addWidget(self.ros_add_btn)
        ros_lay.addLayout(add_row)

        self.roster_table = QTableWidget(0, 5)
        polish_table(self.roster_table)
        self.roster_table.setHorizontalHeaderLabels(["姓名", "MAC", "IP", "备注", "操作"])
        _rh = self.roster_table.horizontalHeader()
        _rh.setSectionResizeMode(QHeaderView.ResizeToContents)
        _rh.setSectionResizeMode(0, QHeaderView.Stretch)
        self.roster_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.roster_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.roster_table.setMaximumHeight(150)
        ros_lay.addWidget(self.roster_table)

        self.roster_hint = QLabel("")
        self.roster_hint.setStyleSheet(TOOL_LABEL_SECONDARY)
        ros_lay.addWidget(self.roster_hint)

        lay.addWidget(roster_group, 1)

        self.status_bar = QLabel("就绪。设备名册为空时姓名列显示 —，右键设备行即可登记。")
        self.status_bar.setStyleSheet(TOOL_STATUS_INFO)
        self.status_bar.setWordWrap(True)
        lay.addWidget(self.status_bar)

        self._refresh_roster()

    # ================= 网卡/网段 =================
    def refresh_adapters(self):
        self.adapter_combo.blockSignals(True)
        self.adapter_combo.clear()
        self.adapter_combo.addItem("手动指定网段", None)
        try:
            adapters = arp_scan.get_adapters()
        except Exception:
            adapters = []
        default_idx = 0
        for i, a in enumerate(adapters):
            cidr = arp_scan.ip_to_cidr(a["ip"], a["mask"]) if a.get("mask") else ""
            label = f"{a['name']}: {a['ip']}"
            if cidr:
                label += f" ({cidr})"
            if a.get("gateway"):
                label += f" 网关 {a['gateway']}"
            if a.get("virtual"):
                label += " 【虚拟网卡】"
            self.adapter_combo.addItem(label, {"cidr": cidr, "ip": a["ip"]})
            if not a.get("virtual") and a.get("gateway") and default_idx == 0:
                default_idx = i + 1
        self.adapter_combo.setCurrentIndex(default_idx)
        self.adapter_combo.blockSignals(False)
        self._on_adapter_changed()

    def _on_adapter_changed(self, *_):
        data = self.adapter_combo.currentData()
        if data and data.get("cidr"):
            self.cidr_edit.setText(data["cidr"])
        elif data and data.get("ip") and not self.cidr_edit.text().strip():
            self.cidr_edit.setText(data["ip"] + "/24")

    # ================= 扫描 =================
    def start_scan(self):
        cidr = self.cidr_edit.text().strip()
        if not cidr:
            warn_box(self, "提示", "请填写要扫描的网段，或选择一块网卡自动填充")
            return
        self.scan_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self._devices.clear()
        self._row_index.clear()
        self.device_table.setRowCount(0)
        self.risk_label.setText("扫描中…")
        self.risk_label.setStyleSheet(TOOL_STATUS_INFO)
        self.status_bar.setStyleSheet(TOOL_STATUS_INFO)
        self.status_bar.setText(f"正在扫描 {cidr}：多线程 ping 激发 ARP 解析…")
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setFormat("准备中")


        self.worker = ArpScanWorker(cidr=cidr, workers=self.workers_spin.value(),
                                    nbt_enabled=self.nbt_check.isChecked())
        self.worker.progress.connect(self.on_progress)
        self.worker.device_found.connect(self.on_device)
        self.worker.finished_ok.connect(self.on_finished)
        self.worker.failed.connect(self.on_failed)
        self.worker.start()

    def stop_scan(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.status_bar.setStyleSheet(TOOL_STATUS_WARNING)
            self.status_bar.setText("⚠ 已请求停止，等待收尾（已发现的设备会保留）…")

    def on_progress(self, phase, done, total):
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(done)
            if phase == "ping":
                self.progress.setFormat(f"ping 激发 %v/%m")
            else:
                self.progress.setFormat(f"主机名解析 %v/%m")

    def on_device(self, device):
        """实时逐台填充（ip+mac 查重 upsert，nbt/名册回填后重复信号更新同一行）"""
        key = (device.get("ip", ""), device.get("mac", ""))
        self._devices[key] = device
        if key in self._row_index:
            r = self._row_index[key]
        else:
            r = self.device_table.rowCount()
            self.device_table.insertRow(r)
            self._row_index[key] = r
        name_txt = device.get("name") or "—"
        tags_txt = " / ".join(device.get("tags", [])) or "—"
        vals = [device.get("ip", ""), device.get("mac", ""), device.get("vendor") or "—",
                device.get("hostname") or "—", name_txt, tags_txt,
                device.get("arp_type") or "—"]
        for c, v in enumerate(vals):
            it = QTableWidgetItem(v)
            if c == 5 and "⚠" in tags_txt:
                it.setForeground(QColor("#f87171"))
            elif c == 4 and device.get("name"):
                it.setForeground(QColor("#4ade80"))
            self.device_table.setItem(r, c, it)

    def on_finished(self, result):
        self.scan_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._reorder_by_ip()
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.progress.setFormat("完成")
        stats = result.get("stats", {})
        n = stats.get("total", len(self._devices))
        prefix = "已停止，" if result.get("stopped") else ""
        extra = []
        if stats.get("virtual"):
            extra.append(f"虚拟化设备 {stats['virtual']}")
        if stats.get("random_mac"):
            extra.append(f"随机化 MAC {stats['random_mac']}")
        extra_txt = f"（{'、'.join(extra)}）" if extra else ""
        self.status_bar.setStyleSheet(TOOL_STATUS_SUCCESS)
        self.status_bar.setText(f"✅ {prefix}扫描完成：发现 {n} 台活动设备{extra_txt}"
                                f"（网段 {result.get('cidr', '')}，网关 {result.get('gateway') or '未识别'}）")
        risks = result.get("risks", [])
        self._render_risks(risks)

    def _reorder_by_ip(self):
        """扫描完成后按 IP 数值序重排表格行（实时填充阶段按发现顺序，先快后整）"""
        if not self._devices:
            return
        try:
            keys = sorted(self._devices.keys(),
                          key=lambda k: tuple(int(x) for x in k[0].split(".") if x.isdigit()))
        except Exception:
            return
        self._row_index = {}
        self.device_table.setRowCount(len(keys))
        for r, key in enumerate(keys):
            self._row_index[key] = r
            self.on_device(self._devices[key])

    def on_failed(self, msg):
        self.scan_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setFormat("")
        self.status_bar.setStyleSheet(TOOL_STATUS_ERROR)
        self.status_bar.setText(f"❌ {msg}")
        self.risk_label.setText("扫描失败")
        self.risk_label.setStyleSheet(TOOL_STATUS_ERROR)

    def _render_risks(self, risks):
        if not risks:
            self.risk_label.setText("✅ 未发现虚拟 IP 冲突/ARP 欺骗迹象"
                                    "（每次扫描会自动记录网关 MAC 作为下次比对基线）")
            self.risk_label.setStyleSheet(TOOL_STATUS_SUCCESS)
            return
        colors = {"danger": "#f87171", "warning": "#fbbf24", "info": "#8ab4ff"}
        parts = []
        for k in risks:
            c = colors.get(k.get("level"), "#8ab4ff")
            parts.append(f"<span style='color:{c};'>{k.get('text', '')}</span>")
        self.risk_label.setText("风险提示：" + "<br>· " + "<br>· ".join(parts))
        if any(k.get("level") == "danger" for k in risks):
            self.risk_label.setStyleSheet(TOOL_STATUS_ERROR)
        else:
            self.risk_label.setStyleSheet(TOOL_STATUS_WARNING)

    # ================= 右键菜单 =================
    def _ctx_menu(self, pos):
        row = self.device_table.rowAt(pos.y())
        if row < 0:
            return
        ip_it = self.device_table.item(row, 0)
        mac_it = self.device_table.item(row, 1)
        if not ip_it:
            return
        ip = ip_it.text()
        mac = mac_it.text() if mac_it else ""
        menu = QMenu(self)
        act_reg = QAction("📝 登记姓名（预填名册行）", menu)
        act_ping = QAction(f"🔔 Ping 此 IP", menu)
        act_copy_ip = QAction("复制 IP", menu)
        act_copy_mac = QAction("复制 MAC", menu)
        act_csv = QAction("📄 导出设备清单 CSV", menu)
        for a in (act_reg, act_ping, act_copy_ip, act_copy_mac, act_csv):
            menu.addAction(a)
        chosen = menu.exec_(self.device_table.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if chosen == act_reg:
            self.ros_mac_edit.setText("" if mac == "—" else mac)
            self.ros_ip_edit.setText(ip)
            self.ros_name_edit.setFocus()
            self.roster_hint.setText("已预填，请补姓名后点「登记」。")
            self.roster_hint.setStyleSheet(TOOL_STATUS_INFO)
        elif chosen == act_ping:
            self._ping_one(ip)
        elif chosen == act_copy_ip:
            from PyQt5.QtWidgets import QApplication
            QApplication.clipboard().setText(ip)
        elif chosen == act_copy_mac:
            from PyQt5.QtWidgets import QApplication
            QApplication.clipboard().setText("" if mac == "—" else mac)
        elif chosen == act_csv:
            self.export_csv()

    def _ping_one(self, ip):
        from gui.tools.ping_tool import PingWorker

        self.status_bar.setStyleSheet(TOOL_STATUS_INFO)
        self.status_bar.setText(f"正在 Ping {ip} …")

        worker = PingWorker(ip, 4, 1)

        def _on_result(result):
            if result.get("success"):
                avg = result.get("avg_time", 0)
                self.status_bar.setStyleSheet(TOOL_STATUS_SUCCESS)
                self.status_bar.setText(f"✅ {ip} 可达，平均延迟 {avg:.1f}ms")
            else:
                self.status_bar.setStyleSheet(TOOL_STATUS_ERROR)
                err = result.get("error") or "不可达"
                self.status_bar.setText(f"❌ {ip} {err}")

        worker.result_ready.connect(_on_result)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def export_csv(self):
        if self.device_table.rowCount() == 0:
            warn_box(self, "提示", "当前没有可导出的设备清单")
            return
        path, _f = QFileDialog.getSaveFileName(
            self, "导出设备清单", "arp_devices.csv", "CSV 文件 (*.csv)")
        if not path:
            return
        try:
            import csv
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                wr = csv.writer(f)
                headers = [self.device_table.horizontalHeaderItem(c).text()
                           for c in range(self.device_table.columnCount())]
                wr.writerow(headers)
                for r in range(self.device_table.rowCount()):
                    wr.writerow([(self.device_table.item(r, c).text() if self.device_table.item(r, c) else "")
                                 for c in range(self.device_table.columnCount())])
            self.status_bar.setStyleSheet(TOOL_STATUS_SUCCESS)
            self.status_bar.setText(f"✅ 已导出 {self.device_table.rowCount()} 条到 {path}")
        except OSError as e:
            warn_box(self, "导出失败", str(e))

    # ================= 名册 =================
    def add_roster(self):
        mac = self.ros_mac_edit.text().strip()
        ip = self.ros_ip_edit.text().strip()
        name = self.ros_name_edit.text().strip()
        note = self.ros_note_edit.text().strip()
        r = arp_scan.upsert_roster(mac=mac, ip=ip, name=name, note=note)
        if not r.get("ok"):
            self.roster_hint.setStyleSheet(TOOL_STATUS_ERROR)
            self.roster_hint.setText(f"⚠ {r.get('error', '登记失败')}")
            return
        self.roster_hint.setStyleSheet(TOOL_STATUS_SUCCESS)
        self.roster_hint.setText("✅ 已" + ("更新" if r.get("updated") else "登记")
                                 + "，下次扫描自动回填姓名列；也可右键设备行立即刷新。")
        self.ros_mac_edit.clear()
        self.ros_ip_edit.clear()
        self.ros_name_edit.clear()
        self.ros_note_edit.clear()
        self._refresh_roster()
        # 已展示的设备表就地回填（不用重扫）
        key = None
        cm = arp_scan.clean_mac(mac)
        for k in self._devices:
            if (cm and k[1] == cm) or (not cm and k[0] == ip):
                key = k
                break
        if key and key in self._row_index:
            self._devices[key]["name"] = name or self._devices[key]["name"]
            self._devices[key]["note"] = note or self._devices[key]["note"]
            r_i = self._row_index[key]
            it = QTableWidgetItem(self._devices[key]["name"] or "—")
            if name:
                it.setForeground(QColor("#4ade80"))
            self.device_table.setItem(r_i, 4, it)

    def _refresh_roster(self):
        entries = arp_scan.load_roster().get("entries", [])
        self.roster_table.setRowCount(len(entries))
        for r, e in enumerate(entries):
            self.roster_table.setItem(r, 0, QTableWidgetItem(e.get("name", "")))
            self.roster_table.setItem(r, 1, QTableWidgetItem(e.get("mac", "") or "—"))
            self.roster_table.setItem(r, 2, QTableWidgetItem(e.get("ip", "") or "—"))
            self.roster_table.setItem(r, 3, QTableWidgetItem(e.get("note", "") or "—"))
            del_btn = QPushButton("删除")
            del_btn.setStyleSheet(
                "QPushButton { padding: 3px 10px; font-size: 12px; border: none;"
                " border-radius: 8px; background: transparent; color: #FA5151; }"
                "QPushButton:hover { background: #FDEEEE; }")
            del_btn.setCursor(Qt.PointingHandCursor)
            del_btn.clicked.connect(
                lambda _=False, mac_e=e.get("mac", ""), ip_e=e.get("ip", ""): self._del_roster(mac_e, ip_e))
            self.roster_table.setCellWidget(r, 4, del_btn)
        if not entries:
            self.roster_table.setRowCount(0)

    def _del_roster(self, mac, ip):
        arp_scan.remove_roster(mac=mac, ip=ip)
        self._refresh_roster()
        self.roster_hint.setStyleSheet(TOOL_STATUS_INFO)
        self.roster_hint.setText("已删除名册条目。")

    # 资源收尾：仅整窗关闭/隐藏时协作式停止（工具箱内切页不打断扫描）；
    # QThread 子类 + stop_flag + PingTool 子进程注册表，线程自然收尾不 terminate
    def hideEvent(self, event):
        try:
            win_visible = self.window().isVisible()
        except Exception:
            win_visible = True
        if self.worker and self.worker.isRunning() and not win_visible:
            self.worker.stop()
        super().hideEvent(event)
