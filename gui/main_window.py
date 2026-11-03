#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
交换机配置生成器 - 主窗口 v3.0
支持华为/H3C配置生成，集成网络工具箱
"""

from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QTabWidget, QPushButton, QTextEdit, QLabel,
                             QMessageBox, QFileDialog, QSplitter, QStatusBar,
                             QDialog, QListWidget, QDialogButtonBox, QMenu, QAction,
                             QComboBox, QMenuBar)
from PyQt5.QtCore import Qt, QPoint, QEvent, QObject
from PyQt5.QtGui import QFont, QIcon, QPainter, QColor, QCursor, QGuiApplication

from gui.styles import MODERN_STYLE, TOOLTIP_STYLE, DIALOG_STYLE, BG
from gui.title_bar import FramelessTitleBar
from gui.tabs.basic_tab import BasicConfigTab
from gui.tabs.vlan_tab import VLANConfigTab
from gui.tabs.routing_tab import RoutingConfigTab
from gui.tabs.security_tab import SecurityConfigTab
from gui.tabs.interface_tab import InterfaceConfigTab
from gui.tabs.device_ops_tab import DeviceOpsTab
from gui.tabs.console_viz_tab import ConsoleVizTab
from utils.templates import get_template_names, get_template_config
from utils.validator import ConfigValidator


HUAWEI_TEMPLATES = {
    "接入交换机标准配置": {
        "description": "企业接入层交换机标准配置模板",
        "config": {
            "basic": {
                "hostname": "Access-SW-01",
                "password": {"value": "Admin@123", "encrypted": True},
                "mgmt_interface": {
                    "interface": "Vlanif1",
                    "ip_address": "192.168.1.1",
                    "mask": "255.255.255.0",
                    "gateway": "192.168.1.254"
                },
                "enable_ssh": True,
                "user": {"username": "admin", "password": "Admin@123", "level": 15}
            },
            "vlan": {
                "vlans": [{"id": 1, "name": "Management"}, {"id": 10, "name": "Sales"}]
            }
        }
    }
}

H3C_TEMPLATES = {
    "接入交换机标准配置": {
        "description": "H3C接入层交换机标准配置模板",
        "config": {
            "basic": {
                "hostname": "Access-SW-01",
                "password": {"value": "Admin@123", "encrypted": True},
                "mgmt_interface": {
                    "interface": "Vlan-interface1",
                    "ip_address": "192.168.1.1",
                    "mask": "255.255.255.0",
                    "gateway": "192.168.1.254"
                },
                "enable_ssh": True,
                "user": {"username": "admin", "password": "Admin@123", "level": 3}
            }
        }
    },
    "核心交换机配置": {
        "description": "H3C核心层交换机配置模板",
        "config": {
            "basic": {
                "hostname": "Core-SW-01",
                "password": {"value": "CoreAdmin@123", "encrypted": True},
                "mgmt_interface": {
                    "interface": "Vlan-interface1",
                    "ip_address": "10.0.0.1",
                    "mask": "255.255.255.0"
                },
                "enable_ssh": True,
                "user": {"username": "admin", "password": "CoreAdmin@123", "level": 3}
            }
        }
    }
}


class TemplateDialog(QDialog):
    """模板选择对话框"""
    
    def __init__(self, device_type="huawei", parent=None):
        super().__init__(parent)
        self.selected_template = None
        self.device_type = device_type
        self.initUI()
    
    def initUI(self):
        self.setWindowTitle(f"选择{'华为' if self.device_type == 'huawei' else 'H3C'}配置模板")
        self.setFixedSize(500, 400)
        self.setStyleSheet(MODERN_STYLE + DIALOG_STYLE)
        
        layout = QVBoxLayout(self)
        
        label = QLabel("请选择一个预设模板快速生成配置：")
        label.setStyleSheet("font-size: 14px; font-weight: bold; padding: 10px; color: #1F2A37;")
        layout.addWidget(label)
        
        self.template_list = QListWidget()
        
        if self.device_type == "huawei":
            templates = get_template_names()
        else:
            templates = list(H3C_TEMPLATES.keys())
        
        for name in templates:
            self.template_list.addItem(name)
        
        self.template_list.setStyleSheet("font-size: 13px;")
        self.template_list.currentRowChanged.connect(self.on_selection_changed)
        layout.addWidget(self.template_list)
        
        self.desc_label = QLabel("选择模板查看描述")
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet("font-size: 12px; padding: 10px; color: #8a8a9e;")
        layout.addWidget(self.desc_label)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def on_selection_changed(self, row):
        if self.device_type == "huawei":
            from utils.templates import get_template_description
            template_names = get_template_names()
            if 0 <= row < len(template_names):
                desc = get_template_description(template_names[row])
                self.desc_label.setText(desc)
        else:
            template_names = list(H3C_TEMPLATES.keys())
            if 0 <= row < len(template_names):
                desc = H3C_TEMPLATES[template_names[row]]["description"]
                self.desc_label.setText(desc)


class MainWindow(QMainWindow):
    """主窗口"""
    
    def __init__(self):
        self.current_device_type = "huawei"
        self.h3c_tabs = {}
        super().__init__()
        self.initUI()
    
    def initUI(self):
        self.setWindowTitle("NetOps Toolkit v4.0 - 网络运维工具集")
        self.setMinimumSize(1024, 640)
        # 窗口尺寸：默认 1200x740（约7成屏）；用户拖动调整过的尺寸会被记住（key: window_geometry）
        # 比例法在不同 DPI 感知模式下结果漂移，故用绝对默认值 + 记忆用户尺寸代替
        geo = self._restore_geometry()
        if geo is None:
            self.resize(1200, 740)
        # 无边框圆角窗口（二开：现代标题栏，对标桌面管家类工具）
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window | Qt.WindowSystemMenuHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setStyleSheet(MODERN_STYLE + TOOLTIP_STYLE)
        
        self.createMenuBar()
        
        # 自定义标题栏 + 菜单栏融合（menuBar 位于标题栏正下方）
        self.title_bar = FramelessTitleBar("NetOps Toolkit", self)
        title_container = QWidget()
        title_v = QVBoxLayout(title_container)
        title_v.setContentsMargins(0, 0, 0, 0)
        title_v.setSpacing(0)
        title_v.addWidget(self.title_bar)
        title_v.addWidget(self.menuBar())
        self.setMenuWidget(title_container)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(20)
        
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(4, 0, 0, 8)
        header_layout.setSpacing(16)
        
        self.header_label = QLabel("华为交换机配置脚本生成工具")
        self.header_label.setStyleSheet("""
            font-size: 26px;
            font-weight: bold;
            color: #1F2A37;
            padding: 4px;
            background: transparent;
        """)
        self.header_label.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(self.header_label, 1)
        
        device_widget = QWidget()
        device_layout = QHBoxLayout(device_widget)
        device_layout.setContentsMargins(15, 0, 0, 0)
        device_layout.setSpacing(10)
        
        device_label = QLabel("设备品牌")
        device_label.setStyleSheet("font-weight: bold; color: #5A6B7B; font-size: 14px;")
        device_layout.addWidget(device_label)
        
        self.device_combo = QComboBox()
        self.device_combo.addItems(["华为 (Huawei)", "华三 (H3C)", "锐捷 (Ruijie)", "迈普 (Maipu)"])
        self.device_combo.currentIndexChanged.connect(self.on_device_changed)
        self.device_combo.setMinimumWidth(160)
        device_layout.addWidget(self.device_combo)
        
        header_layout.addWidget(device_widget)
        
        version_label = QLabel("v4.0")
        version_label.setStyleSheet("""
            font-size: 13px;
            font-weight: bold;
            color: #ffffff;
            padding: 6px 14px;
            background: #0089FF;
            border-radius: 11px;
        """)
        header_layout.addWidget(version_label)
        
        main_layout.addWidget(header_widget)
        
        content_splitter = QSplitter(Qt.Horizontal)
        content_splitter.setHandleWidth(3)
        
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)
        
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabPosition(QTabWidget.North)
        # 标准（非 document）模式：tab 栏带安全内边距，tab 过多时出滚动箭头而不是裁切首 tab
        self.tab_widget.setUsesScrollButtons(True)
        self.tab_widget.setElideMode(Qt.ElideNone)
        
        self.tabs = {
            "basic": BasicConfigTab(),
            "vlan": VLANConfigTab(),
            "routing": RoutingConfigTab(),
            "security": SecurityConfigTab(),
            "interface": InterfaceConfigTab(),
            "device_ops": DeviceOpsTab(),
            "console_viz": ConsoleVizTab()
        }

        def scroll_wrap(widget):
            """tab 内容包滚动区：视口装不下时出滚动条（横向纵向皆可滚动），
            绝不允许压缩表单卡片（防文字叠印/横向截断）"""
            from PyQt5.QtWidgets import QScrollArea, QFrame, QGroupBox, QLineEdit, QSpinBox, QComboBox
            # 1) 输入控件设最小宽：保证占位提示/输入内容读得清（150px ≈ 12 汉字占位）
            for editor in widget.findChildren(QLineEdit):
                editor.setMinimumWidth(150)
            for sp in widget.findChildren(QSpinBox):
                sp.setMinimumWidth(110)
            for cb in widget.findChildren(QComboBox):
                cb.setMinimumWidth(130)
            # 2) 双栏页的左右面板设最小宽：每栏表单不被压扁
            for panel in widget.findChildren(QWidget):
                lay = panel.layout()
                if lay is None:
                    continue
                if lay.count() and any(lay.itemAt(i) and isinstance(lay.itemAt(i).widget(), QGroupBox)
                                        for i in range(lay.count())):
                    panel.setMinimumWidth(300)
            area = QScrollArea()
            area.setWidget(widget)
            area.setWidgetResizable(True)
            area.setFrameShape(QFrame.NoFrame)
            area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            area.setStyleSheet("QScrollArea { background: transparent; border: none; }")
            return area

        self.tab_widget.addTab(scroll_wrap(self.tabs["basic"]), "基础配置")
        self.tab_widget.addTab(scroll_wrap(self.tabs["vlan"]), "VLAN配置")
        self.tab_widget.addTab(scroll_wrap(self.tabs["routing"]), "路由配置")
        self.tab_widget.addTab(scroll_wrap(self.tabs["security"]), "安全配置")
        self.tab_widget.addTab(scroll_wrap(self.tabs["interface"]), "接口配置")
        self.tab_widget.addTab(scroll_wrap(self.tabs["device_ops"]), "设备运维")
        self.tab_widget.addTab(self.tabs["console_viz"], "Console 可视化")
        
        left_layout.addWidget(self.tab_widget)
        
        button_widget = QWidget()
        button_layout = QHBoxLayout(button_widget)
        button_layout.setSpacing(12)
        button_layout.setContentsMargins(5, 10, 5, 5)
        
        template_btn = QPushButton("配置模板")
        template_btn.setObjectName("ghostButton")
        template_btn.setToolTip("选择预设配置模板 (Ctrl+L)")
        template_btn.clicked.connect(self.show_template_dialog)
        button_layout.addWidget(template_btn)
        
        validate_btn = QPushButton("验证配置")
        validate_btn.setObjectName("ghostButton")
        validate_btn.setToolTip("验证当前配置参数")
        validate_btn.clicked.connect(self.validate_config)
        button_layout.addWidget(validate_btn)
        
        generate_btn = QPushButton("生成配置")
        generate_btn.setObjectName("primaryButton")
        generate_btn.setToolTip("生成完整配置脚本 (Ctrl+G)")
        generate_btn.clicked.connect(self.generate_config)
        button_layout.addWidget(generate_btn)
        
        clear_btn = QPushButton("清空")
        clear_btn.setObjectName("dangerButton")
        clear_btn.setToolTip("清空所有配置项")
        clear_btn.clicked.connect(self.clear_config)
        button_layout.addWidget(clear_btn)
        
        # 预览区折叠按钮：窄屏时收起给左侧表单让位（QQ管家式侧栏收纳）
        self.toggle_preview_btn = QPushButton("⟩ 收起预览")
        self.toggle_preview_btn.setObjectName("ghostButton")
        self.toggle_preview_btn.setToolTip("收起/展开右侧配置预览区，收起后左侧表单区更宽")
        self.toggle_preview_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.toggle_preview_btn.clicked.connect(self.toggle_preview_panel)
        button_layout.addWidget(self.toggle_preview_btn)
        
        left_layout.addWidget(button_widget)
        
        content_splitter.addWidget(left_widget)
        
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)
        
        preview_header = QHBoxLayout()
        preview_label = QLabel("配置预览")
        preview_label.setStyleSheet("""
            font-size: 18px;
            font-weight: bold;
            color: #1F2A37;
            padding: 4px;
        """)
        preview_header.addWidget(preview_label)
        
        preview_header.addStretch()
        
        self.info_label = QLabel("")
        self.info_label.setStyleSheet("font-size: 12px; color: rgba(224, 224, 224, 0.7);")
        preview_header.addWidget(self.info_label)
        
        right_layout.addLayout(preview_header)
        
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setStyleSheet("""
            font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
            font-size: 14px;
            line-height: 1.65;
            background: #1E2430;
            border: 1px solid #2C3444;
            border-radius: 16px;
            padding: 14px;
            color: #C8D3E8;
            selection-background-color: #0089FF;
            selection-color: #ffffff;
        """)
        self.preview_text.setPlaceholderText("← 在左侧填写参数，点击「生成配置」后，完整配置将在这里输出\n\n生成的配置可直接复制上设备，或用「设备运维」页下发到真机")
        self.preview_text.textChanged.connect(self.update_info)
        right_layout.addWidget(self.preview_text, 1)
        
        export_widget = QWidget()
        export_layout = QHBoxLayout(export_widget)
        export_layout.setSpacing(12)
        export_layout.setContentsMargins(5, 10, 5, 5)
        
        export_btn = QPushButton("导出文件")
        export_btn.setObjectName("secondaryButton")
        export_btn.setToolTip("导出配置到文件")
        export_btn.clicked.connect(self.export_config)
        export_layout.addWidget(export_btn)
        
        copy_btn = QPushButton("复制配置")
        copy_btn.setObjectName("secondaryButton")
        copy_btn.setToolTip("复制配置到剪贴板 (Ctrl+C)")
        copy_btn.clicked.connect(self.copy_to_clipboard)
        export_layout.addWidget(copy_btn)
        
        export_layout.addStretch()
        
        right_layout.addWidget(export_widget)
        
        content_splitter.addWidget(right_widget)
        self.content_splitter = content_splitter
        self.right_widget = right_widget
        content_splitter.setStretchFactor(0, 3)
        content_splitter.setStretchFactor(1, 2)
        content_splitter.setSizes([900, 520])
        
        main_layout.addWidget(content_splitter, 1)
        
        self.statusBar().showMessage("就绪 | 点击「网络工具」菜单使用网络工具箱")
        self._apply_form_layout_polish()

    def _restore_geometry(self):
        """从 settings 恢复上次窗口尺寸（用户拖过的尺寸优先于默认值）"""
        try:
            from utils.settings import Settings
            s = Settings()
            saved = s.get("window_geometry", None)
            if saved and isinstance(saved, (list, tuple)) and len(saved) == 4:
                from PyQt5.QtCore import QRect
                r = QRect(*[int(v) for v in saved])
                screen = QGuiApplication.primaryScreen()
                if screen is not None:
                    avail = screen.availableGeometry()
                    # 带回屏幕内 & 不小于最小尺寸
                    r = r.intersected(avail)
                    if r.width() >= self.minimumWidth() and r.height() >= self.minimumHeight() and r.width() > 0:
                        self.setGeometry(r)
                        return r
        except Exception:
            pass
        return None

    def closeEvent(self, event):
        """关闭时记住窗口尺寸位置"""
        try:
            from utils.settings import Settings
            g = self.geometry()
            Settings().set("window_geometry", [g.x(), g.y(), g.width(), g.height()])
        except Exception:
            pass
        super().closeEvent(event)

    def toggle_preview_panel(self):
        """折叠/展开右侧配置预览区"""
        if self.right_widget.isVisible():
            self.right_widget.hide()
            self.toggle_preview_btn.setText("⟨ 展开")
        else:
            self.right_widget.show()
            self.toggle_preview_btn.setText("⟩ 收起")

    def _apply_form_layout_polish(self):
        """统一打磨全窗口表单与卡片（一处代码覆盖所有 tab）：
        - 标签右对齐 + 按字体实际宽度自适应列宽 → 所有分组的输入框起点跨布局对齐
        - QGroupBox 轻阴影 → 卡片层次感
        """
        from PyQt5.QtWidgets import QFormLayout, QGroupBox, QLabel
        from PyQt5.QtWidgets import QGraphicsDropShadowEffect
        from PyQt5.QtGui import QFontMetrics

        # 1) 收集全窗口所有表单标签，计算统一标签列宽（最长标签宽 + 余量）
        label_width = 0
        for form in self.findChildren(QFormLayout):
            for row in range(form.rowCount()):
                item = form.itemAt(row, QFormLayout.LabelRole)
                if item is not None and isinstance(item.widget(), QLabel):
                    fm = QFontMetrics(item.widget().font())
                    text = item.widget().text()
                    if text:
                        label_width = max(label_width, fm.horizontalAdvance(text))
        label_width = max(label_width, 64) + 16  # 至少 64px，加 16px 呼吸空间

        # 2) 应用到所有表单：右对齐 + 统一列宽 + 间距
        for form in self.findChildren(QFormLayout):
            form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
            form.setFormAlignment(Qt.AlignTop | Qt.AlignHCenter)
            form.setHorizontalSpacing(14)
            form.setVerticalSpacing(13)
            for row in range(form.rowCount()):
                item = form.itemAt(row, QFormLayout.LabelRole)
                if item is not None and isinstance(item.widget(), QLabel):
                    item.widget().setFixedWidth(label_width)

        # 3) 卡片轻阴影
        for group in self.findChildren(QGroupBox):
            shadow = QGraphicsDropShadowEffect(self)
            shadow.setBlurRadius(22)
            shadow.setOffset(0, 3)
            shadow.setColor(QColor(31, 42, 55, 28))  # 墨色 11% 透明度
            group.setGraphicsEffect(shadow)

        # 4) 卡片折叠化（信息分层）：点标题收起/展开，每个 tab 默认只展开第一张卡片
        self._collapser = _GroupCollapser(self)
        for tab_key in ("basic", "vlan", "routing", "security", "interface"):
            tab = self.tabs.get(tab_key)
            if tab is None:
                continue
            groups = tab.findChildren(QGroupBox)
            for idx, group in enumerate(groups):
                if idx == 0:
                    self._collapser.mark_expanded(group)
                else:
                    self._collapser.collapse(group)
                group.installEventFilter(self._collapser)
                group.setCursor(QCursor(Qt.PointingHandCursor))
                group.setToolTip(f"{group.title()} —— 点击标题栏可展开/收起")

    
    # ---------------- 无边框窗口：圆角绘制与边缘缩放（二开新增）----------------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(BG))
        radius = 12 if not self.isMaximized() else 0
        painter.drawRoundedRect(0, 0, self.width(), self.height(), radius, radius)

    _RESIZE_MARGIN = 8
    _resize_edge = None
    _resize_start = None
    _resize_geo = None

    def _edge_at(self, pos):
        right = pos.x() >= self.width() - self._RESIZE_MARGIN
        bottom = pos.y() >= self.height() - self._RESIZE_MARGIN
        if right and bottom:
            return "rb"
        if right:
            return "r"
        if bottom:
            return "b"
        return ""

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self.isMaximized():
            edge = self._edge_at(event.pos())
            if edge:
                self._resize_edge = edge
                self._resize_start = event.globalPos()
                self._resize_geo = self.geometry()
                return
        self._resize_edge = None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resize_edge:
            diff = event.globalPos() - self._resize_start
            geo = self._resize_geo
            min_w = self.minimumSize().width()
            min_h = self.minimumSize().height()
            if "r" in self._resize_edge:
                geo.setWidth(max(min_w, geo.width() + diff.x()))
            if "b" in self._resize_edge:
                geo.setHeight(max(min_h, geo.height() + diff.y()))
            self.setGeometry(geo)
            return
        if not self.isMaximized():
            edge = self._edge_at(event.pos())
            cursors = {"rb": Qt.SizeFDiagCursor, "r": Qt.SizeHorCursor, "b": Qt.SizeVerCursor}
            self.setCursor(QCursor(cursors[edge]) if edge else Qt.ArrowCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._resize_edge = None
        super().mouseReleaseEvent(event)

    def createMenuBar(self):
        """创建菜单栏"""
        menubar = self.menuBar()
        
        file_menu = menubar.addMenu("文件(&F)")
        
        batch_action = QAction("批量配置生成", self)
        batch_action.setShortcut("Ctrl+B")
        batch_action.triggered.connect(self.open_batch_config)
        file_menu.addAction(batch_action)
        
        file_menu.addSeparator()
        
        export_action = QAction("导出配置", self)
        export_action.setShortcut("Ctrl+S")
        export_action.triggered.connect(self.export_config)
        file_menu.addAction(export_action)
        
        file_menu.addSeparator()
        
        settings_action = QAction("系统设置", self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self.open_settings)
        file_menu.addAction(settings_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("退出", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        tools_menu = menubar.addMenu("网络工具(&T)")
        
        subnet_action = QAction("子网计算器", self)
        subnet_action.triggered.connect(lambda: self.open_network_tool("subnet"))
        tools_menu.addAction(subnet_action)
        
        ping_action = QAction("Ping测试", self)
        ping_action.triggered.connect(lambda: self.open_network_tool("ping"))
        tools_menu.addAction(ping_action)
        
        port_action = QAction("端口扫描", self)
        port_action.triggered.connect(lambda: self.open_network_tool("port"))
        tools_menu.addAction(port_action)
        
        trace_action = QAction("路由跟踪", self)
        trace_action.triggered.connect(lambda: self.open_network_tool("trace"))
        tools_menu.addAction(trace_action)
        
        dns_action = QAction("DNS/Whois查询", self)
        dns_action.triggered.connect(lambda: self.open_network_tool("dns"))
        tools_menu.addAction(dns_action)
        
        http_action = QAction("HTTP状态检测", self)
        http_action.triggered.connect(lambda: self.open_network_tool("http"))
        tools_menu.addAction(http_action)
        
        mac_action = QAction("MAC地址查询", self)
        mac_action.triggered.connect(lambda: self.open_network_tool("mac"))
        tools_menu.addAction(mac_action)
        
        tools_menu.addSeparator()
        
        password_action = QAction("密码生成器", self)
        password_action.triggered.connect(lambda: self.open_network_tool("password"))
        tools_menu.addAction(password_action)
        
        encoder_action = QAction("编码转换器", self)
        encoder_action.triggered.connect(lambda: self.open_network_tool("encoder"))
        tools_menu.addAction(encoder_action)
        
        tools_menu.addSeparator()
        
        manual_action = QAction("配置命令手册", self)
        manual_action.setShortcut("Ctrl+M")
        manual_action.triggered.connect(lambda: self.open_network_tool("manual"))
        tools_menu.addAction(manual_action)
        
        tools_menu.addSeparator()
        
        compare_action = QAction("配置比较工具", self)
        compare_action.setShortcut("Ctrl+Shift+C")
        compare_action.triggered.connect(lambda: self.open_network_tool("compare"))
        tools_menu.addAction(compare_action)
        
        io_action = QAction("配置导入导出", self)
        io_action.setShortcut("Ctrl+I")
        io_action.triggered.connect(lambda: self.open_network_tool("configio"))
        tools_menu.addAction(io_action)
        
        tools_menu.addSeparator()
        
        all_tools_action = QAction("打开工具箱", self)
        all_tools_action.setShortcut("Ctrl+T")
        all_tools_action.triggered.connect(self.open_tools_window)
        tools_menu.addAction(all_tools_action)
        
        template_menu = menubar.addMenu("模板(&M)")
        
        manager_action = QAction("模板管理器", self)
        manager_action.setShortcut("Ctrl+M")
        manager_action.triggered.connect(self.open_template_manager)
        template_menu.addAction(manager_action)
        
        save_action = QAction("保存为模板", self)
        save_action.setShortcut("Ctrl+Shift+S")
        save_action.triggered.connect(self.save_as_template)
        template_menu.addAction(save_action)
        
        template_menu.addSeparator()
        
        apply_huawei_action = QAction("应用华为模板", self)
        apply_huawei_action.triggered.connect(lambda: self.quick_apply_template("huawei"))
        template_menu.addAction(apply_huawei_action)
        
        apply_h3c_action = QAction("应用H3C模板", self)
        apply_h3c_action.triggered.connect(lambda: self.quick_apply_template("h3c"))
        template_menu.addAction(apply_h3c_action)
        
        template_menu.addSeparator()
        
        import_template_action = QAction("导入模板", self)
        import_template_action.triggered.connect(self.import_template)
        template_menu.addAction(import_template_action)
        
        export_template_action = QAction("导出当前模板", self)
        export_template_action.triggered.connect(self.export_current_template)
        template_menu.addAction(export_template_action)
        
        help_menu = menubar.addMenu("帮助(&H)")
        
        about_action = QAction("关于", self)
        about_action.setShortcut("F1")
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def on_device_changed(self, index):
        """设备类型切换"""
        device_types = ["huawei", "h3c", "ruijie", "maipu"]
        self.current_device_type = device_types[index]
        
        device_names = {
            "huawei": ("华为交换机配置脚本生成工具", "华为", "Huawei"),
            "h3c": ("H3C华三交换机配置脚本生成工具", "H3C", "H3C"),
            "ruijie": ("锐捷交换机配置脚本生成工具", "锐捷", "Ruijie"),
            "maipu": ("迈普交换机配置脚本生成工具", "迈普", "Maipu")
        }
        
        title, name, _ = device_names[self.current_device_type]
        self.header_label.setText(title)
        self.setWindowTitle(f"NetOps Toolkit v4.0 - {name}配置")
        
        for tab in self.tabs.values():
            tab.clear_config()
        self.preview_text.clear()
        
        self.statusBar().showMessage(f"已切换到{name}模式", 3000)
    
    def open_network_tool(self, tool_name):
        """打开单个网络工具"""
        from gui.tools_window import NetworkToolsWindow
        from gui.tools.subnet_tool import SubnetCalculatorWidget
        from gui.tools.ping_tool import PingTestWidget
        from gui.tools.port_tool import PortScanWidget
        from gui.tools.trace_tool import TraceRouteWidget
        from gui.tools.dns_tool import DNSToolWidget
        from gui.tools.manual_tool import ManualToolWidget
        from gui.tools.config_compare_tool import ConfigCompareWidget
        from gui.tools.config_io_tool import ConfigIOWidget
        
        tool_widgets = {
            "subnet": SubnetCalculatorWidget,
            "ping": PingTestWidget,
            "port": PortScanWidget,
            "trace": TraceRouteWidget,
            "dns": DNSToolWidget,
            "manual": ManualToolWidget,
            "compare": ConfigCompareWidget,
            "configio": ConfigIOWidget
        }
        
        if tool_name in tool_widgets:
            dialog = QDialog(self)
            
            titles = {
                "subnet": "子网计算器",
                "ping": "Ping测试",
                "port": "端口扫描",
                "trace": "路由跟踪",
                "dns": "DNS工具",
                "manual": "配置命令速查手册",
                "compare": "配置比较工具",
                "configio": "配置导入导出"
            }
            
            dialog.setWindowTitle(f"{titles.get(tool_name, tool_name)}")
            dialog.setMinimumSize(800, 600)
            dialog.resize(1000, 750)
            
            dialog.setStyleSheet(MODERN_STYLE + TOOLTIP_STYLE + DIALOG_STYLE)
            
            layout = QVBoxLayout(dialog)
            layout.setContentsMargins(15, 15, 15, 15)
            layout.setSpacing(10)
            widget = tool_widgets[tool_name]()
            layout.addWidget(widget)
            
            dialog.exec_()
    
    def open_tools_window(self):
        """打开完整工具箱窗口"""
        from gui.tools_window import NetworkToolsWindow
        
        self.tools_window = NetworkToolsWindow()
        self.tools_window.show()
    
    def open_settings(self):
        """打开设置对话框"""
        from gui.dialogs import SettingsDialog
        dialog = SettingsDialog(self)
        dialog.exec_()
    
    def open_batch_config(self):
        """打开批量配置生成对话框"""
        from gui.dialogs import BatchConfigDialog
        dialog = BatchConfigDialog(self, self.current_device_type)
        dialog.exec_()
    
    def show_about(self):
        """显示关于对话框"""
        from gui.dialogs import AboutDialog
        dialog = AboutDialog(self)
        dialog.exec_()
    
    def update_info(self):
        text = self.preview_text.toPlainText()
        line_count = text.count('\n') + 1 if text else 0
        char_count = len(text)
        config_sections = text.count('#')
        self.info_label.setText(f"行数: {line_count} | 字符: {char_count} | 配置块: {config_sections // 2}")
    
    def show_template_dialog(self):
        dialog = TemplateDialog(self.current_device_type, self)
        if dialog.exec_() == QDialog.Accepted:
            if self.current_device_type == "huawei":
                template_names = get_template_names()
            else:
                template_names = list(H3C_TEMPLATES.keys())
            
            row = dialog.template_list.currentRow()
            if 0 <= row < len(template_names):
                template_name = template_names[row]
                self.load_template(template_name)
    
    def load_template(self, template_name):
        if self.current_device_type == "huawei":
            template_config = get_template_config(template_name)
        else:
            template_config = H3C_TEMPLATES.get(template_name, {}).get("config", {})
        
        if not template_config:
            QMessageBox.warning(self, "警告", f"模板 {template_name} 不存在！")
            return
        
        reply = QMessageBox.question(
            self, "加载模板",
            f"确定要加载模板 \"{template_name}\" 吗？\n这将覆盖当前所有配置。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            for tab in self.tabs.values():
                tab.clear_config()
            
            if "basic" in template_config:
                basic_tab = self.tabs["basic"]
                basic_cfg = template_config["basic"]
                if "hostname" in basic_cfg:
                    basic_tab.hostname_input.setText(basic_cfg["hostname"])
                if "password" in basic_cfg:
                    basic_tab.password_input.setText(basic_cfg["password"]["value"])
                    basic_tab.encrypted_checkbox.setChecked(basic_cfg["password"].get("encrypted", False))
                if "mgmt_interface" in basic_cfg:
                    mgmt = basic_cfg["mgmt_interface"]
                    basic_tab.mgmt_interface.setText(mgmt.get("interface", "Vlanif1"))
                    basic_tab.mgmt_ip.setText(mgmt.get("ip_address", ""))
                    basic_tab.mgmt_mask.setText(mgmt.get("mask", "255.255.255.0"))
                    basic_tab.mgmt_gateway.setText(mgmt.get("gateway", ""))
                if basic_cfg.get("enable_ssh"):
                    basic_tab.enable_ssh.setChecked(True)
                if "user" in basic_cfg:
                    user = basic_cfg["user"]
                    basic_tab.username_input.setText(user.get("username", "admin"))
                    basic_tab.user_password_input.setText(user.get("password", ""))
                    basic_tab.privilege_level.setValue(user.get("level", 15))
            
            self.statusBar().showMessage(f"已加载模板: {template_name}", 5000)
            QMessageBox.information(self, "成功", f"模板 \"{template_name}\" 已加载！")
    
    def validate_config(self):
        errors = []
        basic_tab = self.tabs["basic"]
        
        hostname = basic_tab.hostname_input.text().strip()
        if hostname:
            is_valid, msg = ConfigValidator.validate_hostname(hostname)
            if not is_valid:
                errors.append(f"主机名: {msg}")
        
        mgmt_ip = basic_tab.mgmt_ip.text().strip()
        if mgmt_ip:
            is_valid, msg = ConfigValidator.validate_ip_address(mgmt_ip)
            if not is_valid:
                errors.append(f"管理IP: {msg}")
        
        mgmt_mask = basic_tab.mgmt_mask.text().strip()
        if mgmt_mask:
            is_valid, msg = ConfigValidator.validate_subnet_mask(mgmt_mask)
            if not is_valid:
                errors.append(f"子网掩码: {msg}")
        
        if errors:
            error_msg = "配置验证失败：\n\n" + "\n".join(f"• {e}" for e in errors)
            QMessageBox.warning(self, "验证失败", error_msg)
            self.statusBar().showMessage(f"验证失败: {len(errors)} 个错误", 5000)
        else:
            QMessageBox.information(self, "验证通过", "所有配置参数格式正确！")
            self.statusBar().showMessage("验证通过", 3000)
    
    def generate_config(self):
        all_config = []
        
        device_headers = {
            "huawei": ("华为交换机配置脚本", "huawei"),
            "h3c": ("H3C华三交换机配置脚本", "h3c"),
            "ruijie": ("锐捷交换机配置脚本", "ruijie"),
            "maipu": ("迈普交换机配置脚本", "maipu")
        }
        
        basic_config = self.tabs["basic"].get_config()
        if basic_config:
            all_config.append(basic_config)
        
        vlan_config = self.tabs["vlan"].get_config()
        if vlan_config:
            all_config.append(vlan_config)
        
        routing_config = self.tabs["routing"].get_config()
        if routing_config:
            all_config.append(routing_config)
        
        security_config = self.tabs["security"].get_config()
        if security_config:
            all_config.append(security_config)
        
        interface_config = self.tabs["interface"].get_config()
        if interface_config:
            all_config.append(interface_config)
        
        if not all_config:
            QMessageBox.warning(self, "警告", "请至少配置一个模块！")
            return
        
        full_config = "\n".join(all_config)
        
        header_title, _ = device_headers.get(self.current_device_type, device_headers["huawei"])
        header = f"""#
# {header_title}
# 生成时间: {__import__('time').strftime('%Y-%m-%d %H:%M:%S')}
#

"""
        
        if self.current_device_type == "h3c":
            full_config = full_config.replace("Vlanif", "Vlan-interface")
        
        self.preview_text.setPlainText(header + full_config)
        self.statusBar().showMessage("配置生成成功！", 3000)
        QMessageBox.information(self, "成功", "配置生成成功！")
    
    def export_config(self):
        config_text = self.preview_text.toPlainText()
        if not config_text:
            QMessageBox.warning(self, "警告", "请先生成配置！")
            return
        
        default_name = f"{self.current_device_type}_switch_config.txt"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存配置文件", default_name,
            "配置文件 (*.txt);;脚本文件 (*.cfg);;所有文件 (*)"
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(config_text)
                self.statusBar().showMessage(f"配置已导出到: {file_path}", 5000)
                QMessageBox.information(self, "成功", f"配置已导出到：\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"导出失败：\n{str(e)}")
    
    def copy_to_clipboard(self):
        config_text = self.preview_text.toPlainText()
        if not config_text:
            QMessageBox.warning(self, "警告", "请先生成配置！")
            return
        
        from PyQt5.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(config_text)
        
        self.statusBar().showMessage("配置已复制到剪贴板", 3000)
        QMessageBox.information(self, "成功", "配置已复制到剪贴板！")
    
    def clear_config(self):
        reply = QMessageBox.question(
            self, "确认", "确定要清空所有配置吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            for tab in self.tabs.values():
                tab.clear_config()
            self.preview_text.clear()
            self.statusBar().showMessage("配置已清空", 3000)
    
    def open_template_manager(self):
        from gui.dialogs.template_dialog import TemplateManagerDialog
        
        dialog = TemplateManagerDialog(self, self.current_device_type)
        dialog.template_selected.connect(self.apply_template_config)
        dialog.exec_()
    
    def apply_template_config(self, template_data):
        config = template_data.get("config", {})
        
        if "basic" in config and "basic" in self.tabs:
            self.tabs["basic"].load_config(config["basic"])
        if "vlan" in config and "vlan" in self.tabs:
            self.tabs["vlan"].load_config(config["vlan"])
        if "routing" in config and "routing" in self.tabs:
            self.tabs["routing"].load_config(config["routing"])
        if "security" in config and "security" in self.tabs:
            self.tabs["security"].load_config(config["security"])
        if "interface" in config and "interface" in self.tabs:
            self.tabs["interface"].load_config(config["interface"])
        
        self.statusBar().showMessage(f"已应用模板: {template_data.get('name', '')}", 5000)
        QMessageBox.information(self, "成功", f"模板 '{template_data.get('name', '')}' 已应用！")
    
    def save_as_template(self):
        from gui.dialogs.template_dialog import SaveTemplateDialog
        
        config = self._collect_current_config()
        
        dialog = SaveTemplateDialog(self, config, self.current_device_type)
        dialog.exec_()
    
    def _collect_current_config(self):
        config = {}
        
        if "basic" in self.tabs:
            config["basic"] = self.tabs["basic"].get_config_data()
        if "vlan" in self.tabs:
            config["vlan"] = self.tabs["vlan"].get_config_data()
        if "routing" in self.tabs:
            config["routing"] = self.tabs["routing"].get_config_data()
        if "security" in self.tabs:
            config["security"] = self.tabs["security"].get_config_data()
        if "interface" in self.tabs:
            config["interface"] = self.tabs["interface"].get_config_data()
        
        return config
    
    def quick_apply_template(self, device_type):
        from gui.dialogs.template_dialog import TemplateManagerDialog
        
        dialog = TemplateManagerDialog(self, device_type)
        dialog.template_selected.connect(self.apply_template_config)
        dialog.exec_()
    
    def import_template(self):
        from utils.template_manager import TemplateManager
        from PyQt5.QtWidgets import QFileDialog
        
        file_path, _ = QFileDialog.getOpenFileName(
            self, "导入模板", "", "JSON文件 (*.json)"
        )
        
        if file_path:
            manager = TemplateManager()
            if manager.import_template(file_path):
                QMessageBox.information(self, "成功", "模板导入成功！")
            else:
                QMessageBox.warning(self, "失败", "导入模板失败，请检查文件格式。")
    
    def export_current_template(self):
        from utils.template_manager import TemplateManager
        from PyQt5.QtWidgets import QInputDialog
        
        name, ok = QInputDialog.getText(self, "导出模板", "请输入模板名称:")
        if not ok or not name:
            return
        
        config = self._collect_current_config()
        manager = TemplateManager()
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出模板", f"{name}.json", "JSON文件 (*.json)"
        )
        
        if file_path:
            from utils.template_manager import Template
            template = Template(
                name=name,
                device_type=self.current_device_type,
                config=config
            )
            if manager.export_template(name, self.current_device_type, file_path):
                QMessageBox.information(self, "成功", "模板导出成功！")
            else:
                QMessageBox.warning(self, "失败", "导出模板失败。")



class _GroupCollapser(QObject):
    """QGroupBox 折叠管理器：点击标题区切换收起/展开（不改动各 tab 源码）"""

    COLLAPSED_MARK = " ▸"
    EXPANDED_MARK = " ▾"
    TITLE_ZONE = 40  # QSS 中标题位于 padding 顶部 36px 区，点击命中判定线
    COLLAPSED_HEIGHT = 44

    def __init__(self, parent=None):
        super().__init__(parent)
        self._expanded = set()  # id(QGroupBox) 集合

    # ---- 状态 ----
    def is_expanded(self, group):
        return id(group) in self._expanded

    def mark_expanded(self, group):
        self._expanded.add(id(group))
        self._set_title(group, self.EXPANDED_MARK)

    # ---- 切换 ----
    def collapse(self, group):
        from PyQt5.QtWidgets import QWidget
        for child in group.findChildren(QWidget):
            child.hide()
        group.setMaximumHeight(self.COLLAPSED_HEIGHT)
        self._expanded.discard(id(group))
        self._set_title(group, self.COLLAPSED_MARK)

    def expand(self, group):
        from PyQt5.QtWidgets import QWidget
        group.setMaximumHeight(16777215)  # QWIDGETSIZE_MAX
        for child in group.findChildren(QWidget):
            child.show()
        self._expanded.add(id(group))
        self._set_title(group, self.EXPANDED_MARK)

    def toggle(self, group):
        if self.is_expanded(group):
            self.collapse(group)
        else:
            self.expand(group)

    def _set_title(self, group, mark):
        base = group.title().replace(self.COLLAPSED_MARK, "").replace(self.EXPANDED_MARK, "")
        group.setTitle(base + mark)

    # ---- 事件过滤：标题区点击 ----
    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonRelease:
            if 0 <= event.pos().y() <= self.TITLE_ZONE:
                self.toggle(obj)
                return True
        return super().eventFilter(obj, event)
