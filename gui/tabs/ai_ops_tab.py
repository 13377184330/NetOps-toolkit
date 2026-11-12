#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
AI 运维页（v4.1 新增）
自然语言运维三模式：生成配置 / 诊断分析 / 自由问答。

安全闭环（HITL，借鉴开源项目 Netiarius 的 plan/confirm 范式）：
  AI 流式生成 → 命令进「审阅队列」（风险徽标 + 语法体检）
  → 人工逐条勾选/编辑 → 下发确认弹窗（命令全文 + 高危横幅 + 责任勾选）
  → 受控下发（走 device_connector.send_config，默认不存盘，验收后人工 save）
AI 不可用时 gen 模式自动降级离线规则引擎（modules.nl_engine），页面永远可用。

渲染遵循全局铁律：流式期间逐字实时插入（insertHtml），绝不冻结画面再一次性渲染；
消息完成后才做一次全量重绘（换气泡样式），单次 <10ms 用户无感。
"""

import html as _html
import re

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QGroupBox, QHBoxLayout,
                              QLabel, QPushButton, QScrollArea, QTextBrowser,
                              QTextEdit, QVBoxLayout, QWidget)

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from modules import ai_ops
from modules import device_connector
from gui import theme
from gui.styles import ACCENT, BORDER, CARD, DANGER, TEXT, TEXT_SUB
from gui.widget_utils import page_header
from gui.dialogs.base import BaseDialog, info_box, warn_box, error_box
from utils.device_store import DeviceStore

_MODES = [("gen", "生成配置"), ("analyze", "诊断分析"), ("chat", "自由问答")]
_VENDORS = ("huawei", "h3c", "ruijie", "maipu", "cisco")

_PLACEHOLDER = {
    "gen": "用大白话描述变更需求，Ctrl+Enter 发送\n"
           "例：创建vlan10 20，把gi1/0/1划入vlan10，GE1/0/24做trunk放行，开启ssh账号admin密码Admin@123",
    "analyze": "先选好设备厂商，再粘贴设备回显/配置/日志片段，让 AI 定位异常\n"
               "例：粘贴 display interface brief / 设备日志 / running-config 片段",
    "chat": "任何网络运维问题都可以问：原理、排错思路、命令语义…",
}


# ================================================================ 后台线程
class _StreamWorker(QThread):
    """AI 流式对话（网络阻塞放子线程，delta 信号驱动 UI 实时渲染）"""
    delta = pyqtSignal(str)
    ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, messages, config, parent=None):
        super().__init__(parent)
        self._messages = messages
        self._config = config

    def run(self):
        full, err = ai_ops.stream_chat(
            self._messages,
            on_delta=lambda t: self.delta.emit(t),
            config=self._config)
        if err:
            self.failed.emit(err)
        else:
            self.ok.emit(full or "")


class _SendWorker(QThread):
    """真机下发（netmiko 阻塞调用放子线程）"""
    done = pyqtSignal(bool, str)

    def __init__(self, device, password, cmd_text, parent=None):
        super().__init__(parent)
        self._device = device
        self._password = password
        self._cmd_text = cmd_text

    def run(self):
        try:
            ok, log = device_connector.send_config(
                self._device, self._password, self._cmd_text, timeout=60)
            self.done.emit(ok, log)
        except Exception as e:
            self.done.emit(False, f"{type(e).__name__}: {e}")


# ================================================================ 下发确认弹窗
class _DeployConfirmDialog(BaseDialog):
    """下发前最后一道闸：命令全文 + 高危横幅 + 责任勾选（不勾选无法确认）"""

    def __init__(self, parent, device_label, cmd_lines, danger_count):
        super().__init__("确认下发到设备", "", parent,
                         min_width=660, min_height=520, scrollable=True)
        self._confirmed = False
        lay = self.content_layout()

        dev = QLabel(f"目标设备：{device_label}")
        dev.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {TEXT};")
        lay.addWidget(dev)

        body = QTextEdit()
        body.setReadOnly(True)
        body.setStyleSheet("""
            font-family: 'JetBrains Mono', 'Consolas', monospace;
            font-size: 13px; line-height: 1.6;
            background: #1E2430; border: 1px solid #2C3444; border-radius: 12px;
            padding: 12px; color: #C8D3E8;
        """)
        body.setPlainText("\n".join(cmd_lines))
        body.setMinimumHeight(220)
        lay.addWidget(body, 1)

        if danger_count:
            banner = QLabel(f"⚠ 本批含 {danger_count} 条高危命令（删配置/重启/清库/恢复出厂类），"
                            f"请务必核对回退方案后再执行。")
            banner.setWordWrap(True)
            banner.setStyleSheet(f"""
                background: #FDEEEE; color: {DANGER}; border-radius: 10px;
                padding: 10px 14px; font-size: 13px; font-weight: bold;
            """)
            lay.addWidget(banner)

        tip = QLabel("设备回显会显示在聊天区。下发默认不存盘，验收合格后请手动 save。")
        tip.setWordWrap(True)
        tip.setStyleSheet(f"color: {TEXT_SUB}; font-size: 12px;")
        lay.addWidget(tip)

        self.ack_cb = QCheckBox("我已逐条核验以上命令，知晓在真机执行的后果")
        self.ack_cb.setMinimumHeight(26)
        lay.addWidget(self.ack_cb)

        self.btn_confirm = self.add_button("确认下发", "primary",
                                           self._confirm, close_on_click=False)
        self.btn_confirm.setEnabled(False)
        self.ack_cb.toggled.connect(lambda on: self.btn_confirm.setEnabled(on))
        self.add_close_button("取消", "ghost")

    def _confirm(self):
        self._confirmed = True
        self.accept()

    @property
    def confirmed(self):
        return self._confirmed


# ================================================================ 主页面
class AIOpsTab(QWidget):
    """AI 运维页：聊天区（上） + 待确认命令队列（中） + 输入区（下）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._history = []          # [{"role": user/assistant, "content": str}]
        self._cards = []            # 审阅队列卡片 [{"cmd","note","risk","lint","checked","source"}]
        self._busy = False          # 流式生成中
        self._aborted = False       # 用户点了停止（后续 delta 丢弃）
        self._stream_worker = None
        self._send_worker = None
        self._device_ids = []       # combo index -> device_id
        self.initUI()

    # ---------------------------------------------------------------- 布局
    def initUI(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(10)

        lay.addWidget(page_header("AI 运维", "自然语言描述 → AI 生成命令 → 人工审阅确认 → 受控下发"))

        # ---- 工具行 ----
        bar = QHBoxLayout()
        bar.setSpacing(8)

        self.mode_combo = QComboBox()
        for key, name in _MODES:
            self.mode_combo.addItem(name, key)
        self.mode_combo.setMinimumWidth(120)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        bar.addWidget(QLabel("模式:"))
        bar.addWidget(self.mode_combo)

        self.vendor_combo = QComboBox()
        for v in _VENDORS:
            self.vendor_combo.addItem(ai_ops.VENDOR_CN[v], v)
        bar.addWidget(QLabel("厂商:"))
        bar.addWidget(self.vendor_combo)

        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(180)
        self._reload_devices()
        bar.addWidget(QLabel("目标设备:"))
        bar.addWidget(self.device_combo, 1)

        refresh_btn = QPushButton("↻")
        refresh_btn.setFixedSize(34, 34)
        refresh_btn.setToolTip("刷新设备清单")
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.setStyleSheet(f"""
            QPushButton {{ background: {CARD}; border: 1px solid {BORDER};
                border-radius: 17px; font-size: 15px; color: {TEXT}; }}
            QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}
        """)
        refresh_btn.clicked.connect(self._reload_devices)
        bar.addWidget(refresh_btn)

        cfg_btn = QPushButton("⚙ AI 设置")
        cfg_btn.setObjectName("ghostButton")
        cfg_btn.setCursor(Qt.PointingHandCursor)
        cfg_btn.setToolTip("配置模型服务商 / 地址 / Key（设置对话框 → AI 页）")
        cfg_btn.clicked.connect(self._open_ai_settings)
        bar.addWidget(cfg_btn)
        lay.addLayout(bar)

        # ---- 聊天区 ----
        self.chat_view = QTextBrowser()
        self.chat_view.setOpenExternalLinks(True)
        self.chat_view.setStyleSheet(f"""
            QTextBrowser {{
                background: {CARD}; border: 1px solid {BORDER};
                border-radius: 14px; padding: 14px;
            }}
        """)
        lay.addWidget(self.chat_view, 3)

        # ---- 待确认命令队列 ----
        queue_group = QGroupBox()
        queue_group.setStyleSheet(f"""
            QGroupBox {{
                border: 1px solid {BORDER}; border-radius: 14px;
                background: {CARD}; padding: 26px 14px 14px 14px;
                font-weight: bold;
            }}
            QGroupBox::title {{
                subcontrol-origin: padding; subcontrol-position: top left;
                left: 14px; top: 8px; padding: 0;
                color: {TEXT}; font-size: 14px;
            }}
        """)
        q_lay = QVBoxLayout(queue_group)
        q_lay.setContentsMargins(0, 4, 0, 0)
        q_lay.setSpacing(8)

        self.queue_title = queue_group
        self._queue_group = queue_group

        q_bar = QHBoxLayout()
        q_bar.setSpacing(8)
        self.select_all_btn = QPushButton("全选写命令")
        self.select_all_btn.setObjectName("ghostButton")
        self.select_all_btn.setToolTip("勾选全部「写配置」命令（只读命令不参与下发）")
        self.select_all_btn.clicked.connect(lambda: self._toggle_all(True))
        q_bar.addWidget(self.select_all_btn)

        none_btn = QPushButton("全部取消")
        none_btn.setObjectName("ghostButton")
        none_btn.clicked.connect(lambda: self._toggle_all(False))
        q_bar.addWidget(none_btn)

        clear_btn = QPushButton("清空队列")
        clear_btn.setObjectName("ghostButton")
        clear_btn.clicked.connect(self._clear_queue)
        q_bar.addWidget(clear_btn)

        q_bar.addStretch()

        self.deploy_btn = QPushButton("确认下发")
        self.deploy_btn.setObjectName("primaryButton")
        self.deploy_btn.setCursor(Qt.PointingHandCursor)
        self.deploy_btn.setToolTip("把勾选的命令下发到目标设备（逐条人工确认后执行）")
        self.deploy_btn.clicked.connect(self._deploy)
        q_bar.addWidget(self.deploy_btn)
        q_lay.addLayout(q_bar)

        # 队列容器：QScrollArea + 纵向直排卡片（高度自适应；不用 QListWidget——
        # setItemWidget 依赖手动 sizeHint，布局未激活时高度偏小实测会裁掉注释行/徽标）
        self.queue_scroll = QScrollArea()
        self.queue_scroll.setWidgetResizable(True)
        self.queue_scroll.setFrameShape(QScrollArea.NoFrame)
        self.queue_scroll.setMinimumHeight(150)   # 至少容下 2-3 张卡，更多走滚动
        self.queue_scroll.setMaximumHeight(260)
        self.queue_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.queue_host = QWidget()
        self.queue_host.setStyleSheet("background: transparent;")
        self.queue_lay = QVBoxLayout(self.queue_host)
        self.queue_lay.setContentsMargins(2, 2, 2, 2)
        self.queue_lay.setSpacing(8)
        self.queue_scroll.setWidget(self.queue_host)
        q_lay.addWidget(self.queue_scroll)
        lay.addWidget(queue_group, 2)

        # ---- 输入区 ----
        input_group = QWidget()
        in_lay = QHBoxLayout(input_group)
        in_lay.setContentsMargins(0, 0, 0, 0)
        in_lay.setSpacing(8)

        self.input_view = QTextEdit()
        self.input_view.setMinimumHeight(64)
        self.input_view.setMaximumHeight(110)
        self.input_view.setPlaceholderText(_PLACEHOLDER["gen"])
        self.input_view.installEventFilter(self)
        in_lay.addWidget(self.input_view, 1)

        btn_col = QVBoxLayout()
        btn_col.setSpacing(8)
        self.send_btn = QPushButton("发送")
        self.send_btn.setObjectName("primaryButton")
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.setToolTip("Ctrl+Enter 快捷发送")
        self.send_btn.clicked.connect(self._on_send_clicked)
        btn_col.addWidget(self.send_btn)

        self.stop_btn = QPushButton("停止")
        self.stop_btn.setObjectName("dangerGhostButton")
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.setToolTip("中断本次生成（已生成内容保留）")
        self.stop_btn.setVisible(False)
        self.stop_btn.clicked.connect(self._stop_stream)
        btn_col.addWidget(self.stop_btn)
        in_lay.addLayout(btn_col)
        lay.addWidget(input_group)

        # ---- 状态行 ----
        self.status_label = QLabel()
        self.status_label.setStyleSheet(f"color: {TEXT_SUB}; font-size: 12px;")
        lay.addWidget(self.status_label)
        self._sync_status()
        self._render_welcome()
        # 主题切换时重绘聊天气泡：HTML 内联色不走 QSS 重映射，必须现取现刷
        theme.on_change(self._on_theme_changed)

    def _on_theme_changed(self):
        """主题切换：欢迎语与历史气泡的 HTML 内联色现取，必须重绘"""
        if self._history:
            self._rerender()
        else:
            self._render_welcome()

    # ---------------------------------------------------------------- 事件
    def eventFilter(self, obj, ev):
        if obj is self.input_view and ev.type() == ev.KeyPress:
            if ev.key() in (Qt.Key_Return, Qt.Key_Enter) and ev.modifiers() & Qt.ControlModifier:
                self._on_send_clicked()
                return True
        return super().eventFilter(obj, ev)

    def showEvent(self, ev):
        super().showEvent(ev)
        self._reload_devices()   # 每次进页刷新设备清单

    def _on_mode_changed(self):
        self.input_view.setPlaceholderText(_PLACEHOLDER[self._mode()])

    # ---------------------------------------------------------------- 小工具
    def _mode(self):
        return self.mode_combo.currentData() or "gen"

    def _vendor(self):
        return self.vendor_combo.currentData() or "huawei"

    def _sync_status(self, running=False):
        cfg = ai_ops.get_ai_config()
        if running:
            self.status_label.setText("● AI 生成中…")
            self.status_label.setStyleSheet(f"color: {ACCENT}; font-size: 12px;")
        else:
            if cfg["configured"]:
                self.status_label.setText(f"就绪 · 模型: {cfg['model'] or '（未填）'} · 服务商: {cfg['name']}")
            else:
                self.status_label.setText("AI 未配置——点击右上「⚙ AI 设置」填写，"
                                          "或直接用生成配置模式（离线规则引擎兜底可用）")
            self.status_label.setStyleSheet(f"color: {TEXT_SUB}; font-size: 12px;")

    def _reload_devices(self):
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        self.device_combo.addItem("（不选设备，仅生成配置）", None)
        self._device_ids = [None]
        for d in DeviceStore().list_all():
            label = f"{d.get('name') or d.get('ip')}（{d.get('ip')}）"
            self.device_combo.addItem(label, d.get("id"))
            self._device_ids.append(d.get("id"))
        self.device_combo.blockSignals(False)

    def _open_ai_settings(self):
        from gui.dialogs.settings_dialog import SettingsDialog
        dlg = SettingsDialog(self)
        dlg.go_ai_tab()
        dlg.exec_()
        self._sync_status()

    # ---------------------------------------------------------------- 聊天渲染
    def _render_welcome(self):
        self.chat_view.clear()
        self._sys_line("AI 运维已就绪：命令只生成草稿、永不自动执行；"
                       "下发前需逐条勾选并二次确认。生成配置模式离线可用（规则引擎兜底）。")

    def _sys_line(self, text):
        """系统提示行（居中灰）——色值 theme.t() 现取，双主题可用"""
        self.chat_view.append(
            f'<div align="center" style="color:{theme.t("text_sub")};font-size:12px;'
            f'margin:4px 0;">{_html.escape(text)}</div>')

    def _append_user(self, text):
        body = _html.escape(text).replace("\n", "<br>")
        self.chat_view.append(
            '<table width="100%" cellspacing="0" cellpadding="0"><tr>'
            f'<td></td><td width="80%" align="right">'
            f'<div style="background:{theme.t("accent")};color:#FFFFFF;border-radius:12px;'
            f'padding:9px 14px;font-size:13px;">{body}</div>'
            '</td></tr></table>')

    def _append_stream_head(self):
        self.chat_view.append(
            f'<div style="color:{theme.t("text_sub")};font-size:11px;margin-bottom:2px;">AI</div>')

    def _append_stream_delta(self, text):
        """流式期间逐段实时插入（无样式纯文本），完成后再全量重绘换样式"""
        cur = self.chat_view.textCursor()
        cur.movePosition(QTextCursor.End)
        cur.insertHtml(_html.escape(text))

    def _append_ai_final(self, full, n_cards, n_danger):
        self._history.append({"role": "assistant", "content": full})
        self._rerender()
        if n_cards:
            warn = f"，其中高危 {n_danger} 条" if n_danger else ""
            self._sys_line(f"{n_cards} 条命令已进入审阅队列{warn}——请逐条核验后勾选下发。")

    def _rerender(self):
        """把聊天历史全量重绘为样式化气泡（完成态调用，单次 <10ms）"""
        view = self.chat_view
        view.clear()
        self._sys_line("AI 运维已就绪：命令只生成草稿、永不自动执行；"
                       "下发前需逐条勾选并二次确认。")
        for m in self._history:
            if m["role"] == "user":
                self._append_user(m["content"])
            else:
                view.append(self._ai_bubble(m["content"]))

    def _ai_bubble(self, text):
        body = _render_ai_content(text)
        return ('<table width="100%" cellspacing="0" cellpadding="0"><tr>'
                f'<td width="80%" align="left">'
                f'<div style="background:{theme.t("card")};border:1px solid {theme.t("border")};'
                f'border-radius:12px;padding:10px 14px;font-size:13px;'
                f'color:{theme.t("text")};">{body}</div>'
                '</td></tr></table>')

    def _auto_scroll(self):
        sb = self.chat_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ---------------------------------------------------------------- 发送 / 流式
    def _on_send_clicked(self):
        if self._busy:
            return
        text = self.input_view.toPlainText().strip()
        if not text:
            warn_box(self, "提示", "请先输入内容")
            return

        mode = self._mode()
        vendor = self._vendor()
        self._append_user(text)
        self._history.append({"role": "user", "content": text})

        cfg = ai_ops.get_ai_config()
        messages = ai_ops.build_messages(mode, vendor, self._history[:-1], text)

        self._busy = True
        self._aborted = False
        self.send_btn.setVisible(False)
        self.stop_btn.setVisible(True)
        self._sync_status(running=True)
        self._append_stream_head()

        self._stream_worker = _StreamWorker(messages, cfg)
        self._stream_worker.delta.connect(self._on_delta)
        self._stream_worker.ok.connect(lambda full: self._on_stream_ok(full, mode, vendor))
        self._stream_worker.failed.connect(lambda err: self._on_stream_failed(err, mode, vendor, text))
        self._stream_worker.start()

    def _stop_stream(self):
        if self._busy:
            self._aborted = True   # 后续 delta 丢弃；worker 网络读无法强杀，结束后自然收尾
            self._sys_line("已停止生成（保留已输出部分）")
            self._restore_after_stream()

    def _on_delta(self, text):
        if self._aborted:
            return
        self._append_stream_delta(text)
        self._auto_scroll()

    def _on_stream_ok(self, full, mode, vendor):
        if self._aborted:
            return
        if not full.strip():
            self._on_stream_failed("模型返回为空（接口异常或本地模型未加载）",
                                   mode, vendor, self._last_user_text())
            return
        cards = ai_ops.parse_command_blocks(full)
        if cards:
            ai_ops.lint_cards(cards, vendor)
            self._queue_cards(cards, source="AI")
        n_danger = sum(1 for c in cards if c["risk"] == "dangerous")
        self._append_ai_final(full, len(cards), n_danger)
        self._restore_after_stream()

    def _on_stream_failed(self, err, mode, vendor, user_text):
        if self._aborted:
            return
        self._sys_line(f"AI 调用失败：{err}")
        if mode == "gen":
            cards, unknown = ai_ops.fallback_parse(user_text, vendor)
            if cards:
                self._queue_cards(cards, source="离线规则引擎")
                n_danger = sum(1 for c in cards if c["risk"] == "dangerous")
                self._sys_line(f"已自动降级为离线规则引擎生成：{len(cards)} 条命令入队"
                               + (f"，高危 {n_danger} 条" if n_danger else ""))
                if unknown:
                    self._sys_line(f"规则引擎未识别：{'、'.join(f'「{u}」' for u in unknown)}——"
                                   f"可换说法重试或配置 AI 后再试")
            else:
                self._sys_line("离线规则引擎也未识别该说法，请按「厂商黑话」改写"
                               "（vlan/接口名/掩码/下一跳），或配置 AI 处理自由表达。")
        self._restore_after_stream()

    def _restore_after_stream(self):
        self._busy = False
        self.send_btn.setVisible(True)
        self.stop_btn.setVisible(False)
        self._sync_status()
        self._auto_scroll()

    def _last_user_text(self):
        for m in reversed(self._history):
            if m["role"] == "user":
                return m["content"]
        return ""

    # ---------------------------------------------------------------- 命令队列
    def _queue_cards(self, cards, source="AI"):
        """AI/规则引擎产出的命令进审阅队列（默认全部不勾选——人工确认从零开始）"""
        for c in cards:
            c["source"] = source
            c["checked"] = False
            self._cards.append(c)
        self._refresh_queue()

    def _refresh_queue(self):
        """重建队列卡片（scroll+直排布局，卡片高度由内容自适应，不裁切）"""
        while self.queue_lay.count():
            item = self.queue_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        n_danger = sum(1 for c in self._cards if c["risk"] == "dangerous")
        n_readonly = sum(1 for c in self._cards if c["risk"] == "readonly")
        self._queue_group.setTitle(
            f"待确认命令队列（{len(self._cards)} 条 · 高危 {n_danger} · 只读 {n_readonly}）")
        if not self._cards:
            empty = QLabel("队列空：AI 生成的命令会出现在这里，逐条核验勾选后才可下发")
            empty.setStyleSheet(f"color: {TEXT_SUB}; font-size: 12px;")
            empty.setAlignment(Qt.AlignCenter)
            self.queue_lay.addWidget(empty)
        for idx, c in enumerate(self._cards):
            self.queue_lay.addWidget(self._make_card_row(c, idx))
        self.queue_lay.addStretch()
        self._sync_deploy_btn()

    def _make_card_row(self, card, idx):
        row = QWidget()
        row.setStyleSheet(f"""
            QWidget#cardRow {{ background: {CARD}; border: 1px solid {BORDER};
                border-radius: 12px; }}
        """)
        row.setObjectName("cardRow")
        v = QVBoxLayout(row)
        v.setContentsMargins(12, 8, 12, 8)
        v.setSpacing(3)

        top = QHBoxLayout()
        top.setSpacing(8)
        chk = QCheckBox()
        chk.setMinimumHeight(20)                     # 防布局压缩把指示器挤扁
        chk.setChecked(bool(card["checked"]))
        if card["risk"] == "readonly":
            chk.setEnabled(False)
            chk.setToolTip("只读命令不参与下发，仅供核对设备状态")
        chk.toggled.connect(lambda on, i=idx: self._on_card_checked(i, on))
        top.addWidget(chk)

        cmd_label = QLabel(card["cmd"])
        cmd_label.setMinimumHeight(20)
        # 高危命令红字（与聊天代码块同一着色语义，风险扫读跨区一致）
        cmd_color = DANGER if card["risk"] == "dangerous" else TEXT
        cmd_label.setStyleSheet(f"""
            font-family: 'JetBrains Mono', 'Consolas', monospace;
            font-size: 12px; color: {cmd_color}; background: transparent;
        """)
        top.addWidget(cmd_label, 1)

        badge = QLabel(ai_ops.RISK_LABEL[card["risk"]])
        badge.setMinimumHeight(20)                    # 徽标必须完整容纳 11px 字
        color = ai_ops.RISK_COLOR[card["risk"]]
        badge.setStyleSheet(f"""
            background: {color}; color: #FFFFFF; border-radius: 10px;
            padding: 2px 10px; font-size: 11px; font-weight: bold;
        """)
        badge.setToolTip(f"来源：{card.get('source', 'AI')}")
        top.addWidget(badge)

        if card["risk"] == "dangerous":
            del_btn = QPushButton("✕")
            del_btn.setFixedSize(26, 26)
            del_btn.setCursor(Qt.PointingHandCursor)
            del_btn.setStyleSheet(f"""
                QPushButton {{ background: transparent; border: none;
                    color: {DANGER}; font-size: 13px; }}
                QPushButton:hover {{ color: #D03030; }}
            """)
            del_btn.setToolTip("从队列删除该高危命令")
            del_btn.clicked.connect(lambda _=False, i=idx: self._remove_card(i))
            top.addWidget(del_btn)
        v.addLayout(top)

        if card.get("note"):
            note = QLabel("# " + card["note"])
            note.setMinimumHeight(16)
            note.setStyleSheet(f"color: {TEXT_SUB}; font-size: 11px; background: transparent;")
            note.setContentsMargins(30, 0, 0, 0)
            v.addWidget(note)
        for it in card.get("lint", [])[:2]:
            warn_l = QLabel(f"ⓘ [{it.get('level', '警告')}] {it.get('issue', '')} → {it.get('advice', '')}")
            warn_l.setMinimumHeight(16)
            warn_l.setStyleSheet("color: #FA9D3B; font-size: 11px; background: transparent;")
            warn_l.setContentsMargins(30, 0, 0, 0)
            v.addWidget(warn_l)
        # 卡高钉死到内容 sizeHint：防止滚动区空间不足时布局把整卡压扁
        # （布局只会压缩到 minimumSize，把 minimum 提到 sizeHint 即不可压）
        row.adjustSize()
        row.setMinimumHeight(max(row.sizeHint().height(), 40))
        return row

    def _on_card_checked(self, idx, on):
        if 0 <= idx < len(self._cards):
            self._cards[idx]["checked"] = on
        self._sync_deploy_btn()

    def _toggle_all(self, on):
        for c in self._cards:
            if c["risk"] != "readonly":
                c["checked"] = on
        self._refresh_queue()

    def _remove_card(self, idx):
        if 0 <= idx < len(self._cards):
            self._cards.pop(idx)
            self._refresh_queue()

    def _clear_queue(self):
        if self._cards:
            self._cards.clear()
            self._refresh_queue()

    def _sync_deploy_btn(self):
        n = sum(1 for c in self._cards if c["checked"] and c["risk"] != "readonly")
        self.deploy_btn.setText(f"下发所选（{n}）" if n else "确认下发")
        self.deploy_btn.setEnabled(n > 0)

    # ---------------------------------------------------------------- 下发（人工确认闸门）
    def _deploy(self):
        picks = [c for c in self._cards if c["checked"] and c["risk"] != "readonly"]
        if not picks:
            warn_box(self, "提示", "请先在队列中勾选要执行的命令")
            return
        device_id = self.device_combo.currentData()
        if device_id is None:
            warn_box(self, "提示", "请先在顶部选择目标设备（没有设备可先在「设备运维」页添加）")
            return
        device = DeviceStore().get(device_id)
        if not device:
            warn_box(self, "提示", "设备不存在，请刷新设备清单后重选")
            return
        password = DeviceStore().get_plain_password(device_id)
        if not password:
            warn_box(self, "提示", f"设备「{device.get('name')}」未保存 SSH 密码，"
                                  f"请先在「设备运维」页维护凭据")
            return

        cmd_lines = [c["cmd"] for c in picks]
        danger_n = sum(1 for c in picks if c["risk"] == "dangerous")
        dev_label = f"{device.get('name')}（{device.get('ip')} · {ai_ops.VENDOR_CN.get(device.get('vendor'), '')}）"
        dlg = _DeployConfirmDialog(self, dev_label, cmd_lines, danger_n)
        dlg.exec_()
        if not dlg.confirmed:
            return

        self._sys_line(f"正在下发 {len(cmd_lines)} 条命令到 {device.get('ip')}…")
        self._send_worker = _SendWorker(device, password, "\n".join(cmd_lines))
        self._send_worker.done.connect(
            lambda ok, log: self._on_deploy_done(ok, log, device, len(cmd_lines)))
        self._send_worker.start()

    def _on_deploy_done(self, ok, log, device, total):
        ip = device.get("ip")
        if ok:
            self._sys_line(f"✅ 已下发 {total} 条命令到 {ip}（未存盘——验收合格后请手动 save）")
            info_box(self, "下发完成",
                     f"命令已执行完毕（未存盘）。\n\n{str(log)[:400]}\n\n"
                     f"验收合格后请在设备上执行 save 存盘。")
        else:
            self._sys_line(f"❌ 下发失败：{str(log)[:120]}")
            error_box(self, "下发失败", str(log)[:600])
        self._cards = [c for c in self._cards if not c["checked"] or c["risk"] == "readonly"]
        self._refresh_queue()
        self._auto_scroll()


# ---------------------------------------------------------------- AI 正文渲染（命令块着色）
_FENCE_FIND = re.compile(r"```(?:netcfg|cli|bash|shell)?[ \t]*\r?\n(.*?)```", re.S)


def _render_ai_content(text: str) -> str:
    """AI 回复 → 气泡内 HTML：fenced 命令块渲染为深色代码卡（高危行标红）
    色值 theme.t() 现取——QTextBrowser 的 HTML 不走 QSS 重映射，双主题必须现取"""
    out, last = [], 0
    for m in _FENCE_FIND.finditer(text or ""):
        seg = text[last:m.start()]
        if seg.strip():
            out.append(_html.escape(seg).replace("\n", "<br>"))
        lines_html = []
        for raw in m.group(1).splitlines():
            if not raw.strip():
                continue
            cmd, note = _split_line_note(raw)
            risk = ai_ops.classify_command(cmd)
            color = theme.t("danger") if risk == "dangerous" else theme.t("preview_text")
            note_html = (f'<span style="color:{theme.t("preview_ph")}">  # {_html.escape(note)}</span>'
                         if note else "")
            lines_html.append(f'<div style="color:{color};">{_html.escape(cmd)}{note_html}</div>')
        out.append(
            f'<div style="background:{theme.t("preview_bg")};border:1px solid '
            f'{theme.t("preview_border")};border-radius:10px;padding:10px 12px;'
            'margin:6px 0;font-family:Consolas, monospace;font-size:12px;'
            f'line-height:1.6;">{"".join(lines_html)}</div>')
        last = m.end()
    tail = text[last:] if text else ""
    if tail.strip():
        out.append(_html.escape(tail).replace("\n", "<br>"))
    return "".join(out) or "（空回复）"


def _split_line_note(line: str):
    m = re.search(r"\s+#\s*(.+)$", line)
    if m:
        return line[:m.start()].rstrip(), m.group(1).strip()
    return line.strip(), ""
