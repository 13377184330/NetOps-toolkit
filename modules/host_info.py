#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
本机信息采集（拓扑中「本机 PC」节点用）
- 主机名 / IPv4 / 网卡 MAC
- 不发任何网络探测报文：UDP connect 只取路由出口地址，不实际发包
- 优先 psutil（若安装），否则用 Windows 自带 getmac，最后 uuid.getnode() 兜底
"""

import re
import socket
import subprocess
import sys
import uuid


def normalize_mac(value: str) -> str:
    """任意写法 MAC → 12 位小写十六进制（001122334455）"""
    digits = re.sub(r"[^0-9a-fA-F]", "", value or "").lower()
    return digits if len(digits) == 12 else ""


def format_mac(norm: str) -> str:
    """12 位 hex → XX-XX-XX-XX-XX-XX（H3C 展示风格）"""
    n = normalize_mac(norm)
    if not n:
        return norm or ""
    return "-".join(n[i:i + 2] for i in range(0, 12, 2)).upper()


def local_macs() -> set:
    """本机所有网卡 MAC（小写 12 位 hex 集合）"""
    macs = set()
    # 1) psutil（若已安装，最准确）
    try:
        import psutil  # type: ignore
        for _name, addrs in psutil.net_if_addrs().items():
            for a in addrs:
                if getattr(a, "family", None) == getattr(psutil, "AF_LINK", object()):
                    m = normalize_mac(a.address)
                    if m and m != "000000000000":
                        macs.add(m)
    except Exception:
        pass

    # 2) Windows 自带 getmac（零依赖）
    if sys.platform == "win32":
        try:
            out = subprocess.run(
                ["getmac", "/fo", "csv", "/nh"],
                capture_output=True, text=True, timeout=8,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ).stdout
            for m in re.findall(r"([0-9A-Fa-f]{2}(?:-[0-9A-Fa-f]{2}){5})", out):
                n = normalize_mac(m)
                if n and n != "000000000000":
                    macs.add(n)
        except Exception:
            pass

    # 3) 兜底
    try:
        macs.add(f"{uuid.getnode():012x}")
    except Exception:
        pass
    return macs


def local_ips() -> list:
    """本机 IPv4 地址（不含回环）"""
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.3)
        s.connect(("223.5.5.5", 53))   # 只取默认出口地址，不真正发包
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except Exception:
        pass
    return sorted(i for i in ips if i and not i.startswith("127."))


def local_host() -> dict:
    return {"name": socket.gethostname(), "ips": local_ips(), "macs": local_macs()}


if __name__ == "__main__":
    import json
    print(json.dumps(local_host(), ensure_ascii=False, indent=2))
