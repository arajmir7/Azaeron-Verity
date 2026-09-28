"""AZAERON database configuration with async SQLAlchemy and RLS."""

from contextvars import ContextVar
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, text, func
from sqlalchemy.pool import NullPool
from datetime import datetime
import os
import uuid
from app.core.config import settings
from app.core.observability import configure_database_metrics

organization_id_ctx: ContextVar[Optional[str]] = ContextVar(
    "organization_id", default=None
)
user_id_ctx: ContextVar[Optional[str]] = ContextVar("user_id", default=None)


class Base(DeclarativeBase):
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


_engine_options: dict[str, object] = {
    "echo": settings.DEBUG,
    "future": True,
    "hide_parameters": True,
}
if settings.DATABASE_URL.startswith("postgresql"):
    _engine_options["connect_args"] = {
        "timeout": settings.DATABASE_CONNECT_TIMEOUT_SECONDS,
        "command_timeout": settings.DATABASE_COMMAND_TIMEOUT_SECONDS,
    }
# Celery prefork workers execute each task with asyncio.run().  Reusing an
# asyncpg connection created by a prior event loop causes cross-loop failures.
# NullPool creates and closes a connection within each task's loop instead.
if os.getenv("CELERY_WORKER", "").lower() == "true":
    _engine_options["poolclass"] = NullPool
else:
    _engine_options.update(
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_MAX_OVERFLOW,
        pool_recycle=settings.DATABASE_POOL_RECYCLE,
        pool_timeout=settings.DATABASE_POOL_TIMEOUT_SECONDS,
    )

engine = create_async_engine(settings.DATABASE_URL, **_engine_options)
configure_database_metrics(engine)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        org_id = organization_id_ctx.get()
        user_id = user_id_ctx.get()
        await apply_tenant_context(session, org_id, user_id)
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def apply_tenant_context(
    session: AsyncSession, org_id: Optional[str], user_id: Optional[str]
) -> None:
    """Bind RLS settings to the current transaction after authentication."""
    if not session.bind or session.bind.dialect.name != "postgresql":
        return
    # Explicitly clear absent values, including when authentication loses a
    # membership or a session changes scope within the same transaction.
    await session.execute(
        text("SELECT set_config('app.current_organization_id', :value, true)"),
        {"value": org_id or ""},
    )
    await session.execute(
        text("SELECT set_config('app.current_user_id', :value, true)"),
        {"value": user_id or ""},
    )


async def init_db():
    """Schema changes are exclusively managed by Alembic; only verify connectivity."""
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def close_db():
    await engine.dispose()


def set_organization_context(org_id: Optional[str]) -> None:
    organization_id_ctx.set(org_id)


def set_user_context(user_id: Optional[str]) -> None:
    user_id_ctx.set(user_id)
