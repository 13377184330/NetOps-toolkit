# 设备凭据加密存储（复用 cryptography 库，不自造加密算法）
import os
from cryptography.fernet import Fernet

from utils.app_paths import app_root

# 密钥与 settings.json 同存于数据根 config/，并加入 .gitignore
# 开发态 = 项目根；冻结态 = exe 同目录（_MEIPASS 是只读临时目录，密钥放那里每次启动都变，
# 已加密的设备凭据将全部无法解密）
_KEY_FILE = os.path.join(app_root(), "config", "secret.key")


def _load_or_create_key() -> bytes:
    os.makedirs(os.path.dirname(_KEY_FILE), exist_ok=True)
    if os.path.exists(_KEY_FILE):
        with open(_KEY_FILE, "rb") as f:
            return f.read().strip()
    key = Fernet.generate_key()
    with open(_KEY_FILE, "wb") as f:
        f.write(key)
    return key


_fernet = Fernet(_load_or_create_key())


def encrypt(plain: str) -> str:
    """加密明文，返回 base64 密文字符串"""
    if not plain:
        return ""
    return _fernet.encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt(token: str) -> str:
    """解密密文，失败返回空字符串（不抛异常，避免凭据损坏拖垮 API）"""
    if not token:
        return ""
    try:
        return _fernet.decrypt(token.encode("ascii")).decode("utf-8")
    except Exception:
        return ""
