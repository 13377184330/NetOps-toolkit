# 设备管理 API：CRUD + SSH 连通性测试
import asyncio
import time
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.device import Device
from ..schemas.device import DeviceCreate, DeviceUpdate, DeviceOut, ConnectionTestResult
from ..core import crypto

router = APIRouter(prefix="/api/devices", tags=["devices"])


async def _tcp_probe(ip: str, port: int, timeout: float = 3.0) -> tuple[bool, str, float | None]:
    """M1 连通测试：TCP 探测管理端口（SSH）。
    不做 SSH 握手，零凭据依赖；真实 SSH 命令执行在 M2 用 Netmiko 实现。
    """
    start = time.perf_counter()
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout=timeout)
        latency = (time.perf_counter() - start) * 1000
        # 尝试读取 SSH banner，进一步确认是网络设备
        banner = ""
        try:
            banner_bytes = await asyncio.wait_for(reader.read(64), timeout=1.5)
            banner = banner_bytes.decode("utf-8", errors="ignore").strip()
        except Exception:
            pass
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True, f"端口 {port} 可达" + (f"，banner: {banner[:40]}" if banner else ""), round(latency, 1)
    except asyncio.TimeoutError:
        return False, f"连接超时（{timeout}s）：{ip}:{port} 无响应", None
    except (ConnectionRefusedError, OSError) as e:
        return False, f"连接失败：{type(e).__name__} {e}", None


@router.get("", response_model=dict)
async def list_devices(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    keyword: str = Query("", description="按名称/IP/型号模糊搜索"),
    vendor: str = Query("", description="按厂商过滤"),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Device)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(
            Device.name.like(like) | Device.ip.like(like) | Device.model.like(like)
        )
    if vendor:
        stmt = stmt.where(Device.vendor == vendor)

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    rows = (
        await db.execute(
            stmt.order_by(Device.id.desc()).offset((page - 1) * page_size).limit(page_size)
        )
    ).scalars().all()
    return {"total": total, "items": [DeviceOut.model_validate(r) for r in rows]}


@router.post("", response_model=DeviceOut)
async def create_device(payload: DeviceCreate, db: AsyncSession = Depends(get_db)):
    device = Device(
        **payload.model_dump(exclude={"password"}),
        password_enc=crypto.encrypt(payload.password),
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return device


@router.get("/{device_id}", response_model=DeviceOut)
async def get_device(device_id: int, db: AsyncSession = Depends(get_db)):
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(404, "设备不存在")
    return device


@router.put("/{device_id}", response_model=DeviceOut)
async def update_device(device_id: int, payload: DeviceUpdate, db: AsyncSession = Depends(get_db)):
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(404, "设备不存在")
    data = payload.model_dump(exclude={"password"})
    for k, v in data.items():
        setattr(device, k, v)
    if payload.password is not None:  # 传了才改，不传保持原密码
        device.password_enc = crypto.encrypt(payload.password)
    await db.commit()
    await db.refresh(device)
    return device


@router.delete("/{device_id}")
async def delete_device(device_id: int, db: AsyncSession = Depends(get_db)):
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(404, "设备不存在")
    await db.delete(device)
    await db.commit()
    return {"ok": True}


@router.post("/{device_id}/test-connection", response_model=ConnectionTestResult)
async def test_connection(device_id: int, db: AsyncSession = Depends(get_db)):
    """对设备做连通性测试（TCP 探测 SSH 端口），并回写状态"""
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(404, "设备不存在")
    ok, msg, latency = await _tcp_probe(device.ip, device.ssh_port)
    device.status = "online" if ok else "offline"
    device.last_check = datetime.now()
    await db.commit()
    return ConnectionTestResult(success=ok, message=msg, latency_ms=latency)
