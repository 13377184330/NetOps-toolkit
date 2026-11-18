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

import modules.ipam as _ipam
import tempfile, shutil
# 真正调用被测函数 suggest_free（此前的假绿：只重写了一遍惰性循环，
# 从未触碰被测函数）。隔离到临时账本，登记 /8 后计时；若有人改回
# list(network.hosts()) 全量物化，这里会耗时数秒 → 超时失败。
_d = tempfile.mkdtemp()
_orig_file = _ipam.IPAM_FILE
_ipam.IPAM_FILE = os.path.join(_d, "ipam.json")
try:
    _ipam.add_subnet("10.0.0.0/8", name="test")
    t0 = time.time()
    first = _ipam.suggest_free("10.0.0.0/8")
    elapsed = time.time() - t0
    case("U4 大网段惰性取可用IP(无全量物化)",
         first == "10.0.0.2" and elapsed < 2.0,
         f"首IP={first} 耗时={elapsed:.2f}s")
finally:
    _ipam.IPAM_FILE = _orig_file
    shutil.rmtree(_d, ignore_errors=True)

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
        # 必须断言调用次数：否则实现改成根本不建 loop 时 loops=[]，
        # all([]) 恒真会造成假绿。
        case("U6 SNMP loop 用完即关闭",
             len(loops) == 3 and all(lp.is_closed() for lp in loops),
             f"调用{len(loops)}次 closed={[lp.is_closed() for lp in loops]}")
    else:
        # 本机未装 pysnmp：明确标 SKIP，不计入 PASS（避免"跳过伪装成通过"）
        print("  SKIP  U6 SNMP loop（pysnmp 未安装，无法验证）")
except Exception as e:
    case("U6 SNMP loop 用完即关闭", False, repr(e))

n_pass = sum(1 for _, ok, _ in results if ok)
print("\n" + "=" * 68)
print(f"工具模块修复定向回归: PASS {n_pass} / FAIL {len(results) - n_pass}")
for name, ok, note in results:
    if not ok:
        print(f"  ❌ {name} —— {note[:140]}")
sys.exit(0 if all(ok for _, ok, _ in results) else 1)
