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
    if "irf" in text:
        info["堆叠(IRF)"] = "启用" if re.search(r"^\s*irf\s+auto-update enable", text, re.M) else "未启用"
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
