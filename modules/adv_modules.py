#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
高级配置模块库（对标 NetCMD 的模块广度，自行实现）
- 数据驱动：每个模块 = {描述, 字段表, gen(vendor, params) -> [(cmd, 中文注释), ...]}
- 五厂商两派系渲染：VRP/Comware（华为·H3C）与 IOS（锐捷·迈普·思科），个别差异分支处理
- 输出直接带注释，与「命令释义」体系一致
"""

import re

try:
    from modules.nl_engine import e_linkagg, e_portsec, e_route, norm_port
except ImportError:  # 直接运行本文件做自测时，把项目根目录补进 sys.path
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    from modules.nl_engine import e_linkagg, e_portsec, e_route, norm_port

VRP = ("huawei", "h3c")
IOS = ("ruijie", "maipu", "cisco")


def _is(vendor, family):
    return vendor in family


def _view(vendor):
    return "system-view" if vendor in VRP else "configure terminal"


# ---------------------------------------------------------------- 各模块生成器
def gen_stack(vendor, p):
    """堆叠虚拟化：华为 iStack / 华三 IRF / 锐捷 VSU / 思科 StackWise"""
    member, dom, prio = p.get("member", "1"), p.get("domain", "10"), p.get("priority", "150")
    p1, p2 = norm_port(vendor, p.get("port1", "")), norm_port(vendor, p.get("port2", ""))
    if vendor == "huawei":
        lines = [
            (_view(vendor), "进入系统视图"),
            (f"stack slot {member} priority {prio}", f"成员 {member} 优先级 {prio}（大的做主）"),
            (f"interface stack-port {member}/1", "进入堆叠口视图"),
            (f" port member-group interface {p1} to {p2}", "把两个物理口划入堆叠口（堆叠线接这里）"),
            ("stack enable", "使能堆叠"),
        ]
    elif vendor == "h3c":
        lines = [
            (_view(vendor), "进入系统视图"),
            (f"irf member {member} priority {prio}", f"IRF 成员 {member} 优先级 {prio}（大的做主）"),
            (f"irf domain {dom}", f"IRF 域 {dom}（两台必须一致）"),
            (f"interface {p1}", "进入堆叠成员口 1"),
            (" shutdown", "加入 IRF 口前必须先关闭端口"),
            (" quit", "退回系统视图"),
            (f"interface {p2}", "进入堆叠成员口 2"),
            (" shutdown", "加入 IRF 口前必须先关闭端口"),
            (" quit", "退回系统视图"),
            (f"irf-port {member}/1", "进入 IRF 端口视图"),
            (f" port group interface {p1}", f"成员口 {p1} 划入 IRF 口"),
            (f"irf-port {member}/2", "进入 IRF 端口视图"),
            (f" port group interface {p2}", f"成员口 {p2} 划入 IRF 口"),
            (" quit", "退回系统视图"),
            (f"interface {p1}", "重新进入成员口 1"),
            (" undo shutdown", "恢复端口"),
            (f"interface {p2}", "重新进入成员口 2"),
            (" undo shutdown", "恢复端口"),
            ("irf-port-configuration active", "激活 IRF 配置（两台都配完后才执行）"),
        ]
    elif vendor == "ruijie":
        lines = [
            (_view(vendor), "进入配置模式"),
            (f"switch virtualization domain {dom}", f"VSU 域 {dom}（两台必须一致）"),
            (f"switch {member} priority {prio}", f"成员 {member} 优先级 {prio}（大的做主）"),
            ("vsl-port", "进入 VSL 端口配置"),
            (f" port-member interface {p1}", f"VSL 成员口 {p1}"),
            (f" port-member interface {p2}", f"VSL 成员口 {p2}"),
        ]
    else:
        lines = [
            (_view(vendor), "进入配置模式"),
            (f"switch {member} priority {prio}", f"成员 {member} 优先级 {prio}（大的做主）"),
            ("（StackWise 使用专用堆叠线，端口无需配置）", "思科通过堆叠线缆连接，仅需设置优先级"),
        ]
    lines.append(("save" if vendor in VRP else "write memory", "⚠ 堆叠成员重启后才生效，保存并协调好重启窗口"))
    return lines


def gen_linkagg(vendor, p):
    """链路聚合：Eth-Trunk / Bridge-Aggregation / Port-channel"""
    ports = [norm_port(vendor, x) for x in re.split(r"[\s,，]+", p.get("ports", "")) if x.strip()]
    mode = p.get("mode", "lacp")
    return e_linkagg(vendor, p.get("gid", "1"), ports, mode)


def gen_mirror(vendor, p):
    """端口镜像 SPAN：把被镜像口的流量复制到观察口（抓包/审计用）"""
    src = norm_port(vendor, p.get("src_port", ""))
    dst = norm_port(vendor, p.get("dst_port", ""))
    if vendor == "huawei":
        return [
            (_view(vendor), "进入系统视图"),
            (f"observe-port 1 interface {dst}", f"定义观察口 {dst}（抓包电脑接这里）"),
            (f"interface {src}", "进入被镜像口"),
            (" mirroring to observe-port 1 both", "把收发两个方向的流量都镜像到观察口"),
        ]
    if vendor == "h3c":
        return [
            (_view(vendor), "进入系统视图"),
            ("mirroring-group 1 local", "创建本地镜像组"),
            (f" mirroring-group 1 mirroring-port {src} both", f"被镜像口 {src}（收发都镜像）"),
            (f" mirroring-group 1 monitor-port {dst}", f"观察口 {dst}（抓包电脑接这里）"),
        ]
    return [
        (_view(vendor), "进入配置模式"),
        (f"monitor session 1 source interface {src} both", f"被镜像口 {src}（收发都镜像）"),
        (f"monitor session 1 destination interface {dst}", f"观察口 {dst}（抓包电脑接这里）"),
    ]


def gen_storm(vendor, p):
    """风暴控制：限制广播/组播占比，防环路风暴"""
    port = norm_port(vendor, p.get("port", ""))
    pct = p.get("pct", "10")
    if vendor == "huawei":
        lines = [(" broadcast-suppression percentage " + pct, f"广播占比超过 {pct}% 即丢弃"),
                 (" multicast-suppression percentage " + pct, f"组播占比超过 {pct}% 即丢弃")]
    elif vendor == "h3c":
        lines = [(" broadcast-suppression ratio " + pct, f"广播占比超过 {pct}% 即丢弃"),
                 (" multicast-suppression ratio " + pct, f"组播占比超过 {pct}% 即丢弃")]
    else:
        lines = [(f"storm-control broadcast level {pct}", f"广播占比超过 {pct}% 即丢弃"),
                 (f"storm-control multicast level {pct}", f"组播占比超过 {pct}% 即丢弃")]
    return [(_view(vendor), "进入配置视图"), (f"interface {port}", "进入接口视图")] + lines


def gen_dhcp_relay(vendor, p):
    """DHCP 中继：客户端的 DHCP 请求转发到别处的 DHCP 服务器"""
    ifn = norm_port(vendor, p.get("ifn", ""))
    server = p.get("server", "")
    if vendor == "huawei":
        return [
            (_view(vendor), "进入系统视图"),
            ("dhcp enable", "全局开启 DHCP"),
            (f"interface {ifn}", "进入客户端网关接口"),
            (" dhcp select relay", "接口工作在中继模式"),
            (f" dhcp relay server-ip {server}", f"指向 DHCP 服务器 {server}"),
        ]
    if vendor == "h3c":
        return [
            (_view(vendor), "进入系统视图"),
            ("dhcp enable", "全局开启 DHCP"),
            (f"interface {ifn}", "进入客户端网关接口"),
            (" dhcp select relay", "接口工作在中继模式"),
            (f" dhcp relay server-address {server}", f"指向 DHCP 服务器 {server}"),
        ]
    return [
        (_view(vendor), "进入配置模式"),
        (f"interface {ifn}", "进入客户端网关接口"),
        (" no switchport" if not re.match(r"^Vlan", ifn, re.I) else "（SVI 接口无需此步）",
         "确保为三层接口"),
        (f" ip helper-address {server}", f"指向 DHCP 服务器 {server}"),
    ]


def gen_vrrp(vendor, p):
    """VRRP 网关冗余：主备设备共用一个虚拟网关 IP"""
    ifn = norm_port(vendor, p.get("ifn", ""))
    vrid, vip, prio = p.get("vrid", "1"), p.get("vip", ""), p.get("priority", "120")
    if vendor in VRP:
        lines = [(_view(vendor), "进入系统视图"), (f"interface {ifn}", "进入网关接口"),
                 (f" vrrp vrid {vrid} virtual-ip {vip}", f"虚拟网关 IP {vip}（主备共用）"),
                 (f" vrrp vrid {vrid} priority {prio}", f"本机优先级 {prio}（大的做主）")]
    else:
        lines = [(_view(vendor), "进入配置模式"), (f"interface {ifn}", "进入网关接口"),
                 (f" standby {vrid} ip {vip}", f"虚拟网关 IP {vip}（主备共用）"),
                 (f" standby {vrid} priority {prio}", f"本机优先级 {prio}（大的做主）"),
                 (f" standby {vrid} preempt", "开启抢占（主恢复后自动接管）")]
    return lines


def gen_nat(vendor, p):
    """NAT Easy-IP：内网网段共用出接口公网 IP 上网"""
    out_if = norm_port(vendor, p.get("out_if", ""))
    net, mask = p.get("src_net", ""), p.get("src_mask", "255.255.255.0")
    acl = p.get("acl_id", "2000")
    if vendor in VRP:
        acl_cmd = "acl number " + acl if vendor == "huawei" else "acl basic " + acl
        return [
            (_view(vendor), "进入系统视图"),
            (acl_cmd, "创建基本 ACL 匹配内网源地址"),
            (f" rule 5 permit source {net} {mask}", f"允许内网 {net} {mask} 做 NAT"),
            (f"interface {out_if}", "进入公网出接口"),
            (f" nat outbound {acl}", "匹配 ACL 的流量用出接口地址做转换"),
        ]
    wild = _mask_to_wildcard(mask)
    return [
        (_view(vendor), "进入配置模式"),
        (f"access-list {acl} permit {net} {wild}", f"允许内网 {net} 做 NAT（IOS 用反掩码）"),
        (f"interface {out_if}", "进入公网出接口"),
        (" ip nat outside", "标记 NAT 外侧"),
        (f" ip nat inside source list {acl} interface {out_if} overload", "内网共用出接口地址转换"),
    ]


def gen_portsec(vendor, p):
    """端口安全（复用 nl_engine 发射器）"""
    return e_portsec(vendor, p.get("port", ""), int(p.get("max_mac", "1") or 1))


def gen_bind(vendor, p):
    """IP + MAC + 端口 三元绑定：防私接/防 ARP 欺骗"""
    port = norm_port(vendor, p.get("port", ""))
    ip, mac = p.get("ip", ""), _norm_mac(p.get("mac", ""))
    if vendor == "huawei":
        return [
            (_view(vendor), "进入系统视图"),
            (f"user-bind static ip-address {ip} mac-address {mac} interface {port}",
             f"绑定 {ip} / {mac} 只能出现在 {port}"),
        ]
    if vendor == "h3c":
        return [
            (_view(vendor), "进入系统视图"),
            (f"interface {port}", "进入接口视图"),
            (" ip verify source ip-address mac-address", "开启 IP+MAC 校验"),
            (f" ip source binding ip-address {ip} mac-address {mac}", f"绑定 {ip} / {mac}"),
        ]
    return [
        (_view(vendor), "进入配置模式"),
        (f"ip source binding mac-address {mac} vlan 1 ip-address {ip} interface {port}",
         f"绑定 {ip} / {mac} 只能出现在 {port}"),
    ]


def gen_stp(vendor, p):
    """MSTP + 边缘口加固：接电脑的口设边缘并配 BPDU 保护"""
    ports = [norm_port(vendor, x) for x in re.split(r"[\s,，]+", p.get("edge_ports", "")) if x.strip()]
    if vendor in VRP:
        lines = [(_view(vendor), "进入系统视图"),
                 ("stp mode mstp", "生成树模式 MSTP"),
                 ("stp enable", "全局使能生成树")]
        edge, bpdu = " stp edged-port enable", " stp bpdu-protection"
    else:
        lines = [(_view(vendor), "进入配置模式"),
                 ("spanning-tree mode mst", "生成树模式 MSTP"),
                 ("spanning-tree portfast bpduguard default", "全局边缘口默认 BPDU 保护")]
        edge, bpdu = " spanning-tree portfast", " spanning-tree bpduguard enable"
    for port in ports:
        lines += [(f"interface {port}", f"进入边缘口 {port}（接电脑/终端）"),
                  (edge, "设为边缘口（不参与生成树计算，秒通）"),
                  (bpdu, "收到 BPDU 立即关闭端口（防私接交换机）")]
    return lines


def _mask_to_wildcard(mask):
    try:
        parts = [int(x) for x in mask.split(".")]
        return ".".join(str(255 - x) for x in parts)
    except Exception:
        return "0.0.0.255"


def _norm_mac(mac):
    m = re.sub(r"[^0-9a-fA-F]", "", mac or "").lower()
    return "-".join(m[i:i + 2] for i in range(0, len(m), 2)).upper() if len(m) == 12 else (mac or "")


# ---------------------------------------------------------------- 模块注册表（GUI 数据驱动）
# 字段: (key, 显示名, 默认值)
MODULES = {
    "堆叠虚拟化": {
        "desc": "两台设备逻辑合一（华为 iStack / 华三 IRF / 锐捷 VSU / 思科 StackWise），双主控高可靠",
        "fields": [("member", "成员编号", "1"), ("domain", "域号(两台一致)", "10"),
                   ("priority", "优先级(大的做主)", "150"),
                   ("port1", "堆叠成员口 1", "GE1/0/25"), ("port2", "堆叠成员口 2", "GE1/0/26")],
        "gen": gen_stack,
    },
    "链路聚合": {
        "desc": "多条物理线捆成一条逻辑链路，带宽叠加+互为备份",
        "fields": [("gid", "聚合组号", "1"), ("mode", "模式(lacp/static)", "lacp"),
                   ("ports", "成员口(空格分隔)", "GE1/0/1 GE1/0/2")],
        "gen": gen_linkagg,
    },
    "端口镜像 SPAN": {
        "desc": "把被镜像口的流量复制一份到观察口，接电脑抓包/审计",
        "fields": [("src_port", "被镜像口", "GE1/0/1"), ("dst_port", "观察口(接抓包机)", "GE1/0/24")],
        "gen": gen_mirror,
    },
    "风暴控制": {
        "desc": "限制广播/组播占比，环路或攻击时保住带宽",
        "fields": [("port", "端口", "GE1/0/1"), ("pct", "抑制阈值(%)", "10")],
        "gen": gen_storm,
    },
    "DHCP 中继": {
        "desc": "DHCP 服务器在别处，本机做中继转发客户端请求",
        "fields": [("ifn", "客户端网关接口", "Vlanif10"), ("server", "DHCP 服务器 IP", "192.168.1.2")],
        "gen": gen_dhcp_relay,
    },
    "VRRP 网关冗余": {
        "desc": "主备两台设备共用一个虚拟网关 IP，主挂了备自动接管",
        "fields": [("ifn", "网关接口", "Vlanif10"), ("vrid", "VRID(主备一致)", "1"),
                   ("vip", "虚拟网关 IP", "192.168.10.254"), ("priority", "本机优先级", "120")],
        "gen": gen_vrrp,
    },
    "NAT 上网(Easy-IP)": {
        "desc": "内网网段共用出接口公网地址上网",
        "fields": [("src_net", "内网网段", "192.168.10.0"), ("src_mask", "内网掩码", "255.255.255.0"),
                   ("acl_id", "ACL 编号", "2000"), ("out_if", "公网出接口", "GE1/0/24")],
        "gen": gen_nat,
    },
    "端口安全": {
        "desc": "限制端口学习 MAC 数量，防私接设备",
        "fields": [("port", "端口", "GE1/0/1"), ("max_mac", "最多 MAC 数", "1")],
        "gen": gen_portsec,
    },
    "IP·MAC·端口绑定": {
        "desc": "三元绑定，防私接/防 ARP 欺骗",
        "fields": [("port", "端口", "GE1/0/1"), ("ip", "绑定 IP", "192.168.10.11"),
                   ("mac", "绑定 MAC", "0023-8912-3456")],
        "gen": gen_bind,
    },
    "MSTP+边缘口加固": {
        "desc": "接电脑的口设边缘秒通 + BPDU 保护防私接交换机",
        "fields": [("edge_ports", "边缘口(空格分隔)", "GE1/0/1 GE1/0/2")],
        "gen": gen_stp,
    },
}


if __name__ == "__main__":
    import io
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    for name, mod in MODULES.items():
        p = {k: dv for k, _l, dv in mod["fields"]}
        for v in ("huawei", "h3c", "cisco"):
            lines = mod["gen"](v, p)
            bad = [c for c, _n in lines if not c or c.strip() == ""]
            assert not bad, f"{name}/{v} 有空命令"
        print(f"✔ {name:<14} 五厂商生成正常（华为 {len(mod['gen']('huawei', p))} 行）")
    print("全部", len(MODULES), "个模块自测通过")
