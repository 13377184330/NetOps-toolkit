#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Console 只读可视化标签页（二开新增）
插 Console 线 → 扫描串口 → 连接（自动识别厂商）→ 只读抓配置 → 分层可视化树
红线：全程只读，连接器模块层面强制白名单，本页无任何写入口
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
                             QGroupBox, QComboBox, QPushButton, QLabel,
                             QTreeWidget, QTreeWidgetItem, QTextEdit,
                             QMessageBox, QProgressBar, QSpinBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from modules import console_reader as cr
from modules import config_visualizer as cv
from modules.device_connector import VENDOR_LABELS


# ---------------------------------------------------------------- 后台读取线程
class _ConsoleWorker(QThread):
    """Console 读取在后台线程执行，避免阻塞 UI"""
    log = pyqtSignal(str)
    progress = pyqtSignal(int, str)   # percent, message
    done = pyqtSignal(bool, dict)     # ok, {vendor, version, config, parsed}

    def __init__(self, port, baud, parent=None):
        super().__init__(parent)
        self.port = port
        self.baud = baud

    def run(self):
        result = {"vendor": None, "version": "", "config": "", "parsed": None}
        try:
            self.log.emit(f"[Console] 打开 {self.port} @ {self.baud} …")
            with cr.ConsoleReader(self.port, self.baud) as reader:
                self.progress.emit(15, "已连接，识别设备厂商…")
                vendor = reader.detect()
                result["vendor"] = vendor
                if not vendor:
                    self.log.emit("[Console] 未能识别厂商（设备无回显，请检查 Console 线与波特率）")
                    self.done.emit(False, result)
                    return
                self.log.emit(f"[Console] 识别厂商：{VENDOR_LABELS.get(vendor, vendor)}")
                self.progress.emit(35, "读取设备版本信息…")
                result["version"] = reader.read_version()
                self.progress.emit(60, "抓取 running-configuration（只读）…")

                def on_rcv(n):
                    self.log.emit(f"[Console] 已接收 {n} 字节…")

                result["config"] = reader.read_config(progress_cb=on_rcv)
                self.progress.emit(90, "解析配置…")
                result["parsed"] = cv.parse_config(result["config"])
                self.progress.emit(100, "完成")
                self.log.emit(f"[Console] 抓取完成：{len(result['config'])} 字节配置")
                self.done.emit(True, result)
        except PermissionError as e:
            self.log.emit(f"[红线拦截] {e}")
            self.done.emit(False, result)
        except Exception as e:
            self.log.emit(f"[Console] 错误：{type(e).__name__}: {e}")
            self.done.emit(False, result)


# ---------------------------------------------------------------- 主面板
class ConsoleVizTab(QWidget):
    """Console 只读可视化面板"""

    def __init__(self):
        super().__init__()
        self._worker = None
        self.initUI()

    # ---------------- UI ----------------
    def initUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 顶部说明条（红线声明）
        banner = QLabel("🔒 只读模式：本页面仅发送 display/show 查询命令，"
                        "任何写操作（system-view/save/undo 等）在连接层被强制拦截")
        banner.setStyleSheet("""
            background: #FFF7E8; color: #B26A00;
            border: 1px solid #FFD591; border-radius: 10px;
            padding: 9px 14px; font-size: 13px;
        """)
        banner.setWordWrap(True)
        layout.addWidget(banner)

        # 连接卡
        conn_group = QGroupBox("Console 连接")
        conn_form = QHBoxLayout()
        conn_form.setSpacing(10)

        self.port_combo = QComboBox()
        self.refresh_ports()

        refresh_btn = QPushButton("↻ 刷新串口")
        refresh_btn.setObjectName("secondaryButton")
        refresh_btn.clicked.connect(self.refresh_ports)

        self.baud_spin = QSpinBox()
        self.baud_spin.setRange(1200, 115200)
        self.baud_spin.setValue(9600)

        self.connect_btn = QPushButton("🔌 连接并读取配置")
        self.connect_btn.setObjectName("primaryButton")
        self.connect_btn.clicked.connect(self.start_read)

        conn_form.addWidget(QLabel("串口:"))
        conn_form.addWidget(self.port_combo, 1)
        conn_form.addWidget(QLabel("波特率:"))
        conn_form.addWidget(self.baud_spin)
        conn_form.addWidget(refresh_btn)
        conn_form.addWidget(self.connect_btn)
        conn_group.setLayout(conn_form)
        layout.addWidget(conn_group)

        # 进度条
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)
        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)
        self.progress_label.setStyleSheet("color: #7A8699; font-size: 12px;")
        layout.addWidget(self.progress_label)

        # 可视化区（树 + 配置原文 双栏）
        viz_splitter_layout = QHBoxLayout()
        viz_splitter_layout.setSpacing(10)

        # 左：信息树
        tree_group = QGroupBox("配置概览（分层）")
        tree_lay = QVBoxLayout(tree_group)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["项目", "值/详情"])
        self.tree.setColumnWidth(0, 260)
        self.tree.setAlternatingRowColors(True)
        tree_lay.addWidget(self.tree)
        viz_splitter_layout.addWidget(tree_group, 3)

        # 右：原文 + 统计
        right_group = QGroupBox("配置原文 / 采集日志")
        right_lay = QVBoxLayout(right_group)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("连接信息与采集日志显示在这里")
        self.log_view.setMaximumHeight(140)
        right_lay.addWidget(self.log_view)

        self.raw_view = QTextEdit()
        self.raw_view.setReadOnly(True)
        self.raw_view.setPlaceholderText("running-configuration 原文显示在这里")
        right_lay.addWidget(self.raw_view, 1)

        save_btn = QPushButton("💾 保存配置文件（.cfg）")
        save_btn.setObjectName("secondaryButton")
        save_btn.clicked.connect(self.save_config)
        right_lay.addWidget(save_btn)

        viz_splitter_layout.addWidget(right_group, 2)

        layout.addLayout(viz_splitter_layout, 1)

        self._last_result = None
        self._raw_config = ""

    # ---------------- 逻辑 ----------------
    def refresh_ports(self):
        self.port_combo.clear()
        ports = cr.list_console_ports()
        if ports:
            for p, desc in ports:
                self.port_combo.addItem(f"{p} — {desc}", p)
        else:
            self.port_combo.addItem("（未检测到串口）", "")

    def log(self, text):
        self.log_view.append(text)

    def start_read(self):
        port = self.port_combo.currentData()
        if not port:
            QMessageBox.warning(self, "提示", "未检测到串口：请插入 Console 线后点「刷新串口」\n"
                                "（首次使用需安装 USB 转串口驱动，如 FTDI/CH340）")
            return
        self.connect_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress_label.setVisible(True)
        self.progress.setValue(5)
        self.progress_label.setText("正在连接…")
        self._worker = _ConsoleWorker(port, self.baud_spin.value(), self)
        self._worker.log.connect(self.log)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _on_progress(self, pct, msg):
        self.progress.setValue(pct)
        self.progress_label.setText(msg)

    def _on_done(self, ok, result):
        self.connect_btn.setEnabled(True)
        self.progress.setVisible(False)
        self.progress_label.setVisible(False)
        if not ok:
            return
        self._last_result = result
        self._raw_config = result["config"]
        self.raw_view.setPlainText(result["config"])
        self._build_tree(result)

    # ---------------- 可视化树构建 ----------------
    def _build_tree(self, result: dict):
        self.tree.clear()
        parsed = result["parsed"]
        vendor = result.get("vendor") or "unknown"

        # 基本信息
        basic = QTreeWidgetItem(["基本信息", ""])
        for k, v in parsed["basic"].items():
            QTreeWidgetItem(basic, [k, str(v)])
        QTreeWidgetItem(basic, ["厂商", VENDOR_LABELS.get(vendor, vendor)])
        # 统计
        stats = parsed["stats"]
        for k, v in stats.items():
            QTreeWidgetItem(basic, [k, str(v)])
        self.tree.addTopLevelItem(basic)

        # 接口
        ifaces_root = QTreeWidgetItem([
            "接口", f"{len(parsed['interfaces'])} 个"])
        for itf in parsed["interfaces"]:
            detail_txt = "  ".join(f"{k}:{v}" for k, v in itf["detail"].items()) if itf["detail"] else "（默认配置）"
            node = QTreeWidgetItem([itf["name"], f"{itf['kind']}  {detail_txt}"])
            # 配置行明细
            for ln in itf["lines"]:
                QTreeWidgetItem(node, ["", ln.strip()])
            ifaces_root.addChild(node)
        self.tree.addTopLevelItem(ifaces_root)
        self.tree.expandItem(ifaces_root) if len(parsed["interfaces"]) <= 8 else None

        # VLAN
        vlans_root = QTreeWidgetItem(["VLAN", f"{len(parsed['vlans'])} 个"])
        for v in parsed["vlans"]:
            QTreeWidgetItem(vlans_root, [f"VLAN {v['id']}", v["name"]])
        self.tree.addTopLevelItem(vlans_root)

        # 路由
        routes_root = QTreeWidgetItem(["路由", f"{len(parsed['routes'])} 条静态路由"])
        for r in parsed["routes"]:
            QTreeWidgetItem(routes_root, [r["目的网段"], f"下一跳 {r['下一跳']}"])
        self.tree.addTopLevelItem(routes_root)

        # 安全
        sec_root = QTreeWidgetItem(["安全", f"{len(parsed['security'])} 项"])
        for s in parsed["security"]:
            node = QTreeWidgetItem(sec_root, [s, ""])
        self.tree.addTopLevelItem(sec_root)

        self.tree.expandItem(basic)

    # ---------------- 保存 ----------------
    def save_config(self):
        if not self._raw_config:
            QMessageBox.information(self, "提示", "还没有抓取到配置，请先连接读取")
            return
        from PyQt5.QtWidgets import QFileDialog
        default_name = f"console_{self._last_result.get('vendor', 'device')}_running.cfg"
        path, _ = QFileDialog.getSaveFileName(self, "保存配置", default_name,
                                              "配置文件 (*.cfg);;文本 (*.txt);;所有文件 (*)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._raw_config)
            QMessageBox.information(self, "成功", f"配置已保存到：\n{path}")
