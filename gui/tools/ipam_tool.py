#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
IPAM 小账本工具页（工具箱内）
网段登记 / 已用标记 / 建议下一个可用 IP —— 教育城域网项目分配账本
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QComboBox, QHBoxLayout, QHeaderView, QLabel,
                             QLineEdit, QPushButton, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)

from gui.styles import CARD, BORDER, TEXT, TEXT_SUB, ACCENT
from gui import theme
from modules import ipam


class IPAMWidget(QWidget):
    """IPAM 小账本：网段 · 已用 · 用途"""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(12)

        head = QLabel("🗂 IPAM 小账本")
        head.setStyleSheet(f"font-size: 17px; font-weight: bold; color: {TEXT};")
        Lay2 = QLabel("学校网段登记与分配记录：网段 · 已用 IP · 用途——谁问『这段还有多少地址』秒回答")
        Lay2.setStyleSheet(f"font-size: 12px; color: {TEXT_SUB};")
        lay.addWidget(head)
        lay.addWidget(Lay2)

        # ---- 登记行 ----
        add_row = QHBoxLayout()
        add_row.setSpacing(8)
        self.cidr_edit = QLineEdit()
        self.cidr_edit.setPlaceholderText("网段，如 192.168.10.0/24（裸地址自动按 /24）")
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("名称（如：高一教学楼）")
        self.usage_edit = QLineEdit()
        self.usage_edit.setPlaceholderText("用途（可选，如：教学办公 AP）")
        add_btn = QPushButton("登记网段")
        add_btn.setObjectName("primaryButton")
        add_btn.clicked.connect(self._add)
        for w, s in ((self.cidr_edit, 3), (self.name_edit, 2), (self.usage_edit, 2)):
            add_row.addWidget(w, s)
        add_row.addWidget(add_btn)
        lay.addLayout(add_row)

        # ---- 网段表 ----
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["网段", "名称/用途", "已用/容量", "最近已用 IP", "操作"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 150)
        self.table.setColumnWidth(2, 110)
        self.table.setColumnWidth(3, 190)
        self.table.setColumnWidth(4, 210)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        lay.addWidget(self.table, 1)

        # ---- 标记已用行 ----
        mark_row = QHBoxLayout()
        mark_row.setSpacing(8)
        self.subnet_combo = QComboBox()
        self.subnet_combo.setMinimumWidth(180)
        self.ip_edit = QLineEdit()
        self.ip_edit.setPlaceholderText("IP（留空 = 自动建议下一个可用）")
        self.note_edit = QLineEdit()
        self.note_edit.setPlaceholderText("用途备注（如：SW-01 管理口）")
        self.mark_btn = QPushButton("标记已用")
        self.mark_btn.setObjectName("secondaryButton")
        self.mark_btn.clicked.connect(self._mark)
        mark_row.addWidget(QLabel("网段:"))
        mark_row.addWidget(self.subnet_combo, 2)
        mark_row.addWidget(self.ip_edit, 2)
        mark_row.addWidget(self.note_edit, 2)
        mark_row.addWidget(self.mark_btn)
        lay.addLayout(mark_row)

        self.hint = QLabel("")
        self.hint.setStyleSheet(f"color: {TEXT_SUB}; font-size: 12px;")
        lay.addWidget(self.hint)

        self._refresh()

    # ---------------- 数据展示 ----------------
    def _refresh(self, select_subnet=None):
        subs = ipam.list_subnets()
        self.table.setRowCount(len(subs))
        cur_sel = select_subnet or (self.subnet_combo.currentData() or "")
        self.subnet_combo.blockSignals(True)
        self.subnet_combo.clear()
        for r, s in enumerate(subs):
            self.table.setItem(r, 0, QTableWidgetItem(s["subnet"]))
            name_usage = s["name"] or "未命名"
            if s["usage"]:
                name_usage += f" · {s['usage']}"
            self.table.setItem(r, 1, QTableWidgetItem(name_usage))
            ratio = f"{s['used_n']}/{s['total']}"
            it_ratio = QTableWidgetItem(ratio)
            if s["total"] and s["used_n"] / s["total"] > 0.8:
                it_ratio.setForeground(Qt.red)      # 80% 以上标红（快满了）
            self.table.setItem(r, 2, it_ratio)
            recent = s["used"][-3:] if s["used"] else []
            recent_txt = "、".join(f"{u['ip']}" for u in reversed(recent)) or "—"
            it_recent = QTableWidgetItem(recent_txt)
            if s["used"]:
                # hover 看全部已用明细（界面只放最近 3 个，列表可以很长）
                it_recent.setToolTip("\n".join(
                    f"{u['ip']}　{u.get('note', '')}　({u.get('at', '')})"
                    for u in reversed(s["used"])))
            self.table.setItem(r, 3, it_recent)
            self.subnet_combo.addItem(s["subnet"], s["subnet"])

            # 操作列：建议可用 / 删除
            op_row = QWidget()
            op_lay = QHBoxLayout(op_row)
            op_lay.setContentsMargins(4, 2, 4, 2)
            op_lay.setSpacing(4)
            sug_btn = QPushButton("建议可用")
            sug_btn.setStyleSheet(
                f"QPushButton {{ padding: 4px 10px; font-size: 12px; border: 1px solid {BORDER};"
                f" border-radius: 8px; background: {CARD}; color: {TEXT}; }}"
                f"QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}")
            sug_btn.setCursor(Qt.PointingHandCursor)
            sug_btn.clicked.connect(lambda _=False, c=s["subnet"]: self._suggest(c))
            del_btn = QPushButton("删除")
            del_btn.setStyleSheet(
                "QPushButton { padding: 4px 10px; font-size: 12px; border: none;"
                " border-radius: 8px; background: transparent; color: #FA5151; }"
                "QPushButton:hover { background: #FDEEEE; }")
            del_btn.setCursor(Qt.PointingHandCursor)
            del_btn.clicked.connect(lambda _=False, c=s["subnet"]: self._del(c))
            op_lay.addWidget(sug_btn)
            op_lay.addWidget(del_btn)
            op_lay.addStretch()
            self.table.setCellWidget(r, 4, op_row)

        if cur_sel:
            i = self.subnet_combo.findData(cur_sel)
            if i >= 0:
                self.subnet_combo.setCurrentIndex(i)
        self.subnet_combo.blockSignals(False)

    # ---------------- 动作 ----------------
    def _add(self):
        r = ipam.add_subnet(self.cidr_edit.text(), self.name_edit.text(),
                            self.usage_edit.text())
        if not r.get("ok"):
            self.hint.setText(f"⚠ {r.get('error', '登记失败')}")
            return
        self.hint.setText(f"✅ 已登记 {r['record']['subnet']}")
        for w in (self.cidr_edit, self.name_edit, self.usage_edit):
            w.clear()
        self._refresh(select_subnet=r["record"]["subnet"])

    def _del(self, cidr):
        if ipam.remove_subnet(cidr):
            self.hint.setText(f"已删除 {cidr}")
            self._refresh()

    def _suggest(self, cidr):
        ip = ipam.suggest_free(cidr)
        if not ip:
            self.hint.setText(f"⚠ {cidr} 没有可用地址了")
            return
        # 建议直接填进标记行（顺手点「标记已用」完成分配）
        i = self.subnet_combo.findData(cidr)
        if i >= 0:
            self.subnet_combo.setCurrentIndex(i)
        self.ip_edit.setText(ip)
        self.ip_edit.setFocus()
        self.hint.setText(f"💡 {cidr} 建议下一个可用：{ip}（已填入标记行，补用途后点「标记已用」）")

    def _mark(self):
        cidr = self.subnet_combo.currentData()
        if not cidr:
            self.hint.setText("⚠ 请先选择网段（还没登记过就先登记一个）")
            return
        ip = self.ip_edit.text().strip()
        if not ip:
            ip = ipam.suggest_free(cidr)
            if not ip:
                self.hint.setText(f"⚠ {cidr} 没有可用地址了")
                return
            self.ip_edit.setText(ip)
        r = ipam.mark_ip(cidr, ip, self.note_edit.text())
        if not r.get("ok"):
            self.hint.setText(f"⚠ {r.get('error', '标记失败')}")
            return
        verb = "更新备注" if r.get("updated") else "已标记"
        self.hint.setText(f"✅ {verb}：{ip}（{self.note_edit.text() or '未填用途'}）")
        self.ip_edit.clear()
        self.note_edit.clear()
        self._refresh(select_subnet=cidr)
