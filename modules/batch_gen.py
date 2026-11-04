#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
批量生成引擎（对标 NetCMD 的「批量参数导入 CSV」）
两种模式：
  1) 批量接口：一行一个端口（接口/模式/VLAN/描述）→ 一次吐几十条端口配置
  2) 批量设备：一行一台设备（设备名/管理IP/掩码/网关/VLAN）→ 每台一份开局配置
表头支持中英文别名，分隔符自动识别（逗号/制表符，可直接贴 Excel）
"""

import re

try:
    from modules.nl_engine import (e_hostname, e_iface, e_login, e_ntp, e_route,
                                   e_syslog, e_vlan_create, norm_port)
except ImportError:  # 直接运行自测
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    from modules.nl_engine import (e_hostname, e_iface, e_login, e_ntp, e_route,
                                   e_syslog, e_vlan_create, norm_port)

# 表头别名 → 标准字段名
ALIASES = {
    "port": ("接口", "端口", "端口名", "interface", "port"),
    "mode": ("模式", "类型", "mode", "type"),
    "vlan": ("vlan", "vlan号", "vlanid", "vlan id"),
    "desc": ("描述", "备注", "说明", "desc", "description"),
    "name": ("设备", "设备名", "主机名", "名称", "name", "hostname", "sysname"),
    "ip": ("管理ip", "ip", "ip地址", "地址"),
    "mask": ("掩码", "子网掩码", "mask"),
    "gw": ("网关", "gateway", "gw", "默认网关"),
    "trunk_vlans": ("放行vlan", "trunk vlan", "trunk放行", "放行"),
}


def _canon(h):
    h = (h or "").strip().lower().replace(" ", "")
    for key, names in ALIASES.items():
        if h in [n.lower().replace(" ", "") for n in names]:
            return key
    return h


def parse_table(text: str):
    """CSV/TSV 文本 → (标准列头, [dict 行])；首行为表头"""
    lines = [l for l in (text or "").splitlines() if l.strip() and not l.strip().startswith("#")]
    if len(lines) < 2:
        return [], []
    delim = "\t" if "\t" in lines[0] else ","
    header = [_canon(h) for h in lines[0].split(delim)]
    rows = []
    for ln in lines[1:]:
        cells = [c.strip().strip('"').strip("'") for c in ln.split(delim)]
        if not any(cells):
            continue
        rows.append({k: (cells[i] if i < len(cells) else "") for i, k in enumerate(header)})
    return header, rows


def _l2_iface_block(vendor, port, mode, vlan, trunk_vlans, desc):
    """二层端口配置块（批量接口用，一次进入接口把所有参数配完）"""
    port = norm_port(vendor, port)
    if not port:
        return []
    vrp = vendor in ("huawei", "h3c")
    lines = [("system-view" if vrp else "configure terminal", "进入配置视图"),
             (f"interface {port}", "进入接口视图")]
    mode = (mode or "").lower()
    if mode.startswith("trunk") or trunk_vlans:
        if vrp:
            lines.append((" port link-type trunk", "端口设为 Trunk 模式"))
            vs = trunk_vlans.replace(",", " ").replace("，", " ")
            if vs:
                cmd = "port trunk allow-pass vlan" if vendor == "huawei" else "port trunk permit vlan"
                lines.append((f" {cmd} {vs}", f"Trunk 放行 VLAN {vs}"))
        else:
            lines.append((" switchport mode trunk", "端口设为 Trunk 模式"))
            if trunk_vlans:
                lines.append((f" switchport trunk allowed vlan add {trunk_vlans}", "Trunk 放行 VLAN"))
    else:
        if vrp:
            lines.append((" port link-type access", "端口设为 Access 模式"))
            if vlan:
                cmd = "port default vlan" if vendor == "huawei" else "port access vlan"
                lines.append((f" {cmd} {vlan}", f"端口划入 VLAN {vlan}"))
        else:
            lines.append((" switchport mode access", "端口设为 Access 模式"))
            if vlan:
                lines.append((f" switchport access vlan {vlan}", f"端口划入 VLAN {vlan}"))
    if desc:
        lines.append((f" description {desc}", "接口描述"))
    return lines


def gen_interface_batch(vendor, rows):
    """批量接口 → {lines, stats}"""
    lines, n = [], 0
    for r in rows:
        block = _l2_iface_block(vendor, r.get("port", ""), r.get("mode", ""),
                                r.get("vlan", ""), r.get("trunk_vlans", ""), r.get("desc", ""))
        if block:
            lines += block
            n += 1
    return {"lines": lines, "count": n}


def gen_device_batch(vendor, rows):
    """批量设备 → [{'name', 'lines'}], 跳过没有设备名的行"""
    devices = []
    for r in rows:
        name = r.get("name", "").strip()
        if not name:
            continue
        ip, mask = r.get("ip", ""), r.get("mask", "") or "255.255.255.0"
        gw, vid = r.get("gw", ""), (r.get("vlan", "") or "1").strip()
        lines = e_hostname(vendor, name)
        vrp = vendor in ("huawei", "h3c")
        if ip:
            if vid and vid != "1":
                lines += e_vlan_create(vendor, [vid])
            svi = f"Vlanif{vid}" if vendor == "huawei" else (
                f"Vlan-interface{vid}" if vendor == "h3c" else f"Vlan{vid}")
            lines += e_iface(vendor, svi, ip, mask)
        if gw:
            lines += e_route(vendor, "0.0.0.0", "0.0.0.0", gw)
        lines += e_login(vendor, "admin", "Admin@123", ssh=True)
        lines.append(("save" if vrp else "write memory", "保存配置（设备会提示确认）"))
        devices.append({"name": name, "lines": lines})
    return devices


def to_plain(lines):
    return "\n".join(c for c, _ in lines)


# ---------------------------------------------------------------- 自测
if __name__ == "__main__":
    import io
    import sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    csv1 = """接口,模式,VLAN,描述
GE1/0/1,access,10,前台电脑
1/0/2,access,10,打印机
GE1/0/24,trunk,,"上联核心 放行 10 20"
"""
    h, rows = parse_table(csv1)
    r = gen_interface_batch("huawei", rows)
    print("批量接口：", r["count"], "个口")
    print(to_plain(r["lines"])[:300], "...")

    csv2 = """设备名,管理IP,掩码,网关,VLAN
Access-01F-03,10.10.3.2,255.255.255.0,10.10.3.1,30
Access-02F-03,10.10.3.3,255.255.255.0,10.10.3.1,30
"""
    h2, rows2 = parse_table(csv2)
    devs = gen_device_batch("h3c", rows2)
    print("\n批量设备：", [d["name"] for d in devs])
    print(to_plain(devs[0]["lines"])[:260])
    assert len(devs) == 2 and "10.10.3.2" in to_plain(devs[0]["lines"])
    print("批量引擎自测通过")