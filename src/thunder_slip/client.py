"""Resource clients with matching synchronous and asynchronous APIs."""

from __future__ import annotations
import asyncio
import os
import time
import queue
import threading
from dataclasses import replace
from pathlib import Path
from collections.abc import Iterator, AsyncIterator
from typing import Any, BinaryIO, TypeVar, cast
import httpx
from . import models as m
from ._codec import decode, encode, UNSET
from ._transport import Transport, AsyncTransport
from .files import image_input
from .errors import (
    InputError,
    BatchSubmitError,
    JobWaitTimeoutError,
    RequestTimeoutError,
    rate_limit,
    redact,
    redact_header,
)

T = TypeVar("T", bound=m.Model)
FileInput = str | Path | bytes | BinaryIO


def _settings(api_key: str | None, v2: str | None, v1: str | None) -> tuple[str, str, str, str]:
    key = api_key or os.environ.get("THUNDER_API_KEY")
    if not key:
        file = os.environ.get("THUNDER_API_KEY_FILE")
        if file:
            try:
                key = Path(file).read_text().strip()
            except OSError:
                raise InputError("INVALID_ARGUMENT", "Cannot read API key file") from None
    if not key:
        raise InputError("INVALID_ARGUMENT", "API key is required")
    return (
        key,
        v2 or os.environ.get("THUNDER_V2_BASE_URL") or "https://api.thunder.in.th/v2",
        v1 or os.environ.get("THUNDER_V1_BASE_URL") or "https://api.thunder.in.th/v1",
        "thunder-slip-python/1.0.0",  # x-release-please-version
    )


def _text(value: str, maximum: int) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= maximum:
        raise InputError("INVALID_ARGUMENT", "String argument has invalid length")
    return value


def _id(value: int) -> str:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise InputError("INVALID_ARGUMENT", "Account id must be positive")
    return str(value)


def _form(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return format(value, ".15g")
    return str(value)


def _decode_response(model: type[T], response: httpx.Response, secret: str) -> T:
    body = response.json()
    data = body["data"]
    result = (
        cast(T, m.BankList(items=[decode(m.Bank, x) for x in data]))
        if model is m.BankList
        else decode(model, data)
    )
    headers = {k: redact_header(k, v, secret) for k, v in response.headers.items()}
    result.meta = m.ResponseMeta(
        status=response.status_code,
        request_id=headers.get("x-request-id") or headers.get("cf-ray"),
        message=redact(body["message"], secret) if isinstance(body.get("message"), str) else None,
        rate_limit=rate_limit(headers),
        headers=headers,
    )
    return result


class Resource:
    """Internal resource base; transports remain owned by the parent client."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def _call(
        self, model: type[T], method: str, path: str, *, safe: bool = False, **kwargs: Any
    ) -> T:
        response = self._transport.request(method, path, safe=safe, **kwargs)
        return _decode_response(model, response, self._transport._key)


class Verify(Resource):
    """Billed bank and wallet verification operations."""

    def _verify(
        self,
        field: str,
        value: str | FileInput,
        options: m.VerifyOptions | None,
        wallet: bool = False,
    ) -> m.BankSlipResult | m.TrueWalletResult:
        body = encode(options) if options else {}
        path = "/verify/truewallet" if wallet else "/verify/bank"
        model: type[m.TrueWalletResult] | type[m.BankSlipResult] = (
            m.TrueWalletResult if wallet else m.BankSlipResult
        )
        if field == "image":
            image = image_input(value, max_bytes=4194304)
            return self._call(
                model,
                "POST",
                path,
                data={k: _form(v) for k, v in body.items()},
                files={"image": (image.filename, image.data, image.content_type)},
            )
        body[field] = value
        return self._call(model, "POST", path, json=body)

    def bank_by_payload(
        self, payload: str, options: m.VerifyOptions | None = None
    ) -> m.BankSlipResult:
        """Verify one bank slip using payload; may spend quota."""
        _text(payload, 128)
        return cast(m.BankSlipResult, self._verify("payload", payload, options, False))

    def bank_by_image(
        self, file: FileInput, options: m.VerifyOptions | None = None
    ) -> m.BankSlipResult:
        """Verify one bank slip using image; may spend quota."""
        return cast(m.BankSlipResult, self._verify("image", file, options, False))

    def bank_by_base64(
        self, base64: str, options: m.VerifyOptions | None = None
    ) -> m.BankSlipResult:
        """Verify one bank slip using base64; may spend quota."""
        return cast(m.BankSlipResult, self._verify("base64", base64, options, False))

    def bank_by_url(self, url: str, options: m.VerifyOptions | None = None) -> m.BankSlipResult:
        """Verify one bank slip using url; may spend quota."""
        _text(url, 2048)
        return cast(m.BankSlipResult, self._verify("url", url, options, False))

    def truewallet_by_image(
        self, file: FileInput, options: m.VerifyOptions | None = None
    ) -> m.TrueWalletResult:
        """Verify one wallet slip using image; may spend quota."""
        return cast(m.TrueWalletResult, self._verify("image", file, options, True))

    def truewallet_by_base64(
        self, base64: str, options: m.VerifyOptions | None = None
    ) -> m.TrueWalletResult:
        """Verify one wallet slip using base64; may spend quota."""
        return cast(m.TrueWalletResult, self._verify("base64", base64, options, True))

    def truewallet_by_url(
        self, url: str, options: m.VerifyOptions | None = None
    ) -> m.TrueWalletResult:
        """Verify one wallet slip using url; may spend quota."""
        _text(url, 255)
        return cast(m.TrueWalletResult, self._verify("url", url, options, True))


class Banks(Resource):
    """Bank catalog."""

    def list(self) -> m.BankList:
        """Return supported banks and their verification choices."""
        return self._call(m.BankList, "GET", "/banks", safe=True)


class BankAccounts(Resource):
    """Receiving account management and lazy pagination."""

    def _list(
        self, params: m.ListBankAccountsParams | None, all_accounts: bool
    ) -> m.BankAccountPage:
        query = encode(params) if params else {}
        if "page" in query and (type(query["page"]) is not int or query["page"] < 1):
            raise InputError("INVALID_ARGUMENT", "page must be positive")
        if "limit" in query and (type(query["limit"]) is not int or not 1 <= query["limit"] <= 100):
            raise InputError("INVALID_ARGUMENT", "limit must be between 1 and 100")
        return self._call(
            m.BankAccountPage,
            "GET",
            "/bank-accounts" + ("/all" if all_accounts else ""),
            safe=True,
            params={k: _form(v) for k, v in query.items()},
        )

    def list(self, params: m.ListBankAccountsParams | None = None) -> m.BankAccountPage:
        """Return one page linked to this branch."""
        return self._list(params, False)

    def list_all(self, params: m.ListBankAccountsParams | None = None) -> m.BankAccountPage:
        """Return one page across the service."""
        return self._list(params, True)

    def get(self, id: int) -> m.BankAccount:
        """Read one receiving account."""
        return self._call(m.BankAccount, "GET", "/bank-accounts/" + _id(id), safe=True)

    def create(self, params: m.CreateBankAccountParams) -> m.BankAccount:
        """Create an account; ambiguous failures are never retried."""
        return self._call(m.BankAccount, "POST", "/bank-accounts", json=encode(params))

    def update(self, id: int, params: m.UpdateBankAccountParams) -> m.BankAccount:
        """Update selected fields; explicit extra_verify=None clears that field."""
        return self._call(m.BankAccount, "PATCH", "/bank-accounts/" + _id(id), json=encode(params))

    def link(self, id: int) -> m.LinkResult:
        """Idempotently link an account to this branch."""
        return self._call(m.LinkResult, "POST", "/bank-accounts/" + _id(id) + "/link", safe=True)

    def unlink(self, id: int) -> m.UnlinkResult:
        """Unlink an account from this branch."""
        return self._call(m.UnlinkResult, "DELETE", "/bank-accounts/" + _id(id) + "/link")

    def _iterate(
        self, params: m.ListBankAccountsParams | None, all_accounts: bool
    ) -> Iterator[m.BankAccount]:
        params = params or m.ListBankAccountsParams()
        page = params.page if params.page is not UNSET else 1
        limit = params.limit if params.limit is not UNSET else 100
        while True:
            response = self._list(replace(params, page=page, limit=limit), all_accounts)
            for item in response.items:
                yield item
            if not response.items or page * limit >= response.total:
                break
            page += 1

    def iterate(self, params: m.ListBankAccountsParams | None = None) -> Iterator[m.BankAccount]:
        """Lazily walk every linked account, starting at params.page."""
        for item in self._iterate(params, False):
            yield item

    def iterate_all(
        self, params: m.ListBankAccountsParams | None = None
    ) -> Iterator[m.BankAccount]:
        """Lazily walk service accounts, requesting at most one page at a time."""
        for item in self._iterate(params, True):
            yield item


class Jobs(Resource):
    """Async verification, polling and independent batch submission."""

    def submit_bank(
        self, payload: str, options: m.AsyncVerifyOptions | None = None
    ) -> m.JobSubmission:
        """Enqueue one bank slip; successful verification spends quota."""
        body = encode(options) if options else {}
        body["payload"] = _text(payload, 128)
        return self._call(m.JobSubmission, "POST", "/verify/bank/async", json=body)

    def submit_bank_batch(
        self, slips: list[m.BatchSlip], options: m.BatchOptions | None = None
    ) -> m.BatchSubmission:
        """Enqueue 1-100 slips; each successful slip spends quota separately."""
        if not slips:
            raise InputError("EMPTY_BATCH", "At least one slip is required")
        if len(slips) > 100:
            raise InputError("BATCH_TOO_LARGE", "At most 100 slips per batch")
        body = encode(options) if options else {}
        body["slips"] = encode(slips)
        return self._call(m.BatchSubmission, "POST", "/verify/bank/batch", json=body)

    def submit_bank_many(
        self, slips: list[m.BatchSlip], options: m.BatchOptions | None = None
    ) -> list[m.BatchSubmission]:
        """Submit chunks of 100 in order, retaining receipts on partial failure."""
        if not slips:
            raise InputError("EMPTY_BATCH", "At least one slip is required")
        submitted: list[m.BatchSubmission] = []
        for index in range(0, len(slips), 100):
            try:
                submitted.append(self.submit_bank_batch(slips[index : index + 100], options))
            except Exception as cause:
                raise BatchSubmitError(submitted, index // 100, cause) from None
        return submitted

    def get(self, job_id: str) -> m.Job:
        """Read one job, including failed jobs without raising an API error."""
        from urllib.parse import quote

        return self._call(
            m.Job, "GET", "/verify/bank/jobs/" + quote(_text(job_id, 255), safe=""), safe=True
        )

    def wait_for_job(self, job_id: str, *, interval: float = 2, timeout: float = 600) -> m.Job:
        """Poll until done or failed, bounded by an overall timeout."""
        import math

        if (
            not math.isfinite(interval)
            or interval < 0.5
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise InputError("INVALID_ARGUMENT", "Invalid polling interval or timeout")
        deadline = time.monotonic() + timeout
        last: m.Job | None = None
        while time.monotonic() < deadline:
            # HTTPX phase timeouts alone do not bound a slow trickle or a custom
            # transport. One worker bounds the caller's total wall-clock budget.
            # No more polling/retries are started after the deadline.
            replies: queue.Queue[httpx.Response | Exception] = queue.Queue(maxsize=1)

            def fetch(replies: queue.Queue[httpx.Response | Exception] = replies) -> None:
                try:
                    replies.put(
                        self._transport.request(
                            "GET",
                            "/verify/bank/jobs/"
                            + __import__("urllib.parse", fromlist=["quote"]).quote(
                                _text(job_id, 255), safe=""
                            ),
                            safe=True,
                            _deadline=deadline,
                        )
                    )
                except Exception as error:
                    replies.put(error)

            worker = threading.Thread(target=fetch, name="sdk-job-poll", daemon=True)
            worker.start()
            try:
                response = replies.get(timeout=max(0, deadline - time.monotonic()))
            except queue.Empty:
                raise JobWaitTimeoutError(last) from None
            if time.monotonic() >= deadline or isinstance(response, RequestTimeoutError):
                raise JobWaitTimeoutError(last) from None
            if isinstance(response, Exception):
                raise response
            job = _decode_response(m.Job, response, self._transport._key)
            if time.monotonic() >= deadline:
                raise JobWaitTimeoutError(last)
            last = job
            if last.status in ("done", "failed"):
                return last
            time.sleep(min(interval, max(0, deadline - time.monotonic())))
        raise JobWaitTimeoutError(last)


class V1(Resource):
    """Legacy API operations using the independent v1 base URL."""

    def get_me(self) -> m.V1Me:
        """Read application quota and credit."""
        return self._call(m.V1Me, "GET", "/me", safe=True)

    def verify_bank_by_payload(
        self, payload: str, options: m.V1VerifyOptions | None = None
    ) -> m.BankSlip:
        """Verify a payload through the billed legacy GET endpoint."""
        query = encode(options) if options else {}
        query["payload"] = _text(payload, 255)
        return self._call(
            m.BankSlip, "GET", "/verify", params={k: _form(v) for k, v in query.items()}
        )

    def _verify(
        self,
        field: str,
        value: str | FileInput,
        options: m.V1VerifyOptions | None,
        wallet: bool = False,
    ) -> m.BankSlip | m.TrueWalletSlip:
        body = encode(options) if options else {}
        model: type[m.TrueWalletSlip] | type[m.BankSlip] = (
            m.TrueWalletSlip if wallet else m.BankSlip
        )
        path = "/verify/truewallet" if wallet else "/verify"
        if field == "file":
            image = image_input(value, max_bytes=4194304)
            return self._call(
                model,
                "POST",
                path,
                data={k: _form(v) for k, v in body.items()},
                files={"file": (image.filename, image.data, image.content_type)},
            )
        body[field] = value
        return self._call(model, "POST", path, json=body)

    def verify_bank_by_image(
        self, file: FileInput, options: m.V1VerifyOptions | None = None
    ) -> m.BankSlip:
        """Upload an image to v1 using multipart field file."""
        return cast(m.BankSlip, self._verify("file", file, options))

    def verify_bank_by_base64(
        self, base64: str, options: m.V1VerifyOptions | None = None
    ) -> m.BankSlip:
        """Send base64 using the legacy JSON field image."""
        return cast(m.BankSlip, self._verify("image", base64, options))

    def verify_bank_by_url(self, url: str, options: m.V1VerifyOptions | None = None) -> m.BankSlip:
        """Verify a remote image through v1."""
        return cast(m.BankSlip, self._verify("url", _text(url, 2048), options))

    def verify_truemoney_by_image(
        self, file: FileInput, options: m.V1VerifyOptions | None = None
    ) -> m.TrueWalletSlip:
        """Upload a wallet image to the legacy endpoint."""
        return cast(m.TrueWalletSlip, self._verify("file", file, options, True))

    def generate_qr(self, request: m.QrRequest) -> m.QrCode:
        """Generate a QR code without verification quota consumption."""
        return self._call(m.QrCode, "POST", "/qr/generate", safe=True, json=encode(request))


class Client:
    """Credential-safe API client; use a context manager to close owned connections."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        v2_base_url: str | None = None,
        v1_base_url: str | None = None,
        timeout: float = 30,
        max_retries: int = 2,
        http: httpx.Client | None = None,
    ) -> None:
        key, v2, v1, agent = _settings(api_key, v2_base_url, v1_base_url)
        try:
            self._v2 = Transport(
                key, v2, http=http, timeout=timeout, max_retries=max_retries, user_agent=agent
            )
            self._v1 = Transport(
                key, v1, http=http, timeout=timeout, max_retries=max_retries, user_agent=agent
            )
        except ValueError:
            raise InputError("INVALID_ARGUMENT", "Invalid client configuration") from None
        self.verify = Verify(self._v2)
        self.banks = Banks(self._v2)
        self.bank_accounts = BankAccounts(self._v2)
        self.jobs = Jobs(self._v2)
        self.v1 = V1(self._v1)

    def get_info(self) -> m.Info:
        """Read application, branch, quota and credit information."""
        response = self._v2.request("GET", "/info", safe=True)
        return _decode_response(m.Info, response, self._v2._key)

    def close(self) -> None:
        """Close connections created by this client; injected HTTP clients remain open."""
        self._v2.close()
        self._v1.close()

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


class AsyncResource:
    """Internal resource base; transports remain owned by the parent client."""

    def __init__(self, transport: AsyncTransport) -> None:
        self._transport = transport

    async def _call(
        self, model: type[T], method: str, path: str, *, safe: bool = False, **kwargs: Any
    ) -> T:
        response = await self._transport.request(method, path, safe=safe, **kwargs)
        return _decode_response(model, response, self._transport._key)


class AsyncVerify(AsyncResource):
    """Billed bank and wallet verification operations."""

    async def _verify(
        self,
        field: str,
        value: str | FileInput,
        options: m.VerifyOptions | None,
        wallet: bool = False,
    ) -> m.BankSlipResult | m.TrueWalletResult:
        body = encode(options) if options else {}
        path = "/verify/truewallet" if wallet else "/verify/bank"
        model: type[m.TrueWalletResult] | type[m.BankSlipResult] = (
            m.TrueWalletResult if wallet else m.BankSlipResult
        )
        if field == "image":
            image = image_input(value, max_bytes=4194304)
            return await self._call(
                model,
                "POST",
                path,
                data={k: _form(v) for k, v in body.items()},
                files={"image": (image.filename, image.data, image.content_type)},
            )
        body[field] = value
        return await self._call(model, "POST", path, json=body)

    async def bank_by_payload(
        self, payload: str, options: m.VerifyOptions | None = None
    ) -> m.BankSlipResult:
        """Verify one bank slip using payload; may spend quota."""
        _text(payload, 128)
        return cast(m.BankSlipResult, await self._verify("payload", payload, options, False))

    async def bank_by_image(
        self, file: FileInput, options: m.VerifyOptions | None = None
    ) -> m.BankSlipResult:
        """Verify one bank slip using image; may spend quota."""
        return cast(m.BankSlipResult, await self._verify("image", file, options, False))

    async def bank_by_base64(
        self, base64: str, options: m.VerifyOptions | None = None
    ) -> m.BankSlipResult:
        """Verify one bank slip using base64; may spend quota."""
        return cast(m.BankSlipResult, await self._verify("base64", base64, options, False))

    async def bank_by_url(
        self, url: str, options: m.VerifyOptions | None = None
    ) -> m.BankSlipResult:
        """Verify one bank slip using url; may spend quota."""
        _text(url, 2048)
        return cast(m.BankSlipResult, await self._verify("url", url, options, False))

    async def truewallet_by_image(
        self, file: FileInput, options: m.VerifyOptions | None = None
    ) -> m.TrueWalletResult:
        """Verify one wallet slip using image; may spend quota."""
        return cast(m.TrueWalletResult, await self._verify("image", file, options, True))

    async def truewallet_by_base64(
        self, base64: str, options: m.VerifyOptions | None = None
    ) -> m.TrueWalletResult:
        """Verify one wallet slip using base64; may spend quota."""
        return cast(m.TrueWalletResult, await self._verify("base64", base64, options, True))

    async def truewallet_by_url(
        self, url: str, options: m.VerifyOptions | None = None
    ) -> m.TrueWalletResult:
        """Verify one wallet slip using url; may spend quota."""
        _text(url, 255)
        return cast(m.TrueWalletResult, await self._verify("url", url, options, True))


class AsyncBanks(AsyncResource):
    """Bank catalog."""

    async def list(self) -> m.BankList:
        """Return supported banks and their verification choices."""
        return await self._call(m.BankList, "GET", "/banks", safe=True)


class AsyncBankAccounts(AsyncResource):
    """Receiving account management and lazy pagination."""

    async def _list(
        self, params: m.ListBankAccountsParams | None, all_accounts: bool
    ) -> m.BankAccountPage:
        query = encode(params) if params else {}
        if "page" in query and (type(query["page"]) is not int or query["page"] < 1):
            raise InputError("INVALID_ARGUMENT", "page must be positive")
        if "limit" in query and (type(query["limit"]) is not int or not 1 <= query["limit"] <= 100):
            raise InputError("INVALID_ARGUMENT", "limit must be between 1 and 100")
        return await self._call(
            m.BankAccountPage,
            "GET",
            "/bank-accounts" + ("/all" if all_accounts else ""),
            safe=True,
            params={k: _form(v) for k, v in query.items()},
        )

    async def list(self, params: m.ListBankAccountsParams | None = None) -> m.BankAccountPage:
        """Return one page linked to this branch."""
        return await self._list(params, False)

    async def list_all(self, params: m.ListBankAccountsParams | None = None) -> m.BankAccountPage:
        """Return one page across the service."""
        return await self._list(params, True)

    async def get(self, id: int) -> m.BankAccount:
        """Read one receiving account."""
        return await self._call(m.BankAccount, "GET", "/bank-accounts/" + _id(id), safe=True)

    async def create(self, params: m.CreateBankAccountParams) -> m.BankAccount:
        """Create an account; ambiguous failures are never retried."""
        return await self._call(m.BankAccount, "POST", "/bank-accounts", json=encode(params))

    async def update(self, id: int, params: m.UpdateBankAccountParams) -> m.BankAccount:
        """Update selected fields; explicit extra_verify=None clears that field."""
        return await self._call(
            m.BankAccount, "PATCH", "/bank-accounts/" + _id(id), json=encode(params)
        )

    async def link(self, id: int) -> m.LinkResult:
        """Idempotently link an account to this branch."""
        return await self._call(
            m.LinkResult, "POST", "/bank-accounts/" + _id(id) + "/link", safe=True
        )

    async def unlink(self, id: int) -> m.UnlinkResult:
        """Unlink an account from this branch."""
        return await self._call(m.UnlinkResult, "DELETE", "/bank-accounts/" + _id(id) + "/link")

    async def _iterate(
        self, params: m.ListBankAccountsParams | None, all_accounts: bool
    ) -> AsyncIterator[m.BankAccount]:
        params = params or m.ListBankAccountsParams()
        page = params.page if params.page is not UNSET else 1
        limit = params.limit if params.limit is not UNSET else 100
        while True:
            response = await self._list(replace(params, page=page, limit=limit), all_accounts)
            for item in response.items:
                yield item
            if not response.items or page * limit >= response.total:
                break
            page += 1

    async def iterate(
        self, params: m.ListBankAccountsParams | None = None
    ) -> AsyncIterator[m.BankAccount]:
        """Lazily walk every linked account, starting at params.page."""
        async for item in self._iterate(params, False):
            yield item

    async def iterate_all(
        self, params: m.ListBankAccountsParams | None = None
    ) -> AsyncIterator[m.BankAccount]:
        """Lazily walk service accounts, requesting at most one page at a time."""
        async for item in self._iterate(params, True):
            yield item


class AsyncJobs(AsyncResource):
    """Async verification, polling and independent batch submission."""

    async def submit_bank(
        self, payload: str, options: m.AsyncVerifyOptions | None = None
    ) -> m.JobSubmission:
        """Enqueue one bank slip; successful verification spends quota."""
        body = encode(options) if options else {}
        body["payload"] = _text(payload, 128)
        return await self._call(m.JobSubmission, "POST", "/verify/bank/async", json=body)

    async def submit_bank_batch(
        self, slips: list[m.BatchSlip], options: m.BatchOptions | None = None
    ) -> m.BatchSubmission:
        """Enqueue 1-100 slips; each successful slip spends quota separately."""
        if not slips:
            raise InputError("EMPTY_BATCH", "At least one slip is required")
        if len(slips) > 100:
            raise InputError("BATCH_TOO_LARGE", "At most 100 slips per batch")
        body = encode(options) if options else {}
        body["slips"] = encode(slips)
        return await self._call(m.BatchSubmission, "POST", "/verify/bank/batch", json=body)

    async def submit_bank_many(
        self, slips: list[m.BatchSlip], options: m.BatchOptions | None = None
    ) -> list[m.BatchSubmission]:
        """Submit chunks of 100 in order, retaining receipts on partial failure."""
        if not slips:
            raise InputError("EMPTY_BATCH", "At least one slip is required")
        submitted: list[m.BatchSubmission] = []
        for index in range(0, len(slips), 100):
            try:
                submitted.append(await self.submit_bank_batch(slips[index : index + 100], options))
            except Exception as cause:
                raise BatchSubmitError(submitted, index // 100, cause) from None
        return submitted

    async def get(self, job_id: str) -> m.Job:
        """Read one job, including failed jobs without raising an API error."""
        from urllib.parse import quote

        return await self._call(
            m.Job, "GET", "/verify/bank/jobs/" + quote(_text(job_id, 255), safe=""), safe=True
        )

    async def wait_for_job(
        self, job_id: str, *, interval: float = 2, timeout: float = 600
    ) -> m.Job:
        """Poll until done or failed, bounded by an overall timeout."""
        import math

        if (
            not math.isfinite(interval)
            or interval < 0.5
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise InputError("INVALID_ARGUMENT", "Invalid polling interval or timeout")
        deadline = time.monotonic() + timeout
        last: m.Job | None = None
        while time.monotonic() < deadline:

            async def fetch() -> m.Job:
                response = await self._transport.request(
                    "GET",
                    "/verify/bank/jobs/"
                    + __import__("urllib.parse", fromlist=["quote"]).quote(
                        _text(job_id, 255), safe=""
                    ),
                    safe=True,
                    _deadline=deadline,
                )
                return _decode_response(m.Job, response, self._transport._key)

            task = asyncio.create_task(fetch())
            # Retrieve an eventual failure even if an injected transport suppresses
            # cancellation. Such a late result never becomes last_job.
            task.add_done_callback(
                lambda finished: None if finished.cancelled() else finished.exception()
            )
            try:
                done, _ = await asyncio.wait({task}, timeout=max(0, deadline - time.monotonic()))
            except asyncio.CancelledError:
                task.cancel()
                raise
            if not done:
                task.cancel()
                raise JobWaitTimeoutError(last)
            if time.monotonic() >= deadline:
                raise JobWaitTimeoutError(last)
            try:
                job = task.result()
            except RequestTimeoutError:
                raise JobWaitTimeoutError(last) from None
            if time.monotonic() >= deadline:
                raise JobWaitTimeoutError(last)
            last = job
            if last.status in ("done", "failed"):
                return last
            await asyncio.sleep(min(interval, max(0, deadline - time.monotonic())))
        raise JobWaitTimeoutError(last)


class AsyncV1(AsyncResource):
    """Legacy API operations using the independent v1 base URL."""

    async def get_me(self) -> m.V1Me:
        """Read application quota and credit."""
        return await self._call(m.V1Me, "GET", "/me", safe=True)

    async def verify_bank_by_payload(
        self, payload: str, options: m.V1VerifyOptions | None = None
    ) -> m.BankSlip:
        """Verify a payload through the billed legacy GET endpoint."""
        query = encode(options) if options else {}
        query["payload"] = _text(payload, 255)
        return await self._call(
            m.BankSlip, "GET", "/verify", params={k: _form(v) for k, v in query.items()}
        )

    async def _verify(
        self,
        field: str,
        value: str | FileInput,
        options: m.V1VerifyOptions | None,
        wallet: bool = False,
    ) -> m.BankSlip | m.TrueWalletSlip:
        body = encode(options) if options else {}
        model: type[m.TrueWalletSlip] | type[m.BankSlip] = (
            m.TrueWalletSlip if wallet else m.BankSlip
        )
        path = "/verify/truewallet" if wallet else "/verify"
        if field == "file":
            image = image_input(value, max_bytes=4194304)
            return await self._call(
                model,
                "POST",
                path,
                data={k: _form(v) for k, v in body.items()},
                files={"file": (image.filename, image.data, image.content_type)},
            )
        body[field] = value
        return await self._call(model, "POST", path, json=body)

    async def verify_bank_by_image(
        self, file: FileInput, options: m.V1VerifyOptions | None = None
    ) -> m.BankSlip:
        """Upload an image to v1 using multipart field file."""
        return cast(m.BankSlip, await self._verify("file", file, options))

    async def verify_bank_by_base64(
        self, base64: str, options: m.V1VerifyOptions | None = None
    ) -> m.BankSlip:
        """Send base64 using the legacy JSON field image."""
        return cast(m.BankSlip, await self._verify("image", base64, options))

    async def verify_bank_by_url(
        self, url: str, options: m.V1VerifyOptions | None = None
    ) -> m.BankSlip:
        """Verify a remote image through v1."""
        return cast(m.BankSlip, await self._verify("url", _text(url, 2048), options))

    async def verify_truemoney_by_image(
        self, file: FileInput, options: m.V1VerifyOptions | None = None
    ) -> m.TrueWalletSlip:
        """Upload a wallet image to the legacy endpoint."""
        return cast(m.TrueWalletSlip, await self._verify("file", file, options, True))

    async def generate_qr(self, request: m.QrRequest) -> m.QrCode:
        """Generate a QR code without verification quota consumption."""
        return await self._call(m.QrCode, "POST", "/qr/generate", safe=True, json=encode(request))


class AsyncClient:
    """Credential-safe API client; use a context manager to close owned connections."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        v2_base_url: str | None = None,
        v1_base_url: str | None = None,
        timeout: float = 30,
        max_retries: int = 2,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        key, v2, v1, agent = _settings(api_key, v2_base_url, v1_base_url)
        try:
            self._v2 = AsyncTransport(
                key, v2, http=http, timeout=timeout, max_retries=max_retries, user_agent=agent
            )
            self._v1 = AsyncTransport(
                key, v1, http=http, timeout=timeout, max_retries=max_retries, user_agent=agent
            )
        except ValueError:
            raise InputError("INVALID_ARGUMENT", "Invalid client configuration") from None
        self.verify = AsyncVerify(self._v2)
        self.banks = AsyncBanks(self._v2)
        self.bank_accounts = AsyncBankAccounts(self._v2)
        self.jobs = AsyncJobs(self._v2)
        self.v1 = AsyncV1(self._v1)

    async def get_info(self) -> m.Info:
        """Read application, branch, quota and credit information."""
        response = await self._v2.request("GET", "/info", safe=True)
        return _decode_response(m.Info, response, self._v2._key)

    async def close(self) -> None:
        """Close connections created by this client; injected HTTP clients remain open."""
        await self._v2.close()
        await self._v1.close()

    async def __aenter__(self) -> AsyncClient:
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.close()
