"""Isolated API test database; production schema creation remains Alembic-only."""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.core.database import Base, get_db
from app.core.config import settings
from app.core.dependencies import auth_rate_limiter, rate_limiter
from app.main import app


@pytest_asyncio.fixture
async def client(tmp_path):
    # The fallback limiter is intentionally process-local when Redis is not
    # available in unit tests. Isolate test clients without weakening the
    # production limit.
    auth_rate_limiter._fallback.clear()
    rate_limiter._fallback.clear()
    redis_url = settings.REDIS_URL
    settings.REDIS_URL = "redis://127.0.0.1:63999/15"
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    app.state.test_session_factory = session_factory
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as test_client:
            yield test_client
    finally:
        auth_rate_limiter._fallback.clear()
        rate_limiter._fallback.clear()
        settings.REDIS_URL = redis_url
        app.dependency_overrides.clear()
        delattr(app.state, "test_session_factory")
        await engine.dispose()


@pytest_asyncio.fixture
async def db_session(client):
    async with app.state.test_session_factory() as session:
        yield session
        await session.commit()
