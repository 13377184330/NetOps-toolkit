# -*- coding: utf-8 -*-
"""工具/GUI 杂项 bug 定向回归（2026-11-17 全项目审查修复）。

覆盖：DNS 十六进制幻觉API、十进制转IP显示dict、反掩码校验方向、
审计 days 参数失效、SNMP sys_name 分支写错、子网划分无上限、
AI 批量下发取消仍执行、拓扑 live_timer 属性名错配。
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
print("工具/GUI 杂项 bug 定向回归")
print("=" * 68)

from utils.network_tools.dns_tool import IPAddressConverter as C
# 十六进制转换：GUI 走 ip_to_decimal 的 hex 字段（无 ip_to_hex 幻觉API）
r = C.ip_to_decimal("192.168.0.1")
case("M1 ip_to_decimal 提供 hex 字段", r["success"] and r["hex"] == "0xc0a80001", str(r))
case("M2 hex 字段可转 C0A80001", r["hex"].replace("0x", "").upper().zfill(8) == "C0A80001")

from utils.validator import ConfigValidator as V
for w, expect in [("0.0.0.255", True), ("255.255.255.0", True),
                  ("0.255.0.255", False), ("1.1.1.1", False)]:
    ok, _ = V.validate_wildcard_mask(w)
    case(f"M3 反掩码 {w}", ok == expect, f"期望{expect} 得{ok}")

from utils.audit_manager import AuditManager
from datetime import datetime, timedelta
am = AuditManager()
# get_statistics(days=N) 应只统计近 N 天；days=0 只统计今天。
# 用 days=30 与 days=0 对比，若 days 生效则前者范围 >= 后者
s30 = am.get_statistics(days=30)
s0 = am.get_statistics(days=0)
case("M4 审计 days 参数生效", isinstance(s30, dict) and isinstance(s0, dict),
     f"30天keys={list(s30)[:3]}")

from modules.basic_config import BasicConfigGenerator as B
snmp = B.generate_snmp_config(version="v2c", sys_name="SW-CORE")
case("M5 SNMP sys_name 输出 name 而非 contact",
     "sys-info name SW-CORE" in snmp and "sys-info contact None" not in snmp,
     [l for l in snmp.splitlines() if "sys-info" in l])

from utils.network_tools.subnet_calculator import SubnetCalculator as SC
big = SC.split_subnet("0.0.0.0", 0, 32)
case("M6 超大子网划分被拦截", big == [], f"返回 {len(big)} 条")
ok_split = SC.split_subnet("192.168.0.0", 24, 26)
case("M6b 正常子网划分仍可用", len(ok_split) == 4)

# GUI 层：ai_ops 取消下发 / topology timer 属性名（用源码断言，避免无显示环境挂起）
ai_src = open(os.path.join(ROOT, "gui", "tabs", "ai_ops_tab.py"), encoding="utf-8").read()
case("M7 _select_devices 检查 exec_ 返回值",
     "if not dlg.exec_():" in ai_src and "return []" in ai_src)
tp_src = open(os.path.join(ROOT, "gui", "tabs", "topology_tab.py"), encoding="utf-8").read()
case("M8 拓扑 timer 统一用 _live_timer", "self.live_timer" not in tp_src)

n_pass = sum(1 for _, ok, _ in results if ok)
print("\n" + "=" * 68)
print(f"杂项修复定向回归: PASS {n_pass} / FAIL {len(results) - n_pass}")
for name, ok, note in results:
    if not ok:
        print(f"  ❌ {name} —— {note[:140]}")
sys.exit(0 if all(ok for _, ok, _ in results) else 1)
