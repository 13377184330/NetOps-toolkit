# -*- coding: utf-8 -*-
"""AI 运维页逻辑冒烟：渲染、卡片队列、队列刷新（离屏无头，不连真机不调 AI）"""
import io
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtWidgets import QApplication
app = QApplication([])

from modules import ai_ops
from gui.tabs.ai_ops_tab import AIOpsTab, _render_ai_content

# 1) AI 正文渲染：fenced 块命令着色 + 高危行红色
reply = ("好的，按你的需求：\n```netcfg\n"
         "system-view # 进入系统视图\n"
         "vlan batch 10 20 # 批量建 VLAN\n"
         "undo vlan 30 # 删掉 VLAN 30\n"
         "display vlan # 核对\n```\n注意 undo 是高危操作。")
html = _render_ai_content(reply)
assert "1E2430" in html, "代码块深色底未渲染"
assert "#FA5151" in html, "高危行未标红"
assert "undo vlan 30" in html
print("[1] 渲染：fence 代码块 + 高危红行 OK")

# 2) 解析 + lint + 入队
cards = ai_ops.parse_command_blocks(reply)
risks = [c["risk"] for c in cards]
assert risks[2] == "dangerous" and risks[3] == "readonly", risks
ai_ops.lint_cards(cards, "huawei")
print("[2] 解析风险分级：", [(c["cmd"], c["risk"]) for c in cards])

# 3) 离屏构建页面：布局不崩、队列卡片可增删、部署按钮联动
tab = AIOpsTab()
tab._queue_cards(cards, source="AI")
assert len(tab._cards) == 4 and tab.queue_lay.count() >= 4
assert not tab.deploy_btn.isEnabled(), "默认无勾选，不应可执行"
# 勾选一条写命令
tab._on_card_checked(0, True)
assert tab.deploy_btn.isEnabled() and tab.deploy_btn.text().startswith("下发所选（1）")
# 勾选一条只读命令（readonly 可勾选执行，运维闭环）
tab._on_card_checked(3, True)
assert tab.deploy_btn.text().startswith("执行所选（验证 1 · 下发 1）"), tab.deploy_btn.text()
# 全选：readonly 也勾（只读验证命令可执行）
tab._toggle_all(True)
n_checked = sum(1 for c in tab._cards if c["checked"])
assert n_checked == 4, f"全选应含只读共 4 条，实际 {n_checked}"
assert tab.deploy_btn.text().startswith("执行所选（验证 1 · 下发 3）"), tab.deploy_btn.text()
# 执行分流：纯只读 → 轻量确认链；含写 → 备份链（这里只验分流数据，不连真机）
picks = [c for c in tab._cards if c["checked"]]
read_lines = [c["cmd"] for c in picks if c["risk"] == "readonly"]
write_lines = [c["cmd"] for c in picks if c["risk"] != "readonly"]
assert read_lines == ["display vlan"] and len(write_lines) == 3
# 回显注入 AI 上下文：device 角色 + build_messages 映射为 user
tab._append_device_echo("display vlan", "VLAN 10 → gigabitethernet1/0/1")
assert tab._history[-1]["role"] == "device" and "VLAN 10" in tab._history[-1]["content"]
msgs = ai_ops.build_messages("analyze", "huawei", tab._history, "继续分析")
roles = [m["role"] for m in msgs]
assert "device" not in roles and roles.count("user") >= 2, roles
print("[3] 队列：全选含只读 / 按钮分档 / 执行分流 / 回显回注 AI 上下文 OK")

# 4) 降级路径：AI 失败时规则引擎兜底进队
fb_cards, unknown = ai_ops.fallback_parse("创建vlan10，把gi1/0/1划入vlan10", "huawei")
assert fb_cards, "规则引擎兜底未产出"
tab2 = AIOpsTab()
tab2._queue_cards(fb_cards, source="离线规则引擎")
assert len(tab2._cards) == len(fb_cards)
print("[4] 离线兜底：", [c["cmd"] for c in fb_cards][:3], "…")

# 6) 保存回读（先备份原配置，测完还原，不污染用户设置）
from gui.dialogs.settings_dialog import SettingsDialog
from utils.settings import Settings
_s = Settings()
_ai_backup = dict(_s.get("ai", {}) or {})
dlg = SettingsDialog()
assert dlg.tabs_widget.count() == 4
dlg.go_ai_tab()
assert dlg.tabs_widget.tabText(dlg.tabs_widget.currentIndex()) == "AI"
assert dlg.ai_provider_combo.count() == len(ai_ops.PROVIDERS)
print("[5] 设置页：AI 页存在（4 tab），预设", dlg.ai_provider_combo.count(), "项")

# 保存回读
dlg.ai_provider_combo.setCurrentIndex(0)
dlg.ai_base_edit.setText("https://api.deepseek.com/v1")
dlg.ai_model_edit.setText("deepseek-chat")
dlg._save_ai_config()
cfg = ai_ops.get_ai_config()
assert cfg["configured"] and cfg["model"] == "deepseek-chat", cfg
print("[6] 配置回读：", {k: (v[:18] if isinstance(v, str) else v) for k, v in cfg.items()})
_s.set("ai", _ai_backup)   # 还原用户原配置，测试不污染设置

# 7) 未配置时 stream_chat 应给中文提示（空 config 直测，不依赖真实设置）
empty_cfg = {"base_url": "", "model": "", "api_key": "", "configured": False}
full, err = ai_ops.stream_chat([{"role": "user", "content": "hi"}], config=empty_cfg)
assert err and "未配置" in err, f"未配置时应有中文错误提示，实际: {err!r}"
print("[7] 未配置提示 OK:", err)

print("\n=== 全部冒烟通过 ===")
