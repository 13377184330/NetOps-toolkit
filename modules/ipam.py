#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
IPAM 小账本（学 NetBox IPAM 的轻量版，本地 JSON 存储）
网段登记 / 已用 IP / 用途备注 —— 教育城域网项目场景：学校给多少段、用了多少、留给谁
"""

import ipaddress
import json
import os
from datetime import datetime

from utils.app_paths import app_root

IPAM_FILE = os.path.join(app_root(), "config", "ipam.json")


def _backup_corrupt():
    """把损坏账本另存为带时间戳的 .corrupt，避免多次损坏互相覆盖。"""
    try:
        import shutil
        from datetime import datetime
        stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        shutil.copy2(IPAM_FILE, IPAM_FILE + "." + stamp + ".corrupt")
    except OSError:
        pass


def _load():
    if os.path.exists(IPAM_FILE):
        data = None
        try:
            with open(IPAM_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            data = None
        # 不仅校验 JSON 语法，也校验结构：合法 JSON 但非 dict / 缺
        # subnets 列表同样属损坏，否则后续 data["subnets"] 会崩 UI。
        if isinstance(data, dict) and isinstance(data.get("subnets"), list):
            return data
        _backup_corrupt()
        # 损坏绝不能当空账本继续：下一次 _save 会覆盖原文件导致数据全丢。
        # 先把坏文件挪开（copy 已留档），再返回空账本重建。
        try:
            os.remove(IPAM_FILE)
        except OSError:
            pass
    return {"subnets": []}


def _save(data):
    try:
        os.makedirs(os.path.dirname(IPAM_FILE), exist_ok=True)
        with open(IPAM_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"IPAM 保存失败: {e}")


def normalize_subnet(text: str) -> str:
    """任意写法 → 规范 CIDR（192.168.10.1/24 → 192.168.10.0/24）；非法返回空"""
    t = (text or "").strip()
    if not t:
        return ""
    if "/" not in t:
        t += "/24"      # 裸地址默认 /24（学校场景最常见）
    try:
        net = ipaddress.ip_network(t, strict=False)
        return str(net)
    except ValueError:
        return ""


def add_subnet(cidr: str, name: str = "", usage: str = "") -> dict:
    """登记网段（cidr 自动规范化）。重复网段返回已有记录（带 error 键）。"""
    net = normalize_subnet(cidr)
    if not net:
        return {"ok": False, "error": f"网段格式不正确：{cidr}"}
    data = _load()
    for s in data["subnets"]:
        if s["subnet"] == net:
            return {"ok": False, "error": f"网段 {net} 已登记（{s.get('name') or '未命名'}）"}
    rec = {
        "subnet": net,
        "name": name.strip(),
        "usage": usage.strip(),
        "used": [],           # [{"ip": "x.x.x.x", "note": "用途", "at": "时间"}]
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    data["subnets"].append(rec)
    _save(data)
    return {"ok": True, "record": rec}


def remove_subnet(cidr: str) -> bool:
    net = normalize_subnet(cidr)
    data = _load()
    before = len(data["subnets"])
    data["subnets"] = [s for s in data["subnets"] if s["subnet"] != net]
    if len(data["subnets"]) < before:
        _save(data)
        return True
    return False


def mark_ip(cidr: str, ip: str, note: str = "") -> dict:
    """标记已用 IP（自动校验属于该网段）"""
    net = normalize_subnet(cidr)
    data = _load()
    rec = next((s for s in data["subnets"] if s["subnet"] == net), None)
    if rec is None:
        return {"ok": False, "error": f"网段 {net} 未登记"}
    try:
        addr = ipaddress.ip_address((ip or "").strip())
        if addr not in ipaddress.ip_network(net):
            return {"ok": False, "error": f"{ip} 不属于网段 {net}"}
    except ValueError:
        return {"ok": False, "error": f"IP 格式不正确：{ip}"}
    ip_s = str(addr)
    # 损坏/旧格式的记录可能缺 used 键，list_subnets 用 .get 保护了读路径，
    # 写路径也必须同样容错，否则点「标记已用」直接 KeyError 崩 UI。
    used_list = rec.setdefault("used", [])
    for u in used_list:
        if u.get("ip") == ip_s:
            u["note"] = note.strip() or u.get("note", "")
            _save(data)
            return {"ok": True, "record": rec, "updated": True}
    used_list.append({"ip": ip_s, "note": note.strip(),
                      "at": datetime.now().strftime("%Y-%m-%d %H:%M")})
    _save(data)
    return {"ok": True, "record": rec}


def unmark_ip(cidr: str, ip: str) -> bool:
    net = normalize_subnet(cidr)
    data = _load()
    rec = next((s for s in data["subnets"] if s["subnet"] == net), None)
    if rec is None:
        return False
    before = len(rec.get("used", []))
    rec["used"] = [u for u in rec.get("used", []) if u.get("ip") != (ip or "").strip()]
    if len(rec["used"]) < before:
        _save(data)
        return True
    return False


def suggest_free(cidr: str) -> str:
    """网段内建议下一个可用 IP（跳过网络地址/网关位/已用）"""
    net = normalize_subnet(cidr)
    data = _load()
    rec = next((s for s in data["subnets"] if s["subnet"] == net), None)
    if rec is None:
        return ""
    used = {u.get("ip") for u in rec.get("used", [])}
    # 惰性遍历，找到第一个未用 IP 即返回。原实现 `list(network.hosts())`
    # 会把 /8 的 1600 万个主机一次性物化（7s+ 卡顿 / 高内存 / 可能 OOM）。
    for idx, h in enumerate(ipaddress.ip_network(net).hosts()):
        if idx == 0:
            continue  # 第一个 host 位留作网关（学校惯例）
        if str(h) not in used:
            return str(h)
    return ""


def list_subnets() -> list:
    """[{subnet,name,usage,used:[...],total,used_n,free_n,capacity}]"""
    data = _load()
    out = []
    for s in data["subnets"]:
        try:
            net = ipaddress.ip_network(s["subnet"])
            total = max(0, net.num_addresses - 2)  # /31 /32 无常规主机位，不出现负数
        except ValueError:
            total = 0
        used_n = len(s.get("used", []))
        out.append({
            "subnet": s["subnet"], "name": s.get("name", ""),
            "usage": s.get("usage", ""), "used": s.get("used", []),
            "total": total, "used_n": used_n, "free_n": max(0, total - used_n),
        })
    return out


if __name__ == "__main__":
    # 自测
    assert normalize_subnet("192.168.10.1/24") == "192.168.10.0/24"
    assert normalize_subnet("10.1.2.3/8") == "10.0.0.0/8"
    assert normalize_subnet("abc") == ""
    print("normalize OK")
