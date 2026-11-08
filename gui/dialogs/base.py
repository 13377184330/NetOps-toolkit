#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
统一对话框基建（二开 v2：无边框子窗口统一）

v2 动机（真机截图反馈）：子窗口此前仍用系统原生标题栏（Windows 亮蓝标题 + 问号按钮），
与主窗口「红黄绿圆点 + 圆角」的语言完全脱节；且长内容弹窗（Ping 表格等）超出屏幕
被任务栏截断。v2 全量对齐：

- **无边框**：Qt.Dialog | Qt.FramelessWindowHint + WA_TranslucentBackground，
  paintEvent 手绘圆角底（与主窗口同一画法，radius 12）
- **子窗口标题栏**：红点（关闭）+ 标题 13px + 可拖动，与主窗口红黄绿圆点同语言；
  对话框无最大化语义，不摆黄绿点
- **高度钳制**：任何子窗口高度 ≤ 屏幕可用区 85%——长内容走 scrollable=True
  的内部滚动（按钮行固定在滚动区外，永远可见），彻底告别「超出屏幕」
- **消息框同皮肤**：info/warn/error/question 不再用系统 QMessageBox，
  改为 StyledMessageBox（同一套无边框 + 红点标题栏 + 四档按钮）
- 按钮四档语义不变：primary / secondary / ghost / danger
- 内联 QSS 一律写「浅色词汇」（theme.py 声明级重映射才能在深色主题翻译）；
  手绘色一律 theme.t()/qcolor() 现取

兼容：BaseDialog 对外接口（content_layout/add_content/add_button/add_close_button、
info_box/warn_box/error_box/question_box）签名与语义保持 v1 不变。
"""

from PyQt5.QtCore import QPoint, QRect, Qt
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel,
                              QPushButton, QScrollArea, QVBoxLayout, QWidget)

from gui.styles import MODERN_STYLE, TOOLTIP_STYLE, DIALOG_STYLE
from gui.title_bar import DotButton
from gui import theme

# 按钮语义档位 → QSS objectName（styles.py 已有全套四档样式）
ROLE_OBJECT = {
    "primary":   "primaryButton",
    "secondary": "secondaryButton",
    "ghost":     "ghostButton",
    "danger":    "dangerButton",
}

# 兼容旧代码里直接传 objectName 的写法
_OBJECT_ALIASES = {
    "primaryButton":   "primaryButton",
    "secondaryButton": "secondaryButton",
    "ghostButton":     "ghostButton",
    "dangerButton":    "dangerButton",
    "warningButton":   "warningButton",
    "dangerGhostButton": "dangerGhostButton",
}

# 四档按钮的内联样式（与 styles.py 的 QSS 同色值，浅色词——深色主题靠
# theme.py 的声明级重映射照常翻译）。
# 为什么内联：实测窗口级 QSS 的 #primaryButton 规则在 QStackedWidget 子树
# 会失灵（主窗直挂蓝、页内挂白，逐层二分实锤），控件级样式优先级最高、
# 不依赖级联，保证按钮语义色在任何容器层级都成立。
from gui.styles import (ACCENT, ACCENT_HOVER, ACCENT_PRESSED, ACCENT_LIGHT,
                        BORDER, BORDER_STRONG, CARD, DANGER, DANGER_HOVER,
                        DISABLED_BG, DISABLED_TEXT, SUCCESS, SUCCESS_HOVER,
                        TEXT, WARNING, WARNING_HOVER)

_ROLE_QSS = {
    "primaryButton": f"""
        QPushButton {{
            background: {ACCENT}; color: #FFFFFF; border: none;
            padding: 11px 30px; border-radius: 11px; font-weight: bold; font-size: 14px;
        }}
        QPushButton:hover {{ background: {ACCENT_HOVER}; }}
        QPushButton:pressed {{ background: {ACCENT_PRESSED}; }}
        QPushButton:disabled {{ background: #A8CDF5; color: #FFFFFF; }}
    """,
    "secondaryButton": f"""
        QPushButton {{
            background: {ACCENT_LIGHT}; color: {ACCENT};
            border: 1px solid rgba(0, 137, 255, 0.25);
            padding: 11px 30px; border-radius: 11px; font-weight: bold; font-size: 14px;
        }}
        QPushButton:hover {{ background: #D8EAFF; }}
    """,
    "ghostButton": f"""
        QPushButton {{
            background: transparent; border: 1px solid {BORDER}; color: {TEXT};
            padding: 11px 30px; border-radius: 11px; font-weight: bold; font-size: 14px;
        }}
        QPushButton:hover {{
            border: 1px solid {ACCENT}; color: {ACCENT}; background: {ACCENT_LIGHT};
        }}
    """,
    "dangerButton": f"""
        QPushButton {{
            background: {DANGER}; color: #FFFFFF; border: none;
            padding: 11px 30px; border-radius: 11px; font-weight: bold; font-size: 14px;
        }}
        QPushButton:hover {{ background: {DANGER_HOVER}; }}
    """,
    "warningButton": f"""
        QPushButton {{
            background: {WARNING}; color: #FFFFFF; border: none;
            padding: 11px 30px; border-radius: 11px; font-weight: bold; font-size: 14px;
        }}
        QPushButton:hover {{ background: {WARNING_HOVER}; }}
    """,
    "dangerGhostButton": f"""
        QPushButton {{
            background: {CARD}; border: 1px solid {BORDER}; color: {DANGER};
            padding: 11px 30px; border-radius: 11px; font-weight: bold; font-size: 14px;
        }}
        QPushButton:hover {{
            background: #FDEEEE; border: 1px solid {DANGER}; color: {DANGER_HOVER};
        }}
    """,
}

# 屏幕可用区高度上限（%）：子窗口永远不许超出屏幕（真机截图教训：
# Ping 弹窗 560+ 内高在 150% 缩放屏上直接被任务栏截断）
_MAX_SCREEN_RATIO = 0.85


def _screen_avail_h():
    screen = QApplication.primaryScreen()
    if screen is None:
        return 760
    return int(screen.availableGeometry().height() * _MAX_SCREEN_RATIO)


def make_button(text, role="secondary", parent=None, tip=None):
    """按语义档位造一个统一样式的按钮（对话框外也可复用）。
    样式为控件级内联（浅色词），不依赖窗口级 QSS 级联——后者在
    QStackedWidget 子树实测会失灵。"""
    btn = QPushButton(text, parent)
    obj = ROLE_OBJECT.get(role) or _OBJECT_ALIASES.get(role, "secondaryButton")
    btn.setObjectName(obj)
    btn.setStyleSheet(_ROLE_QSS.get(obj, _ROLE_QSS["ghostButton"]))
    btn.setCursor(Qt.PointingHandCursor)
    if tip:
        btn.setToolTip(tip)
    return btn


# ---------------------------------------------------------------- 子窗口标题栏
class DialogTitleBar(QWidget):
    """无边框对话框标题栏：红点（关闭）+ 标题，可拖动整窗。
    与主窗口 FramelessTitleBar 同语言（红=关闭圆点），但不摆黄/绿点——
    对话框没有最小化/最大化语义，摆了反而误导。"""

    def __init__(self, title, dialog, parent=None):
        super().__init__(dialog)
        self._dialog = dialog
        self._drag_start = None
        self._drag_start_pos = None
        self.setFixedHeight(38)
        self.setStyleSheet(
            "background: #FFFFFF; border: none;"
            "border-top-left-radius: 12px; border-top-right-radius: 12px;")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(10)

        self.close_dot = DotButton("#FA5151", "#E64646", "关闭")
        self.close_dot.clicked.connect(self._do_close)
        lay.addWidget(self.close_dot)

        self.title_label = QLabel(title or "对话框")
        self.title_label.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: #1F2A37;"
            "border: none; background: transparent;")
        lay.addSpacing(4)
        lay.addWidget(self.title_label)
        lay.addStretch()

    def set_title(self, title):
        self.title_label.setText(title)

    def _do_close(self):
        # QDialog.close() 语义等同 reject（Esc/关闭一致），非模态窗口同样干净退出
        self._dialog.close()

    # ---- 拖动 ----
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start = event.globalPos()
            self._drag_start_pos = self._dialog.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start is not None and event.buttons() & Qt.LeftButton:
            self._dialog.move(self._drag_start_pos + event.globalPos() - self._drag_start)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_start = None
        super().mouseReleaseEvent(event)


# ---------------------------------------------------------------- 基类
class BaseDialog(QDialog):
    """统一对话框骨架 v2：无边框 + 圆点标题栏 + 圆角 + 高度钳制。

    子类典型用法：
        dlg = BaseDialog("标题", "副标题说明", self, min_width=520)
        lay = dlg.content_layout()
        lay.addWidget(...)
        dlg.add_button("复制", "secondary", self.copy)
        dlg.add_button("生成", "primary", self.generate)
        dlg.exec_()

    scrollable=True：内容区放进 QScrollArea（按钮行固定在外，长内容永远可达）。
    """

    def __init__(self, title, subtitle="", parent=None, min_width=520,
                 min_height=None, window_title=None, scrollable=False):
        super().__init__(parent)
        # 无边框 + 圆角手绘（同主窗口画法）。
        # 注意 flag 组合必须与主窗口同款（Qt.Window）：Qt.Dialog + Translucent
        # 在 Windows 上触发原生层崩溃（0xC0000409，show 后首次 paint）；
        # QDialog 的模态语义由 exec_ 管理，与 Qt::Dialog flag 无关，去掉它零损失。
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window | Qt.WindowSystemMenuHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle(window_title or title or "对话框")

        # 高度钳制：子窗口永不超出屏幕（长内容应配 scrollable=True）
        self._min_h_requested = min_height
        self.setMinimumWidth(min_width)
        if min_height:
            self.setMinimumHeight(min(min_height, _screen_avail_h()))

        self.setStyleSheet(MODERN_STYLE + TOOLTIP_STYLE + DIALOG_STYLE)
        self._scrollable = scrollable

        # 根布局：标题栏通栏 + 主体
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(0)

        self._title_bar = DialogTitleBar(window_title or title or "对话框", self)
        self._root.addWidget(self._title_bar)

        # ---- 主体（原 v1 的标题/副标题/内容/按钮行；标题已上移标题栏，正文只留副标题） ----
        self._body = QVBoxLayout()
        self._body.setContentsMargins(22, 12, 22, 18)
        self._body.setSpacing(14)
        self._root.addLayout(self._body, 1)

        if subtitle:
            s = QLabel(subtitle)
            s.setObjectName("dlgSubtitle")
            s.setWordWrap(True)
            s.setStyleSheet(
                "font-size: 13px; color: #5F6B7A; background: transparent;"
                "line-height: 1.5;")
            self._body.addWidget(s)

        # 内容区（滚动可选）
        self._content = QVBoxLayout()
        self._content.setSpacing(10)
        if scrollable:
            host = QWidget()
            host.setObjectName("dlgScrollHost")
            host.setStyleSheet("#dlgScrollHost { background: transparent; }")
            host.setLayout(self._content)
            self._scroll = QScrollArea()
            self._scroll.setWidget(host)
            self._scroll.setWidgetResizable(True)
            self._scroll.setFrameShape(QScrollArea.NoFrame)
            self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
            self._body.addWidget(self._scroll, 1)
        else:
            self._body.addLayout(self._content, 1)

        # 按钮行（永远在滚动区外）
        self._btn_row = QHBoxLayout()
        self._btn_row.setSpacing(10)
        self._btn_row.addStretch()
        self._body.addLayout(self._btn_row)

        self._centered = False

    # ---- 圆角底（透明背景下手绘，同主窗口） ----
    def paintEvent(self, event):
        # 描边用「双层填充」实现：先画边框色大圆角、再叠底色小圆角，全程 NoPen。
        # 不能用 setPen + setBrush(Qt.NoBrush) 的描边画法——QDialog 在
        # WA_TranslucentBackground 下走那条路径会在首次 paint 原生崩溃
        # （0xC0000409，Windows 实测三组对照实锤；主窗口同款双层画法无此问题）。
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(theme.t("border_strong")))
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 12, 12)
        painter.setBrush(theme.qcolor("bg"))
        painter.drawRoundedRect(1, 1, self.width() - 2, self.height() - 2, 11, 11)

    # ---- 首次显示：居中于父窗口（无边框窗口必须自己摆位） ----
    def showEvent(self, event):
        super().showEvent(event)
        if not self._centered:
            self._centered = True
            self._center_on_parent()

    def _center_on_parent(self):
        """把子窗口摆在父窗口正中，并钳制在屏幕可用区内（绝不越界出屏）。
        注意：非顶层控件（如拓扑页 page）的 frameGeometry() 是**父坐标系**坐标，
        不能直接当屏幕坐标用（曾把弹窗移到左上角、左侧切字，真机截图实锤）；
        必须 mapToGlobal 转全局。父不可见时退回屏幕居中。"""
        fg = self.frameGeometry()
        parent = self.parent()
        if parent is not None and parent.isVisible():
            top_left = parent.mapToGlobal(QPoint(0, 0))
            ref = QRect(top_left, parent.size())
        else:
            ref = QApplication.primaryScreen().availableGeometry()
        x = ref.left() + (ref.width() - fg.width()) // 2
        y = ref.top() + (ref.height() - fg.height()) // 2
        # 屏幕四边钳制：即使公式/参考区异常，也绝不越出可用区
        scr = QApplication.primaryScreen().availableGeometry()
        x = max(scr.left(), min(x, scr.right() - fg.width()))
        y = max(scr.top(), min(y, scr.bottom() - fg.height()))
        self.move(x, y)

    # ---- 对外接口（与 v1 兼容） ----
    def content_layout(self):
        """内容区布局：子类往这里 addWidget / addLayout（scrollable 时在滚动区里）"""
        return self._content

    def add_content(self, widget, stretch=0):
        self._content.addWidget(widget, stretch)
        return widget

    def set_title(self, title):
        """标题栏 + 窗口标题一起换（消息框等动态标题用）"""
        self._title_bar.set_title(title)
        self.setWindowTitle(title)

    def add_button(self, text, role="secondary", callback=None,
                   close_on_click=True, tip=None):
        """加一个按钮。callback 为 None 时仅关闭不做事。
        close_on_click=False：点了不关对话框（如表单校验失败后再试）"""
        btn = make_button(text, role, self, tip)
        if callback is None and not close_on_click:
            raise ValueError("无回调且不关闭的按钮没有行为，别加")
        btn.clicked.connect(lambda _=False, f=callback: self._on_btn(f, close_on_click))
        self._btn_row.addWidget(btn)
        return btn

    def _on_btn(self, callback, close_on_click):
        if close_on_click:
            self.accept()
        if callback:
            callback()

    def add_close_button(self, text="关闭", role="ghost"):
        """信息型对话框统一的收尾按钮（永远只是关闭）"""
        btn = make_button(text, role, self)
        btn.clicked.connect(self.reject)
        self._btn_row.addWidget(btn)
        return btn


# ---------------------------------------------------------------- 统一消息框
class _StyledMessageBox(BaseDialog):
    """info/warn/error/question 的统一载体：无边框同皮肤消息框。
    图标用主题状态色圆点（非系统图标），文字纯文本。"""

    _DOT = {"info": "accent", "warn": "warning", "error": "danger", "question": "accent"}

    def __init__(self, kind, title, text, buttons, default_text, parent=None):
        super().__init__(title, "", parent, min_width=420, scrollable=False)
        self._result_text = None

        # 图标圆点 + 正文
        row = QHBoxLayout()
        row.setSpacing(12)
        dot = QLabel()
        dot.setFixedSize(14, 14)
        dot.setStyleSheet(
            f"border-radius: 7px; background: {theme.t(self._DOT.get(kind, 'accent'))};")
        row.addWidget(dot, 0, Qt.AlignTop)
        body = QLabel(text)
        body.setObjectName("dlgSubtitle")
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body.setStyleSheet("font-size: 13px; color: #1F2A37; background: transparent;")
        row.addWidget(body, 1)
        self.content_layout().addLayout(row)
        # 正文与按钮间的呼吸空间
        self.content_layout().addSpacing(2)

        self._btns = []
        for text_, role_hint in buttons:
            role = "primary" if role_hint in ("yes", "accept") else "ghost"
            b = self.add_button(text_, role, callback=None)
            b.clicked.connect(lambda _=False, t=text_: self._pick(t))
            if text_ == default_text:
                b.setDefault(True)
                b.setFocus()
            self._btns.append(b)

    def _pick(self, text):
        self._result_text = text
        self.accept()

    def result_text(self):
        return self._result_text


def _styled_box(parent, kind, title, text, buttons, default_role=None):
    """统一消息框入口。buttons: [(文字, yes|no / accept|reject)]"""
    if default_role in ("ok", "yes", None):
        default_text = buttons[0][0]
    elif len(buttons) > 1:
        default_text = buttons[1][0]
    else:
        default_text = buttons[0][0]
    box = _StyledMessageBox(kind, title, text, buttons, default_text, parent)
    box.exec_()
    return box.result_text()


def info_box(parent, title, text, ok="知道了"):
    _styled_box(parent, "info", title, text,
                [(ok, "accept")], "ok")


def warn_box(parent, title, text, ok="知道了"):
    _styled_box(parent, "warn", title, text,
                [(ok, "accept")], "ok")


def error_box(parent, title, text, ok="知道了"):
    _styled_box(parent, "error", title, text,
                [(ok, "accept")], "ok")


def question_box(parent, title, text, ok="确定", cancel="取消", default="cancel"):
    """两键确认框，返回 True=用户点了 ok。
    default：回车默认按钮——"cancel"（安全，危险确认的回车保护）或 "ok"。
    默认按钮拿到焦点（回车触发），另一个按钮不夺焦点。"""
    roles = {"ok": "yes", "cancel": "no"}
    clicked = _styled_box(parent, "question", title, text,
                           [(ok, "yes"), (cancel, "no")], default)
    return clicked is not None and clicked == ok
