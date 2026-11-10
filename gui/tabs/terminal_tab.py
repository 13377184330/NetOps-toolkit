#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
自由终端标签页（二开新增）
Console 交互式终端：像 SecureCRT 一样直接敲命令、实时回显、↑↓ 翻历史。

只读红线不破：
- 采集闭环（Console 可视化页）的白名单一个字不动；
- 本页默认「只读模式」，发送前走同一套 check_read_only 白名单校验；
- 写命令须显式开启「写模式」（危险确认弹窗、回车默认落在否）；
  断开连接时写模式自动复位为只读。
- 多行配置批量下发仍走 Console 可视化页的下发闭环（本页是行式交互）。
"""

import queue
import time

import serial
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QEvent
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
                             QComboBox, QPushButton, QLabel, QTextEdit,
                             QSpinBox, QLineEdit, QCheckBox)

from gui.dialogs.base import question_box
from gui.widget_utils import page_header
from modules import console_reader as cr
from modules.device_connector import VENDOR_LABELS

# 终端区配色：与主窗口配置预览同源（浅色即源语言，深色主题由 theme 引擎翻译；
# 深色终端区在浅/深两主题下都保持深色——SecureCRT/Xshell 惯例）
_TERM_QSS = """
    font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
    font-size: 13px;
    background: #1E2430;
    border: 1px solid #2C3444;
    border-radius: 16px;
    padding: 12px;
    color: #C8D3E8;
    selection-background-color: #0089FF;
    selection-color: #ffffff;
"""

# 写模式警示横幅（浅色源语言，danger 系 token）
_BANNER_QSS = (
    "background: #FDEEEE; color: #FA5151; border-radius: 8px;"
    " padding: 6px 12px; font-size: 12px; font-weight: bold;"
)

# 输入行敲入被拦截命令时的红边闪烁（非法参数即时红边先例）
_INPUT_ALERT_QSS = "QLineEdit { border: 1px solid #FA5151; border-radius: 8px; }"


# ---------------------------------------------------------------- 后台线程
class _TermWorker(QThread):
    """终端 IO 线程：串口的读/写全部集中在本线程，主线程只通过队列投递命令。
    逐字符发送（15ms 间隔，与采集闭环同策略，防设备行编辑器吞字符）；
    持续读串口 → text 信号回显；遇 ---- More ---- 自动发空格翻页（可关）。"""
    text = pyqtSignal(str)          # 设备回显增量
    state = pyqtSignal(bool, str)   # (已连接, 厂商或失败原因)

    def __init__(self, port, baud, parent=None):
        super().__init__(parent)
        self.port = port
        self.baud = baud
        self._queue = queue.Queue()
        self._stop = False
        self.auto_more = True       # 主线程直接切换（bool 读写原子，安全）

    def send(self, cmd: str):
        self._queue.put(cmd)

    def request_stop(self):
        self._stop = True

    def run(self):
        try:
            # write_timeout：USB 串口适配器驱动卡死时 write() 会无限阻塞，
            # 写超时把卡死变成可报错的异常（采集闭环真机实测教训）
            ser = serial.Serial(self.port, self.baud, bytesize=8, parity="N",
                                stopbits=1, timeout=0.05, write_timeout=5)
        except Exception as e:
            self.state.emit(False, f"连接失败：{e}")
            return
        try:
            ser.reset_input_buffer()
            # 提示符同步 + 厂商识别（detect_vendor 只发回车/display version，只读安全）
            try:
                vendor = cr.detect_vendor(ser)
            except Exception:
                vendor = None
            self.state.emit(True, vendor or "")
            try:
                self._loop(ser)
            except Exception as e:
                # 拔线/驱动卡死等 IO 异常：必须发 state 复位 UI，
                # 否则页面永远停在「已连接」
                self.state.emit(False, f"连接中断：{e}")
                return
        finally:
            try:
                ser.close()
            except Exception:
                pass
        self.state.emit(False, "已断开")

    def _loop(self, ser):
        tail = ""
        while not self._stop:
            # 1) 发送队列（非阻塞）
            try:
                cmd = self._queue.get_nowait()
            except queue.Empty:
                cmd = None
            if cmd is not None:
                for ch in cmd:
                    ser.write(ch.encode("utf-8"))
                    time.sleep(0.015)
                ser.write(b"\r\n")
                time.sleep(0.2)
                tail = ""
            # 2) 读回显
            n = ser.in_waiting
            if n:
                text = ser.read(n).decode("utf-8", errors="replace")
                self.text.emit(text)
                tail = (tail + text)[-60:]
                # 3) More 自动翻页（空格仅翻页，不会误执行命令）
                if self.auto_more and "---- More ----" in tail:
                    ser.write(b" ")
                    time.sleep(0.25)
                    tail = ""
                continue
            time.sleep(0.02)


# ---------------------------------------------------------------- 主页面
class TerminalTab(QWidget):
    """自由终端：交互式 Console 会话（只读模式默认，写模式显式开启）"""

    def __init__(self):
        super().__init__()
        self._worker = None
        self._connected = False
        self._vendor = None
        self._write_mode = False
        self._history = []        # 命令历史（↑↓ 翻）
        self._hist_idx = 0
        self.initUI()
        self._term_note("[终端] 未连接——选择串口后点「连接」。写命令需先开启写模式。")

    # ---------------- UI ----------------
    def initUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)
        layout.addWidget(page_header(
            "自由终端", "Console 交互终端——像 SecureCRT 一样直接敲命令、实时回显；"
                       "默认只读，写命令须显式开启写模式"))

        # ---- 连接卡 ----
        conn_group = QGroupBox("终端连接")
        conn_form = QHBoxLayout()
        conn_form.setSpacing(16)
        conn_form.setContentsMargins(16, 8, 16, 8)

        self.port_combo = QComboBox()
        self.port_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.port_combo.setMinimumWidth(220)
        self.refresh_ports()

        refresh_btn = QPushButton("刷新串口")
        refresh_btn.setObjectName("secondaryButton")
        refresh_btn.setToolTip("重新扫描本机串口（插拔 Console 线后点这里）")
        refresh_btn.clicked.connect(self.refresh_ports)

        self.baud_spin = QSpinBox()
        self.baud_spin.setRange(1200, 115200)
        self.baud_spin.setValue(9600)

        self.connect_btn = QPushButton("连接")
        self.connect_btn.setObjectName("primaryButton")
        self.connect_btn.clicked.connect(self._toggle_connect)

        self.status_label = QLabel("未连接")
        self.status_label.setStyleSheet("font-size: 12px; color: #5F6B7A;")

        conn_form.addWidget(QLabel("串口:"))
        conn_form.addWidget(self.port_combo, 2)
        conn_form.addStretch(1)
        conn_form.addWidget(QLabel("波特率:"))
        conn_form.addWidget(self.baud_spin)
        conn_form.addStretch(1)
        conn_form.addWidget(refresh_btn)
        conn_form.addStretch(2)
        conn_form.addWidget(self.connect_btn)
        conn_form.addWidget(self.status_label)
        conn_group.setLayout(conn_form)
        layout.addWidget(conn_group)

        # ---- 模式行：写模式按钮 + 警示横幅 + More 开关 + 快捷命令 ----
        mode_row = QHBoxLayout()
        mode_row.setSpacing(10)

        self.write_btn = QPushButton("开启写模式")
        self.write_btn.setObjectName("dangerGhostButton")
        self.write_btn.setEnabled(False)   # 连接后可用（与 _reset_ui 语义一致）
        self.write_btn.setToolTip(
            "开启后本终端可发送任意命令（配置修改 / save / 重启），白名单不再拦截；\n"
            "断开连接时自动复位为只读")
        self.write_btn.clicked.connect(self._toggle_write_mode)
        mode_row.addWidget(self.write_btn)

        self.banner = QLabel("写模式已开启：任意命令直接生效（含 save / 重启），谨慎操作")
        self.banner.setStyleSheet(_BANNER_QSS)
        self.banner.setVisible(False)
        mode_row.addWidget(self.banner, 1)

        self.more_check = QCheckBox("More 自动翻页")
        self.more_check.setChecked(True)
        self.more_check.setToolTip("输出出现 ---- More ---- 时自动发空格翻页；设备交互确认时再关闭")
        self.more_check.toggled.connect(self._sync_more)
        mode_row.addWidget(self.more_check)

        self._quick_btns = []
        for label, cmd_map in (("当前配置", cr.VENDOR_CONFIG_CMD),
                               ("设备版本", cr.VENDOR_VERSION_CMD)):
            btn = QPushButton(label)
            btn.setObjectName("secondaryButton")
            btn.setEnabled(False)   # 连接后按厂商启用
            btn.clicked.connect(
                lambda _=False, m=cmd_map: self._quick_send(m))
            self._quick_btns.append((btn, cmd_map))
            mode_row.addWidget(btn)
        layout.addLayout(mode_row)

        # ---- 终端回显区 ----
        self.term_view = QTextEdit()
        self.term_view.setReadOnly(True)
        self.term_view.setStyleSheet(_TERM_QSS)
        layout.addWidget(self.term_view, 1)

        # ---- 输入行（常驻底部）----
        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        self.cmd_input = QLineEdit()
        self.cmd_input.setFont(self._mono_font())
        self.cmd_input.setPlaceholderText("输入命令，回车发送（↑↓ 翻历史）")
        self.cmd_input.returnPressed.connect(self._do_send)
        self.cmd_input.installEventFilter(self)   # ↑↓ 历史
        input_row.addWidget(self.cmd_input, 1)

        send_btn = QPushButton("发送")
        send_btn.setObjectName("primaryButton")
        send_btn.clicked.connect(self._do_send)
        input_row.addWidget(send_btn)

        clear_btn = QPushButton("清屏")
        clear_btn.setObjectName("ghostButton")
        clear_btn.setToolTip("清空终端回显（不影响设备，也不清空命令历史）")
        clear_btn.clicked.connect(self.term_view.clear)
        input_row.addWidget(clear_btn)
        layout.addLayout(input_row)

    @staticmethod
    def _mono_font():
        from PyQt5.QtGui import QFont
        f = QFont("JetBrains Mono")
        f.setStyleHint(QFont.Monospace)
        f.setPixelSize(14)
        return f

    # ---------------- 契约方法（主窗口切换品牌时遍历调用） ----------------
    def clear_config(self):
        """终端会话不随品牌切换清理：只清输入行草稿，连接状态保持"""
        self.cmd_input.clear()

    def shutdown(self):
        """主窗口关闭时调用：停止终端线程、释放串口"""
        if self._worker is not None:
            self._worker.request_stop()
            self._worker.wait(3000)
            self._worker = None
            self._connected = False

    # ---------------- 逻辑 ----------------
    def _sync_more(self, checked: bool):
        """More 开关同步给当前终端线程（未连接时只存 UI 状态）"""
        if self._worker is not None:
            self._worker.auto_more = checked

    def refresh_ports(self):
        self.port_combo.clear()
        ports = cr.list_console_ports()
        if ports:
            for p, desc in ports:
                self.port_combo.addItem(f"{p} — {desc}", p)
        else:
            self.port_combo.addItem("（未检测到串口）", None)

    # ---- 连接 ----
    def _toggle_connect(self):
        if self._connected:
            self._disconnect()
            return
        port = self.port_combo.currentData()
        if not port:
            self._term_note("[终端] 未检测到串口——请插好 Console 线后点「刷新串口」")
            return
        self.connect_btn.setEnabled(False)
        self.connect_btn.setText("连接中…")
        self._worker = _TermWorker(port, self.baud_spin.value())
        self._worker.auto_more = self.more_check.isChecked()   # 开关状态在连接时同步给线程
        self._worker.text.connect(self._on_text)
        self._worker.state.connect(self._on_state)
        self._worker.start()

    def _disconnect(self):
        if self._worker is not None:
            self._worker.request_stop()
            self._worker.wait(3000)
        self._worker = None
        self._reset_ui("已断开")

    def _on_state(self, ok: bool, msg: str):
        if ok:
            self._connected = True
            self._vendor = msg or None
            name = VENDOR_LABELS.get(msg, msg or "未识别")
            self.status_label.setText(f"已连接 · {name}")
            self.connect_btn.setText("断开")
            self.connect_btn.setObjectName("secondaryButton")
            self.write_btn.setEnabled(True)
            for btn, _ in self._quick_btns:
                btn.setEnabled(True)
            self._term_note(
                f"[终端] 已连接（厂商：{name}）。直接敲命令回车发送；↑↓ 翻历史；"
                f"默认只读，写命令须开启写模式。")
        else:
            # 连接失败 / 线程退出：统一复位（幂等）
            self._worker = None
            self._reset_ui(msg)
            if "连接失败" in msg:
                self._term_note(
                    f"[终端] {msg}\n"
                    "         排查：① Console 线/波特率是否正确（默认 9600）；"
                    "② 串口是否被 Console 可视化页或 MobaXterm/Xshell 等程序占用。")

    def _reset_ui(self, status: str):
        self._connected = False
        self._vendor = None
        # 断开即复位只读（安全默认：每次连接都需重新显式开启写模式）
        self._write_mode = False
        self.write_btn.setText("开启写模式")
        self.write_btn.setObjectName("dangerGhostButton")
        self.write_btn.setEnabled(False)
        self.banner.setVisible(False)
        self.connect_btn.setEnabled(True)
        self.connect_btn.setText("连接")
        self.connect_btn.setObjectName("primaryButton")
        for btn, _ in self._quick_btns:
            btn.setEnabled(False)
        self.status_label.setText(status)

    # ---- 写模式 ----
    def _toggle_write_mode(self):
        if self._write_mode:
            self._write_mode = False
            self.write_btn.setText("开启写模式")
            self.write_btn.setObjectName("dangerGhostButton")
            self.banner.setVisible(False)
            self._term_note("[写模式] 已关闭——恢复只读白名单校验")
            return
        if not self._connected:
            self._term_note("[终端] 请先连接设备，再开启写模式")
            return
        # 危险确认：回车默认落在「否」（与下发闭环同一安全约定）
        if question_box(
                self, "开启写模式",
                "写模式开启后，本终端可发送任意命令——配置修改、save 存盘、"
                "重启设备都将直接生效，只读白名单不再拦截。\n\n"
                "建议先用 Console 可视化页「保存配置文件」备份当前配置。\n"
                "确认开启写模式？",
                ok="开启写模式", cancel="保持只读", default="cancel"):
            self._write_mode = True
            self.write_btn.setText("关闭写模式")
            self.write_btn.setObjectName("dangerButton")
            self.banner.setVisible(True)
            self._term_note("[写模式] 已开启——任意命令直接生效，谨慎操作")

    # ---- 发送 ----
    def _do_send(self):
        if not self._connected or self._worker is None:
            self._term_note("[终端] 未连接")
            return
        cmd = self.cmd_input.text().strip()
        if not cmd:
            return
        if not self._write_mode:
            ok, reason = cr.check_read_only(cmd)
            if not ok:
                self._flash_input_alert()
                self._term_note(f"[只读拦截] {reason}")
                self._term_note("         点「开启写模式」可放行写命令")
                return
        self._push_history(cmd)
        self._worker.send(cmd)
        self.cmd_input.clear()

    def _quick_send(self, cmd_map):
        """快捷只读命令：按已识别厂商取命令，填入输入行走统一发送/校验/历史路径"""
        if not self._connected:
            return
        cmd = cmd_map.get(self._vendor or "", "display current-configuration")
        self.cmd_input.setText(cmd)
        self._do_send()

    def _flash_input_alert(self):
        self.cmd_input.setStyleSheet(_INPUT_ALERT_QSS)
        QTimer.singleShot(900, lambda: self.cmd_input.setStyleSheet(""))

    # ---- 命令历史（↑↓）----
    def _push_history(self, cmd: str):
        if not self._history or self._history[-1] != cmd:
            self._history.append(cmd)
        self._hist_idx = len(self._history)

    def _hist_move(self, delta: int):
        if not self._history:
            return
        idx = self._hist_idx + delta
        if delta < 0:
            self._hist_idx = max(0, idx)
            self.cmd_input.setText(self._history[self._hist_idx])
        else:
            if idx >= len(self._history):
                self._hist_idx = len(self._history)
                self.cmd_input.clear()
            else:
                self._hist_idx = idx
                self.cmd_input.setText(self._history[idx])

    def eventFilter(self, obj, event):
        if obj is self.cmd_input and event.type() == QEvent.KeyPress:
            key = event.key()
            if key == Qt.Key_Up:
                self._hist_move(-1)
                return True
            if key == Qt.Key_Down:
                self._hist_move(1)
                return True
        return super().eventFilter(obj, event)

    # ---- 回显 ----
    def _on_text(self, text: str):
        sb = self.term_view.verticalScrollBar()
        at_bottom = sb.value() >= sb.maximum() - 4
        self.term_view.moveCursor(QTextCursor.End)
        self.term_view.insertPlainText(text)
        if at_bottom:
            sb.setValue(sb.maximum())

    def _term_note(self, text: str):
        """本页提示行（区别于设备回显，带前缀）"""
        self.term_view.moveCursor(QTextCursor.End)
        self.term_view.insertPlainText(text + "\n")
        self.term_view.moveCursor(QTextCursor.End)
