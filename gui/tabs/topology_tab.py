#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
网络拓扑可视化页（二开重构 v3：参数结合拓扑的运维驾驶舱）

数据源（全部只读采集）：
  1) LLDP 邻居  —— 只能发现"开了 LLDP 的网管设备"（交换机/路由器）
  2) MAC 地址表 —— 发现接在端口上的终端（PC/打印机/摄像头），终端不应答 LLDP
  3) ARP 表     —— 给终端补 IP，便于 Ping / 定位
  4) 本机信息   —— 始终绘制「本机 PC」节点，并把 Console 线画成一条链路
  5) 端口链路状态 + 接口解析 —— 交换机节点画成真实端口面板（v3 新增）

交互：
  - 单击选中 → 右侧详情面板联动（非模态，参数直接可见）
  - 双击 / 右键 → 设备面板：端口配置 / 查看配置 / 健康度 / 端口表 / Ping / 备份
  - 点击端口面板上的端口格 → 直接打开该口配置生成器（预选）
  - hover 端口格 → 端口名/状态/VLAN/描述（不打开任何窗口）
  - 「一键采集」：不离开本页直接发起 Console 采集
Qt 原生图形框架实现，不重复造绘图轮子
"""

import math
import re

from PyQt5.QtCore import QEvent, QPointF, QRectF, Qt, QTimer
from PyQt5.QtGui import (QBrush, QColor, QFont, QFontMetrics, QPainter,
                          QPainterPath, QPen, QMouseEvent)
from PyQt5.QtWidgets import (QApplication, QAbstractItemView, QCheckBox, QComboBox,
                              QFormLayout,
                              QGraphicsItem, QGraphicsObject, QGraphicsScene,
                              QGraphicsTextItem, QGraphicsView, QGroupBox,
                              QHBoxLayout, QLabel, QLineEdit, QListWidget,
                              QListWidgetItem, QMenu,
                              QPushButton, QScrollArea, QSpinBox, QSplitter,
                              QTableWidget, QTableWidgetItem, QTextEdit,
                              QVBoxLayout, QWidget, QHeaderView)

from gui.styles import MODERN_STYLE, TOOLTIP_STYLE, DIALOG_STYLE
from gui.dialogs.base import (BaseDialog, make_button, info_box, warn_box,
                              question_box)
from gui.widget_utils import page_header
from gui import theme
from modules.config_visualizer import expand_vlan_body
from modules.nl_engine import e_port_access, e_port_trunk

# ---------------------------------------------------------------- 视觉规范
def KIND_STYLE():
    """节点配色：画的时候现取主题（切主题后 scene.update() 即全量生效）"""
    from gui import theme
    t = theme.t
    return {
        #          填充             描边              主文字      副文字
        "switch":      (t("accent"), t("accent_pressed"), "#FFFFFF", t("accent_light")),
        "placeholder": (t("card_alt"), t("border_strong"), t("text_muted"), t("text_muted")),
        "neighbor":    (t("card"), t("accent"), t("text"), t("text_muted")),
        "pc":          (t("success"), t("success_hover"), "#FFFFFF", t("success")),
        "host":        (t("card"), t("border_strong"), t("text"), t("text_muted")),
        "unknown":     (t("card_alt"), t("border_strong"), t("text_sub"), t("text_muted")),
    }
NODE_ICON_W, NODE_ICON_H = 88, 58


def _short_port(port: str) -> str:
    """长端口名缩写：GigabitEthernet1/0/12 → GE1/0/12（节点下方标签用）"""
    p = port or ""
    for full, abbr in (("Ten-GigabitEthernet", "XGE"),
                      ("FortyGigE", "FGE"),
                      ("GigabitEthernet", "GE"),
                      ("FastEthernet", "Fa"),
                      ("Ethernet", "Eth"),
                      ("Bridge-Aggregation", "BAGG"),
                      ("Port-channel", "Po")):
        p = p.replace(full, abbr)
    return p


def _norm_port(p: str) -> str:
    """端口名归一化（大小写/全称与缩写/空格差异 → 可比对）"""
    s = (p or "").strip().lower().replace(" ", "")
    for full, abbr in (("ten-gigabitethernet", "xge"), ("fortygige", "fge"),
                       ("m-gigabitethernet", "mge"), ("gigabitethernet", "ge"),
                       ("fastethernet", "fa"), ("ethernet", "eth")):
        s = s.replace(full, abbr)
    return s


def _usable_ip(v: str) -> str:
    """可用 IP 提取：占位值（未获取/—/空）不算 IP
    （真机实测：终端无 ARP 数据时 meta 存“未获取”，若不拦会生成「Ping 未获取」菜单项）"""
    v = (v or "").split()[0] if (v or "").strip() else ""
    return "" if v in ("", "未获取", "—", "-") else v


# ---------------------------------------------------------------- 端口面板几何
# 交换机节点按真实端口排布画端口格：
#   - 电口（GE）与光口（XGE/FGE）分组，光口用浅蓝底区分
#   - 每格一盏状态灯：绿=UP / 灰=DOWN / 蓝=Trunk / 红边=手工 shutdown / 空心=无数据
#   - 格内标端口序号，hover 显全名，点击直接进端口配置
PORT_CELL_W, PORT_CELL_H, PORT_CELL_GAP = 17, 20, 3
PORT_GROUP_PAD = 8          # 分组内边距
PORT_PER_ROW_MAX = 14       # 电口每行最多格数（>28 口时换行）


def _port_label(name: str) -> str:
    """端口格内序号：取名字里最后一段数字（GE1/0/12 → 12；XGE1/0/25 → 25）"""
    nums = re.findall(r"\d+", name or "")
    return nums[-1] if nums else "?"


def _port_state(itf: dict, link_up: dict) -> str:
    """端口状态：up/down/trunk/shutdown/unknown（采集读不到链路时 unknown）"""
    detail = itf.get("detail") or {}
    if detail.get("状态") == "administratively down":
        return "shutdown"
    vlan = str(detail.get("VLAN", ""))
    if vlan.startswith("trunk"):
        return "trunk"
    key = _norm_port(itf["name"])
    for k, up in (link_up or {}).items():
        if _norm_port(k) == key:
            return "up" if up else "down"
    return "unknown"


def _port_tip(itf: dict, state: str) -> str:
    d = itf.get("detail") or {}
    state_txt = {"up": "链路 UP", "down": "链路 DOWN", "trunk": "Trunk 干道",
                 "shutdown": "已手工关闭(shutdown)", "unknown": "链路状态未知"}[state]
    bits = [itf["name"], state_txt]
    if d.get("VLAN"):
        bits.append(f"VLAN {d['VLAN']}")
    if d.get("描述"):
        bits.append(d["描述"])
    if d.get("IP"):
        bits.append(f"IP {d['IP']}")
    return "\n".join(bits) + "\n（点击端口格 → 打开该口配置生成器）"


# ---------------------------------------------------------------- 连线
class LinkItem(QGraphicsItem):
    """两端节点之间的连线（位置实时跟随节点，无需重建）。

    state 决定视觉语义（参数直接上图，不弹窗就能读懂链路）：
      "up"       实线 + 主题绿   —— 链路 UP（电/光口正常转发）
      "down"     实线 + 弱灰      —— 链路 DOWN
      "unknown"  虚线 + 警戒橙   —— 有线但对端无 LLDP/MAC（未识别设备）
      "console"  虚线 + 主题蓝   —— Console 管理线（不是转发链路）
      默认        实线 + 常规灰   —— 普通链路（状态未知/未特别标注）
    """

    def __init__(self, a, b, label="", dashed=False, state=""):
        super().__init__()
        self.a, self.b = a, b
        self.label = label or ""
        self.state = "console" if (not state and dashed) else state
        if dashed and not state:
            self.state = "console"
        self.dashed = dashed or self.state in ("unknown", "console")
        self.setZValue(-1)
        a.links.append(self)
        b.links.append(self)
        scene = a.scene() or b.scene()
        if scene is not None:
            scene.addItem(self)   # 必须入场景，否则画不出来

    def _pen(self):
        color_map = {
            "up": theme.t("success"),
            "down": theme.t("scroll_handle"),
            "unknown": theme.t("warning"),
            "console": theme.t("accent"),
        }
        pen = QPen(QColor(color_map.get(self.state, theme.t("scroll_handle_hover"))), 2)
        if self.state == "up":
            pen.setWidth(3)          # UP 链路视觉加权（一眼看到主干）
        if self.dashed:
            pen.setStyle(Qt.DashLine)
        return pen

    def boundingRect(self):
        pa, pb = self.a.scenePos(), self.b.scenePos()
        # 曲线最大法向偏移 36，中点偏移为其半；标签胶囊最宽 ~110
        return QRectF(pa, pb).normalized().adjusted(-110, -70, 110, 70)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        pa, pb = self.a.scenePos(), self.b.scenePos()
        painter.setPen(self._pen())
        # 圆角连线：二次贝塞尔（draw.io / NetBox 拓扑的标准画法）——控制点
        # 取弦中点沿法线偏移，短链弯度小、长链弯度大且有上限，避开“硬直线”
        d = pb - pa
        dist = (d.x() ** 2 + d.y() ** 2) ** 0.5 or 1.0
        k = max(14.0, min(dist * 0.10, 36.0))
        ctrl = QPointF((pa.x() + pb.x()) / 2 + d.y() / dist * k,
                       (pa.y() + pb.y()) / 2 - d.x() / dist * k)
        path = QPainterPath()
        path.moveTo(pa)
        path.quadTo(ctrl, pb)
        painter.drawPath(path)
        if not self.label:
            return
        # 标签贴在曲线真实中点（贝塞尔中点 = 0.25A + 0.5C + 0.25B）
        mid = QPointF(0.25 * pa.x() + 0.5 * ctrl.x() + 0.25 * pb.x(),
                      0.25 * pa.y() + 0.5 * ctrl.y() + 0.25 * pb.y())
        font = QFont("Microsoft YaHei UI", 9)
        if self.state == "up":
            font.setBold(True)
        fm = QFontMetrics(font)
        tw = fm.horizontalAdvance(self.label) + 14
        th = fm.height() + 4
        rect = QRectF(mid.x() - tw / 2, mid.y() - th - 10, tw, th)
        painter.setPen(Qt.NoPen)
        label_bg = QColor(theme.t("card"))
        label_bg.setAlpha(232)
        painter.setBrush(label_bg)
        painter.drawRoundedRect(rect, 7, 7)
        painter.setPen(QColor(theme.t("text_muted") if self.state != "up"
                              else theme.t("text")))
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignCenter, self.label)

    def refresh(self):
        self.prepareGeometryChange()
        self.update()


# ---------------------------------------------------------------- 节点
class DeviceNode(QGraphicsObject):
    """可拖动设备节点（交换机 / PC / 邻居 / 终端），带矢量图标与悬停反馈。

    v3 新增（参数结合拓扑）：
      - 交换机节点（kind=switch 且有 ports 数据）画成**真实端口面板**：
        按接口类型分组排布端口格，每格一盏状态灯，hover 看参数、点击进配置
      - 所有节点支持**参数徽章**（IP / VLAN / 健康度等小胶囊直接上图）
      - 布局以 _w/_h 自适应，端口面板节点比抽象图标宽得多
    """

    def __init__(self, name, kind="switch", meta=None, subtitle="",
                 ports=None, badges=None, health=None):
        super().__init__()
        self.device_name = name or "设备"
        self.kind = kind
        self.meta = meta or {}
        self.subtitle = subtitle or ""
        self.links = []
        self._hover = False
        self._active = False

        # ---- v3：端口面板 / 徽章 / 健康度 ----
        self._ports = ports or []      # [{name, state, label, tip}]
        self._badges = badges or []    # [(text, tone)]  tone: ip/vlan/ok/warn/danger
        self._health = health          # (score, level)  交换机健康度徽章
        self._port_rects = []          # paint 时缓存 [(name, QRectF)]（节点本地坐标）
        self._hover_port = ""          # 当前 hover 的端口格
        self._press_port = ""          # press 命中的端口格（release 同格才算点击）
        self._vlan_boxes = []          # 本节点参与的 VLAN 分组框（拖动时通知重算几何）

        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setZValue(2)
        self.setToolTip(self._tooltip())

        f_name = QFont("Microsoft YaHei UI", 10)
        f_name.setBold(True)
        fm = QFontMetrics(f_name)
        fm2 = QFontMetrics(QFont("Microsoft YaHei UI", 9))
        self._w = max(NODE_ICON_W, fm.horizontalAdvance(self.device_name) + 8,
                      fm2.horizontalAdvance(self.subtitle) + 8 if self.subtitle else 0)
        self._compute_panel()

    # ---- 端口面板几何 ----
    def _compute_panel(self):
        """交换机有 ports 时计算端口面板尺寸；其余节点维持旧尺寸"""
        self._panel = None
        if self.kind != "switch" or not self._ports:
            return
        # 按接口类型分组（GE 电口 / 10GE 光口 / 聚合口 …），保持采集顺序
        groups = []
        for p in self._ports:
            if groups and groups[-1][0] == p["group"]:
                groups[-1][1].append(p)
            else:
                groups.append((p["group"], [p]))
        total_w = 0
        total_h = 0
        for gname, plist in groups:
            n = len(plist)
            # 端口数多于每行上限时铺满上限换行；少量时按实际数量收窄
            cols = 12 if n > 12 else n
            gw = cols * (PORT_CELL_W + PORT_CELL_GAP) - PORT_CELL_GAP + 2 * PORT_GROUP_PAD
            rows = math.ceil(n / cols)
            gh = rows * (PORT_CELL_H + PORT_CELL_GAP) - PORT_CELL_GAP + 2 * PORT_GROUP_PAD + 14
            total_w = max(total_w, gw)
            total_h += gh + 6
        total_h -= 6
        fm_name = QFontMetrics(QFont("Microsoft YaHei UI", 11, QFont.Bold))
        fm_badge = QFontMetrics(QFont("Microsoft YaHei UI", 9))
        badge_w = 0
        x = 8
        for text, tone in self._badges:
            x += fm_badge.horizontalAdvance(text) + 18 + 6
        badge_w = x
        pw = max(total_w, fm_name.horizontalAdvance(self.device_name) + 20,
                 fm_badge.horizontalAdvance(self.subtitle) + 16, badge_w) + 16
        ph = 30 + total_h + (22 if self.subtitle else 0) + (26 if self._badges else 0) + 14
        self._panel = {
            "groups": groups, "pw": pw, "ph": ph,
            "title_h": 30, "sub_h": 22 if self.subtitle else 0,
            "badge_h": 26 if self._badges else 0,
        }
        self._w = max(self._w, pw)
        # 预填命中表：没渲染过也能命中（测试/自动化友好）
        self._port_rects = [(n, r, d) for n, r, d in self._panel_layout() if not n.startswith("_group:")]

    def _panel_layout(self):
        """端口格在节点本地坐标中的排布（画与命中共用一份，永不漂移）。
        所有分组矩形统一面板宽（左右对齐），格子阵在组内居中——
        光口/聚合口这类小分组不会挂左留大片空白（真机实测观感问题）"""
        if not self._panel:
            return []
        p = self._panel
        group_w = p["pw"] - 16
        left = -p["pw"] / 2 + 8
        y = -p["ph"] / 2 + p["title_h"]
        rects = []
        for gname, plist in p["groups"]:
            n = len(plist)
            cols = 12 if n > 12 else n
            rows = math.ceil(n / cols)
            gh = rows * (PORT_CELL_H + PORT_CELL_GAP) - PORT_CELL_GAP + 2 * PORT_GROUP_PAD
            group_rect = QRectF(left, y, group_w, gh + 14)
            rects.append(("_group:" + gname, group_rect, gname))
            cells_w = cols * PORT_CELL_W + (cols - 1) * PORT_CELL_GAP
            gx = left + (group_w - cells_w) / 2
            gy = y + 14 + PORT_GROUP_PAD
            for i, port in enumerate(plist):
                r, c = divmod(i, cols)
                cell = QRectF(gx + c * (PORT_CELL_W + PORT_CELL_GAP),
                             gy + r * (PORT_CELL_H + PORT_CELL_GAP),
                             PORT_CELL_W, PORT_CELL_H)
                rects.append((port["name"], cell, port))
            y += gh + 14 + 6
        return rects

    # ---- 几何 ----
    def boundingRect(self):
        if self._panel:
            pw, ph = self._panel["pw"] + 24, self._panel["ph"] + 24
            return QRectF(-pw / 2, -ph / 2, pw, ph)
        half = self._w / 2 + 12
        return QRectF(-half, -NODE_ICON_H / 2 - 14, half * 2, NODE_ICON_H + 76)

    def _tooltip(self):
        lines = [f"{self.device_name}"]
        if self.subtitle:
            lines.append(self.subtitle)
        lines += [f"{k}: {v}" for k, v in self.meta.items() if v]
        lines.append("双击/右键 → 设备面板；单击 → 右侧详情联动")
        return "\n".join(lines)

    # ---- 绘制 ----
    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        if self._panel:
            self._paint_switch_panel(painter)
            return
        fill, border = KIND_STYLE().get(self.kind, KIND_STYLE()["host"])[:2]
        fill, border = QColor(fill), QColor(border)
        if self.kind in ("placeholder", "unknown"):
            pen = QPen(border, 2, Qt.DashLine)
        elif self._hover or self._active:
            pen = QPen(QColor(theme.t("accent")) if self.kind != "host" else QColor(theme.t("text_sub")), 3)
        else:
            pen = QPen(border, 2)

        painter.setPen(pen)
        painter.setBrush(QBrush(fill))
        self._draw_icon(painter, fill, border)

        # 名称（在图标下方，颜色跟主题走，避免深色主题下黑字画在深底上）
        f = QFont("Microsoft YaHei UI", 10)
        f.setBold(True)
        painter.setFont(f)
        painter.setPen(QColor(theme.t("text")))
        painter.drawText(QRectF(-self._w / 2, NODE_ICON_H / 2 + 2, self._w, 20),
                         Qt.AlignHCenter | Qt.AlignVCenter, self.device_name)

        # 副标题（端口 / 型号 / 说明）：text_sub 比 muted 深一档（视觉审查两轮指出浅色底上辨识不足）
        if self.subtitle:
            painter.setFont(QFont("Microsoft YaHei UI", 9))
            painter.setPen(QColor(theme.t("text_sub")))
            painter.drawText(QRectF(-self._w / 2, NODE_ICON_H / 2 + 22, self._w, 18),
                             Qt.AlignHCenter | Qt.AlignVCenter, self.subtitle)

        # 参数徽章行（IP / VLAN 直接上图，不用点开任何窗口）
        if self._badges:
            self._paint_badges(painter, NODE_ICON_H / 2 + 44)

        # 选中环
        if self.isSelected():
            painter.setPen(QPen(QColor(theme.t("accent")), 2, Qt.DotLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(
                QRectF(-self._w / 2 - 8, -NODE_ICON_H / 2 - 12,
                       self._w + 16, NODE_ICON_H + 22), 14, 14)

    # ---- 真实端口面板（交换机） ----
    def _paint_switch_panel(self, painter):
        p = self._panel
        rect = QRectF(-p["pw"] / 2, -p["ph"] / 2, p["pw"], p["ph"])

        # 面板底：卡片色 + 细边；hover 时边框变主蓝
        fill = QColor(theme.t("card"))
        border = QColor(theme.t("accent") if (self._hover or self._active)
                        else theme.t("border_strong"))
        if self.isSelected():
            border = QColor(theme.t("accent"))
        painter.setPen(QPen(border, 2))
        painter.setBrush(QBrush(fill))
        painter.drawRoundedRect(rect, 12, 12)

        # 标题行：设备名（左）+ 健康度徽章（右）
        f_name = QFont("Microsoft YaHei UI", 11)
        f_name.setBold(True)
        painter.setFont(f_name)
        painter.setPen(QColor(theme.t("text")))
        name_rect = QRectF(rect.left() + 10, rect.top() + 4,
                           p["pw"] - 26 - (54 if self._health else 0), 22)
        painter.drawText(name_rect, Qt.AlignVCenter | Qt.AlignLeft, self.device_name)
        if self._health:
            score, level = self._health
            tone = "ok" if score >= 85 else ("warn" if score >= 60 else "danger")
            brect = QRectF(rect.right() - 60, rect.top() + 5, 52, 20)
            self._paint_one_badge(painter, brect, f"♥ {score}", tone)

        # 端口组
        self._port_rects = []
        for key, crect, data in self._panel_layout():
            if key.startswith("_group:"):
                # 组底 + 组名
                gfill = QColor(theme.t("card_alt"))
                if "光口" in data:
                    gfill = QColor(theme.t("accent_light"))
                    gfill.setAlpha(120)
                painter.setPen(Qt.NoPen)
                painter.setBrush(gfill)
                painter.drawRoundedRect(crect, 8, 8)
                painter.setPen(QColor(theme.t("text_muted")))
                painter.setFont(QFont("Microsoft YaHei UI", 8))
                painter.drawText(QRectF(crect.left() + PORT_GROUP_PAD, crect.top(),
                                        crect.width() - 2 * PORT_GROUP_PAD, 13),
                                 Qt.AlignVCenter | Qt.AlignLeft, data)
                continue
            self._port_rects.append((key, crect, data))
            state = data["state"]
            cell = crect.adjusted(0, 0, 0, 0)
            hovered = key == self._hover_port
            # 状态灯颜色：绿 UP / 灰 DOWN / 蓝 Trunk / 红边 shutdown / 空心 unknown
            colors = {
                "up": theme.t("success"),
                "down": theme.t("track"),
                "trunk": theme.t("accent"),
                "shutdown": theme.t("danger"),
                "unknown": theme.t("card"),
            }
            c = QColor(colors.get(state, theme.t("card")))
            if state == "down":
                c = QColor(theme.t("scroll_handle"))
            painter.setBrush(QBrush(c))
            border_col = QColor(theme.t("accent") if hovered
                                else theme.t("border_strong"))
            if state == "shutdown":
                border_col = QColor(theme.t("danger"))
            elif state == "unknown":
                border_col = QColor(theme.t("border_strong"))
            painter.setPen(QPen(border_col, 1 if not hovered else 2))
            painter.drawRoundedRect(cell, 3, 3)
            # VLAN 色条（v3.1 参数可视化）：Access 口且知道 VLAN 时，格底画 VLAN 色条，
            # 同 VLAN 端口同色——扫一眼就知道哪些口在同一广播域（与分组框/图例同色源）
            if data.get("vlan"):
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(theme.vlan_color(data["vlan"])))
                painter.drawRect(QRectF(cell.left() + 2, cell.bottom() - 4,
                                        cell.width() - 4, 3.5))
            # 格内端口序号
            fnum = QFont("Microsoft YaHei UI", 7)
            painter.setFont(fnum)
            num_col = QColor("#FFFFFF") if state in ("up", "trunk", "shutdown") \
                else QColor(theme.t("text_muted"))
            painter.setPen(num_col)
            painter.drawText(cell, Qt.AlignCenter, data["label"])

        # 副标题（型号 · 接口数）
        if self.subtitle:
            fy = rect.bottom() - p["badge_h"] - p["sub_h"] - 8
            painter.setFont(QFont("Microsoft YaHei UI", 9))
            painter.setPen(QColor(theme.t("text_sub")))
            painter.drawText(QRectF(rect.left() + 10, fy, p["pw"] - 20, 18),
                             Qt.AlignVCenter | Qt.AlignLeft, self.subtitle)

        # 参数徽章行
        if self._badges:
            self._paint_badges(painter,
                               rect.bottom() - p["badge_h"] - 10)

    # ---- 徽章 ----
    def _paint_badges(self, painter, top_y):
        fm = QFontMetrics(QFont("Microsoft YaHei UI", 9))
        x = -self._panel["pw"] / 2 + 10 if self._panel else -self._w / 2
        y = top_y
        for text, tone in self._badges:
            w = fm.horizontalAdvance(text) + 18
            self._paint_one_badge(painter, QRectF(x, y, w, 20), text, tone)
            x += w + 6

    def _paint_one_badge(self, painter, rect, text, tone):
        """小胶囊徽章：浅底 + 深字（主题感知）。
        tone 支持 "vlan:<id>"——用 VLAN 配色，与分组框/端口色条/图例同源"""
        if str(tone).startswith("vlan:"):
            fg = theme.vlan_color(str(tone).split(":", 1)[1])
        else:
            palette = {
                "ip":    (theme.t("success"), theme.t("card")),
                "vlan":  (theme.t("accent"), theme.t("card")),
                "ok":    (theme.t("success"), theme.t("card")),
                "warn":  (theme.t("warning"), theme.t("card")),
                "danger": (theme.t("danger"), theme.t("card")),
            }
            fg, bg = palette.get(tone, (theme.t("text_sub"), theme.t("card")))
        bgc = QColor(theme.t("card"))
        # 半透明浅底：拿前景色混一层白色（浅色主题）；深色主题混卡片色
        if theme.is_dark():
            base = QColor(theme.t("card"))
            mixed = QColor(theme.t("card"))
            t = 34
            mixed.setRed((base.red() * (100 - t) + QColor(fg).red() * t) // 100)
            mixed.setGreen((base.green() * (100 - t) + QColor(fg).green() * t) // 100)
            mixed.setBlue((base.blue() * (100 - t) + QColor(fg).blue() * t) // 100)
            bgc = mixed
        else:
            bgc = QColor(fg)
            bgc.setAlpha(38)
        painter.setPen(Qt.NoPen)
        painter.setBrush(bgc)
        painter.drawRoundedRect(rect, 10, 10)
        painter.setPen(QColor(fg))
        painter.setFont(QFont("Microsoft YaHei UI", 9))
        painter.drawText(rect, Qt.AlignCenter, text)

    def _draw_icon(self, painter, fill, border):
        """按设备类型画矢量图标（不依赖任何图片资源）"""
        if self.kind == "pc":
            # 显示器 + 支架
            screen = QRectF(-34, -26, 68, 46)
            painter.drawRoundedRect(screen, 7, 7)
            painter.setBrush(QBrush(fill))
            painter.drawRect(QRectF(-7, 20, 14, 7))
            painter.drawRoundedRect(QRectF(-20, 26, 40, 6), 3, 3)
            # 屏幕内容线
            painter.setPen(QPen(QColor(255, 255, 255, 150), 2))
            for i, y in enumerate((-15, -6, 3)):
                painter.drawLine(QPointF(-24, y), QPointF(-24 + (40 if i != 1 else 26), y))
        elif self.kind == "host":
            # 终端小方盒
            body = QRectF(-30, -22, 60, 40)
            painter.drawRoundedRect(body, 8, 8)
            painter.setPen(QPen(QColor(theme.t("border_strong")), 2))
            painter.drawLine(QPointF(-18, 8), QPointF(18, 8))
        else:
            # 交换机：圆角机身 + 端口指示灯
            body = QRectF(-40, -26, 80, 50)
            painter.drawRoundedRect(body, 12, 12)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(255, 255, 255, 210) if self.kind == "switch"
                                    else QColor(theme.t("border_strong"))))
            for row in range(2):
                for i in range(6):
                    painter.drawRoundedRect(
                        QRectF(-34 + i * 11.5, 2 + row * 9, 7, 6), 1.5, 1.5)
            if self.kind == "switch":
                painter.setBrush(QBrush(QColor(theme.t("success"))))
                painter.drawEllipse(QRectF(26, -20, 7, 7))

    # ---- 交互 ----
    def hoverEnterEvent(self, event):
        self._hover = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hover = False
        self._hover_port = ""
        self.update()
        super().hoverLeaveEvent(event)

    def hoverMoveEvent(self, event):
        """hover 端口格：tooltip 换成该端口的参数（VLAN/描述/状态）"""
        hit = self._port_at(event.pos())
        if hit != self._hover_port:
            self._hover_port = hit[0] if hit else ""
            tip = hit[2]["tip"] if hit else self._tooltip()
            self.setToolTip(tip)
            self.update()
        super().hoverMoveEvent(event)

    def _port_at(self, local_pos):
        """命中检测：返回 (name, rect, data) 或 None"""
        for name, rect, data in self._port_rects:
            if rect.contains(local_pos):
                return (name, rect, data)
        return None

    def mousePressEvent(self, event):
        hit = self._port_at(event.pos()) if event.button() == Qt.LeftButton else None
        if hit:
            # 命中端口格：不启动拖动（吃掉 press），release 同格才触发配置
            self._press_port = hit[0]
            self._hover_port = hit[0]
            self.update()
            event.accept()
            return
        self._press_port = ""
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._press_port:
            hit = self._port_at(event.pos())
            if hit and hit[0] == self._press_port:
                cb = getattr(self.scene(), "on_port_clicked", None)
                if cb:
                    cb(self, hit[0])
            self._press_port = ""
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            for link in self.links:
                link.refresh()
            for box in self._vlan_boxes:
                box.refresh()
        return super().itemChange(change, value)

    def mouseDoubleClickEvent(self, event):
        # 双击落在端口格上：不弹设备面板（避免误弹，端口单击已能进配置）
        if self._port_at(event.pos()):
            event.accept()
            return
        cb = getattr(self.scene(), "on_node_activated", None)
        if cb:
            cb(self)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        if self._port_at(event.pos()):
            event.accept()      # 端口格上右键不出设备菜单
            return
        cb = getattr(self.scene(), "on_node_menu", None)
        if cb:
            cb(self, event.screenPos())
            event.accept()
            return
        super().contextMenuEvent(event)


# ---------------------------------------------------------------- VLAN 分组框
class VlanGroupItem(QGraphicsItem):
    """VLAN 分组围栏：同 VLAN 终端被圆角虚线框围住（颜色=VLAN 色），
    参数结合拓扑的分组层——图上直接看到「谁和谁在同一个广播域」。
    几何实时跟随成员节点（拖动节点框自动重算），标签带 VLAN ID 与台数。"""

    def __init__(self, vlan_id, nodes):
        super().__init__()
        self.vlan = str(vlan_id)
        self.nodes = list(nodes)
        self.setZValue(-2)          # 连线(-1)之下、画布之上
        self._hover = False
        self.setAcceptHoverEvents(True)
        self.setToolTip(f"VLAN {self.vlan} 广播域：{len(self.nodes)} 台终端" +
                         "\n（同 VLAN 终端互通；改端口 VLAN = 改它的广播域）")

    def _union_rect(self):
        rect = QRectF()
        for n in self.nodes:
            r = n.boundingRect().translated(n.scenePos())
            rect = r if rect.isNull() else rect.united(r)
        if rect.isNull():
            return QRectF()
        return rect.adjusted(-42, -40, 42, 26)

    def boundingRect(self):
        return self._union_rect()

    def paint(self, painter, option, widget=None):
        rect = self._union_rect()
        if rect.isNull():
            return
        painter.setRenderHint(QPainter.Antialiasing)
        color = QColor(theme.vlan_color(self.vlan))
        # 半透明 VLAN 色底 + 同色虚线边框
        fill = QColor(color)
        fill.setAlpha(16)
        painter.setPen(Qt.NoPen)
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, 14, 14)
        pen = QPen(color, 2)
        pen.setStyle(Qt.DashLine if not self._hover else Qt.SolidLine)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect, 14, 14)
        # 左上标签：色块 + VLAN n · 台数
        font = QFont("Microsoft YaHei UI", 9)
        font.setBold(True)
        fm = QFontMetrics(font)
        label = f"VLAN {self.vlan} · {len(self.nodes)} 台"
        tw = fm.horizontalAdvance(label) + 34
        th = fm.height() + 6
        lrect = QRectF(rect.left() + 12, rect.top() - th / 2, tw, th)
        painter.setPen(Qt.NoPen)
        bg = QColor(theme.t("card"))
        bg.setAlpha(232)
        painter.setBrush(bg)
        painter.drawRoundedRect(lrect, 9, 9)
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(lrect.left() + 8, lrect.center().y() - 4, 8, 8), 2, 2)
        painter.setPen(QColor(theme.t("text")))
        painter.setFont(font)
        painter.drawText(QRectF(lrect.left() + 20, lrect.top(), tw, th),
                         Qt.AlignVCenter | Qt.AlignLeft, label)

    def refresh(self):
        self.prepareGeometryChange()
        self.update()

    def hoverEnterEvent(self, event):
        self._hover = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hover = False
        self.update()
        super().hoverLeaveEvent(event)


# ---------------------------------------------------------------- 场景
class TopologyScene(QGraphicsScene):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.on_node_activated = None   # 双击回调
        self.on_node_menu = None        # 右键回调
        self.on_port_clicked = None     # 端口格点击回调（v3：面板端口直配）

    def nodes(self):
        return [i for i in self.items() if isinstance(i, DeviceNode)]

    def auto_layout(self):
        """层级布局（参考 L0p4Map 层级拓扑范式，符合网络实际结构）：
        - 交换机面板在顶部中央（运维视角的"根"）
        - 本机 PC 在左侧（Console 维护位）
        - LLDP 邻居 / 未识别设备第二层横排（同层设备）
        - 终端第三层，按接入端口分组聚合（同端口下的终端挨着排）"""
        nodes = self.nodes()
        if not nodes:
            return
        sw = next((n for n in nodes if n.kind in ("switch", "placeholder")), None)
        pc = next((n for n in nodes if n.kind == "pc"), None)
        nbs = [n for n in nodes if n.kind in ("neighbor", "unknown")]
        hosts = [n for n in nodes if n.kind == "host"]

        if sw:
            sw.setPos(0, 0)
        if pc:
            pc.setPos(-380, -40)

        if nbs:
            n = len(nbs)
            per_row = 4
            for i, node in enumerate(nbs):
                row, col = divmod(i, per_row)
                in_row = min(per_row, n - row * per_row)
                # 交换机面板较宽，第二层从面板下方展开
                x = (col - (in_row - 1) / 2) * 260
                y = 210 + row * 130
                node.setPos(x, y)

        if hosts:
            # 按 VLAN 分组排布（与分组围栏对齐，围栏自动围住）；
            # 无 VLAN 数据的终端退回按接入端口分组
            groups = {}
            order = []
            for h in hosts:
                v = str(h.meta.get("VLAN", "") or "").strip()
                key = v if v.isdigit() else ("p:" + _norm_port(h.meta.get("接入端口", "") or "-"))
                if key not in groups:
                    groups[key] = []
                    order.append(key)
                groups[key].append(h)
            n_groups = len(order)
            for gi, key in enumerate(order):
                gx = (gi - (n_groups - 1) / 2) * 340
                for hi, node in enumerate(groups[key]):
                    node.setPos(gx + (hi % 2) * 170 - 85, 430 + (hi // 2) * 124)

        # 空状态/采集后通用：布局完成由页面按钮的 fit_content 统一适配视口。
        # （历史版本尾部 centerOn(0,160) 硬编码场景点，把视口中心对到节点群下方，
        # 内容悬在视口上部——真机截图反馈“画面飘移”，已删）


# ---------------------------------------------------------------- 画布视图（点阵背景）
class TopologyView(QGraphicsView):
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        # 拖动残影根治（真机实锤）：主窗口 WA_TranslucentBackground（无边框半透明）下，
        # 默认 MinimalViewportUpdate 的局部重绘没有不透明背景可擦除，拖动节点时旧位置
        # 残留浅蓝残影——半透明窗口内的 QGraphicsView 必须全量重绘视口（Qt 官方口径）。
        # 拓扑画布节点少，全量每帧 <5ms，性能无感。
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        # 不开鼠标跟踪时 hover 事件只在按住按键时才产生，悬停高亮会是死的（真机实测发现）
        self.setMouseTracking(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet("QGraphicsView { background: #F7F9FC; border: 1px dashed #D3DBE7;"
                           " border-radius: 12px; }")
        self.setSceneRect(QRectF(-900, -600, 1800, 1200))

    def drawBackground(self, painter, rect):
        painter.fillRect(rect, QColor(theme.t("canvas_bg")))
        painter.setPen(QPen(QColor(theme.t("canvas_grid")), 1))
        step = 28
        left = int(rect.left()) - int(rect.left()) % step
        top = int(rect.top()) - int(rect.top()) % step
        x = left
        while x < rect.right():
            y = top
            while y < rect.bottom():
                painter.drawPoint(QPointF(x, y))
                y += step
            x += step

    def wheelEvent(self, event):
        self._keep_center = False   # 用户主动缩放：不再自动对中（免得对着光标缩放被拽回）
        factor = 1.12 if event.angleDelta().y() > 0 else 1 / 1.12
        cur = self.transform().m11()
        if 0.45 <= cur * factor <= 2.6:
            self.scale(factor, factor)

    def mousePressEvent(self, event):
        self._keep_center = False   # 手动平移同理
        super().mousePressEvent(event)

    def resizeEvent(self, event):
        """视口尺寸变化（splitter 重新分配/窗口缩放）时保持内容居中。
        QSplitter 的尺寸是异步稳定的：fit_content 后 processEvents 一轮视口宽
        可变 180px+，QGraphicsView 对 resize 的默认补偿会把场景中心点拖偏
        ~120px（真机反馈「画面飘移」的实测根因）。fit 之后短暂接管，
        用户一动手（缩放/拖动）就交还控制。"""
        super().resizeEvent(event)
        if getattr(self, "_keep_center", False) and self.scene() is not None:
            rect = self.scene().itemsBoundingRect()
            if not rect.isNull() and not rect.isEmpty():
                self.centerOn(rect.center())

    def fit_content(self):
        """缩放到刚好装下全部节点（留边距），文字仍可读"""
        scene = self.scene()
        rect = scene.itemsBoundingRect()
        if rect.isNull() or rect.isEmpty():
            return
        # sceneRect 跟随内容放大：固定 1800 宽的旧值比缩放后的视口视野还窄时，
        # 视口会被 sceneRect 钳死无法滚动，centerOn 静默失效 → 内容偏在一边
        self.setSceneRect(rect.adjusted(-900, -700, 900, 700))
        self.fitInView(rect.adjusted(-70, -50, 70, 50), Qt.KeepAspectRatio)
        s = self.transform().m11()
        if s > 1.15:      # 内容很少时不要放太大（放大会跑到左上角）
            self.resetTransform()
        elif s < 0.72:    # 太小就看不清文字了，保证可读性（用户可拖动/缩放）
            f = 0.72 / s
            self.scale(f, f)
        self.centerOn(rect.center())
        self._keep_center = True    # 视口后续 resize（splitter 异步）时保持居中


# ---------------------------------------------------------------- 通用对话框
class DeviceDetailDialog(BaseDialog):
    """设备面板：信息 + 操作按钮（把运维动作聚合到一处）
    v3 起日常"看参数"由右侧联动面板承担，本对话框专注"选操作"。"""

    def __init__(self, title, subtitle, rows, buttons, parent=None):
        super().__init__(title, subtitle, parent, min_width=520)

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(9)
        for label, value in rows:
            k = QLabel(f"{label}")
            k.setStyleSheet("color: #5F6B7A; font-size: 13px;")
            v = QLabel(str(value) if value not in (None, "") else "—")
            v.setWordWrap(True)
            v.setTextInteractionFlags(Qt.TextSelectableByMouse)
            v.setStyleSheet("color: #1F2A37; font-size: 13px;")
            form.addRow(k, v)
        self.content_layout().addLayout(form)

        # 旧代码传 objectName（primaryButton…），统一翻译成语义档位
        role_map = {"primaryButton": "primary", "secondaryButton": "secondary",
                    "ghostButton": "ghost", "dangerButton": "danger"}
        for text, cb, obj in buttons:
            self.add_button(text, role_map.get(obj or "", "secondary"), cb)
        self.add_close_button()


class PortTableDialog(BaseDialog):
    """端口表：每个口的配置 + 下挂终端（定位"哪个口接了什么东西"）"""

    def __init__(self, rows, parent=None):
        super().__init__("端口一览", "按接口列出配置/链路状态/下挂终端"
                         "（running-config + MAC/ARP 表 + 端口链路状态，只读）",
                         parent, min_width=760, min_height=520, scrollable=True)

        table = QTableWidget(len(rows), 5)
        table.setHorizontalHeaderLabels(["接口", "状态", "描述", "VLAN", "下挂终端"])
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                item = QTableWidgetItem(str(val))
                if c == 1:
                    color = theme.t("success") if val == "up" else (
                        theme.t("danger") if val == "down" else theme.t("text_muted"))
                    item.setForeground(QBrush(QColor(color)))
                table.setItem(r, c, item)
        self.add_content(table, 1)
        self.add_close_button()


class PortConfigDialog(BaseDialog):
    """端口级配置生成器（Access/Trunk）——交换机最基础的操作。
    端口列表来自最近一次采集的真实接口（多选），按当前设备厂商语法生成命令；
    只生成不自动下发：命令送 Console「配置原文」框，由用户点「下发到设备」并确认后才写入设备
    （保持只读红线：写入永远走显式确认的下发闭环）。
    布局：左端口右表单底部预览——长文本/长列表左右并列，不上下堆叠压高度。
    v3：支持从拓扑端口格点击进入并预选该端口。"""

    def __init__(self, ports, vendor, parent=None, vlan_map=None, preselect=None):
        super().__init__(
            "端口配置（Access / Trunk）",
            f"多选左侧端口 → 按当前设备厂商（{vendor or 'huawei'}）语法生成命令；"
            "「送往下发」会填入 Console 页，点「下发到设备」确认后才写入设备",
            parent, min_width=880, min_height=560, scrollable=True)
        self._vendor = vendor or "huawei"
        self._lines = []          # [(cmd, 中文释义)]
        self._vlan_map = vlan_map or {}   # 端口名 → 当前 Access VLAN（采集读到的，预填用）

        lay = self.content_layout()
        lay.setSpacing(10)

        body = QHBoxLayout()
        body.setSpacing(14)

        # ---- 左：真实端口列表（多选；短行长列表适合窄栏） ----
        left = QVBoxLayout()
        left.setSpacing(6)
        left_lab = QLabel("端口（可多选 · 来自最近一次采集）")
        left_lab.setStyleSheet("font-weight: bold;")
        left.addWidget(left_lab)
        self.port_list = QListWidget()
        self.port_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.port_list.setAlternatingRowColors(True)
        self.port_list.setStyleSheet("QListWidget::item { padding: 6px 4px; }")
        for name, hint in ports:
            it = QListWidgetItem(name if not hint else f"{name}  ·  {hint}")
            it.setData(Qt.UserRole, name)
            it.setToolTip(hint)
            self.port_list.addItem(it)
        # 选中变化 → 自动预填当前 VLAN（能读到的信息不让人填）
        self.port_list.itemSelectionChanged.connect(self._prefill_vlan)
        left.addWidget(self.port_list, 1)
        sel_row = QHBoxLayout()
        sel_all = make_button("全选", "ghost")
        sel_all.clicked.connect(self.port_list.selectAll)
        sel_none = make_button("清空", "ghost")
        sel_none.clicked.connect(self.port_list.clearSelection)
        sel_row.addWidget(sel_all)
        sel_row.addWidget(sel_none)
        sel_row.addStretch()
        left.addLayout(sel_row)
        body.addLayout(left, 2)

        # ---- 右：配置表单 ----
        right = QVBoxLayout()
        right.setSpacing(10)
        form = QFormLayout()
        form.setSpacing(8)

        self.type_combo = QComboBox()
        self.type_combo.addItems(["Access（接入口）", "Trunk（干道口）"])
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        form.addRow("链路类型:", self.type_combo)

        self.access_vlan = QSpinBox()
        self.access_vlan.setRange(1, 4094)
        self.access_vlan.setValue(1)
        form.addRow("Access VLAN:", self.access_vlan)

        self.trunk_vlans = QLineEdit()
        self.trunk_vlans.setPlaceholderText("放行 VLAN，空格分隔，支持 to，例：1 5 999 to 1048")
        self.trunk_vlans.setEnabled(False)
        form.addRow("Trunk 放行:", self.trunk_vlans)

        self.desc_edit = QLineEdit()
        self.desc_edit.setPlaceholderText("可选，例：dT:打印机")
        form.addRow("接口描述:", self.desc_edit)

        self.shut_check = QCheckBox("同时关闭端口（生成的命令里带 shutdown）")
        form.addRow("", self.shut_check)

        right.addLayout(form)

        gen_btn = make_button("⚙ 生成命令", "primary")
        gen_btn.clicked.connect(self.generate)
        right.addWidget(gen_btn)

        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("生成的命令（带中文释义）显示在这里")
        right.addWidget(self.preview, 1)
        body.addLayout(right, 3)

        lay.addLayout(body, 1)

        # ---- 预选端口（从拓扑端口格点击进入） ----
        if preselect:
            sel = set(preselect)
            for i in range(self.port_list.count()):
                if self.port_list.item(i).data(Qt.UserRole) in sel:
                    self.port_list.item(i).setSelected(True)
            if self.port_list.selectedItems():
                self.port_list.scrollToItem(self.port_list.selectedItems()[0])

        # ---- 底部按钮行 ----
        self.copy_btn = self.add_button("📋 复制纯命令", "secondary",
                                        self.copy_commands, close_on_click=False)
        self.send_btn = self.add_button("⤴ 送往下发（Console 页）", "primary",
                                        self.send_to_deploy, close_on_click=False)
        self.add_close_button()

    def _on_type_changed(self, idx):
        self.access_vlan.setEnabled(idx == 0)
        self.trunk_vlans.setEnabled(idx != 0)

    def _prefill_vlan(self):
        """选中端口后自动预填 Access VLAN：所有选中端口的当前 VLAN 一致才预填，
        有任一读不到就不精（严禁猜测）；切换到 Trunk 时不干扰"""
        if self.type_combo.currentIndex() != 0:
            return
        vals = set()
        for it in self.port_list.selectedItems():
            v = self._vlan_map.get(it.data(Qt.UserRole))
            if v is None:
                return
            vals.add(v)
        if len(vals) == 1:
            self.access_vlan.setValue(vals.pop())

    def _plain(self):
        return "\n".join(cmd for cmd, _ in self._lines)

    def generate(self):
        ports = [it.data(Qt.UserRole) for it in self.port_list.selectedItems()]
        if not ports:
            warn_box(self, "端口配置", "请先在左侧选择端口（按住 Ctrl/Shift 可多选）")
            return
        mode = "access" if self.type_combo.currentIndex() == 0 else "trunk"
        desc = self.desc_edit.text().strip()
        lines = []
        for p in ports:
            if mode == "access":
                lines += e_port_access(self._vendor, p, str(self.access_vlan.value()))
            else:
                raw = self.trunk_vlans.text().strip()
                if not raw:
                    warn_box(self, "端口配置", "Trunk 需要填写放行 VLAN（如：1 5 999 to 1048）")
                    return
                vids = [str(v) for v in expand_vlan_body(raw)]
                lines += e_port_trunk(self._vendor, p, vids)
            if desc:
                lines.append((f" description {desc}", "接口描述（便于运维识别）"))
            if self.shut_check.isChecked():
                lines.append((" shutdown", "手工关闭端口"))
        self._lines = lines
        self.preview.setPlainText("\n".join(f"{c}   # {n}" for c, n in lines))

    def copy_commands(self):
        if not self._lines:
            warn_box(self, "端口配置", "请先点「生成命令」")
            return
        QApplication.clipboard().setText(self._plain())
        info_box(self, "端口配置", f"已复制 {len(self._lines)} 行纯命令（无注释），可直接粘贴")

    def send_to_deploy(self):
        """把生成的命令填入 Console 页「配置原文」框并跳转；真正的写入仍需用户点「下发到设备」确认"""
        if not self._lines:
            warn_box(self, "端口配置", "请先点「生成命令」")
            return
        page = self.parent()          # NetworkTopologyPage
        main = page.window() if page else None
        cv = getattr(main, "tabs", {}).get("console_viz") if main else None
        if cv is None:
            info_box(self, "端口配置", "未找到 Console 页（主窗口未就绪）")
            return
        if not question_box(
                self, "送往下发",
                f"将把 {len(self._lines)} 行命令填入 Console 页「配置原文」框（替换当前内容），\n"
                "随后请在该页点「下发到设备」并确认——是否继续？"):
            return
        cv.raw_view.setPlainText(self._plain())
        page._goto("Console 可视化")
        self.accept()


class AddDeviceDialog(BaseDialog):
    """[已退役] 手工添加设备旧弹窗——被右侧面板的内联表单取代（弹窗是对思维的打断）。
    保留常量供表单复用；类本体不再被调用。"""

    TYPES = ["交换机", "PC / 服务器", "路由器", "防火墙", "AP / 其他"]


# ---------------------------------------------------------------- 主页面
class NetworkTopologyPage(QWidget):
    """网络拓扑（可视化运维入口）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = {}          # 最近一次采集结果
        self._sw_node = None
        self._pc_node = None
        self._manual = []        # 手工添加的节点
        self.initUI()
        self.clear_config()
        # 画布是手绘的（不走 QSS 重映射），主题切换时整体重绘一次
        theme.on_change(self._refresh_theme)

    def _refresh_theme(self):
        scene = getattr(self, "scene", None)
        if scene is not None:
            scene.update()
        view = getattr(self, "view", None)
        if view is not None:
            view.viewport().update()
        # 图例色块跟主题走（富文本里埋的是当前主题色值，切后必须重生成）
        legend = getattr(self, "legend_label", None)
        if legend is not None:
            self._refresh_legend()

    # ---------------- UI ----------------
    def initUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        layout.addWidget(page_header(
            "网络拓扑", "LLDP 邻居自动成图，链路状态实时标注（采集只读，不下发配置）"))

        bar = QHBoxLayout()
        bar.setSpacing(8)
        bar.addStretch(1)

        # 按钮统一走 make_button：控件级样式不依赖窗口级 QSS 级联
        # （后者在 QStackedWidget 子树实测失灵，会让主按钮变白灰）
        collect_btn = make_button("🔌 一键采集", "primary",
                                  tip="在当前页直接通过 Console 线采集交换机信息")
        collect_btn.clicked.connect(self.collect_now)

        panel_btn = make_button("🖥 设备面板", "primary",
                                tip="把交换机画成端口面板：颜色看状态、点端口看参数，\n"
                                    "改参数实时出命令，一键应用（经确认后写入设备）")
        panel_btn.clicked.connect(self.show_device_panel)

        help_btn = make_button("为什么只有自己？", "ghost",
                               tip="说明拓扑的数据来源与发现不到设备的原因")
        help_btn.clicked.connect(self.show_why)

        add_btn = make_button("＋ 添加设备", "secondary")
        add_btn.clicked.connect(self.add_manual_node)

        ports_btn = make_button("端口一览", "secondary",
                                tip="查看每个接口的配置和下挂终端")
        ports_btn.clicked.connect(self.show_port_table)

        layout_btn = make_button("自动布局", "secondary")
        layout_btn.clicked.connect(self._do_auto_layout)

        fit_btn = make_button("适应窗口", "ghost")
        fit_btn.clicked.connect(lambda: self.view.fit_content())

        # 实时刷新开关（学 eNSP：端口灯定时跳动，不用反复手动采集）
        self.live_btn = make_button("实时: 关", "secondary",
                                    tip="每 30 秒自动重采一次端口链路状态（只读），端口灯实时跳动。\n"
                                        "需 Console 口空闲；采集/下发布会自动跳过冲突轮次")
        self.live_btn.setCheckable(True)
        self.live_btn.clicked.connect(self._toggle_live)
        self._live_timer = None     # QTimer（轮询调度）
        self._live_busy = False     # 本轮轮询中（防重入 + 串口冲突检测）

        for w in (collect_btn, panel_btn, help_btn, add_btn, ports_btn,
                  layout_btn, fit_btn, self.live_btn):
            bar.addWidget(w)
        layout.addLayout(bar)

        # ---- 画布（左） + 详情面板（右）：参数结合拓扑的联动核心 ----
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)

        canvas_group = QGroupBox("拓扑视图")
        canvas_lay = QVBoxLayout(canvas_group)
        canvas_lay.setContentsMargins(10, 26, 10, 10)
        self.scene = TopologyScene(self)
        self.view = TopologyView(self.scene)
        canvas_lay.addWidget(self.view)
        # 图例（色块富文本，主题切换时刷新）
        self.legend_label = QLabel()
        self.legend_label.setStyleSheet("font-size: 12px; color: #5F6B7A; background: transparent;")
        canvas_lay.addWidget(self.legend_label)
        self.splitter.addWidget(canvas_group)

        self.splitter.addWidget(self._build_detail_panel())
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        # 注意：setSizes 是按比例归一化，不是像素——原 [9000, 330] 实际只分给侧板 ~38px，
        # 再被最小尺寸提示垫到 ~110px（实测截图「未选择设备」被挤到折行）。
        # 用真实像素量级 + 侧板 setMinimumWidth(280) 兑现预期宽度
        self.splitter.setSizes([1000, 300])
        layout.addWidget(self.splitter, 1)

        self.status_label = QLabel("尚未连接交换机 —— 点「🔌 一键采集」开始")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #5A6B82; font-size: 13px; font-weight: bold;")
        layout.addWidget(self.status_label)

        self.hint_label = QLabel(
            "💡 单击节点 → 右侧看参数 ｜ 交换机端口格：hover 看状态，点击直接配置 ｜ 双击节点打开操作面板 ｜ 拖动/滚轮缩放/空白平移")
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet("color: #9AA7B8; font-size: 12px;")
        layout.addWidget(self.hint_label)

        self.scene.on_node_activated = self.open_device_panel
        self.scene.on_node_menu = self._show_node_menu
        self.scene.on_port_clicked = self._on_port_clicked
        self.scene.selectionChanged.connect(self._on_selection_changed)
        self._refresh_legend()

    def _refresh_legend(self):
        """图例：端口灯与连线颜色语义 + VLAN 色卡（画布上直接读图，不用猜）"""
        def dot(c):
            return (f"<span style='background:{c};color:{c}'>&nbsp;&nbsp;&nbsp;</span>")
        t = theme.t
        html = (f"端口格：{dot(t('success'))} UP　{dot(t('scroll_handle'))} DOWN　"
                f"{dot(t('accent'))} Trunk　{dot(t('danger'))} 已shutdown　"
                f"｜ 连线：{dot(t('success'))} UP链路　{dot(t('warning'))} 未识别链路"
                f"　{dot(t('accent'))} Console管理线（虚线）")
        # VLAN 色卡（采集后展示全网 VLAN 分布，与分组框/端口色条/徽章同色）
        vids = []
        for v in (self._data.get("parsed") or {}).get("vlans") or []:
            try:
                vids.append(int(v.get("id")))
            except (TypeError, ValueError):
                continue
        vids = sorted(set(vids))
        if vids:
            shown = vids[:10]
            cards = "　".join(f"{dot(theme.vlan_color(v))} {v}" for v in shown)
            more = f"　…等 {len(vids) - 10} 个" if len(vids) > 10 else ""
            html += f"　｜ VLAN：{cards}{more}"
        self.legend_label.setText(html)

    # ---------------- 右侧详情面板（单击联动，非模态） ----------------
    def _build_detail_panel(self):
        """侧边详情面板：选中节点的参数 + 常用操作，单击即联动（不用双击弹窗）"""
        panel = QWidget()
        panel.setMinimumWidth(280)   # 兑现侧板预期宽度：否则被画布挤到 ~110px，标题折行
        panel.setStyleSheet("""
            QWidget#detailPanel { background: #FFFFFF; border: 1px solid #DFE6F0;
                                  border-radius: 12px; }
        """)
        panel.setObjectName("detailPanel")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)

        self.detail_title = QLabel("未选择设备")
        self.detail_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #1F2A37;")
        self.detail_title.setWordWrap(True)
        lay.addWidget(self.detail_title)

        self.detail_kind = QLabel("单击拓扑中的节点，参数直接显示在这里")
        self.detail_kind.setStyleSheet("font-size: 12px; color: #5F6B7A;")
        self.detail_kind.setWordWrap(True)
        lay.addWidget(self.detail_kind)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.detail_body = QWidget()
        self.detail_body.setStyleSheet("background: transparent;")
        self._detail_form = QFormLayout(self.detail_body)
        self._detail_form.setContentsMargins(0, 8, 0, 8)
        self._detail_form.setHorizontalSpacing(14)
        self._detail_form.setVerticalSpacing(8)
        scroll.setWidget(self.detail_body)
        lay.addWidget(scroll, 1)

        self.detail_btn_col = QVBoxLayout()
        self.detail_btn_col.setSpacing(8)
        lay.addLayout(self.detail_btn_col)
        lay.addStretch()
        return panel

    def _clear_detail_body(self):
        """清空侧板动态区（表单行 + 按钮），供详情/添加表单两个模式共用"""
        while self._detail_form.count():
            item = self._detail_form.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        while self.detail_btn_col.count():
            item = self.detail_btn_col.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _on_selection_changed(self):
        nodes = [i for i in self.scene.selectedItems() if isinstance(i, DeviceNode)]
        self._show_detail(nodes[0] if len(nodes) == 1 else None)

    def _show_detail(self, node):
        """侧板填充：参数行 + 操作按钮（保持与设备面板同一套动作）"""
        # 清空旧内容
        self._clear_detail_body()

        if node is None:
            self.detail_title.setText("未选择设备")
            self.detail_kind.setText("单击拓扑中的节点，参数直接显示在这里")
            return

        self.detail_title.setText(node.device_name)
        kind_txt = {"switch": "交换机（本机采集）", "pc": "本机 PC",
                    "neighbor": "邻居设备", "host": "终端设备",
                    "unknown": "未识别设备（端口有链路，对端无 LLDP 信息）",
                    "placeholder": "交换机（未采集）"}.get(node.kind, "未知")
        self.detail_kind.setText(f"{kind_txt}" + (f" ｜ {node.subtitle}" if node.subtitle else ""))

        f_key = "color: #5F6B7A; font-size: 13px;"
        f_val = "color: #1F2A37; font-size: 13px;"
        for k, v in node.meta.items():
            if v in (None, ""):
                continue
            lab = QLabel(str(k))
            lab.setStyleSheet(f_key)
            val = QLabel(str(v))
            val.setWordWrap(True)
            val.setTextInteractionFlags(Qt.TextSelectableByMouse)
            val.setStyleSheet(f_val)
            self._detail_form.addRow(lab, val)

        # 操作按钮（与 open_device_panel 同一套动作，非模态版）
        rows, buttons = self._panel_actions(node)
        for text, cb, obj in buttons:
            role = {"primaryButton": "primary", "secondaryButton": "secondary",
                    "ghostButton": "ghost", "dangerButton": "danger"}.get(obj, "secondary")
            btn = make_button(text, role, self)
            btn.clicked.connect(lambda _=False, f=cb: f())
            self.detail_btn_col.addWidget(btn)
        if node.kind == "switch" and node._ports:
            tip = QLabel(f"端口格已画在节点上（{len(node._ports)} 口）：悬停看参数、点击端口进配置")
            tip.setStyleSheet("color: #9AA7B8; font-size: 12px;")
            tip.setWordWrap(True)
            self.detail_btn_col.addWidget(tip)

    # ---------------- 契约方法（主窗口切换品牌时会调用） ----------------
    def clear_config(self):
        """清空拓扑，回到空状态（不报错、不残留）"""
        self._data = {}
        self._sw_node = None
        self._pc_node = None
        self._manual = []
        self.scene.clear()
        self._build_empty_state()
        self._refresh_legend()

    def _build_empty_state(self):
        from modules.host_info import local_host
        host = local_host()
        ips = [i for i in host["ips"] if not i.startswith("169.254.")] or host["ips"]
        pc_ip = ips[0] if ips else "未获取"
        self._pc_node = DeviceNode(host["name"], "pc",
                                   meta={"IP": pc_ip,
                                         "角色": "运维终端（本机）"},
                                   subtitle="本机 PC",
                                   badges=[(f"IP {pc_ip}", "ip")] if pc_ip != "未获取" else [])
        self._sw_node = DeviceNode("交换机（未采集）", "placeholder",
                                   meta={"说明": "点右上角「一键采集」读取设备"},
                                   subtitle="等待连接")
        self.scene.addItem(self._pc_node)
        self.scene.addItem(self._sw_node)
        LinkItem(self._pc_node, self._sw_node, "Console 线", dashed=True)
        self._pc_node.setPos(-300, -10)
        self._sw_node.setPos(0, 0)
        self.status_label.setText("尚未连接交换机 —— 点「🔌 一键采集」开始")
        self.view.fit_content()

    # ---------------- 采集入口 ----------------
    def _do_auto_layout(self):
        """自动布局 = 重排列节点 + 视图适配到内容（用户预期：点完看到整齐居中的全图）"""
        self.scene.auto_layout()
        self.view.fit_content()

    def collect_now(self):
        """不离开本页直接采集：调用 Console 页的采集流程（复用同一套逻辑）"""
        main = self.window()
        tab_widget = getattr(main, "tab_widget", None)
        console = getattr(main, "tabs", {}).get("console_viz") if hasattr(main, "tabs") else None
        if tab_widget is None or console is None:
            info_box(self, "提示", "未找到 Console 采集页")
            return
        # 切到 Console 页，让用户看到进度与日志
        for i in range(tab_widget.count()):
            if tab_widget.tabText(i) == "Console 可视化":
                tab_widget.setCurrentIndex(i)
                break
        console.start_read()
        self.status_label.setText("正在采集…（进度见 Console 可视化页）")

    # ---------------- 端口状态实时刷新（学 eNSP：端口灯定时跳动） ----------------
    _LIVE_INTERVAL_MS = 30 * 1000    # 30s 一轮

    def _toggle_live(self, on):
        from gui.styles import ACCENT, BORDER
        if on:
            if not (self._data.get("port") or "").strip():
                # 没有过 Console 采集记录：无法确定串口，友好提示并弹回开关
                self.live_btn.setChecked(False)
                info_box(self, "提示", "还没有采集记录（不知道 Console 口是哪个）。\n"
                         "请先点「🔌 一键采集」完成一次采集，再开启实时刷新。")
                return
            from PyQt5.QtCore import QTimer
            self.live_timer = QTimer(self)
            self.live_timer.timeout.connect(self._live_tick)
            self.live_timer.start(2000)   # 开启后 2s 先来一轮（快速反馈）
            self.live_btn.setText("实时: 开")
            self._sys_live_note("实时刷新已开启（30s 一轮，只读；采集/下发期间自动让路）")
        else:
            if self.live_timer is not None:
                self.live_timer.stop()
                self.live_timer = None
            self.live_btn.setText("实时: 关")
            self._sys_live_note("实时刷新已关闭")

    def _sys_live_note(self, text):
        """实时刷新状态打到拓扑底部提示行（不打断主状态）"""
        self.hint_label.setText(f"⏱ {text}")

    def _live_tick(self):
        """一轮轮询：短会话只读重采链路状态 → 更新 _data['link_up'] → 重画端口灯。
        串口被占用（用户正在采集/下发/别的程序占用）时本轮静默跳过。"""
        if self._live_busy:
            return
        port = (self._data.get("port") or "").strip()
        vendor = self._data.get("vendor") or ""
        if not port:
            return
        # 厂商名→键（ConsoleReader 用 h3c/huawei 等键）
        cn2key = {"华为": "huawei", "H3C": "h3c", "锐捷": "ruijie", "迈普": "maipu", "思科": "cisco"}
        vkey = cn2key.get(vendor) or vendor or "h3c"
        self._live_busy = True

        class _LiveWorker(QThread):
            done = pyqtSignal(bool, dict)

            def run(self):
                from modules import console_reader as cr
                try:
                    with cr.ConsoleReader(port, 9600) as rd:
                        rd.vendor = vkey
                        link = rd.read_link_state()
                        self.done.emit(True, link)
                except Exception:
                    self.done.emit(False, {})

        def _on_live(ok, link):
            self._live_busy = False
            if not ok or not link:
                return   # 串口忙/解析为空：本轮跳过，下轮再试
            old = self._data.get("link_up") or {}
            changed = {k: v for k, v in link.items() if old.get(k) != v}
            self._data["link_up"] = link
            if changed:
                # 只重画端口面板（保留节点位置）；重画走 load 的局部刷新太重，
                # 直接更新交换机节点的端口状态灯
                sw = self._sw_node
                if sw is not None and getattr(sw, "_ports", None):
                    for p in sw._ports:
                        name = p["name"]
                        if name in link or name in old:
                            p["state"] = _port_state({"name": name}, link)
                    sw._compute_panel()
                    sw.update()
                ups = sum(1 for v in link.values() if v)
                self._sys_live_note(f"端口状态已刷新：UP {ups} 口"
                                    + (f"，变化 {len(changed)} 口" if changed else ""))
                self._refresh_legend()

        self._live_worker = _LiveWorker()
        self._live_worker.done.connect(_on_live)
        self._live_worker.start()

    # ---------------- 数据填充 ----------------
    def load_topology(self, local_name="", local_meta=None, neighbors=None,
                      end_hosts=None, parsed=None, raw_config="",
                      console_port="", vendor="", health=None, link_up=None):
        """Console/SSH 采集完成后调用，重绘整张拓扑"""
        neighbors = neighbors or []
        end_hosts = end_hosts or []
        local_meta = dict(local_meta or {})
        parsed = parsed or {}
        link_up = link_up or {}
        self._data = {
            "name": local_name, "meta": local_meta, "neighbors": neighbors,
            "hosts": end_hosts, "parsed": parsed, "raw": raw_config,
            "port": console_port, "vendor": vendor, "health": health,
            "link_up": link_up,
        }

        self.scene.clear()
        self._manual = []

        from modules.host_info import local_host, normalize_mac
        me = local_host()
        my_macs = {normalize_mac(m) for m in me["macs"]}

        # 本机 PC（始终存在）；IP 取首个非链路本地地址——右键 Ping 要直接可用
        pc_name = me["name"] or "本机 PC"
        pc_ips = [i for i in me["ips"] if not i.startswith("169.254.")] or me["ips"]
        self._pc_node = DeviceNode(pc_name, "pc",
                                   meta={"IP": (pc_ips[0] if pc_ips else "未获取"),
                                         "角色": "运维终端（本机）",
                                         "Console": console_port or "—"},
                                   subtitle="本机 PC",
                                   badges=[(f"IP {pc_ips[0]}", "ip")] if pc_ips else [])
        self.scene.addItem(self._pc_node)

        # 交换机：真实端口面板 + 参数徽章 + 健康度（v3 参数结合拓扑）
        meta = dict(local_meta)
        if console_port:
            meta["管理通道"] = f"Console {console_port}"
        n_if = len(parsed.get("interfaces") or [])
        sw_sub = f"{vendor} · {n_if} 个接口" if (vendor and n_if) else (vendor or "")
        ports = self._build_port_cells(parsed, link_up)
        sw_badges = []
        mgmt_ip = self._switch_mgmt_ip()
        if mgmt_ip:
            sw_badges.append((f"管理 IP {mgmt_ip}", "ip"))
        model = str(local_meta.get("型号") or "").strip()
        if model and len(model) <= 18:
            sw_badges.append((model, "vlan"))
        health_badge = None
        if health and isinstance(health.get("score"), (int, float)):
            health_badge = (int(health["score"]), health.get("level") or "")
        sw = DeviceNode(local_name or "交换机", "switch", meta=meta, subtitle=sw_sub,
                        ports=ports, badges=sw_badges, health=health_badge)
        self.scene.addItem(sw)
        self._sw_node = sw

        pc_link_label = f"Console {console_port}" if console_port else "Console 线"
        LinkItem(self._pc_node, sw, pc_link_label, state="console")

        # LLDP 邻居
        for nb in neighbors:
            name = nb.get("name") or nb.get("peer", "邻居设备")
            nb_badges = []
            if nb.get("peer_port"):
                nb_badges.append((f"对端 {nb.get('peer_port')}", "vlan"))
            node = DeviceNode(name, "neighbor",
                              meta={"对端端口": nb.get("peer_port", ""),
                                    "本地端口": nb.get("port", "")},
                              subtitle=f"经 {nb.get('port', '')}",
                              badges=nb_badges)
            self.scene.addItem(node)
            LinkItem(sw, node, nb.get("port", ""), state="up")

        # 终端（来自 MAC/ARP 表）——本机 MAC 的那个就是"本机 PC"
        port_hosts = {}
        for h in end_hosts:
            mac = normalize_mac(h.get("mac", ""))
            is_me = bool(mac) and mac in my_macs
            port = h.get("port", "")
            port_hosts.setdefault(port, []).append(h)
            if is_me:
                self._pc_node.subtitle = f"接入 {_short_port(port)}" if port else "本机 PC"
                self._pc_node.meta["接入端口"] = port
                self._pc_node.meta["MAC"] = h.get("mac_display", "")
                if h.get("ip"):
                    self._pc_node.meta["IP"] = h["ip"]
                self._pc_node._badges = [(f"IP {h['ip']}", "ip")] if h.get("ip") else []
                # 本机其实是这样连的：撤掉 Console 线，改画接入端口链路
                for item in list(self.scene.items()):
                    if isinstance(item, LinkItem) and item.a is self._pc_node:
                        self.scene.removeItem(item)
                        self._pc_node.links.clear()
                LinkItem(self._pc_node, sw, f"接入 {_short_port(port)}" if port else "直连",
                         state="up")
                self._pc_node.setToolTip(self._pc_node._tooltip())
                continue
            label = h.get("ip") or h.get("mac_display", "终端")
            h_badges = []
            if h.get("ip"):
                h_badges.append((f"IP {h['ip']}", "ip"))
            if h.get("vlan"):
                # VLAN 徽章用 VLAN 配色（与分组框/端口色条/图例同源，一眼归堆）
                h_badges.append((f"VLAN {h['vlan']}", f"vlan:{h['vlan']}"))
            node = DeviceNode(label, "host",
                              meta={"MAC": h.get("mac_display", ""),
                                    "IP": h.get("ip", "") or "未获取",
                                    "接入端口": port,
                                    "VLAN": h.get("vlan", "")},
                              subtitle=f"{_short_port(port)} · VLAN {h.get('vlan') or '-'}",
                              badges=h_badges)
            self.scene.addItem(node)
            LinkItem(sw, node, "", state="up")   # 节点下方已标端口，连线不再重复写

        # 有链路但没有任何发现数据的端口 → 「未识别设备」
        # 真实场景：对端交换机未启用 LLDP（思科等出厂默认关）或哑交换机；
        # 不标出来用户会以为软件坏了，标出来才是"看得见"的运维
        # 不标出来用户会以为软件坏了，标出来才是“看得见”的运维
        known = set()
        pc_port = self._pc_node.meta.get("接入端口", "")
        if pc_port:
            known.add(_norm_port(pc_port))
        for nb in neighbors:
            known.add(_norm_port(nb.get("port", "")))
        for h in end_hosts:
            known.add(_norm_port(h.get("port", "")))
        skip_kw = ("vlan", "null", "inloop", "reg", "mge", "m-gigabit", "mgigabit",
                   "loopback", "tunnel", "bridge-aggregation", "bagg")
        unknown_ports = [n for n, up in link_up.items()
                         if up and _norm_port(n) not in known
                         and not n.lower().startswith(skip_kw)]
        for i, port in enumerate(unknown_ports, 1):
            label = "未识别设备" if len(unknown_ports) == 1 else f"未识别设备 {i}"
            node = DeviceNode(label, "unknown",
                              meta={"接入端口": port,
                                    "说明": "端口有链路，但对端未响应 LLDP、也没有 MAC/ARP 数据"
                                            "（对端未启用 LLDP 或为非管理型交换机）"},
                              subtitle=f"{_short_port(port)} · 有链路")
            self.scene.addItem(node)
            LinkItem(sw, node, f"{_short_port(port)} · 有链路", state="unknown")

        # ---- VLAN 分组围栏（v3.1 参数可视化）：同 VLAN 终端围一个框 ----
        vlan_groups = {}
        for n in self.scene.nodes():
            if n.kind == "host":
                v = str(n.meta.get("VLAN", "") or "").strip()
                if v.isdigit():
                    vlan_groups.setdefault(v, []).append(n)
        for vid, members in vlan_groups.items():
            if len(members) >= 1:
                box = VlanGroupItem(vid, members)
                self.scene.addItem(box)
                for n in members:
                    n._vlan_boxes.append(box)

        self.scene.auto_layout()
        self.view.fit_content()
        self._update_status(sw, neighbors, end_hosts, unknown_ports)
        self._refresh_legend()

    # ---------------- 端口面板数据装配 ----------------
    def _build_port_cells(self, parsed, link_up):
        """采集接口 → 端口格列表（只画物理/聚合口，SVI/NULL/管理口不上面板）。
        v3.1：附 vlan 字段（Access VLAN 数字），端口格底部画 VLAN 色条"""
        cells = []
        for itf in parsed.get("interfaces") or []:
            name = itf["name"]
            if name.lower().startswith(("vlan", "vlanif", "null", "m-gigabit",
                                       "mgigabit", "loopback", "inloop", "tunnel")):
                continue
            state = _port_state(itf, link_up)
            vlan_val = str((itf.get("detail") or {}).get("VLAN", "") or "").strip()
            vlan_id = vlan_val if vlan_val.isdigit() else ""   # "trunk 1 to 10" 不画色条
            cells.append({
                "name": name,
                "state": state,
                "label": _port_label(name),
                "group": itf.get("kind") or "其他",
                "vlan": vlan_id,
                "tip": _port_tip(itf, state),
            })
        return cells

    def _on_port_clicked(self, node, port_name):
        """点击端口格 → 直接打开该口配置生成器（预选）"""
        self.show_port_config(preselect=[port_name])

    def _update_status(self, sw, neighbors, end_hosts, unknown_ports=None):
        parsed = self._data.get("parsed") or {}
        n_if = len(parsed.get("interfaces") or [])
        n_hosts = len(end_hosts)
        unknown_ports = unknown_ports or []
        parts = [f"交换机：{self._data.get('name') or '未命名'}"]
        if n_if:
            parts.append(f"接口 {n_if}")
        parts.append(f"LLDP 邻居 {len(neighbors)}")
        parts.append(f"发现终端 {n_hosts}")
        if unknown_ports:
            parts.append(f"未识别链路 {len(unknown_ports)} 个")
        if not neighbors:
            parts.append("（终端不会应答 LLDP，靠 MAC 表发现）")
        self.status_label.setText(" ｜ ".join(parts))

        if unknown_ports:
            ports_txt = "、".join(_short_port(p) for p in unknown_ports[:3])
            self.hint_label.setText(
                f"💡 {ports_txt} 有链路但对端未响应 LLDP——对端交换机可能没开 LLDP（思科等出厂默认关），"
                "在对端执行 lldp run / lldp global enable 后再采集即可看到它的型号与端口")
        elif n_hosts == 0:
            self.hint_label.setText(
                "💡 没有发现终端：设备端口上可能没接设备，或终端长期空闲导致 MAC 表项老化。"
                "换台在用的电脑接入后再采集即可看到它。")
        else:
            self.hint_label.setText(
                "💡 单击节点 → 右侧看参数 ｜ 交换机端口格：hover 看状态，点击直接配置 ｜ 双击节点打开操作面板 ｜ 拖动/滚轮缩放/空白平移")

    # ---------------- 交互：设备面板 ----------------
    def _panel_actions(self, node):
        """设备面板的动作集（弹窗版与侧板联动版共用同一份）"""
        rows, buttons = [], []
        kind = node.kind
        rows.append(("设备类型", {"switch": "交换机（本机采集）", "pc": "本机 PC",
                                  "neighbor": "邻居设备", "host": "终端设备",
                                  "unknown": "未识别设备（端口有链路，对端无 LLDP 信息）"}.get(kind, "未知")))
        for k, v in node.meta.items():
            if v not in (None, ""):
                rows.append((k, v))

        if kind in ("switch", "placeholder"):
            buttons = [
                ("端口面板（可视化配置）", self.show_device_panel, "primaryButton"),
                ("进入终端 CLI", self._goto_terminal, "secondaryButton"),
                ("端口配置（Access/Trunk）", self.show_port_config, "secondaryButton"),
                ("AI 诊断此设备", self._goto_ai_diagnosis, "secondaryButton"),
                ("查看完整配置", lambda: self._goto("Console 可视化"), "secondaryButton"),
                ("配置健康度", self._show_health, "secondaryButton"),
                ("端口一览", self.show_port_table, "secondaryButton"),
                ("备份配置", self._backup_config, "secondaryButton"),
            ]
            ip = self._switch_mgmt_ip()
            if ip:
                buttons.append((f"Ping {ip}", lambda: self._ping(ip, node.device_name), "ghostButton"))
        elif kind == "pc":
            buttons = [("Ping 本机", lambda: self._ping(_usable_ip(node.meta.get("IP", "")), node.device_name),
                        "secondaryButton"),
                       ("重新采集", self.collect_now, "primaryButton")]
        else:
            ip = _usable_ip(node.meta.get("IP", ""))
            if ip:
                buttons.append((f"Ping {ip}", lambda: self._ping(ip, node.device_name), "secondaryButton"))
            buttons.append(("复制信息", lambda: self._copy_node(node), "ghostButton"))
            buttons.append(("删除节点", lambda: self._remove_node(node), "ghostButton"))
        return rows, buttons

    def open_device_panel(self, node):
        rows, buttons = self._panel_actions(node)
        DeviceDetailDialog(node.device_name, node.subtitle, rows, buttons, self).exec_()
        # 面板是模态的：双击的收尾 release 会被模态事件循环吃掉，场景既认为按键仍按着、
        # 抓取者也残留——用户关掉面板后的下一击会被重定向到旧节点（拖错节点/再双击又
        # 弹旧面板，真机仪表实测：连点三个不同节点，后两次全部命中第一个节点）。
        # 不能用 ungrabMouse 硬摘（按键逻辑未结束时 Qt 会触发 regrab，在物理光标位置
        # 合成新 press，反而搅乱状态机）；正确做法是给场景补发那个丢失的 release，
        # 让 press→release 周期干净收尾。singleShot(0) 保证在 mouseDoubleClickEvent
        # 返回、抓取登记完成之后才执行。
        def _finish_dblclick(n=node):
            try:
                if self.scene.mouseGrabberItem() is n:
                    vp = self.view.viewport()
                    pos = QPointF(vp.width() / 2, vp.height() / 2)
                    QApplication.postEvent(vp, QMouseEvent(
                        QEvent.MouseButtonRelease, pos,
                        vp.mapToGlobal(pos.toPoint()),
                        Qt.LeftButton, Qt.NoButton, Qt.NoModifier))
            except RuntimeError:      # 节点/视图已被销毁
                pass
        QTimer.singleShot(0, _finish_dblclick)

    def _show_node_menu(self, node, screen_pos):
        menu = QMenu(self)
        menu.addAction("设备面板", lambda: self.open_device_panel(node))
        menu.addSeparator()
        if node.kind in ("switch", "placeholder"):
            menu.addAction("端口面板（可视化配置）", self.show_device_panel)
            menu.addAction("端口配置（Access/Trunk）", self.show_port_config)
            menu.addAction("查看完整配置", lambda: self._goto("Console 可视化"))
            menu.addAction("配置健康度体检", self._show_health)
            menu.addAction("端口一览", self.show_port_table)
            menu.addAction("备份配置到文件", self._backup_config)
            ip = self._switch_mgmt_ip()
            if ip:
                menu.addAction(f"Ping 管理地址 {ip}", lambda: self._ping(ip, node.device_name))
            menu.addSeparator()
            menu.addAction("重新采集", self.collect_now)
        elif node.kind == "pc":
            ip = _usable_ip(node.meta.get("IP", ""))
            if ip:
                menu.addAction(f"Ping {ip}", lambda: self._ping(ip, node.device_name))
            menu.addAction("重新采集", self.collect_now)
            menu.addAction("复制本机信息", lambda: self._copy_node(node))
        else:
            ip = _usable_ip(node.meta.get("IP", ""))
            if ip:
                menu.addAction(f"Ping {ip}", lambda: self._ping(ip, node.device_name))
            menu.addAction("复制设备信息", lambda: self._copy_node(node))
            menu.addAction("删除该节点", lambda: self._remove_node(node))
        menu.exec_(screen_pos)

    # ---------------- 动作 ----------------
    def _goto(self, title):
        main = self.window()
        tw = getattr(main, "tab_widget", None)
        if tw is None:
            return
        for i in range(tw.count()):
            if tw.tabText(i) == title:
                tw.setCurrentIndex(i)
                return

    def _goto_terminal(self):
        """联动（学 eNSP 双击设备进 CLI）：带 Console 口跳自由终端并预填，
        连接动作留给用户点（操作可见）；无串口记录时提示先采集"""
        port = (self._data.get("port") or "").strip()
        if not port:
            info_box(self, "提示", "还没有 Console 采集记录（不知道串口）。\n"
                     "请先点「🔌 一键采集」完成一次采集。")
            return
        main = self.window()
        term = getattr(main, "tabs", {}).get("terminal")
        if term is None:
            return
        if term.prefill_console(port, 9600,
                                note=f"[拓扑] 来自 {self._data.get('name') or '交换机'} 的 Console 口"):
            self._goto("自由终端")

    def _goto_ai_diagnosis(self):
        """联动：把采集到的设备运行配置带去「AI 运维」页诊断（一次性上下文，不重复抓取）"""
        main = self.window()
        ai = getattr(main, "tabs", {}).get("ai_ops")
        raw = (self._data or {}).get("raw") or ""
        if ai is None or not raw.strip():
            info_box(self, "提示", "请先点「🔌 一键采集」拿到设备运行配置，再使用 AI 诊断")
            return
        ai.start_external_diagnosis(
            self._data.get("name") or "交换机", raw, self._data.get("vendor") or "")

    def _switch_mgmt_ip(self):
        """管理 IP：优先配置里的 Vlan-interface IP"""
        for itf in (self._data.get("parsed") or {}).get("interfaces") or []:
            if itf["name"].lower().startswith(("vlan", "vlanif")):
                ip = (itf.get("detail") or {}).get("IP", "")
                if ip:
                    return ip.split()[0]
        return ""

    def _show_health(self):
        health = self._data.get("health")
        if not health:
            info_box(
                self, "配置健康度",
                "还没有体检数据。\n\n请先点「🔌 一键采集」读取交换机配置，"
                "系统会按等保/基线自动打分。")
            return
        rows = [("健康度评分", f"{health.get('score')} 分（{health.get('level')}）")]
        st = health.get("stats", {})
        rows.append(("统计", f"严重 {st.get('严重', 0)} · 警告 {st.get('警告', 0)} · "
                             f"提示 {st.get('提示', 0)} · 通过 {st.get('通过', 0)}"))
        for it in health.get("items", []):
            if it.get("level") in ("严重", "警告"):
                rows.append((it.get("level"), f"{it.get('domain')} · {it.get('item')}"))
        DeviceDetailDialog("配置健康度体检", "按等保与厂商基线对当前运行配置打分（只读分析）",
                           rows, [("查看完整配置", lambda: self._goto("Console 可视化"),
                                   "primaryButton")], self).exec_()

    def show_port_table(self):
        parsed = (self._data.get("parsed") or {})
        ifaces = parsed.get("interfaces") or []
        if not ifaces:
            info_box(self, "端口一览",
                     "还没有接口数据。\n\n请先点「🔌 一键采集」。")
            return
        # 端口 → 下挂终端
        by_port = {}
        for h in self._data.get("hosts") or []:
            by_port.setdefault(h.get("port", ""), []).append(h)

        # 真实链路状态（display interface brief，采集时一并抓取）——有实时值优先用实时值
        link_up = self._data.get("link_up") or {}
        live_map = {_norm_port(k): v for k, v in link_up.items()}

        def norm(p):
            return (p or "").lower().replace("gigabitethernet", "ge").replace(" ", "")

        rows = []
        for itf in ifaces:
            d = itf.get("detail") or {}
            live = live_map.get(_norm_port(itf["name"]))
            if live is True:
                status = "up"
            elif live is False:
                status = "down"
            else:
                status = "down" if d.get("状态") else ("up" if d.get("描述") or d.get("IP")
                                                       or d.get("VLAN") else "—")
            hosts = by_port.get(itf["name"], [])
            rows.append([
                itf["name"], status, d.get("描述", ""),
                d.get("VLAN", "") or d.get("IP", ""),
                "、".join((h.get("ip") or h.get("mac_display", "")) for h in hosts) or "—",
            ])
        # 端口名大小写/别名不一致时，补一遍宽松匹配
        for r, itf in zip(rows, ifaces):
            if r[4] == "—":
                for p, hs in by_port.items():
                    if norm(p) == norm(itf["name"]):
                        r[4] = "、".join((h.get("ip") or h.get("mac_display", "")) for h in hs)
                        break
        PortTableDialog(rows, self).exec_()

    def show_device_panel(self):
        """设备面板（大端口矩阵 + 参数卡 + 实时命令预览）——傻瓜式配置主入口。
        对标 eSight/IMC 设备面板视图；非模态 show()：可与拓扑同屏观察，
        面板选中端口会联动拓扑端口格高亮。"""
        parsed = (self._data.get("parsed") or {})
        if not (parsed.get("interfaces") or []):
            info_box(self, "设备面板",
                     "还没有接口数据。\n\n请先点「🔌 一键采集」，端口面板会自动画出来。")
            return
        from gui.dialogs.device_panel import DevicePanelDialog
        DevicePanelDialog(self).show()     # 非模态：parent=本页，Qt 对象树托管生命周期

    def show_port_config(self, preselect=None):
        """端口级配置（Access/Trunk）：交换机最基础的操作。
        用采集到的真实端口列表 + 当前厂商语法生成命令，经 Console 下发闭环写回设备。
        v3：拓扑端口格点击进入时 preselect 预选该口"""
        parsed = (self._data.get("parsed") or {})
        ifaces = parsed.get("interfaces") or []
        if not ifaces:
            info_box(
                self, "端口配置",
                "还没有接口数据。\n\n请先点「🔌 一键采集」，端口列表会自动带出。")
            return
        # 只列物理/聚合端口（SVI、NULL、管理口不参与 access/trunk 划分）
        skip = ("vlan", "vlanif", "null", "m-gigabit", "mgigabit", "loopback", "inloop")
        ports = []
        for itf in ifaces:
            name = itf["name"]
            if name.lower().startswith(skip):
                continue
            d = itf.get("detail") or {}
            bits = []
            if d.get("VLAN"):
                bits.append(f"VLAN {d['VLAN']}")
            if d.get("IP"):
                bits.append(d["IP"])
            if d.get("描述"):
                bits.append(d["描述"])
            ports.append((name, " · ".join(bits)))
        if not ports:
            info_box(self, "端口配置", "未解析出可配置的物理端口。")
            return
        # 端口当前 Access VLAN 映射（选中后自动预填，能读到的信息不让人填）
        vlan_map = {}
        for itf in ifaces:
            m = re.match(r"^(\d+)", str((itf.get("detail") or {}).get("VLAN", "")).strip())
            if m:
                vlan_map[itf["name"]] = int(m.group(1))
        # 注意：_data["vendor"] 存的是显示标签（如 "H3C"），发射器按小写厂商键匹配，
        # 必须小写化——否则语法分支全部落空、误走思科兑底
        vendor = (self._data.get("vendor") or "huawei").lower()
        PortConfigDialog(ports, vendor, self, vlan_map=vlan_map,
                         preselect=preselect).exec_()

    def _backup_config(self):
        raw = self._data.get("raw") or ""
        if not raw:
            info_box(self, "备份配置", "还没有采集到配置，请先「🔌 一键采集」。")
            return
        from PyQt5.QtWidgets import QFileDialog
        import time as _t
        name = (self._data.get("name") or "switch").replace(" ", "_")
        default = f"{name}_running_{_t.strftime('%Y%m%d_%H%M%S')}.cfg"
        path, _ = QFileDialog.getSaveFileName(self, "备份配置", default,
                                              "配置文件 (*.cfg);;文本 (*.txt);;所有文件 (*)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(raw)
            info_box(self, "备份完成", f"已保存到：\n{path}")
        except Exception as e:
            from gui.dialogs.base import error_box
            error_box(self, "备份失败", f"{type(e).__name__}: {e}")

    def _ping(self, ip, name="设备"):
        ip = _usable_ip(ip)
        if not ip:
            info_box(self, "Ping", "该设备没有可用的 IP 地址")
            return
        try:
            from gui.tools.ping_tool import PingTestWidget
        except Exception as e:
            warn_box(self, "Ping", f"Ping 工具不可用：{e}")
            return
        dlg = BaseDialog(f"Ping {name}", f"目标：{ip}（连通性验证，只读）",
                         self, min_width=780, min_height=560, scrollable=True)
        w = PingTestWidget()
        if hasattr(w, "host_input"):
            w.host_input.setText(ip)
        dlg.add_content(w, 1)
        dlg.add_close_button()
        dlg.exec_()

    def _copy_node(self, node):
        from PyQt5.QtWidgets import QApplication
        text = node.device_name + "\n" + "\n".join(
            f"{k}: {v}" for k, v in node.meta.items() if v)
        QApplication.clipboard().setText(text)
        self.status_label.setText(f"已复制「{node.device_name}」的信息到剪贴板")

    def _remove_node(self, node):
        if node is self._sw_node or node is self._pc_node:
            info_box(self, "提示", "交换机与本机节点是采集结果，不能删除")
            return
        for link in list(node.links):
            if link.scene() is not None:
                link.scene().removeItem(link)
            for other in (link.a, link.b):
                if link in getattr(other, "links", []):
                    other.links.remove(link)
        if node.scene() is not None:
            node.scene().removeItem(node)

    # ---------------- 手工添加（侧板内联表单，不弹窗打断） ----------------
    def add_manual_node(self):
        """「＋ 添加设备」入口：右侧面板就地切换为添加表单。
        弹窗是对思维的打断——内联表单就地填写、填完即回详情，全程不离开本页。"""
        self._show_add_form()

    def _show_add_form(self):
        """右侧详情区切换为「添加设备」内联表单（添加完成/取消后自动切回详情）"""
        self._add_err = ""
        self.detail_title.setText("添加设备")
        self.detail_kind.setText("没有 LLDP 时也能把真实网络画出来；填完点「添加」")
        self._clear_detail_body()

        f_key = "color: #5F6B7A; font-size: 13px;"
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("例如：办公区接入交换机 / 前台PC")
        self._type_combo = QComboBox()
        self._type_combo.addItems(AddDeviceDialog.TYPES)
        self._ip_edit = QLineEdit()
        self._ip_edit.setPlaceholderText("可选，用于 Ping / SSH")
        self._port_edit = QLineEdit()
        self._port_edit.setPlaceholderText("可选，例如 GE1/0/8")
        self._note_edit = QLineEdit()
        self._note_edit.setPlaceholderText("可选，备注")
        for label, w in (("名称", self._name_edit), ("类型", self._type_combo),
                         ("管理 IP", self._ip_edit), ("接入端口", self._port_edit),
                         ("备注", self._note_edit)):
            lab = QLabel(label)
            lab.setStyleSheet(f_key)
            self._detail_form.addRow(lab, w)
        # Enter 直接提交（表单节奏：填完回车，不用找按钮）
        for w in (self._name_edit, self._ip_edit, self._port_edit, self._note_edit):
            w.returnPressed.connect(self._submit_add_form)
        # 输入即清红边（校验状态不残留）
        self._name_edit.textChanged.connect(lambda: self._name_edit.setStyleSheet(""))

        add_btn = make_button("添加", "primary", self)
        add_btn.clicked.connect(self._submit_add_form)
        cancel_btn = make_button("取消", "ghost", self)
        cancel_btn.clicked.connect(lambda: self._show_detail(None))
        self.detail_btn_col.addWidget(add_btn)
        self.detail_btn_col.addWidget(cancel_btn)
        self._name_edit.setFocus()

    def _submit_add_form(self):
        name = self._name_edit.text().strip()
        if not name:
            # 非打断式校验：红边 + 说明文字（内联表单不用弹窗打断思维，
            # 与设备面板的字段红边同一套反馈语言）
            self._name_edit.setStyleSheet(
                "border: 2px solid #FA5151; border-radius: 9px;")
            self.detail_kind.setText("⚠ 名称必填——填一个便于识别的名字（如：办公区交换机）")
            self._name_edit.setFocus()
            return
        self._name_edit.setStyleSheet("")   # 清红边
        self.detail_kind.setText("没有 LLDP 时也能把真实网络画出来；填完点「添加」")
        dtype = self._type_combo.currentText()
        ip = self._ip_edit.text().strip()
        port = self._port_edit.text().strip()
        note = self._note_edit.text().strip()
        # 类型 → 节点形态：交换机画网管设备机身、PC/服务器画显示器、其余画终端盒
        kind = ("pc" if ("PC" in dtype or "服务器" in dtype)
                else "neighbor" if dtype == "交换机" else "host")
        meta = {"管理 IP": ip, "接入端口": port, "类型": dtype, "备注": note}
        node = DeviceNode(name, kind, meta=meta, subtitle=port or ip or dtype)
        if ip:
            node._badges = [(f"IP {ip}", "ip")]     # 与采集节点同语言
        self.scene.addItem(node)
        self._manual.append(node)
        anchor = self._sw_node or self._pc_node
        if anchor is not None:
            LinkItem(anchor, node, port)
        node.setPos(160, 200 + 110 * (len(self._manual) - 1))
        self.view.fit_content()
        self.status_label.setText(f"已添加「{name}」——右侧面板已切回该设备详情")
        # 添加完成就换回来：选中新节点，侧板自动联动显示它的参数
        node.setSelected(True)

    # ---------------- 说明 ----------------
    def show_why(self):
        DeviceDetailDialog(
            "为什么图上设备这么少？",
            "拓扑不是「扫描」出来的，而是从设备上「读」出来的——读不到的就画不出来。",
            [
                ("LLDP 邻居", "只能发现开启并运行 LLDP 的网管设备（交换机/路由器/AP）。"
                             "Windows 电脑、打印机、手机不应答 LLDP，所以永远不会以邻居身份出现。"),
                ("终端设备", "改用 MAC 地址表发现：只要终端在端口上发过帧，交换机就会学到它的 MAC，"
                            "本工具据此把它画成「终端」节点，并可用 ARP 表补上 IP。"),
                ("本机 PC", "始终会画出来（绿色），并用一条线连到交换机：如果你就是通过网线接在这台"
                           "交换机上，会自动标注真实接入端口；只有 Console 线时标注 Console。"),
                ("还是很少？", "端口空着 / 终端长时间空闲导致 MAC 表项老化 / 交换机之间没配 LLDP。"
                             "可以用「＋ 添加设备」把真实存在的设备先画上去。"),
            ],
            [("一键采集", self.collect_now, "primaryButton")], self).exec_()
