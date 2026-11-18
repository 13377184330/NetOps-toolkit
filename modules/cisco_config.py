#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
思科 Catalyst IOS 交换机配置生成器

语法来源：IOS 15.x 公开标准语法，关键差异点与「五厂商对照」系列
（链路聚合 port-channel/风暴控制 level 百分比/STP portfast·guard/端口安全
switchport port-security/ACL ip access-list + ip access-group/MSTP/SNMP·NTP·syslog）
交叉核验。消费与华为版生成器完全同构的 config dict，页签层零字段适配。
"""
import re
from utils.net_addr import bgp_network_line


def _parse_timezone(timezone):
    """`UTC+8`/`UTC-5` → (名称, 偏移小时)，供 IOS `clock timezone NAME HOURS` 使用。
    解析逻辑复用公共函数，越界偏移标 _CHECK 并回退 0，避免生成非法命令。
    """
    from utils.net_addr import parse_timezone
    name, hours, valid = parse_timezone(timezone)
    return name if valid else f"{name}_CHECK", hours if valid else 0


class CiscoBasicGenerator:
    """思科基础配置生成器"""

    @staticmethod
    def generate_hostname(hostname):
        return f"hostname {hostname}"

    @staticmethod
    def generate_password(password, encrypted=False):
        if encrypted:
            return f"enable secret 5 {password}"
        return f"enable password {password}"

    @staticmethod
    def generate_user(username, password, level=15, encrypted=False):
        priv_level = "15" if int(level) >= 15 else str(level)
        kw = "secret" if encrypted else "password"
        return f"username {username} privilege {priv_level} {kw} {password}"

    @staticmethod
    def generate_mgmt_interface(interface, ip, mask, gateway=None):
        lines = [
            f"interface {interface}",
            f" ip address {ip} {mask}",
            " no shutdown",
            "!"
        ]
        if gateway:
            lines.append(f"ip default-gateway {gateway}")
        return "\n".join(lines)

    @staticmethod
    def generate_ssh(ssh_version=2, port=22, timeout=60, max_auth=5, domain="local"):
        # IOS 的 RSA 密钥生成依赖 domain-name；SVC 系交换机无全局改 SSH 端口的
        # 通用命令（rotary 属路由器方案），非 22 端口只给提示不给伪命令
        lines = [
            f"ip domain-name {domain}",
            f"crypto key generate rsa modulus 2048",
            f"ip ssh version {ssh_version}",
            f"ip ssh time-out {timeout}",
            f"ip ssh authentication-retries {max_auth}",
            "!",
            "line vty 0 4",
            " transport input ssh",
            " login local",
            "!"
        ]
        if port and int(port) != 22:
            lines.append(f"! 注：IOS 交换机无全局改 SSH 端口通用命令（当前期望端口 {port}），默认 22")
        return "\n".join(lines)

    @staticmethod
    def generate_telnet():
        return """line vty 0 4
 transport input telnet
 login local
!"""

    @staticmethod
    def generate_ntp(servers, timezone="UTC+8"):
        lines = []
        for server in servers:
            prefer = " prefer" if server.get("prefer") else ""
            lines.append(f"ntp server {server['ip']}{prefer}")
        if timezone:
            # IOS clock timezone 需要「名称 + 整数偏移小时」两个参数（如
            # `clock timezone CST 8`）；GUI 值是 `UTC+8` 字符串，原实现直接
            # 拼成 `clock timezone UTC+8`（缺参数，设备拒绝）。解析 ±N 补偏移。
            name, hours = _parse_timezone(timezone)
            lines.append(f"clock timezone {name} {hours}")
        return "\n".join(lines)

    @staticmethod
    def generate_snmp(version="2c", community_read=None, community_write=None,
                      location=None, contact=None, trap_enable=False, trap_host=None):
        lines = []
        # community（v2c）只在 v2c/all 下生成；v3 用基于用户的安全模型，
        # 不能输出 snmp-server community —— 与华为版 version 分流保持一致。
        ver = str(version).lower()
        if ver in ("v1", "v2", "v2c", "all", "1", "2", "2c"):
            if community_read:
                lines.append(f"snmp-server community {community_read} ro")
            if community_write:
                lines.append(f"snmp-server community {community_write} rw")
        elif ver == "v3":
            lines.append("! 注：SNMPv3 需配置 snmp-server user/group/view（GUI 暂不采集这些字段），请手工补充")
        if location:
            lines.append(f"snmp-server location {location}")
        if contact:
            lines.append(f"snmp-server contact {contact}")
        if trap_enable and trap_host:
            lines.append(f"snmp-server host {trap_host} traps")
            lines.append("snmp-server enable traps")
        return "\n".join(lines)

    @staticmethod
    def generate_logging(host, level="informational"):
        return f"""logging host {host}
logging trap {level}
!"""

    @staticmethod
    def generate_banner(motd=None, login=None):
        lines = []
        if motd:
            lines.append(f"banner motd #\n{motd}\n#")
        if login:
            lines.append(f"banner login #\n{login}\n#")
        return "\n".join(lines)

    @staticmethod
    def generate_dns(servers, domain=None):
        lines = []
        for server in servers:
            lines.append(f"ip name-server {server}")
        if domain:
            lines.append(f"ip domain-name {domain}")
        return "\n".join(lines)

    @staticmethod
    def generate_basic_all(config):
        lines = ["!", "# 思科交换机基础配置", "!"]

        if "hostname" in config:
            lines.append(CiscoBasicGenerator.generate_hostname(config["hostname"]))
            lines.append("!")

        if "password" in config:
            pwd = config["password"]
            lines.append(CiscoBasicGenerator.generate_password(
                pwd["value"], pwd.get("encrypted", False)))
            lines.append("!")

        if "user" in config:
            user = config["user"]
            lines.append(CiscoBasicGenerator.generate_user(
                user["username"], user["password"],
                user.get("level", 15), user.get("encrypted", False)))
            lines.append("!")

        if "mgmt_interface" in config:
            mgmt = config["mgmt_interface"]
            lines.append(CiscoBasicGenerator.generate_mgmt_interface(
                mgmt["interface"], mgmt["ip_address"],
                mgmt["mask"], mgmt.get("gateway")))

        if config.get("enable_ssh"):
            domain = (config.get("dns", {}) or {}).get("domain") or "local"
            lines.append(CiscoBasicGenerator.generate_ssh(
                config.get("ssh_version", 2),
                config.get("ssh_port", 22),
                config.get("ssh_timeout", 60),
                config.get("ssh_max_auth_tries", 5),
                domain=domain))

        if config.get("enable_telnet"):
            lines.append(CiscoBasicGenerator.generate_telnet())
            lines.append("!")

        if "ntp" in config:
            lines.append(CiscoBasicGenerator.generate_ntp(
                config["ntp"]["servers"],
                config["ntp"].get("timezone", "UTC+8")))
            lines.append("!")

        if "snmp" in config:
            snmp = config["snmp"]
            lines.append(CiscoBasicGenerator.generate_snmp(
                snmp.get("version", "2c"),
                snmp.get("community_read"),
                snmp.get("community_write"),
                snmp.get("sys_location"),
                snmp.get("sys_contact"),
                snmp.get("trap_enable", False),
                snmp.get("trap_host")))
            lines.append("!")

        if "log" in config:
            log = config["log"]
            if log.get("host"):
                lines.append(CiscoBasicGenerator.generate_logging(
                    log["host"], log.get("log_level", "informational")))

        if "banner" in config:
            banner = config["banner"]
            lines.append(CiscoBasicGenerator.generate_banner(
                banner.get("motd"), banner.get("login")))
            lines.append("!")

        if "dns" in config:
            dns = config["dns"]
            lines.append(CiscoBasicGenerator.generate_dns(
                dns["servers"], dns.get("domain")))
            lines.append("!")

        lines.append("end")
        return "\n".join(lines)


class CiscoVLANGenerator:
    """思科 VLAN 配置生成器"""

    @staticmethod
    def generate_vlan(vlan_id, name=None):
        lines = [f"vlan {vlan_id}"]
        if name:
            lines.append(f" name {name}")
        lines.append("!")
        return "\n".join(lines)

    @staticmethod
    def generate_vlans(vlans):
        return "\n".join(CiscoVLANGenerator.generate_vlan(
            v["id"], v.get("name")) for v in vlans)

    @staticmethod
    def generate_interface(interface, vlan_type, vlan_id, trunk_vlans=None, pvid=None):
        lines = [f"interface {interface}"]
        if vlan_type == "access":
            lines.append(" switchport mode access")
            lines.append(f" switchport access vlan {vlan_id}")
        elif vlan_type == "trunk":
            lines.append(" switchport mode trunk")
            if trunk_vlans:
                vlans = " ".join(str(v) for v in trunk_vlans) if isinstance(trunk_vlans, (list, tuple)) else str(trunk_vlans)
                lines.append(f" switchport trunk allowed vlan {vlans}")
            if pvid:
                lines.append(f" switchport trunk native vlan {pvid}")
        elif vlan_type == "hybrid":
            # IOS 无 hybrid 端口类型：按 trunk 语义处理（NetCMD 五厂商对照同惯例）
            # hybrid 接口在 GUI 里既不设 vlan_id 也不设 trunk_vlans，原实现
            # 无条件拼 `allowed vlan {vlan_id}` 会输出非法字面量 `... None`。
            lines.append("! 注：IOS 无 hybrid 类型，已按 trunk 语义生成")
            lines.append(" switchport mode trunk")
            # hybrid 场景：trunk_vlans 为 tagged VLAN 列表，pvid 为 native VLAN。
            # 两者皆空时只输出 mode trunk，不生成 allowed/native 行（避免 None）。
            allowed = _vlans_str(trunk_vlans)
            if allowed:
                lines.append(f" switchport trunk allowed vlan {allowed}")
            if pvid:
                lines.append(f" switchport trunk native vlan {pvid}")
        lines.append(" no shutdown")
        lines.append("!")
        return "\n".join(lines)

    @staticmethod
    def generate_vlanif(vlan_id, ip, mask, description=None):
        lines = [
            f"interface vlan {vlan_id}",
            f" ip address {ip} {mask}"
        ]
        if description:
            lines.append(f" description {description}")
        lines.append(" no shutdown")
        lines.append("!")
        return "\n".join(lines)

    @staticmethod
    def generate_stp(mode="mstp", priority=32768, enable=True):
        # IOS 生成树模式名：pvst / rapid-pvst / mst（与页签 stp/rstp/mstp 映射）
        mode_map = {"stp": "pvst", "rstp": "rapid-pvst", "mstp": "mst"}
        ios_mode = mode_map.get(mode, mode)
        lines = []
        if enable:
            lines.append(f"spanning-tree mode {ios_mode}")
            if priority != 32768:
                lines.append(f"! 注：IOS 优先级按 VLAN 维度配置，如：spanning-tree vlan 1 priority {priority}")
        else:
            lines.append("! 注：IOS 无全局关闭生成树命令，请按 VLAN 维度 no spanning-tree vlan X")
        lines.append("!")
        return "\n".join(lines)


class CiscoRoutingGenerator:
    """思科路由配置生成器"""

    @staticmethod
    def generate_static_route(dest, mask, nexthop, preference=None):
        route = f"ip route {dest} {mask} {nexthop}"
        if preference:
            route += f" {preference}"   # IOS 管理距离直接跟在末位
        return route

    @staticmethod
    def generate_ospf(process_id, router_id, networks):
        lines = [f"router ospf {process_id}"]
        if router_id:
            lines.append(f" router-id {router_id}")
        for net in networks:
            lines.append(f" network {net['network']} {net['wildcard']} area {net['area']}")
        lines.append("!")
        return "\n".join(lines)

    @staticmethod
    def generate_bgp(as_number, router_id, peers, networks):
        lines = [f"router bgp {as_number}"]
        if router_id:
            lines.append(f" bgp router-id {router_id}")
        for peer in peers:
            lines.append(f" neighbor {peer['ip']} remote-as {peer['remote_as']}")
        for net in networks:
            lines.append(f" {bgp_network_line(net, style='ios')}")
        lines.append("!")
        return "\n".join(lines)

    @staticmethod
    def generate_rip(version=2, networks=None):
        lines = ["router rip", f" version {version}"]
        for network in networks or []:
            lines.append(f" network {network}")
        lines.append("!")
        return "\n".join(lines)


class CiscoSecurityGenerator:
    """思科安全配置生成器"""

    @staticmethod
    def generate_acl(number, rules, description=None, acl_type="extended"):
        lines = [f"ip access-list {acl_type} {number}"]
        if description:
            lines.append(f" remark {description}")
        for rule in rules:
            action = rule.get("action", "permit")
            # IOS 标准 ACL 只能按源地址过滤，不允许协议/目的/端口。
            # GUI 的 standard 规则 protocol/destination 均为 None，经 _acl_rules
            # 兜底成 ip/any 后会生成 `permit ip <src> <wc> any`——设备整行拒绝。
            if str(acl_type).lower() in ("standard", "std"):
                src = rule.get("source") or "any"
                src_wc = rule.get("src_wildcard") or ""
                line = f" {action} {src}"
                if src != "any" and src_wc:
                    line += f" {src_wc}"
                lines.append(line)
                continue
            proto = rule.get("protocol") or "ip"
            src = rule.get("source") or "any"
            src_wc = rule.get("src_wildcard") or ""
            dst = rule.get("dest") or "any"
            dst_wc = rule.get("dst_wildcard") or ""
            port = rule.get("port") or ""
            line = f" {action} {proto}"
            if src != "any":
                line += f" {src}"
                if src_wc:
                    line += f" {src_wc}"
            else:
                line += " any"
            if dst != "any":
                line += f" {dst}"
                if dst_wc:
                    line += f" {dst_wc}"
            else:
                line += " any"
            if port and proto in ["tcp", "udp"]:
                line += f" eq {port}"
            lines.append(line)
        lines.append("!")
        return "\n".join(lines)

    @staticmethod
    def generate_port_security(interface, max_mac=1, violation="shutdown", sticky=False):
        lines = [
            f"interface {interface}",
            " switchport port-security",
            f" switchport port-security maximum {max_mac}",
            f" switchport port-security violation {violation}"
        ]
        if sticky:
            lines.append(" switchport port-security mac-address sticky")
        lines.append("!")
        return "\n".join(lines)

    @staticmethod
    def generate_traffic_filter(interface, acl_number, direction="in"):
        # 页签方向值 inbound/outbound → IOS in/out
        d = str(direction).lower().replace("bound", "") or "in"
        return f"""interface {interface}
 ip access-group {acl_number} {d}
!"""

    @staticmethod
    def generate_dhcp_snooping(enable=True, trusted_ports=None, vlan=None):
        if not enable:
            return "no ip dhcp snooping\n!"
        lines = ["ip dhcp snooping"]
        if vlan:
            lines.append(f"ip dhcp snooping vlan {vlan}")
        for port in trusted_ports or []:
            lines.append(f"interface {port}")
            lines.append(" ip dhcp snooping trust")
        lines.append("!")
        return "\n".join(lines)

    @staticmethod
    def generate_arp_inspection(vlans=None, trusted_ports=None):
        lines = []
        if vlans:
            lines.append(f"ip arp inspection vlan {' '.join(map(str, vlans))}")
        for port in trusted_ports or []:
            lines.append(f"interface {port}")
            lines.append(" ip arp inspection trust")
        if lines:
            lines.append("!")
            return "\n".join(lines)
        return ""

    @staticmethod
    def generate_storm_control(interface, broadcast=None, multicast=None, unicast=None):
        # 五厂商对照实锤：GUI 该字段标签为「广播(pps)/(组播(pps))」，
        # 值是每秒包数；IOS storm-control level 裸数字才是百分比(0-100)，
        # 直接把 pps 填进去会生成 level 5000 这类设备拒绝的命令。
        # IOS 支持 `storm-control ... level pps <pps>` 精确表达 pps 语义。
        lines = [f"interface {interface}"]
        if broadcast:
            lines.append(f" storm-control broadcast level pps {broadcast}")
        if multicast:
            lines.append(f" storm-control multicast level pps {multicast}")
        if unicast:
            lines.append(f" storm-control unicast level pps {unicast}")
        lines.append("!")
        return "\n".join(lines)


class CiscoInterfaceGenerator:
    """思科接口配置生成器"""

    @staticmethod
    def generate_eth_trunk(trunk_id, mode="lacp", members=None, description=None,
                           trunk_vlans=None, native_vlan=None, lacp=True):
        """思科 Port-Channel（五厂商对照实锤）：成员口 channel-group N mode active/on"""
        lines = [f"interface port-channel {trunk_id}"]
        if description:
            lines.append(f" description {description}")
        lines.append(f" switchport mode {mode}")
        if trunk_vlans:
            vlans = " ".join(str(v) for v in trunk_vlans) if isinstance(trunk_vlans, (list, tuple)) else str(trunk_vlans)
            lines.append(f" switchport trunk allowed vlan {vlans}")
        if native_vlan:
            lines.append(f" switchport trunk native vlan {native_vlan}")
        lines.append("!")
        if members:
            for member in members:
                lines.append(f"interface {member}")
                lines.append(f" channel-group {trunk_id} mode active" if lacp else f" channel-group {trunk_id} mode on")
                lines.append("!")
        return "\n".join(lines)

    @staticmethod
    def generate_lldp(enable=True, mode="both", interval=30, holdtime=120):
        lines = []
        if enable:
            lines.append("lldp run")
            lines.append(f"lldp timer {interval}")
            lines.append(f"lldp holdtime {holdtime}")
        else:
            lines.append("no lldp run")
        lines.append("!")
        return "\n".join(lines)

    @staticmethod
    def generate_loop_detect(enable=True, interval=5, action="shutdown"):
        # IOS 无 loopback-detection 命令：语义等价物是 STP loop guard（全局默认开启）
        lines = []
        if enable:
            lines.append("spanning-tree loopguard default")
            lines.append(f"! 注：IOS 无 loopback-detection，已按 loop guard 语义生成（检测间隔 {interval}s 为华为概念）")
        else:
            lines.append("no spanning-tree loopguard default")
        lines.append("!")
        return "\n".join(lines)

    @staticmethod
    def generate_poe(interface=None, enable=True, priority="low", power=None):
        lines = []
        if interface:
            lines.append(f"interface {interface}")
            if enable:
                lines.append(" power inline auto")
                if priority:
                    lines.append(f" power inline port priority {priority}")
                if power:
                    lines.append(f" power inline auto max {power}")
            else:
                lines.append(" power inline never")
            lines.append("!")
        else:
            lines.append("! 注：Cisco PoE 默认全局使能，无全局开关命令；端口级用 power inline auto/never")
        return "\n".join(lines)

    @staticmethod
    def generate_rate_limit(interface, rate_in=None, rate_out=None):
        # GUI 入口限速单位是 kbps（SpinBox suffix="kbps"），IOS rate-limit
        # 命令用 bps。原实现把 kbps 塞进 storm-control level（百分比语义），
        # 既单位错又命令错。改用 CAR：`rate-limit {in|out} <bps> <burst> <burst>
        # conform-action transmit exceed-action drop`，kbps×1000 换算。
        lines = [f"interface {interface}"]
        def _car(direction, kbps):
            # 外部 JSON 恢复的限速值可能是字符串（含小数），int() 会抛
            # ValueError 崩到生成线程；用 float 中转并兜底。
            try:
                bps = int(float(kbps)) * 1000
            except (ValueError, TypeError):
                return f" ! 注：限速值「{kbps}」无法解析，已跳过该方向"
            burst = max(bps // 8, 1500)  # 约 1 秒突发量，下限一个以太网帧
            return (f" rate-limit {direction} {bps} {burst} {burst} "
                    "conform-action transmit exceed-action drop")
        if rate_in:
            lines.append(_car("input", rate_in))
        if rate_out:
            lines.append(_car("output", rate_out))
        lines.append("!")
        return "\n".join(lines)


# ================================================================ 页签级聚合
# 与华为侧 VLANConfigGenerator.generate_vlan_all 等消费同一 config dict，
# 页签层零字段适配即可按厂商取用。

def _acl_rules(rules):
    """页签 ACL 规则字段 → 思科生成器字段（None → any/ip 兜底）"""
    return [{
        "action": r.get("action", "permit"),
        "protocol": r.get("protocol") or "ip",
        "source": r.get("source") or "any",
        "src_wildcard": r.get("source_wildcard") or "",
        "dest": r.get("destination") or "any",
        "dst_wildcard": r.get("destination_wildcard") or "",
        "port": r.get("dest_port") or "",
    } for r in rules]


def _vlans_str(v):
    if v is None:
        return None
    return " ".join(str(x) for x in v) if isinstance(v, (list, tuple)) else str(v)


def generate_vlan_all(config: dict) -> str:
    """消费 VLAN 页签 config dict（vlans/interfaces/vlanifs/stp）"""
    parts = []
    if "vlans" in config:
        parts.append(CiscoVLANGenerator.generate_vlans(config["vlans"]))
    if "interfaces" in config:
        parts.append("\n".join(CiscoVLANGenerator.generate_interface(
            i["interface"], i.get("type", "access"), i.get("vlan_id"),
            i.get("trunk_vlans"), i.get("pvid"))
            for i in config["interfaces"]))
    if "vlanifs" in config:
        parts.append("\n".join(CiscoVLANGenerator.generate_vlanif(
            v["vlan_id"], v["ip_address"], v.get("mask", "255.255.255.0"), v.get("description"))
            for v in config["vlanifs"]))
    if "stp" in config:
        s = config["stp"]
        parts.append(CiscoVLANGenerator.generate_stp(
            s.get("mode", "mstp"), s.get("priority", 32768), s.get("enable", True)))
    return "\n".join(p for p in parts if p)


def generate_route_all(config: dict) -> str:
    """消费路由页签 config dict（static_routes/ospf/bgp/rip）"""
    parts = []
    for r in config.get("static_routes", []):
        parts.append(CiscoRoutingGenerator.generate_static_route(
            r["dest_network"], r["mask"],
            r.get("next_hop") or r.get("interface"), r.get("preference")))
    if "ospf" in config:
        o = config["ospf"]
        nets = [{"network": n["address"], "wildcard": n.get("mask", "0.0.0.255"),
                 "area": o.get("area_id", "0")} for n in o.get("networks", [])]
        parts.append(CiscoRoutingGenerator.generate_ospf(
            o.get("process_id", 1), o.get("router_id"), nets))
    if "bgp" in config:
        b = config["bgp"]
        peers = [{"ip": p["ip"], "remote_as": p["as"]} for p in b.get("peers", [])]
        parts.append(CiscoRoutingGenerator.generate_bgp(
            b["as_number"], b.get("router_id"), peers, b.get("networks", [])))
    if "rip" in config:
        rip = config["rip"]
        parts.append(CiscoRoutingGenerator.generate_rip(
            rip.get("version", 2), rip.get("networks", [])))
    return "\n".join(p for p in parts if p)


def generate_security_all(config: dict) -> str:
    """消费安全页签 config dict（acls/port_security/traffic_filters/dhcp_snooping/arp_inspection/storm_controls）"""
    parts = []
    for acl in config.get("acls", []):
        parts.append(CiscoSecurityGenerator.generate_acl(
            acl["number"], _acl_rules(acl.get("rules", [])),
            acl.get("description"), acl_type=acl.get("type", "extended")))
    for ps in config.get("port_security", []):
        parts.append(CiscoSecurityGenerator.generate_port_security(
            ps["interface"], ps.get("max_mac", 1), ps.get("action", "shutdown"),
            ps.get("sticky", False)))
    for tf in config.get("traffic_filters", []):
        parts.append(CiscoSecurityGenerator.generate_traffic_filter(
            tf["interface"], tf["acl_number"], tf.get("direction", "in")))
    if "dhcp_snooping" in config:
        ds = config["dhcp_snooping"]
        parts.append(CiscoSecurityGenerator.generate_dhcp_snooping(
            ds.get("enable", True), ds.get("trusted_ports"), ds.get("vlan")))
    if "arp_inspection" in config:
        ai = config["arp_inspection"]
        parts.append(CiscoSecurityGenerator.generate_arp_inspection(
            ai.get("vlans"), ai.get("trusted_ports")))
    if "storm_controls" in config:
        # GUI 风暴抑制值为 pps，生成器已用 IOS `storm-control ... level pps` 精确表达
        for st in config.get("storm_controls", []):
            parts.append(CiscoSecurityGenerator.generate_storm_control(
                st["interface"], st.get("broadcast"), st.get("multicast"), st.get("unicast")))
    if "anti_attack" in config:
        # IOS 无华为 anti-attack 体系，不自动翻译，防静默漏配
        parts.append(f"# 反攻击功能（类型 {config['anti_attack'].get('type', 'all')}）"
                     "请按思科安全特性（CoPP/端口安全/DAI）核对后手工补充")
    return "\n".join(p for p in parts if p)


def generate_interface_all(config: dict) -> str:
    """消费接口页签 config dict（eth_trunks/lldp/loopback_detection/poe/rate_limits）"""
    parts = []
    for t in config.get("eth_trunks", []):
        tab_mode = t.get("mode", "lacp-static")
        parts.append(CiscoInterfaceGenerator.generate_eth_trunk(
            t["trunk_id"], t.get("port_link_type", "trunk"),
            t.get("member_ports"), t.get("description"),
            t.get("trunk_vlans"), t.get("native_vlan"),
            lacp=("lacp" in tab_mode)))
    if "lldp" in config:
        l = config["lldp"]
        parts.append(CiscoInterfaceGenerator.generate_lldp(
            l.get("enable", True), l.get("mode", "both"),
            l.get("interval", 30), l.get("holdtime", 120)))
    if "loopback_detection" in config:
        ld = config["loopback_detection"]
        parts.append(CiscoInterfaceGenerator.generate_loop_detect(
            ld.get("enable", True), ld.get("interval", 5), ld.get("action", "shutdown")))
    if "poe" in config:
        p = config["poe"]
        parts.append(CiscoInterfaceGenerator.generate_poe(
            None, p.get("enable", True), None, p.get("max_power")))
        for i in p.get("interfaces", []):
            parts.append(CiscoInterfaceGenerator.generate_poe(
                i["interface"], i.get("enable", True), i.get("priority"), i.get("max_power")))
    for rl in config.get("rate_limits", []):
        parts.append(CiscoInterfaceGenerator.generate_rate_limit(
            rl["interface"], rl.get("cir_in"), rl.get("cir_out")))
    return "\n".join(p for p in parts if p)
