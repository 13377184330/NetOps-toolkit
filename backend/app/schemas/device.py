from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from typing import Optional


class DeviceBase(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    ip: str = Field(min_length=1, max_length=64)
    ssh_port: int = Field(default=22, ge=1, le=65535)
    vendor: str = Field(default="huawei")
    model: str = Field(default="", max_length=64)
    role: str = Field(default="access")
    username: str = Field(default="", max_length=64)
    notes: str = Field(default="")

    @field_validator("vendor")
    @classmethod
    def check_vendor(cls, v: str) -> str:
        allowed = {"huawei", "h3c", "ruijie", "maipu", "cisco"}
        if v not in allowed:
            raise ValueError(f"vendor 必须是 {allowed} 之一")
        return v

    @field_validator("role")
    @classmethod
    def check_role(cls, v: str) -> str:
        allowed = {"access", "core", "exit", "dc"}
        if v not in allowed:
            raise ValueError(f"role 必须是 {allowed} 之一")
        return v


class DeviceCreate(DeviceBase):
    password: str = Field(default="", max_length=128)  # 明文进、加密存


class DeviceUpdate(DeviceBase):
    password: Optional[str] = Field(default=None, max_length=128)  # None=不改密码


class DeviceOut(DeviceBase):
    id: int
    status: str
    last_check: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConnectionTestResult(BaseModel):
    success: bool
    message: str
    latency_ms: Optional[float] = None
