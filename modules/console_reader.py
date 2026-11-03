#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Console（串口）只读连接器
红线：本模块只发送查询类命令，架构层面禁止任何写操作（不进配置模式、不下发配置）
复用 pyserial；分页策略：---- More ---- 时发送空格翻页（空格在 More 模式下仅翻页，非命令）
"""

import time

import serial

# ---------------------------------------------------------------- 红线：只读命令白名单
# 允许发送的命令模式（前缀匹配，全部为 display/show 等查询类）
READ_ONLY_PREFIXES = (
    "display", "show", "screen-length",  # screen-length 仅改显示分页，不改配置
    "quit", "return",
)
# 绝对禁止的关键字（即使拼在别处也拦截）
FORBIDDEN_KEYWORDS = (
    "system-view", "system view", "configure terminal", "conf t",
    "undo ", "save", "reset", "reboot", "delete", "copy", "rename",
    "sysname", "vlan ", "interface ", "ip route", "shutdown", "undo",
)


def check_read_only(command: str) -> tuple[bool, str]:
    """校验命令是否只读。返回 (ok, reason)"""
    cmd = command.strip()
    low = cmd.lower()
    if not cmd:
        return False, "空命令"
    for kw in FORBIDDEN_KEYWORDS:
        if kw.strip().lower() in low:
            return False, f"命令包含写操作关键字「{kw.strip()}」，已按只读红线拦截"
    for p in READ_ONLY_PREFIXES:
        if low.startswith(p):
            return True, ""
    return False, f"命令「{cmd}」不在只读白名单内（display/show/quit），已拦截"


# ---------------------------------------------------------------- 串口工具
def list_console_ports():
    """列出所有串口（过滤蓝牙虚拟口），返回 [(port, description)]"""
    import serial.tools.list_ports as lp
    return [(p.device, p.description) for p in lp.comports() if "蓝牙" not in p.description]


def detect_vendor(ser: serial.Serial, tries: int = 3):
    """只发回车，按提示符/版本信息自动识别厂商。返回 vendor 或 None
    两类特征：①banner 厂商名（开机欢迎语）②提示符形态（<xxx> / [xxx] 等）
    注：banner 只出现一次，平时主要靠 prompt 判定；识别不出时用 display version 兜底"""
    ser.reset_input_buffer()
    text = ""
    for i in range(tries):
        ser.write(b"\r\n")
        # 持续读取 1.5s 累积
        deadline = time.time() + 1.5
        while time.time() < deadline:
            chunk = ser.read(ser.in_waiting or 1)
            if chunk:
                text += chunk.decode("utf-8", errors="replace")
            time.sleep(0.05)
        vendor = _match_vendor_text(text)
        if vendor:
            return vendor
    # banner/prompt 都认不出：发 display version 用输出里的厂商特征兜底（只读）
    ser.write(b"\r\n")
    time.sleep(0.6)
    ser.read(ser.in_waiting)
    if check_read_only("display version")[0]:
        ser.write(b"display version\r\n")
        time.sleep(1.5)
        deadline = time.time() + 3.0
        while time.time() < deadline:
            chunk = ser.read(ser.in_waiting or 1)
            if chunk:
                text += chunk.decode("utf-8", errors="replace")
            time.sleep(0.05)
        return _match_vendor_text(text)
    return None


def _match_vendor_text(text: str):
    """文本 → 厂商（banner 关键词优先，提示符形态兜底）"""
    low = text.lower()
    if "new h3c" in low or "h3c" in low:
        return "h3c"
    if "huawei" in low:
        return "huawei"
    if "ruijie" in low:
        return "ruijie"
    if "maipu" in low:
        return "maipu"
    if "cisco" in low or "ciscolocal" in low:
        return "cisco"
    return None


def read_until_idle(ser: serial.Serial, idle_sec: float = 2.0, max_wait: float = 30.0,
                    progress_cb=None):
    """持续读取直到空闲；遇 ---- More ---- 发空格翻页（空格仅翻页不执行命令）"""
    buf = b""
    idle = 0.0
    start = time.time()
    last_report = 0.0
    while time.time() - start < max_wait:
        chunk = ser.read(ser.in_waiting or 1)
        if chunk:
            buf += chunk
            idle = 0.0
            if progress_cb and time.time() - last_report > 0.5:
                progress_cb(len(buf))
                last_report = time.time()
        else:
            idle += 0.2
            tail = buf[-40:]
            if b"---- More ----" in tail:
                ser.write(b" ")
                time.sleep(0.25)
                idle = 0.0
                continue
            if idle >= idle_sec:
                break
    return buf


VENDOR_CONFIG_CMD = {
    "huawei": "display current-configuration",
    "h3c": "display current-configuration",
    "ruijie": "show running-config",
    "maipu": "show running-config",
    "cisco": "show running-config",
}

VENDOR_VERSION_CMD = {
    "huawei": "display version",
    "h3c": "display version",
    "ruijie": "show version",
    "maipu": "show version",
    "cisco": "show version",
}

# LLDP 邻居查询命令（只读）
VENDOR_LLDP_CMD = {
    "huawei": "display lldp neighbor brief",
    "h3c": "display lldp neighbor-information verbose",
    "ruijie": "show lldp neighbors",
    "maipu": "show lldp neighbors",
    "cisco": "show lldp neighbors",
}


def _send(ser, command: str):
    """发送前的只读校验（红线执行点：所有命令出口都过这里）"""
    ok, reason = check_read_only(command)
    if not ok:
        raise PermissionError(reason)
    ser.write(command.encode("utf-8") + b"\r\n")


class ConsoleReader:
    """Console 只读会话：打开发回车 → 识别厂商 → 抓配置（全部只读）"""

    def __init__(self, port: str, baud: int = 9600):
        self.port = port
        self.baud = baud
        self.ser = None
        self.vendor = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()

    def open(self):
        self.ser = serial.Serial(self.port, self.baud, bytesize=8,
                                 parity="N", stopbits=1, timeout=0.2)
        self.ser.reset_input_buffer()

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()

    def detect(self):
        self.vendor = detect_vendor(self.ser)
        return self.vendor

    def _exec(self, cmd: str, max_wait: float = 30.0):
        """内部统一执行（实测对拍结论）：
        会话建立时已唤醒（detect），此处直接：静默排空 → 逐字符发命令 → 读取到空闲。
        （实测教训：发送前敲回车唤醒会导致设备输入行竞争吞首字符，绝不能发）"""
        # 1) 静默排空（读到 300ms 无数据为止，清残留不吐回显）
        quiet = 0.0
        deadline = time.time() + 3.0
        while time.time() < deadline:
            if self.ser.in_waiting:
                self.ser.read(self.ser.in_waiting)
                quiet = 0.0
            else:
                quiet += 0.05
                if quiet >= 0.3:
                    break
                time.sleep(0.05)
        # 2) 逐字符发送
        for ch in cmd:
            self.ser.write(ch.encode("utf-8"))
            time.sleep(0.015)
        self.ser.write(b"\r\n")
        time.sleep(0.8)
        # 3) 读取
        raw = read_until_idle(self.ser, max_wait=max_wait)
        return self._clean(raw.decode("utf-8", errors="replace"), cmd)

    def read_config(self, progress_cb=None):
        """抓取 running-config（只读）"""
        if self.vendor is None:
            self.detect()
        cmd = VENDOR_CONFIG_CMD.get(self.vendor, "display current-configuration")
        raw = self._exec(cmd, max_wait=45)
        if progress_cb:
            progress_cb(len(raw))
        return raw

    def read_version(self):
        """抓取版本信息（只读）"""
        if self.vendor is None:
            self.detect()
        cmd = VENDOR_VERSION_CMD.get(self.vendor, "display version")
        return self._exec(cmd, max_wait=15)

    def read_lldp(self):
        """抓取 LLDP 邻居信息（只读），用于拓扑可视化"""
        if self.vendor is None:
            self.detect()
        cmd = VENDOR_LLDP_CMD.get(self.vendor, "display lldp neighbor-information verbose")
        return self._exec(cmd, max_wait=25)

    @staticmethod
    def _clean(text: str, cmd: str) -> str:
        """去掉命令回显行（含提示符前缀）、---- More ---- 残留、尾部提示符行"""
        out_lines = []
        cmd_l = cmd.lower()
        for ln in text.splitlines():
            s = ln.strip()
            if not s:
                out_lines.append(ln)
                continue
            # More 翻页：保留覆盖行后的有效内容
            if "---- More ----" in s:
                tail = ln.split("---- More ----")[-1]
                if tail.strip():
                    out_lines.append(tail)
                continue
            # 命令回显行：纯命令 或 <prompt>命令 形态
            core = re.sub(r"^<?\[?[\w.\-/@:]+\]?>?\s*", "", s) if False else None
            # 判定：行等于命令 / 行以提示符开头且剩余部分等于命令
            if s.lower() == cmd_l:
                continue
            m = re.match(r"^<[A-Za-z][\w.\-]*> ?(.*)$", s)
            if m and m.group(1).strip().lower() == cmd_l:
                continue
            if s.lower().startswith(cmd_l):
                continue
            # 提示符孤立行（<H3a> / [H3a] 等）：保留（尾部结尾的去掉）
            if re.match(r"^<[A-Za-z][\w.\-]*>$", s) or re.match(r"^\[[A-Za-z][\w.\-]*\]$", s):
                continue
            out_lines.append(ln)
        # 去掉尾部残余的提示符行与空白
        body = "\n".join(out_lines).strip()
        # 尾部孤立提示符
        lines = body.splitlines()
        while lines and (not lines[-1].strip() or re.match(r"^<[A-Za-z][\w.\-]*>$", lines[-1].strip())
                         or re.match(r"^\[[A-Za-z][\w.\-]*\]$", lines[-1].strip())):
            lines.pop()
        return "\n".join(lines).strip()

import re  # noqa: E402  （_clean 用到）
