#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
一键标准化开局（对标 NetCMD 的「一键标准化开局」）
按"新交换机上线"的固定顺序生成全套配置：命名 → 管理VLAN/SVI → 默认路由 →
SSH 账号 → NTP → 日志外送 → MSTP 加固 → 保存提示。
字段少、默认值合理，填 3 个值就能出全套。
"""

try:
    from modules.nl_engine import (e_hostname, e_iface, e_login, e_ntp, e_route,
                                   e_syslog, e_vlan_create)
except ImportError:  # 直接运行自测
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    from modules.nl_engine import (e_hostname, e_iface, e_login, e_ntp, e_route, e_syslog, e_vlan_create)

# (key, 显示名, 默认值)
FIELDS = [
    ("name", "设备名称", "Access-01F-03"),
    ("vlan", "管理 VLAN", "30"),
    ("ip", "管理 IP", "10.10.3.2"),
    ("mask", "子网掩码", "255.255.255.0"),
    ("gw", "默认网关", "10.10.3.1"),
    ("user", "管理员账号", "admin"),
    ("pwd", "管理员密码", "Admin@123"),
    ("ntp", "NTP 服务器（可空）", "10.10.0.10"),
    ("syslog", "日志服务器（可空）", "10.10.0.11"),
]


def build(vendor, p):
    """参数 → [(cmd, 注释)]，按标准开局顺序"""
    name = p.get("name", "").strip() or "Access-01"
    vid = (p.get("vlan", "") or "1").strip()
    ip, mask = p.get("ip", "").strip(), p.get("mask", "").strip() or "255.255.255.0"
    gw = p.get("gw", "").strip()
    user = p.get("user", "").strip() or "admin"
    pwd = p.get("pwd", "").strip() or "Admin@123"
    ntp, syslog = p.get("ntp", "").strip(), p.get("syslog", "").strip()
    vrp = vendor in ("huawei", "h3c")

    lines = []
    # 1) 命名
    lines += e_hostname(vendor, name)
    # 2) 管理 VLAN + SVI
    if vid != "1":
        lines += e_vlan_create(vendor, [vid])
    if ip:
        svi = (f"Vlanif{vid}" if vendor == "huawei"
               else (f"Vlan-interface{vid}" if vendor == "h3c" else f"Vlan{vid}"))
        lines += e_iface(vendor, svi, ip, mask)
    # 3) 默认路由
    if gw:
        lines += e_route(vendor, "0.0.0.0", "0.0.0.0", gw)
    # 4) 登录（SSH）
    lines += e_login(vendor, user, pwd, ssh=True, telnet=False)
    # 5) 时间同步
    if ntp:
        lines += e_ntp(vendor, ntp)
    # 6) 日志外送
    if syslog:
        lines += e_syslog(vendor, syslog)
    # 7) MSTP 基础加固
    if vrp:
        lines += [("system-view", "进入系统视图"),
                  ("stp mode mstp", "生成树模式 MSTP（默认即是，显式确认）"),
                  ("stp enable", "使能生成树"),
                  ("stp bpdu-protection", "全局 BPDU 保护（边缘口收到 BPDU 即关闭）")]
    else:
        lines += [("configure terminal", "进入配置模式"),
                  ("spanning-tree mode mst", "生成树模式 MSTP"),
                  ("spanning-tree portfast bpduguard default", "全局边缘口 + BPDU 保护")]
    # 8) 保存
    lines.append(("save" if vrp else "write memory", "保存配置（设备会提示确认）"))
    return lines


if __name__ == "__main__":
    import io
    import sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    params = {k: v for k, _l, v in FIELDS}
    for v in ("huawei", "h3c", "cisco"):
        lines = build(v, params)
        assert any("sysname" in c or "hostname" in c for c, _ in lines)
        assert any("0.0.0.0" in c for c, _ in lines)
        print(f"===== {v} : {len(lines)} 行 =====")
    print("\n华为全套：")
    for c, n in build("huawei", params):
        print(f"{c:<52} # {n}")
    print("开局模板自测通过")