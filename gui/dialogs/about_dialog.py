#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
关于对话框
"""

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QTabWidget, QWidget, QTextBrowser)
from PyQt5.QtCore import Qt

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from gui.styles import MODERN_STYLE, TOOLTIP_STYLE, DIALOG_STYLE, ACCENT, TEXT, TEXT_SUB


class AboutDialog(QDialog):
    """关于对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()

    def initUI(self):
        self.setWindowTitle("关于 NetOps Toolkit")
        self.setFixedSize(560, 460)
        self.setStyleSheet(MODERN_STYLE + TOOLTIP_STYLE + DIALOG_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(14)

        # ---------- 头部 ----------
        header = QHBoxLayout()
        header.setSpacing(14)

        logo = QLabel("N")
        logo.setFixedSize(44, 44)
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet(
            f"background: {ACCENT}; color: #FFFFFF; border-radius: 12px;"
            "font-size: 22px; font-weight: bold;")
        header.addWidget(logo)

        info = QVBoxLayout()
        info.setSpacing(2)
        title = QLabel("NetOps Toolkit")
        title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {TEXT};")
        info.addWidget(title)
        version = QLabel("版本 4.0 · 网络运维工具集")
        version.setStyleSheet(f"color: {TEXT_SUB}; font-size: 12px;")
        info.addWidget(version)
        header.addLayout(info)
        header.addStretch()
        layout.addLayout(header)

        # ---------- 分页 ----------
        tabs = QTabWidget()
        tabs.addTab(self._page(_ABOUT_HTML), "关于")
        tabs.addTab(self._page(_FEATURE_HTML), "功能")
        tabs.addTab(self._page(_CREDIT_HTML), "致谢")
        layout.addWidget(tabs, 1)

        # ---------- 底部 ----------
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok_btn = QPushButton("确定")
        ok_btn.setObjectName("primaryButton")
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

    @staticmethod
    def _page(html):
        """用 QTextBrowser 而不是 QLabel：内容超长时可滚动，不会把文字裁掉"""
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        browser = QTextBrowser()
        browser.setHtml(html)
        browser.setOpenExternalLinks(True)
        browser.setStyleSheet("QTextBrowser { border: none; background: transparent; }")
        v.addWidget(browser)
        return w


_ABOUT_HTML = f"""
<div style="font-size:13px; color:{TEXT}; line-height:1.9;">
<p><b>NetOps Toolkit</b> 是一款面向内网的交换机运维桌面工具，覆盖
「配置生成 → 真机采集 → 拓扑还原 → 配置下发/备份」的完整闭环。</p>
<p><b>配置生成：</b>华为、H3C、锐捷、迈普四个品牌，按厂商自动适配命令格式。</p>
<p><b>Console 采集：</b>插线即可只读抓取 running-config 与 LLDP / MAC / ARP /
端口状态，自动识别华为、H3C、锐捷、迈普、思科。</p>
<p><b>离线优先：</b>核心流程零网络调用，无遥测、无更新检查，断网可用。</p>
</div>
"""

_FEATURE_HTML = f"""
<div style="font-size:13px; color:{TEXT}; line-height:1.9;">
<p><b>配置</b></p>
<ul style="margin-left:18px;">
<li>基础 / 接口 / VLAN / 路由 / 安全 / 高级配置，命中多厂商语法</li>
<li>模板管理、批量生成（CSV）、配置比较、语法纠错、跨厂商转换</li>
<li>命令释义：预览区逐行中文注释，复制与下发始终走纯命令</li>
</ul>
<p><b>真机运维</b></p>
<ul style="margin-left:18px;">
<li>设备清单（凭据本地加密）、连通测试、命令执行、配置下发</li>
<li>配置备份：版本化 + Diff，回滚有据可查</li>
</ul>
<p><b>可视化</b></p>
<ul style="margin-left:18px;">
<li>Console 分层配置树 + 配置健康度体检</li>
<li>网络拓扑自动成图：邻居、终端、哑交换机如实标注</li>
</ul>
<p><b>网络工具箱</b>：子网计算、Ping、端口扫描、路由跟踪、DNS/Whois、
HTTP 检测、MAC 查询、密码生成、编码转换等 20+ 个工具。</p>
</div>
"""

_CREDIT_HTML = f"""
<div style="font-size:13px; color:{TEXT}; line-height:1.9;">
<p><b>开发框架</b><br>Python 3 + PyQt5</p>
<p><b>开源依赖</b><br>netmiko、paramiko、pyserial、cryptography、requests、dnspython</p>
<p><b>上游项目</b><br>
基于 MIT 协议的
<a href="https://gitee.com/cooltea521/NetOps-toolkit" style="color:{ACCENT};">cooltea521/NetOps-toolkit</a>
二次开发，保留原始版权声明。</p>
<p style="color:{TEXT_SUB};">本工具为运维辅助软件，配置下发前请在测试设备验证。</p>
</div>
"""
