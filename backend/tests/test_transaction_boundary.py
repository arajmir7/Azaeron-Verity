"""A transaction-finalization failure must happen before HTTP success is sent."""

from fastapi import HTTPException
from fastapi.routing import APIRoute
from sqlalchemy import select

from app.core.database import get_db
from app.main import app
from app.modules.auth.models import User


def test_database_dependencies_finish_before_response_delivery():
    def check(dependency):
        if dependency.call is get_db:
            assert dependency.computed_scope == "function"
        for child in dependency.dependencies:
            check(child)

    for route in app.routes:
        if isinstance(route, APIRoute):
            check(route.dependant)


async def test_finalization_failure_returns_failure_and_rolls_back(client):
    original = app.dependency_overrides[get_db]

    async def unavailable_commit():
        async with app.state.test_session_factory() as session:
            yield session
            await session.rollback()
            raise HTTPException(503, "Fixture transaction commit unavailable")

    app.dependency_overrides[get_db] = unavailable_commit
    try:
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "commit-fixture@example.com",
                "password": "CommitFixture123!",
            },
        )
        assert response.status_code == 503
        async with app.state.test_session_factory() as session:
            assert (
                await session.scalar(
                    select(User.id).where(User.email == "commit-fixture@example.com")
                )
                is None
            )
    finally:
        app.dependency_overrides[get_db] = original
