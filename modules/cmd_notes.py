#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
命令释义引擎：给每条配置命令配一行中文说明（对标 NetCMD 的"命令释义"）
- 屏幕上显示 `命令  # 注释`，方便不懂命令的人看懂每行在干嘛
- 注释只用于阅读：复制 / 导出 / 下发一律走纯命令（strip_notes 兜底）
纯规则实现，无任何外部依赖
"""

import html
import re

# ---------------------------------------------------------------- 规则表
# (正则, 中文注释)。按顺序匹配，第一条命中即返回。
# 兼容 VRP/Comware（华为·H3C）与 IOS 派系（锐捷·迈普·思科）
_RULES = [
    # ---- 视图切换 ----
    (re.compile(r"^system-view$"), "进入系统视图"),
    (re.compile(r"^(sys|configure terminal|conf t)$"), "进入配置模式"),
    (re.compile(r"^(quit|exit)$"), "退出当前视图"),
    (re.compile(r"^(end|return)$"), "退回用户视图"),
    (re.compile(r"^interface\s+(\S+)", re.I), "进入接口视图"),
    (re.compile(r"^vlan\s+(\d+)", re.I), "创建/进入 VLAN"),
    (re.compile(r"^vlan\s+batch\s+(.+)", re.I), "批量创建 VLAN"),
    (re.compile(r"^vlan\s+database", re.I), "进入 VLAN 数据库（IOS 派系）"),

    # ---- 基本信息 ----
    (re.compile(r"^ ?sysname\s+(\S+)", re.I), "设置设备名称"),
    (re.compile(r"^hostname\s+(\S+)", re.I), "设置设备名称"),
    (re.compile(r"^ ?version\s+([\d.]+)", re.I), "软件版本信息"),
    (re.compile(r"^(#|!)$"), "配置分段符"),
    (re.compile(r"^ ?description\s+(.+)", re.I), "设置描述信息"),
    (re.compile(r"^ ?undo\s+description", re.I), "删除描述信息"),

    # ---- 用户与登录 ----
    (re.compile(r"^(aaa|local-user\s+\S+)$", re.I), "进入用户管理（AAA）"),
    (re.compile(r"^ ?local-user\s+(\S+)", re.I), "创建本地用户"),
    (re.compile(r"^(username|user\s+\S+)\s", re.I), "创建本地用户"),
    (re.compile(r"password( simple| cipher| \S+)?\s+\S+", re.I), "设置登录密码（密文存储）"),
    (re.compile(r"^ ?authorization-attribute\s+level\s+(\d+)", re.I), "设置用户权限等级"),
    (re.compile(r"^(privilege|level)\s*(level)?\s*(\d+)", re.I), "设置用户权限等级"),
    (re.compile(r"^ ?service-type\s+(.*)", re.I), "允许该用户使用的登录方式"),
    (re.compile(r"^(ssh server enable|stelnet server enable)$", re.I), "开启 SSH 服务"),
    (re.compile(r"^(telnet server enable|ip telnet server enable)$", re.I), "开启 Telnet 服务（明文，慎用）"),
    (re.compile(r"^(no|undo)\s+(telnet server enable|ip telnet server)", re.I), "关闭 Telnet 服务（安全加固）"),
    (re.compile(r"public-key\s+local\s+create\s+rsa", re.I), "生成本地 RSA 密钥对（SSH 必需）"),
    (re.compile(r"crypto key generate rsa", re.I), "生成 RSA 密钥对（SSH 必需）"),
    (re.compile(r"user-interface\s+(vty|con\w*)", re.I), "进入线路视图（远程/Console）"),
    (re.compile(r"line\s+(vty|con\w*)", re.I), "进入线路视图（远程/Console）"),
    (re.compile(r"authentication-mode\s+(scheme|password|none)", re.I), "线路认证方式"),
    (re.compile(r"login\s+(local|authentication)", re.I), "线路认证方式"),
    (re.compile(r"protocol\s+inbound\s+(all|ssh|telnet)", re.I), "线路允许的接入协议"),
    (re.compile(r"transport input ssh", re.I), "线路只允许 SSH 接入"),
    (re.compile(r"idle-timeout\s+(\d+)", re.I), "空闲超时自动登出（分钟）"),
    (re.compile(r"^(set authentication password|password)\s", re.I), "设置线路密码"),

    # ---- VLAN / 端口模式 ----
    (re.compile(r"^ ?name\s+(\S+)", re.I), "设置 VLAN 名称"),
    (re.compile(r"port\s+link-mode\s+(bridge|route)", re.I), "端口工作模式：bridge=二层 route=三层"),
    (re.compile(r"port\s+link-type\s+(trunk|access|hybrid)", re.I), "设置端口链路类型"),
    (re.compile(r"switchport\s+mode\s+(trunk|access)", re.I), "设置端口链路类型"),
    (re.compile(r"port\s+default\s+vlan\s+(\d+)", re.I), "端口划入 VLAN（H3C）"),
    (re.compile(r"port\s+access\s+vlan\s+(\d+)", re.I), "端口划入 VLAN"),
    (re.compile(r"switchport\s+access\s+vlan\s+(\d+)", re.I), "端口划入 VLAN"),
    (re.compile(r"switchport\s+trunk\s+allowed\s+vlan\s+(add\s+)?(.+)", re.I), "Trunk 放行 VLAN"),
    (re.compile(r"port\s+trunk\s+(pvid\s+vlan|permit\s+vlan)\s+(.+)", re.I), "Trunk 放行 VLAN"),
    (re.compile(r"undo\s+port\s+trunk\s+permit\s+vlan\s+(\d+)", re.I), "Trunk 移除 VLAN 放行"),
    (re.compile(r"port\s+trunk\s+encapsulation\s+dot1q", re.I), "Trunk 封装 802.1Q"),
    (re.compile(r"^(shutdown)$", re.I), "手工关闭端口"),
    (re.compile(r"^(undo shutdown|no shutdown)$", re.I), "启用端口"),

    # ---- 三层 / 路由 ----
    (re.compile(r"ip\s+address\s+(\S+\s+\S+|\S+/\d+)", re.I), "配置接口 IP 地址"),
    (re.compile(r"undo\s+ip\s+address", re.I), "删除接口 IP 地址"),
    (re.compile(r"ip\s+route-static\s+(\S+)\s+(\S+)\s+(\S+)", re.I), "配置静态路由（目的网段+掩码+下一跳）"),
    (re.compile(r"ip\s+route\s+(\S+)\s+(\S+)\s+(\S+)", re.I), "配置静态路由（IOS 派系）"),
    (re.compile(r"ip\s+route-static\s+0\.0\.0\.0\s+0\.0\.0\.0", re.I), "配置默认路由"),
    (re.compile(r"ip\s+route\s+0\.0\.0\.0\s+0\.0\.0\.0", re.I), "配置默认路由（IOS 派系）"),
    (re.compile(r"^ospf\s+(\d+)", re.I), "创建 OSPF 进程"),
    (re.compile(r"^router\s+(ospf|bgp)\s*(\S*)", re.I), "进入动态路由进程"),
    (re.compile(r"network\s+(\S+)\s+(\S+|0\.0\.0\.\d+)", re.I), "OSPF 宣告网段"),
    (re.compile(r"area\s+(\d+)", re.I), "进入 OSPF 区域"),
    (re.compile(r"^bgp\s+(\d+)", re.I), "启动 BGP 进程（AS 号）"),
    (re.compile(r"peer\s+(\S+)\s+as-number\s+(\d+)", re.I), "BGP 指定邻居"),
    (re.compile(r"neighbor\s+(\S+)\s+remote-as\s+(\d+)", re.I), "BGP 指定邻居"),

    # ---- 安全 ----
    (re.compile(r"acl\s+(number\s+)?(\d+)", re.I), "创建 ACL"),
    (re.compile(r"access-list\s+(\w+)\s+(\d+)", re.I), "创建 ACL（IOS 派系）"),
    (re.compile(r"rule\s+(permit|deny)", re.I), "ACL 规则：允许/拒绝"),
    (re.compile(r"permit\s+.*source\s+(\S+)", re.I), "ACL 规则：允许源地址"),
    (re.compile(r"deny\s+.*source\s+(\S+)", re.I), "ACL 规则：拒绝源地址"),
    (re.compile(r"packet-filter\s+(\S+)\s+(inbound|outbound)", re.I), "在接口应用 ACL"),
    (re.compile(r"ip\s+access-group\s+(\S+)\s+(in|out)", re.I), "在接口应用 ACL（IOS 派系）"),
    (re.compile(r"port-security\s+enable", re.I), "开启端口安全"),
    (re.compile(r"port-security\s+(max-mac-count|maximum)\s+(\d+)", re.I), "端口最大 MAC 数（防私接）"),
    (re.compile(r"port-security\s+protect-action\s+(restrict|shutdown)", re.I), "违规处理动作"),
    (re.compile(r"am\s+ip-mac\s+binding\s+(\S+)", re.I), "IP+MAC 绑定"),
    (re.compile(r"ip\s+source\s+guard\s+ip-address", re.I), "IP 源防欺骗（绑定）"),
    (re.compile(r"arp\s+detection\s+enable", re.I), "开启 ARP 检测"),
    (re.compile(r"^(stp|spanning-tree)", re.I), "生成树相关配置"),
    (re.compile(r"undo\s+stp\s+enable|no\s+spanning-tree", re.I), "关闭端口生成树（边缘口用）"),
    (re.compile(r"stp\s+edged-port\s+enable", re.I), "设为边缘端口（接电脑，加速收敛）"),
    (re.compile(r"bpdu-protection", re.I), "BPDU 保护（边缘口收到 BPDU 即关闭）"),
    (re.compile(r"(broadcast-suppression|storm-control)\s+(\S+)", re.I), "风暴抑制：限制广播/组播/单播"),
    (re.compile(r"loopback-detect(ion)?\s+enable", re.I), "开启环路检测"),

    # ---- 链路聚合 ----
    (re.compile(r"^(interface\s+)?(Bridge-Aggregation|eth-trunk|Port-channel|agg)\s*(\d+)?", re.I), "进入链路聚合口"),
    (re.compile(r"port\s+link-aggregation\s+group\s+(\d+)", re.I), "把端口加入聚合组"),
    (re.compile(r"channel-group\s+(\d+)", re.I), "把端口加入聚合组（IOS 派系）"),
    (re.compile(r"lacp\s+enable|mode\s+lacp", re.I), "聚合使用 LACP 动态协商"),

    # ---- 网络服务 ----
    (re.compile(r"^ ?dhcp\s+enable", re.I), "全局开启 DHCP"),
    (re.compile(r"dhcp\s+select\s+(relay|server|global)", re.I), "接口 DHCP 模式"),
    (re.compile(r"dhcp\s+relay\s+server-address\s+(\S+)", re.I), "DHCP 中继指向服务器"),
    (re.compile(r"ip\s+helper-address\s+(\S+)", re.I), "DHCP 中继指向服务器（IOS 派系）"),
    (re.compile(r"ntp-service\s+unicast-server\s+(\S+)|ntp\s+server\s+(\S+)", re.I), "NTP 时间同步服务器"),
    (re.compile(r"snmp-agent\s+community\s+(read|write)", re.I), "SNMP 团体字"),
    (re.compile(r"snmp-agent\s+sys-info\s+version\s+(\S+)", re.I), "SNMP 版本"),
    (re.compile(r"snmp-server\s+community\s+(\S+)", re.I), "SNMP 团体字（IOS 派系）"),
    (re.compile(r"info-center\s+loghost\s+(\S+)|logging\s+host\s+(\S+)", re.I), "日志外送服务器"),

    # ---- 堆叠 ----
    (re.compile(r"irf\s+(member|domain|priority)", re.I), "IRF 堆叠成员/域/优先级"),
    (re.compile(r"^stack$|^virtual-system", re.I), "进入堆叠配置"),

    # ---- 保存 ----
    (re.compile(r"^save(\s+\S+)?$", re.I), "保存配置到存储介质"),
    (re.compile(r"^write(\s+memory)?$", re.I), "保存配置（IOS 派系）"),
    (re.compile(r"copy\s+running-config\s+startup-config", re.I), "保存配置到启动文件"),
]

# 视图切换行（进入/退出视图），渲染时用不同底色高亮
_VIEW_RE = re.compile(
    r"^(system-view|sys$|configure terminal|conf t|interface\s+\S+|vlan\s+\d+|quit$|exit$|end$|return$)",
    re.I)
# 注释行（整行就是注释的），渲染时整行弱化
_COMMENT_LINE_RE = re.compile(r"^\s*(#|!|//)")


def note_of(line: str):
    """单条命令 → 中文注释；无匹配返回 None"""
    s = line.strip()
    if not s or _COMMENT_LINE_RE.match(s):
        return None
    for pat, note in _RULES:
        if pat.search(s):
            return note
    return None


def is_view_line(line: str) -> bool:
    """是否为视图切换行（高亮用）"""
    return bool(_VIEW_RE.match(line.strip()))


def annotate_config(text: str, colors: dict = None) -> str:
    """纯命令配置 → 带中文注释的 HTML（供 QTextEdit 预览渲染）
    colors: 可覆盖默认配色 {cmd, view, note, comment}
    """
    c = {"cmd": "#C8D3E8", "view": "#7EE0A3", "note": "#7C93B8", "comment": "#55617A"}
    c.update(colors or {})
    out = ["<html><body>"]
    for raw in text.splitlines() or [""]:
        s = raw.rstrip()
        if not s.strip():
            out.append("<div>&nbsp;</div>")
            continue
        esc = html.escape(s, quote=False)
        if _COMMENT_LINE_RE.match(s):
            out.append(f'<div style="color:{c["comment"]}">{esc}</div>')
            continue
        note = note_of(s)
        if note:
            span = (f'<span style="color:{c["note"]}">'
                    f'  # {html.escape(note, quote=False)}</span>')
        else:
            span = ""
        color = c["view"] if is_view_line(s) else c["cmd"]
        out.append(f'<div style="color:{color}">{esc}{span}</div>')
    out.append("</body></html>")
    return "".join(out)


def annotate_text(text: str) -> str:
    """纯命令配置 → 带注释的纯文本（导出 md 用）"""
    lines = []
    for raw in text.splitlines():
        s = raw.rstrip()
        note = note_of(s)
        lines.append(f"{s}  # {note}" if (note and s.strip()) else s)
    return "\n".join(lines)


def strip_notes(text: str) -> str:
    """带注释文本 → 纯命令（剥掉行尾 `# ...` 注释；保护原命令中合法的 # 使用）
    仅当 # 前有 ≥2 空格且不是行首时视为注释分隔"""
    out = []
    for raw in text.splitlines():
        m = re.match(r"^(.*?)\s{2,}#(?!/).*$", raw)
        out.append(m.group(1).rstrip() if m else raw)
    return "\n".join(out)


# ---------------------------------------------------------------- 自测
if __name__ == "__main__":
    demo = """#
 sysname Access-SW-01
#
interface GigabitEthernet1/0/1
 port link-mode bridge
 port link-type trunk
 port trunk permit vlan 10 20
#
interface Vlan-interface10
 ip address 192.168.10.1 255.255.255.0
#
ip route-static 0.0.0.0 0.0.0.0 192.168.10.254
ssh server enable
local-user admin
 password cipher Admin@123
 service-type ssh
user-interface vty 0 4
 authentication-mode scheme
save
"""
    for ln in demo.splitlines():
        s = ln.rstrip()
        if not s.strip():
            continue
        n = note_of(s)
        print(f"{s:<55} {('# ' + n) if n else ''}")
    print("view 行高亮:", [s for s in demo.splitlines() if is_view_line(s)])
    back = strip_notes(annotate_text(demo))
    assert strip_notes(annotate_text(demo)).splitlines()[1].strip() == "sysname Access-SW-01"
    print("strip_notes 回到纯命令 OK")
