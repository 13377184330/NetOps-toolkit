#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""一键回归跑批器：顺序执行 tests/ 下全部 test_*.py，逐项 PASS/FAIL 汇总。
用法：
    python tests/run_tests.py             # 全量
    python tests/run_tests.py test_ai     # 名字含 test_ai 的子集
依赖：PyQt5/netmiko/paramiko/requests/pyserial（pysnmp 可选）+ Windows 字体目录。"""

import io
import os
import subprocess
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def main():
    pattern = sys.argv[1] if len(sys.argv) > 1 else ""
    tests = sorted(f for f in os.listdir(HERE)
                   if f.startswith("test_") and f.endswith(".py")
                   and pattern in f and f != os.path.basename(__file__))
    if not tests:
        print(f"未找到匹配「{pattern}」的测试")
        return 1

    env = dict(os.environ)
    # 离屏无头：不弹窗、CI/无人值守友好（每个脚本内部也自设，此处兜底）
    env.setdefault("QT_QPA_PLATFORM", "offscreen")

    results, t_all = [], time.time()
    for t in tests:
        t0 = time.time()
        r = subprocess.run([sys.executable, os.path.join(HERE, t)],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", cwd=ROOT, timeout=900, env=env)
        ok = r.returncode == 0
        dt = time.time() - t0
        results.append((t, ok, dt))
        tail = (r.stdout or "").strip().splitlines()
        last = tail[-1][:66] if tail else (r.stderr or "").strip().splitlines()[-1][:66] if r.stderr.strip() else ""
        print(f"  {'PASS' if ok else 'FAIL'}  {t:<32} {dt:5.1f}s  {last}")

    n_pass = sum(1 for _, ok, _ in results if ok)
    print("\n" + "=" * 66)
    print(f"回归汇总: PASS {n_pass} / FAIL {len(results) - n_pass}"
          f"（总 {time.time() - t_all:.0f}s）")
    for t, ok, _ in results:
        if not ok:
            print(f"  ❌ {t}")
    return 0 if n_pass == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
