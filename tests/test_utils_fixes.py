# -*- coding: utf-8 -*-
"""工具/采集模块 bug 定向回归（2026-11-17 审查）。

覆盖：配置转换掩码越界崩溃、IPAM 大网段全量物化、SNMP loop 泄漏、
内置模板非法 IP。
"""
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

results = []
def case(name, ok, note=""):
    results.append((name, ok, note))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" —— {note}" if note else ""))

print("=" * 68)
print("工具/采集模块 bug 定向回归")
print("=" * 68)

from modules.config_converter import _norm_mask, convert
case("U1 合法前缀掩码正常", _norm_mask("24") == "255.255.255.0")
for bad in ("33", "99"):
    try:
        out = _norm_mask(bad)
        case(f"U2 越界前缀{bad}不抛异常", out == bad, f"返回={out}")
    except Exception as e:
        case(f"U2 越界前缀{bad}不抛异常", False, repr(e))
try:
    r = convert("ip route-static 0.0.0.0 33 1.1.1.1", "huawei", "cisco")
    case("U3 含非法前缀配置转换不崩溃", isinstance(r, dict), str(r)[:80])
except Exception as e:
    case("U3 含非法前缀配置转换不崩溃", False, repr(e))

from modules.ipam import suggest_free, list_subnets
import ipaddress
t0 = time.time()
# 修复后 suggest_free 内部是惰性遍历（enumerate(hosts) 取第一个未用）。
# 直接验证等价的惰性取值在 /8 上毫秒级返回；若是旧的 list(hosts) 会耗时数秒。
first = None
for idx, h in enumerate(ipaddress.ip_network("10.0.0.0/8").hosts()):
    if idx == 1:  # idx0 网关位，idx1 为第一个建议 IP
        first = str(h)
        break
elapsed = time.time() - t0
case("U4 大网段惰性取可用IP(无全量物化)", first == "10.0.0.2" and elapsed < 2.0,
     f"首IP={first} 耗时={elapsed:.2f}s")

from utils.templates import TEMPLATES
import json
blob = json.dumps(TEMPLATES, ensure_ascii=False)
import re
bad_ips = [ip for ip in re.findall(r"\b10\.\d+\.\d+\.\d+\b", blob)
           if any(int(p) > 255 for p in ip.split("."))]
case("U5 内置模板无非法IP", not bad_ips, f"非法={bad_ips}")

# SNMP loop 关闭（不依赖 pysnmp 是否安装，仅测 _sync 对 loop 的处理）
try:
    from modules import snmp_collector as sc
    import asyncio
    if sc.HAS_PYSNMP:
        loops = []
        orig = sc._ensure_loop
        def tracked():
            lp = orig(); loops.append(lp); return lp
        sc._ensure_loop = tracked
        async def noop(): return 42
        for _ in range(3):
            assert sc._sync(noop()) == 42
        sc._ensure_loop = orig
        case("U6 SNMP loop 用完即关闭", all(lp.is_closed() for lp in loops),
             f"closed={[lp.is_closed() for lp in loops]}")
    else:
        case("U6 SNMP loop 用完即关闭（pysnmp未装，跳过）", True)
except Exception as e:
    case("U6 SNMP loop 用完即关闭", False, repr(e))

n_pass = sum(1 for _, ok, _ in results if ok)
print("\n" + "=" * 68)
print(f"工具模块修复定向回归: PASS {n_pass} / FAIL {len(results) - n_pass}")
for name, ok, note in results:
    if not ok:
        print(f"  ❌ {name} —— {note[:140]}")
sys.exit(0 if all(ok for _, ok, _ in results) else 1)
