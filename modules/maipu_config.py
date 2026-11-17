#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
迈普交换机配置生成器
"""


class MaipuBasicGenerator:
    """迈普基础配置生成器"""
    
    @staticmethod
    def generate_hostname(hostname):
        return f"hostname {hostname}"
    
    @staticmethod
    def generate_password(password, encrypted=False):
        if encrypted:
            return f"enable password 5 {password}"
        return f"enable password {password}"
    
    @staticmethod
    def generate_user(username, password, level=15, encrypted=False):
        lines = []
        priv_level = "15" if level >= 15 else str(level)
        if encrypted:
            lines.append(f"username {username} privilege {priv_level} password 5 {password}")
        else:
            lines.append(f"username {username} privilege {priv_level} password {password}")
        return "\n".join(lines)
    
    @staticmethod
    def generate_mgmt_interface(interface, ip, mask, gateway=None):
        lines = [
            f"interface {interface}",
            f" ip address {ip} {mask}",
            " no shutdown",
            "!"
        ]
        if gateway:
            lines.append(f"ip route 0.0.0.0 0.0.0.0 {gateway}")
            lines.append("!")
        return "\n".join(lines)
    
    @staticmethod
    def generate_ssh(ssh_version=2, port=22, timeout=60, max_auth=5):
        lines = [
            f"ip ssh version {ssh_version}",
            f"ip ssh port {port}",
            f"ip ssh timeout {timeout}",
            f"ip ssh authentication-retries {max_auth}",
            "crypto key generate rsa",
            "!",
            "line vty 0 15",
            " transport input ssh",
            " login local",
            "!"
        ]
        return "\n".join(lines)
    
    @staticmethod
    def generate_telnet():
        return """line vty 0 15
 transport input telnet
 login local
!"""
    
    @staticmethod
    def generate_ntp(servers, timezone="UTC+8"):
        lines = []
        for server in servers:
            prefer = "prefer" if server.get("prefer") else ""
            lines.append(f"ntp server {server['ip']} {prefer}")
        lines.append(f"clock timezone {timezone}")
        return "\n".join(lines)
    
    @staticmethod
    def generate_snmp(version="2c", community_read=None, community_write=None,
                     location=None, contact=None, trap_enable=False, trap_host=None):
        lines = [f"snmp-server version {version}"]
        
        if community_read:
            lines.append(f"snmp-server community {community_read} ro")
        if community_write:
            lines.append(f"snmp-server community {community_write} rw")
        if location:
            lines.append(f"snmp-server location {location}")
        if contact:
            lines.append(f"snmp-server contact {contact}")
        if trap_enable and trap_host:
            lines.append(f"snmp-server host {trap_host} traps")
        
        return "\n".join(lines)
    
    @staticmethod
    def generate_logging(host, level="informational"):
        return f"""logging host {host}
logging trap {level}
logging enable
!"""
    
    @staticmethod
    def generate_banner(motd=None, login=None):
        lines = []
        if motd:
            lines.append(f"banner motd ^\n{motd}\n^")
        if login:
            lines.append(f"banner login ^\n{login}\n^")
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
        lines = ["!", "# 迈普交换机基础配置", "!"]
        
        if "hostname" in config:
            lines.append(MaipuBasicGenerator.generate_hostname(config["hostname"]))
            lines.append("!")
        
        if "password" in config:
            pwd = config["password"]
            lines.append(MaipuBasicGenerator.generate_password(
                pwd["value"], pwd.get("encrypted", False)
            ))
            lines.append("!")
        
        if "user" in config:
            user = config["user"]
            lines.append(MaipuBasicGenerator.generate_user(
                user["username"], user["password"],
                user.get("level", 15), user.get("encrypted", False)
            ))
            lines.append("!")
        
        if "mgmt_interface" in config:
            mgmt = config["mgmt_interface"]
            lines.append(MaipuBasicGenerator.generate_mgmt_interface(
                mgmt["interface"], mgmt["ip_address"],
                mgmt["mask"], mgmt.get("gateway")
            ))
        
        if config.get("enable_ssh"):
            lines.append(MaipuBasicGenerator.generate_ssh(
                config.get("ssh_version", 2),
                config.get("ssh_port", 22),
                config.get("ssh_timeout", 60),
                config.get("ssh_max_auth_tries", 5)
            ))
        
        if config.get("enable_telnet"):
            lines.append(MaipuBasicGenerator.generate_telnet())
            lines.append("!")
        
        if "ntp" in config:
            lines.append(MaipuBasicGenerator.generate_ntp(
                config["ntp"]["servers"],
                config["ntp"].get("timezone", "UTC+8")
            ))
            lines.append("!")
        
        if "snmp" in config:
            snmp = config["snmp"]
            lines.append(MaipuBasicGenerator.generate_snmp(
                snmp.get("version", "2c"),
                snmp.get("community_read"),
                snmp.get("community_write"),
                snmp.get("sys_location"),
                snmp.get("sys_contact"),
                snmp.get("trap_enable", False),
                snmp.get("trap_host")
            ))
            lines.append("!")
        
        if "log" in config:
            log = config["log"]
            if log.get("host"):
                lines.append(MaipuBasicGenerator.generate_logging(
                    log["host"], log.get("log_level", "informational")
                ))
        
        if "banner" in config:
            banner = config["banner"]
            lines.append(MaipuBasicGenerator.generate_banner(
                banner.get("motd"), banner.get("login")
            ))
            lines.append("!")
        
        if "dns" in config:
            dns = config["dns"]
            lines.append(MaipuBasicGenerator.generate_dns(
                dns["servers"], dns.get("domain")
            ))
            lines.append("!")
        
        lines.append("end")
        return "\n".join(lines)


class MaipuVLANGenerator:
    """迈普VLAN配置生成器"""
    
    @staticmethod
    def generate_vlan(vlan_id, name=None):
        lines = [f"vlan {vlan_id}"]
        if name:
            lines.append(f" name {name}")
        lines.append("!")
        return "\n".join(lines)
    
    @staticmethod
    def generate_vlans(vlans):
        lines = []
        for vlan in vlans:
            lines.append(MaipuVLANGenerator.generate_vlan(
                vlan["id"], vlan.get("name")
            ))
        return "\n".join(lines)
    
    @staticmethod
    def generate_interface(interface, vlan_type, vlan_id, trunk_vlans=None, pvid=None):
        lines = [f"interface {interface}"]
        
        if vlan_type == "access":
            lines.append(" switchport mode access")
            lines.append(f" switchport access vlan {vlan_id}")
        elif vlan_type == "trunk":
            lines.append(" switchport mode trunk")
            if trunk_vlans:
                if trunk_vlans == "all":
                    lines.append(" switchport trunk allowed vlan all")
                else:
                    lines.append(f" switchport trunk allowed vlan {trunk_vlans}")
            if pvid:
                lines.append(f" switchport trunk native vlan {pvid}")
        elif vlan_type == "hybrid":
            lines.append(" switchport mode hybrid")
            lines.append(f" switchport hybrid vlan {vlan_id}")
        
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
    def generate_stp(mode="rstp", priority=32768, enable=True):
        lines = []
        if enable:
            lines.append("spanning-tree enable")
            lines.append(f"spanning-tree mode {mode}")
            if priority != 32768:
                lines.append(f"spanning-tree priority {priority}")
        else:
            lines.append("no spanning-tree enable")
        lines.append("!")
        return "\n".join(lines)


class MaipuRoutingGenerator:
    """迈普路由配置生成器"""
    
    @staticmethod
    def generate_static_route(dest, mask, nexthop, preference=60):
        return f"ip route {dest} {mask} {nexthop} {preference}"
    
    @staticmethod
    def generate_static_routes(routes):
        lines = []
        for route in routes:
            lines.append(MaipuRoutingGenerator.generate_static_route(
                route["dest"], route["mask"],
                route["nexthop"], route.get("preference", 60)
            ))
        return "\n".join(lines)
    
    @staticmethod
    def generate_ospf(process_id, router_id, networks):
        lines = [
            f"router ospf {process_id}",
            f" router-id {router_id}"
        ]
        for net in networks:
            lines.append(f" network {net['network']} {net['wildcard']} area {net['area']}")
        lines.append("!")
        return "\n".join(lines)
    
    @staticmethod
    def generate_bgp(as_number, router_id, peers, networks):
        lines = [
            f"router bgp {as_number}",
            f" bgp router-id {router_id}"
        ]
        for peer in peers:
            lines.append(f" neighbor {peer['ip']} remote-as {peer['remote_as']}")
        for net in networks:
            lines.append(f" network {net}")
        lines.append("!")
        return "\n".join(lines)

    @staticmethod
    def generate_rip(version=2, networks=None):
        lines = ["router rip", f" version {version}"]
        for network in networks or []:
            lines.append(f" network {network}")
        lines.append("!")
        return "\n".join(lines)


class MaipuSecurityGenerator:
    """迈普安全配置生成器"""
    
    @staticmethod
    def generate_acl(number, rules, description=None):
        acl_type = "extended" if int(number) >= 100 else "standard"
        lines = [f"ip access-list {acl_type} {number}"]
        if description:
            lines.append(f" remark {description}")
        
        for rule in rules:
            action = rule.get("action", "permit")
            proto = rule.get("protocol", "ip")
            src = rule.get("source", "any")
            src_wc = rule.get("src_wildcard", "")
            dst = rule.get("dest", "any")
            dst_wc = rule.get("dst_wildcard", "")
            port = rule.get("port", "")
            
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
        return f"""interface {interface}
 ip access-group {acl_number} {direction}
!"""

    @staticmethod
    def generate_dhcp_snooping(enable=True, trusted_ports=None, vlan=None):
        """迈普 DHCP Snooping（NetCMD 校准集实锤，标注迈普官方）：
        全局 dhcp-snooping（连字符、无 enable），接口下 dhcp-snooping trust；
        无 IOS 式 ip dhcp snooping vlan 子命令，按端口/接口维度启用"""
        if not enable:
            return "no dhcp-snooping\n!"
        lines = ["dhcp-snooping"]
        if vlan:
            lines.append(f"# 注：迈普按端口维度启用，无 vlan 子命令；本例规划 VLAN {vlan}")
        for port in trusted_ports or []:
            lines.append(f"interface {port}")
            lines.append(" dhcp-snooping trust")
        lines.append("!")
        return "\n".join(lines)

    @staticmethod
    def generate_arp_inspection(vlans=None, trusted_ports=None):
        """迈普 ARP 防护（NetCMD 校准集实锤，标注迈普官方）：接口级 arp-check 体系，
        非 IOS ip arp inspection——用户口 arp-check enable + arp-check binding，
        上联/信任口不配置即为信任；不生成伪命令，输出配置指引"""
        lines = [
            "# 迈普 ARP 防护为接口级 arp-check（非 ip arp inspection）：",
            "#   用户口：interface <port> 后 arp-check enable + arp-check binding <MAC> <IP>",
            "#   上联/信任口：不配置 arp-check 即为信任",
        ]
        if trusted_ports:
            lines.append(f"# 本次信任口（无需配置）: {', '.join(map(str, trusted_ports))}")
        if vlans:
            lines.append(f"# VLAN 维度（{', '.join(map(str, vlans))}）仅锐捷/思科 DAI 适用，迈普按接口逐口开启")
        return "\n".join(lines)

    @staticmethod
    def generate_storm_control(interface, broadcast=None, multicast=None, unicast=None):
        # 五厂商对照实锤：迈普 S3400/S4330 接入系列只支持 pps/bps、无百分比模式，
        # 用 pps 跨全系列最稳；旧版 rate 关键字非实机语法已修正
        lines = [f"interface {interface}"]
        if broadcast:
            lines.append(f" storm-control broadcast pps {broadcast}")
        if multicast:
            lines.append(f" storm-control multicast pps {multicast}")
        if unicast:
            lines.append(f" storm-control unicast pps {unicast}")
        lines.append("!")
        return "\n".join(lines)


class MaipuInterfaceGenerator:
    """迈普接口配置生成器"""
    
    @staticmethod
    def generate_eth_trunk(trunk_id, mode="lacp", members=None, description=None,
                           trunk_vlans=None):
        """迈普链路聚合（NetCMD 校准集实锤，HiOS 主线多平台核验）：
        聚合组全局定义 link-aggregation N mode lacp|manual，成员口 link-aggregation N mode lacp|manual
        （成员口用 mode lacp，不分 active/passive）；
        S3000 等 ROS 老平台为 port-group N mode active|on 语法（见校准摘录）"""
        lines = []
        if mode in ("lacp", "lacp-static", "lacp-dynamic"):
            lines.append(f"link-aggregation {trunk_id} mode lacp")
            member_cmd = f"link-aggregation {trunk_id} mode lacp"
        else:
            lines.append(f"link-aggregation {trunk_id} mode manual")
            member_cmd = f"link-aggregation {trunk_id} mode manual"
        lines.append("# 注：S3000 等 ROS 老平台为 port-group {0} mode active|on（全局+成员口）".format(trunk_id))
        lines.append("!")
        if members:
            for member in members:
                lines.append(f"interface {member}")
                if description:
                    lines.append(f" description {description}")
                lines.append(f" {member_cmd}")
                if trunk_vlans:
                    vlans = " ".join(str(v) for v in trunk_vlans) if isinstance(trunk_vlans, (list, tuple)) else str(trunk_vlans)
                    lines.append(" switchport trunk allowed vlan " + vlans)
                lines.append("!")
        return "\n".join(lines)
    
    @staticmethod
    def generate_lldp(enable=True, mode="tx_rx", interval=30, holdtime=120):
        lines = []
        if enable:
            lines.append("lldp enable")
            lines.append(f"lldp timer {interval}")
            lines.append(f"lldp holdtime {holdtime}")
        else:
            lines.append("no lldp enable")
        lines.append("!")
        return "\n".join(lines)
    
    @staticmethod
    def generate_loop_detect(enable=True, interval=5, action="shutdown"):
        lines = []
        if enable:
            lines.append("loopback-detection enable")
            lines.append(f"loopback-detection interval {interval}")
            lines.append(f"loopback-detection action {action}")
        else:
            lines.append("no loopback-detection enable")
        lines.append("!")
        return "\n".join(lines)
    
    @staticmethod
    def generate_poe(interface=None, enable=True, priority="low", power=None):
        # 核验依据：迈普 SM3100/SM3900 实机命令手册——PoE 总闸/分闸均为
        # power inline enable，关闭为 no power inline enable（旧版 poe enable 非实机语法，已修正）
        # priority/max-power 为 IOS 家族扩展写法，未在公开手册核到，下发前请以型号手册核对
        lines = []
        if interface:
            lines.append(f"interface {interface}")
            if enable:
                lines.append(" power inline enable")
                if priority:
                    lines.append(f" power inline priority {priority}")
                if power:
                    lines.append(f" power inline max {power}")
            else:
                lines.append(" no power inline enable")
            lines.append("!")
        else:
            lines.append("power inline enable" if enable else "no power inline enable")
        return "\n".join(lines)
    
    @staticmethod
    def generate_rate_limit(interface, rate_in=None, rate_out=None):
        lines = [f"interface {interface}"]
        if rate_in:
            lines.append(f" storm-control broadcast pps {rate_in}")
        if rate_out:
            lines.append(f" storm-control multicast pps {rate_out}")
        lines.append("!")
        return "\n".join(lines)


# ================================================================ 页签级聚合
# 与华为侧 VLANConfigGenerator.generate_vlan_all 等消费同一 config dict，
# 页签层零字段适配即可按厂商取用。迈普未在公开渠道核到的细粒度语法
# 在对应段带「请以设备手册核对」标注，不静默猜测。

def _acl_rules(rules):
    """页签 ACL 规则字段 → 迈普生成器字段（None → any/ip 兑底）"""
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
        parts.append(MaipuVLANGenerator.generate_vlans(config["vlans"]))
    if "interfaces" in config:
        parts.append("\n".join(MaipuVLANGenerator.generate_interface(
            i["interface"], i.get("type", "access"), i.get("vlan_id"),
            _vlans_str(i.get("trunk_vlans")), i.get("pvid"))
            for i in config["interfaces"]))
    if "vlanifs" in config:
        parts.append("\n".join(MaipuVLANGenerator.generate_vlanif(
            v["vlan_id"], v["ip_address"], v.get("mask", "255.255.255.0"), v.get("description"))
            for v in config["vlanifs"]))
    if "stp" in config:
        s = config["stp"]
        parts.append(MaipuVLANGenerator.generate_stp(
            s.get("mode", "rstp"), s.get("priority", 32768), s.get("enable", True)))
    return "\n".join(p for p in parts if p)


def generate_route_all(config: dict) -> str:
    """消费路由页签 config dict（static_routes/ospf/bgp/rip）"""
    parts = []
    for r in config.get("static_routes", []):
        parts.append(MaipuRoutingGenerator.generate_static_route(
            r["dest_network"], r["mask"],
            r.get("next_hop") or r.get("interface"), r.get("preference") or 60))
    if "ospf" in config:
        o = config["ospf"]
        nets = [{"network": n["address"], "wildcard": n.get("mask", "0.0.0.255"),
                 "area": o.get("area_id", "0")} for n in o.get("networks", [])]
        parts.append(MaipuRoutingGenerator.generate_ospf(
            o.get("process_id", 1), o.get("router_id"), nets))
    if "bgp" in config:
        b = config["bgp"]
        peers = [{"ip": p["ip"], "remote_as": p["as"]} for p in b.get("peers", [])]
        parts.append(MaipuRoutingGenerator.generate_bgp(
            b["as_number"], b.get("router_id"), peers, b.get("networks", [])))
    if "rip" in config:
        rip = config["rip"]
        parts.append(MaipuRoutingGenerator.generate_rip(
            rip.get("version", 2), rip.get("networks", [])))
    return "\n".join(p for p in parts if p)


def generate_security_all(config: dict) -> str:
    """消费安全页签 config dict；DHCP/ARP 段为 IOS 家族通用语法，带核对标注"""
    parts = []
    for acl in config.get("acls", []):
        parts.append(MaipuSecurityGenerator.generate_acl(
            acl["number"], _acl_rules(acl.get("rules", [])), acl.get("description")))
    for ps in config.get("port_security", []):
        parts.append(MaipuSecurityGenerator.generate_port_security(
            ps["interface"], ps.get("max_mac", 1), ps.get("action", "shutdown"),
            ps.get("sticky", False)))
    for tf in config.get("traffic_filters", []):
        parts.append(MaipuSecurityGenerator.generate_traffic_filter(
            tf["interface"], tf["acl_number"], tf.get("direction", "in")))
    if "dhcp_snooping" in config:
        ds = config["dhcp_snooping"]
        parts.append(MaipuSecurityGenerator.generate_dhcp_snooping(
            ds.get("enable", True), ds.get("trusted_ports"), ds.get("vlan")))
    if "arp_inspection" in config:
        ai = config["arp_inspection"]
        parts.append(MaipuSecurityGenerator.generate_arp_inspection(
            ai.get("vlans"), ai.get("trusted_ports")))
    for st in config.get("storm_controls", []):
        parts.append(MaipuSecurityGenerator.generate_storm_control(
            st["interface"], st.get("broadcast"), st.get("multicast"), st.get("unicast")))
    if "anti_attack" in config:
        # 防攻击语法厂商差异大，不自动翻译，防静默漏配
        parts.append(f"# 反攻击功能（类型 {config['anti_attack'].get('type', 'all')}）"
                     "请按迈普设备手册核对后手工补充")
    return "\n".join(p for p in parts if p)


def generate_interface_all(config: dict) -> str:
    """消费接口页签 config dict；链路聚合已按五厂商对照实锤语法生成"""
    parts = []
    for t in config.get("eth_trunks", []):
        parts.append(MaipuInterfaceGenerator.generate_eth_trunk(
            t["trunk_id"], t.get("mode", "lacp"),
            t.get("member_ports"), t.get("description"),
            t.get("trunk_vlans")))
    if "lldp" in config:
        l = config["lldp"]
        parts.append(MaipuInterfaceGenerator.generate_lldp(
            l.get("enable", True), l.get("mode", "both"),
            l.get("interval", 30), l.get("holdtime", 120)))
    if "loopback_detection" in config:
        ld = config["loopback_detection"]
        parts.append(MaipuInterfaceGenerator.generate_loop_detect(
            ld.get("enable", True), ld.get("interval", 5), ld.get("action", "shutdown")))
    if "poe" in config:
        p = config["poe"]
        parts.append(MaipuInterfaceGenerator.generate_poe(
            None, p.get("enable", True), None, p.get("max_power")))
        for i in p.get("interfaces", []):
            parts.append(MaipuInterfaceGenerator.generate_poe(
                i["interface"], i.get("enable", True), i.get("priority"), i.get("max_power")))
    for rl in config.get("rate_limits", []):
        parts.append(MaipuInterfaceGenerator.generate_rate_limit(
            rl["interface"], rl.get("cir_in"), rl.get("cir_out")))
    return "\n".join(p for p in parts if p)
