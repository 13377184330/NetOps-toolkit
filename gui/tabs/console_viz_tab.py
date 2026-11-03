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
from PyQt5.QtGui import QColor, QBrush
from PyQt5.QtCore import Qt, QThread, pyqtSignal, pyqtSlot

from modules import console_reader as cr
from modules import config_visualizer as cv
from modules.device_connector import VENDOR_LABELS


# 识别厂商 → 设备品牌下拉索引映射（右上角厂商联动）
VENDOR_TO_BRAND_INDEX = {
    "huawei": 0, "h3c": 1, "ruijie": 2, "maipu": 3, "cisco": 4,
}


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
        result = {"vendor": None, "version": "", "config": "", "parsed": None, "lldp": ""}
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
                self.progress.emit(30, "读取设备版本信息…")
                result["version"] = reader.read_version()
                self.progress.emit(55, "抓取 running-configuration…")

                def on_rcv(n):
                    self.log.emit(f"[Console] 已接收 {n} 字节…")

                result["config"] = reader.read_config(progress_cb=on_rcv)
                self.progress.emit(80, "解析配置…")
                result["parsed"] = cv.parse_config(result["config"])
                self.progress.emit(88, "采集 LLDP 邻居（拓扑用）…")
                try:
                    result["lldp"] = reader.read_lldp()
                except Exception as e:
                    self.log.emit(f"[Console] LLDP 采集跳过：{e}")
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
class _DeployWorker(QThread):
    """配置下发后台线程（Console 写模式）"""
    log = pyqtSignal(str)
    done = pyqtSignal(bool, str)

    def __init__(self, port, baud, lines, parent=None):
        super().__init__(parent)
        self.port = port
        self.baud = baud
        self.lines = lines

    def run(self):
        try:
            with cr.ConsoleReader(self.port, self.baud, allow_write=True) as reader:
                reader.detect()
                self.log.emit(f"[下发] 已连接 {self.port}，开始下发 {len(self.lines)} 条命令…")
                steps = reader.send_config(self.lines, save=False)
                errs = [c for c, out in steps if any(k in out for k in ("% Unrecognized", "% Wrong", "Error:", "Incomplete"))]
                if errs:
                    self.log.emit(f"[下发] 注意：{len(errs)} 条命令可能有语法问题：{errs[:3]}")
                self.done.emit(True, f"已下发 {len(self.lines)} 条命令（未存盘）。"
                                     f"\n有问题的命令：{len(errs)} 条" + (f"\n{errs[:3]}" if errs else ""))
        except PermissionError as e:
            self.done.emit(False, str(e))
        except Exception as e:
            self.done.emit(False, f"{type(e).__name__}: {e}")


class ConsoleVizTab(QWidget):
    """Console 只读可视化面板"""

    def __init__(self):
        super().__init__()
        self._worker = None
        self.initUI()

    # ---------------- UI ----------------
    def initUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(14)

        # 连接卡（控件间放宽间隔 + 弹性分配，不挤左边）
        conn_group = QGroupBox("Console 连接")
        conn_form = QHBoxLayout()
        conn_form.setSpacing(16)
        conn_form.setContentsMargins(16, 8, 16, 8)

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
        conn_form.addWidget(self.port_combo, 2)
        conn_form.addStretch(1)
        conn_form.addWidget(QLabel("波特率:"))
        conn_form.addWidget(self.baud_spin)
        conn_form.addStretch(1)
        conn_form.addWidget(refresh_btn)
        conn_form.addStretch(2)
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

        # ===== 单栏到底：配置概览 → 健康度 → 采集日志 → 配置原文（上下排列，不左右拉）=====
        tree_group = QGroupBox("配置概览（分层）")
        tree_group.setMinimumHeight(260)
        tree_lay = QVBoxLayout(tree_group)
        tree_lay.setContentsMargins(12, 24, 12, 12)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["项目", "值/详情"])
        self.tree.setColumnWidth(0, 260)
        self.tree.setAlternatingRowColors(True)
        self.tree.setStyleSheet("QTreeWidget::item { padding: 8px 4px; }")  # 行高充足不压抑
        tree_lay.addWidget(self.tree)
        layout.addWidget(tree_group, 4)

        # 健康度卡片（横向内部布局：左评分、右风险列表——省高度装下更多内容）
        health_group = QGroupBox("配置健康度")
        health_group.setMinimumHeight(170)
        health_lay = QHBoxLayout(health_group)
        health_lay.setContentsMargins(16, 24, 16, 12)
        health_lay.setSpacing(18)

        score_box = QVBoxLayout()
        score_box.setSpacing(2)
        self.health_score = QLabel("--")
        self.health_score.setAlignment(Qt.AlignCenter)
        self.health_score.setStyleSheet("font-size: 48px; font-weight: bold; color: #9AA7B8;")
        score_box.addWidget(self.health_score)
        self.health_level = QLabel("未体检")
        self.health_level.setAlignment(Qt.AlignCenter)
        self.health_level.setWordWrap(True)
        self.health_level.setStyleSheet("font-size: 12px; color: #7A8699;")
        score_box.addWidget(self.health_level)
        score_box.addStretch()
        health_lay.addLayout(score_box, 1)

        self.health_list = QTreeWidget()
        self.health_list.setHeaderLabels(["风险项", "等级"])
        self.health_list.setColumnWidth(0, 260)
        self.health_list.setAlternatingRowColors(True)
        self.health_list.setStyleSheet("QTreeWidget::item { padding: 6px 3px; }")
        health_lay.addWidget(self.health_list, 3)
        layout.addWidget(health_group, 2)

        # 采集日志（固定较小高度：只是操作记录）
        log_group = QGroupBox("采集日志")
        log_group.setMaximumHeight(150)
        log_lay = QVBoxLayout(log_group)
        log_lay.setContentsMargins(12, 24, 12, 12)
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("连接信息与采集日志显示在这里")
        log_lay.addWidget(self.log_view)
        layout.addWidget(log_group)

        # 配置原文（可编辑 + 下发闭环：读到的东西能改、能回写）
        raw_group = QGroupBox("配置原文（可编辑 → 下发到设备）")
        raw_group.setMinimumHeight(240)
        raw_lay = QVBoxLayout(raw_group)
        raw_lay.setContentsMargins(12, 24, 12, 12)
        raw_lay.setSpacing(8)
        self.raw_view = QTextEdit()
        self.raw_view.setReadOnly(False)   # 可编辑：改完可直接下发
        self.raw_view.setPlaceholderText(
            "配置原文显示在这里（可直接编辑）——改完点下方「下发到设备」写回交换机")
        raw_lay.addWidget(self.raw_view, 1)

        raw_btn_row = QHBoxLayout()
        raw_btn_row.setSpacing(8)
        self.save_btn = QPushButton("💾 保存配置文件（.cfg）")
        self.save_btn.setObjectName("secondaryButton")
        self.save_btn.clicked.connect(self.save_config)
        self.deploy_btn_c = QPushButton("⤴ 下发到设备")
        self.deploy_btn_c.setObjectName("primaryButton")
        self.deploy_btn_c.setToolTip("把上方编辑后的配置命令下发到当前 Console 连接的交换机（会先弹确认）")
        self.deploy_btn_c.clicked.connect(self.deploy_to_device)
        self.reset_btn = QPushButton("↺ 还原原文")
        self.reset_btn.setObjectName("ghostButton")
        self.reset_btn.setToolTip("丢弃编辑，恢复为最近一次采集到的原文")
        self.reset_btn.clicked.connect(
            lambda: self.raw_view.setPlainText(self._raw_config))
        raw_btn_row.addWidget(self.reset_btn)
        raw_btn_row.addStretch()
        raw_btn_row.addWidget(self.save_btn)
        raw_btn_row.addWidget(self.deploy_btn_c)
        raw_lay.addLayout(raw_btn_row)
        layout.addWidget(raw_group, 5)

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
        self._sync_brand_combo(result.get("vendor"))
        self._sync_topology(result)
        self._build_health(result)

    def _build_health(self, result):
        """配置健康度体检（本地规则分析，不发任何命令）"""
        try:
            from modules.health_checker import check_health
            res = check_health(result.get("config", ""), result.get("vendor") or "h3c")
            score = res["score"]
            level = res["level"]
            color = {"优秀": "#34C759", "良好": "#0089FF",
                     "需改进": "#FA9D3B", "高风险": "#FA5151"}.get(level, "#9AA7B8")
            self.health_score.setText(str(score))
            self.health_score.setStyleSheet(f"font-size: 40px; font-weight: bold; color: {color};")
            st = res["stats"]
            self.health_level.setText(
                f"{level}　严重 {st['严重']} · 警告 {st['警告']} · 提示 {st['提示']} · 通过 {st['通过']}")
            self.health_level.setStyleSheet(f"font-size: 12px; color: {color};")

            self.health_list.clear()
            level_color = {"严重": "#FA5151", "警告": "#FA9D3B", "提示": "#7A8699", "通过": "#34C759"}
            order = {"严重": 0, "警告": 1, "提示": 2, "通过": 3}
            for it in sorted(res["items"], key=lambda x: order.get(x["level"], 9)):
                if it["level"] == "通过":
                    continue
                node = QTreeWidgetItem([f"{it['domain']} · {it['item']}", it["level"]])
                node.setForeground(1, QBrush(QColor(level_color.get(it["level"], "#7A8699"))))
                node.setToolTip(0, it["advice"] or it["baseline"])
                self.health_list.addTopLevelItem(node)
            if self.health_list.topLevelItemCount() == 0:
                QTreeWidgetItem(self.health_list, ["全部检查项通过 ✓", "通过"])
            self.log(f"[体检] 健康度评分 {score}（{level}）")
        except Exception as e:
            self.log(f"[体检] 失败：{e}")

    def _sync_topology(self, result):
        """Console 采集的 LLDP 邻居 → 自动填充「网络拓扑」页"""
        try:
            main = self.window()
            topo = getattr(main, "tabs", {}).get("topology") if hasattr(main, "tabs") else None
            if topo is None:
                return
            lldp_text = result.get("lldp") or ""
            neighbors = cv.parse_lldp(lldp_text)
            parsed_basic = result.get("parsed", {}).get("basic", {})
            local_name = parsed_basic.get("主机名", "")
            local_meta = {
                "版本": parsed_basic.get("软件版本", ""),
                "厂商": VENDOR_LABELS.get(result.get("vendor") or "", ""),
            }
            topo.load_topology(local_name, local_meta, neighbors)
            self.log(f"[拓扑] 已更新网络拓扑：发现 {len(neighbors)} 台 LLDP 邻居")
        except Exception as e:
            self.log(f"[拓扑] 更新失败：{e}")

    def _sync_brand_combo(self, vendor):
        """厂商联动：Console 识别出厂商后，自动同步右上角设备品牌下拉
        （可视化运维逻辑：设备自己“告诉”工具它是什么，不用人手选）"""
        if not vendor:
            return
        main = self.window()
        combo = getattr(main, "device_combo", None)
        if combo is None:
            return
        idx = VENDOR_TO_BRAND_INDEX.get(vendor)
        if idx is not None and idx < combo.count():
            if combo.currentIndex() != idx:
                combo.blockSignals(True)   # 防重入：不触发 on_device_changed 清空表单
                combo.setCurrentIndex(idx)
                combo.blockSignals(False)
                self.log(f"[联动] 已自动切换设备品牌：{VENDOR_LABELS.get(vendor, vendor)}（右侧配置页语法已同步）")

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

    # ---------------- 配置下发（闭环） ----------------
    def deploy_to_device(self):
        """把编辑后的配置下发回当前 Console 交换机（双重确认 + 自动备份原文）"""
        port = self.port_combo.currentData()
        if not port:
            QMessageBox.warning(self, "提示", "未检测到串口，请先连接 Console")
            return
        text = self.raw_view.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "提示", "配置内容为空")
            return

        lines = [l.rstrip() for l in text.splitlines()
                 if l.strip() and not l.strip().startswith("#")
                 and not l.strip().startswith("<")]  # 去掉提示符残留行
        if not lines:
            QMessageBox.warning(self, "提示", "没有可下发的配置命令行")
            return

        preview = "\n".join(lines[:8]) + ("\n…" if len(lines) > 8 else "")
        ret = QMessageBox.question(
            self, "确认下发配置",
            f"即将向 Console 交换机（{port}）下发 {len(lines)} 条配置命令：\n\n{preview}\n\n"
            "下发会立即改变设备运行配置（不自动存盘）。\n"
            "建议先「保存配置文件」备份当前配置。继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ret != QMessageBox.Yes:
            return

        self.deploy_btn_c.setEnabled(False)
        self.progress.setVisible(True)
        self.progress_label.setVisible(True)
        self.progress.setValue(10)
        self.progress_label.setText("正在下发配置…")
        self._worker = _DeployWorker(port, self.baud_spin.value(), lines, self)
        self._worker.log.connect(self.log)
        self._worker.done.connect(self._on_deploy_done)
        self._worker.start()

    def _on_deploy_done(self, ok, msg):
        self.deploy_btn_c.setEnabled(True)
        self.progress.setVisible(False)
        self.progress_label.setVisible(False)
        if ok:
            QMessageBox.information(self, "下发完成", msg)
            # 下发后自动重新采集，展示设备最新配置
            if self.port_combo.currentData():
                self.start_read()
        else:
            QMessageBox.critical(self, "下发失败", msg)
