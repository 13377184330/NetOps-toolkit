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

# MAC 地址表 / ARP 表（拓扑发现终端设备用，均只读）
VENDOR_MAC_CMD = {
    "huawei": "display mac-address",
    "h3c": "display mac-address",
    "ruijie": "show mac-address-table",
    "maipu": "show mac-address-table",
    "cisco": "show mac address-table",
}
VENDOR_ARP_CMD = {
    "huawei": "display arp",
    "h3c": "display arp",
    "ruijie": "show arp",
    "maipu": "show arp",
    "cisco": "show arp",
}


def _send(ser, command: str, allow_write: bool = False):
    """命令发送出口。allow_write=False 时强校验只读（安全默认）；
    显式允许写入（配置下发场景，需用户在 UI 确认）时放行配置/撤销类命令"""
    if not allow_write:
        ok, reason = check_read_only(command)
        if not ok:
            raise PermissionError(reason)
    ser.write(command.encode("utf-8") + b"\r\n")


class ConsoleReader:
    """Console 会话：识别厂商 / 抓配置（只读） / 下发配置（需 allow_write=True 显式开启）"""

    def __init__(self, port: str, baud: int = 9600, allow_write: bool = False):
        self.port = port
        self.baud = baud
        self.ser = None
        self.vendor = None
        self.allow_write = allow_write

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()

    def open(self):
        # write_timeout：真机实测教训——USB 串口适配器驱动层偶尔卡死时 ser.write() 无限阻塞
        # （下发线程挂死 250s+，UI 永远「忙」）；加写超时让卡死变成可报错的异常
        self.ser = serial.Serial(self.port, self.baud, bytesize=8,
                                 parity="N", stopbits=1, timeout=0.2, write_timeout=5)
        self.ser.reset_input_buffer()
        self._prompt_synced = False

    def _sync_prompt(self):
        """会话首条命令前的提示符同步（真机实测连锁陷阱的修复）：
        sysname 不含厂商名时（如 Core-SW-01 / Test-Run-01），detect() 的提示符快路径
        失效，走 display version 慢兜底——返回时设备发送队列里还压着未画完的提示符，
        此时打字首字符必被设备行编辑器吞掉（% Unrecognized 且回显缺首字母）。
        正确握手：发回车 → 等设备把新提示符画完（读到空闲）→ 再打字。
        （旧教训「回车后直接打字会吞首字符」仍然成立，差的就是等提示符画完这一步）"""
        self.ser.write(b"\r\n")
        time.sleep(0.3)
        read_until_idle(self.ser, max_wait=4.0)
        self._prompt_synced = True

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()

    def detect(self):
        self.vendor = detect_vendor(self.ser)
        return self.vendor

    def _exec(self, cmd: str, max_wait: float = 30.0):
        """内部统一执行：首条命令前先同步提示符，随后静默排空 → 逐字符发送 → 读到空闲。"""
        # 0) 会话首条命令前同步提示符（防首字符被吞，见 _sync_prompt 注释）
        if not getattr(self, "_prompt_synced", False):
            self._sync_prompt()
        # 1) 静默排空（读到 0.8s 无数据为止，清残留不吐回显）
        quiet = 0.0
        deadline = time.time() + 4.0
        while time.time() < deadline:
            if self.ser.in_waiting:
                self.ser.read(self.ser.in_waiting)
                quiet = 0.0
            else:
                quiet += 0.05
                if quiet >= 0.8:
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

    def read_mac_table(self):
        """抓取 MAC 地址表（只读）——用于发现各接口下挂的终端设备"""
        if self.vendor is None:
            self.detect()
        cmd = VENDOR_MAC_CMD.get(self.vendor, "display mac-address")
        return self._exec(cmd, max_wait=30)

    def read_arp(self):
        """抓取 ARP 表（只读）——为终端设备补 IP 信息"""
        if self.vendor is None:
            self.detect()
        cmd = VENDOR_ARP_CMD.get(self.vendor, "display arp")
        return self._exec(cmd, max_wait=25)

    # ---------------- 配置下发（需显式 allow_write） ----------------
    def send_config(self, config_lines, apply_mode=True, save=False):
        """把配置命令逐条下发到设备（需 allow_write=True 才可调用）
        apply_mode: 是否自动进入 system-view
        save: 是否存盘（默认不存盘，只改 running-config，可撤回）
        返回每步回显列表
        """
        if not self.allow_write:
            raise PermissionError("未开启写模式（ConsoleReader(allow_write=True)）")
        results = []
        cmds = [c.strip() for c in config_lines if c.strip() and not c.strip().startswith("#")]
        if apply_mode:
            results.append(("system-view", self._exec("system-view", max_wait=10)))
            # 二次确认进入系统视图（部分设备提示 [Y/N]）
            tail = results[-1][1][-80:].lower()
            if "[y/n]" in tail or "yes/no" in tail:
                self.ser.write(b"y\r\n")
                time.sleep(0.8)
                results[-1] = ("system-view", results[-1][1] + self._clean(
                    read_until_idle(self.ser, max_wait=8).decode("utf-8", errors="replace"), "y"))
        for cmd in cmds:
            results.append((cmd, self._exec(cmd, max_wait=12)))
        if apply_mode:
            results.append(("return", self._exec("return", max_wait=8)))
        if save:
            save_out = self._exec("save", max_wait=10)
            if "[y/n]" in save_out.lower() or "yes/no" in save_out.lower():
                self.ser.write(b"y\r\n")
                time.sleep(2.0)
                save_out += self._clean(read_until_idle(self.ser, max_wait=15).decode("utf-8", errors="replace"), "y")
            results.append(("save", save_out))
        return results

    @staticmethod
    def _clean(text: str, cmd: str) -> str:
        """清洗串口输出：去命令回显、More 残留、行尾空格、纯空白行、尾部提示符
        （More 翻页会留下覆盖残行，表现为行内大量空格；统一 rstrip + 过滤空行）"""
        out_lines = []
        cmd_l = cmd.lower()
        for ln in text.splitlines():
            s = ln.strip()
            # More 翻页：取覆盖行之后的有效内容
            if "---- More ----" in s:
                s = ln.split("---- More ----")[-1].strip()
                if not s:
                    continue
            if not s:
                continue   # 纯空白行直接丢弃（More 残行归一）
            # 命令回显行（纯命令 / <prompt>命令）
            if s.lower() == cmd_l or s.lower().startswith(cmd_l):
                continue
            m = re.match(r"^<[A-Za-z][\w.\-]*> ?(.*)$", s)
            if m and m.group(1).strip().lower() == cmd_l:
                continue
            # 孤立提示符行
            if re.match(r"^<[A-Za-z][\w.\-]*>$", s) or re.match(r"^\[[A-Za-z][\w.\-]*\]$", s):
                continue
            # 行尾空格统一去掉（保留行首缩进，配置层级靠缩进）
            out_lines.append(ln.rstrip())
        # 去掉尾部残余提示符/空白
        while out_lines and (not out_lines[-1].strip()
                             or re.match(r"^<[A-Za-z][\w.\-]*>$", out_lines[-1].strip())
                             or re.match(r"^\[[A-Za-z][\w.\-]*\]$", out_lines[-1].strip())):
            out_lines.pop()
        return "\n".join(out_lines).strip()

import re  # noqa: E402  （_clean 用到）
