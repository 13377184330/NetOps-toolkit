#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
应用数据根目录（打包分发适配）

开发态：项目根目录（与现状一致，utils/ 的上一级）。
冻结态（PyInstaller，sys.frozen）：exe 所在目录——onedir 分发的解压位置可写；
绝不能落在 sys._MEIPASS（一次运行的临时目录，且只读），否则设置/设备清单/
加密密钥每次启动丢失。

约定：设备清单、settings、secret.key、历史、审计、备份、自定义模板
全部挂在 app_root() 下的子目录，随 exe 文件夹一起搬走不丢数据。
"""

import os
import sys


def app_root() -> str:
    """可写数据根目录：frozen → exe 同目录；源码 → 项目根"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def meipass() -> str:
    """只读资源目录（打包内置资源；源码态返回空串）"""
    return getattr(sys, "_MEIPASS", "") or ""