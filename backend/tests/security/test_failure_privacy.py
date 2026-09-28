import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.core.config import settings
from app.core.dependencies import RateLimiter
from app.main import global_exception_handler


async def test_production_limiter_does_not_fall_back_when_redis_is_unavailable(
    monkeypatch,
):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "REDIS_URL", "redis://127.0.0.1:63999/15")
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/documents",
            "headers": [],
            "client": ("127.0.0.1", 80),
        }
    )
    with pytest.raises(HTTPException) as error:
        await RateLimiter()(request)
    assert error.value.status_code == 503


async def test_error_response_and_logs_exclude_exception_contents(capsys):
    marker = "PRIVATE-CUSTOMER-DOCUMENT-CONTENT"
    request = Request(
        {"type": "http", "method": "POST", "path": "/api/v1/documents", "headers": []}
    )
    response = await global_exception_handler(request, ValueError(marker))
    assert response.status_code == 500
    assert marker not in response.body.decode()
    assert marker not in capsys.readouterr().out
