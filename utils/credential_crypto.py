# 设备凭据加密存储（复用 cryptography 库，不自造加密算法）
import os
import stat
import sys
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


def _load_or_create_key() -> bytes:
    """加载或创建加密密钥，确保文件权限安全（仅当前用户可读写）"""
    key_dir = os.path.dirname(_KEY_FILE)
    os.makedirs(key_dir, exist_ok=True)

    if os.path.exists(_KEY_FILE):
        # 现有密钥：校正权限（历史遗留的宽权限文件也一并收紧）
        _lock_permissions(_KEY_FILE)
        with open(_KEY_FILE, "rb") as f:
            key = f.read().strip()
        # 损坏的密钥（磁盘满/写入中断/手工误改）若在导入期直接交给
        # Fernet() 会抛 ValueError，导致整个设备模块链无法导入。
        # 校验失败则备份坏文件并重新生成（旧密文将不可解，需告知用户）。
        try:
            Fernet(key)
            return key
        except (ValueError, TypeError):
            # 坏密钥：备份后 fall-through 到下方统一的新密钥生成/落盘路径
            try:
                import shutil
                shutil.move(_KEY_FILE, _KEY_FILE + ".corrupt")
            except OSError:
                pass

    # 创建新密钥（首次创建，或坏密钥备份后重建）——只在此处生成一次
    key = Fernet.generate_key()

    # 类 Unix：用 os.open 的 mode 直接以 0o600 原子创建；Windows：mode 参数被忽略，稍后 ACL 收紧
    try:
        fd = os.open(_KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        handed_off = False
        try:
            # fdopen 成功后 fd 归 with 管理；失败前仍需手动关闭。
            f = os.fdopen(fd, "wb")
            handed_off = True
            with f:
                f.write(key)
        except Exception:
            if not handed_off:
                os.close(fd)
            raise
    except FileExistsError:
        # 竞态条件：另一进程同时创建，重新读取
        with open(_KEY_FILE, "rb") as f:
            return f.read().strip()

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
