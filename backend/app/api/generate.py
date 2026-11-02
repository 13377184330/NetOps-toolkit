# 配置生成 API：复用原项目 modules/ 引擎（fork 二开核心资产）
from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional

from modules.vlan_config import VLANConfigGenerator

router = APIRouter(prefix="/api/generate", tags=["generate"])


class PortVlanItem(BaseModel):
    interface: str = Field(examples=["GE0/0/1"])
    type: str = Field(default="access", pattern="^(access|trunk|hybrid)$")
    vlan_id: Optional[int] = None
    trunk_vlans: Optional[list[int]] = None
    pvid: Optional[int] = None


class VlanIfItem(BaseModel):
    vlan_id: int
    ip_address: str = Field(examples=["192.168.10.1"])
    mask: str = Field(default="255.255.255.0")
    description: Optional[str] = None


class VlanGenerateRequest(BaseModel):
    """VLAN 配置生成请求（M1 先支持华为语法，H3C/锐捷/迈普/思科 M2 统一参数化）"""
    vendor: str = Field(default="huawei", pattern="^(huawei|h3c|ruijie|maipu|cisco)$")
    vlans: list[int | dict] = Field(default_factory=list, description="VLAN ID 列表，支持 [10,20] 或 [{'id':10,'name':'office'}]")
    interfaces: list[PortVlanItem] = Field(default_factory=list)
    vlanifs: list[VlanIfItem] = Field(default_factory=list)
    stp: Optional[dict] = None


class GenerateResponse(BaseModel):
    vendor: str
    config: str


@router.post("/vlan", response_model=GenerateResponse)
async def generate_vlan(req: VlanGenerateRequest):
    """一键生成 VLAN 配置（调用上游 NetOps-toolkit 的生成引擎）"""
    config = VLANConfigGenerator.generate_vlan_all(req.model_dump())
    return GenerateResponse(vendor=req.vendor, config=config)
