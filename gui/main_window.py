#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
交换机配置生成器 - 主窗口 v3.0
支持华为/H3C配置生成，集成网络工具箱
"""

from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QTabWidget, QPushButton, QTextEdit, QLabel,
                             QFileDialog, QSplitter, QStatusBar,
                             QListWidget, QMenu, QAction,
                             QComboBox, QMenuBar)
from PyQt5.QtCore import Qt, QPoint, QEvent, QObject
from PyQt5.QtGui import QFont, QIcon, QPainter, QColor, QCursor, QGuiApplication, QPalette

from gui.styles import MODERN_STYLE, TOOLTIP_STYLE, DIALOG_STYLE, BG
from gui.dialogs.base import BaseDialog, info_box, warn_box, error_box, question_box
from gui import theme
from gui.title_bar import FramelessTitleBar
from gui.side_nav import _SideNavWidget
from gui.tabs.basic_tab import BasicConfigTab
from gui.tabs.vlan_tab import VLANConfigTab
from gui.tabs.routing_tab import RoutingConfigTab
from gui.tabs.security_tab import SecurityConfigTab
from gui.tabs.interface_tab import InterfaceConfigTab
from gui.tabs.device_ops_tab import DeviceOpsTab
from gui.tabs.console_viz_tab import ConsoleVizTab
from gui.tabs.topology_tab import NetworkTopologyPage
from gui.tabs.adv_config_tab import AdvConfigTab
from gui.config_gen_page import ConfigGenPage
from modules import cmd_notes
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

# ---------------- 其余三厂商模板（二开补齐：五厂商全支持）----------------
def _mk_template(desc, hostname, mgmt_if, ip, pwd, ssh_user):
    return {
        "description": desc,
        "config": {
            "basic": {
                "hostname": hostname,
                "password": {"value": pwd, "encrypted": True},
                "mgmt_interface": {"interface": mgmt_if, "ip_address": ip, "mask": "255.255.255.0"},
                "enable_ssh": True,
                "user": {"username": ssh_user, "password": pwd, "level": 15},
            }
        }
    }


RUIJIE_TEMPLATES = {
    "接入交换机标准配置": _mk_template("锐捷接入层交换机标准配置模板", "Access-SW-01",
                                   "VLAN 1", "192.168.1.1", "Admin@123", "admin"),
    "核心交换机配置": _mk_template("锐捷核心层交换机配置模板", "Core-SW-01",
                                "VLAN 1", "10.0.0.1", "CoreAdmin@123", "admin"),
}

MAIPU_TEMPLATES = {
    "接入交换机标准配置": _mk_template("迈普接入层交换机标准配置模板", "Access-SW-01",
                                   "Vlan1", "192.168.1.1", "Admin@123", "admin"),
    "核心交换机配置": _mk_template("迈普核心层交换机配置模板", "Core-SW-01",
                                "Vlan1", "10.0.0.1", "CoreAdmin@123", "admin"),
}

CISCO_TEMPLATES = {
    "接入交换机标准配置": _mk_template("思科接入层交换机标准配置模板", "Access-SW-01",
                                   "Vlan1", "192.168.1.1", "Admin@123", "admin"),
    "核心交换机配置": _mk_template("思科核心层交换机配置模板", "Core-SW-01",
                                "Vlan1", "10.0.0.1", "CoreAdmin@123", "admin"),
}

# 厂商 → 模板集（模板对话框与菜单统一从这里取）
VENDOR_TEMPLATE_SETS = {
    "huawei": "HUAWEI",  # 华为走 utils.templates 动态加载
    "h3c": "H3C",
    "ruijie": "RUIJIE",
    "maipu": "MAIPU",
    "cisco": "CISCO",
}

TEMPLATE_SET_DICTS = {
    "H3C": H3C_TEMPLATES,
    "RUIJIE": RUIJIE_TEMPLATES,
    "MAIPU": MAIPU_TEMPLATES,
    "CISCO": CISCO_TEMPLATES,
}

VENDOR_CN = {"huawei": "华为", "h3c": "H3C", "ruijie": "锐捷", "maipu": "迈普", "cisco": "思科"}


def get_vendor_templates(vendor: str):
    """取某厂商的模板 {名称: {description, config}}"""
    if vendor == "huawei":
        from utils.templates import get_template_names, get_template_config
        out = {}
        for n in get_template_names():
            out[n] = {"description": f"华为{n}", "config": get_template_config(n)}
        return out
    return TEMPLATE_SET_DICTS.get(VENDOR_TEMPLATE_SETS.get(vendor, "H3C"), H3C_TEMPLATES)


class TemplateDialog(BaseDialog):
    """模板选择对话框（统一无边框子窗口骨架）"""

    def __init__(self, device_type="huawei", parent=None):
        super().__init__(f"选择{VENDOR_CN.get(device_type, '')}配置模板",
                         "请选择一个预设模板快速生成配置：",
                         parent, min_width=500, scrollable=False)
        self.selected_template = None
        self.device_type = device_type
        self.setFixedSize(500, 400)

        self.template_list = QListWidget()

        # 五厂商统一取模板集
        self._templates = get_vendor_templates(self.device_type)
        for name in self._templates.keys():
            self.template_list.addItem(name)

        self.template_list.setStyleSheet("font-size: 13px;")
        self.template_list.currentRowChanged.connect(self.on_selection_changed)
        self.add_content(self.template_list, 1)

        self.desc_label = QLabel("选择模板查看描述")
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet("font-size: 12px; padding: 10px; color: #8A95A6;")
        self.add_content(self.desc_label)

        self.add_button("确定", "primary", None)
        self.add_close_button("取消", "ghost")

    def on_selection_changed(self, row):
        names = list(self._templates.keys())
        if 0 <= row < len(names):
            self.desc_label.setText(self._templates[names[row]].get("description", ""))

    def accept(self):
        # 确定前把选中模板写回 selected_template（保持旧接口）
        row = self.template_list.currentRow()
        names = list(self._templates.keys())
        if 0 <= row < len(names):
            self.selected_template = self._templates[names[row]]
        super().accept()


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
        # 设备品牌下拉并入标题栏右侧（与右侧窗口边界同行，省一整行）
        self.device_combo = QComboBox()
        self.device_combo.addItems(["华为 Huawei", "华三 H3C", "锐捷 Ruijie", "迈普 Maipu", "思科 Cisco"])
        self.device_combo.currentIndexChanged.connect(self.on_device_changed)
        self.device_combo.setMinimumWidth(130)
        self.device_combo.setStyleSheet("""
            QComboBox { font-size: 12px; padding: 4px 10px; }
        """)
        self.title_bar.add_trailing(self.device_combo)

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
        main_layout.setContentsMargins(22, 18, 22, 18)
        main_layout.setSpacing(14)
        
        content_splitter = QSplitter(Qt.Horizontal)
        content_splitter.setHandleWidth(3)
        
        self.tab_widget = _SideNavWidget()
        # 页面映射：tab_widget.addTab(widget, title) → 导航列表 + 堆栈页
        self.tabs = {
            "basic": BasicConfigTab(),
            "vlan": VLANConfigTab(),
            "routing": RoutingConfigTab(),
            "security": SecurityConfigTab(),
            "interface": InterfaceConfigTab(),
            "adv": AdvConfigTab(),
            "device_ops": DeviceOpsTab(),
            "console_viz": ConsoleVizTab(),
            "topology": NetworkTopologyPage()
        }
        # 配置生成聚合页（配置模块收进二级导航，按使用频率排序：高频在前）
        self.config_gen_page = ConfigGenPage({
            "基础配置": self.tabs["basic"],
            "接口配置": self.tabs["interface"],
            "VLAN配置": self.tabs["vlan"],
            "路由配置": self.tabs["routing"],
            "安全配置": self.tabs["security"],
            "高级配置": self.tabs["adv"],
        })

        # 配置生成页自带子页滚动区，不再重复外包（防宽度需求叠算出横向溢出）
        self.tab_widget.addTab(self.config_gen_page, "配置生成")
        # 运维/可视化页内容较高：包滚动区（保证各卡片最小高，不被压扁）
        from gui.widget_utils import scroll_wrap as _sw
        self.tab_widget.addTab(_sw(self.tabs["device_ops"]), "设备运维")
        self.tab_widget.addTab(self.tabs["topology"], "网络拓扑")
        self.tab_widget.addTab(_sw(self.tabs["console_viz"]), "Console 可视化")
        # 页面切换时：配置页带预览区、运维/Console 页独占全宽
        self.tab_widget.currentChanged.connect(self._on_page_changed)
        self._preview_collapsed = False
        # 全局样式后显式应用侧边导航样式（防覆盖）
        from gui.side_nav import NAV_QSS
                # QSS 层级实测：给整棵页签容器设样式表会切断 MainWindow 层的 QPushButton#primaryButton
        # 等规则对页内按钮的作用（内联表单主按钮变白灰、主次不分）。nav 在
        # side_nav.py:60 已单独设置，此行多余且有害，弃用。
        # self.tab_widget.setStyleSheet(NAV_QSS)
        self.tab_widget._nav.setStyleSheet(NAV_QSS)
        self.tab_widget.select_first()  # 默认选中第一页（导航高亮）
        
        self._clean_config = ""  # 最近一次生成的纯命令（注释另加，见 cmd_notes）
        
        # 主内容：左侧导航+页面（widget），右侧预览区
        nav_widget = QWidget()
        nav_layout = QVBoxLayout(nav_widget)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(0)
        nav_layout.addWidget(self.tab_widget)
        
        left_widget = nav_widget
        left_layout = nav_layout
        
        # 配置操作按钮行（模板/验证/生成/清空/收预览——仅配置页显示）
        button_widget = QWidget()
        button_layout = QHBoxLayout(button_widget)
        button_layout.setContentsMargins(0, 0, 0, 0)
        self._config_tools_widget = button_widget

        template_btn = None  # 「配置模板」按钮已移除：与顶部「模板(M)」菜单重复

        # 命令释义开关（对标 NetCMD）：并肩显示每条命令的中文说明，降低门槛；
        # 注释仅用于阅读，复制/导出/下发永远走纯命令
        self.comment_btn = QPushButton("命令释义")
        self.comment_btn.setObjectName("ghostButton")
        self.comment_btn.setCheckable(True)
        self.comment_btn.setChecked(True)
        self.comment_btn.setToolTip("开启后，右侧预览每条命令后显示中文说明（仅阅读用，复制时不包含）")
        self.comment_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.comment_btn.toggled.connect(self._toggle_comments)
        button_layout.addWidget(self.comment_btn)

        validate_btn = QPushButton("验证配置")
        # 次级操作档（视觉审查：与同排「导出文件/复制配置」同为次级却用 ghost，
        # 两档混排观感割裂；统一为 secondary）
        validate_btn.setObjectName("secondaryButton")
        validate_btn.setToolTip("验证当前配置参数")
        validate_btn.clicked.connect(self.validate_config)
        button_layout.addWidget(validate_btn)
        
        generate_btn = QPushButton("生成配置")
        generate_btn.setObjectName("primaryButton")
        generate_btn.setToolTip("生成完整配置脚本 (Ctrl+G)")
        generate_btn.clicked.connect(self.generate_config)
        button_layout.addWidget(generate_btn)
        
        clear_btn = QPushButton("清空")
        # 原来是实心红 dangerButton：和主按钮「生成配置」并排，视觉重量压过主操作，
        # 误触代价又高。改为红色描边的次级按钮，危险语义保留、不再抢视线。
        clear_btn.setObjectName("dangerGhostButton")
        clear_btn.setToolTip("清空所有配置项")
        clear_btn.clicked.connect(self.clear_config)
        button_layout.addWidget(clear_btn)
        
        # 预览区折叠按钮：窄屏时收起给左侧表单让位（QQ管家式侧栏收纳）
        # 不用 ⟩/⟨ 这类字符：Microsoft YaHei UI 下 U+27E9 会渲染成全角右括号"）"，
        # 按钮看起来像"）收起预览"，实测很怪。纯文字最稳。
        self.toggle_preview_btn = QPushButton("收起预览")
        self.toggle_preview_btn.setObjectName("ghostButton")
        self.toggle_preview_btn.setToolTip("收起/展开右侧配置预览区，收起后左侧表单区更宽")
        self.toggle_preview_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.toggle_preview_btn.clicked.connect(self.toggle_preview_panel)
        button_layout.addWidget(self.toggle_preview_btn)
        
        # 按页隐藏操作按钮行（模板/生成/清空等仅配置页需要）
        button_layout.setSpacing(8)
        left_layout.addWidget(button_widget)
        content_splitter.addWidget(left_widget)
        
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)
        
        preview_header = QHBoxLayout()
        preview_label = QLabel("配置预览")
        preview_label.setStyleSheet("""
            font-size: 15px;
            font-weight: bold;
            color: #1F2A37;
            padding: 2px;
        """)
        preview_header.addWidget(preview_label)
        
        preview_header.addStretch()
        
        self.info_label = QLabel("")
        # 原 rgba(224,224,224,.7) 是浅色字，放在浅底上几乎看不见（实测对比度 <1.5:1）
        self.info_label.setStyleSheet("font-size: 12px; color: #5F6B7A;")
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
        # 深色底上的占位文字：全局 placeholder 色是给浅底用的，在 #1E2430 上太暗
        _pal = self.preview_text.palette()
        _pal.setColor(QPalette.PlaceholderText, QColor("#8FA0B8"))
        self.preview_text.setPalette(_pal)
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
        self._toggle_comments(self.comment_btn.isChecked())  # 初始化"命令释义"开态的可见样式
        self._apply_form_layout_polish()
        # 无边框窗口底色是 paintEvent 手绘的：主题切换后主动重绘
        theme.on_change(self.update)

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

    # 全宽独占页集合（无右侧预览、无配置操作按钮）
    _FULL_WIDTH_PAGES = {"设备运维", "Console 可视化", "网络拓扑"}

    def _on_page_changed(self, index: int):
        """页面切换：配置页显示预览区+操作行；运维/Console 页独占全宽"""
        if index < 0:
            return
        title = self.tab_widget.tabText(index)
        full_width = title in self._FULL_WIDTH_PAGES
        # 右侧预览区
        if hasattr(self, "right_widget"):
            self.right_widget.setVisible(not full_width)
        # 折叠状态重置（全宽页强制视为展开）
        if full_width:
            self._preview_collapsed = False
        # 配置操作按钮行
        if hasattr(self, "_config_tools_widget"):
            self._config_tools_widget.setVisible(not full_width)

    def _toggle_comments(self, checked: bool):
        """命令释义开关：切换预览渲染方式"""
        # 开关的"开"态必须有可见反馈：原来只在 toggled 时设样式，
        # 启动时默认就是选中态，却看不出已开启（一个隐形的开关）
        self.comment_btn.setStyleSheet(
            "QPushButton:checked { color: #0089FF; border-color: #0089FF;"
            " background: #EAF4FF; }")
        self._render_preview()

    def _render_preview(self):
        """预览区渲染：释义开 → 带中文注释的彩色 HTML；关 → 纯命令"""
        text = self._clean_config
        if not text:
            self.preview_text.clear()
            return
        if self.comment_btn.isChecked():
            self.preview_text.setHtml(cmd_notes.annotate_config(text))
        else:
            self.preview_text.setPlainText(text)
        self.update_info()

    def toggle_preview_panel(self):
        """折叠/展开右侧配置预览区"""
        if self.right_widget.isVisible():
            self.right_widget.hide()
            self.toggle_preview_btn.setText("展开预览")
        else:
            self.right_widget.show()
            self.toggle_preview_btn.setText("收起预览")

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

        # 3) 卡片轻阴影（深色主题下用黑影，浅色保持墨色淡影）
        for group in self.findChildren(QGroupBox):
            shadow = QGraphicsDropShadowEffect(self)
            shadow.setBlurRadius(22)
            shadow.setOffset(0, 3)
            shadow.setColor(QColor(0, 0, 0, 90) if theme.is_dark()
                            else QColor(31, 42, 55, 28))  # 墨色 11% 透明度
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
        painter.setBrush(theme.qcolor("bg"))
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

    def menuBar(self):
        """缓存菜单栏引用。菜单栏被重挂进自定义标题栏（setMenuWidget）后，
        Qt 5.15.10 Windows 下再走 QMainWindow.menuBar() 原生 getter 会触发
        QMainWindowLayout 状态损坏 → 0xC0000005 原生崩溃（全量功能测试发现的地雷）。
        Python 层一律返回缓存，杜绝任何后续代码路径踩雷。"""
        mb = getattr(self, "_cached_menubar", None)
        if mb is None:
            mb = super().menuBar()
            self._cached_menubar = mb
        return mb

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

        # 菜单是入口不是清单：总入口（工具箱网格含全部 17 个工具卡片）+
        # 高频 5 项直达 + 带全局快捷键的 3 项（保留肌肉记忆，删了快捷键就失效）。
        # （历史版本 18 项一列垂到屏底，真机截图反馈“左右失衡”）
        all_tools_action = QAction("🧰 打开工具箱（全部工具）", self)
        all_tools_action.setShortcut("Ctrl+T")
        all_tools_action.triggered.connect(self.open_tools_window)
        tools_menu.addAction(all_tools_action)

        tools_menu.addSeparator()

        for label, key in (("Ping 测试", "ping"),
                           ("端口扫描", "port"),
                           ("子网计算器", "subnet"),
                           ("跨厂商配置转换", "convert"),
                           ("批量生成（CSV）", "batch")):
            act = QAction(label, self)
            act.triggered.connect(lambda _=False, k=key: self.open_network_tool(k))
            tools_menu.addAction(act)

        tools_menu.addSeparator()

        manual_action = QAction("配置命令手册", self)
        manual_action.setShortcut("Ctrl+M")
        manual_action.triggered.connect(lambda: self.open_network_tool("manual"))
        tools_menu.addAction(manual_action)

        compare_action = QAction("配置比较工具", self)
        compare_action.setShortcut("Ctrl+Shift+C")
        compare_action.triggered.connect(lambda: self.open_network_tool("compare"))
        tools_menu.addAction(compare_action)

        io_action = QAction("配置导入导出", self)
        io_action.setShortcut("Ctrl+I")
        io_action.triggered.connect(lambda: self.open_network_tool("configio"))
        tools_menu.addAction(io_action)
        
        template_menu = menubar.addMenu("模板(&M)")
        
        manager_action = QAction("模板管理器", self)
        # Ctrl+M 已给「配置命令手册」：避免歧义快捷键双双失效，改为 Ctrl+Shift+M
        manager_action.setShortcut("Ctrl+Shift+M")
        manager_action.triggered.connect(self.open_template_manager)
        template_menu.addAction(manager_action)
        
        save_action = QAction("保存为模板", self)
        save_action.setShortcut("Ctrl+Shift+S")
        save_action.triggered.connect(self.save_as_template)
        template_menu.addAction(save_action)
        
        template_menu.addSeparator()
        
        # 五厂商模板（二开补齐：华为/H3C/锐捷/迈普/思科）
        for _vendor in ("huawei", "h3c", "ruijie", "maipu", "cisco"):
            act = QAction(f"应用{VENDOR_CN[_vendor]}模板", self)
            act.triggered.connect(lambda checked=False, v=_vendor: self.quick_apply_template(v))
            template_menu.addAction(act)
        
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
        device_types = ["huawei", "h3c", "ruijie", "maipu", "cisco"]
        self.current_device_type = device_types[index]
        
        device_names = {
            "huawei": ("华为交换机配置脚本生成工具", "华为", "Huawei"),
            "h3c": ("H3C华三交换机配置脚本生成工具", "H3C", "H3C"),
            "ruijie": ("锐捷交换机配置脚本生成工具", "锐捷", "Ruijie"),
            "maipu": ("迈普交换机配置脚本生成工具", "迈普", "Maipu"),
            "cisco": ("思科交换机配置脚本生成工具", "思科", "Cisco"),
        }
        
        title, name, _ = device_names[self.current_device_type]
        # 品牌切换不再更新大标题（标题栏常驻"NetOps Toolkit"，品牌以下拉自示）
        self.setWindowTitle(f"NetOps Toolkit v4.0 - {name}配置")
        
        for tab in self.tabs.values():
            tab.clear_config()
        self.preview_text.clear()
        self._clean_config = ""
        
        self.statusBar().showMessage(f"已切换到{name}模式", 3000)
    
    def open_network_tool(self, tool_name):
        """打开单个网络工具"""
        from gui.tools_window import NetworkToolsWindow  # noqa: F401  （菜单弹窗用不到，保留导入位置）
        from gui.tools.subnet_tool import SubnetCalculatorWidget
        from gui.tools.ping_tool import PingTestWidget
        from gui.tools.port_tool import PortScanWidget
        from gui.tools.trace_tool import TraceRouteWidget
        from gui.tools.dns_tool import DNSToolWidget
        from gui.tools.http_tool import HTTPStatusWidget
        from gui.tools.mac_tool import MACToolWidget
        from gui.tools.password_tool import PasswordGeneratorWidget
        from gui.tools.encoder_tool import EncoderToolWidget
        from gui.tools.manual_tool import ManualToolWidget
        from gui.tools.config_compare_tool import ConfigCompareWidget
        from gui.tools.config_io_tool import ConfigIOWidget
        from gui.tools.nl_gen_tool import NLGenWidget
        from gui.tools.troubleshoot_tool import TroubleshootWidget
        from gui.tools.lint_tool import LintWidget
        from gui.tools.convert_tool import ConvertWidget
        from gui.tools.batch_tool import BatchWidget
        from gui.tools.onboard_tool import OnboardWidget
        
        tool_widgets = {
            "subnet": SubnetCalculatorWidget,
            "ping": PingTestWidget,
            "port": PortScanWidget,
            "trace": TraceRouteWidget,
            "dns": DNSToolWidget,
            "http": HTTPStatusWidget,
            "mac": MACToolWidget,
            "password": PasswordGeneratorWidget,
            "encoder": EncoderToolWidget,
            "manual": ManualToolWidget,
            "compare": ConfigCompareWidget,
            "configio": ConfigIOWidget,
            "nlgen": NLGenWidget,
            "trouble": TroubleshootWidget,
            "lint": LintWidget,
            "convert": ConvertWidget,
            "batch": BatchWidget,
            "onboard": OnboardWidget
        }
        
        if tool_name in tool_widgets:
            titles = {
                "subnet": "子网计算器",
                "ping": "Ping测试",
                "port": "端口扫描",
                "trace": "路由跟踪",
                "dns": "DNS工具",
                "http": "HTTP状态检测",
                "mac": "MAC地址查询",
                "password": "密码生成器",
                "encoder": "编码转换器",
                "manual": "配置命令速查手册",
                "compare": "配置比较工具",
                "configio": "配置导入导出",
                "nlgen": "自然语言生成配置",
                "trouble": "排错·重置命令速查",
                "lint": "配置语法纠错",
                "convert": "跨厂商配置转换",
                "batch": "批量生成（CSV）",
                "onboard": "一键标准化开局"
            }
            title = titles.get(tool_name, tool_name)
            # 统一子窗口：BaseDialog（无边框圆点标题栏 + 高度钐制 + 长内容滚动）
            dialog = BaseDialog(title, "", self, min_width=800, min_height=600,
                                scrollable=True)
            dialog.resize(1000, 750)
            widget = tool_widgets[tool_name]()
            dialog.add_content(widget, 1)

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
        text = self._clean_config or self.preview_text.toPlainText()
        line_count = text.count('\n') + 1 if text else 0
        char_count = len(text)
        config_sections = text.count('#')
        note = " ｜ 释义：开（复制不含注释）" if self.comment_btn.isChecked() else ""
        self.info_label.setText(
            f"行数: {line_count} | 字符: {char_count} | 配置块: {config_sections // 2}{note}")
    
    def show_template_dialog(self):
        dialog = TemplateDialog(self.current_device_type, self)
        if dialog.exec_() == BaseDialog.Accepted:
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
            warn_box(self, "警告", f"模板 {template_name} 不存在！")
            return
        
        if question_box(
            self, "加载模板",
            f"确定要加载模板 \"{template_name}\" 吗？\n这将覆盖当前所有配置。",
            ok="是", cancel="否"
        ):
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
            info_box(self, "成功", f"模板 \"{template_name}\" 已加载！")
    
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
            warn_box(self, "验证失败", error_msg)
            self.statusBar().showMessage(f"验证失败: {len(errors)} 个错误", 5000)
        else:
            info_box(self, "验证通过", "所有配置参数格式正确！")
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
        
        adv_config = self.tabs["adv"].get_config()
        if adv_config:
            all_config.append(adv_config)
        
        if not all_config:
            warn_box(self, "警告", "请至少配置一个模块！")
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
        
        self._clean_config = header + full_config
        self._render_preview()
        self.statusBar().showMessage("配置生成成功！", 3000)
        info_box(self, "成功", "配置生成成功！")
    
    def export_config(self):
        config_text = self._clean_config or self.preview_text.toPlainText()
        if not config_text:
            warn_box(self, "警告", "请先生成配置！")
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
                info_box(self, "成功", f"配置已导出到：\n{file_path}")
            except Exception as e:
                error_box(self, "错误", f"导出失败：\n{str(e)}")
    
    def copy_to_clipboard(self):
        config_text = self._clean_config or self.preview_text.toPlainText()
        if not config_text:
            warn_box(self, "警告", "请先生成配置！")
            return
        
        from PyQt5.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(config_text)
        
        msg = "配置已复制到剪贴板（纯命令，注释不包含，可直接粘贴设备）"
        self.statusBar().showMessage(msg, 4000)
        info_box(self, "成功", msg + "！")
    
    def clear_config(self):
        if question_box(
            self, "确认", "确定要清空所有配置吗？",
            ok="是", cancel="否"
        ):
            for tab in self.tabs.values():
                tab.clear_config()
            self.preview_text.clear()
            self._clean_config = ""
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
        info_box(self, "成功", f"模板 '{template_data.get('name', '')}' 已应用！")
    
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
                info_box(self, "成功", "模板导入成功！")
            else:
                warn_box(self, "失败", "导入模板失败，请检查文件格式。")
    
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
            # 全量测试修复：当前表单模板尚未存入注册表，须用导出对象方法（原按名查表必失败）
            if manager.export_template_object(template, file_path):
                info_box(self, "成功", "模板导出成功！")
            else:
                warn_box(self, "失败", "导出模板失败。")



class _GroupCollapser(QObject):
    """QGroupBox 折叠管理器：点击标题区切换收起/展开（不改动各 tab 源码）"""

    # 箭头放标题左侧：右侧箭头会被误读成"更多操作"，且中文标题宽度不一导致箭头不对齐
    COLLAPSED_MARK = "▸ "
    EXPANDED_MARK = "▾ "
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
        base = group.title().replace("▸", "").replace("▾", "").strip()
        group.setTitle(mark + base)

    # ---- 事件过滤：标题区点击 ----
    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonRelease:
            if 0 <= event.pos().y() <= self.TITLE_ZONE:
                self.toggle(obj)
                return True
        return super().eventFilter(obj, event)
