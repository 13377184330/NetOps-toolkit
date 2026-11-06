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
    """按信号强度排序：强语法标记 > 服务命令 > sysname 出厂默认值启发式。
    真机实测教训：精简配置（无 SSH/无 SVI）没有任何强标记，
    只剩 sysname 值可判（H3C 出厂默认 sysname 即 "H3C"，华为为 "Huawei"）。"""
    t = (text or "").lower()
    # 1) 华为特有：Vlanif SVI / vlan batch 批量建 VLAN
    if re.search(r"\bvlanif", t) or "vlan batch" in t:
        return "huawei"
    # 2) H3C 特有：Vlan-interface SVI / Comware 字样
    if "vlan-interface" in t or "comware" in t:
        return "h3c"
    # 3) 块式语法家族
    if "switchport" in t or "running-config" in t or re.search(r"^hostname\s", text or "", re.M):
        return "cisco"
    # 4) 服务命令：stelnet 为华为 VRP 写法（stelnet server enable）
    if "stelnet" in t:
        return "huawei"
    # 5) H3C Comware 的 SSH 开启写法
    if "ssh server enable" in t:
        return "h3c"
    # 6) sysname 值启发式：出厂默认/常见命名（H3C→"H3C"，华为→"Huawei"，锐捷 RG，迈普，思科）
    m = re.search(r"^ ?sysname\s+(\S+)", text or "", re.M | re.I)
    if m:
        v = m.group(1).lower()
        if "h3c" in v:
            return "h3c"
        if "huawei" in v or v.startswith("hw"):
            return "huawei"
        if "ruijie" in v or v.startswith("rg"):
            return "ruijie"
        if "maipu" in v:
            return "maipu"
        if "cisco" in v:
            return "cisco"
    # 7) 弱默认
    if "ip route-static" in t or re.search(r"^ ?sysname\s", text or "", re.M):
        return "huawei"
    return "huawei"


# ---------------------------------------------------------------- 解析（→ 中立结构）
def parse_neutral(text: str, vendor: str) -> dict:
    """配置文本 → {sysname, vlans, ifaces, routes, ssh, telnet, users}"""
    neutral = {"sysname": "", "vlans": [], "ifaces": [], "routes": [],
               "ssh": False, "telnet": False, "users": [], "sub_ips": 0}
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
                   "trunk_vlans": [], "trunk_removed": [], "ip": "", "mask": "", "desc": "",
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

        # 黑洞路由也解析（真机实测：ip route-static x.x.x.x 32 NULL0 曾被静默丢弃）
        m = re.search(r"^ip\s+route(?:-static)?\s+(\d+\.\d+\.\d+\.\d+)\s+(\S+)\s+(\d+\.\d+\.\d+\.\d+|NULL0)", s, re.I)
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
        # undo 撤销 trunk 放行（真机教训：undo port trunk permit vlan 1 曾被下面的 permit
        # 正则误当「添加」解析，转换结果与源配置意图相反——华为/H3C trunk 默认放行
        # VLAN 1，源配置显式撤销，转换必须同样撤销而不是放行）
        m_undo = re.match(r"^undo\s+port\s+trunk\s+(?:permit|allow-pass)\s+vlan\s+([\d\s,，\-to]+)$", s, re.I)
        if m_undo:
            for v in re.findall(r"\d+", m_undo.group(1)):
                v = int(v)
                if v in cur["trunk_vlans"]:
                    cur["trunk_vlans"].remove(v)
                if v not in cur["trunk_removed"]:
                    cur["trunk_removed"].append(v)
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
            if re.search(r"\bsub\s*$", s, re.I):
                # secondary IP（H3C 末尾 sub / 思科 secondary）：不覆盖主 IP，仅计数提示
                # （真机实测：Vlan-interface999 的 secondary 曾把主 IP 覆盖掉）
                neutral["sub_ips"] += 1
            else:
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
            if ifc.get("trunk_removed"):
                if dst_vendor in ("huawei", "h3c"):
                    # 华为/H3C trunk 默认放行 VLAN 1：源配置显式 undo 撤销的 VLAN 必须同样撤销
                    verb = "allow-pass" if dst_vendor == "huawei" else "permit"
                    for v in ifc["trunk_removed"]:
                        lines.append((f" undo port trunk {verb} vlan {v}",
                                      f"撤销 trunk 默认放行的 VLAN {v}（源配置显式 undo）"))
                # IOS 系 allowed 列表是绝对集合：不在列表中即已排除，无需额外命令
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
    if n.get("sub_ips"):
        report.append(f"跳过 {n['sub_ips']} 个 secondary IP（仅保留主 IP，如需请手工补配）")

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
