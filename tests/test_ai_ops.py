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
assert not tab.deploy_btn.isEnabled(), "默认无勾选，不应可下发"
# 勾选一条写命令
tab._on_card_checked(0, True)
assert tab.deploy_btn.isEnabled() and tab.deploy_btn.text().startswith("下发所选（1）")
# readonly 不可勾选（chk 被禁用）——由 UI 层保证；逻辑层全选应跳过 readonly
tab._toggle_all(True)
n_checked = sum(1 for c in tab._cards if c["checked"])
assert n_checked == 3, f"全选应只勾 3 条（1 只读除外），实际 {n_checked}"
print("[3] 队列：入队 4 条 / 全选跳过只读 / 下发按钮联动 OK")

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
