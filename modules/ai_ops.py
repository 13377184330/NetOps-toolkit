#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
AI 运维引擎（大模型自然语言运维，v4.1 增量功能）
安全架构借鉴开源项目 Netiarius（MIT, github.com/Joeen-AI-Labs/Netiarius）的 HITL 范式：
  AI 只生成命令草稿、永不直接触达设备；一切写入必须「人工逐条审阅 → 二次确认 → 受控下发」。
- OpenAI 兼容协议（requests 直连，零新增依赖），SSE 流式输出
- 三种模式：gen 生成配置 / analyze 诊断分析 / chat 自由问答
- 命令解析成卡片队列 + 风险三级分类（readonly/write/dangerous）+ 复用 config_lint 语法体检
- 离线规则引擎 nl_engine 兜底：AI 不可用时自动降级，工具永远可用
- API Key 用 Fernet 加密存储（复用 utils.credential_crypto）
"""

import json
import re

import requests

try:
    from utils.settings import Settings
    from utils.credential_crypto import encrypt, decrypt
    from modules.config_lint import lint
    from modules.cmd_notes import note_of
    from modules import nl_engine
except ImportError:  # 直接运行本文件做自测时，把项目根目录补进 sys.path
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    from utils.settings import Settings
    from utils.credential_crypto import encrypt, decrypt
    from modules.config_lint import lint
    from modules.cmd_notes import note_of
    from modules import nl_engine

VENDORS = nl_engine.VENDORS            # ("huawei", "h3c", "ruijie", "maipu", "cisco")
VENDOR_CN = nl_engine.VENDOR_CN

# ---------------------------------------------------------------- 服务商预设
# base_url 均为 OpenAI 兼容入口；本地两类接 vLLM / Ollama（DGX Spark 默认地址作预设）
PROVIDERS = {
    "deepseek": ("DeepSeek", "https://api.deepseek.com/v1", "deepseek-chat"),
    "zhipu":    ("智谱 GLM",  "https://open.bigmodel.cn/api/paas/v4", "glm-4-flash"),
    "qwen":     ("通义千问",   "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus"),
    "moonshot": ("Moonshot",  "https://api.moonshot.cn/v1", "moonshot-v1-8k"),
    "openai":   ("OpenAI",    "https://api.openai.com/v1", "gpt-4o-mini"),
    "ollama":   ("本地 Ollama", "http://127.0.0.1:11434/v1", "qwen2.5:7b"),
    "vllm":     ("本地 vLLM",  "http://192.168.0.224:8000/v1", ""),
    "custom":   ("自定义",     "", ""),
}

# 风险等级 → (中文标签, 展示色)
RISK_LABEL = {"readonly": "只读安全", "write": "写配置", "dangerous": "高危"}
RISK_COLOR = {"readonly": "#34C759", "write": "#0089FF", "dangerous": "#FA5151"}


# ---------------------------------------------------------------- 配置读写
def get_ai_config() -> dict:
    """读 AI 配置（api_key 解密），返回 {provider,name,base_url,model,api_key,configured}"""
    s = Settings()
    ai = s.get("ai", {}) or {}
    pid = ai.get("provider", "deepseek")
    name, def_url, def_model = PROVIDERS.get(pid, PROVIDERS["custom"])
    return {
        "provider": pid,
        "name": name,
        "base_url": (ai.get("base_url") or def_url).strip(),
        "model": (ai.get("model") or def_model).strip(),
        "api_key": decrypt(ai.get("api_key_enc", "")),
        "configured": bool((ai.get("base_url") or def_url) and (ai.get("model") or def_model)),
    }


def save_ai_config(provider: str, base_url: str, model: str, api_key: str = ""):
    """保存 AI 配置。api_key 为空 = 保留原 Key（与设备清单『空密码不改』语义一致）"""
    s = Settings()
    old = s.get("ai", {}) or {}
    enc = old.get("api_key_enc", "")
    if api_key:
        enc = encrypt(api_key)
    s.set("ai", {"provider": provider, "base_url": base_url.strip(),
                 "model": model.strip(), "api_key_enc": enc})


# ---------------------------------------------------------------- 流式对话（OpenAI 兼容）
def stream_chat(messages, on_delta=None, config=None, timeout=(10, 120)):
    """SSE 流式调用。on_delta(text) 逐段回调；返回 (full_text, error)"""
    cfg = config or get_ai_config()
    if not cfg["base_url"] or not cfg["model"]:
        return "", "AI 未配置：请在「设置 → AI」填写 API 地址与模型（或改用本地 vLLM/Ollama）"
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if cfg["api_key"]:
        headers["Authorization"] = "Bearer " + cfg["api_key"]
    payload = {"model": cfg["model"], "messages": messages,
               "stream": True, "temperature": 0.2}
    chunks = []
    try:
        with requests.post(url, json=payload, headers=headers,
                           stream=True, timeout=timeout) as r:
            r.encoding = "utf-8"   # 流式 chunk 无 charset，requests 默认 ISO-8859-1 会把中文解成乱码
            if r.status_code != 200:
                try:
                    err = r.json().get("error", {}).get("message", r.text[:200])
                except Exception:
                    err = r.text[:200]
                return "", f"API 调用失败（HTTP {r.status_code}）：{err}"
            for raw in r.iter_lines(decode_unicode=True):
                if not raw or not raw.startswith("data:"):
                    continue
                data = raw[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except ValueError:
                    continue
                try:
                    delta = obj["choices"][0].get("delta", {}).get("content") or ""
                except (KeyError, IndexError, TypeError):
                    delta = ""
                if delta:
                    chunks.append(delta)
                    if on_delta:
                        on_delta(delta)
    except requests.exceptions.ConnectionError:
        return "".join(chunks), "连接失败：请检查 API 地址与网络（本地服务确认已启动）"
    except requests.exceptions.Timeout:
        return "".join(chunks), "请求超时：API 长时间无响应，可重试或换本地模型"
    except Exception as e:
        return "".join(chunks), f"{type(e).__name__}: {e}"
    return "".join(chunks), None


def test_connection(config=None):
    """连通测试：发一句极短对话，返回 (ok, msg)"""
    cfg = config or get_ai_config()
    if not cfg["base_url"] or not cfg["model"]:
        return False, "请先填写 API 地址与模型名称"
    text, err = stream_chat([{"role": "user", "content": "回复：OK"}],
                            config=cfg, timeout=(8, 30))
    if err:
        return False, err
    return True, f"连接成功 · 模型 {cfg['model']} 回复：{(text or '').strip()[:30]}"


# ---------------------------------------------------------------- 提示词（三模式）
_GEN_RULES = """\
输出铁律（必须严格遵守）：
1. 所有可执行命令必须放进一个 ```netcfg 代码块中，每行一条；不要带 <主机名>、[主机名] 等提示符。
2. 每条命令行尾用 " # "（空格+#+空格）接一句中文释义，说明该命令做什么。
3. 严格使用目标厂商官方语法，进入/退出视图命令（system-view、configure terminal、quit、exit 等）不可省略。
4. 用户没给全的参数用 TODO(待填项) 占位，严禁编造 IP、密码、VLAN 号、接口号。
5. 代码块之外先给 1-3 句变更说明与风险提示，不要在块外罗列命令。
6. 默认不生成保存命令（save / write memory）：配置验收合格后由人工存盘，除非用户明确要求。
7. 涉及删除/重启/清空/恢复出厂类高危命令，必须在块外说明风险并给回退思路。"""


def build_system_prompt(mode: str, vendor: str) -> str:
    vendor = vendor if vendor in VENDORS else "huawei"
    hint = {
        "huawei": "华为 VRP（system-view 进入系统视图；undo 前缀表示删除配置；vlan batch 批量建 VLAN；stelnet 即 SSH）",
        "h3c": "H3C Comware V5/V7（system-view；port access vlan / port trunk permit vlan；ssh server enable；注意部分现网为老 V5 设备，语法保守取 V7 兼容写法）",
        "ruijie": "锐捷 RGOS（configure terminal；switchport mode access / trunk；IOS 风格但关键字有差异）",
        "maipu": "迈普 MyPower（configure terminal；IOS 风格）",
        "cisco": "思科 IOS（configure terminal；switchport access vlan；ip route）",
    }[vendor]

    if mode == "gen":
        return (
            "你是资深交换机/路由器运维工程师，精通网络设备 CLI 配置。目标设备："
            f"{VENDOR_CN[vendor]}，语法体系：{hint}。\n"
            "用户用中文大白话描述变更需求，你把它翻译成该设备可直接粘贴执行的配置命令序列。\n"
            + _GEN_RULES
        )
    if mode == "analyze":
        return (
            "你是资深网络排障专家。用户会粘贴设备回显/配置/日志片段，请按固定结构输出：\n"
            "① 结论（一句话）；② 发现的异常点（指明具体行/关键值）；③ 下一步建议。\n"
            f"当前设备为 {VENDOR_CN[vendor]}（{hint}）。\n"
            "如需补充验证命令，只允许给只读查看类命令，放进 ```netcfg 块，每行尾 \" # \" 加中文释义；"
            "禁止建议任何写配置/重启/删除动作，如确有必要只做文字提醒。"
        )
    return (
        f"你是资深网络运维专家，精通 {VENDOR_CN[vendor]} 与主流厂商设备、交换路由原理与现场运维经验，"
        "用简洁中文回答；涉及命令时给出可直接粘贴的写法并用 \" # \" 注释。"
    )


def build_messages(mode: str, vendor: str, history: list, user_text: str) -> list:
    """system + 最近历史 + 本轮输入（历史裁剪防上下文膨胀）"""
    msgs = [{"role": "system", "content": build_system_prompt(mode, vendor)}]
    msgs += history[-12:]
    msgs.append({"role": "user", "content": user_text})
    return msgs


# ---------------------------------------------------------------- 命令风险分级（学 Netiarius safe_mode 思想）
_DANGER_RE = re.compile(
    r"^(?:reset(?!\s+counters)\b|delete\b|erase\b|format\b|reboot\b|reload\b|restore\b|"
    r"undo\s|clear\s|startup\s+saved-configuration|boot-loader\b|boot\s+system\b|xmodem\b)",
    re.I)
_READONLY_RE = re.compile(
    r"^(?:display\b|show\b|ping\b|tracert\b|traceroute\b|tcp-ping\b|nslookup\b|dir\b|"
    r"more\b|screen-length\b|clock\b|check\b|terminal\s+monitor|reset\s+counters)",
    re.I)


def classify_command(cmd: str) -> str:
    """readonly 只读安全 / write 常规写配置 / dangerous 高危（删配/重启/清库/恢复出厂）"""
    c = (cmd or "").strip()
    if _DANGER_RE.match(c):
        return "dangerous"
    if _READONLY_RE.match(c):
        return "readonly"
    return "write"


# ---------------------------------------------------------------- 解析 AI 输出
# fenced 代码块与命令行注释切分：引擎解析与 GUI 聊天渲染共用同一份正则/切分，
# 避免 ai_ops_tab 重复定义导致两处口径漂移
CMD_FENCE_RE = re.compile(r"```(?:netcfg|cli|bash|shell)?[ \t]*\r?\n(.*?)```", re.S)
_NOTE_RE = re.compile(r"\s+#\s*(?=\S)(.+)$")


def split_cmd_note(line: str):
    """`cmd  # 中文释义` → (cmd, note)；命令体内没有注释时 note 为空"""
    m = _NOTE_RE.search(line)
    if m:
        return line[:m.start()].rstrip(), m.group(1).strip()
    return line, ""


def parse_command_blocks(text: str) -> list:
    """AI 回复 → 命令卡片数据 [{'cmd','note','risk'}]
    只认 fenced 代码块（强提示词约定），正文散文绝不误入队列——宁缺勿滥。
    行首 <host> / [host] 提示符自动剥除；块内空行/注释行跳过；完全重复命令去重。"""
    cards = []
    seen = set()
    for blk in CMD_FENCE_RE.findall(text or ""):
        for raw in blk.splitlines():
            s = raw.strip()
            if not s or s.startswith("#"):
                continue
            s = re.sub(r"^(?:<[A-Za-z0-9\-_.@]+>|\[[A-Za-z0-9\-_.@]+\])\s*", "", s)
            cmd, note = split_cmd_note(s)
            if not cmd:
                continue
            key = re.sub(r"\s+", " ", cmd.lower())
            if key in seen:
                continue
            seen.add(key)
            cards.append({"cmd": cmd, "note": note or note_of(cmd) or "",
                          "risk": classify_command(cmd)})
    return cards


def lint_cards(cards: list, vendor: str) -> dict:
    """把卡片命令喂给现有 config_lint 做语法体检，问题挂到对应卡片 c['lint']=[issue...]"""
    for c in cards:
        c["lint"] = []
    if not cards:
        return {"items": [], "stats": {}}
    text = "\n".join(c["cmd"] for c in cards)
    try:
        result = lint(text, vendor if vendor in VENDORS else "huawei")
    except Exception:
        return {"items": [], "stats": {}}
    for it in result.get("items", []):
        idx = it.get("line_no", 0) - 1
        if 0 <= idx < len(cards):
            cards[idx]["lint"].append(it)
    return result


# ---------------------------------------------------------------- 规则引擎兜底（离线降级）
def fallback_parse(text: str, vendor: str) -> list:
    """AI 不可用/无输出时，退回离线规则引擎 nl_engine，卡片结构与 AI 路径完全一致"""
    r = nl_engine.parse(text, vendor)
    cards = []
    for cmd, note in r.get("lines", []):
        stripped = cmd.strip()
        if not stripped:
            continue
        cards.append({"cmd": stripped, "note": note, "risk": classify_command(stripped),
                      "lint": []})
    return cards, r.get("unknown", [])


# ---------------------------------------------------------------- 自测
if __name__ == "__main__":
    import io
    import sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    demo_reply = (
        "好的，创建 VLAN 并划端口：\n```netcfg\n"
        "system-view # 进入系统视图\n"
        "vlan batch 10 20 # 批量创建 VLAN\n"
        "interface GigabitEthernet1/0/1\n"
        " port link-type access\n"
        " port default vlan 10\n"
        "undo stp enable  # 关掉生成树\n"
        "display vlan 10 # 核对\n```\n"
        "注意 undo 属删除类命令，高危。"
    )
    cards = parse_command_blocks(demo_reply)
    print("== 命令卡片 ==")
    for c in cards:
        print(f"[{c['risk']:<9}] {c['cmd']:<44} # {c['note']}")
    lint_cards(cards, "huawei")
    print("\n== lint 体检 ==")
    for c in cards:
        for it in c["lint"]:
            print(f"  {c['cmd'][:30]}: [{it['level']}] {it['issue']}")
    fb, unknown = fallback_parse("创建vlan10，把gi1/0/1划入vlan10", "huawei")
    print("\n== 规则引擎兜底 ==")
    for c in fb:
        print(f"[{c['risk']:<9}] {c['cmd']:<44} # {c['note']}")
    print("规则未识别:", unknown)
