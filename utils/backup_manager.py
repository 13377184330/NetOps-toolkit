#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
配置备份管理器
"""

import os
import json
import shutil
import hashlib
import zipfile
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
import difflib

from utils.app_paths import app_root


@dataclass
class BackupRecord:
    """备份记录"""
    id: str
    filename: str
    device_name: str
    device_type: str
    ip_address: str
    backup_time: str
    file_size: int
    md5_hash: str
    description: str
    is_auto: bool
    tags: List[str]
    operator: str = ""      # 操作人（Windows 登录名；老记录无此字段兼容为空）


class ConfigBackupManager:
    """配置备份管理器（v2：备份 Git 化——学 Oxidized 的核心机制）

    每台设备一个 Git 仓库目录 backups/git/<设备>/，每次 create_backup 自动 commit：
    - 配置变更链完整可回溯（谁在何时改了哪一行 → git log -p）
    - 任意历史版本可检出恢复
    - git 不可用（未安装/打包环境缺 git.exe）时优雅降级为纯文件备份，不影响主流程
    """

    # Git 元信息目录名（.git 放在各设备仓库内）
    _GIT_SUBDIR = "git"
    
    def __init__(self, backup_dir: str = None):
        if backup_dir is None:
            # 开发态：项目根/backups（保持现状）；冻结态：exe 同目录/backups（可写持久）
            backup_dir = os.path.join(app_root(), "backups")
        
        self.backup_dir = os.path.abspath(backup_dir)
        os.makedirs(self.backup_dir, exist_ok=True)
        
        self.records_file = os.path.join(self.backup_dir, "backup_records.json")
        self.records: List[BackupRecord] = []
        self._load_records()
    
    def _load_records(self):
        if os.path.exists(self.records_file):
            try:
                with open(self.records_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.records = [BackupRecord(**r) for r in data]
            except Exception:
                self.records = []
    
    def _save_records(self):
        try:
            with open(self.records_file, 'w', encoding='utf-8') as f:
                json.dump([asdict(r) for r in self.records], f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存备份记录失败: {e}")
    
    def _calculate_md5(self, file_path: str) -> str:
        hash_md5 = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    
    def _generate_id(self) -> str:
        return datetime.now().strftime("%Y%m%d%H%M%S%f")
    
    def create_backup(self, config_content: str, device_name: str, device_type: str,
                     ip_address: str = "", description: str = "",
                     is_auto: bool = False, tags: List[str] = None,
                     operator: str = "") -> Optional[str]:
        """创建配置备份（operator：操作人——默认 Windows 登录名）"""
        try:
            if not operator:
                import getpass
                operator = getpass.getuser()
            backup_id = self._generate_id()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            filename = f"{device_type}_{device_name}_{timestamp}.cfg"
            filename = filename.replace(" ", "_").replace("/", "-")
            
            file_path = os.path.join(self.backup_dir, filename)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(config_content)
            
            file_size = os.path.getsize(file_path)
            md5_hash = self._calculate_md5(file_path)
            
            record = BackupRecord(
                id=backup_id,
                filename=filename,
                device_name=device_name,
                device_type=device_type,
                ip_address=ip_address,
                backup_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                file_size=file_size,
                md5_hash=md5_hash,
                description=description,
                is_auto=is_auto,
                tags=tags or [],
                operator=operator,
            )
            
            self.records.append(record)
            self._save_records()

            # Git 化：当前配置另存为设备仓库的 running.cfg 并自动 commit
            # （失败不影响备份主流程——降级为纯文件备份）
            self._git_snapshot(config_content, record)

            return backup_id
        except Exception as e:
            print(f"创建备份失败: {e}")
            return None

    # ---------------- Git 快照层（学 Oxidized：每设备一个仓库，变更即 commit） ----------------
    def _git_available(self) -> bool:
        """git CLI 是否可用（缓存结果，避免每次备份都探测）"""
        if not hasattr(self, "_git_ok"):
            import shutil as _sh
            self._git_ok = bool(_sh.which("git"))
        return self._git_ok

    def _device_repo_dir(self, device_name: str, device_type: str) -> str:
        safe = f"{device_type}_{device_name}".replace(" ", "_").replace("/", "-")
        return os.path.join(self.backup_dir, self._GIT_SUBDIR, safe)

    def _git_snapshot(self, config_content: str, record: BackupRecord):
        """把当前配置作为 running.cfg 提交到设备 Git 仓库。
        - 首次运行自动 init 仓库（identity 用本地占位，不动全局配置）
        - 配置无变化时跳过 commit（不产生噪声提交）
        - 异常一律吞掉（备份本身已成功，Git 层失败只降级）"""
        try:
            if not self._git_available():
                return
            import subprocess
            repo = self._device_repo_dir(record.device_name, record.device_type)
            os.makedirs(repo, exist_ok=True)
            cfg_path = os.path.join(repo, "running.cfg")
            with open(cfg_path, "w", encoding="utf-8") as f:
                f.write(config_content)

            def git(*args):
                return subprocess.run(
                    ["git", "-C", repo] + list(args),
                    capture_output=True, text=True, timeout=30,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

            if not os.path.isdir(os.path.join(repo, ".git")):
                r = git("init", "-q")
                if r.returncode != 0:
                    return
                git("config", "user.name", "NetOps-Toolkit")
                git("config", "user.email", "netops@local")

            git("add", "running.cfg")
            # 变更检测：无 diff 不提交
            staged = git("diff", "--cached", "--quiet")
            if staged.returncode == 0:
                return   # 配置无变化
            msg = (f"backup {record.backup_time} [{record.device_type}/{record.device_name}] "
                   + (f"by {record.operator} " if record.operator else "")
                   + (record.description or "config backup"))
            git("commit", "-q", "-m", msg[:200])
        except Exception as e:
            # Git 层失败只降级，不影响备份功能
            print(f"[backup-git] 快照提交跳过: {e}")

    def git_history(self, device_name: str, device_type: str, limit: int = 50) -> List[Dict]:
        """设备配置变更历史（git log 一页式），供 UI 展示与回溯。
        返回 [{commit, date, message}]；git 不可用或无仓库返回 []"""
        try:
            if not self._git_available():
                return []
            import subprocess
            repo = self._device_repo_dir(device_name, device_type)
            if not os.path.isdir(os.path.join(repo, ".git")):
                return []
            r = subprocess.run(
                ["git", "-C", repo, "log", f"-{limit}", "--pretty=format:%h%x09%ad%x09%s",
                 "--date=format:%Y-%m-%d %H:%M:%S"],
                capture_output=True, text=True, timeout=30,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if r.returncode != 0:
                return []
            out = []
            for ln in (r.stdout or "").splitlines():
                parts = ln.split("\t", 2)
                if len(parts) == 3:
                    out.append({"commit": parts[0], "date": parts[1], "message": parts[2]})
            return out
        except Exception:
            return []
    
    def restore_backup(self, backup_id: str) -> Optional[str]:
        """恢复配置备份"""
        record = self.get_backup_by_id(backup_id)
        if not record:
            return None
        
        file_path = os.path.join(self.backup_dir, record.filename)
        if not os.path.exists(file_path):
            return None
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception:
            return None
    
    def delete_backup(self, backup_id: str) -> bool:
        """删除备份"""
        record = self.get_backup_by_id(backup_id)
        if not record:
            return False
        
        file_path = os.path.join(self.backup_dir, record.filename)
        
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
            
            self.records = [r for r in self.records if r.id != backup_id]
            self._save_records()
            return True
        except Exception:
            return False
    
    def get_backup_by_id(self, backup_id: str) -> Optional[BackupRecord]:
        """根据ID获取备份记录"""
        for record in self.records:
            if record.id == backup_id:
                return record
        return None
    
    def get_backups_by_device(self, device_name: str, device_type: str = None) -> List[BackupRecord]:
        """获取设备的所有备份"""
        results = []
        for record in self.records:
            if record.device_name == device_name:
                if device_type is None or record.device_type == device_type:
                    results.append(record)
        return sorted(results, key=lambda x: x.backup_time, reverse=True)
    
    def get_all_backups(self, device_type: str = None, 
                       start_date: str = None, 
                       end_date: str = None) -> List[BackupRecord]:
        """获取所有备份（支持筛选）"""
        results = self.records.copy()
        
        if device_type:
            results = [r for r in results if r.device_type == device_type]
        
        if start_date:
            results = [r for r in results if r.backup_time >= start_date]
        
        if end_date:
            results = [r for r in results if r.backup_time <= end_date]
        
        return sorted(results, key=lambda x: x.backup_time, reverse=True)
    
    @staticmethod
    def summarize_diff(diff_text: str) -> str:
        """diff → 人话摘要（改了几口/VLAN/路由/ACL——运维视角不是行数视角）"""
        add, rem = [], []
        for ln in (diff_text or "").splitlines():
            if ln.startswith("+") and not ln.startswith("+++"):
                add.append(ln[1:].strip())
            elif ln.startswith("-") and not ln.startswith("---"):
                rem.append(ln[1:].strip())
        # 高频变更域统计（以命令首词分域）
        domains = {"端口配置": 0, "VLAN": 0, "路由": 0, "ACL/安全": 0, "其他": 0}
        iface_names = set()

        def _count(ln):
            low = ln.lower()
            if low.startswith(("interface", "port")):
                domains["端口配置"] += 1
                if low.startswith("interface"):
                    parts = ln.split()
                    if len(parts) > 1:
                        iface_names.add(parts[1])
            elif low.startswith(("vlan", "port access vlan", "port trunk permit")):
                domains["VLAN"] += 1
            elif "ip route" in low or low.startswith(("route", "ospf", "bgp")):
                domains["路由"] += 1
            elif "acl" in low or "packet-filter" in low:
                domains["ACL/安全"] += 1
            else:
                domains["其他"] += 1

        for ln in add + rem:
            _count(ln)
        # 上下文行（空格开头）里的 interface 行也算"涉及端口"——
        # 真实 diff 常态：接口行不变，变的是它下面的子行
        for ln in (diff_text or "").splitlines():
            s = ln[1:].strip() if ln[:1] in (" ", "+", "-") else ln.strip()
            if s.lower().startswith("interface "):
                parts = s.split()
                if len(parts) > 1:
                    iface_names.add(parts[1])
        parts = []
        if iface_names:
            parts.append(f"涉及 {len(iface_names)} 个端口")
        for k in ("VLAN", "路由", "ACL/安全", "端口配置", "其他"):
            if k != "端口配置" and domains[k]:
                parts.append(f"{k} {domains[k]} 处")
        if not parts:
            return ""
        summary = "，".join(parts[:4])
        return f"{summary}（+{len(add)} -{len(rem)}）"

    def compare_backups(self, backup_id1: str, backup_id2: str) -> Optional[Dict]:
        """比较两个备份的差异"""
        config1 = self.restore_backup(backup_id1)
        config2 = self.restore_backup(backup_id2)
        
        if not config1 or not config2:
            return None
        
        lines1 = config1.splitlines()
        lines2 = config2.splitlines()
        
        diff = list(difflib.unified_diff(
            lines1, lines2,
            fromfile=f"备份1 ({backup_id1})",
            tofile=f"备份2 ({backup_id2})",
            lineterm=""
        ))
        
        return {
            "backup1_id": backup_id1,
            "backup2_id": backup_id2,
            "diff": "\n".join(diff),
            "added": len([l for l in diff if l.startswith('+') and not l.startswith('+++')]),
            "removed": len([l for l in diff if l.startswith('-') and not l.startswith('---')]),
            "changed": sum(1 for l in diff if l.startswith('@@'))
        }
    
    def export_backups(self, backup_ids: List[str], export_path: str) -> bool:
        """导出备份到压缩包"""
        try:
            with zipfile.ZipFile(export_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for backup_id in backup_ids:
                    record = self.get_backup_by_id(backup_id)
                    if record:
                        file_path = os.path.join(self.backup_dir, record.filename)
                        if os.path.exists(file_path):
                            zf.write(file_path, record.filename)
            
            return True
        except Exception as e:
            print(f"导出备份失败: {e}")
            return False
    
    def cleanup_old_backups(self, days: int = 30, keep_count: int = 10) -> int:
        """清理过期备份"""
        cutoff_date = datetime.now() - timedelta(days=days)
        deleted_count = 0
        
        to_delete = []
        device_backups = {}
        
        for record in self.records:
            key = (record.device_name, record.device_type)
            if key not in device_backups:
                device_backups[key] = []
            device_backups[key].append(record)
        
        for key, backups in device_backups.items():
            sorted_backups = sorted(backups, key=lambda x: x.backup_time, reverse=True)
            for i, record in enumerate(sorted_backups):
                backup_date = datetime.strptime(record.backup_time, "%Y-%m-%d %H:%M:%S")
                if i >= keep_count and backup_date < cutoff_date:
                    to_delete.append(record.id)
        
        for backup_id in to_delete:
            if self.delete_backup(backup_id):
                deleted_count += 1
        
        return deleted_count
    
    def get_backup_statistics(self) -> Dict:
        """获取备份统计信息"""
        total_count = len(self.records)
        total_size = sum(r.file_size for r in self.records)
        
        device_types = {}
        for record in self.records:
            dt = record.device_type
            device_types[dt] = device_types.get(dt, 0) + 1
        
        auto_count = sum(1 for r in self.records if r.is_auto)
        manual_count = total_count - auto_count
        
        return {
            "total_count": total_count,
            "total_size": total_size,
            "total_size_mb": round(total_size / 1024 / 1024, 2),
            "device_types": device_types,
            "auto_count": auto_count,
            "manual_count": manual_count,
            "oldest_backup": min((r.backup_time for r in self.records), default=None),
            "newest_backup": max((r.backup_time for r in self.records), default=None)
        }
