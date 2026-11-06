#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
自然语言 → 配置命令引擎（离线纯规则，借鉴 NetCMD ai.js 的架构思路自行实现）
架构：分句 → 同义词命中 → 数据驱动意图表（match 识别 / build 抽槽生成）→ 上下文携带
- 五大厂商按两大派系渲染：VRP/Comware（华为·H3C）、IOS（锐捷·迈普·思科）
- 输出带中文注释，与「命令释义」体系一致
"""

import re

VENDORS = ("huawei", "h3c", "ruijie", "maipu", "cisco")
VENDOR_CN = {"huawei": "华为", "h3c": "H3C", "ruijie": "锐捷",
             "maipu": "迈普", "cisco": "思科"}

# 接口名识别（含 vlanif/SVI 写法）
IF_RE = re.compile(
    r"(?:GigabitEthernet|Ten-GigabitEthernet|XGE|GE|Gi|Eth(?:ernet)?|Fa(?:stEthernet)?|Te|"
    r"Eth-Trunk|Bridge-Aggregation|Port-channel|Vlanif|Vlan-interface|vlan-interface"
    r")\s?-?\s?\d+(?:/\d+)*(?::\d+)?",
    re.I)
IP_RE = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?![\d.])")  # \b 在中文字符后不成立，用环视断言

_SKIP = {"__skip__": True}  # 哨兵：本分句已自行处理（路由/VLAN 直接入块）


# ---------------------------------------------------------------- 槽位抽取
def _ports(seg):
    """一句话里出现的全部接口名"""
    return [p for p in IF_RE.findall(seg) or []]


def _ips(seg):
    return IP_RE.findall(seg or "")


def _ip_mask(seg):
    """抽 IP（含 /掩码 或 点分掩码）"""
    m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})(?:\s*/\s*(\d{1,2})|\s+(\d{1,3}(?:\.\d{1,3}){3}))?", seg or "")
    if not m:
        return {"ip": "", "mask": ""}
    mask = m.group(2)
    if mask:
        mask = _cidr_to_mask(int(mask))
    elif m.group(3):
        mask = m.group(3)
    else:
        mask = "255.255.255.0"
    return {"ip": m.group(1), "mask": mask}


def _cidr_to_mask(bits):
    if not 0 <= bits <= 32:
        return "255.255.255.0"
    return ".".join(str((((0xFFFFFFFF << (32 - bits)) & 0xFFFFFFFF) >> ((3 - i) * 8)) & 0xFF) for i in range(4))


def _vlan_ids(seg):
    """抽 VLAN 号：先剥掉接口名 / IP / 密码 / 账号等噪音，再取剩余数字"""
    s = seg or ""
    s = IF_RE.sub(" ", s)                       # 接口名（含 vlanif）
    s = IP_RE.sub(" ", s)                       # IP 地址
    s = re.sub(r"(?:密码|口令|账号|账户|用户名?|password|pwd)[^\s，,。;；]*", " ", s, flags=re.I)
    s = re.sub(r"\b\d{1,3}/\d{1,2}\b", " ", s)  # /掩码写法
    out = []
    for v in re.findall(r"(?<![\d/])(\d{1,4})(?![\d/])", s):
        if 1 <= int(v) <= 4094 and v not in out:
            out.append(v)
    return out


def _between(seg, ctx):
    """上下文合并：本句没有就看上一句（接口/VLAN 常跨句出现）"""
    return seg if seg.strip() else (ctx or "")


_SVI_RE = re.compile(r"^(?:vlanif|vlan-interface|vlan)\s*-?\s*(\d+)$", re.I)
_SHORT_IF = [(re.compile(r"^(gigabitethernet|gi|ge|g)\s*-?\s*(.+)$", re.I), "GigabitEthernet"),
             (re.compile(r"^(fastethernet|fa)\s*-?\s*(.+)$", re.I), "FastEthernet"),
             # 注意顺序：带连字符全名 ten-gigabitethernet 必须排在短名 te 之前，
             # 否则全名的前缀 "Te" 会被短名分支再展开一次（真机 Ten-GE 口实测踩中：
             # Ten-GigabitEthernet1/0/27 → Ten-GigabitEthernetn-GigabitEthernet1/0/27）
             (re.compile(r"^(tengigabitethernet|ten-gigabitethernet|xge|te)\s*-?\s*(.+)$", re.I), "Ten-GigabitEthernet"),
             (re.compile(r"^(ethernet|eth)\s*-?\s*(\d.*)$", re.I), "Ethernet")]


def _is_svi(raw: str) -> bool:
    return bool(_SVI_RE.match((raw or "").strip()))


def norm_port(vendor: str, raw: str) -> str:
    """接口名规范化：gi1/0/5 → GigabitEthernet1/0/5；vlanif10 → Vlanif10（按厂商）"""
    p = (raw or "").strip().replace(" ", "")
    m = _SVI_RE.match(p)
    if m:
        vid = m.group(1)
        if vendor == "huawei":
            return f"Vlanif{vid}"
        if vendor == "h3c":
            return f"Vlan-interface{vid}"
        return f"Vlan{vid}"
    bare = re.match(r"^(\d+/\d+/\d+)$", p)   # 裸端口名（1/0/2）→ 补全成 GigabitEthernet
    if bare:
        return "GigabitEthernet" + bare.group(1)
    for pat, full in _SHORT_IF:
        m = pat.match(p)
        if m:
            return full + m.group(2)
    return p


# ---------------------------------------------------------------- 发射器（按派系）
def _em(vendor, huawei, h3c, ios):
    if vendor == "huawei":
        return huawei
    if vendor == "h3c":
        return h3c if h3c is not None else huawei
    return ios


def e_hostname(vendor, name):
    return _em(vendor,
               [("system-view", "进入系统视图"), (f"sysname {name}", "设置设备名称")],
               None,
               [("configure terminal", "进入配置模式"), (f"hostname {name}", "设置设备名称")])


def e_login(vendor, user, pwd, ssh=True, telnet=False):
    """远程登录（SSH/Telnet）+ 本地账号"""
    if vendor in ("huawei", "h3c"):
        lines = [("system-view", "进入系统视图")]
        if ssh:
            lines += _em(vendor,
                         [("stelnet server enable", "开启 SSH 服务"),
                          ("public-key local create rsa", "生成本地 RSA 密钥对（SSH 必需）")],
                         [("ssh server enable", "开启 SSH 服务"),
                          ("public-key local create rsa", "生成本地 RSA 密钥对（SSH 必需）")], [])
        if telnet:
            lines.append(("telnet server enable", "开启 Telnet 服务（明文传输，慎用）"))
        lines.append(("aaa", "进入 AAA 视图"))
        lines.append((f"local-user {user}", f"创建本地用户 {user}"))
        pw_cmd = "password cipher" if vendor == "huawei" else "password simple"
        lines.append((f" {pw_cmd} {pwd}", "设置登录密码（密文存储）"))
        svc = "ssh" if (ssh and not telnet) else ("telnet" if (telnet and not ssh) else "ssh telnet")
        lines.append((f" service-type {svc}", "允许该用户使用的登录方式"))
        if vendor == "huawei":
            lines.append((f" local-user {user} privilege level 15", "用户权限：最高级"))
            lines.append(("quit", "退回系统视图"))
            lines.append(("user-interface vty 0 4", "进入虚拟终端线路"))
            lines.append((" authentication-mode aaa", "线路认证走 AAA"))
            if ssh:
                lines.append((" protocol inbound ssh", "线路只允许 SSH 接入"))
        else:
            lines.append((" authorization-attribute user-role network-admin", "用户权限：管理员"))
            lines.append(("quit", "退回系统视图"))
            lines.append(("line vty 0 4", "进入虚拟终端线路"))
            lines.append((" authentication-mode scheme", "线路认证走本地用户"))
        return lines
    lines = [("configure terminal", "进入配置模式")]
    if ssh:
        lines += [("crypto key generate rsa", "生成 RSA 密钥对（SSH 必需）"),
                  ("ip ssh version 2", "SSH 使用 v2")]
    lines += [(f"username {user} privilege 15 secret {pwd}", "创建管理员账号（密码加密存储）"),
              ("line vty 0 4", "进入虚拟终端线路"),
              (" login local", "线路使用本地账号认证")]
    if ssh and not telnet:
        lines.append((" transport input ssh", "线路只允许 SSH 接入"))
    if telnet:
        lines.append((" transport input telnet" if not ssh else " transport input all", "允许 Telnet 接入"))
    return lines


def _vlan_runs(vids):
    """[1,5,92,999..1048] → [(1,1),(5,5),(92,92),(999,1048)]（连号≥3 才成段）"""
    try:
        vs = sorted({int(v) for v in vids})
    except (TypeError, ValueError):
        return None
    runs, i = [], 0
    while i < len(vs):
        j = i
        while j + 1 < len(vs) and vs[j + 1] == vs[j] + 1:
            j += 1
        runs.append((vs[i], vs[j]))
        i = j + 1
    return runs


def e_vlan_create(vendor, vids):
    runs = _vlan_runs(vids)
    if vendor == "huawei":
        if runs:
            # 连号段压缩（真机实测：60 个 VLAN 平铺一行不可读，vlan batch 999 to 1048 更标准）
            toks = []
            for a, b in runs:
                if b >= a + 2:
                    toks.append(f"{a} to {b}")
                else:
                    toks.extend(str(v) for v in range(a, b + 1))
            body = " ".join(toks)
        else:
            body = " ".join(str(v) for v in vids)
        return [("system-view", "进入系统视图"), (f"vlan batch {body}", "批量创建 VLAN")]
    if vendor == "h3c":
        out = [("system-view", "进入系统视图")]
        if runs:
            for a, b in runs:
                if b >= a + 2:
                    out.append((f"vlan {a} to {b}", f"创建 VLAN {a}~{b}"))
                else:
                    out.extend((f"vlan {v}", f"创建 VLAN {v}") for v in range(a, b + 1))
        else:
            out.extend((f"vlan {v}", f"创建 VLAN {v}") for v in vids)
        return out
    out = [("configure terminal", "进入配置模式")]
    for v in vids:
        out += [(f"vlan {v}", f"创建 VLAN {v}"), ("exit", "退出 VLAN 视图")]
    return out


def e_port_access(vendor, port, vid):
    port = norm_port(vendor, port)
    base = [("system-view" if vendor in ("huawei", "h3c") else "configure terminal", "进入配置视图"),
            (f"interface {port}", "进入接口视图"),
            (" port link-type access", "端口设为 Access 模式")]
    if vendor == "huawei":
        base.append((f" port default vlan {vid}", f"端口划入 VLAN {vid}"))
    elif vendor == "h3c":
        base.append((f" port access vlan {vid}", f"端口划入 VLAN {vid}"))
    else:
        base[-1] = (" switchport mode access", "端口设为 Access 模式")
        base.append((f" switchport access vlan {vid}", f"端口划入 VLAN {vid}"))
    return base


def e_port_trunk(vendor, port, vids):
    port = norm_port(vendor, port)
    head = [("system-view" if vendor in ("huawei", "h3c") else "configure terminal", "进入配置视图"),
            (f"interface {port}", "进入接口视图")]
    vs = " ".join(vids) if vendor in ("huawei", "h3c") else ",".join(vids)
    if vendor == "huawei":
        head += [(" port link-type trunk", "端口设为 Trunk 模式"),
                 (f" port trunk allow-pass vlan {vs}", "Trunk 放行 VLAN")]
    elif vendor == "h3c":
        head += [(" port link-type trunk", "端口设为 Trunk 模式"),
                 (f" port trunk permit vlan {vs}", "Trunk 放行 VLAN")]
    else:
        head += [(" switchport mode trunk", "端口设为 Trunk 模式"),
                 (f" switchport trunk allowed vlan add {vs}", "Trunk 放行 VLAN")]
    return head


def e_iface(vendor, port, ip="", mask="", desc="", shut="", mtu=""):
    port = norm_port(vendor, port)
    head = [("system-view" if vendor in ("huawei", "h3c") else "configure terminal", "进入配置视图"),
            (f"interface {port}", "进入接口视图")]
    svi = _is_svi(port)
    if vendor == "huawei" and not svi:
        head.append((" undo portswitch", "切换为三层接口"))
    elif vendor == "h3c" and not svi:
        head.append((" port link-mode route", "切换为三层接口"))
    elif vendor in ("ruijie", "maipu", "cisco") and not svi and not re.match(r"^Vlan", port, re.I):
        head.append((" no switchport", "切换为三层接口"))
    if ip:
        head.append((f" ip address {ip} {mask}", "配置接口 IP 地址"))
    if desc:
        head.append((f" description {desc}", "接口描述（便于运维识别）"))
    if mtu:
        head.append((f" mtu {mtu}", "设置接口 MTU"))
    if shut == "down":
        head.append((" shutdown", "手工关闭端口"))
    elif shut == "up":
        head.append((" undo shutdown" if vendor in ("huawei", "h3c") else " no shutdown", "启用端口"))
    return head


def e_route(vendor, dst, mask, nh):
    cmd = "ip route-static" if vendor in ("huawei", "h3c") else "ip route"
    return [(f"{cmd} {dst} {mask} {nh}", "静态路由（目的网段+掩码+下一跳）")]


def e_route_default(vendor, nh):
    cmd = "ip route-static" if vendor in ("huawei", "h3c") else "ip route"
    return [(f"{cmd} 0.0.0.0 0.0.0.0 {nh}", "默认路由（所有未知流量走下一跳）")]


def e_linkagg(vendor, gid, ports, mode="lacp"):
    ports = [norm_port(vendor, p) for p in ports]
    if vendor == "huawei":
        lines = [("system-view", "进入系统视图"), (f"interface Eth-Trunk {gid}", "创建链路聚合口")]
        if mode == "lacp":
            lines.append((" mode lacp", "聚合使用 LACP 动态协商"))
        for p in ports:
            lines.append((f"interface {p}", "进入成员口视图"))
            lines.append((f" eth-trunk {gid}", f"加入聚合组 {gid}"))
        return lines
    if vendor == "h3c":
        lines = [("system-view", "进入系统视图"), (f"interface Bridge-Aggregation {gid}", "创建链路聚合口")]
        for p in ports:
            lines.append((f"interface {p}", "进入成员口视图"))
            lines.append((f" port link-aggregation group {gid}", f"加入聚合组 {gid}"))
        return lines
    lines = [("configure terminal", "进入配置模式"), (f"interface Port-channel {gid}", "创建链路聚合口")]
    for p in ports:
        lines.append((f"interface {p}", "进入成员口视图"))
        lines.append((f" channel-group {gid} mode active", f"加入聚合组 {gid}（LACP）"))
    return lines


def e_acl(vendor, act, src, mask, dst="", dmask="", port="", direction="in"):
    if port:
        port = norm_port(vendor, port)
    if vendor in ("huawei", "h3c"):
        ext = bool(dst)
        num = 3000 if ext else 2000
        lines = [("system-view", "进入系统视图"), (f"acl number {num}", f"创建{'扩展' if ext else '基本'}ACL"),
                 (f" rule 10 {act} ip source {src} {mask}" +
                  (f" destination {dst} {dmask}" if ext else ""), f"规则：{('允许' if act == 'permit' else '拒绝')}该网段")]
        if port:
            lines.append((f"interface {port}", "进入接口视图"))
            lines.append(((" traffic-filter" if vendor == "huawei" else " packet-filter") +
                          f" {'inbound' if direction == 'in' else 'outbound'} acl {num}", "在接口应用 ACL"))
        return lines
    lines = [("configure terminal", "进入配置模式"),
             ("ip access-list extended NETOPS_ACL", "创建扩展 ACL"),
             (f" {act} ip {src} {mask} {' host ' + dst if dst else 'any'}", f"规则：{('允许' if act == 'permit' else '拒绝')}该网段")]
    if port:
        lines.append((f"interface {port}", "进入接口视图"))
        lines.append((f" ip access-group NETOPS_ACL {direction}", "在接口应用 ACL"))
    return lines


def e_portsec(vendor, port, max_mac=1):
    port = norm_port(vendor, port)
    head = [("system-view" if vendor in ("huawei", "h3c") else "configure terminal", "进入配置视图"),
            (f"interface {port}", "进入接口视图")]
    if vendor in ("huawei", "h3c"):
        head += [(" port-security enable", "开启端口安全"),
                 (f" port-security max-mac-count {max_mac}" if vendor == "h3c" else
                  f" port-security max-mac-num {max_mac}", f"最多学习 {max_mac} 个 MAC（防私接）"),
                  (" port-security protect-action restrict" if vendor == "h3c" else
                   " port-security protect-action restrict", "违规报文丢弃并告警")]
    else:
        head += [(" switchport port-security", "开启端口安全"),
                 (f" switchport port-security maximum {max_mac}", f"最多学习 {max_mac} 个 MAC（防私接）"),
                 (" switchport port-security violation restrict", "违规报文丢弃并告警")]
    return head


def e_dhcp_server(vendor, pool, ip, mask, gw):
    if vendor == "huawei":
        return [("system-view", "进入系统视图"), ("dhcp enable", "全局开启 DHCP"),
                (f"ip pool {pool}", f"创建地址池 {pool}"),
                (f" network {ip} mask {mask}", "地址池网段"),
                (f" gateway-list {gw}", "下发的网关地址")]
    if vendor == "h3c":
        return [("system-view", "进入系统视图"), ("dhcp enable", "全局开启 DHCP"),
                (f"dhcp server ip-pool {pool}", f"创建地址池 {pool}"),
                (f" network {ip} mask {mask}", "地址池网段"),
                (f" gateway-list {gw}", "下发的网关地址")]
    return [("configure terminal", "进入配置模式"),
            (f"ip dhcp pool {pool}", f"创建地址池 {pool}"),
            (f" network {ip} {mask}", "地址池网段"),
            (f" default-router {gw}", "下发的网关地址")]


def e_ntp(vendor, ip):
    if vendor in ("huawei", "h3c"):
        return [("system-view", "进入系统视图"), (f"ntp-service unicast-server {ip}", "NTP 时间同步服务器")]
    return [("configure terminal", "进入配置模式"), (f"ntp server {ip}", "NTP 时间同步服务器")]


def e_syslog(vendor, ip):
    if vendor in ("huawei", "h3c"):
        return [("system-view", "进入系统视图"), (f"info-center loghost {ip}", "日志外送服务器")]
    return [("configure terminal", "进入配置模式"), (f"logging host {ip}", "日志外送服务器")]


def e_snmp(vendor, community, trap_ip=""):
    if vendor in ("huawei", "h3c"):
        lines = [("system-view", "进入系统视图"), ("snmp-agent", "开启 SNMP"),
                 ("snmp-agent community read " + community, "只读团体字"),
                 ("snmp-agent sys-info version v2c", "SNMP 使用 v2c")]
        if trap_ip:
            lines.append((f"snmp-agent target-host trap address udp-domain {trap_ip} "
                          f"params securityname {community}", "告警上送网管服务器"))
        return lines
    lines = [("configure terminal", "进入配置模式"),
             (f"snmp-server community {community} RO", "只读团体字"),
             ("snmp-server enable traps", "开启告警")]
    if trap_ip:
        lines.append((f"snmp-server host {trap_ip} version 2c {community}", "告警上送网管服务器"))
    return lines


def e_save(vendor):
    return [("save" if vendor in ("huawei", "h3c") else "write memory", "保存配置（设备会提示确认）")]


# ---------------------------------------------------------------- 意图表（顺序即优先级）
INTENTS = [
    {"key": "hostname",
     "match": lambda s, c: re.search(r"命名(?:为)?|主机名|设备名|sysname|hostname|起名|取名|叫(?:做)?(?=\s*[A-Za-z0-9])|名字", s, re.I),
     "build": lambda s, c, v: _ok(e_hostname(v, re.search(r"(?:命名(?:为)?|主机名|设备名|sysname|hostname|起名(?:为)?|取名(?:为)?|叫做|名字(?:叫|为|是|设为)?)\s*[:：]?\s*([A-Za-z0-9_\-]+)", s, re.I).group(1)), "设备命名")},

    {"key": "login",
     "match": lambda s, c: re.search(r"ssh|telnet|远程登录|远程管理|开启登录|管理登录|账号|账户|登录名|创建用户|建用户|console\s*密码|串口密码", s, re.I),
     "build": lambda s, c, v: _ok(e_login(v, re.search(r"(?:账号|账户|用户名?|登录名|user)\s*[:：]?\s*([A-Za-z0-9_\-]+)", s, re.I).group(1) if re.search(r"账号|账户|用户名|登录名", s, re.I) else "admin",
                                  re.search(r"(?:密码|口令|password|pwd)\s*[:：]?\s*([A-Za-z0-9_@#.\-]+)", s, re.I).group(1) if re.search(r"密码|口令|password|pwd", s, re.I) else "Admin@123",
                                  ssh=not re.search(r"关闭|禁用|不要|别开|关掉", s) and (not re.search(r"telnet", s, re.I) or re.search(r"ssh", s, re.I)),
                                  telnet=bool(re.search(r"telnet", s, re.I))), "远程登录")},

    {"key": "acl",
     "match": lambda s, c: re.search(r"\bacl\b|访问控制|拒绝|deny|封|拦|屏蔽|阻止|不许|不让|不能访问|禁止.*(访问|网段)|允许访问", s, re.I),
     "build": lambda s, c, v: _build_acl(s, c, v)},

    {"key": "portsec",
     "match": lambda s, c: re.search(r"端口安全|port-?security|限制.*mac|最多.*mac|防私接|只能接", s, re.I),
     "build": lambda s, c, v: _build_portsec(s, c, v)},

    {"key": "linkagg",
     "match": lambda s, c: re.search(r"聚合|eth-?trunk|链路捆绑|link\s*agg|绑成|绑一起|做.*聚合|两根.*绑", s, re.I),
     "build": lambda s, c, v: _build_linkagg(s, c, v)},

    {"key": "dhcp",
     "match": lambda s, c: re.search(r"dhcp", s, re.I) and not re.search(r"中继|relay|转发", s, re.I) and re.search(r"地址池|pool|服务器|自动获取|分配|开启?dhcp|自动\s*ip", s, re.I),
     "build": lambda s, c, v: _build_dhcp(s, c, v)},

    {"key": "iface",
     "match": lambda s, c: IF_RE.search(s) and (_ips(s) or re.search(r"描述|description|关闭|启用|打开|shutdown|mtu|隔离", s, re.I)),
     "build": lambda s, c, v: _build_iface(s, c, v)},

    {"key": "trunk",
     "match": lambda s, c: re.search(r"trunk|干道|中继", s, re.I),
     "build": lambda s, c, v: _build_trunk(s, c, v)},

    {"key": "access",
     "match": lambda s, c: re.search(r"access|接入", s, re.I),
     "build": lambda s, c, v: _build_access(s, c, v)},

    {"key": "vlan",
     "match": lambda s, c: re.search(r"vlan|划分|划到|划进|创建.*vlan|新建.*vlan|建.*vlan", s, re.I),
     "build": lambda s, c, v: _build_vlan(s, c, v)},

    {"key": "route_default",
     "match": lambda s, c: re.search(r"默认路由|缺省路由|默认网关|上外网|出外网|访问外网|访问互联网|所有.*流量.*走", s, re.I) and (_ips(s) or _ips(c)),
     "build": lambda s, c, v: _build_default_route(s, c, v)},

    {"key": "route",
     "match": lambda s, c: (re.search(r"到|去|经|走|下一跳|经由|通过|送往", s) and len(_ips(s)) >= 2) or (re.search(r"静态路由|明细路由", s) and _ips(s)),
     "build": lambda s, c, v: _build_route(s, c, v)},

    {"key": "ntp",
     "match": lambda s, c: re.search(r"ntp|时间同步|时钟|对时|授时", s, re.I),
     "build": lambda s, c, v: _ok(e_ntp(v, (_ips(s) or _ips(c))[0]), "NTP 时间同步") if (_ips(s) or _ips(c)) else None},

    {"key": "syslog",
     "match": lambda s, c: re.search(r"syslog|日志主机|日志服务器|远程日志|日志.*上送|日志.*外发", s, re.I),
     "build": lambda s, c, v: _ok(e_syslog(v, (_ips(s) or _ips(c))[0]), "日志外送") if (_ips(s) or _ips(c)) else None},

    {"key": "snmp",
     "match": lambda s, c: re.search(r"snmp|团体字|网管|trap|监控.*(交换机|路由|设备)", s, re.I),
     "build": lambda s, c, v: _ok(e_snmp(v, (re.search(r"团体字?\s*[:：]?\s*([A-Za-z0-9_\-]+)", s, re.I).group(1) if re.search(r"团体字", s) else "public"),
                                        (_ips(s) or _ips(c))[0] if (_ips(s) or _ips(c)) else ""), "SNMP 网管")},

    {"key": "save",
     "match": lambda s, c: re.search(r"保存|存盘|保存配置", s),
     "build": lambda s, c, v: _ok(e_save(v), "保存配置")},
]


def _ok(lines, intent):
    return {"lines": lines, "intent": intent}


# ---------------------------------------------------------------- 复杂意图的 build
def _build_acl(s, c, v):
    ips = _ips(s) or _ips(c)
    if not ips:
        return None
    m = _ip_mask(s)
    src, mask = m["ip"], m["mask"]
    act = "deny" if re.search(r"拒绝|deny|封|拦|屏蔽|阻止|不许|不让|不能访问|禁止", s, re.I) else "permit"
    port = _ports(s)[0] if _ports(s) else ""
    return _ok(e_acl(v, act, src, mask, port=port), f"ACL {'拒绝' if act == 'deny' else '允许'} {src}")


def _build_portsec(s, c, v):
    pts = _ports(s) or _ports(c)
    if not pts:
        return None
    m = re.search(r"(?:最多|限制|只能接?)\s*(\d+)", s)
    return _ok(e_portsec(v, pts[0], int(m.group(1)) if m else 1), f"端口安全 {pts[0]}")


def _build_linkagg(s, c, v):
    pts = _ports(s) or _ports(c)
    if not pts:
        return None
    m = re.search(r"(?:组|group|trunk)\s*(\d+)", s, re.I)
    return _ok(e_linkagg(v, m.group(1) if m else "1", pts), "链路聚合")


def _build_dhcp(s, c, v):
    m = _ip_mask(s) or _ip_mask(c)
    if not m["ip"]:
        return None
    ips = _ips(s)
    gw = ips[1] if len(ips) > 1 else m["ip"].rsplit(".", 1)[0] + ".1"
    pool = re.search(r"(?:地址池|pool)\s*[:：]?\s*([A-Za-z0-9_\-]+)", s, re.I)
    return _ok(e_dhcp_server(v, pool.group(1) if pool else "pool1", m["ip"], m["mask"], gw), "DHCP 服务器")


def _build_trunk(s, c, v):
    vids = _vlan_ids(s) or _vlan_ids(c)
    pts = _ports(s) or _ports(c)
    if not (vids and pts) or _is_svi(pts[0]):
        return None
    return _ok(e_port_trunk(v, pts[0], vids), f"Trunk {pts[0]} 放行 VLAN {','.join(vids)}")


def _build_access(s, c, v):
    vids = _vlan_ids(s) or _vlan_ids(c)
    pts = _ports(s) or _ports(c)
    if not (vids and pts) or _is_svi(pts[0]):
        return None
    return _ok(e_port_access(v, pts[0], vids[0]), f"Access {pts[0]} → VLAN {vids[0]}")


def _build_vlan(s, c, v):
    vids = _vlan_ids(s) or _vlan_ids(c)
    if not vids:
        return None
    pts = [p for p in _ports(s) if not _is_svi(p)]  # SVI（vlanif）不是 access 口
    if pts:
        return {"lines": e_port_access(v, pts[0], vids[0]), "intent": f"VLAN {vids[0]} / Access {pts[0]}"}
    return {"lines": e_vlan_create(v, vids), "intent": f"创建 VLAN {','.join(vids)}"}


def _build_default_route(s, c, v):
    ips = _ips(s) or _ips(c)
    if not ips:
        return None
    nh = ips[-1]
    return {"lines": e_route_default(v, nh), "intent": f"默认路由 → {nh}"}


def _build_route(s, c, v):
    ips = _ips(s)
    if len(ips) < 2:
        return None
    dst, nh = ips[0], ips[-1]
    m = _ip_mask(s)
    return {"lines": e_route(v, dst, m["mask"], nh), "intent": f"静态路由 {dst} → {nh}"}


def _build_iface(s, c, v):
    pts = _ports(s) or _ports(c)
    if not pts:
        return None
    m = _ip_mask(s)
    d = re.search(r"(?:描述|description|desc)\s*[:：]?\s*([^\s，,。]+)", s, re.I)
    shut = "down" if re.search(r"关闭|shutdown|禁用|关掉|停掉", s, re.I) else ("up" if re.search(r"启用|打开|开启|激活", s, re.I) else "")
    mtu = re.search(r"mtu\s*(\d+)", s, re.I)
    if not (m["ip"] or d or shut or mtu):
        return None
    return {"lines": e_iface(v, pts[0], m["ip"], m["mask"], d.group(1) if d else "", shut,
                             mtu.group(1) if mtu else ""),
            "intent": f"接口 {pts[0]}" + (f" IP {m['ip']}" if m["ip"] else "")}


# ---------------------------------------------------------------- 主入口
def parse(text: str, vendor: str):
    """中文需求 → {'lines': [(cmd, note)], 'intents': [str], 'unknown': [分句]}"""
    vendor = vendor if vendor in VENDORS else "huawei"
    result = {"lines": [], "intents": [], "unknown": []}
    if not (text or "").strip():
        return result

    # 1) 口语化分句：标点 + 并列连词
    segs = re.split(r"[\n。；;，,]+|(?=并且|然后|另外|同时|以及|还有|接着|顺带)", text)
    segs = [x.strip() for x in segs if x.strip()]

    # 2) 逐句匹配意图（携带上一分句作上下文：接口/VLAN 常跨句）
    ctx = ""
    route_seen = set()
    seen_blocks = set()
    last_key, last_start = None, 0
    for seg in segs:
        hit, hit_key = None, None
        for it in INTENTS:
            try:
                if it["match"](seg, ctx):
                    built = it["build"](seg, ctx, vendor)
                    if built:
                        hit, hit_key = built, it["key"]
                        break
            except Exception:
                continue
        if hit:
            # 路由去重（分句可能重复命中）
            if hit["intent"].startswith(("静态路由", "默认路由")):
                key = hit["lines"][0][0]
                if key in route_seen:
                    ctx = seg
                    continue
                route_seen.add(key)
            if hit_key == last_key:
                # 连续同类意图：后句是对前句的补充（如「开启ssh」→「账号xx密码yy」），以后句为准替换
                del result["lines"][last_start:]
                result["intents"][-1] = hit["intent"]
            else:
                sig = tuple(cmd for cmd, _ in hit["lines"])
                if sig in seen_blocks:   # 完全重复的配置块直接跳过
                    ctx = seg
                    continue
                seen_blocks.add(sig)
                last_start = len(result["lines"])
                result["intents"].append(hit["intent"])
            result["lines"].extend(hit["lines"])
            last_key = hit_key
        else:
            result["unknown"].append(seg)
            last_key = None   # 隔了一句后不再合并同类块
        ctx = seg
    return result


def to_plain(lines):
    """[(cmd, note)] → 纯命令文本"""
    return "\n".join(cmd for cmd, _ in lines)


if __name__ == "__main__":
    demo = ("设备命名为 CORE-01，创建vlan10 20，把gi1/0/5设为access口划入vlan10，"
            "GE1/0/24做trunk放行vlan 10 20，vlanif10配ip 192.168.10.1/24，"
            "默认路由指向192.168.10.254，开启ssh，账号admin密码Huawei@123，保存配置")
    import io
    import sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    for v in ("huawei", "h3c", "cisco"):
        r = parse(demo, v)
        print(f"\n===== {VENDOR_CN[v]} =====")
        print("意图:", " | ".join(r["intents"]))
        print("未识别:", r["unknown"])
        for cmd, note in r["lines"]:
            print(f"{cmd:<58} # {note}")
