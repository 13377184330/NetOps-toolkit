#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
配置健康度诊断（二开新增）
参考业界基线核查规范（配置域 / 配置项 / 基线要求 / 检查方式 / 风险等级 五要素），
对从真机抓回的配置做规则化体检，输出评分 + 风险项清单，全可视化不用读原文。

只做分析、不发送任何命令，天然只读。
"""

import re

# 风险等级
CRITICAL = "严重"   # 安全隐患，建议立即处理
WARNING = "警告"    # 不规范，建议整改
INFO = "提示"       # 优化建议
OK = "通过"

LEVEL_WEIGHT = {CRITICAL: 15, WARNING: 6, INFO: 2, OK: 0}


def _has(text, pattern, flags=re.M):
    return re.search(pattern, text, flags) is not None


def check_health(raw: str, vendor: str = "h3c") -> dict:
    """执行配置体检
    返回 {
      score: 0-100,
      level: 优秀/良好/需改进/高风险,
      items: [{domain, item, baseline, result, level, advice}],
      stats: {严重:n, 警告:n, 提示:n, 通过:n}
    }
    """
    t = raw or ""
    items = []

    def add(domain, item, baseline, passed, level_when_fail, advice):
        items.append({
            "domain": domain,
            "item": item,
            "baseline": baseline,
            "result": OK if passed else level_when_fail,
            "level": OK if passed else level_when_fail,
            "advice": "" if passed else advice,
        })

    # ---------- 1. 身份鉴别 ----------
    ssh_on = _has(t, r"^\s*ssh server enable", re.M) or _has(t, r"^\s*stelnet server enable", re.M) \
        or _has(t, r"^transport input.*ssh", re.M) or _has(t, r"^ip ssh", re.M)
    telnet_on = _has(t, r"^\s*telnet server enable", re.M) or _has(t, r"^transport input.*telnet", re.M)
    add("身份鉴别", "SSH 远程管理", "应启用 SSH 加密远程管理", ssh_on, CRITICAL,
        "执行 ssh server enable（H3C/华为），并配置本地用户与公钥/密码认证")
    add("身份鉴别", "Telnet 明文服务", "应关闭 Telnet（明文传输）", not telnet_on, CRITICAL,
        "执行 undo telnet server enable 关闭 Telnet，统一改 SSH 管理")

    # ---------- 2. 账号与权限 ----------
    has_local_user = _has(t, r"^\s*local-user\s+\S+", re.M) or _has(t, r"^username\s+\S+", re.M)
    add("账号与权限", "本地管理员账号", "应配置具名管理员账号并分权", has_local_user, WARNING,
        "创建具名 local-user，按角色分权（network-admin 仅限少数人）")
    weak_pwd = _has(t, r"password\s+(simple\s+)?(admin|123456|huawei|h3c|cisco|password)\b", re.M | re.I)
    add("账号与权限", "弱口令检测", "禁止 admin/123456 等弱口令", not weak_pwd, CRITICAL,
        "立即修改弱口令，使用 cipher 加密存储")
    all_admin_line = len(re.findall(r"user-role\s+network-admin", t)) >= 3
    add("账号与权限", "线路权限收敛", "VTY/AUX 线路应按需授权，不宜全部 admin",
        not all_admin_line, WARNING, "将 VTY 线路角色降为 network-operator，按需提权")

    # ---------- 3. 日志与审计 ----------
    log_on = _has(t, r"^\s*info-center enable", re.M) or not _has(t, r"undo info-center enable", re.M)
    add("日志审计", "日志中心", "应启用 info-center 并配置日志主机", log_on, WARNING,
        "执行 info-center enable，并配置 info-center loghost <日志服务器IP>")
    ntp_on = _has(t, r"ntp-service unicast-server", re.M) or _has(t, r"^ntp server", re.M)
    add("日志审计", "NTP 时间同步", "应配置 NTP，保证日志时间可追溯", ntp_on, INFO,
        "配置 ntp-service unicast-server <NTP服务器>，确保日志时间准确")

    # ---------- 4. SNMP ----------
    snmp_community_default = _has(t, r"snmp-agent community\s+(read|write)?\s*(public|private)", re.M | re.I)
    insec_snmp = _has(t, r"snmp-agent.*(v1|v2c)", re.M | re.I) or _has(t, r"snmp-server community", re.M)
    add("SNMP", "默认团体字", "禁止使用 public/private 团体字", not snmp_community_default, CRITICAL,
        "修改 SNMP 团体字为强口令，或升级为 SNMPv3（认证+加密）")
    add("SNMP", "SNMP 安全版本", "建议使用 SNMPv3", not insec_snmp, INFO,
        "在支持时迁移至 SNMPv3，配置认证与加密")

    # ---------- 5. 二层安全 ----------
    stp_on = _has(t, r"stp global enable", re.M) or _has(t, r"^stp enable", re.M) or _has(t, r"spanning-tree", re.M)
    add("二层安全", "生成树防环", "应启用 STP/MSTP 防环", stp_on, WARNING,
        "启用 stp global enable，核心设为根桥")
    bpdu_guard = _has(t, r"stp bpdu-protection", re.M)
    add("二层安全", "BPDU 保护", "接入端口应启用 BPDU 保护防攻击", bpdu_guard, INFO,
        "全局 stp bpdu-protection，防非法 BPDU 环路攻击")
    port_sec = _has(t, r"port-security", re.M)
    add("二层安全", "端口安全", "接入口建议启用端口安全（限制 MAC 数）", port_sec, INFO,
        "在接入端口启用 port-security max-mac-count，防 MAC 泛洪")

    # ---------- 6. VLAN 隔离 ----------
    vlan_count = len(re.findall(r"^vlan\s+\d+", t, re.M))
    all_in_vlan1 = vlan_count <= 1
    add("VLAN 规划", "业务 VLAN 划分", "业务应独立 VLAN，避免全部在 VLAN1", not all_in_vlan1, WARNING,
        "按业务/部门划分 VLAN，接入端口 port access vlan 指定")

    # ---------- 7. 管理面 ----------
    mgmt_ip = _has(t, r"^\s*ip address\s+\d+\.", re.M) or _has(t, r"interface (Vlan-interface|Vlanif|LoopBack)", re.M)
    add("管理面", "管理 IP", "应配置管理地址便于远程维护", mgmt_ip, WARNING,
        "配置管理 VLAN 及 Vlan-interface IP，专用管理网段")
    acl_on_vty = _has(t, r"ssh|telnet", re.M) and _has(t, r"acl\s+\d+.*inbound|acl apply", re.M)
    add("管理面", "远程登录 ACL 限制", "远程管理应配置 ACL 源地址限制", acl_on_vty, WARNING,
        "配置 ACL 限定管理源地址，并应用到 VTY 线路")

    # ---------- 8. 冗余与可用性 ----------
    link_agg = _has(t, r"link-aggregation|interface Bridge-Aggregation|port-channel", re.M)
    add("可用性", "链路聚合", "核心互联建议链路聚合提升带宽与冗余", link_agg, INFO,
        "核心/汇聚互联使用 link-aggregation 做链路冗余")
    vrrp = _has(t, r"vrrp", re.M)
    add("可用性", "网关冗余", "双核心场景建议 VRRP 网关冗余", vrrp, INFO,
        "双核心部署 VRRP 提供网关冗余")

    # ---------- 评分 ----------
    stats = {CRITICAL: 0, WARNING: 0, INFO: 0, OK: 0}
    for it in items:
        stats[it["level"]] += 1
    score = 100
    for it in items:
        if it["level"] != OK:
            score -= LEVEL_WEIGHT.get(it["level"], 0)
    score = max(0, min(100, score))

    if score >= 90:
        level = "优秀"
    elif score >= 75:
        level = "良好"
    elif score >= 60:
        level = "需改进"
    else:
        level = "高风险"

    return {"score": score, "level": level, "items": items, "stats": stats}


if __name__ == "__main__":
    demo = """
 sysname H3a
#
 telnet server enable
#
 interface Vlan-interface1
  ip address 192.168.0.233 255.255.255.0
#
 stp global enable
#
 local-user admin
  password simple admin
#
"""
    r = check_health(demo)
    print("评分:", r["score"], r["level"], r["stats"])
    for it in r["items"]:
        if it["level"] != OK:
            print(f"  [{it['level']}] {it['domain']} - {it['item']}: {it['advice']}")
