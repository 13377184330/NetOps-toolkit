# -*- coding: utf-8 -*-
"""最终轮审查修复的定向回归（2026-11-18）。

覆盖：nl_engine 上下文 ACL 空源、config_lint ACL 顺序误报、
adv_modules 中文说明混入下发命令、ipam 损坏数据 KeyError、
credential_crypto 坏密钥导入期崩溃。
"""
import os
import sys
import json
import tempfile
import shutil

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

results = []
def case(name, ok, note=""):
    results.append((name, ok, note))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" —— {note}" if note else ""))

print("=" * 68)
print("最终轮审查修复 定向回归")
print("=" * 68)

# ---- BUG1 nl_engine 上下文 ACL 空源 ----
from modules.nl_engine import _build_acl
r = _build_acl("禁止访问", "192.168.1.1/24", "huawei")
cmds = [c for c, _ in r["lines"]]
case("F1 上下文IP生成有效ACL规则",
     any("deny ip source 192.168.1.1" in c for c in cmds)
     and not any(c.rstrip().endswith("source") for c in cmds),
     str([c for c in cmds if "rule" in c]))

# ---- BUG2 config_lint ACL 顺序误报 ----
from modules.config_lint import lint
after = lint("interface GigabitEthernet0/1\n packet-filter 3000 inbound\n!\nacl number 3000\n rule 5 permit ip\n", "huawei")
before = lint("acl number 3000\n rule 5 permit ip\n!\ninterface GigabitEthernet0/1\n packet-filter 3000 inbound\n", "huawei")
def missing_acl(items):
    return [x for x in items if "不存在" in str(x) and "ACL" in str(x)]
case("F2 ACL后置不再误报不存在",
     len(missing_acl(after["items"])) == len(missing_acl(before["items"])),
     f"后置={len(missing_acl(after['items']))} 前置={len(missing_acl(before['items']))}")
# IOS 语法：ip access-list / access-list / 具名 ACL 都须正确识别，不误报
ios_acl = lint("ip access-list extended 100\n permit ip any any\n!\ninterface Gi0/1\n ip access-group 100 in\n", "cisco")
ios_named = lint("ip access-list extended WEB\n!\ninterface Gi0/1\n ip access-group web in\n", "cisco")
ios_missing = lint("interface Gi0/1\n ip access-group NOPE in\n", "cisco")
case("F2b IOS编号ACL不误报", len(missing_acl(ios_acl["items"])) == 0)
case("F2c IOS具名ACL不误报(大小写)", len(missing_acl(ios_named["items"])) == 0)
case("F2d IOS真不存在的ACL仍报错", len(missing_acl(ios_missing["items"])) == 1)

# ---- 弱口令多入口漏同步 ----
from modules.nl_engine import parse as nl_parse
nl = str(nl_parse("开启ssh远程登录", "huawei"))
case("F2e 自然语言引擎无硬编码弱口令",
     "Admin@123" not in nl and "admin@123" not in nl, nl[:100])
for _f in ("utils/templates.py", "utils/template_manager.py",
           "gui/tabs/basic_tab.py", "modules/onboard.py"):
    _src = open(os.path.join(ROOT, _f), encoding="utf-8").read()
    case(f"F2f {_f} 无硬编码弱口令",
         "Admin@123" not in _src and "admin@123" not in _src)

# ---- BUG3 adv_modules 中文说明不进命令 ----
from modules.adv_modules import gen_stack, gen_dhcp_relay
stack_cmds = [c for c, _ in gen_stack("cisco", {"priority": 150})]
case("F3 堆叠命令不含中文说明",
     not any("专用堆叠线" in c or "无需配置" in c for c in stack_cmds),
     str([c for c in stack_cmds if "堆叠" in c]))
relay_cmds = [c for c, _ in gen_dhcp_relay("cisco", {"ifn": "Vlan10", "server": "1.1.1.1"})]
case("F3b DHCP中继SVI无中文伪命令",
     not any("无需此步" in c or "无需" in c for c in relay_cmds), str(relay_cmds))

# ---- BUG4 ipam 损坏数据 ----
import modules.ipam as ip
d = tempfile.mkdtemp()
orig = ip.IPAM_FILE
ip.IPAM_FILE = os.path.join(d, "ipam.json")
try:
    with open(ip.IPAM_FILE, "w", encoding="utf-8") as f:
        json.dump({"subnets": [{"subnet": "10.0.0.0/24", "name": "x", "usage": ""}]}, f)
    ok1 = ok2 = False
    try: ip.mark_ip("10.0.0.0/24", "10.0.0.5"); ok1 = True
    except Exception as e: note1 = repr(e)
    try: r = ip.suggest_free("10.0.0.0/24"); ok2 = bool(r)
    except Exception as e: note2 = repr(e)
    case("F4 缺used键mark_ip不崩", ok1)
    case("F4b 缺used键suggest_free不崩", ok2)
    # 损坏账本须备份，不能静默当空（否则下次保存覆盖原数据）
    with open(ip.IPAM_FILE, "w", encoding="utf-8") as f:
        f.write("{BROKEN")
    ip._load()
    import glob
    case("F4c 损坏账本已备份不静默丢数据",
         len(glob.glob(ip.IPAM_FILE + ".*.corrupt")) >= 1)
finally:
    ip.IPAM_FILE = orig
    shutil.rmtree(d, ignore_errors=True)

# ---- BUG5 credential_crypto 坏密钥 ----
import utils.credential_crypto as cc
d = tempfile.mkdtemp()
kf = os.path.join(d, "secret.key")
orig_keyfile = cc._KEY_FILE
try:
    with open(kf, "wb") as f:
        f.write(b"short-bad-key")
    cc._KEY_FILE = kf
    key = cc._load_or_create_key()
    from cryptography.fernet import Fernet
    Fernet(key)  # 新 key 合法
    case("F5 坏密钥自愈不崩溃",
         len(key) == 44 and os.path.exists(kf + ".corrupt"),
         f"keylen={len(key)} 备份={os.path.exists(kf+'.corrupt')}")
finally:
    cc._KEY_FILE = orig_keyfile
    shutil.rmtree(d, ignore_errors=True)

# ---- 第六轮：config_lint ACL 全语法 ----
def _acl_miss(cfg, v):
    return [x["issue"] for x in lint(cfg, v)["items"] if "不存在的 ACL" in x["issue"]]
vrp_variants = [
    ("acl 3000", "packet-filter 3000 inbound"),
    ("acl number 3000", "packet-filter 3000 inbound"),
    ("acl name WEB", "packet-filter WEB inbound"),
    ("acl ipv6 3000", "traffic-filter inbound acl 3000"),
    ("acl ipv6 number 3000", "traffic-filter outbound acl 3000"),
    ("acl advanced 3000", "traffic-filter inbound acl 3000"),
]
for defin, ref in vrp_variants:
    cfg = f"{defin}\n!\ninterface GE0/1\n {ref}\n"
    case(f"G1 {defin} + {ref}", len(_acl_miss(cfg, "huawei")) == 0, str(_acl_miss(cfg, "huawei")))
case("G1x VRP真不存在ACL仍报错",
     len(_acl_miss("interface GE0/1\n traffic-filter inbound acl 3999\n", "huawei")) == 1)

# ---- 第六轮：credential 备份失败仍自愈 ----
import shutil as _sh
d = tempfile.mkdtemp(); kf = os.path.join(d, "secret.key")
open(kf, "wb").write(b"short-bad-key")
cc._KEY_FILE = kf
_orig_copy = _sh.copy2
_sh.copy2 = lambda *a, **k: (_ for _ in ()).throw(OSError("模拟备份失败"))
try:
    k = cc._load_or_create_key()
    Fernet(k)
    case("G2 密钥备份失败仍返回合法key", len(k) == 44)
finally:
    _sh.copy2 = _orig_copy; cc._KEY_FILE = orig_keyfile; shutil.rmtree(d, ignore_errors=True)

# ---- 第六轮：ipam 结构损坏 + 多次备份 ----
d = tempfile.mkdtemp(); import glob as _glob
orig_ip = ip.IPAM_FILE; ip.IPAM_FILE = os.path.join(d, "ipam.json")
try:
    open(ip.IPAM_FILE, "w").write("[]")   # 合法 JSON 但结构错
    ip._load()
    ip.add_subnet("10.0.0.0/24")
    case("G3 结构损坏账本可自愈", len(ip.list_subnets()) == 1)
    open(ip.IPAM_FILE, "w").write("{BAD1")
    ip._load()
    open(ip.IPAM_FILE, "w").write("{BAD2")
    ip._load()
    case("G3b 多次损坏备份不互相覆盖",
         len(_glob.glob(ip.IPAM_FILE + ".*.corrupt")) >= 2)
finally:
    ip.IPAM_FILE = orig_ip; shutil.rmtree(d, ignore_errors=True)

# ---- 第六轮：nl_engine 错误记录有界 ----
import modules.nl_engine as _nl
_nl.LAST_PARSE_ERRORS.clear()
for _ in range(200):
    _nl.parse("创建用户 用户名：@@@", "huawei")
case("G4 解析错误记录有界(maxlen=100)", len(_nl.LAST_PARSE_ERRORS) <= 100,
     f"长度={len(_nl.LAST_PARSE_ERRORS)}")

# ---- 第六轮：source_port 不再静默漏配 ----
from modules.qos_config import QoSConfigGenerator as _Q
qsrc = str(_Q.generate_acl_qos("3000", [{"id": 5, "protocol": "tcp", "source": "1.1.1.1",
                                         "source_port": 1234, "dest_port": 80, "dscp": 10}]))
case("G5 QoS规则输出source-port", "source-port eq 1234" in qsrc, qsrc[:160])

# ---- 第七轮：NAT 掩码反掩码 + 连续性校验 ----
from modules.adv_modules import gen_nat, gen_stack
vrp_nat = str(gen_nat("huawei", {"src_net": "192.168.10.0", "src_mask": "255.255.255.0",
                                 "acl_id": "2000", "out_if": "GE0/1"}))
case("H1 VRP NAT用反掩码(非子网掩码)",
     "permit source 192.168.10.0 0.0.0.255" in vrp_nat
     and "permit source 192.168.10.0 255.255.255.0" not in vrp_nat, vrp_nat[:200])
bad_nat = str(gen_nat("huawei", {"src_net": "192.168.10.0", "src_mask": "255.0.255.0",
                                 "acl_id": "2000", "out_if": "GE0/1"}))
case("H1b 不连续掩码被拦截", "掩码" in bad_nat and "permit source" not in bad_nat,
     bad_nat[:120])
from utils.net_addr import mask_valid, mask_to_wildcard
case("H1c 掩码校验口径统一",
     mask_valid("255.255.255.0") and not mask_valid("255.0.255.0")
     and mask_to_wildcard("1.2.3.4") is None)

# ---- 第七轮：h3c protocol=None 不崩 ----
from modules.h3c_config import H3CConfigGenerator as _H
try:
    _H.generate_security_config({"acls": [{"number": 3000, "rules": [
        {"action": "permit", "source": "1.1.1.0", "source_port": 80, "protocol": None}]}]})
    case("H2 protocol=None不崩溃", True)
except Exception as e:
    case("H2 protocol=None不崩溃", False, repr(e))

# ---- 第七轮：思科堆叠优先级范围 ----
cisco_stack = str(gen_stack("cisco", {"member": "1", "priority": "150"}))
case("H3 思科堆叠优先级钳制到<=15",
     "priority 150" not in cisco_stack and "priority 15" in cisco_stack
     and "1-15" in cisco_stack, cisco_stack[:200])

# ---- 第七轮：settings 浅拷贝污染 ----
import utils.settings as _sm
_d = tempfile.mkdtemp(); _orig_sf = _sm.SETTINGS_FILE
_sm.SETTINGS_FILE = os.path.join(_d, "s.json")
try:
    _s = _sm.Settings(); _s.add_recent_file("HOST_A")
    _s.reset()
    case("H4 reset真正恢复默认(不污染DEFAULT)",
         _s.get_recent_files() == [] and _sm.DEFAULT_SETTINGS.get("recent_files") == [],
         f"reset后={_s.get_recent_files()} DEFAULT={_sm.DEFAULT_SETTINGS.get('recent_files')}")
finally:
    _sm.SETTINGS_FILE = _orig_sf; shutil.rmtree(_d, ignore_errors=True)

# ---- 第七轮：时区越界统一标记 ----
from modules.cisco_config import _parse_timezone as _p1
from modules.basic_config import _vrp_timezone as _p2
from modules.h3c_config import _comware_timezone as _p3
from modules.maipu_config import _tz_name_offset as _p4
case("H5 时区解析越界统一标_CHECK",
     all("_CHECK" in str(f("UTC+99")[0]) and f("UTC+8")[0] == "UTC"
         for f in (_p1, _p2, _p3, _p4)))

n_pass = sum(1 for _, ok, _ in results if ok)
print("\n" + "=" * 68)
print(f"最终轮修复定向回归: PASS {n_pass} / FAIL {len(results) - n_pass}")
for name, ok, note in results:
    if not ok:
        print(f"  ❌ {name} —— {note[:140]}")
sys.exit(0 if all(ok for _, ok, _ in results) else 1)
