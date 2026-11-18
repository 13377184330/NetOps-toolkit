#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
配置命令速查手册初始化
"""

from .huawei_manual import HUAWEI_COMMANDS, HUAWEI_CASES
from .h3c_manual import H3C_COMMANDS, H3C_CASES
# C-B1: 补齐包级导出——目录已存在 maipu/ruijie 手册，但 __init__ 仅导出华为/H3C，
# 导致 `from utils.manual import MAIPU_COMMANDS` / `import *` 失败，包 API 与目录不一致。
from .maipu_manual import MAIPU_COMMANDS, MAIPU_CASES
from .ruijie_manual import RUIJIE_COMMANDS, RUIJIE_CASES

__all__ = [
    "HUAWEI_COMMANDS",
    "HUAWEI_CASES",
    "H3C_COMMANDS",
    "H3C_CASES",
    "MAIPU_COMMANDS",
    "MAIPU_CASES",
    "RUIJIE_COMMANDS",
    "RUIJIE_CASES",
]
