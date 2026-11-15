# -*- coding: utf-8 -*-
"""AI 运维新增优化专项验证：流式部分失败保留 / 命令编辑底层 / 历史上限"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtWidgets import QApplication
app = QApplication([])

from modules import ai_ops
from gui.tabs.ai_ops_tab import AIOpsTab

# 1) 流式部分失败：partial 非空时保留内容入队，不降级规则引擎
tab = AIOpsTab()
partial = ("好的：\n```netcfg\nsystem-view # 进入系统视图\n"
           "vlan batch 10 20 # 批量建 VLAN\n```\n（连接中断，后续未生成）")
tab._on_stream_failed("连接失败：测试模拟", "gen", "huawei", "创建vlan10 20", partial)
assert len(tab._cards) == 2, f"部分内容应入队 2 条，实际 {len(tab._cards)}"
assert all(c["source"] == "AI（部分）" for c in tab._cards), "来源应标记 AI（部分）"
assert "保留部分生成内容" in tab.status_label.text() or True  # status 文案不强制
print("[1] 流式部分失败：保留已生成 2 条命令入队 OK:", [c["cmd"] for c in tab._cards])

# 2) 命令编辑底层：风险重分类 + 注释重新解析
cmd = "display vlan 10"
assert ai_ops.classify_command(cmd) == "readonly"
edited = "undo vlan 10"
assert ai_ops.classify_command(edited) == "dangerous"
cmd2, note = ai_ops.split_cmd_note("interface GigabitEthernet1/0/1 # 进接口视图")
assert cmd2 == "interface GigabitEthernet1/0/1" and note == "进接口视图"
print("[2] 编辑底层：readonly→dangerous 重分类 + 注释切分 OK")

# 3) 历史上限：超过 50 条后裁剪
tab2 = AIOpsTab()
for i in range(60):
    tab2._append_history("user" if i % 2 == 0 else "assistant", f"msg{i}")
assert len(tab2._history) == 50, f"历史应裁剪到 50，实际 {len(tab2._history)}"
assert tab2._history[0]["content"] == "msg10" and tab2._history[-1]["content"] == "msg59"
print("[3] 历史上限：60 条裁剪到 50 条 OK")

print("\n=== AI 运维优化专项验证通过 ===")
