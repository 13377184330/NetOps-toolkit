#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
配置语法/规范纠错引擎（对标 NetCMD 的「配置语法纠错」，规则自行设计实现）
粘贴一份 running-config → 按厂商语法与安全基线逐行体检：
  严重：会直接导致功能失效/登录不上/下错命令
  警告：有安全隐患或大概率配错
  提示 ：基线规范建议
纯规则实现，不联网。
"""

import re

VRP = ("huawei", "h3c")
IOS = ("ruijie", "maipu", "cisco")

LEVEL_COLOR = {"严重": "#FA5151", "警告": "#FA9D3B", "提示": "#7A8699"}


def _mask_valid(mask: str) -> bool:
    """掩码必须连续（255.255.255.0 合法，255.255.255.1 非法）"""
    try:
        parts = [int(x) for x in mask.split(".")]
    except Exception:
        return False
    if len(parts) != 4 or any(p < 0 or p > 255 for p in parts):
        return False
    m = int.from_bytes(bytes(parts), "big")
    inv = (~m) & 0xFFFFFFFF
    if m == 0:
        return False
    return inv & (inv + 1) == 0


def lint(text: str, vendor: str) -> dict:
    """配置文本 → {items: [{line_no, level, issue, advice, line}], stats: {...}}"""
    vendor = vendor if vendor in VRP + IOS else "huawei"
    items = []
    lines = text.splitlines()

    def add(no, level, issue, advice, line=""):
        items.append({"line_no": no, "level": level, "issue": issue,
                      "advice": advice, "line": line.strip()})

    # ---------- 状态收集 ----------
    created_vlans = set()          # 显式创建的 VLAN
    access_refs = {}               # VLAN -> [行号]
    trunk_refs = {}                # VLAN -> [行号]
    ifaces = []                    # [(名称, 行号)]
    iface_ips = {}                 # IP -> (接口, 行号)
    acl_defined = set()
    acl_refs = {}
    ssh_on = telnet_on = False
    local_users = []
    users_no_service = []          # (用户, 行号)
    vty_lines = []
    vty_auth = False
    sysname = ""
    cur_iface = None
    trunk_pending = {}             # 接口名 -> 行号（trunk 未放行）

    for i, raw in enumerate(lines, 1):
        s = raw.strip()
        low = s.lower()

        # sysname
        m = re.match(r"^(?: )?(?:sysname|hostname)\s+(\S+)", low)
        if m:
            sysname = m.group(1)
            continue

        # interface 块
        m = re.match(r"^interface\s+(\S+)", low)
        if m:
            name = m.group(1)
            if any(n == name for n, _ in ifaces):
                add(i, "警告", f"接口 {name} 的配置块出现多次",
                    "合并到同一个 interface 块内，重复块可能导致前一块被误解为已撤销", s)
            ifaces.append((name, i))
            cur_iface = name
            continue

        # VLAN 创建
        m = re.match(r"^vlan\s+batch\s+([\d\s to]+)", low)
        if m:
            for v in re.findall(r"\d+", m.group(1)):
                created_vlans.add(int(v))
            continue
        m = re.match(r"^vlan\s+(\d+)", low)
        if m and "vlanif" not in low and "vlan-interface" not in low:
            created_vlans.add(int(m.group(1)))
            continue

        # access 口引用
        m = re.search(r"(?:port\s+default\s+vlan|port\s+access\s+vlan|switchport\s+access\s+vlan)\s+(\d+)", low)
        if m:
            access_refs.setdefault(int(m.group(1)), []).append(i)
            if int(m.group(1)) == 1:
                add(i, "提示", "Access 口使用默认 VLAN 1",
                    "默认 VLAN 建议只做管理隔离，业务口尽量划独立 VLAN", s)
            continue

        # trunk 放行
        m = re.search(r"(?:port\s+trunk\s+(?:permit|pvid)\s+vlan|port\s+trunk\s+allow-pass\s+vlan"
                      r"|switchport\s+trunk\s+allowed\s+vlan(?:\s+add)?)\s+([\d\s,，\-to]+)", low)
        if m:
            for v in re.findall(r"\d+", m.group(1)):
                trunk_refs.setdefault(int(v), []).append(i)
            trunk_pending.pop(cur_iface, None)
            continue
        if re.search(r"port\s+link-type\s+trunk|switchport\s+mode\s+trunk", low):
            trunk_pending[cur_iface] = i

        # IP 与掩码
        m = re.search(r"ip\s+address\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)", low)
        if m:
            ip, mask = m.group(1), m.group(2)
            if not _mask_valid(mask):
                add(i, "严重", f"掩码 {mask} 非法（不连续）",
                    "掩码必须从高位连续，如 255.255.255.0；请核对 IP 规划", s)
            if ip in iface_ips:
                other, other_no = iface_ips[ip]
                add(i, "严重", f"IP {ip} 重复配置（{other} 第 {other_no} 行已用）",
                    "同网段同 IP 会造成地址冲突，删除其一", s)
            iface_ips[ip] = (cur_iface or "?", i)
            continue

        # ACL
        m = re.search(r"\bacl\s+(?:basic\s+|number\s+|advanced\s+)?(\d+)", low)
        if m and cur_iface is None:
            acl_defined.add(m.group(1))
            continue
        m = re.search(r"(?:packet-filter|traffic-filter|ip\s+access-group)\s+(?:acl\s+)?(\d+)", low)
        if m:
            acl_refs.setdefault(m.group(1), []).append(i)

        # 登录/用户
        if re.search(r"^(?:stelnet|ssh)\s+server\s+enable", low):
            ssh_on = True
        if re.search(r"^telnet\s+server\s+enable|^ip\s+telnet\s+server", low):
            telnet_on = True
        m = re.match(r"^local-user\s+(\S+)", low)
        if m:
            local_users.append(m.group(1))
            users_no_service.append((m.group(1), i))
        if re.match(r"^ ?service-type\s+\S+", low) and users_no_service:
            users_no_service.pop()
        m = re.match(r"^username\s+(\S+)", low)
        if m:
            local_users.append(m.group(1))
        if re.search(r"user-interface\s+vty|line\s+vty", low):
            vty_lines.append(i)
        if re.search(r"authentication-mode|login\s+(local|authentication|scheme)", low):
            vty_auth = True

        # 明文密码
        if re.search(r"password\s+simple\s+\S+", low):
            add(i, "警告", "密码以明文形式存储（password simple）",
                "改用 password cipher / secret，避免配置文件泄露密码", s)
        if vendor in IOS and re.match(r"^password\s+\S+$", low):
            add(i, "警告", "线路密码未加密（IOS password 明文）",
                "改用 enable secret / username ... secret，并开启 service password-encryption", s)
        # IOS trunk 封装提示
        if vendor in IOS and re.search(r"switchport\s+mode\s+trunk", low):
            add(i, "提示", "Trunk 口建议显式指定封装",
                "部分平台需要 switchport trunk encapsulation dot1q，再 switchport mode trunk", s)

    # ---------- 交叉检查 ----------
    for vid, nos in access_refs.items():
        if vid not in created_vlans:
            add(nos[0], "严重", f"Access 口引用了未创建的 VLAN {vid}",
                f"先创建：{'vlan batch ' if vendor == 'huawei' else 'vlan '}{vid}", "")
    for vid, nos in trunk_refs.items():
        if vid not in created_vlans and vid != 1:
            add(nos[0], "警告", f"Trunk 放行了未创建的 VLAN {vid}",
                f"放行前先创建 VLAN {vid}，否则该 VLAN 流量不通", "")
    for iface, no in trunk_pending.items():
        if iface:
            add(no, "提示", f"{iface} 设了 Trunk 但未放行任何 VLAN",
                "默认只放行 VLAN 1；按需 port trunk permit/allow-pass vlan …", "")
    for acl, nos in acl_refs.items():
        if acl not in acl_defined:
            add(nos[0], "严重", f"接口引用了不存在的 ACL {acl}",
                f"先创建 acl {acl} 再应用到接口，否则过滤不生效/命令报错", "")
    if telnet_on and not acl_defined:
        add(0, "警告", "开启了 Telnet 且 VTY 无 ACL 限制",
            "Telnet 明文传输且全网可连；建议关闭或用 ACL 限定管理网段", "")
    if vty_lines and not vty_auth:
        add(vty_lines[0], "严重", "VTY 线路没有配置认证方式",
            "任何人敲回车就能进（VRP： authentication-mode scheme；IOS：login local）——"
            "这正是 SSH 登录立即被断的常见原因", "")
    if ssh_on and not local_users:
        add(0, "警告", "开启了 SSH 但没有创建本地用户",
            "先 local-user/username 创建账号，否则无凭据可登录", "")
    if not sysname and lines:
        add(0, "提示", "没有配置设备名称（sysname/hostname）",
            "命名规范便于拓扑识别与日志检索，如 Access-01F-03", "")
    if not iface_ips and lines:
        add(0, "提示", "整份配置没有任何 IP 地址",
            "没有管理地址就无法远程运维；建议给 Vlanif/Vlan-interface 配 IP", "")
    for user, no in users_no_service:
        add(no, "提示", f"本地用户 {user} 未指定 service-type",
            "未授权登录方式的用户创建后无法使用，补 service-type ssh/telnet", "")

    # 排序：严重 → 警告 → 提示，同级按行号
    order = {"严重": 0, "警告": 1, "提示": 2}
    items.sort(key=lambda x: (order.get(x["level"], 9), x["line_no"]))
    stats = {lv: sum(1 for x in items if x["level"] == lv) for lv in ("严重", "警告", "提示")}
    return {"items": items, "stats": stats}


def lint_score(stats: dict) -> str:
    """简单评分文案：问题越多分越低"""
    bad = stats["严重"] * 10 + stats["警告"] * 4 + stats["提示"] * 1
    score = max(0, 100 - bad)
    level = "优秀" if score >= 90 else ("良好" if score >= 75 else ("需改进" if score >= 60 else "高风险"))
    return f"{score} 分（{level}）"


# ---------------------------------------------------------------- 自测
if __name__ == "__main__":
    import io
    import sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    demo = """
 sysname Access-01
#
vlan batch 10
#
telnet server enable
#
interface GigabitEthernet1/0/1
 port link-type access
 port access vlan 20
#
interface GigabitEthernet1/0/2
 port link-type trunk
#
interface Vlan-interface10
 ip address 192.168.10.1 255.255.255.1
#
interface Vlan-interface10
 ip address 192.168.10.1 255.255.255.0
#
user-interface vty 0 4
 packet-filter 3000 inbound
"""
    r = lint(demo, "h3c")
    print("统计:", r["stats"], "|", lint_score(r["stats"]))
    for it in r["items"]:
        print(f"L{it['line_no']:<3} [{it['level']}] {it['issue']}")
    assert r["stats"]["严重"] >= 3, "应检出未创建VLAN/非法掩码/重复IP/不存在ACL"
    print("纠错引擎自测通过")
