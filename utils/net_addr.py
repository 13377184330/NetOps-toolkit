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
