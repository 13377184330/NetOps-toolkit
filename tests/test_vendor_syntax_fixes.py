# -*- coding: utf-8 -*-
"""其余四厂商(华为/H3C/锐捷/迈普)配置语法 bug 定向回归。

来源：2026-11-17 审查确认并修复的 11 处缺陷（思科同源复制时漏同步 + 华为
storm action f-string + BGP network CIDR）。此前 test_vendor_gen 未覆盖这些路径。
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

results = []
def case(name, ok, note=""):
    results.append((name, ok, note))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" —— {note}" if note else ""))

from modules.basic_config import BasicConfigGenerator as HuaweiBasic
from modules.security_config import SecurityConfigGenerator as HuaweiSec
from modules.routing_config import RoutingConfigGenerator as HuaweiRoute
from modules.ruijie_config import (
    RuijieSecurityGenerator as RSec, RuijieInterfaceGenerator as RIf,
    RuijieBasicGenerator as RBasic, RuijieRoutingGenerator as RRoute)
from modules.maipu_config import (
    MaipuSecurityGenerator as MSec, MaipuInterfaceGenerator as MIf,
    MaipuBasicGenerator as MBasic, MaipuRoutingGenerator as MRoute)
from modules.h3c_config import H3CConfigGenerator as H3
from utils.net_addr import parse_network, bgp_network_line

print("=" * 68)
print("四厂商配置语法修复 定向回归")
print("=" * 68)

# ---- 华为 ----
hs = HuaweiSec.generate_storm_control("GE0/0/1", broadcast=5000, action="block")
case("HW1 storm action 变量已替换",
     "storm-control action block" in hs and "{action}" not in hs, hs.replace("\n", " | "))
for tz, expect in [("UTC-5", "subtract 05:00:00"),
                   ("UTC+8", "add 08:00:00"),
                   ("UTC+0", "add 00:00:00")]:
    ntp = HuaweiBasic.generate_ntp_config([], tz)
    case(f"HW2 华为NTP时区 {tz}", expect in ntp, ntp.strip())

# ---- 锐捷 ----
rs = RSec.generate_storm_control("Gi0/1", broadcast=5000, multicast=3000)
case("RJ1 storm 用 level pps", "level pps 5000" in rs and "level 5000" not in rs,
     rs.replace("\n", " | "))
rl = RIf.generate_rate_limit("Gi0/1", rate_in=10000, rate_out=20000)
case("RJ2 限速用rate-limit非storm",
     "storm-control" not in rl and "rate-limit input 10000000" in rl
     and "rate-limit output 20000000" in rl, rl.replace("\n", " | "))
rntp = RBasic.generate_ntp([{"ip": "1.1.1.1"}], "UTC-5")
case("RJ3 NTP时区 UTC-5", "clock timezone UTC -5" in rntp, rntp.replace("\n", " | "))
rv3 = RBasic.generate_snmp("v3", "pub", "pri")
case("RJ4 SNMPv3不输出community", "community" not in rv3 and "snmp-server user" in rv3)
rstd = RSec.generate_acl(10, [{"action": "permit", "source": "1.1.1.1",
                               "src_wildcard": "0.0.0.0"}], acl_type="standard")
case("RJ5 标准ACL只按源过滤",
     "permit 1.1.1.1 0.0.0.0" in rstd and "permit ip" not in rstd,
     rstd.replace("\n", " | "))

# ---- 迈普 ----
ml = MIf.generate_rate_limit("ge0/1", rate_in=10000, rate_out=20000)
case("MP1 限速用rate-limit非storm",
     "storm-control" not in ml and "rate-limit input 10000000" in ml,
     ml.replace("\n", " | "))
mntp = MBasic.generate_ntp([{"ip": "1.1.1.1"}], "UTC+8")
case("MP2 NTP时区 UTC+8", "clock timezone UTC 8" in mntp, mntp.replace("\n", " | "))
mv3 = MBasic.generate_snmp("v3", "pub", "pri")
case("MP3 SNMPv3不输出community", "community" not in mv3 and "snmp-server user" in mv3)
mstd = MSec.generate_acl(2000, [{"action": "permit", "source": "1.1.1.1",
                                 "src_wildcard": "0.0.0.0"}], acl_type="standard")
case("MP4 标准ACL只按源过滤",
     "permit 1.1.1.1 0.0.0.0" in mstd and "permit ip" not in mstd,
     mstd.replace("\n", " | "))

# ---- BGP CIDR（五厂商）----
case("BGP1 CIDR解析", parse_network("3.3.3.0/24") == ("3.3.3.0", "255.255.255.0"))
case("BGP2 裸地址不臆造掩码", parse_network("192.168.0.0") == ("192.168.0.0", None))
case("BGP3 VRP network带掩码",
     bgp_network_line("3.3.3.0/24", "vrp") == "network 3.3.3.0 255.255.255.0")
case("BGP4 IOS network带mask关键字",
     bgp_network_line("3.3.3.0/24", "ios") == "network 3.3.3.0 mask 255.255.255.0")
hb = HuaweiRoute.generate_bgp_config(65001, networks=["3.3.3.0/24"])
case("BGP5 华为生成器CIDR", "network 3.3.3.0 255.255.255.0" in hb)
for nm, gen in [("锐捷", RRoute), ("迈普", MRoute), ("思科", None)]:
    if gen:
        out = gen.generate_bgp(65001, None, [], ["3.3.3.0/24"])
    else:
        from modules.cisco_config import CiscoRoutingGenerator
        out = CiscoRoutingGenerator.generate_bgp(65001, None, [], ["3.3.3.0/24"])
    case(f"BGP6 {nm}生成器CIDR", "network 3.3.3.0 mask 255.255.255.0" in out
         and "/24" not in out)

# ---- H3C 死代码 ----
try:
    h3out = H3.generate_service_config(
        {"snmp": {"version": "v3", "trap_enable": True, "trap_host": "2.2.2.2"},
         "ntp": {"servers": [], "timezone": "UTC-5"}})
    case("H3C1 v3+trap 不抛 UnboundLocalError", "target-host" in h3out)
    case("H3C2 NTP时区带偏移", "subtract 5" in h3out)
except Exception as e:
    case("H3C v3+trap", False, repr(e))

n_pass = sum(1 for _, ok, _ in results if ok)
print("\n" + "=" * 68)
print(f"四厂商语法修复定向回归: PASS {n_pass} / FAIL {len(results) - n_pass}")
for name, ok, note in results:
    if not ok:
        print(f"  ❌ {name} —— {note[:140]}")
sys.exit(0 if all(ok for _, ok, _ in results) else 1)
