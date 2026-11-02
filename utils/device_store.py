#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
设备清单存储
设备信息存 config/devices.json，SSH 密码用 Fernet 加密（utils.credential_crypto）
存储风格与上游 Settings 单例保持一致
"""

import os
import json
from datetime import datetime

from utils.credential_crypto import encrypt, decrypt

DEVICES_FILE = os.path.join(os.path.dirname(__file__), "..", "config", "devices.json")


class DeviceStore:
    """设备清单管理（单例，风格对齐 utils.settings.Settings）"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._devices = []
            cls._instance._load()
        return cls._instance

    # ---------- 持久化 ----------
    def _load(self):
        try:
            os.makedirs(os.path.dirname(DEVICES_FILE), exist_ok=True)
            if os.path.exists(DEVICES_FILE):
                with open(DEVICES_FILE, "r", encoding="utf-8") as f:
                    self._devices = json.load(f)
        except Exception as e:
            print(f"加载设备清单失败: {e}")
            self._devices = []

    def _save(self):
        try:
            os.makedirs(os.path.dirname(DEVICES_FILE), exist_ok=True)
            with open(DEVICES_FILE, "w", encoding="utf-8") as f:
                json.dump(self._devices, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"保存设备清单失败: {e}")

    # ---------- 增删改查 ----------
    def list_all(self, keyword=""):
        """全部设备，支持按名称/IP/型号模糊过滤；密码永不返回明文"""
        if not keyword:
            items = list(self._devices)
        else:
            kw = keyword.lower()
            items = [d for d in self._devices
                     if kw in d.get("name", "").lower()
                     or kw in d.get("ip", "").lower()
                     or kw in d.get("model", "").lower()]
        out = []
        for d in items:
            x = dict(d)
            x.pop("password_enc", None)
            x["has_password"] = bool(d.get("password_enc"))
            out.append(x)
        return out

    def get(self, device_id):
        return next((d for d in self._devices if d.get("id") == device_id), None)

    def get_plain_password(self, device_id):
        """供连接器使用：解密取回明文密码（仅内部调用，不进 GUI）"""
        d = self.get(device_id)
        if not d:
            return ""
        return decrypt(d.get("password_enc", ""))

    def add(self, data: dict):
        device = {
            "id": max([d.get("id", 0) for d in self._devices], default=0) + 1,
            "name": data.get("name", ""),
            "ip": data.get("ip", ""),
            "ssh_port": int(data.get("ssh_port", 22)),
            "vendor": data.get("vendor", "huawei"),
            "model": data.get("model", ""),
            "role": data.get("role", "access"),
            "username": data.get("username", ""),
            "password_enc": encrypt(data.get("password", "")),
            "notes": data.get("notes", ""),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._devices.append(device)
        self._save()
        return device["id"]

    def update(self, device_id, data: dict):
        d = self.get(device_id)
        if not d:
            return False
        for k in ("name", "ip", "ssh_port", "vendor", "model", "role", "username", "notes"):
            if k in data:
                d[k] = data[k]
        if "password" in data and data["password"]:  # 空密码=不修改
            d["password_enc"] = encrypt(data["password"])
        self._save()
        return True

    def delete(self, device_id):
        before = len(self._devices)
        self._devices = [d for d in self._devices if d.get("id") != device_id]
        self._save()
        return len(self._devices) < before
