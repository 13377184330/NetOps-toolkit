#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ARP 内网扫描 —— 局域网活动设备发现 + 虚拟 IP 风险检测

方案来源（先调研再实现，2026-11-20）：
- GitHub royhills/arp-scan（GPLv3，C 语言）：业界标准 ARP 扫描器，原理为二层 ARP
  广播请求 + 应答收集，同 IP 多 MAC 直接报 IP 冲突。Windows 需 WinPcap/Npcap 驱动，
  无法直接搬进"绿色离线零依赖"的 PyQt5 工具 → 借鉴其检测规则。
- Python 社区主流 scapy 广播 ARP 方案同样依赖 Npcap，重依赖违背本项目
  「内网离线、零额外依赖」红线 → 不用。
- 采用「多线程 ping 全网段激发 + 读取本机 ARP 缓存表」零依赖实现（CSDN/51cto
  多篇实测文章、Home Assistant arpscan_tracker 同思路）：Windows 发 ping 前必须
  先做 ARP 解析，即使目标防火墙拦截 ICMP，二层 ARP 应答仍会写入本机 ARP 缓存
  → ping 是"激发器"，ARP 表才是"收集器"，拦 ping 的设备也逃不掉。

功能：
- 自动识别本机网卡/网段/网关，多线程 ping 激发 → ARP 缓存收集活动设备（IP/MAC/厂商）
- NetBIOS 主机名解析（Windows nbtstat，尽力而为，失败静默）
- 设备名册（MAC/IP → 姓名·备注，本地 JSON）——ARP 协议本身拿不到姓名，
  业界工具（Angry IP Scanner 等）同样靠本地登记，本项目做成名册自动回填
- 虚拟 IP 风险检测：
  * 同 IP 多 MAC → IP 冲突 / ARP 欺骗（高危）
  * 同 MAC 多 IP → 虚拟机 / 虚拟网卡（按 OUI 识别）或多地址设备
  * 网关 MAC 与上次扫描记录不一致 → 疑似 ARP 欺骗
  * 随机化 MAC（本地管理位）识别（手机隐私 MAC / Windows 随机硬件地址）
- 只读红线：仅 ping / nbtstat / arp -a 只读探测，无任何写操作
"""

import ipaddress
import json
import os
import platform
import re
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from utils.app_paths import app_root
from utils.network_tools.ping_tool import PingTool

ROSTER_FILE = os.path.join(app_root(), "config", "arp_roster.json")
GW_HISTORY_FILE = os.path.join(app_root(), "config", "arp_gateway_history.json")

# ---------------- OUI 厂商库（离线） ----------------
# 虚拟化/虚拟网卡前缀（IEEE 公开注册，确定性高）：虚拟 IP 判断的关键依据
VIRTUAL_OUI = {
    "000569": "VMware", "000C29": "VMware", "001C14": "VMware", "005056": "VMware",
    "080027": "VirtualBox", "00155D": "Hyper-V", "525400": "KVM/QEMU",
    "001C42": "Parallels", "00163E": "Xen",
}

# 常见厂商速查（与 gui/tools/mac_tool.py 同源数据子集 + 网络设备；
# 未命中留空，不猜测）
LOCAL_OUI = {
    "001A2C": "Huawei", "001A2D": "Huawei", "002568": "Huawei", "00E0FC": "Huawei",
    "001E10": "H3C", "000FE2": "H3C", "001FC6": "H3C",
    "00000C": "Cisco", "001007": "Cisco", "0018BA": "Cisco",
    "001C0D": "Cisco", "00234E": "Cisco", "002414": "Cisco",
    "002719": "ZTE", "00268C": "ZTE", "002902": "ZTE", "0023EB": "ZTE", "001C44": "ZTE",
    "002275": "TP-Link", "0023CD": "TP-Link", "002522": "TP-Link",
    "0026C6": "TP-Link", "00310E": "TP-Link", "0050DA": "TP-Link",
    "000393": "Apple", "000502": "Apple", "001124": "Apple", "0017F2": "Apple",
    "001E52": "Apple", "0021E9": "Apple", "002312": "Apple", "002436": "Apple",
    "002500": "Apple", "002608": "Apple", "00264A": "Apple",
    "000BCD": "Dell", "001B2B": "Dell", "001C23": "Dell", "0023AE": "Dell",
    "0050B6": "Dell", "001FF3": "Dell",
    "000AF7": "HP", "001083": "HP", "0011FB": "HP", "0014C2": "HP",
    "001635": "HP", "001702": "HP", "0018FE": "HP", "001BB9": "HP",
    "001E0B": "HP", "0021CC": "HP", "002324": "HP", "0024E8": "HP",
    "0025B3": "HP", "00268A": "HP", "948BB6": "HP",
    "000BB4": "Intel", "000CD5": "Intel", "001111": "Intel", "0012F0": "Intel",
    "001302": "Intel", "001676": "Intel", "001AE8": "Intel", "001B21": "Intel",
    "001CBE": "Intel", "001E64": "Intel", "001FF0": "Intel", "0020F3": "Intel",
    "00248C": "Intel", "00265C": "Intel", "E8611F": "Intel",
    "00B0D0": "Microsoft", "0014A5": "Microsoft", "0017FA": "Microsoft",
    "001DD8": "Microsoft", "00215C": "Microsoft", "0023A4": "Microsoft",
    "00260B": "Microsoft", "7C1E52": "Microsoft",
    "00055B": "D-Link", "000D88": "D-Link", "001195": "D-Link",
    "001346": "D-Link", "0015E9": "D-Link", "00179A": "D-Link",
    "001B11": "D-Link", "001CF6": "D-Link", "001E58": "D-Link",
    "000DE9": "Samsung", "0011F6": "Samsung", "0014A8": "Samsung",
    "0017C9": "Samsung", "001A8A": "Samsung", "001CB3": "Samsung", "001E7D": "Samsung",
    "001B63": "Netgear", "000FB5": "Netgear", "00146C": "Netgear",
    "00184D": "Netgear", "001E2A": "Netgear", "001F33": "Netgear",
    "00223F": "Netgear", "0024B2": "Netgear", "008EF2": "Netgear",
    "001D09": "Juniper", "001F12": "Juniper", "00226F": "Juniper",
    "002283": "Juniper", "002319": "Juniper", "0026BB": "Juniper",
}


# ---------------- MAC 处理 ----------------

def clean_mac(mac: str) -> str:
    """任意格式 MAC（-/:/. 分隔、大小写）→ 大写冒号分隔 AA:BB:CC:DD:EE:FF；无效返回空"""
    if not mac:
        return ""
    s = re.sub(r"[^0-9a-fA-F]", "", str(mac)).upper()
    if len(s) != 12:
        return ""
    return ":".join(s[i:i + 2] for i in range(0, 12, 2))


def mac_kind(mac: str) -> str:
    """MAC 分类：normal / broadcast / multicast / locally(本地管理位=随机化常见) / invalid"""
    c = clean_mac(mac)
    if not c:
        return "invalid"
    if c == "FF:FF:FF:FF:FF:FF":
        return "broadcast"
    if c == "00:00:00:00:00:00":
        return "invalid"    # ARP 未完成解析 / 无效条目
    first = int(c[0:2], 16)
    if first & 0x01:
        return "multicast"
    if first & 0x02:
        return "locally"    # 随机化 MAC / 软件虚拟适配器（手机隐私 MAC、Win11 随机硬件地址）
    return "normal"


def lookup_vendor(mac: str) -> str:
    """OUI → 厂商名（虚拟化厂商带标注）；随机化/无效 MAC 返回空"""
    kind = mac_kind(mac)
    if kind in ("locally", "invalid", "broadcast", "multicast"):
        return ""
    oui = clean_mac(mac).replace(":", "")[:6]
    if oui in VIRTUAL_OUI:
        return f"{VIRTUAL_OUI[oui]}（虚拟化）"
    return LOCAL_OUI.get(oui, "")


def is_virtual_mac(mac: str) -> bool:
    oui = clean_mac(mac).replace(":", "")[:6]
    return oui in VIRTUAL_OUI


# 网络设备厂商 OUI（交换机/路由器等，值得纳管到设备清单）
_NETWORK_DEVICE_OUIS = set()
for _ouis in (
        ("001A2C", "001A2D", "002568", "00E0FC"),                # Huawei
        ("001E10", "000FE2", "001FC6"),                          # H3C
        ("00000C", "001007", "0018BA", "001C0D", "00234E", "002414"),  # Cisco
        ("002719", "00268C", "002902", "0023EB", "001C44"),      # ZTE
        ("001D09", "001F12", "00226F", "002283", "002319", "0026BB"),  # Juniper
        ("00055B", "000D88", "001195", "001346", "0015E9",
         "00179A", "001B11", "001CF6", "001E58"),                # D-Link
        ("002275", "0023CD", "002522", "0026C6", "0050DA"),      # TP-Link
        ("001B63", "000FB5", "00146C", "00184D", "001E2A",
         "001F33", "00223F", "0024B2", "008EF2")):               # Netgear
    _NETWORK_DEVICE_OUIS.update(_ouis)


def network_vendor(mac: str) -> str:
    """OUI 命中网络设备厂商 → 返回厂商名；否则空"""
    if mac_kind(mac) != "normal":
        return ""
    oui = clean_mac(mac).replace(":", "")[:6]
    if oui in _NETWORK_DEVICE_OUIS:
        return LOCAL_OUI.get(oui, "")
    return ""


# ---------------- 控制台编码（chcp 检测，模块级缓存） ----------------

_CONSOLE_ENC_CACHE = []


def console_encoding() -> str:
    """检测 Windows 控制台活动代码页：65001=UTF-8（系统开了 Beta UTF-8），否则 GBK。
    实机踩过：开了“使用 Unicode UTF-8 提供全球语言支持”后 ipconfig/arp/nbtstat
    输出全是 UTF-8，固定 GBK 解码会把“接口/以太网”解成乱码导致关键词全失配。"""
    if _CONSOLE_ENC_CACHE:
        return _CONSOLE_ENC_CACHE[0]
    enc = "gbk"
    if platform.system().lower() == "windows":
        try:
            out = subprocess.run(["cmd", "/c", "chcp"], capture_output=True,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
            text = out.stdout.decode("ascii", errors="ignore")
            m = re.search(r"(\d+)\s*$", text)
            if m and int(m.group(1)) == 65001:
                enc = "utf-8"
        except Exception:
            pass
    _CONSOLE_ENC_CACHE.append(enc)
    return enc


# ---------------- 网卡识别 ----------------

_VIRTUAL_DESC_WORDS = ("vmware", "virtualbox", "hyper-v", "vethernet", "virtual",
                       "tap-", "tap_", "loopback", "wintun", "tailscale",
                       "vpn", "bluetooth", "蓝牙", "虚拟", "docker", "veth",
                       "tun", "wg", "virbr", "br-")


def _is_virtual_adapter(name: str, desc: str) -> bool:
    text = f"{name} {desc}".lower()
    return any(w in text for w in _VIRTUAL_DESC_WORDS)


def _ipconfig_kv(line: str):
    """ipconfig 的 '关键词. . . . : 值' 行 → (关键词, 值)；非键值行返回 None"""
    m = re.match(r"\s*([^:：]+?)\s*[.\s]*[:：]\s*(.*\S)?\s*$", line)
    if not m:
        return None
    key = re.sub(r"[.\s]+$", "", m.group(1)).strip()
    return key, (m.group(2) or "").strip()


def get_adapters() -> list:
    """本机网卡信息 → [{name, desc, ip, mask, gateway, mac, virtual}]
    Windows 走 ipconfig /all（中英文都支持），Linux 走 ip 命令。
    """
    if platform.system().lower() == "windows":
        return _get_adapters_windows()
    return _get_adapters_linux()


def _get_adapters_windows() -> list:
    try:
        proc = subprocess.run(["ipconfig", "/all"], capture_output=True,
                              creationflags=subprocess.CREATE_NO_WINDOW)
        out = proc.stdout.decode(console_encoding(), errors="ignore")
    except Exception:
        return []

    adapters, cur = [], None
    for line in out.splitlines():
        stripped = line.rstrip()
        # 适配器标题行：'以太网适配器 以太网:' / 'Ethernet adapter Ethernet:'
        title = None
        if stripped.endswith((":", "：")):
            probe = _ipconfig_kv(stripped)
            if probe and ("适配器" in probe[0] or "adapter" in probe[0].lower()):
                title = probe[0]
        if title:
            if cur and cur.get("ip"):
                adapters.append(cur)
            cur = {"name": title, "desc": "", "ip": "", "mask": "",
                   "gateway": "", "mac": "", "virtual": False}
            continue
        kv = _ipconfig_kv(line)
        if not kv or cur is None:
            continue
        key, val = kv
        kl = key.lower()
        if not val:
            continue
        if "物理地址" in key or "physical address" in kl:
            cur["mac"] = clean_mac(val) or cur["mac"]
        elif "描述" in key or "description" in kl:
            cur["desc"] = val
        elif "ipv4" in kl:
            m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", val)
            if m:
                # 普通 IPv4 优先于 APIPA 自动配置地址（169.254.x：网卡未连上时的自配址）
                is_auto = "autoconfiguration" in kl or "自动配置" in key
                cur_auto = cur.get("_ip_auto", False)
                if (not cur["ip"]) or (cur_auto and not is_auto):
                    cur["ip"] = m.group(1)
                    cur["_ip_auto"] = is_auto
        elif "子网掩码" in key or "subnet mask" in kl:
            m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", val)
            if m and not cur["mask"]:
                cur["mask"] = m.group(1)
        elif "默认网关" in key or "default gateway" in kl:
            m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", val)
            if m and not cur["gateway"]:
                cur["gateway"] = m.group(1)
    if cur and cur.get("ip"):
        adapters.append(cur)
    for a in adapters:
        a["virtual"] = _is_virtual_adapter(a["name"], a["desc"])
        a.pop("_ip_auto", None)
    # IPv4 网关兜底：部分机器（IPv6 网关 + DHCP 下发场景）ipconfig 的
    # Default Gateway 行只有 fe80::%idx，IPv4 网关要从 route print 的
    # 0.0.0.0 路由拿才权威（route print -4 第一个 0.0.0.0 行 metric 最低）
    try:
        rp = subprocess.run(["route", "print", "-4"], capture_output=True,
                            creationflags=subprocess.CREATE_NO_WINDOW)
        rp_out = rp.stdout.decode(console_encoding(), errors="ignore")
    except Exception:
        rp_out = ""
    for line in rp_out.splitlines():
        m = re.match(
            r"\s*0\.0\.0\.0\s+0\.0\.0\.0\s+(\d{1,3}(?:\.\d{1,3}){3})\s+(\d{1,3}(?:\.\d{1,3}){3})",
            line)
        if not m:
            continue
        gw_ip, iface_ip = m.group(1), m.group(2)
        for a in adapters:
            if a["ip"] == iface_ip and not a["gateway"]:
                a["gateway"] = gw_ip
        break   # 取第一条（metric 最低）默认路由即可
    # 物理（非虚拟）有 IP 的排前面
    adapters.sort(key=lambda a: (a["virtual"], not a["gateway"]))
    return [a for a in adapters if a["ip"]]


def _get_adapters_linux() -> list:
    """Linux：ip -4 addr + ip route（尽力而为）"""
    adapters, cur = [], None
    try:
        out = subprocess.run(["ip", "-o", "-4", "addr"], capture_output=True,
                             text=True).stdout
        for line in out.splitlines():
            m = re.match(r"\d+:\s*(\S+)\s+inet\s+(\d+\.\d+\.\d+\.\d+)/(\d+)", line)
            if not m:
                continue
            ifname, ip, prefix = m.group(1), m.group(2), int(m.group(3))
            adapters.append({
                "name": ifname, "desc": "", "ip": ip,
                "mask": str(ipaddress.ip_network(f"0.0.0.0/{prefix}", strict=False).netmask),
                "gateway": "", "mac": "",
                "virtual": _is_virtual_adapter(ifname, ""),
            })
    except Exception:
        pass
    try:
        out = subprocess.run(["ip", "route"], capture_output=True, text=True).stdout
        for line in out.splitlines():
            m = re.match(r"default via (\d+\.\d+\.\d+\.\d+)", line)
            if not m:
                continue
            m2 = re.search(r"dev\s+(\S+)", line)
            if m2:
                for a in adapters:
                    if a["name"] == m2.group(1) and not a["gateway"]:
                        a["gateway"] = m.group(1)
    except Exception:
        pass
    adapters.sort(key=lambda a: (a["virtual"], not a["gateway"]))
    return [a for a in adapters if a["ip"]]


def ip_to_cidr(ip: str, mask: str) -> str:
    """IP + 子网掩码 → 网段 CIDR（192.168.1.100 + 255.255.255.0 → 192.168.1.0/24）"""
    try:
        net = ipaddress.ip_network(f"{ip}/{mask}", strict=False)
        return str(net)
    except ValueError:
        return ""


# ---------------- ARP 缓存表读取 ----------------

def _valid_ip(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
        return a.version == 4
    except ValueError:
        return False


def _keep_arp_row(ip: str, mac: str) -> bool:
    """ARP 条目过滤：广播/多播/组播段/无效 MAC 不收"""
    mac = clean_mac(mac)
    if not _valid_ip(ip) or not mac:
        return False
    kind = mac_kind(mac)
    if kind in ("broadcast", "multicast", "invalid"):
        return False
    try:
        if ipaddress.ip_address(ip) in ipaddress.ip_network("224.0.0.0/4"):
            return False
        if ip == "255.255.255.255":
            return False
    except ValueError:
        return False
    return True


def parse_arp_output_windows(out: str) -> list:
    """解析 Windows `arp -a` 输出（中英文均可）→ [{ip, mac, arp_type, interface}]"""
    rows = []
    iface = ""
    for line in out.splitlines():
        m = re.match(r"\s*(?:接口|Interface)\s*[:：]\s*(.+)", line, re.IGNORECASE)
        if m:
            iface = m.group(1).strip()
            # 只保留 IPv4 接口：IPv6 接口行（[fe80::...]）与尾部索引号不参与
            ip_m = re.match(r"(\d{1,3}(?:\.\d{1,3}){3})", iface)
            iface = ip_m.group(1) if ip_m else ""
            continue
        m = re.match(
            r"\s*(\d{1,3}(?:\.\d{1,3}){3})\s+((?:[0-9A-Fa-f]{2}[-:]){5}[0-9A-Fa-f]{2})\s+(\S+)",
            line)
        if not m:
            continue
        ip, mac, atype = m.group(1), clean_mac(m.group(2)), m.group(3)
        if _keep_arp_row(ip, mac):
            rows.append({"ip": ip, "mac": mac, "arp_type": atype, "interface": iface})
    return rows


def parse_proc_net_arp(content: str) -> list:
    """解析 Linux /proc/net/arp 内容 → [{ip, mac, arp_type, interface}]"""
    rows = []
    for line in content.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 6:
            continue
        ip, mac, flags, dev = parts[0], parts[3], parts[2], parts[5]
        try:
            if int(flags, 16) & 0x2 == 0:   # ATF_COM 未完成解析
                continue
        except ValueError:
            continue
        if _keep_arp_row(ip, mac):
            rows.append({"ip": ip, "mac": clean_mac(mac), "arp_type": "dynamic",
                         "interface": dev})
    return rows


def read_arp_table() -> list:
    """读本机 ARP 缓存 → [{ip, mac, arp_type, interface}]
    过滤广播/多播/全零/无效 MAC 条目；dynamic(动态)/static(静态) 均保留并标注。
    """
    if platform.system().lower() == "windows":
        try:
            proc = subprocess.run(["arp", "-a"], capture_output=True,
                                  creationflags=subprocess.CREATE_NO_WINDOW)
            out = proc.stdout.decode(console_encoding(), errors="ignore")
        except Exception:
            return []
        return parse_arp_output_windows(out)
    # Linux: /proc/net/arp
    try:
        with open("/proc/net/arp", "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except OSError:
        return []
    return parse_proc_net_arp(content)


# ---------------- ping 激发（实时进度） ----------------

def ping_sweep_progress(hosts: list, timeout_s: int = 1, workers: int = 100,
                        progress_cb=None, stop_flag=None) -> list:
    """多线程 ping（1 包）激发 ARP 解析；progress_cb(done, total, result) 逐台实时回调。
    协作式停止：stop_flag 置位后 kill 子进程并取消剩余任务（复用 PingTool 注册表）。
    返回 ping 成功的结果列表（仅统计用——真正收设备靠 ARP 表）。
    """
    alive = []
    done = 0
    total = len(hosts)
    if total == 0:
        return alive
    ex = ThreadPoolExecutor(max_workers=max(1, workers))
    try:
        futs = {ex.submit(PingTool.ping, h, 1, max(1, timeout_s)): h for h in hosts}
        for fut in as_completed(futs):
            try:
                r = fut.result()
            except Exception:
                r = None
            done += 1
            if r and r.get("success"):
                alive.append(r)
            if progress_cb:
                try:
                    progress_cb(done, total, r)
                except Exception:
                    pass
            if stop_flag is not None and stop_flag.is_set():
                PingTool.stop_all()
                ex.shutdown(wait=False, cancel_futures=True)
                break
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    return alive


# ---------------- NetBIOS 主机名（尽力而为） ----------------

def get_nbt_name(ip: str, timeout: float = 3.0) -> str:
    """Windows nbtstat -A 解析 NetBIOS 计算机名（第一个 <00> UNIQUE 条目）。
    仅 Windows 有效；设备无 NetBIOS/超时 → 返回空串（不视为错误）。
    """
    if platform.system().lower() != "windows":
        return ""
    try:
        proc = subprocess.run(["nbtstat", "-A", ip], capture_output=True,
                              timeout=timeout,
                              creationflags=subprocess.CREATE_NO_WINDOW)
        out = proc.stdout.decode(console_encoding(), errors="ignore")
    except Exception:
        return ""
    for line in out.splitlines():
        m = re.match(r"\s*(\S+)\s+<00>\s+(?:唯一|UNIQUE)", line, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            # 排除 MAC 地址列误匹配（长度 17 且含 - 的行不会进 <00> 格式，双保险）
            if name and len(name) <= 15:
                return name
    return ""


# ---------------- 设备名册（姓名映射，本地 JSON） ----------------

def load_roster() -> dict:
    if os.path.exists(ROSTER_FILE):
        try:
            with open(ROSTER_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("entries"), list):
                return data
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            pass
    return {"entries": []}


def _save_roster(data):
    try:
        os.makedirs(os.path.dirname(ROSTER_FILE), exist_ok=True)
        with open(ROSTER_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def match_roster(ip: str = "", mac: str = "") -> dict:
    """按 MAC 优先、IP 兜底匹配名册 → {name, note}；未命中返回空"""
    data = load_roster()
    mac_k = clean_mac(mac)
    for e in data["entries"]:
        if mac_k and clean_mac(e.get("mac", "")) == mac_k:
            return {"name": e.get("name", ""), "note": e.get("note", "")}
    ip_s = (ip or "").strip()
    if ip_s:
        for e in data["entries"]:
            if not e.get("mac") and e.get("ip", "") == ip_s:
                return {"name": e.get("name", ""), "note": e.get("note", "")}
    return {"name": "", "note": ""}


def upsert_roster(mac: str = "", ip: str = "", name: str = "", note: str = "") -> dict:
    """登记/更新名册条目（MAC 或 IP 至少一项；同 MAC 同 IP 视为同一条目）"""
    mac_k = clean_mac(mac)
    ip_s = (ip or "").strip()
    name_s = (name or "").strip()
    note_s = (note or "").strip()
    if not mac_k and not ip_s:
        return {"ok": False, "error": "MAC 与 IP 至少填一项"}
    if not name_s and not note_s:
        return {"ok": False, "error": "姓名与备注至少填一项"}
    data = load_roster()
    for e in data["entries"]:
        same_mac = mac_k and clean_mac(e.get("mac", "")) == mac_k
        same_ip = (not mac_k and ip_s and not e.get("mac") and e.get("ip") == ip_s)
        if same_mac or same_ip:
            if name_s:
                e["name"] = name_s
            if note_s:
                e["note"] = note_s
            if mac_k and not e.get("mac"):
                e["mac"] = mac_k
            if ip_s and not e.get("ip"):
                e["ip"] = ip_s
            e["at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            _save_roster(data)
            return {"ok": True, "updated": True}
    data["entries"].append({
        "mac": mac_k, "ip": ip_s, "name": name_s, "note": note_s,
        "at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })
    _save_roster(data)
    return {"ok": True, "updated": False}


def remove_roster(mac: str = "", ip: str = "") -> bool:
    data = load_roster()
    mac_k = clean_mac(mac)
    before = len(data["entries"])
    data["entries"] = [
        e for e in data["entries"]
        if not ((mac_k and clean_mac(e.get("mac", "")) == mac_k)
                or (not mac_k and ip and not e.get("mac") and e.get("ip") == ip))
    ]
    if len(data["entries"]) < before:
        _save_roster(data)
        return True
    return False


# ---------------- 网关 MAC 历史（ARP 欺骗比对） ----------------

def load_gateway_history() -> dict:
    if os.path.exists(GW_HISTORY_FILE):
        try:
            with open(GW_HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("gateways"), dict):
                return data
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            pass
    return {"gateways": {}}


def record_gateway(ip: str, mac: str) -> str:
    """记录网关 MAC，返回上一个已知 MAC（无则空串）"""
    if not ip or not clean_mac(mac):
        return ""
    data = load_gateway_history()
    prev = data["gateways"].get(ip, {}).get("mac", "")
    data["gateways"][ip] = {"mac": clean_mac(mac), "at": datetime.now().strftime("%Y-%m-%d %H:%M")}
    try:
        os.makedirs(os.path.dirname(GW_HISTORY_FILE), exist_ok=True)
        with open(GW_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        pass
    return prev


# ---------------- 风险分析（虚拟 IP 判断核心） ----------------

def analyze(devices: list, gateway_ip: str = "", prev_gateway_mac: str = "") -> list:
    """就地给 devices 元素补 tags，返回风险列表。
    规则（与 arp-scan / 主流 ARP 欺骗检测文章一致）：
    1. 同 IP 多 MAC → IP 冲突 / ARP 欺骗（danger）
    2. 同 MAC 多 IP → 虚拟机（OUI 可证）或疑代理共享（warning）
    3. 网关 MAC 与上次扫描不同 → 疑 ARP 欺骗（danger）
    """
    by_ip = {}
    by_mac = {}
    for d in devices:
        if d.get("mac"):
            by_ip.setdefault(d["ip"], set()).add(d["mac"])
            by_mac.setdefault(d["mac"], []).append(d["ip"])

    risks = []
    for ip, macs in by_ip.items():
        if len(macs) > 1:
            risks.append({
                "level": "danger", "type": "ip_conflict", "ip": ip,
                "macs": sorted(macs),
                "text": f"IP {ip} 同时被 {len(macs)} 个 MAC 声明（{'、'.join(sorted(macs))}）→ IP 冲突或 ARP 欺骗",
            })
            for d in devices:
                if d["ip"] == ip:
                    d.setdefault("tags", []).append("⚠ IP冲突/欺骗")
    for mac, ips in by_mac.items():
        if len(ips) > 1:
            if is_virtual_mac(mac):
                vendor = VIRTUAL_OUI[mac.replace(":", "")[:6]]
                risks.append({
                    "level": "info", "type": "virtual_multiip", "mac": mac,
                    "ips": sorted(ips),
                    "text": f"{mac}（{vendor} 虚拟化）占用 {len(ips)} 个 IP（{'、'.join(sorted(ips))}）→ 虚拟机/虚拟网卡，正常现象",
                })
                for d in devices:
                    if d["mac"] == mac:
                        d.setdefault("tags", []).append("虚拟机")
            else:
                risks.append({
                    "level": "warning", "type": "mac_multiip", "mac": mac,
                    "ips": sorted(ips),
                    "text": f"同一 MAC {mac} 占用 {len(ips)} 个 IP（{'、'.join(sorted(ips))}）→ 疑似虚拟机、代理共享或便携热点",
                })
                for d in devices:
                    if d["mac"] == mac:
                        d.setdefault("tags", []).append("⚠ 同MAC多IP")
    if gateway_ip:
        gw = next((d for d in devices if d["ip"] == gateway_ip), None)
        if gw and prev_gateway_mac and gw.get("mac") and gw["mac"] != clean_mac(prev_gateway_mac):
            risks.append({
                "level": "danger", "type": "gateway_mac_changed", "ip": gateway_ip,
                "macs": [prev_gateway_mac, gw["mac"]],
                "text": f"网关 {gateway_ip} 的 MAC 由 {prev_gateway_mac} 变为 {gw['mac']} → 疑似 ARP 欺骗（若网关确已更换可忽略）",
            })
            gw.setdefault("tags", []).append("⚠ 网关MAC漂移")
    return risks


# ---------------- 主流程 ----------------

def _ip_sort_key(ip: str):
    try:
        return tuple(int(x) for x in ip.split("."))
    except Exception:
        return (255, 255, 255, 255)


def _expand_hosts(cidr: str) -> list:
    try:
        net = ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return []
    hosts = [str(h) for h in net.hosts()]
    if net.num_addresses > 65536:
        # 超大网段保护（/15 及以上）——ping 子进程量不可控
        return hosts[:65534]
    return hosts


def scan(cidr: str = "", workers: int = 100, ping_timeout: int = 1,
         nbt_enabled: bool = True, stop_flag: threading.Event = None,
         progress_cb=None, device_cb=None) -> dict:
    """执行一次完整 ARP 扫描。
    progress_cb(phase, done, total)：phase ∈ ping / nbt
    device_cb(device_dict)：每台设备数据就绪即回调（nbt 完成后为完整版）
    返回 {"ok", "error", "cidr", "gateway", "local_ip", "devices", "risks", "stats", "stopped"}
    """
    result = {"ok": False, "error": "", "cidr": "", "gateway": "", "local_ip": "",
              "devices": [], "risks": [], "stats": {}, "stopped": False}

    adapters = get_adapters()
    chosen = None
    if cidr:
        cidr = cidr.strip()
        try:
            ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            result["error"] = f"网段格式不正确：{cidr}（如 192.168.1.0/24）"
            return result
    else:
        # 默认选第一个有网关的物理网卡；都没有则第一个有 IP 的
        for a in adapters:
            if a.get("gateway") and not a.get("virtual"):
                chosen = a
                break
        chosen = chosen or (adapters[0] if adapters else None)
        if not chosen:
            result["error"] = "未检测到可用网卡，请手动指定网段"
            return result
        cidr = ip_to_cidr(chosen["ip"], chosen["mask"])
        if not cidr:
            result["error"] = "无法推导网段（子网掩码异常），请手动指定"
            return result

    result["cidr"] = cidr
    if chosen is None:
        # 手动指定网段时，尽量找 IP 落在该网段的适配器补网关/本机信息
        try:
            net = ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            net = None
        if net:
            for a in adapters:
                try:
                    if ipaddress.ip_address(a["ip"]) in net:
                        chosen = a
                        break
                except ValueError:
                    continue
    if chosen:
        result["gateway"] = chosen.get("gateway", "")
        result["local_ip"] = chosen.get("ip", "")
    gateway_ip = result["gateway"]

    hosts = _expand_hosts(cidr)
    if not hosts:
        result["error"] = "网段内无可用主机位"
        return result

    # 阶段 1：ping 激发（防火墙拦 ICMP 也能靠 ARP 应答收设备）
    if stop_flag is not None and stop_flag.is_set():
        result["stopped"] = True
        return result
    ping_sweep_progress(hosts, timeout_s=max(1, ping_timeout), workers=workers,
                        progress_cb=(lambda d, t, r: progress_cb("ping", d, t)) if progress_cb else None,
                        stop_flag=stop_flag)
    if stop_flag is not None and stop_flag.is_set():
        result["stopped"] = True
        # 停止时仍把已写进缓存的部分收出来，UI 能看到已发现设备
        partial = True
    else:
        partial = False

    # 阶段 2：读 ARP 缓存，过滤目标网段
    try:
        net = ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        net = None
    arp_rows = read_arp_table()
    devices = []
    seen = set()
    for row in arp_rows:
        if net is not None:
            try:
                if ipaddress.ip_address(row["ip"]) not in net:
                    continue
            except ValueError:
                continue
        key = (row["ip"], row["mac"])
        if key in seen:
            continue
        seen.add(key)
        d = {
            "ip": row["ip"], "mac": row["mac"], "arp_type": row.get("arp_type", ""),
            "vendor": lookup_vendor(row["mac"]), "hostname": "",
            "name": "", "note": "", "tags": [],
        }
        kind = mac_kind(row["mac"])
        if kind == "locally":
            d["tags"].append("随机化MAC")
        elif kind == "multicast":
            d["tags"].append("组播MAC")
        if is_virtual_mac(row["mac"]):
            d["tags"].append("虚拟机")
        elif network_vendor(row["mac"]):
            d["tags"].append("疑似网络设备")
        devices.append(d)

    # 本机自己不会出现在 ARP 缓存（自己不解析自己），从网卡信息补上
    if chosen and chosen.get("mac"):
        key = (chosen["ip"], clean_mac(chosen["mac"]))
        if net is not None:
            try:
                in_net = ipaddress.ip_address(chosen["ip"]) in net
            except ValueError:
                in_net = True
        else:
            in_net = True
        if in_net and key not in seen:
            seen.add(key)
            devices.append({
                "ip": chosen["ip"], "mac": clean_mac(chosen["mac"]),
                "arp_type": "local", "vendor": lookup_vendor(chosen["mac"]),
                "hostname": platform.node() or "", "name": "", "note": "",
                "tags": ["本机"],
            })

    # 标注网关
    if gateway_ip:
        for d in devices:
            if d["ip"] == gateway_ip and "默认网关" not in d["tags"]:
                d["tags"].insert(0, "默认网关")

    # 名册匹配（MAC 优先、IP 兜底）
    for d in devices:
        hit = match_roster(ip=d["ip"], mac=d["mac"])
        d["name"] = hit.get("name", "")
        d["note"] = hit.get("note", "")

    # 先全量回调一次（基础版：IP/MAC/厂商/名册）——保证关掉主机名解析时
    # 设备照样上屏（此前 device_cb 只在 nbt 阶段调用，nbt=False 时表格空白）；
    # nbt 阶段每台解析完再回调更新 hostname（GUI 按 ip+mac upsert 同一行）
    if device_cb:
        for d in devices:
            try:
                device_cb(d)
            except Exception:
                pass

    # 阶段 3：NetBIOS 主机名（Windows 尽力而为，可关闭）
    if nbt_enabled and platform.system().lower() == "windows":
        todo = [d for d in devices if not d["hostname"]]
        nbt_done = 0
        nbt_total = len(todo)

        def _fill(d, name):
            d["hostname"] = name

        ex = ThreadPoolExecutor(max_workers=8)
        try:
            futs = {ex.submit(get_nbt_name, d["ip"]): d for d in todo}
            for fut in as_completed(futs):
                d = futs[fut]
                try:
                    name = fut.result()
                except Exception:
                    name = ""
                _fill(d, name)
                nbt_done += 1
                if progress_cb:
                    try:
                        progress_cb("nbt", nbt_done, nbt_total)
                    except Exception:
                        pass
                if device_cb:
                    try:
                        device_cb(d)
                    except Exception:
                        pass
                if stop_flag is not None and stop_flag.is_set():
                    ex.shutdown(wait=False, cancel_futures=True)
                    result["stopped"] = True
                    break
        finally:
            ex.shutdown(wait=False, cancel_futures=True)

    # 分析风险（虚拟 IP 判断）
    prev_gw_mac = ""
    if gateway_ip:
        prev_gw_mac = load_gateway_history().get("gateways", {}).get(gateway_ip, {}).get("mac", "")
    risks = analyze(devices, gateway_ip=gateway_ip, prev_gateway_mac=prev_gw_mac)
    # 更新网关 MAC 历史（本次扫描后的新基线）
    if gateway_ip:
        gw_dev = next((d for d in devices if d["ip"] == gateway_ip and d.get("mac")), None)
        if gw_dev:
            record_gateway(gateway_ip, gw_dev["mac"])

    devices.sort(key=lambda d: _ip_sort_key(d["ip"]))
    result["devices"] = devices
    result["risks"] = risks
    result["ok"] = True
    result["stats"] = {
        "total": len(devices),
        "virtual": sum(1 for d in devices if is_virtual_mac(d["mac"])),
        "random_mac": sum(1 for d in devices if mac_kind(d["mac"]) == "locally"),
        "static_arp": sum(1 for d in devices if "static" in (d.get("arp_type") or "").lower()
                          or "静态" in (d.get("arp_type") or "")),
        "partial": partial,
    }
    return result


# ---------------- 联动：交换机采集 ARP 表合并 ----------------

def merge_switch_arp(devices: list, switch_arp_rows: list) -> dict:
    """把 Console 采集的交换机 ARP 表（cv.parse_arp 输出，mac 为 12 位小写 hex）
    合并进设备列表，就地修改并返回统计。

    价值：交换机视角覆盖多 VLAN 且是权威侧（网关侧）——
    * 交换机 ARP 里有、本机扫描没有 → 新设备（跨段终端，本机视角看不见）
    * 同 IP 交换机视角 MAC ≠ 本机视角 MAC → 合并后 analyze 直接报 IP 冲突/ARP 欺骗
    * 已有同 (ip, mac) → 打「交换机证实」标注（本机结论被权威侧背书）
    """
    added = updated = 0
    seen = {(d["ip"], d["mac"]) for d in devices}
    for row in switch_arp_rows or []:
        ip = (row.get("ip") or "").strip()
        mac = clean_mac(row.get("mac") or "")
        if not ip or not mac or not _valid_ip(ip):
            continue
        key = (ip, mac)
        if key in seen:
            for d in devices:
                # 只给「本机视角发现」的设备打背书标；「交换机视角」来源的
                # 设备本身就出自交换机，自己不能证实自己（重复导入幂等靠它）
                if (d["ip"], d["mac"]) == key and "交换机证实" not in d["tags"] \
                        and d.get("arp_type") != "switch":
                    d["tags"].append("交换机证实")
                    updated += 1
            continue
        seen.add(key)
        d = {
            "ip": ip, "mac": mac, "arp_type": "switch",
            "vendor": lookup_vendor(mac), "hostname": "",
            "name": "", "note": "", "tags": ["交换机视角"],
        }
        kind = mac_kind(mac)
        if kind == "locally":
            d["tags"].append("随机化MAC")
        if is_virtual_mac(mac):
            d["tags"].append("虚拟机")
        elif network_vendor(mac):
            d["tags"].append("疑似网络设备")
        hit = match_roster(ip=ip, mac=mac)
        d["name"] = hit.get("name", "")
        d["note"] = hit.get("note", "")
        devices.append(d)
        added += 1
    devices.sort(key=lambda d: _ip_sort_key(d["ip"]))
    return {"added": added, "updated": updated}


# ---------------- 联动：IPAM 同步 ----------------

def sync_to_ipam(cidr: str, devices: list) -> dict:
    """扫描结果一键同步到 IPAM 小账本（数据闭环：发现的活动 IP 批量标记已用）。

    规则：
    * 网段未登记 → 自动登记（名称「ARP 扫描导入」，后续可改名）
    * IP 不在该网段内 → 跳过（跨段设备不属于本网段账本）
    * IPAM 已有的已用 IP → 跳过（不覆盖用户手写的用途备注）
    """
    from modules import ipam

    net_str = ipam.normalize_subnet(cidr)
    if not net_str:
        return {"ok": False, "error": f"网段格式不正确：{cidr}"}
    net = None
    try:
        net = ipaddress.ip_network(net_str)
    except ValueError:
        pass
    subs = {s["subnet"]: s for s in ipam.list_subnets()}
    subnet_created = False
    if net_str not in subs:
        r = ipam.add_subnet(net_str, name="ARP 扫描导入")
        if not r.get("ok"):
            # 并发下可能刚好被登记——重新查一次拿记录
            subs = {s["subnet"]: s for s in ipam.list_subnets()}
            if net_str not in subs:
                return {"ok": False, "error": r.get("error", "网段登记失败")}
        else:
            subnet_created = True
    rec = subs.get(net_str) or next(
        (s for s in ipam.list_subnets() if s["subnet"] == net_str), None)
    if rec is None:
        return {"ok": False, "error": "IPAM 网段记录获取失败"}
    used = {u.get("ip") for u in rec.get("used", [])}
    marked = skipped = 0
    for d in devices:
        ip = d.get("ip", "")
        if not ip or ip in used:
            if ip:
                skipped += 1
            continue
        if net is not None:
            try:
                if ipaddress.ip_address(ip) not in net:
                    continue   # 跨段设备不记到本网段
            except ValueError:
                continue
        # 备注优先级：姓名 > 主机名 > 厂商；全空给 MAC 便于追溯
        note = d.get("name") or d.get("hostname") or d.get("vendor") or d.get("mac", "")
        ipam.mark_ip(net_str, ip, note)
        used.add(ip)
        marked += 1
    return {"ok": True, "subnet": net_str, "subnet_created": subnet_created,
            "marked": marked, "skipped": skipped}


if __name__ == "__main__":
    # 自测（逻辑层无 GUI）
    assert clean_mac("d8-bb-c1-aa-bb-cc") == "D8:BB:C1:AA:BB:CC"
    assert clean_mac("abcd") == ""
    assert mac_kind("01:00:5e:00:00:16") == "multicast"
    assert mac_kind("ff:ff:ff:ff:ff:ff") == "broadcast"
    assert mac_kind("02:11:22:33:44:55") == "locally"   # 第一字节 bit1 置位=本地管理位
    assert lookup_vendor("00:50:56:c0:00:08") == "VMware（虚拟化）"
    assert is_virtual_mac("00:0c:29:11:22:33")
    assert ip_to_cidr("192.168.1.100", "255.255.255.0") == "192.168.1.0/24"
    print("arp_scan 逻辑自测 OK")
