"""Shared HTTP policy for synchronous and asynchronous clients."""

from __future__ import annotations

import asyncio
import email.utils
import math
import platform
import random
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

import httpx

from .errors import NetworkError, TimeoutError, api_error, SanitizedTransportError


def _url(base_url: str) -> str:
    parsed = urlsplit(base_url)
    if (
        parsed.scheme not in ("https", "http")
        or not parsed.netloc
        or parsed.username
        or parsed.password
    ):
        raise ValueError("base_url must be an HTTP(S) URL without credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("base_url cannot contain query or fragment")
    return base_url.rstrip("/")


def _delay(response: httpx.Response | None, attempt: int) -> float:
    if response is not None:
        value = response.headers.get("retry-after")
        if value:
            try:
                seconds = float(value)
                if math.isfinite(seconds):
                    return max(0.0, seconds)
            except ValueError:
                try:
                    date = email.utils.parsedate_to_datetime(value)
                    return max(0.0, (date - datetime.now(timezone.utc)).total_seconds())
                except (ValueError, TypeError):
                    pass
    return float(min(8.0, 0.5 * 2**attempt) * random.uniform(0.5, 1.0))


class Transport:
    """Internal synchronous transport. Injected HTTP clients remain caller-owned."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        *,
        http: httpx.Client | None = None,
        timeout: float = 30,
        max_retries: int = 2,
        user_agent: str = "sdk/0.0.0",  # x-release-please-version
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if (
            not api_key
            or not math.isfinite(timeout)
            or timeout <= 0
            or isinstance(max_retries, bool)
            or not isinstance(max_retries, int)
            or not 0 <= max_retries <= 20
        ):
            raise ValueError("api_key, timeout and max_retries must be valid")
        self._key = api_key
        self._base = _url(base_url)
        self._http = (
            http if http is not None else httpx.Client(trust_env=False, follow_redirects=False)
        )
        self._owned = http is None
        self._timeout = timeout
        self._retries = max_retries
        self._agent = f"{user_agent} python/{platform.python_version()}"
        self._sleep = sleep

    def request(
        self, method: str, path: str, *, safe: bool = False, **kwargs: Any
    ) -> httpx.Response:
        """Send once, retrying only explicitly safe operations."""
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("path must be relative to the configured API")
        deadline = kwargs.pop("_deadline", None)
        headers = httpx.Headers(kwargs.pop("headers", {}))
        headers["Accept"] = "application/json"
        headers["Authorization"] = f"Bearer {self._key}"
        headers["User-Agent"] = self._agent
        for attempt in range(self._retries + 1):
            remaining = (
                self._timeout
                if deadline is None
                else min(self._timeout, deadline - time.monotonic())
            )
            if remaining <= 0:
                raise TimeoutError("HTTP request timed out")
            response = None
            failure: NetworkError | None = None
            connect_failure = False
            try:
                response = self._http.request(
                    method,
                    self._base + path,
                    headers=headers,
                    timeout=remaining,
                    follow_redirects=False,
                    **kwargs,
                )
            except httpx.TimeoutException as error:
                connect_failure = isinstance(error, httpx.ConnectTimeout)
                failure = TimeoutError(
                    "HTTP request timed out", SanitizedTransportError(error, self._key)
                )
            except httpx.RequestError as error:
                connect_failure = isinstance(error, httpx.ConnectError)
                failure = NetworkError(
                    "HTTP network request failed", SanitizedTransportError(error, self._key)
                )
            if failure is not None:
                if (safe or connect_failure) and attempt < self._retries:
                    self._sleep(
                        min(_delay(None, attempt), max(0, deadline - time.monotonic()))
                        if deadline
                        else _delay(None, attempt)
                    )
                    continue
                raise failure
            assert response is not None
            if deadline is not None and time.monotonic() >= deadline:
                response.close()
                raise TimeoutError("HTTP request timed out")
            delay = _delay(response, attempt)
            if (
                (
                    response.status_code == 429
                    or (safe and response.status_code in (500, 502, 503, 504))
                )
                and attempt < self._retries
                and delay <= 60
            ):
                response.close()
                self._sleep(min(delay, max(0, deadline - time.monotonic())) if deadline else delay)
                continue
            if response.status_code >= 300:
                raise api_error(response, self._key)
            return response
        raise AssertionError("unreachable retry state")

    def close(self) -> None:
        """Close an internally created HTTP client."""
        if self._owned:
            self._http.close()

    def __enter__(self) -> Transport:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


class AsyncTransport:
    """Internal async transport with cancellation-safe retry sleeps."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        *,
        http: httpx.AsyncClient | None = None,
        timeout: float = 30,
        max_retries: int = 2,
        user_agent: str = "sdk/0.0.0",  # x-release-please-version
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if (
            not api_key
            or not math.isfinite(timeout)
            or timeout <= 0
            or isinstance(max_retries, bool)
            or not isinstance(max_retries, int)
            or not 0 <= max_retries <= 20
        ):
            raise ValueError("api_key, timeout and max_retries must be valid")
        self._key = api_key
        self._base = _url(base_url)
        self._http = (
            http if http is not None else httpx.AsyncClient(trust_env=False, follow_redirects=False)
        )
        self._owned = http is None
        self._timeout = timeout
        self._retries = max_retries
        self._agent = f"{user_agent} python/{platform.python_version()}"
        self._sleep = sleep

    async def request(
        self, method: str, path: str, *, safe: bool = False, **kwargs: Any
    ) -> httpx.Response:
        """Send once, retrying only explicitly safe operations."""
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("path must be relative to the configured API")
        deadline = kwargs.pop("_deadline", None)
        headers = httpx.Headers(kwargs.pop("headers", {}))
        headers["Accept"] = "application/json"
        headers["Authorization"] = f"Bearer {self._key}"
        headers["User-Agent"] = self._agent
        for attempt in range(self._retries + 1):
            remaining = (
                self._timeout
                if deadline is None
                else min(self._timeout, deadline - time.monotonic())
            )
            if remaining <= 0:
                raise TimeoutError("HTTP request timed out")
            response = None
            failure: NetworkError | None = None
            connect_failure = False
            try:
                response = await self._http.request(
                    method,
                    self._base + path,
                    headers=headers,
                    timeout=remaining,
                    follow_redirects=False,
                    **kwargs,
                )
            except httpx.TimeoutException as error:
                connect_failure = isinstance(error, httpx.ConnectTimeout)
                failure = TimeoutError(
                    "HTTP request timed out", SanitizedTransportError(error, self._key)
                )
            except httpx.RequestError as error:
                connect_failure = isinstance(error, httpx.ConnectError)
                failure = NetworkError(
                    "HTTP network request failed", SanitizedTransportError(error, self._key)
                )
            if failure is not None:
                if (safe or connect_failure) and attempt < self._retries:
                    await self._sleep(
                        min(_delay(None, attempt), max(0, deadline - time.monotonic()))
                        if deadline
                        else _delay(None, attempt)
                    )
                    continue
                raise failure
            assert response is not None
            delay = _delay(response, attempt)
            if (
                (
                    response.status_code == 429
                    or (safe and response.status_code in (500, 502, 503, 504))
                )
                and attempt < self._retries
                and delay <= 60
            ):
                await response.aclose()
                await self._sleep(
                    min(delay, max(0, deadline - time.monotonic())) if deadline else delay
                )
                continue
            if response.status_code >= 300:
                raise api_error(response, self._key)
            return response
        raise AssertionError("unreachable retry state")

    async def close(self) -> None:
        """Close an internally created HTTP client."""
        if self._owned:
            await self._http.aclose()

    async def __aenter__(self) -> AsyncTransport:
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.close()
