# -*- coding: utf-8 -*-
"""AI 运维 5 项迭代综合验证（离屏，不连真机不调 AI）"""
import io
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtWidgets import QApplication
app = QApplication([])

from modules import ai_ops
from gui.tabs.ai_ops_tab import AIOpsTab, _DeployConfirmDialog, _SCENE_TEMPLATES

tab = AIOpsTab()

# 迭代1：附加设备配置开关 + 无设备时走纯文本
assert tab.attach_cb.isChecked(), "附加设备配置默认应勾选"
assert tab._selected_device_ready() is None, "未选设备应返回 None"
print("[1] 迭代1：attach_cb 默认勾选 + 无设备 _selected_device_ready=None OK")

# 迭代3：场景模板填充
n_tpl = len(_SCENE_TEMPLATES) - 1   # 去掉占位项
assert n_tpl >= 6, f"场景模板应 ≥6 个，实际 {n_tpl}"
tab.scene_combo.setCurrentIndex(1)
tab._apply_scene_template(1)
filled = tab.input_view.toPlainText()
assert "接入" in filled and filled.strip(), "模板应填充输入框"
assert tab.scene_combo.currentIndex() == 0, "填充后应复位到占位项"
print(f"[2] 迭代3：场景模板 {n_tpl} 个，点选填充输入框 OK")

# 迭代4：批量下发按钮存在
assert tab.batch_btn is not None and "批量下发" in tab.batch_btn.text()
print("[3] 迭代4：批量下发按钮存在 OK")

# 迭代2：确认弹窗接受备份状态参数
dlg = _DeployConfirmDialog(tab, "SW-01（192.168.1.1 · 华为）",
                           ["system-view", "vlan batch 10"], 0,
                           backup_ok=True, backup_text="已自动备份变更前配置（ID xxx）")
dlg.deleteLater()
print("[4] 迭代2：确认弹窗带备份状态参数可构建 OK")

# 迭代5：审计枚举 + _audit_deploy 集成不抛异常
from utils.audit_manager import AuditAction, AuditManager
assert AuditAction.AI_DEPLOY.value == "AI 下发"
# 用临时目录验证 log 写入（不污染真实 audit 目录）
tmp = tempfile.mkdtemp(prefix="ai_audit_test_")
m = AuditManager(audit_dir=tmp)
m.log(AuditAction.AI_DEPLOY, "下发 2 条命令", device_name="SW-01",
      device_type="华为", details={"commands": ["vlan batch 10"]},
      result="成功", ip_address="192.168.1.1")
assert len(m.logs) == 1 and m.logs[0].action == "AI 下发"
# _audit_deploy 集成（真实目录，内部 try/except 兜底不抛）
tab._audit_deploy({"name": "SW-01", "ip": "192.168.1.1", "vendor": "huawei"},
                  ["display vlan", "vlan batch 10"], True, "ok")
print("[5] 迭代5：AI_DEPLOY 枚举 + 审计写入 + _audit_deploy 集成 OK")

print("\n=== AI 运维 5 项迭代综合验证通过 ===")
