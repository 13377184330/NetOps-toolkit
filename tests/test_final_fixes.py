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
    case("F4c 损坏账本已备份不静默丢数据",
         os.path.exists(ip.IPAM_FILE + ".corrupt"))
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

n_pass = sum(1 for _, ok, _ in results if ok)
print("\n" + "=" * 68)
print(f"最终轮修复定向回归: PASS {n_pass} / FAIL {len(results) - n_pass}")
for name, ok, note in results:
    if not ok:
        print(f"  ❌ {name} —— {note[:140]}")
sys.exit(0 if all(ok for _, ok, _ in results) else 1)
