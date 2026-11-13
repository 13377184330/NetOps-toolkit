#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SNMP 采集通道（pysnmp 7.x asyncio API 的同步封装）
对标 snmp_exporter 的最小可用集：端口状态 / 端口流量 / 设备信息 / CPU 内存（Vendor OID 兜底）
依赖：pysnmp>=7.0（未安装时 import 检测优雅降级，软件其它功能不受影响）
红线：只读（get/walk），无 set —— 架构层面禁止写入
"""

import asyncio

# 标准网络 MIB-II OID（RFC 1213 / RFC 2863，H3C/华为/思科通吃）
OID_SYS_DESCR = "1.3.6.1.2.1.1.1.0"        # 设备描述
OID_SYS_NAME = "1.3.6.1.2.1.1.5.0"        # 设备名
OID_SYS_UPTIME = "1.3.6.1.2.1.1.3.0"      # 运行时长
OID_IF_DESCR = "1.3.6.1.2.1.2.2.1.2"      # 端口名（表）
OID_IF_OPER_STATUS = "1.3.6.1.2.1.2.2.1.8"    # 端口操作状态（1=up 2=down）
OID_IF_IN_OCTETS = "1.3.6.1.2.1.2.2.1.10"     # 入流量（字节累计）
OID_IF_OUT_OCTETS = "1.3.6.1.2.1.2.2.1.16"    # 出流量（字节累计）
OID_IF_SPEED = "1.3.6.1.2.1.2.2.1.5"          # 端口速率（bps）
# 厂商 CPU/内存（常见值：华为 entityExtCpuUsage；H3C hh3cEntityExtCpuUsage）
OID_CPU_CANDIDATES = (
    "1.3.6.1.4.1.2011.5.25.31.1.1.1.1.5",        # 华为 hwEntityCpuUsage
    "1.3.6.1.4.1.25506.2.6.1.1.1.1.6",           # H3C hh3cEntityExtCpuUsage
    "1.3.6.1.4.1.9.2.1.58.0",                     # 思科 cpu busy
)
OID_MEM_CANDIDATES = (
    "1.3.6.1.4.1.2011.5.25.31.1.1.1.1.7",        # 华为 hwEntityMemUsage
    "1.3.6.1.4.1.25506.2.6.1.1.1.1.8",           # H3C hh3cEntityExtMemUsage
    "1.3.6.1.4.1.9.9.48.1.1.1.6.1",               # 思科 ciscoMemoryPoolUsed（值非百分比，标记）
)

HAS_PYSNMP = False
try:
    from pysnmp.hlapi.asyncio import (SnmpEngine, CommunityData, UdpTransportTarget,
                                      ObjectType, ObjectIdentity, ContextData,
                                      get_cmd, next_cmd)
    HAS_PYSNMP = True
except ImportError:
    pass


def snmp_available() -> bool:
    return HAS_PYSNMP


def get_config() -> dict:
    """读软件设置里的 SNMP 配置（community/version），供采集入口取默认值"""
    try:
        from utils.settings import Settings
        s = Settings().get("snmp", {}) or {}
        return {"community": s.get("community", "public"),
                "version": int(s.get("version", 2))}
    except Exception:
        return {"community": "public", "version": 2}


def _ensure_loop():
    """QThread 里没有现成 event loop——每个采集调用独享新 loop（不复用，
    防 Python 3.12 的 get_event_loop 弃用路径与跨线程 loop 关闭态问题）"""
    return asyncio.new_event_loop()


def _mp_model(version):
    """软件版本语义（1/2）→ SNMP mpModel：v1=0，v2c=1（真机实锤：mpModel=2 非法致请求无响应）"""
    return 0 if int(version) == 1 else 1


async def _get_one(engine, community, version, target_ip, port, oid, timeout):
    """单个 OID 的 get 请求 → (value_str, error)"""
    try:
        transport = await UdpTransportTarget.create((target_ip, port), timeout=timeout, retries=0)
        err_ind, err_status, _, varbinds = await get_cmd(
            engine,
            CommunityData(community, mpModel=_mp_model(version)),
            transport,
            ContextData(),
            ObjectType(ObjectIdentity(oid)))
        if err_ind:
            return None, str(err_ind)
        for name, val in varbinds:
            return str(val), None
        return None, "no response"
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


async def _walk_table(engine, community, version, target_ip, port, base_oid, timeout, max_rows=200):
    """SNMP 表 walk（nextCmd 链式）→ {index_str: value_str}；只走同前缀"""
    out = {}
    current = base_oid
    try:
        for _ in range(max_rows):
            transport = await UdpTransportTarget.create((target_ip, port), timeout=timeout, retries=0)
            err_ind, _, _, varbinds = await next_cmd(
                engine,
                CommunityData(community, mpModel=_mp_model(version)),
                transport,
                ContextData(),
                ObjectType(ObjectIdentity(current)))
            if err_ind:
                break
            done = True
            for name, val in varbinds:
                name_str = str(name)
                if not name_str.startswith(base_oid):
                    return out
                idx = name_str[len(base_oid):].lstrip(".")
                if not idx:
                    return out
                out[idx] = str(val)
                current = name_str
                done = False
            if done:
                break
    except Exception:
        pass
    return out


def _sync(coro):
    return _ensure_loop().run_until_complete(coro)


def _close_engine(engine):
    # pysnmp 7.x：close_dispatcher（旧名 closeDispatcher 已弃用）；两者都没有则跳过
    fn = getattr(engine, "close_dispatcher", None) or getattr(engine, "closeDispatcher", None)
    if fn:
        fn()


# ---------------------------------------------------------------- 高层采集接口
def probe(target_ip: str, community: str = "public", version: int = 2, port: int = 161,
          timeout: float = 3.0) -> dict:
    """SNMP 探测：设备描述/名称/运行时长 → {ok, sys_descr, sys_name, uptime, error}"""
    if not HAS_PYSNMP:
        return {"ok": False, "error": "未安装 pysnmp（pip install pysnmp）"}

    async def _run():
        engine = SnmpEngine()
        try:
            descr, _ = await _get_one(engine, community, version, target_ip, port,
                                      OID_SYS_DESCR, timeout)
            if descr is None:
                return {"ok": False, "error": "SNMP 无响应（检查 community/IP/161 端口）"}
            name, _ = await _get_one(engine, community, version, target_ip, port,
                                     OID_SYS_NAME, timeout)
            uptime, _ = await _get_one(engine, community, version, target_ip, port,
                                       OID_SYS_UPTIME, timeout)
            return {"ok": True, "sys_descr": descr, "sys_name": name or "",
                    "uptime": uptime or ""}
        finally:
            _close_engine(engine)

    return _sync(_run())


def collect_interfaces(target_ip: str, community: str = "public", version: int = 2,
                       port: int = 161, timeout: float = 4.0) -> dict:
    """端口面板采集：端口名 + 操作状态 + 速率。
    返回 {ok, interfaces: [{index, name, status, speed}], up_n, down_n, error}"""
    if not HAS_PYSNMP:
        return {"ok": False, "error": "未安装 pysnmp", "interfaces": [], "up_n": 0, "down_n": 0}

    async def _run():
        engine = SnmpEngine()
        try:
            names = await _walk_table(engine, community, version, target_ip, port,
                                      OID_IF_DESCR, timeout, max_rows=96)
            if not names:
                return {"ok": False, "error": "SNMP 无响应或无端口表",
                        "interfaces": [], "up_n": 0, "down_n": 0}
            statuses = await _walk_table(engine, community, version, target_ip, port,
                                         OID_IF_OPER_STATUS, timeout, max_rows=96)
            speeds = await _walk_table(engine, community, version, target_ip, port,
                                       OID_IF_SPEED, timeout, max_rows=96)
            ifs, up_n, down_n = [], 0, 0
            for idx, nm in names.items():
                st = statuses.get(idx, "?")
                is_up = st == "1"
                up_n += 1 if is_up else 0
                down_n += 0 if is_up else 1
                speed = int(speeds.get(idx, "0") or 0)
                ifs.append({"index": idx, "name": nm, "up": is_up,
                            "status": "up" if is_up else ("down" if st == "2" else st),
                            "speed_mbps": speed // 1_000_000})
            return {"ok": True, "interfaces": ifs, "up_n": up_n, "down_n": down_n}
        finally:
            _close_engine(engine)

    return _sync(_run())


def collect_perf(target_ip: str, community: str = "public", version: int = 2,
                 port: int = 161, timeout: float = 4.0) -> dict:
    """CPU/内存（按厂商 OID 候选逐个探测）。返回 {ok, cpu, mem, error}"""
    if not HAS_PYSNMP:
        return {"ok": False, "error": "未安装 pysnmp"}

    async def _run():
        engine = SnmpEngine()
        try:
            cpu, mem = None, None
            for oid in OID_CPU_CANDIDATES:
                v, _ = await _get_one(engine, community, version, target_ip, port,
                                      oid + ".1", timeout)   # 槽位 1
                if v and v not in ("No Such Object", "No Such Instance", "No Such Instance currently exists"):
                    try:
                        cpu = int(float(v))
                        break
                    except ValueError:
                        pass
            for oid in OID_MEM_CANDIDATES:
                v, _ = await _get_one(engine, community, version, target_ip, port,
                                      oid + ".1", timeout)
                if v and v not in ("No Such Object", "No Such Instance", "No Such Instance currently exists"):
                    try:
                        mem = int(float(v))
                        break
                    except ValueError:
                        pass
            if cpu is None and mem is None:
                return {"ok": False, "error": "CPU/内存 OID 均未命中（厂商专属 OID 未覆盖）"}
            return {"ok": True, "cpu": cpu, "mem": mem}
        finally:
            _close_engine(engine)

    return _sync(_run())


# ---------------------------------------------------------------- 自测（本地无设备，验证降级与导入安全）
if __name__ == "__main__":
    print("pysnmp 可用:", snmp_available())
    r = probe("127.0.0.1", timeout=0.5)
    print("本地探测（预期失败优雅返回）:", r.get("ok"), r.get("error"))
