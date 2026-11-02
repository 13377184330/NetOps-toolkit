#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
真机连接器：基于 Netmiko 的 SSH 连通测试 / 命令执行 / 配置下发 / 配置抓取
Netmiko 官方已支持四厂商 + 思科，本模块只做映射与批量编排，不重复实现协议层
"""

import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoTimeoutException, NetmikoAuthenticationException

# 厂商 -> netmiko device_type（官方 platform 映射，勿自造）
VENDOR_NETMIKO_TYPE = {
    "huawei": "huawei",
    "h3c": "h3c_comware",
    "ruijie": "ruijie_os",
    "maipu": "maipu",
    "cisco": "cisco_ios",
}

VENDOR_LABELS = {"huawei": "华为", "h3c": "H3C", "ruijie": "锐捷", "maipu": "迈普", "cisco": "思科"}


def tcp_probe(ip: str, port: int = 22, timeout: float = 3.0):
    """轻量连通测试：TCP 探测 + 读取 SSH banner，不消耗登录凭据"""
    start = time.perf_counter()
    try:
        with socket.create_connection((ip, port), timeout=timeout) as s:
            s.settimeout(2.0)
            try:
                banner = s.recv(64).decode("utf-8", errors="ignore").strip()
            except Exception:
                banner = ""
            latency = round((time.perf_counter() - start) * 1000, 1)
            return True, f"端口可达（{latency} ms）" + (f" banner: {banner[:50]}" if banner else ""), latency
    except socket.timeout:
        return False, f"连接超时（{timeout}s）：{ip}:{port} 无响应", None
    except OSError as e:
        return False, f"连接失败：{type(e).__name__} {e}", None


def build_handler(device: dict, password: str, timeout: int = 15):
    """构造 netmiko ConnectHandler 参数"""
    vendor = device.get("vendor", "huawei")
    device_type = VENDOR_NETMIKO_TYPE.get(vendor)
    if not device_type:
        raise ValueError(f"不支持的厂商: {vendor}")
    return {
        "device_type": device_type,
        "host": device["ip"],
        "port": int(device.get("ssh_port", 22)),
        "username": device.get("username", ""),
        "password": password,
        "timeout": timeout,
        "session_log": None,
    }


def test_ssh_login(device: dict, password: str, timeout: int = 12):
    """完整连通测试：TCP 探测 + SSH 登录 + 执行一次回显命令"""
    ok, msg, latency = tcp_probe(device["ip"], device.get("ssh_port", 22))
    if not ok:
        return False, msg, None

    try:
        conn = ConnectHandler(**build_handler(device, password, timeout))
    except NetmikoAuthenticationException:
        return False, "SSH 端口可达，但账号或密码错误", latency
    except NetmikoTimeoutException:
        return False, "SSH 握手超时（设备可能未开启 SSH 服务）", latency
    except Exception as e:
        return False, f"SSH 连接失败：{type(e).__name__}: {e}", latency

    try:
        output = conn.send_command("display version", read_timeout=15)
        if "Invalid" in output or "Error" in output or not output.strip():
            # 华三/锐捷/迈普/思科部分平台命令不同，回退通用提示
            first_line = output.strip().splitlines()[0] if output.strip() else ""
            return True, f"SSH 登录成功（{latency} ms）" + (f" | {first_line[:60]}" if first_line else ""), latency
        return True, f"SSH 登录成功（{latency} ms）| {output.strip().splitlines()[0][:60]}", latency
    finally:
        conn.disconnect()


def run_command(device: dict, password: str, command: str, timeout: int = 30):
    """在设备上执行一条回显命令，返回 (ok, output/error)"""
    try:
        conn = ConnectHandler(**build_handler(device, password))
        try:
            output = conn.send_command(command, read_timeout=timeout)
            return True, output or "(无输出)"
        finally:
            conn.disconnect()
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def send_config(device: dict, password: str, config_text: str, timeout: int = 60):
    """把多行配置文本下发到设备（自动进入系统视图/配置模式），返回 (ok, log)"""
    lines = [ln.strip() for ln in config_text.splitlines()
             if ln.strip() and not ln.strip().startswith("#")]
    if not lines:
        return False, "配置内容为空"
    try:
        conn = ConnectHandler(**build_handler(device, password, timeout))
        try:
            output = conn.send_config_set(lines, exit_config_mode=True)
            return True, output or "(设备无回显，通常已生效)"
        finally:
            conn.disconnect()
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def fetch_running_config(device: dict, password: str, timeout: int = 30):
    """抓取设备当前配置（供备份用），返回 (ok, config_text/error)"""
    vendor = device.get("vendor", "huawei")
    cmd = {
        "huawei": "display current-configuration",
        "h3c": "display current-configuration",
        "ruijie": "show running-config",
        "maipu": "show running-config",
        "cisco": "show running-config",
    }.get(vendor, "display current-configuration")
    try:
        conn = ConnectHandler(**build_handler(device, password, timeout))
        try:
            output = conn.send_command(cmd, read_timeout=timeout)
            if not output or not output.strip():
                return False, "设备无回显，抓取失败"
            # 去掉命令回显行，保留纯配置
            lines = [ln for ln in output.splitlines() if not ln.startswith(cmd)]
            return True, "\n".join(lines).strip()
        finally:
            conn.disconnect()
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def batch_execute(devices: list, func, password_getter, max_workers: int = 8, progress_cb=None):
    """线程池批量执行：func(device, password) -> (ok, result)
    返回 {device_id: (ok, result)}；progress_cb(done, total) 用于 GUI 进度回调
    """
    results = {}
    total = len(devices)
    done = 0
    with ThreadPoolExecutor(max_workers=min(max_workers, max(1, total))) as pool:
        futures = {}
        for d in devices:
            futures[pool.submit(func, d, password_getter(d.get("id")))] = d
        for fut in as_completed(futures):
            d = futures[fut]
            try:
                results[d["id"]] = fut.result()
            except Exception as e:
                results[d["id"]] = (False, f"未捕获异常: {e}")
            done += 1
            if progress_cb:
                progress_cb(done, total)
    return results
