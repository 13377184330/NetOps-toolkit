#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
运行配置可视化解析器：running-config 文本 → 结构化分层树
支持 H3C Comware / 华为 VRP（两者语法接近）/ 锐捷迈普思科（show running-config 风格）
纯解析、纯只读，输出 {分组: [条目]} 供 GUI 树展示
"""

import re


# ---------------------------------------------------------------- 主机信息
_INFO_PATTERNS = {
    "sysname": re.compile(r"^\s*sysname\s+(\S+)", re.M),
    "version": re.compile(r"^\s*version\s+([\d.]+[^\n]*)", re.M),
}


def parse_basic(text: str) -> dict:
    info = {}
    m = _INFO_PATTERNS["sysname"].search(text)
    if m:
        info["主机名"] = m.group(1)
    m = re.search(r"version\s+([\d.]+),?\s*(Release\s+\S+)?", text)
    if m:
        info["软件版本"] = (m.group(1) + (" " + m.group(2) if m.group(2) else "")).strip()
    if re.search(r"^\s*(?:irf|mad)\b", text, re.M):
        # 真堆叠标志：irf-port 成员绑定段（如 irf-port 1/1 + port group interface）或 MAD 配置。
        # 出厂单机也带 irf auto-update enable / irf member 1 priority 1 等默认行，不构成"启用"
        # （真机实测：交换机1 S5552S-EI-D 与交换机3 出厂配置均含默认行，旧逻辑一律误判"启用"）。
        enabled = (re.search(r"^\s*irf-port\s+\d+/\d+", text, re.M)
                   or re.search(r"^\s*mad\s+(?:bfd\s+)?enable", text, re.M))
        info["堆叠(IRF)"] = "启用" if enabled else "未启用"
    if re.search(r"^\s*stp global enable", text, re.M) or "stp enable" in text:
        info["STP"] = "启用"
    if re.search(r"^\s*lldp global enable", text, re.M) or "lldp enable" in text:
        info["LLDP"] = "启用"
    return info


# ---------------------------------------------------------------- 接口
# 华为/H3C: interface GigabitEthernet1/0/1 ... （# 结束）
_IFACE_RE = re.compile(r"^interface\s+(\S+)", re.M)

# 接口类型识别（用于图标/分组）
_IFACE_KIND = [
    (re.compile(r"^(GigabitEthernet|GE|Gi|Ethernet|Eth|E)", re.I), "GE 电口"),
    (re.compile(r"^(Ten-GigabitEthernet|XG|TenGig|Te)\b", re.I), "10GE 光口"),
    (re.compile(r"^(Forty|FGE)", re.I), "40GE"),
    (re.compile(r"^(Hundred|HGE)", re.I), "100GE"),
    (re.compile(r"^(Vlan-interface|Vlanif|Vl)", re.I), "VLAN 接口"),
    (re.compile(r"^NULL", re.I), "NULL"),
    (re.compile(r"^(Loopback|Lo)", re.I), "Loopback"),
]


def _iface_kind(name: str) -> str:
    for pat, label in _IFACE_KIND:
        if pat.search(name):
            return label
    return "其他"


def parse_interfaces(text: str) -> list[dict]:
    """解析接口配置块 → [{name, kind, lines, detail}]"""
    result = []
    blocks = re.split(r"\n#", "\n" + text)
    for block in blocks:
        m = re.match(r"\s*\n?interface\s+(\S+)", block)
        if not m:
            continue
        name = m.group(1)
        lines = [ln for ln in block.splitlines() if ln.strip() and not ln.strip().startswith("interface")]
        detail = {
            "描述": None,
            "模式": None,
            "VLAN": None,
            "IP": None,
        }
        for ln in lines:
            s = ln.strip()
            if s.startswith("description "):
                detail["描述"] = s[12:].strip()
            elif s in ("port link-mode bridge",):
                detail["模式"] = "二层桥接"
            elif s in ("port link-mode route",):
                detail["模式"] = "三层路由"
            elif s.startswith("port access vlan"):
                detail["VLAN"] = s.split()[-1]
            elif s.startswith("port trunk permit vlan"):
                detail["VLAN"] = "trunk " + s.split("vlan")[-1].strip()
            elif s.startswith("ip address"):
                detail["IP"] = " ".join(s.split()[2:4])
            elif s == "port link-type trunk":
                detail["模式"] = (detail["模式"] or "") + " trunk"
            elif s == "port link-type access":
                detail["模式"] = (detail["模式"] or "") + " access"
            elif s == "undo stp enable":
                detail["STP"] = "禁用"
            elif s == "shutdown":
                detail["状态"] = "administratively down"
        # 修复模式拼接
        if detail.get("模式"):
            detail["模式"] = detail["模式"].strip()
        detail = {k: v for k, v in detail.items() if v is not None}
        result.append({"name": name, "kind": _iface_kind(name), "lines": lines, "detail": detail})
    return result


# ---------------------------------------------------------------- VLAN
def parse_vlans(text: str) -> list[dict]:
    """解析 VLAN 块（vlan 10 / name xxx）"""
    result = []
    for m in re.finditer(r"^vlan\s+(\d+)([^\n]*)\n((?:\s{2,}\S[^\n]*\n?)*)", text, re.M):
        vid = m.group(1)
        rest = m.group(3) or ""
        name = ""
        nm = re.search(r"name\s+(\S+)", rest)
        if nm:
            name = nm.group(1)
        result.append({"id": vid, "name": name or f"VLAN{vid}"})
    return result


# ---------------------------------------------------------------- 路由
def parse_routes(text: str) -> list[dict]:
    """静态路由"""
    result = []
    for m in re.finditer(r"^\s*ip route-static\s+(\S+)\s+(\S+)\s+(\S+)", text, re.M):
        result.append({"目的网段": f"{m.group(1)}/{m.group(2)}", "下一跳": m.group(3)})
    for m in re.finditer(r"^\s*ip route\s+(\S+)\s+(\S+)\s+(\S+)", text, re.M):
        result.append({"目的网段": f"{m.group(1)}/{m.group(2)}", "下一跳": m.group(3)})
    return result


# ---------------------------------------------------------------- 安全相关
def parse_security(text: str) -> list[str]:
    """摘要安全相关配置"""
    items = []
    if re.search(r"^\s*ssh server enable", text, re.M):
        items.append("SSH 服务：启用")
    else:
        items.append("SSH 服务：未启用")
    if re.search(r"^\s*telnet server enable", text, re.M):
        items.append("Telnet 服务：启用 ⚠")
    if "password-recovery enable" in text:
        items.append("密码恢复：启用")
    # 用户/角色
    users = re.findall(r"^\s*local-user\s+(\S+)", text, re.M)
    if users:
        items.append("本地用户：" + ", ".join(users))
    # line 视图角色
    roles = re.findall(r"^\s*user-role\s+(\S+)", text, re.M)
    if roles:
        from collections import Counter
        cnt = Counter(roles)
        items.append("线路角色：" + ", ".join(f"{r}×{c}" for r, c in cnt.items()))
    # ACL
    acls = re.findall(r"^\s*acl (?:number )?(\d+)", text, re.M)
    if acls:
        items.append(f"ACL 数量：{len(acls)}")
    return items


# ---------------------------------------------------------------- VLAN 声明展开
def expand_vlan_body(body: str) -> list:
    """VLAN 声明体展开：'10 20'→[10,20]；'10 to 20'→[10..20]；'2 to 4094'→[2..4094]
    （真机实测教训：H3C/华为都支持范围写法，漏解析会把合法引用误判成"VLAN 未创建"）"""
    toks = (body or "").split()
    out = []
    i = 0
    while i < len(toks):
        if (i + 2 < len(toks) and toks[i + 1].lower() == "to"
                and toks[i].isdigit() and toks[i + 2].isdigit()):
            out.extend(range(int(toks[i]), int(toks[i + 2]) + 1))
            i += 3
            continue
        if toks[i].isdigit():
            out.append(int(toks[i]))
        i += 1
    return out


# ---------------------------------------------------------------- LLDP 邻居（拓扑）
def parse_lldp(text: str) -> list[dict]:
    """解析 LLDP 邻居信息（H3C verbose / 华为 brief / Cisco show lldp neighbors 通用宽松解析）
    返回 [{port: 本地端口, name: 邻居设备名, peer_port: 对端端口}]
    """
    neighbors = []
    if not text:
        return neighbors
    # H3C verbose: "LLDP neighbor-information of port 1[GigabitEthernet1/0/1]:" 后跟 System name / Port ID
    blocks = re.split(r"LLDP neighbor-information of port\s+\d+\s*\[([^\]]+)\]", text)
    if len(blocks) > 1:
        # blocks: [前导, port1, body1, port2, body2, ...]
        for i in range(1, len(blocks) - 1, 2):
            port = blocks[i].strip()
            body = blocks[i + 1]
            name_m = re.search(r"System name\s*:\s*(\S+)", body)
            peer_m = re.search(r"Port ID\s*:\s*(\S+)", body) or re.search(r"Port ID\s*:\s*(.+)$", body, re.M)
            if name_m:
                neighbors.append({
                    "port": port,
                    "name": name_m.group(1),
                    "peer_port": peer_m.group(1).strip() if peer_m else "",
                })
        return neighbors

    # Cisco / Ruijie 表格风格: "Gi1/0/1    Core-SW    Gi0/1    120"
    for m in re.finditer(r"^(\S(?:i|e|G|T|F)[\w/.:\-]+)\s{2,}(\S+)\s{2,}([\w/.:\-]+)\s{2,}\d+", text, re.M):
        neighbors.append({"port": m.group(1), "name": m.group(2), "peer_port": m.group(3)})
    if neighbors:
        return neighbors

    # 华为 brief: "Local Intf  Neighbor Dev  Neighbor Intf"
    for m in re.finditer(r"^(\S+)\s+(\S+)\s+(\S+)\s*$", text, re.M):
        a, b, c = m.group(1), m.group(2), m.group(3)
        if re.search(r"(GE|GigabitEthernet|Eth|XGE)", a, re.I):
            neighbors.append({"port": a, "name": b, "peer_port": c})
    return neighbors


# ---------------------------------------------------------------- MAC / ARP（终端发现）
# 说明：LLDP 只能发现"支持且开启了 LLDP"的设备（网管型交换机、路由器），
# 而 Windows/手机等终端从不应答 LLDP。要看见接在端口上的 PC，必须查 MAC 地址表。
_MAC_RE = re.compile(
    r"\b([0-9a-fA-F]{4}[-:][0-9a-fA-F]{4}[-:][0-9a-fA-F]{4}"      # 0023-8912-3456 / 0023:8912:3456
    r"|[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}"             # 0023.8912.3456（思科）
    r"|[0-9a-fA-F]{2}(?:[:-][0-9a-fA-F]{2}){5})\b"                  # 00:23:89:12:34:56
)

# 端口名：GigabitEthernet1/0/5、GE1/0/5、Gi1/0/5、Eth0/1、BAGG1、1/0/5 ……
# 注意：长名必须排在短名前（否则 GigabitEthernet 会被 Gi 截断），且必须以数字结尾
_PORT_RE = re.compile(
    r"\b((?:GigabitEthernet|Ten-GigabitEthernet|FortyGigE|FastEthernet|Ethernet"
    r"|Bridge-Aggregation|Port-channel|Vlan-interface|Vlanif"
    r"|XGE|BAGG|GE|Gi|Eth|Fa|Te|Po)[\d/.:]*\d"
    r"|\d+/\d+/\d+)\b",
    re.I,
)

_VIRTUAL_PORTS = ("cpu", "null", "vlan", "register", "route")  # 非物理口，拓扑不画


def _norm_mac(value: str) -> str:
    d = re.sub(r"[^0-9a-fA-F]", "", value or "").lower()
    return d if len(d) == 12 else ""


def _pick_vlan(text: str) -> str:
    for m in re.finditer(r"\b(\d{1,4})\b", text):
        v = int(m.group(1))
        if 1 <= v <= 4094:
            return str(v)
    return ""


def parse_mac_table(text: str) -> list[dict]:
    """解析 MAC 地址表 → [{mac, mac_display, port, vlan}]
    兼容 H3C「display mac-address」、华为「display mac-address」、
    思科/锐捷「show mac address-table」
    """
    rows = []
    if not text:
        return rows
    seen = set()
    for line in text.splitlines():
        m = _MAC_RE.search(line)
        if not m:
            continue
        mac = _norm_mac(m.group(1))
        if not mac or mac in ("000000000000", "ffffffffffff"):
            continue
        after = line[m.end():]
        pm = _PORT_RE.search(after)
        if not pm:
            continue
        port = pm.group(1)
        if any(port.lower().startswith(v) for v in _VIRTUAL_PORTS):
            continue
        # VLAN：端口列之前找；思科格式 VLAN 在 MAC 之前
        vlan = _pick_vlan(after[:pm.start()]) or _pick_vlan(line[:m.start()])
        key = (mac, port, vlan)
        if key in seen:
            continue
        seen.add(key)
        rows.append({"mac": mac, "mac_display": _mac_display(mac),
                     "port": port, "vlan": vlan})
    return rows


def _mac_display(norm: str) -> str:
    return "-".join(norm[i:i + 2] for i in range(0, 12, 2)).upper()


def parse_arp(text: str) -> list[dict]:
    """解析 ARP 表 → [{ip, mac}]（给终端补 IP，便于 Ping / 定位）"""
    rows = []
    if not text:
        return rows
    for line in text.splitlines():
        im = re.match(r"\s*(\d{1,3}(?:\.\d{1,3}){3})\s", line)
        if not im:
            continue
        mm = _MAC_RE.search(line)
        if not mm:
            continue
        mac = _norm_mac(mm.group(1))
        if not mac or mac in ("000000000000", "ffffffffffff"):
            continue
        rows.append({"ip": im.group(1), "mac": mac})
    return rows


def merge_end_hosts(mac_rows: list[dict], arp_rows: list[dict], live_ports=None) -> list[dict]:
    """MAC 表 + ARP 表 → 终端清单 [{mac, mac_display, ip, port, vlan}]
    live_ports（可选）：链路 UP 的端口名集合。同一 MAC 出现在多个端口时
    （真机实测：终端换口后旧口条目残留且端口已 DOWN），优先保留链路 UP 的那条，
    避免把已下线的旧端口当成终端当前位置——这不该让人手工矗别。
    未提供时保持全量（向后兼容）。"""
    ip_map = {r["mac"]: r["ip"] for r in (arp_rows or [])}
    rows = list(mac_rows or [])
    if live_ports is not None:
        def _np(p):
            return (p or "").strip().lower().replace(" ", "")
        live_norm = {_np(p) for p in live_ports}
        best = {}          # mac -> (是否链路UP, 行)
        for r in rows:
            mac = r["mac"]
            live = _np(r.get("port", "")) in live_norm
            cur = best.get(mac)
            if cur is None or (live and not cur[0]):
                best[mac] = (live, r)
        rows = [v[1] for v in best.values()]
    hosts = []
    for r in rows:
        hosts.append({
            "mac": r["mac"],
            "mac_display": r.get("mac_display") or _mac_display(r["mac"]),
            "ip": ip_map.get(r["mac"], ""),
            "port": r.get("port", ""),
            "vlan": r.get("vlan", ""),
        })
    return hosts


# ---------------------------------------------------------------- 汇总
def parse_config(text: str) -> dict:
    """主入口：配置文本 → 可视化数据结构"""
    return {
        "basic": parse_basic(text),
        "interfaces": parse_interfaces(text),
        "vlans": parse_vlans(text),
        "routes": parse_routes(text),
        "security": parse_security(text),
        "raw": text,
        "stats": {
            "接口数": len(parse_interfaces(text)),
            "VLAN 数": len(parse_vlans(text)),
            "静态路由数": len(parse_routes(text)),
        },
    }


# ---------------------------------------------------------------- 自测
if __name__ == "__main__":
    demo = """
#
 version 7.1.070, Release 6321P01
#
 sysname H3a
#
vlan 1
#
vlan 10
 name Office
#
interface NULL0
#
interface GigabitEthernet1/0/1
 port link-mode bridge
 description Uplink-to-Core
 port access vlan 10
#
interface GigabitEthernet1/0/24
 port link-mode bridge
#
interface Vlan-interface10
 ip address 192.168.10.1 255.255.255.0
#
ip route-static 0.0.0.0 0.0.0.0 192.168.10.254
#
telnet server enable
#
local-user admin
#
return
"""
    r = parse_config(demo)
    import json
    print(json.dumps(r, ensure_ascii=False, indent=2)[:1800])
