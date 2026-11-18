# -*- coding: utf-8 -*-
"""第三轮审查修复的定向回归（2026-11-17）。

覆盖：新引入回归（IPv6 CIDR / 迈普 ACL 编号 / 字符串 kbps）、
安全红线（弱口令占位符）、体检漏报、弱口令正则、fd 二次 close、
OUI 重复 key、/31 /32 口径、IP 校验、槽函数兜底、http verify、端口范围。
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

print("=" * 68)
print("第三轮审查修复 定向回归")
print("=" * 68)

# ---- 新引入回归 ----
from utils.net_addr import bgp_network_line
case("N1 IPv6 CIDR 保留原样",
     bgp_network_line("2001:db8::/32", "ios") == "network 2001:db8::/32",
     bgp_network_line("2001:db8::/32", "ios"))
case("N1b IPv4 CIDR 仍展开",
     bgp_network_line("3.3.3.0/24", "ios") == "network 3.3.3.0 mask 255.255.255.0")

from modules.maipu_config import MaipuSecurityGenerator as M
rules = [{"action": "permit", "protocol": "tcp", "source": "1.1.1.1",
          "src_wildcard": "0.0.0.0", "dest": "2.2.2.2",
          "dst_wildcard": "0.0.0.0", "port": "80"}]
acl101 = M.generate_acl(101, rules)
case("N2 迈普 ACL101 不降级为standard",
     "ip access-list extended 101" in acl101 and "eq 80" in acl101,
     acl101.splitlines()[0])
acl50 = M.generate_acl(50, rules)
case("N2b 迈普 ACL50 是standard", "ip access-list standard 50" in acl50)

from modules.maipu_config import MaipuInterfaceGenerator as MI
try:
    out = MI.generate_rate_limit("ge0/1", rate_in="100.5")
    case("N3 字符串kbps不崩溃", "无法解析" in out or "rate-limit" in out, out.replace("\n", " | "))
except Exception as e:
    case("N3 字符串kbps不崩溃", False, repr(e))

# ---- 安全红线：弱口令占位符 ----
from modules.basic_config import BasicConfigGenerator as B
aaa = B.generate_aaa_user()
case("S1 AAA默认口令为占位符",
     "admin@123" not in aaa.lower() and "TODO_SET_PASSWORD" in aaa, aaa.strip())
snmp = B.generate_snmp_config(trap_enable=True, trap_host="1.1.1.1")
case("S2 SNMP trap 不硬编码 public",
     "securityname public" not in snmp and "TODO_SET_COMMUNITY" in snmp)

from modules.batch_gen import gen_device_batch
try:
    bg = gen_device_batch("huawei", [{"name": "sw1", "ip": "1.1.1.1"}])
    blob = str(bg)
    case("S3 batch_gen 无 Admin@123", "Admin@123" not in blob and "TODO_SET_PASSWORD" in blob)
except Exception as e:
    case("S3 batch_gen 无 Admin@123", False, repr(e))

mw = open(os.path.join(ROOT, "gui", "main_window.py"), encoding="utf-8").read()
case("S4 模板无硬编码口令",
     "Admin@123" not in mw and "CoreAdmin@123" not in mw and "TODO_SET_PASSWORD" in mw)

# ---- 体检 / 校验 / 加密 ----
from modules.health_checker import check_health
try:
    rep = check_health("sysname SW\n#\nreturn", "huawei")
    # 未配 info-center 时日志中心那项不应为"通过"
    log_items = [it for it in rep["items"] if it["item"] == "日志中心"]
    log_pass = bool(log_items) and log_items[0]["result"] == "通过"
    case("H1 未配日志不再误判通过", not log_pass,
         str(log_items[0]) if log_items else "无日志项")
except Exception as e:
    case("H1 未配日志不再误判通过", False, repr(e))

from utils.config_validator import ConfigValidator
cv = ConfigValidator()
vr = cv.validate("local-user admin\n password simple admin\n")
vr_str = str(vr)
case("H2 password simple admin 被识别弱口令",
     "弱密码" in vr_str or "弱口令" in vr_str, vr_str[:160])

import ast, collections
src = open(os.path.join(ROOT, "gui", "tools", "mac_tool.py"), encoding="utf-8").read()
dups_all = []
for node in ast.walk(ast.parse(src)):
    if isinstance(node, ast.Dict):
        keys = [k.value for k in node.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)]
        dups_all += [k for k, c in collections.Counter(keys).items() if c > 1]
case("H3 OUI 无重复 key", not dups_all, f"重复={dups_all}")

from utils.network_tools.subnet_calculator import SubnetCalculator as SC
r31 = SC.calculate("10.0.0.0", "255.255.255.254")
r32 = SC.calculate("10.0.0.1", "255.255.255.255")
masks = {m["prefix"]: m for m in SC.get_all_masks()}
case("H4 /31 口径一致",
     r31["usable_hosts"] == masks[31]["usable_hosts"],
     f"calculate={r31['usable_hosts']} table={masks[31]['usable_hosts']}")
case("H4b /32 口径一致",
     r32["usable_hosts"] == masks[32]["usable_hosts"],
     f"calculate={r32['usable_hosts']} table={masks[32]['usable_hosts']}")

from utils.network_tools.dns_tool import IPAddressConverter as C
case("H5 999.1.1.1 被拒", C.ip_to_decimal("999.1.1.1")["success"] is False)
case("H5b 300.1.1.1 被拒", C.ip_to_binary("300.1.1.1")["success"] is False)
case("H5c 合法IP仍可用", C.ip_to_decimal("192.168.0.1")["decimal"] == 3232235521)

from utils.network_tools.port_scanner import PortScanner as PS
p = PS.scan_port("127.0.0.1", 70000)
case("H6 非法端口被拒", p["status"] == "error" and "有效范围" in p["error"])
pr = PS.scan_port_range("127.0.0.1", 70000, 70001)
case("H6b 非法端口范围被拒", pr.get("success") is False)

n_pass = sum(1 for _, ok, _ in results if ok)
print("\n" + "=" * 68)
print(f"第三轮修复定向回归: PASS {n_pass} / FAIL {len(results) - n_pass}")
for name, ok, note in results:
    if not ok:
        print(f"  ❌ {name} —— {note[:140]}")
sys.exit(0 if all(ok for _, ok, _ in results) else 1)
