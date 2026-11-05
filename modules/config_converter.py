#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
跨厂商配置转换引擎（对标 NetCMD 的「跨厂商转换」，思路：先解析成中立结构，再按目标厂商重渲染）
- 支持五大厂商互转，覆盖开局高频项：主机名/VLAN/Access口/Trunk口/SVI IP/静态路由/SSH登录
- 解析侧分两派实现：VRP/Comware（接口子命令带缩进）、IOS（块到 ! 或下一条全局命令为止）
- 渲染复用 nl_engine 的发射器，输出带中文注释
"""

import re

try:
    from modules.config_visualizer import expand_vlan_body
    from modules.nl_engine import (e_hostname, e_iface, e_login, e_port_access,
                                   e_port_trunk, e_route, e_vlan_create)
except ImportError:  # 直接运行本文件做自测时，把项目根目录补进 sys.path
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    from modules.config_visualizer import expand_vlan_body
    from modules.nl_engine import (e_hostname, e_iface, e_login, e_port_access,
                                   e_port_trunk, e_route, e_vlan_create)

VRP = ("huawei", "h3c")
IOS = ("ruijie", "maipu", "cisco")


# ---------------------------------------------------------------- 厂商识别
def detect_vendor(text: str) -> str:
    t = (text or "").lower()
    if "stelnet" in t or re.search(r"\bvlanif", t):
        return "huawei"
    if "vlan-interface" in t or "ssh server enable" in t or "comware" in t:
        return "h3c"
    if "switchport" in t or "running-config" in t or re.search(r"^hostname\s", text or "", re.M):
        return "cisco"
    if "ip route-static" in t or re.search(r"^ ?sysname\s", text or "", re.M):
        return "huawei"
    return "huawei"


# ---------------------------------------------------------------- 解析（→ 中立结构）
def parse_neutral(text: str, vendor: str) -> dict:
    """配置文本 → {sysname, vlans, ifaces, routes, ssh, telnet, users}"""
    neutral = {"sysname": "", "vlans": [], "ifaces": [], "routes": [],
               "ssh": False, "telnet": False, "users": []}
    if not text:
        return neutral
    lines = text.splitlines()
    cur = None

    for raw in lines:
        s = raw.strip()
        if not s or s.startswith(("!", "#")):
            cur = None
            continue
        indented = bool(raw[:1].isspace()) if raw else False

        m = re.match(r"^(?:sysname|hostname)\s+(\S+)", s, re.I)
        if m:
            neutral["sysname"] = m.group(1)
            cur = None
            continue

        m = re.match(r"^interface\s+(\S+)", s, re.I)
        if m:
            cur = {"name": m.group(1), "mode": "", "vlan": None,
                   "trunk_vlans": [], "ip": "", "mask": "", "desc": "",
                   "shut": ""}
            neutral["ifaces"].append(cur)
            continue

        m = re.match(r"^vlan\s+batch\s+([\d\s]+(?:to\s*[\d\s]+)?)$", s, re.I)
        if m:
            for v in expand_vlan_body(m.group(1)):
                _add_vlan(neutral, v)
            cur = None
            continue
        m = re.match(r"^vlan\s+(\d+(?:\s+to\s+\d+)?)\s*$", s, re.I)
        if m and "vlanif" not in s.lower() and "vlan-interface" not in s.lower():
            for v in expand_vlan_body(m.group(1)):
                _add_vlan(neutral, v)
            cur = None
            continue

        m = re.search(r"^ip\s+route(?:-static)?\s+(\d+\.\d+\.\d+\.\d+)\s+(\S+)\s+(\d+\.\d+\.\d+\.\d+)", s, re.I)
        if m and cur is None:
            neutral["routes"].append({"dst": m.group(1), "mask": _norm_mask(m.group(2)), "nh": m.group(3)})
            continue

        if re.search(r"^(?:stelnet|ssh)\s+server\s+enable", s, re.I):
            neutral["ssh"] = True
            continue
        if re.search(r"^ip\s+telnet\s+server|^telnet\s+server\s+enable", s, re.I):
            neutral["telnet"] = True
            continue
        m = re.match(r"^(?:local-user|username)\s+(\S+)", s, re.I)
        if m:
            neutral["users"].append(m.group(1))
            continue

        # ---- 接口子命令 ----
        if cur is None:
            continue
        if re.search(r"port\s+link-type\s+access|switchport\s+mode\s+access", s, re.I):
            cur["mode"] = "access"
        elif re.search(r"port\s+link-type\s+trunk|switchport\s+mode\s+trunk", s, re.I):
            cur["mode"] = "trunk"
        m = re.search(r"(?:port\s+default\s+vlan|port\s+access\s+vlan|switchport\s+access\s+vlan)\s+(\d+)", s, re.I)
        if m:
            cur["vlan"] = int(m.group(1))
            cur["mode"] = cur["mode"] or "access"
        m = re.search(r"(?:port\s+trunk\s+(?:permit|allow-pass)\s+vlan|switchport\s+trunk\s+allowed\s+vlan"
                      r"(?:\s+add)?)\s+([\d\s,，\-to]+)", s, re.I)
        if m:
            for v in re.findall(r"\d+", m.group(1)):
                cur["trunk_vlans"].append(int(v))
        m = re.search(r"ip\s+address\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)", s, re.I)
        if m:
            cur["ip"], cur["mask"] = m.group(1), m.group(2)
        m = re.search(r"^description\s+(.+)$", s, re.I)
        if m:
            cur["desc"] = m.group(1).strip()
        if re.match(r"^shutdown$", s, re.I):
            cur["shut"] = "down"
        elif re.match(r"^(?:undo\s+shutdown|no\s+shutdown)$", s, re.I):
            cur["shut"] = "up"

    return neutral


def _add_vlan(neutral, vid):
    if vid not in neutral["vlans"]:
        neutral["vlans"].append(vid)


def _norm_mask(m):
    if re.fullmatch(r"\d{1,2}", m):
        bits = int(m)
        return ".".join(str((((0xFFFFFFFF << (32 - bits)) & 0xFFFFFFFF) >> ((3 - i) * 8)) & 0xFF)
                        for i in range(4))
    return m


def _is_svi(name: str) -> bool:
    return bool(re.match(r"^(vlanif|vlan-interface|vlan)\s*-?\s*\d+$", (name or "").strip(), re.I))


# ---------------------------------------------------------------- 渲染（中立结构 → 目标厂商）
def convert(text: str, src_vendor: str, dst_vendor: str) -> dict:
    """返回 {lines: [(cmd, note)], report: [str], src_detected: str}"""
    src = detect_vendor(text) if src_vendor == "auto" else src_vendor
    n = parse_neutral(text, src)
    lines, report = [], []

    if n["sysname"]:
        lines += e_hostname(dst_vendor, n["sysname"])
        report.append(f"主机名 {n['sysname']}")
    if n["vlans"]:
        lines += e_vlan_create(dst_vendor, [str(v) for v in n["vlans"]])
        report.append(f"VLAN {', '.join(str(v) for v in n['vlans'])}")

    n_access = n_trunk = n_ip = 0
    for ifc in n["ifaces"]:
        name = ifc["name"]
        if ifc["mode"] == "access" and ifc["vlan"] is not None:
            lines += e_port_access(dst_vendor, name, str(ifc["vlan"]))
            n_access += 1
        elif ifc["mode"] == "trunk" and ifc["trunk_vlans"]:
            lines += e_port_trunk(dst_vendor, name, [str(v) for v in ifc["trunk_vlans"]])
            n_trunk += 1
        elif ifc["ip"]:
            lines += e_iface(dst_vendor, name, ifc["ip"], ifc["mask"],
                             ifc["desc"], ifc["shut"])
            n_ip += 1
        elif ifc["shut"] == "down":
            lines += e_iface(dst_vendor, name, desc=ifc["desc"], shut="down")
    if n_access:
        report.append(f"Access 口 {n_access} 个")
    if n_trunk:
        report.append(f"Trunk 口 {n_trunk} 个")
    if n_ip:
        report.append(f"三层接口/SVI {n_ip} 个")

    for r in n["routes"]:
        lines += e_route(dst_vendor, r["dst"], r["mask"], r["nh"])
    if n["routes"]:
        report.append(f"静态路由 {len(n['routes'])} 条")

    if n["ssh"] or n["telnet"] or n["users"]:
        user = n["users"][0] if n["users"] else "admin"
        lines += e_login(dst_vendor, user, "Admin@123",
                         ssh=n["ssh"], telnet=n["telnet"] and not n["ssh"])
        report.append(f"登录服务（账号 {user}，密码为占位符，需重设）")

    skipped = sum(1 for ifc in n["ifaces"]
                  if not (ifc["mode"] or ifc["ip"] or ifc["shut"] == "down"))
    if skipped:
        report.append(f"跳过 {skipped} 个无实质配置的接口块")

    return {"lines": lines, "report": report, "src_detected": src}


# ---------------------------------------------------------------- 自测
if __name__ == "__main__":
    import io
    import sys
    sys.path.insert(0, __file__.rsplit("\\", 2)[0])
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    h3c_cfg = """
 sysname Core-SW-01
#
vlan batch 10 20
#
telnet server enable
#
local-user admin
#
interface GigabitEthernet1/0/1
 port link-mode bridge
 port link-type access
 port access vlan 10
#
interface GigabitEthernet1/0/24
 port link-type trunk
 port trunk permit vlan 10 20
#
interface Vlan-interface10
 ip address 192.168.10.1 255.255.255.0
#
 ip route-static 0.0.0.0 0.0.0.0 192.168.10.254
"""
    r = convert(h3c_cfg, "auto", "huawei")
    print("识别源厂商:", r["src_detected"])
    print("报告:", " | ".join(r["report"]))
    for c, note in r["lines"]:
        print(f"{c:<52} # {note}")
    assert any("Vlanif" in c for c, _ in r["lines"]), "SVI 应转为华为 Vlanif"
    assert any("port default vlan" in c for c, _ in r["lines"]), "H3C access 应转为华为语法"
    assert any("port trunk allow-pass" in c for c, _ in r["lines"]), "H3C trunk 应转为华为语法"
    print("华为转换 OK")
