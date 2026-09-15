"""Tests for the private Napper API client contract."""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from custom_components.napper.api import NapperApiClient, NapperInvalidOtpError
from custom_components.napper.models import NapperTokens


class FakeResponse:
    """Minimal aiohttp response context manager."""

    def __init__(self, status: int, payload: dict[str, Any]) -> None:
        self.status = status
        self.payload = payload

    async def __aenter__(self) -> FakeResponse:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def json(self, *, content_type: None = None) -> dict[str, Any]:
        return self.payload

    async def read(self) -> bytes:
        return b""


class FakeSession:
    """Queue responses and record requests."""

    def __init__(self, *responses: FakeResponse) -> None:
        self.responses = deque(responses)
        self.requests: list[tuple[str, str, dict[str, Any]]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.requests.append((method, url, kwargs))
        return self.responses.popleft()


def auth_response(
    *, id_token: str = "new-id-token", refresh_token: str = "new-refresh-token"
) -> dict[str, Any]:
    """Return a sanitized authentication response."""
    return {
        "item": {
            "idToken": {
                "token": id_token,
                "payload": {"sub": "account-1", "exp": 2_000_000_000},
            },
            "refreshToken": {
                "token": refresh_token,
                "payload": {"exp": 2_030_000_000},
            },
        }
    }


@pytest.mark.asyncio
async def test_email_login_uses_expected_contract() -> None:
    session = FakeSession(FakeResponse(200, auth_response()))
    client = NapperApiClient(session, "device-1")

    tokens = await client.async_email_login("parent@example.test", "123456")

    method, url, request = session.requests[0]
    assert method == "POST"
    assert url.endswith("/auth/email-login")
    assert request["json"] == {
        "email": "parent@example.test",
        "otp": "123456",
        "useDeviceId": False,
    }
    assert "Authorization" not in request["headers"]
    assert tokens.account_id == "account-1"
    assert tokens.id_token == "new-id-token"


@pytest.mark.asyncio
async def test_invalid_otp_is_reported_separately() -> None:
    session = FakeSession(FakeResponse(400, {}))
    client = NapperApiClient(session, "device-1")

    with pytest.raises(NapperInvalidOtpError):
        await client.async_email_login("parent@example.test", "wrong")


@pytest.mark.asyncio
async def test_get_babies_filters_non_baby_profiles() -> None:
    session = FakeSession(
        FakeResponse(
            200,
            {
                "items": [
                    {
                        "id": "baby-1",
                        "name": "Test Baby",
                        "isOwner": True,
                        "type": "BABY",
                    },
                    {"id": "adult-1", "name": "Parent", "type": "ADULT"},
                ]
            },
        )
    )
    client = NapperApiClient(session, "device-1", tokens=current_tokens())

    babies = await client.async_get_babies()

    assert [baby.id for baby in babies] == ["baby-1"]
    assert session.requests[0][2]["headers"]["Authorization"] == "Bearer id-token"


@pytest.mark.asyncio
async def test_get_today_encodes_path_and_parses_logs() -> None:
    session = FakeSession(
        FakeResponse(
            200,
            {
                "item": {
                    "logs": [
                        {
                            "id": "nap-1",
                            "category": "NAP",
                            "isOpen": True,
                            "start": "2026-09-15T13:00:00Z",
                            "pauses": [],
                        }
                    ],
                    "scheduleItems": [],
                }
            },
        )
    )
    client = NapperApiClient(session, "device-1", tokens=current_tokens())

    logs = await client.async_get_today(
        "baby/1", datetime(2026, 9, 15, 14, 30, tzinfo=UTC)
    )

    assert logs[0].category == "NAP"
    assert logs[0].is_open is True
    assert (
        "/today/baby%2F1/2026-09-15T14%3A30%3A00.000%2B00%3A00"
        in (session.requests[0][1])
    )


@pytest.mark.asyncio
async def test_expiring_token_is_refreshed_before_get() -> None:
    session = FakeSession(
        FakeResponse(200, auth_response()),
        FakeResponse(200, {"items": []}),
    )
    updated: list[NapperTokens] = []
    expiring = NapperTokens(
        account_id="account-1",
        id_token="old-id-token",
        refresh_token="old-refresh-token",
        id_token_expires_at=int((datetime.now(tz=UTC) + timedelta(days=1)).timestamp()),
    )
    client = NapperApiClient(
        session,
        "device-1",
        tokens=expiring,
        on_tokens_updated=updated.append,
    )

    await client.async_get_babies()

    assert session.requests[0][1].endswith("/auth/refresh-token")
    assert session.requests[0][2]["json"] == {
        "idToken": "old-id-token",
        "refreshToken": "old-refresh-token",
    }
    assert session.requests[1][2]["headers"]["Authorization"] == ("Bearer new-id-token")
    assert updated[0].refresh_token == "new-refresh-token"


def current_tokens() -> NapperTokens:
    """Return a token pair that does not need proactive refresh."""
    return NapperTokens(
        account_id="account-1",
        id_token="id-token",
        refresh_token="refresh-token",
        id_token_expires_at=2_000_000_000,
        refresh_token_expires_at=2_030_000_000,
    )
