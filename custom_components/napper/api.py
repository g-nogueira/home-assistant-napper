"""Async client for the private Napper API."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from json import JSONDecodeError
from typing import Any
from urllib.parse import quote

from aiohttp import ClientError, ClientResponse, ClientSession

from .const import (
    API_BASE_URL,
    API_CLIENT_VERSION,
    API_LANGUAGE,
    API_LOCALE,
    API_SOURCE,
    API_TIMEOUT_SECONDS,
    TOKEN_REFRESH_MARGIN,
)
from .models import NapperBaby, NapperLog, NapperTokens

TokenUpdateCallback = Callable[[NapperTokens], Awaitable[None] | None]


class NapperApiError(Exception):
    """Base exception for Napper API failures."""


class NapperConnectionError(NapperApiError):
    """Raised when Napper cannot be reached or returns an invalid response."""


class NapperAuthenticationError(NapperApiError):
    """Raised when authentication has expired or was rejected."""


class NapperInvalidOtpError(NapperAuthenticationError):
    """Raised when Napper rejects a one-time password."""


class NapperRateLimitError(NapperApiError):
    """Raised when Napper rate-limits the client."""


class NapperApiClient:
    """Small async client covering only the read-only integration contract."""

    def __init__(
        self,
        session: ClientSession,
        device_id: str,
        *,
        tokens: NapperTokens | None = None,
        on_tokens_updated: TokenUpdateCallback | None = None,
    ) -> None:
        self._session = session
        self._device_id = device_id
        self._tokens = tokens
        self._on_tokens_updated = on_tokens_updated
        self._refresh_lock = asyncio.Lock()

    @property
    def tokens(self) -> NapperTokens | None:
        """Return the current token pair."""
        return self._tokens

    async def async_send_otp(self, email: str) -> None:
        """Ask Napper to send an email one-time password."""
        await self._async_request(
            "POST",
            "/auth/send-otp",
            auth=False,
            allow_refresh=False,
            expect_json=False,
            json={
                "email": email,
                "useDeviceId": False,
                "source": API_SOURCE,
                "language": API_LANGUAGE,
            },
        )

    async def async_email_login(self, email: str, otp: str) -> NapperTokens:
        """Exchange an email OTP for an ID and refresh token."""
        try:
            response = await self._async_request(
                "POST",
                "/auth/email-login",
                auth=False,
                allow_refresh=False,
                authentication_request=True,
                json={"email": email, "otp": otp, "useDeviceId": False},
            )
        except NapperAuthenticationError as err:
            raise NapperInvalidOtpError(
                "Napper rejected the one-time password"
            ) from err

        tokens = self._parse_tokens(response)
        await self._async_set_tokens(tokens)
        return tokens

    async def async_refresh_tokens(self, *, force: bool = True) -> NapperTokens:
        """Refresh the current ID token and persist both returned tokens."""
        async with self._refresh_lock:
            if self._tokens is None:
                raise NapperAuthenticationError("No Napper refresh token is available")

            # Concurrent baby polls may all notice the same expiring token before
            # the first refresh completes. Only the first caller should rotate it.
            if not force and not self._tokens_need_refresh():
                return self._tokens

            current = self._tokens
            response = await self._async_request(
                "POST",
                "/auth/refresh-token",
                auth=True,
                allow_refresh=False,
                json={
                    "idToken": current.id_token,
                    "refreshToken": current.refresh_token,
                },
            )
            tokens = self._parse_tokens(response)
            await self._async_set_tokens(tokens)
            return tokens

    async def async_get_babies(self) -> tuple[NapperBaby, ...]:
        """Return babies available to the authenticated account."""
        response = await self._async_request("GET", "/babies")
        items = response.get("items")
        if not isinstance(items, list):
            raise NapperConnectionError("Napper returned an invalid babies response")

        try:
            return tuple(
                NapperBaby.from_dict(item)
                for item in items
                if isinstance(item, dict) and item.get("type") == "BABY"
            )
        except (KeyError, TypeError, ValueError) as err:
            raise NapperConnectionError(
                "Napper returned an invalid baby object"
            ) from err

    async def async_get_today(
        self, baby_id: str, at: datetime | None = None
    ) -> tuple[NapperLog, ...]:
        """Return current-day logs for one baby."""
        current_time = at or datetime.now().astimezone()
        timestamp = quote(current_time.isoformat(timespec="milliseconds"), safe="")
        baby_path = quote(baby_id, safe="")
        response = await self._async_request("GET", f"/today/{baby_path}/{timestamp}")
        item = response.get("item")
        logs = item.get("logs") if isinstance(item, dict) else None
        if not isinstance(logs, list):
            raise NapperConnectionError("Napper returned an invalid today response")

        return tuple(NapperLog.from_dict(log) for log in logs if isinstance(log, dict))

    async def _async_request(
        self,
        method: str,
        path: str,
        *,
        auth: bool = True,
        allow_refresh: bool = True,
        authentication_request: bool = False,
        expect_json: bool = True,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if auth and self._tokens is None:
            raise NapperAuthenticationError("Napper authentication is required")

        if auth and allow_refresh and self._tokens_need_refresh():
            await self.async_refresh_tokens(force=False)

        headers = self._headers(auth=auth)
        try:
            async with asyncio.timeout(API_TIMEOUT_SECONDS):
                async with self._session.request(
                    method,
                    f"{API_BASE_URL}{path}",
                    headers=headers,
                    **kwargs,
                ) as response:
                    if response.status in {401, 403} or (
                        authentication_request and response.status == 400
                    ):
                        if auth and allow_refresh and self._tokens is not None:
                            await response.read()
                            await self.async_refresh_tokens()
                            return await self._async_request(
                                method,
                                path,
                                auth=auth,
                                allow_refresh=False,
                                authentication_request=authentication_request,
                                expect_json=expect_json,
                                **kwargs,
                            )
                        raise NapperAuthenticationError(
                            f"Napper rejected authentication ({response.status})"
                        )
                    if response.status == 429:
                        raise NapperRateLimitError("Napper rate limit reached")
                    if response.status >= 400:
                        raise NapperApiError(
                            f"Napper request failed ({response.status})"
                        )
                    if not expect_json:
                        await response.read()
                        return {}
                    return await self._async_json(response)
        except TimeoutError as err:
            raise NapperConnectionError("Timed out while contacting Napper") from err
        except ClientError as err:
            raise NapperConnectionError("Could not connect to Napper") from err

    def _headers(self, *, auth: bool) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Source": API_SOURCE,
            "Version": API_CLIENT_VERSION,
            "Device": self._device_id,
            "Language": API_LANGUAGE,
            "Locale": API_LOCALE,
            "Local-Timestamp": datetime.now()
            .astimezone()
            .isoformat(timespec="milliseconds"),
        }
        if auth and self._tokens is not None:
            headers["Authorization"] = f"Bearer {self._tokens.id_token}"
        return headers

    def _tokens_need_refresh(self) -> bool:
        if self._tokens is None or self._tokens.id_token_expires_at is None:
            return False
        expires_at = datetime.fromtimestamp(self._tokens.id_token_expires_at, tz=UTC)
        return expires_at - datetime.now(tz=UTC) <= TOKEN_REFRESH_MARGIN

    async def _async_set_tokens(self, tokens: NapperTokens) -> None:
        self._tokens = tokens
        if self._on_tokens_updated is not None:
            result = self._on_tokens_updated(tokens)
            if result is not None:
                await result

    @staticmethod
    async def _async_json(response: ClientResponse) -> dict[str, Any]:
        try:
            data = await response.json(content_type=None)
        except (JSONDecodeError, ValueError) as err:
            raise NapperConnectionError("Napper returned invalid JSON") from err
        if not isinstance(data, dict):
            raise NapperConnectionError("Napper returned an invalid JSON object")
        return data

    @staticmethod
    def _parse_tokens(response: dict[str, Any]) -> NapperTokens:
        try:
            item = response["item"]
            id_token = item["idToken"]
            refresh_token = item["refreshToken"]
            id_payload = id_token["payload"]
            refresh_payload = refresh_token.get("payload", {})
            return NapperTokens(
                account_id=str(id_payload["sub"]),
                id_token=str(id_token["token"]),
                refresh_token=str(refresh_token["token"]),
                id_token_expires_at=_optional_int(id_payload.get("exp")),
                refresh_token_expires_at=_optional_int(refresh_payload.get("exp")),
            )
        except (KeyError, TypeError, ValueError) as err:
            raise NapperConnectionError(
                "Napper returned an invalid authentication response"
            ) from err


def _optional_int(value: Any) -> int | None:
    """Return an integer when the token payload contains one."""
    if value is None:
        return None
    return int(value)
