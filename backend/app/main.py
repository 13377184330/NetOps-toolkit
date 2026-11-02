# FastAPI 入口
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import init_db
from .api.devices import router as devices_router
from .api.generate import router as generate_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="NetOps Toolkit Web API",
    description="网络设备配置自动化平台（基于 NetOps-toolkit 二开：PyQt 桌面版引擎 + Web 平台化）",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(devices_router)
app.include_router(generate_router)


@app.get("/api/health")
async def health():
    return {"ok": True, "service": "netops-toolkit-web"}
