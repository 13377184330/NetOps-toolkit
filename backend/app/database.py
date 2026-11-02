# 数据库连接（SQLAlchemy 2.x async + SQLite）
import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "netops.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

engine = create_async_engine(f"sqlite+aiosqlite:///{DB_PATH}", echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    """FastAPI 依赖注入：获取数据库会话"""
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    """建表（开发期用 create_all，后续迁移再引入 alembic）"""
    from .models import device  # noqa: F401 确保模型注册
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
