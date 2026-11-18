# -*- coding: utf-8 -*-
"""网络地址解析工具：BGP network 声明的 CIDR 规范化。

GUI 路由页签只提供一个「宣告网络」输入框（placeholder 192.168.0.0），
用户可能输入裸地址或 CIDR。各厂商 BGP 语法不接受 `3.3.3.0/24` 斜杠写法：
- VRP(华为)：`network <addr> <mask>`（掩码裸写，无 mask 关键字）
- IOS 系(思科/锐捷/迈普)：`network <addr> mask <mask>`

本模块把 CIDR 展开为 (addr, mask)；裸地址原样返回 mask=None，由生成器
决定是保持原样（合法 classful 写法）还是给出核对提示。
"""
import ipaddress
import re


def parse_timezone(value):
    """解析 `UTC+8` / `UTC-5` → (名称, 带符号小时, 是否合法)。

    - 名称取字母部分，小时取数字部分并带符号（UTC-5 → -5）。
    - 合法时区偏移范围 -12..14；越界标 valid=False，供生成器给出核对提示，
      避免 `clock timezone UTC 99` 这类设备必拒的命令。
    - 无法解析返回 (清洗后的原文, 0, False)，绝不抛异常。
    """
    s = str(value).strip() if value is not None else ""
    m = re.fullmatch(r"([A-Za-z]{1,5})([+-])(\d{1,2})", s)
    if m:
        name, sign, hours = m.group(1), m.group(2), int(m.group(3))
        signed = -hours if sign == "-" else hours
        return name, signed, -12 <= signed <= 14
    return (s.replace(" ", "_") or "UTC"), 0, False


def mask_valid(mask: str) -> bool:
    """点分子网掩码是否连续合法（255.255.255.0 合法，255.0.255.0 / 1.2.3.4 非法）。

    统一掩码合法性口径，供配置体检与配置生成共用，避免两处实现不一致。
    """
    try:
        parts = [int(x) for x in str(mask).strip().split(".")]
    except (ValueError, AttributeError):
        return False
    if len(parts) != 4 or any(p < 0 or p > 255 for p in parts):
        return False
    m = int.from_bytes(bytes(parts), "big")
    if m == 0:
        return False
    inv = (~m) & 0xFFFFFFFF
    return inv & (inv + 1) == 0  # 反码必须是低位连续 1


def mask_to_wildcard(mask: str):
    """点分掩码 → 反掩码（逐位取反）。非法/不连续掩码返回 None，不静默兜底。"""
    if not mask_valid(mask):
        return None
    parts = [int(x) for x in str(mask).strip().split(".")]
    return ".".join(str(255 - x) for x in parts)


def parse_network(value):
    """返回 (addr, mask)。

    - CIDR `3.3.3.0/24` → ("3.3.3.0", "255.255.255.0")
    - 裸地址 `192.168.0.0` → ("192.168.0.0", None)
    - 非法/空 → (原样 str, None)（不抛异常，交给生成器输出核对提示）
    """
    s = str(value).strip() if value is not None else ""
    if not s:
        return s, None
    if "/" in s:
        try:
            net = ipaddress.ip_network(s, strict=False)
            # IPv6 不能套用 IPv4 的「地址 + 点分掩码」模板：BGP 下 IPv6
            # 声明保留 CIDR 原样（network 2001:db8::/32），否则会生成
            # `network 2001:db8:: mask ffff:ffff::` 这类非法命令。
            if net.version == 6:
                return s, None
            return str(net.network_address), str(net.netmask)
        except ValueError:
            return s, None
    return s, None


def bgp_network_line(value, style="ios"):
    """生成单条 BGP network 声明行（不含前导空格）。

    style="vrp"  → `network <addr> <mask>`
    style="ios"  → `network <addr> mask <mask>`
    无有效掩码时输出原样 `network <value>`（classful 合法写法），
    并在斜杠非法但无法解析时附核对注释，避免静默生成非法命令。
    """
    addr, mask = parse_network(value)
    if mask:
        if style == "vrp":
            return f"network {addr} {mask}"
        return f"network {addr} mask {mask}"
    s = str(value).strip() if value is not None else ""
    if not s:
        return "network "
    if ":" in s:
        # IPv6：BGP 直接宣告 CIDR 原样，不做点分掩码展开
        return f"network {s}"
    if "/" in s:
        return f"! 注：BGP 宣告网络「{s}」掩码无法解析，请改用 a.b.c.d/前缀 格式核对后下发"
    return f"network {s}"
