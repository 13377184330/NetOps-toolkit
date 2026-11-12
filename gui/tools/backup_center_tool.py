#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""备份中心工具页：备份浏览 / Git 变更链 / 两版 diff / 查看 / 恢复导出
把「自动备份（Console/AI 下发前）+ Git 化」的暗资产变成可见可用——
真机问题回溯三问：改了什么？什么时候改的？改之前是什么？"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (QComboBox, QHBoxLayout, QHeaderView, QLabel,
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QVBoxLayout, QWidget)

from gui.styles import BORDER, CARD, TEXT, TEXT_SUB
from gui.dialogs.base import BaseDialog
from utils.backup_manager import ConfigBackupManager

_MONO = "font-family: 'JetBrains Mono', 'Consolas', monospace;"


class _DiffDialog(BaseDialog):
    """两版备份 diff 对比（等宽深色 diff 视图）"""

    def __init__(self, parent, r1, r2, diff_text, stats):
        super().__init__(f"配置对比：{r1.device_name}", "", parent,
                         min_width=820, min_height=560, scrollable=True)
        lay = self.content_layout()
        head = QLabel(f"{r1.backup_time}（旧） → {r2.backup_time}（新）"
                      f"　｜　新增 {stats['added']} 行 · 删除 {stats['removed']} 行 · 变更块 {stats['changed']}")
        head.setStyleSheet(f"color: {TEXT}; font-size: 13px; font-weight: bold;")
        head.setWordWrap(True)
        lay.addWidget(head)

        from PyQt5.QtWidgets import QTextEdit
        body = QTextEdit()
        body.setReadOnly(True)
        body.setStyleSheet(f"""
            { _MONO }
            font-size: 12px; line-height: 1.5; background: #1E2430;
            border: 1px solid #2C3444; border-radius: 10px; padding: 12px;
            color: #C8D3E8;
        """)
        # 行级着色：+ 绿 - 红 @@ 蓝
        html_lines = []
        for ln in (diff_text or "").splitlines():
            color = "#C8D3E8"
            if ln.startswith("+"):
                color = "#7EE787"
            elif ln.startswith("-"):
                color = "#FF9B9B"
            elif ln.startswith("@@"):
                color = "#79B8FF"
            esc = (ln.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                   .replace(" ", "&nbsp;"))
            html_lines.append(f'<div style="color:{color};">{esc}</div>')
        body.setHtml("".join(html_lines) or "<div>（两版一致）</div>")
        lay.addWidget(body, 1)
        self.add_close_button("关闭", "primary")


class BackupCenterWidget(QWidget):
    """备份中心：设备选择 → 备份列表 + Git 变更链 → 对比/查看"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mgr = ConfigBackupManager()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(12)

        head = QLabel("🗄 备份中心")
        head.setStyleSheet(f"font-size: 17px; font-weight: bold; color: {TEXT};")
        sub = QLabel("全部自动/手动备份一处可查：谁改的、改了什么、改之前什么样——"
                     "下拉溯源与两版对比")
        sub.setStyleSheet(f"font-size: 12px; color: {TEXT_SUB};")
        lay.addWidget(head)
        lay.addWidget(sub)

        # ---- 设备选择行 ----
        sel_row = QHBoxLayout()
        sel_row.setSpacing(8)
        sel_row.addWidget(QLabel("设备:"))
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(260)
        self.device_combo.currentIndexChanged.connect(self._load_device)
        refresh_btn = QPushButton("刷新")
        refresh_btn.setObjectName("secondaryButton")
        refresh_btn.clicked.connect(self._refresh_devices)
        self.diff_btn = QPushButton("对比选中两版")
        self.diff_btn.setObjectName("primaryButton")
        self.diff_btn.setToolTip("列表中勾选两行（勾选框列）后点此对比")
        self.diff_btn.clicked.connect(self._diff_selected)
        sel_row.addWidget(self.device_combo, 2)
        sel_row.addWidget(refresh_btn)
        sel_row.addStretch()
        sel_row.addWidget(self.diff_btn)
        lay.addLayout(sel_row)

        # ---- 备份列表（可勾选两行做对比） ----
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["", "时间", "类型", "描述", "大小", "Git", "操作"])
        self.table.setColumnWidth(0, 36)
        self.table.setColumnWidth(1, 150)
        self.table.setColumnWidth(2, 60)
        self.table.setColumnWidth(5, 80)
        self.table.setColumnWidth(6, 170)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        lay.addWidget(self.table, 3)

        # ---- Git 变更链 ----
        git_head = QLabel("Git 变更链（每次配置变更一条 commit——点列表行切换设备后自动刷新）")
        git_head.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {TEXT};")
        lay.addWidget(git_head)
        self.git_view = QTableWidget(0, 3)
        self.git_view.setHorizontalHeaderLabels(["commit", "时间", "说明"])
        self.git_view.setColumnWidth(0, 90)
        self.git_view.setColumnWidth(1, 155)
        self.git_view.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.git_view.verticalHeader().setVisible(False)
        self.git_view.setEditTriggers(QTableWidget.NoEditTriggers)
        self.git_view.setMaximumHeight(170)
        lay.addWidget(self.git_view, 1)

        self.hint = QLabel("")
        self.hint.setStyleSheet(f"color: #33526E; font-size: 12px; font-weight: bold; padding: 2px 4px;")
        lay.addWidget(self.hint)

        self._picked = []      # 对比勾选的 backup_id（最多 2）
        self._refresh_devices()

    # ---------------- 数据 ----------------
    def _refresh_devices(self):
        devs = sorted({(r.device_name, r.device_type) for r in self._mgr.records})
        cur = self.device_combo.currentData()
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        for name, dtype in devs:
            n = sum(1 for r in self._mgr.records if r.device_name == name)
            self.device_combo.addItem(f"{dtype} · {name}（{n} 份备份）", (name, dtype))
        self.device_combo.blockSignals(False)
        if cur:
            i = self.device_combo.findData(cur)
            if i >= 0:
                self.device_combo.setCurrentIndex(i)
        if devs:
            self._load_device()
        else:
            self.hint.setText("还没有任何备份——在 Console/AI 运维下发前会自动备份，"
                              "或到「设备运维」页手动「备份选中设备配置」")

    def _load_device(self, *_):
        data = self.device_combo.currentData()
        self.table.setRowCount(0)
        self._picked = []
        self.git_view.setRowCount(0)
        if not data:
            return
        name, dtype = data
        records = sorted(self._mgr.get_backups_by_device(name, dtype),
                         key=lambda r: r.backup_time, reverse=True)
        self.table.setRowCount(len(records))
        for i, r in enumerate(records):
            from PyQt5.QtWidgets import QCheckBox, QWidget
            chk_row = QWidget()
            cl = QHBoxLayout(chk_row)
            cl.setContentsMargins(0, 0, 0, 0)
            chk = QCheckBox()
            chk.stateChanged.connect(lambda st, rid=r.id: self._on_pick(rid, st))
            cl.addWidget(chk, 0, Qt.AlignCenter)
            self.table.setCellWidget(i, 0, chk_row)
            self.table.setRowCount(self.table.rowCount())   # no-op 保底
            self.table.setItem(i, 1, QTableWidgetItem(r.backup_time))
            it_type = QTableWidgetItem("自动" if r.is_auto else "手动")
            self.table.setItem(i, 2, it_type)
            self.table.setItem(i, 3, QTableWidgetItem(r.description or "—"))
            self.table.setItem(i, 4, QTableWidgetItem(f"{r.file_size // 1024} KB"))

            # Git 关联（视觉评审：✓变更表意模糊 → 显示对应 commit 短哈希）
            gitmark = QTableWidgetItem("—")
            for h in self._git_hist_cache(name, dtype):
                if r.backup_time[:16] in h.get("date", ""):
                    gitmark = QTableWidgetItem(h["commit"])
                    gitmark.setToolTip(f"本次备份对应 Git 变更 {h['commit']}：{h['message']}")
            self.table.setItem(i, 5, gitmark)

            op_row = QWidget()
            ol = QHBoxLayout(op_row)
            ol.setContentsMargins(4, 2, 4, 2)
            ol.setSpacing(4)
            view_btn = QPushButton("查看")
            view_btn.setStyleSheet(
                f"QPushButton {{ padding: 4px 12px; font-size: 12px; border: 1px solid #9DB2CC;"
                f" border-radius: 8px; background: {CARD}; color: #33526E; font-weight: bold; }}"
                f"QPushButton:hover {{ border-color: #0089FF; color: #0089FF; background: #F5FAFF; }}")
            view_btn.setCursor(Qt.PointingHandCursor)
            view_btn.clicked.connect(lambda _=False, rid=r.id: self._view(rid))
            save_btn = QPushButton("导出")
            save_btn.setStyleSheet(
                f"QPushButton {{ padding: 4px 12px; font-size: 12px; border: 1px solid #9DB2CC;"
                f" border-radius: 8px; background: {CARD}; color: #33526E; font-weight: bold; }}"
                f"QPushButton:hover {{ border-color: #0089FF; color: #0089FF; background: #F5FAFF; }}")
            save_btn.setCursor(Qt.PointingHandCursor)
            save_btn.clicked.connect(lambda _=False, rid=r.id: self._export(rid))
            ol.addWidget(view_btn)
            ol.addWidget(save_btn)
            ol.addStretch()
            self.table.setCellWidget(i, 6, op_row)

        # Git 变更链
        hist = self._git_hist_cache(name, dtype)
        self.git_view.setRowCount(len(hist))
        for i, h in enumerate(hist):
            self.git_view.setItem(i, 0, QTableWidgetItem(h["commit"]))
            self.git_view.setItem(i, 1, QTableWidgetItem(h["date"]))
            self.git_view.setItem(i, 2, QTableWidgetItem(h["message"]))
        if not hist:
            self.hint.setText("该设备暂无 Git 变更记录（未安装 git 或全部备份内容一致）")
        else:
            self.hint.setText(f"共 {len(records)} 份备份 · Git 变更 {len(hist)} 次")

    def _git_hist_cache(self, name, dtype):
        if not hasattr(self, "_hist_map"):
            self._hist_map = {}
        key = (name, dtype)
        if key not in self._hist_map:
            self._hist_map[key] = self._mgr.git_history(name, dtype, limit=100)
        return self._hist_map[key]

    # ---------------- 动作 ----------------
    def _on_pick(self, rid, state):
        if state:
            if rid not in self._picked:
                self._picked.append(rid)
            while len(self._picked) > 2:
                self._picked.pop(0)      # 只留最近勾的两条
        else:
            if rid in self._picked:
                self._picked.remove(rid)
        self.hint.setText((f"✅ 已选 {len(self._picked)}/2 份用于对比"
                           + ("，可点「对比选中两版」" if len(self._picked) == 2 else ""))
                          if self._picked else "")

    def _diff_selected(self):
        if len(self._picked) != 2:
            self.hint.setText("⚠ 请在列表勾选框正好勾两行（旧→新）再对比")
            return
        result = self._mgr.compare_backups(*self._picked)
        if not result:
            self.hint.setText("⚠ 对比失败（备份文件缺失）")
            return
        r1 = self._mgr.get_backup_by_id(self._picked[0])
        r2 = self._mgr.get_backup_by_id(self._picked[1])
        # 时间序规整（旧在前）
        if r1.backup_time > r2.backup_time:
            r1, r2 = r2, r1
            result = self._mgr.compare_backups(r1.id, r2.id)
        _DiffDialog(self, r1, r2, result["diff"], result).exec_()

    def _view(self, rid):
        r = self._mgr.get_backup_by_id(rid)
        cfg = self._mgr.restore_backup(rid)
        if cfg is None:
            self.hint.setText("⚠ 备份文件缺失")
            return
        dlg = BaseDialog(f"备份内容：{r.device_name} {r.backup_time}", "", self,
                         min_width=760, min_height=540, scrollable=True)
        from PyQt5.QtWidgets import QTextEdit
        body = QTextEdit()
        body.setReadOnly(True)
        body.setStyleSheet(f"""
            { _MONO } font-size: 12px; background: #1E2430;
            border: 1px solid #2C3444; border-radius: 10px; padding: 12px;
            color: #C8D3E8;
        """)
        body.setPlainText(cfg)
        dlg.content_layout().addWidget(body, 1)
        dlg.add_close_button("关闭", "primary")
        dlg.exec_()

    def _export(self, rid):
        from PyQt5.QtWidgets import QFileDialog
        r = self._mgr.get_backup_by_id(rid)
        path, _ = QFileDialog.getSaveFileName(self, "导出备份",
                                              f"{r.device_name}_{r.backup_time}.cfg".replace(":", "-").replace(" ", "_"),
                                              "配置文件 (*.cfg);;所有文件 (*)")
        if path:
            cfg = self._mgr.restore_backup(rid)
            if cfg is not None:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(cfg)
                self.hint.setText(f"✅ 已导出到 {path}")
