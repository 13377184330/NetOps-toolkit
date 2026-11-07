#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
UI 小图标（二开新增）

背景：QSS 里用 `border-left/right/top` 拼三角形是 Web 技巧，Qt 5 的样式引擎
不支持——`QComboBox::down-arrow { image: none; border-...: solid }` 会被画成一个
实心矩形（下拉框箭头变成一条灰竖条，实测全窗口所有下拉框都中招）。复选框同理，
`:checked` 只设背景不设图形时，勾选态就是一个纯蓝方块，看不出"已勾选"。

做法：不引入二进制资源文件，启动时用 QPainter 现画 PNG 到系统临时目录，QSS 用
绝对路径引用。无网络、无额外依赖；写不进去（只读盘/权限）时返回空串，样式自动
退化成不带图标的版本，不抛异常。

浅色 / 深色主题各生成一套（箭头灰度不同），QSS 里固定引用 light/ 版本，
主题引擎（gui/theme.py）在深色下把路径里的 /light/ 换成 /dark/。
"""

import os
import tempfile

from PyQt5.QtCore import Qt, QPointF
from PyQt5.QtGui import QImage, QPainter, QColor, QPainterPath, QPen

ASSET_VERSION = "v3"
_CACHE_ROOT = os.path.join(tempfile.gettempdir(), "netops_ui_assets_" + ASSET_VERSION)

CHEVRON_LIGHT = "#7A8699"
CHEVRON_DARK = "#9AA7B8"


def _paint_chevron(color, up=False):
    """画一个 24x16 的箭头（显示时缩到 12x8），圆头线条，缩放不糊"""
    def draw(p, w, h):
        if up:
            path = QPainterPath(QPointF(5, h - 6))
            path.lineTo(w / 2.0, 6)
            path.lineTo(w - 5, h - 6)
        else:
            path = QPainterPath(QPointF(5, 6))
            path.lineTo(w / 2.0, h - 6)
            path.lineTo(w - 5, 6)
        pen = QPen(QColor(color), 2.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
    return draw


def _paint_check(color):
    """画一个 28x28 的对勾（显示时缩到 14x14）"""
    def draw(p, w, h):
        path = QPainterPath(QPointF(6, 15))
        path.lineTo(12, 21)
        path.lineTo(22, 8)
        pen = QPen(QColor(color), 3.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
    return draw


def _spec(theme_name):
    """某主题需要的图标 {文件名: (宽, 高, 绘制函数)}"""
    chevron = CHEVRON_DARK if theme_name == "dark" else CHEVRON_LIGHT
    return {
        "chevron_down": (24, 16, _paint_chevron(chevron, up=False)),
        "chevron_up": (24, 16, _paint_chevron(chevron, up=True)),
        "check_white": (28, 28, _paint_check("#FFFFFF")),
    }


def _ensure(theme_name, name):
    """确保图标文件存在，返回正斜杠绝对路径；失败返回空串"""
    w, h, draw = _spec(theme_name)[name]
    path = os.path.join(_CACHE_ROOT, theme_name, name + ".png")
    try:
        if not (os.path.exists(path) and os.path.getsize(path) > 0):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            img = QImage(w, h, QImage.Format_ARGB32)
            img.fill(Qt.transparent)
            p = QPainter(img)
            p.setRenderHint(QPainter.Antialiasing, True)
            draw(p, w, h)
            p.end()
            if not img.save(path, "PNG"):
                return ""
        return path.replace("\\", "/")
    except Exception:
        return ""


def qss_url(name, theme_name="light"):
    """给 QSS 用的 url(...) 片段；取不到图标时返回空串，调用方需自行降级"""
    path = _ensure(theme_name, name)
    return 'url("%s")' % path if path else ""


# 启动即生成浅色版，供 gui/styles.py 在模块级拼 QSS 使用；
# 深色版由主题引擎在切到深色时按需生成（remap 只换路径）。
URL_CHEVRON_DOWN = qss_url("chevron_down", "light")
URL_CHEVRON_UP = qss_url("chevron_up", "light")
URL_CHECK_WHITE = qss_url("check_white", "light")

if URL_CHEVRON_DOWN:
    # 预生成深色版，避免切换主题那一刻才去写盘
    for _n in ("chevron_down", "chevron_up", "check_white"):
        _ensure("dark", _n)
