# 设备凭据加密存储（复用 cryptography 库，不自造加密算法）
import os
import stat
from cryptography.fernet import Fernet

from utils.app_paths import app_root

# 密钥与 settings.json 同存于数据根 config/，并加入 .gitignore
# 开发态 = 项目根；冻结态 = exe 同目录（_MEIPASS 是只读临时目录，密钥放那里每次启动都变，
# 已加密的设备凭据将全部无法解密）
_KEY_FILE = os.path.join(app_root(), "config", "secret.key")


def _load_or_create_key() -> bytes:
    """加载或创建加密密钥，确保文件权限安全（仅当前用户可读）"""
    key_dir = os.path.dirname(_KEY_FILE)
    os.makedirs(key_dir, exist_ok=True)
    
    if os.path.exists(_KEY_FILE):
        # 验证并修正权限（多用户环境下防止泄露）
        try:
            file_stat = os.stat(_KEY_FILE)
            file_mode = file_stat.st_mode & 0o777
            if file_mode != 0o600:
                os.chmod(_KEY_FILE, 0o600)
        except Exception:
            pass  # 权限调整失败不影响读取
        
        with open(_KEY_FILE, "rb") as f:
            return f.read().strip()
    
    # 创建新密钥，安全权限：仅当前用户可读写
    key = Fernet.generate_key()
    
    # 使用 os.open 的 mode 参数直接创建 0o600 权限的文件（原子操作，更安全）
    try:
        fd = os.open(_KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(key)
        except Exception:
            os.close(fd)
            raise
    except FileExistsError:
        # 竞态条件：另一进程同时创建，重新读取
        with open(_KEY_FILE, "rb") as f:
            return f.read().strip()
    
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
