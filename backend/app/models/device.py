from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Base


class Device(Base):
    """网络设备表"""
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), index=True)          # 设备名称
    ip: Mapped[str] = mapped_column(String(64), index=True)            # 管理IP
    ssh_port: Mapped[int] = mapped_column(Integer, default=22)         # SSH端口
    vendor: Mapped[str] = mapped_column(String(16), default="huawei")  # 厂商: huawei/h3c/ruijie/maipu/cisco
    model: Mapped[str] = mapped_column(String(64), default="")         # 型号
    role: Mapped[str] = mapped_column(String(32), default="access")    # 角色: access/core/exit/dc
    username: Mapped[str] = mapped_column(String(64), default="")      # 登录用户名
    password_enc: Mapped[str] = mapped_column(Text, default="")        # 加密后的密码
    status: Mapped[str] = mapped_column(String(16), default="unknown")  # unknown/online/offline
    last_check: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
