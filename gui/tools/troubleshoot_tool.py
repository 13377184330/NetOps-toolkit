#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
排错 · 保存 · 重置命令速查（工具箱，对标 NetCMD 的「排错/重置命令」并扩展）
- 日常排错：全部只读命令，放心敲
- 配置保存：保存 / 备份命令
- 重置高危：⚠ 会动配置/重启设备的命令，红字警示
- 紧急恢复：忘密码时的 BootROM 恢复流程（Console 线操作步骤）
每条命令带独立「复制」按钮；纯速查工具，不连接任何设备
"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel,
                             QPushButton, QScrollArea, QVBoxLayout, QWidget)

VENDOR_KEYS = ("huawei", "h3c", "ruijie", "maipu", "cisco")
VENDOR_CN = {"huawei": "华为", "h3c": "H3C", "ruijie": "锐捷",
             "maipu": "迈普", "cisco": "思科"}


def _build_cmds():
    """按厂商组织命令数据；共享部分用函数生成，避免五份重复维护"""
    data = {}
    for v in VENDOR_KEYS:
        vrp = v in ("huawei", "h3c")
        d = vrp and (v == "h3c")          # d = 华三特有差异
        ios = not vrp

        daily = [
            ("display version" if vrp else "show version", "查看软件版本与运行时长"),
            ("display current-configuration" if vrp else "show running-config", "查看当前运行配置"),
            ("display interface brief" if vrp else "show interface status", "所有端口状态一览（up/down/速率）"),
            ("display mac-address" if vrp else "show mac address-table", "MAC 地址表（谁接在哪个口）"),
            ("display arp" if vrp else "show arp", "ARP 表（IP 与 MAC 对应）"),
            ("display lldp neighbor brief" if v == "huawei"
             else ("display lldp neighbor-information verbose" if v == "h3c" else "show lldp neighbors"),
             "LLDP 邻居（上联/对端是谁）"),
            ("display vlan summary" if v == "huawei"
             else ("display vlan brief" if v == "h3c" else "show vlan brief"), "VLAN 一览"),
            ("display ip routing-table" if vrp else "show ip route", "路由表"),
            ("display stp brief" if vrp else "show spanning-tree summary", "生成树端口角色"),
            ("display link-aggregation summary" if v == "h3c"
             else ("display eth-trunk" if v == "huawei" else "show etherchannel summary"), "链路聚合状态"),
            ("display cpu-usage" if vrp else "show processes cpu", "CPU 使用率"),
            ("display memory-usage" if v == "huawei"
             else ("display memory" if v == "h3c" else "show memory"), "内存使用率"),
            ("display logbuffer" if vrp else "show logging", "设备日志（排错第一现场）"),
            ("display alarm" if vrp else "show facility-alarm status", "当前告警"),
            ("display transceiver interface" if vrp else "show interface transceiver", "光模块信息（光功率/型号）"),
            ("display users" if vrp else "show users", "当前在线登录用户"),
        ]
        save = [
            ("save" if vrp else "write memory", "保存当前配置到启动配置"),
            ("copy current-configuration tftp://192.168.1.100/sw.cfg" if v == "h3c"
             else ("tftp 192.168.1.100 put vrpcfg.zip" if v == "huawei"
                   else "copy running-config tftp://192.168.1.100/sw.cfg"), "备份配置到 TFTP 服务器"),
        ]
        danger = [
            ("reset saved-configuration" if vrp
             else ("delete flash:config.text" if v in ("ruijie", "maipu") else "erase startup-config"),
             "⚠ 清空启动配置（下次重启恢复出厂，不可撤销）"),
            ("reboot" if vrp else "reload", "⚠ 立即重启设备"),
        ]
        if v == "huawei":
            danger.append(("reboot fast", "⚠ 快速重启（不等保存，仅紧急情况）"))
        recovery = {
            "huawei": ["1. Console 线连接设备，重启设备",
                       "2. 启动提示 Press Ctrl+B 时按 Ctrl+B 进 BootROM 主菜单",
                       "3. 选 Clear password for console user（清除 Console 密码）",
                       "4. 等设备重启后直接进系统视图，重新设置密码",
                       "5. 改完 save 保存，避免下次还要清"],
            "h3c": ["1. Console 线连接设备，重启设备",
                    "2. 出现 Press Ctrl+B 时按 Ctrl+B 进 BootWare 菜单",
                    "3. 选 Skip current configuration file（本次启动跳过配置）",
                    "4. 进系统后 display saved-configuration 摘出原配置",
                    "5. 重新设置密码并 save"],
            "ruijie": ["1. Console 线连接设备，重启设备",
                       "2. 按住 Ctrl+C 进 CTRL 层",
                       "3. 用 rename flash:config.text flash:config.bak 改名跳过配置",
                       "4. 设备空配置启动后 copy flash:config.bak running-config 恢复",
                       "5. 改完密码 write 保存"],
            "maipu": ["1. Console 线连接设备，重启设备",
                      "2. 启动时按 Ctrl+C 进入 Boot 菜单",
                      "3. 选择跳过加载启动配置（类似 Skip startup config）",
                      "4. 空配置启动后恢复原配置并重新设置密码",
                      "5. 改完 write 保存"],
            "cisco": ["1. Console 线连接设备，重启设备",
                      "2. 60 秒倒计时内按 Ctrl+Break 进 rommon 模式",
                      "3. 输入 confreg 0x2142（下次启动跳过启动配置）再 reset",
                      "4. 空配置启动后 no，进配置模式重新设置 enable 密码与 vty",
                      "5. config-register 0x2102 恢复寄存器，copy running-config startup-config 保存"],
        }
        data[v] = {"日常排错": daily, "配置保存": save,
                   "重置高危": danger, "紧急恢复": recovery[v]}
    return data


CMDS = _build_cmds()
CATEGORIES = ("日常排错", "配置保存", "重置高危", "紧急恢复")


class TroubleshootWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._category = "日常排错"
        self.initUI()
        self.refresh()

    def initUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(12)

        bar = QHBoxLayout()
        bar.setSpacing(10)
        bar.addWidget(QLabel("厂商:"))
        self.vendor_combo = QComboBox()
        self.vendor_combo.addItems([f"{VENDOR_CN[v]} {v.capitalize()}" for v in VENDOR_KEYS])
        self.vendor_combo.currentIndexChanged.connect(lambda _: self.refresh())
        bar.addWidget(self.vendor_combo)
        bar.addStretch(1)

        self._cat_buttons = []
        for cat in CATEGORIES:
            btn = QPushButton(cat)
            btn.setObjectName("ghostButton")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet("QPushButton:checked { color: #0089FF; border-color: #0089FF; }")
            if cat == self._category:
                btn.setChecked(True)
            btn.clicked.connect(lambda _=False, b=btn, c=cat: self._pick_category(b, c))
            self._cat_buttons.append(btn)
            bar.addWidget(btn)
        layout.addLayout(bar)

        self.warn_label = QLabel("⚠ 以下命令会修改设备或中断业务：清空配置/重启前，务必先 display current-configuration "
                                 "备份、确认变更窗口，并准备好回退方案。")
        self.warn_label.setWordWrap(True)
        self.warn_label.setStyleSheet(
            "color: #FA5151; font-size: 12px; font-weight: bold;"
            "background: #FDEEEE; border: 1px solid #F5C2C2; border-radius: 10px; padding: 8px 12px;")
        self.warn_label.setVisible(False)
        layout.addWidget(self.warn_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.list_host = QWidget()
        self.list_lay = QVBoxLayout(self.list_host)
        self.list_lay.setContentsMargins(2, 2, 2, 2)
        self.list_lay.setSpacing(8)
        self.list_lay.addStretch(1)
        scroll.setWidget(self.list_host)
        layout.addWidget(scroll, 1)

        tip = QLabel("💡 全部为只读速查与命令复制，本页不连接设备。高危命令红字标注；紧急恢复为 Console 线操作流程。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #9AA7B8; font-size: 12px;")
        layout.addWidget(tip)

    def _pick_category(self, btn, cat):
        """切换分类：互斥高亮 + 重绘列表"""
        self._category = cat
        for b in self._cat_buttons:
            b.setChecked(b is btn)
        self.refresh()

    def refresh(self):
        vendor = VENDOR_KEYS[self.vendor_combo.currentIndex()]
        cat = self._category
        self.warn_label.setVisible(cat == "重置高危")

        # 清空旧行
        while self.list_lay.count() > 1:
            item = self.list_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        entries = CMDS[vendor][cat]
        if cat == "紧急恢复":
            card = QFrame()
            card.setStyleSheet(
                "QFrame { background: #FFFFFF; border: 1px solid #DFE6F0; border-radius: 14px; }")
            lay = QVBoxLayout(card)
            lay.setContentsMargins(18, 16, 18, 16)
            lay.setSpacing(10)
            for step in entries:
                lbl = QLabel(step)
                lbl.setWordWrap(True)
                lbl.setStyleSheet("font-size: 14px; color: #1F2A37;")
                lay.addWidget(lbl)
            copy_btn = QPushButton("复制整个流程")
            copy_btn.setObjectName("secondaryButton")
            copy_btn.clicked.connect(
                lambda _=False, t="\n".join(entries): self._copy_text(t))
            lay.addWidget(copy_btn)
            self.list_lay.insertWidget(0, card)
            return

        for cmd, note in entries:
            row = QFrame()
            danger = note.startswith("⚠")
            row.setStyleSheet(
                "QFrame { background: %s; border: 1px solid %s; border-radius: 14px; }"
                % ("#FDEEEE" if danger else "#FFFFFF",
                   "#F5C2C2" if danger else "#DFE6F0"))
            lay = QHBoxLayout(row)
            lay.setContentsMargins(16, 10, 12, 10)
            lay.setSpacing(14)

            cmd_lbl = QLabel(cmd)
            cmd_lbl.setFont(QFont("JetBrains Mono, Consolas, monospace"))
            cmd_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            cmd_lbl.setStyleSheet(
                f"font-family: 'JetBrains Mono', 'Consolas', monospace; font-size: 13px;"
                f"color: {'#FA5151' if danger else '#1F2A37'}; background: transparent; border: none;")
            cmd_lbl.setToolTip(cmd)
            cmd_lbl.setMinimumWidth(380)
            lay.addWidget(cmd_lbl, 3)

            note_lbl = QLabel(note.replace("⚠ ", ""))
            note_lbl.setWordWrap(True)
            note_lbl.setStyleSheet(
                f"font-size: 12px; color: {'#FA5151' if danger else '#7A8699'};"
                "background: transparent; border: none;")
            lay.addWidget(note_lbl, 4)

            copy_btn = QPushButton("复制")
            copy_btn.setObjectName("dangerButton" if danger else "secondaryButton")
            copy_btn.setCursor(Qt.PointingHandCursor)
            copy_btn.clicked.connect(lambda _=False, t=cmd: self._copy_text(t))
            lay.addWidget(copy_btn)

            self.list_lay.insertWidget(self.list_lay.count() - 1, row)

    def _copy_text(self, text):
        from PyQt5.QtWidgets import QApplication
        QApplication.clipboard().setText(text)
