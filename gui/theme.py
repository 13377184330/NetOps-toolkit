#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
主题引擎（二开新增）：浅色 / 深色 / 跟随系统

设计要点（为什么这么做）：
- 全库有 350+ 处内联 setStyleSheet、几十个 Python 手绘颜色，逐处改成
  "读主题" 的动态字符串不现实（QSS 花括号和 f-string 天然冲突）。
- 这里把"浅色"定为**源语言**：所有代码继续写浅色词汇的样式字符串；
  在 QWidget.setStyleSheet 上做声明级重映射（按属性上下文区分
  background/color/border，同一个 #FFFFFF 既当卡片底又当按钮文字不会互相误伤），
  切主题时用保存的原始字符串重刷全部已存在控件。
- Python 手绘颜色（paintEvent / 拓扑画布 / 启动动画）不走 QSS，
  通过 t()/qcolor() 直接读当前主题，并在切换时回调刷新。
"""

import re

from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QWidget, QApplication

# ---------------- 两套语义 Token ----------------
# 键与 gui/styles.py 的设计 Token 对齐；浅色值即源语言里的取值。
LIGHT = {
    # 品牌蓝
    "accent":        "#0089FF",   # 填充用（按钮底、选中块）
    "accent_hover":  "#0077E6",
    "accent_pressed": "#006AD5",
    "accent_text":   "#0089FF",   # 当文字用时（浅底上）
    "accent_light":  "#EAF4FF",   # 选中/悬浮的浅蓝底
    # 状态色
    "success":       "#34C759",
    "success_hover": "#2EB350",
    "danger":        "#FA5151",
    "danger_hover":  "#E64646",
    "danger_light":  "#FDEEEE",
    "warning":       "#FA9D3B",
    "warning_hover": "#E88E2F",
    # 表面
    "bg":            "#ECF0F6",   # 窗口底
    "card":          "#FFFFFF",   # 卡片底
    "card_alt":      "#F7F9FC",   # 卡片内的次级底/表头底
    "zebra":         "#FAFBFD",   # 表格斑马纹
    "track":         "#E8EDF5",   # 滚动条轨道/分段控件底
    "disabled_bg":   "#F5F7FA",
    # 线
    "border":        "#DFE6F0",
    "border_strong": "#C9D4E3",
    "gridline":      "#ECF0F6",
    # 文字
    "text":          "#1F2A37",
    "text_sub":      "#5F6B7A",
    "text_muted":    "#8A95A6",
    "disabled_text": "#B3BCCB",
    "placeholder":   "#6E7B8C",   # 输入占位：比正文弱但 ≥4.5:1（视觉审查两轮点名后加深）
    # 代码预览（深色面板，两主题都保持深色，只微调边线）
    "preview_bg":    "#1E2430",
    "preview_border": "#2C3444",
    "preview_text":  "#C8D3E8",
    "preview_ph":    "#8FA0B8",
    # 滚动条 / 画布
    "scroll_handle": "#CBD5E3",
    "scroll_handle_hover": "#AEBACB",
    "canvas_bg":     "#F7F9FC",   # 拓扑画布
    "canvas_grid":   "#E4EAF3",
    # 设备面板端口方块（状态色块）：浅色为淡色底+深边框，深色为暗色底+亮边框
    "port_up_bg":     "#E6F7EC",
    "port_up_border": "#27AE60",
    "port_down_bg":   "#EDF1F6",
    "port_down_border": "#AAB8CA",
    "port_trunk_bg":   "#F4EEFC",
    "port_trunk_border": "#8E6FD8",
    # 阴影（QSS rgba）
    "shadow":        "rgba(31, 42, 55, 28)",
}

DARK = {
    "accent":        "#2E9BFF",
    "accent_hover":  "#4DA9FF",
    "accent_pressed": "#1F8CEF",
    "accent_text":   "#5CB0FF",
    "accent_light":  "#1D3A5F",
    "success":       "#4ED882",
    "success_hover": "#6BE29A",
    "danger":        "#FF7373",
    "danger_hover":  "#FF8F8F",
    "danger_light":  "#3A2226",
    "warning":       "#FFAE5E",
    "warning_hover": "#FFC081",
    "bg":            "#171C24",
    "card":          "#232B37",
    "card_alt":      "#1D2430",
    "input_bg":      "#1B2430",   # 输入控件底（比卡片暗一档，内嵌感；层次 P2）
    "zebra":         "#202734",
    "track":         "#2A3340",
    "disabled_bg":   "#202836",
    "border":        "#343F52",
    "border_strong": "#47556C",
    "gridline":      "#262F3D",
    "text":          "#E8EDF4",
    "text_sub":      "#A3AFC2",
    "text_muted":    "#76839A",
    "disabled_text": "#5C6980",
    "placeholder":   "#8B97AC",
    "preview_bg":    "#1A202B",
    "preview_border": "#303A4A",
    "preview_text":  "#C8D3E8",
    "preview_ph":    "#8FA0B8",
    "scroll_handle": "#3A4658",
    "scroll_handle_hover": "#4C5B72",
    "canvas_bg":     "#141A22",
    "canvas_grid":   "#202836",
    # 设备面板端口方块：暗色底 + 提亮边框（深色主题下状态色仍一眼可辨）
    "port_up_bg":     "#20392B",
    "port_up_border": "#4ED882",
    "port_down_bg":   "#2A3340",
    "port_down_border": "#47556C",
    "port_trunk_bg":   "#322B4E",
    "port_trunk_border": "#A88FE8",
    # 阴影（QSS rgba）
    "shadow":        "rgba(0, 0, 0, 90)",
}

THEMES = {"light": LIGHT, "dark": DARK}
_current_name = "light"

# 主题切换回调（手绘控件刷新用）：函数列表，无参数
_change_callbacks = []


def name():
    return _current_name


def is_dark():
    return _current_name == "dark"


def t(key):
    """当前主题的语义色值（返回如 "#232B37" 的字符串）"""
    return THEMES[_current_name][key]


def qcolor(key):
    return QColor(t(key))


# ---------------- VLAN 配色引擎（拓扑/设备面板共用色源） ----------------
# 12 个高区分度色相（紫/玫红/青/金/靛/赭橙/橄榄/梅紫/珊瑚/雾蓝/黄绿/洋红），
# 与状态色（绿 success / 红 danger / 橙 warning / 蓝 accent）拉开观感距离；
# 深浅主题共用同一色板——VLAN 色条/分组框都带 ID 文字标注，撞色相也有数字消歧。
VLAN_PALETTE = [
    "#8E6FD8", "#E85D9E", "#22B8CF", "#C9A227",
    "#6C7BD9", "#D2691E", "#7A9E4F", "#A34BA0",
    "#E8967E", "#5A9BC4", "#94A040", "#C2185B",
]


def vlan_color(vid):
    """VLAN ID → 稳定色值（同一 VLAN 永远同色：端口格色条/终端徽章/分组框/图例一致）"""
    try:
        idx = int(str(vid).strip()) % len(VLAN_PALETTE)
    except (ValueError, TypeError):
        idx = 0
    return VLAN_PALETTE[idx]


def on_change(callback):
    """注册主题切换回调（拓扑画布等手绘控件刷新视图）"""
    if callback not in _change_callbacks:
        _change_callbacks.append(callback)


# ---------------- 声明级颜色重映射 ----------------
# 源语言 = 浅色词汇。切到深色时按下表翻译；不认识的色值原样保留
# （如代码预览面板本来就是深色、拓扑节点色由画布代码自理）。

_BG_PROPS = {
    "background", "background-color", "selection-background-color",
    "alternate-background-color", "gridline-color",
}
_FG_PROPS = {"color", "selection-color"}

# 表面（当背景用时）
_SURFACE_MAP = {
    "#FFFFFF": DARK["card"],
    "#FFF": DARK["card"],
    "#FCFDFE": DARK["input_bg"],   # 输入控件底（styles.py INPUT_BG）
    "#F7F9FC": DARK["card_alt"],
    "#FAFBFD": DARK["zebra"],
    "#F5F7FA": DARK["disabled_bg"],
    "#F8FAFC": DARK["card_alt"],
    "#F5F5F5": DARK["card_alt"],
    "#F0F0F0": DARK["card_alt"],
    "#ECF0F6": DARK["bg"],
    "#E8EDF5": DARK["track"],
    "#E2E9F3": DARK["track"],
    "#E4EAF3": DARK["track"],
    "#E8E8E8": DARK["track"],
    "#E0E0E0": DARK["track"],
    # 滚动条滑块（styles.py 浅色值，深色下需映射到暗色把手，否则亮块刺眼）
    "#CBD5E3": DARK["scroll_handle"],
    "#AEBACB": DARK["scroll_handle_hover"],
    "#D3DBE7": DARK["scroll_handle"],
    # 浅蓝系（选中/悬浮底）
    "#EAF4FF": DARK["accent_light"],
    "#E3F2FD": DARK["accent_light"],
    "#D9ECFF": DARK["accent_light"],
    "#D8EAFF": DARK["accent_light"],
    "#F3F8FF": DARK["accent_light"],
    "#F5FAFF": DARK["accent_light"],
    "#BBDEFB": "#25466B",
    # 状态浅底
    "#FDEEEE": DARK["danger_light"],
    "#F5C2C2": DARK["danger_light"],
    "#DDF6E4": "#1D3626",
    # 主蓝当底（按钮/选中 tab/滚动条 chunk）
    "#0089FF": DARK["accent"],
    "#0077E6": DARK["accent_hover"],
    "#006AD5": DARK["accent_pressed"],
    # 禁用的主蓝按钮
    "#A8CDF5": "#31556E",
}

# 文字
_TEXT_MAP = {
    "#1F2A37": DARK["text"],
    "#1A1A1A": DARK["text"],
    "#333333": DARK["text"],
    "#0A0806": DARK["text"],
    "#5F6B7A": DARK["text_sub"],
    "#666666": DARK["text_sub"],
    "#5A6B7B": DARK["text_sub"],
    "#5A6B82": DARK["text_sub"],
    "#7A8699": DARK["text_muted"],
    "#8A95A6": DARK["text_muted"],
    "#9AA7B8": DARK["text_muted"],
    "#9E9E9E": DARK["text_muted"],
    "#8A8A9E": DARK["text_muted"],
    "#B3BCCB": DARK["disabled_text"],
    "#BDBDBD": DARK["disabled_text"],
    "#757575": DARK["text_muted"],
    # 主蓝当文字
    "#0089FF": DARK["accent_text"],
    "#0077E6": DARK["accent_text"],
    "#0072D6": DARK["accent_text"],
    # 状态色当文字（深底上提亮一档）
    "#34C759": DARK["success"],
    "#2EB350": DARK["success_hover"],
    "#4CAF50": DARK["success"],
    "#22C55E": DARK["success"],
    "#2BA84E": DARK["success_hover"],
    "#4ADE80": DARK["success"],
    "#7CF29B": DARK["success"],
    "#7EE0A3": DARK["success"],
    "#FA5151": DARK["danger"],
    "#E64646": DARK["danger_hover"],
    "#F44336": DARK["danger"],
    "#D32F2F": DARK["danger_hover"],
    "#F87171": DARK["danger"],
    "#FA9D3B": DARK["warning"],
    "#E88E2F": DARK["warning_hover"],
    "#FF9500": DARK["warning"],
    "#FF9800": DARK["warning"],
    "#FFC107": DARK["warning"],
    "#FBBF24": DARK["warning"],
}

# 线（边框 / 下划线）
_LINE_MAP = {
    "#DFE6F0": DARK["border"],
    "#E5EAF2": DARK["border"],
    "#C9D4E3": DARK["border_strong"],
    "#B7C3D4": DARK["border_strong"],
    "#D3DBE7": DARK["border_strong"],
    "#AEBACB": DARK["border_strong"],
    "#CBD5E3": DARK["border_strong"],
    "#D0D0D0": DARK["border"],
    "#E0E0E0": DARK["border"],
    "#E8E8E8": DARK["border"],
    "#0089FF": DARK["accent"],
    "#0077E6": DARK["accent_hover"],
    "#E64646": DARK["danger_hover"],
    "#FA5151": DARK["danger"],
}

# 与属性无关、出现在任何位置都该换的（两边表里没覆盖到的杂色）
_ANY_MAP = {
    "#2196F3": DARK["accent"],
    "#1976D2": DARK["accent"],
    "#4DA8FF": DARK["accent"],
    "#42A5F5": DARK["accent_hover"],
    "#FFC300": DARK["warning"],
    "#EBB000": DARK["warning_hover"],
}

_HEX_RE = re.compile(r"#[0-9A-Fa-f]{3,8}\b")
_PROP_RE = re.compile(r"([a-zA-Z-]+)\s*:[^;{}]*$")


def _map_hex(prop, hexv):
    if hexv in _ANY_MAP:
        return _ANY_MAP[hexv]
    if prop in _BG_PROPS:
        return _SURFACE_MAP.get(hexv, hexv)
    if prop in _FG_PROPS:
        return _TEXT_MAP.get(hexv, hexv)
    if "border" in prop:
        return _LINE_MAP.get(hexv, hexv)
    # 其余属性（如 border 复合简写、outline 等）从三张表里任取
    for m in (_SURFACE_MAP, _TEXT_MAP, _LINE_MAP):
        if hexv in m:
            return m[hexv]
    return hexv


def remap_stylesheet(ss):
    """把浅色词汇的 QSS 翻译成当前主题。浅色主题下原样返回。"""
    if not ss or not isinstance(ss, str) or _current_name == "light":
        return ss

    out = []
    last = 0
    for m in _HEX_RE.finditer(ss):
        hexv = m.group(0).upper()
        # 向前找最近的属性名（决定这个色值是背景/文字/边框）
        prop_m = _PROP_RE.search(ss[:m.start()])
        prop = prop_m.group(1).lower() if prop_m else ""
        out.append(ss[last:m.start()])
        out.append(_map_hex(prop, hexv))
        last = m.end()
    out.append(ss[last:])

    result = "".join(out)
    # 箭头/对勾图标按主题取不同明度的版本（ui_assets 在 light/ dark/ 子目录各生成一套）
    result = result.replace("/light/", "/%s/" % _current_name)
    return result


# ---------------- setStyleSheet 补丁 ----------------
_orig_setStyleSheet = None


def _patched_setStyleSheet(self, ss, *args, **kwargs):
    if isinstance(ss, str):
        self._netops_light_ss = ss
        ss = remap_stylesheet(ss)
    elif ss is None:
        self._netops_light_ss = None
    return _orig_setStyleSheet(self, ss, *args, **kwargs)


def install():
    """给 QWidget.setStyleSheet 打补丁（幂等）。必须在创建任何控件前调用。"""
    global _orig_setStyleSheet
    if _orig_setStyleSheet is not None:
        return
    _orig_setStyleSheet = QWidget.setStyleSheet
    QWidget.setStyleSheet = _patched_setStyleSheet

    # QMenu 圆角补丁（三版踩坑后的最终方案）：
    # ① 什么都不做 → QSS 圆角只剪绘制层，原生窗口是矩形，四角残留白色直角块；
    # ② WA_TranslucentBackground → 普通环境四角 alpha=0 正常，但高 DPI
    #    （AA_EnableHighDpiScaling，150%/200% 实测）下 popup 的逐像素透明失效，
    #    alpha=0 的四角被 DWM 渲染成纯黑（真机截图复现 RGB(0,0,0)）；
    # ③ setMask 圆角遮罩 → 形状在系统层面不含四角像素，残留物理上不可能。
    #    挂载方式踩坑：monkey-patch QMenu.showEvent/resizeEvent 对 Python 创建的
    #    菜单生效、对菜单栏（C++ 侧 addMenu）创建的菜单不生效（sip 虚函数分发
    #    不经过类级补丁）；改用 QApplication 级事件过滤器，C++ 层面拦截所有
    #    QMenu 的 Show/Resize，与实例创建方式无关，确定性生效。
    from PyQt5.QtCore import Qt as _Qt, QEvent as _QEvent, QObject as _QObject
    from PyQt5.QtGui import QPainterPath as _QPainterPath, QRegion as _QRegion
    from PyQt5.QtCore import QRectF as _QRectF
    from PyQt5.QtWidgets import QMenu as _QMenu, QApplication as _QApplication
    global _orig_menu_init, _orig_qapp_init, _menu_radius, _menu_mask_filter
    if _orig_menu_init is None:
        _orig_menu_init = _QMenu.__init__
        _orig_qapp_init = _QApplication.__init__

        def _menu_init(self, *args, **kwargs):
            _orig_menu_init(self, *args, **kwargs)
            self.setAttribute(_Qt.WA_NoSystemBackground)   # 防系统擦除画满矩形

        def _menu_apply_mask(menu):
            # PyQt5 的 QRegion 不接受 QPainterPath 构造（TypeError），
            # 先展平为多边形再建区域
            try:
                path = _QPainterPath()
                path.addRoundedRect(_QRectF(menu.rect()), _menu_radius, _menu_radius)
                polys = path.toSubpathPolygons()
                if polys:
                    menu.setMask(_QRegion(polys[0].toPolygon()))
            except Exception:
                pass

        class _MenuMaskFilter(_QObject):
            def eventFilter(self, obj, ev):
                if ev.type() in (_QEvent.Show, _QEvent.Resize) and isinstance(obj, _QMenu):
                    _menu_apply_mask(obj)
                return False

        # QComboBox 弹出列表（QListView popup）palette 修正：
        # 主窗口 WA_TranslucentBackground 下，popup view 的 palette Window 被
        # 强制成黑（离屏实测 #000000），真机渲染路径 QSS 遮不住 → 整列黑底黑字
        # （拓扑页「添加设备-类型」下拉实锤）。显示前显式把 palette 染回主题色，
        # 渲染时无论走 QSS 还是 palette 路径都正确。
        class _ComboPopupPaletteFilter(_QObject):
            def eventFilter(self, obj, ev):
                if ev.type() != _QEvent.Show:
                    return False
                try:
                    from PyQt5.QtWidgets import QListView
                    if not isinstance(obj, QListView):
                        return False
                    from PyQt5.QtGui import QPalette as _QPal, QColor as _QColor
                    pal = obj.palette()
                    pal.setColor(_QPal.Window, _QColor(t("card")))
                    pal.setColor(_QPal.Base, _QColor(t("card")))
                    pal.setColor(_QPal.Text, _QColor(t("text")))
                    pal.setColor(_QPal.Highlight, _QColor(t("accent")))
                    pal.setColor(_QPal.HighlightedText, _QColor("#FFFFFF"))
                    obj.setPalette(pal)
                except Exception:
                    pass
                return False

        def _qapp_init(self, *args, **kwargs):
            _orig_qapp_init(self, *args, **kwargs)
            f = getattr(self, "_netops_menu_filter", None)
            if f is None:
                f = _MenuMaskFilter(self)
                self.installEventFilter(f)
                self._netops_menu_filter = f
            g = getattr(self, "_netops_combo_palette_filter", None)
            if g is None:
                g = _ComboPopupPaletteFilter(self)
                self.installEventFilter(g)
                self._netops_combo_palette_filter = g
        _QMenu.__init__ = _menu_init
        _QApplication.__init__ = _qapp_init


_orig_menu_init = None
_orig_qapp_init = None
_menu_mask_filter = None
_menu_radius = 12          # 与 styles.py QMenu border-radius 保持一致


# ---------------- 切换 ----------------

def set_theme(theme_name, app=None):
    """切换主题并刷新所有已存在的控件。

    theme_name: 'light' | 'dark'（'system' 请先用 system_theme() 归一化）
    app: 可选，用于同步 QPalette（占位文字颜色）
    """
    global _current_name
    theme_name = theme_name if theme_name in THEMES else "light"
    if theme_name == _current_name and app is None:
        return
    changed = theme_name != _current_name
    _current_name = theme_name

    if app is not None:
        _apply_palette(app)

    if not changed:
        # 首次安装（启动时）：什么都不用刷，控件还没建
        return

    # 1) 所有带样式的控件：用保存的浅色原文重新过一遍新主题
    app_inst = QApplication.instance()
    if app_inst is not None:
        for w in list(QApplication.allWidgets()):
            light_ss = getattr(w, "_netops_light_ss", None)
            if light_ss:
                w.setStyleSheet(light_ss)

    # 2) 手绘控件的刷新回调（拓扑画布、自定义标题栏重绘等）
    for cb in list(_change_callbacks):
        try:
            cb()
        except Exception:
            pass


def _apply_palette(app):
    """QPalette 层面需要主题感知的颜色（QSS 覆盖不到的）：
    - PlaceholderText：占位文字
    - AlternateBase：斑马纹交替行（setAlternatingRowColors(True) 的列表/表格
      走 palette 而非 QSS——深色主题下不映射会冒出刺眼的白色斑马行，
      模板管理器深色截图实锤：交替行 #F5F5F5 + 深色前景几乎不可读）
    - Highlight / HighlightedText：无 QSS 选中规则的控件兜底选中色
      （原生 #0078d7 在深色下偏闷，统一到主题 accent）
    注意：必须基于 app.palette() 增量覆盖——QPalette() 默认构造所有角色都是
    纯黑，直接 setPalette 会让走 palette 渲染的控件黑底黑字（实锤：拓扑页
    添加设备的类型下拉 QListView 弹窗，Windows 真机下整列全黑看不清）。
    """
    from PyQt5.QtGui import QPalette
    pal = QPalette(app.palette())
    pal.setColor(QPalette.PlaceholderText, QColor(t("placeholder")))
    pal.setColor(QPalette.AlternateBase, QColor(t("zebra")))
    pal.setColor(QPalette.Highlight, QColor(t("accent")))
    pal.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    app.setPalette(pal)


def system_theme():
    """跟随系统：读 Windows 亮/暗应用模式；失败按浅色"""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        try:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        finally:
            winreg.CloseKey(key)
        return "dark" if value == 0 else "light"
    except Exception:
        return "light"
