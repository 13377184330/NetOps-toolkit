# 设备凭据加密存储（复用 cryptography 库，不自造加密算法）
import os
import stat
import sys
import shutil
import subprocess
from cryptography.fernet import Fernet

from utils.app_paths import app_root

# 密钥与 settings.json 同存于数据根 config/，并加入 .gitignore
# 开发态 = 项目根；冻结态 = exe 同目录（_MEIPASS 是只读临时目录，密钥放那里每次启动都变，
# 已加密的设备凭据将全部无法解密）
_KEY_FILE = os.path.join(app_root(), "config", "secret.key")


def _lock_permissions(path: str):
    """把密钥文件权限收紧为仅当前用户可访问。
    Windows：os.chmod 只认只读位，不支持 owner/group/other 模型（实测 chmod(0o600)
      后仍是 0o666），必须用 ACL——icacls 关闭继承并只授当前用户完全控制。
    类 Unix：os.chmod(0o600) 即可。"""
    if os.name == "nt":
        try:
            user = os.environ.get("USERNAME") or ""
            if not user:
                return
            # /inheritance:r 移除继承的 ACL；/grant:r 只给当前用户完全控制（覆盖式）
            subprocess.run(
                ["icacls", path, "/inheritance:r", "/grant:r", f"{user}:F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False, timeout=10,
            )
        except Exception:
            pass  # ACL 加固失败不影响功能
    else:
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600
        except Exception:
            pass


def _valid_key(key: bytes) -> bool:
    """校验是否为合法 Fernet 密钥（32 字节 url-safe base64）。"""
    try:
        Fernet(key)
        return True
    except (ValueError, TypeError):
        return False


def _load_or_create_key() -> bytes:
    """加载或创建加密密钥，确保文件权限安全（仅当前用户可读写）"""
    key_dir = os.path.dirname(_KEY_FILE)
    os.makedirs(key_dir, exist_ok=True)

    if os.path.exists(_KEY_FILE):
        _lock_permissions(_KEY_FILE)
        with open(_KEY_FILE, "rb") as f:
            key = f.read().strip()
        if _valid_key(key):
            return key
        # 坏密钥：尽力备份（失败不影响后续覆盖），然后生成新 key 直接覆盖。
        # 关键是绝不让坏 key 继续流向模块级 Fernet()，否则导入期崩溃。
        try:
            shutil.copy2(_KEY_FILE, _KEY_FILE + ".corrupt")
        except OSError:
            pass

    key = Fernet.generate_key()
    # 直接覆盖写：无论是首次创建还是坏密钥重建，都不依赖文件是否已移走，
    # 避免 O_EXCL 竞态分支又把旧坏 key 读回来。
    fd = os.open(_KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    handed_off = False
    try:
        f = os.fdopen(fd, "wb")
        handed_off = True
        with f:
            f.write(key)
    finally:
        if not handed_off:
            os.close(fd)

    _lock_permissions(_KEY_FILE)
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
