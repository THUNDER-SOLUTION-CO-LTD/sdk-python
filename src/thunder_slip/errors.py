"""Typed API and client failures; request credentials are never retained."""

from __future__ import annotations
import email.utils
import json
from urllib.parse import unquote
import re
from datetime import datetime, timezone
from typing import Any, Callable, cast
import httpx
from ._base_error import SDKError
from .models import BankSlip, TrueWalletSlip, RateLimit
from ._codec import decode


class ApiError(SDKError):
    """HTTP error with tracing, rate limits and the response body."""

    def __init__(
        self,
        status: int,
        code: str | None,
        message: str,
        request_id: str | None,
        raw_body: str,
        *,
        headers: dict[str, str] | None = None,
        details: Any = None,
        retry_after: float | None = None,
        rate_limit: RateLimit | None = None,
    ) -> None:
        self._sensitive_body: Callable[[], str] = lambda: raw_body
        self.status = status
        self.code = code
        self.message = message
        self.request_id = request_id
        self.raw_body = raw_body
        self.headers = headers or {}
        self.details = details
        self.retry_after = retry_after
        self.rate_limit = rate_limit
        self.slip: BankSlip | TrueWalletSlip | None = None
        super().__init__(f"[{status} {code or ''}] {message}")

    def sensitive_raw_body(self) -> str:
        """Return the original response body. Do not log or serialize this value."""
        return self._sensitive_body()


APIError = ApiError


class AuthenticationError(ApiError):
    """The API key is missing, malformed or unknown."""


class PermissionDeniedError(ApiError):
    """The key is valid but the account, branch or IP may not call this endpoint."""


class QuotaExceededError(PermissionDeniedError):
    """The service quota is used up. Nothing was charged."""


class InvalidRequestError(ApiError):
    """The API rejected the request body, query or parameters."""


class InvalidImageError(InvalidRequestError):
    """The image is missing, too large, not an image, or not a slip of the right kind."""


class InvalidUrlError(InvalidRequestError):
    """An image URL or callback URL was refused (protocol, private address, unreachable)."""


class DuplicateSlipError(InvalidRequestError):
    """v1 only. The slip was verified before; `slip` holds the parsed original slip."""


class NotFoundError(ApiError):
    """The resource (bank account, job, route) does not exist or is not visible to this branch."""


class SlipNotFoundError(NotFoundError):
    """The bank or wallet could not find the slip, or no QR code was found in the image."""


class SlipPendingError(NotFoundError):
    """Bangkok Bank slip from the last few minutes; try again later."""


class ConflictError(ApiError):
    """The request conflicts with existing data (duplicate bank account)."""


class RateLimitError(ApiError):
    """Too many requests. Carries retryAfter (seconds) when the API sends Retry-After."""


class ServerError(ApiError):
    """5xx from the API or an upstream bank service."""


class ServiceUnavailableError(ServerError):
    """503, a dependency is briefly unavailable. Usually sent with Retry-After."""


class NetworkError(SDKError):
    """A transport failure, with a credential-free cause."""

    def __init__(self, message: str, cause: BaseException | None = None) -> None:
        self.cause = cause
        super().__init__(message)


class RequestTimeoutError(NetworkError):
    """The configured client timeout expired."""


TimeoutError = RequestTimeoutError


class InputError(SDKError, ValueError):
    """An argument rejected before sending any request."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class WebhookSignatureError(SDKError):
    """The raw body did not match the supplied signature."""


class JobWaitTimeoutError(SDKError):
    """Polling deadline reached; last_job retains the last observation."""

    def __init__(self, last_job: Any) -> None:
        self.last_job = last_job
        super().__init__("Job polling timed out")


class BatchSubmitError(SDKError):
    """A chunk failed after earlier independent chunks were accepted."""

    def __init__(self, submitted: list[Any], failed_chunk: int, cause: Exception) -> None:
        self.submitted = submitted
        self.failed_chunk = failed_chunk
        self.cause = cause
        super().__init__(f"Batch chunk {failed_chunk} failed")


def rate_limit(headers: dict[str, str]) -> RateLimit | None:
    """Read the complete rate limit triple, or return None."""
    try:
        return RateLimit(
            **{x: int(headers["x-ratelimit-" + x]) for x in ("limit", "remaining", "reset")}
        )
    except (KeyError, ValueError):
        return None


def retry_after(value: str | None) -> float | None:
    """Parse Retry-After seconds or an HTTP date."""
    if value is None:
        return None
    try:
        return max(0, float(value))
    except ValueError:
        try:
            return max(
                0,
                (
                    email.utils.parsedate_to_datetime(value) - datetime.now(timezone.utc)
                ).total_seconds(),
            )
        except (ValueError, TypeError):
            return None


_CODES = {
    "MISSING_API_KEY": "AuthenticationError",
    "INVALID_API_KEY": "AuthenticationError",
    "BRANCH_INACTIVE": "PermissionDeniedError",
    "SERVICE_BANNED": "PermissionDeniedError",
    "SERVICE_DELETED": "PermissionDeniedError",
    "USER_BANNED": "PermissionDeniedError",
    "IP_NOT_ALLOWED": "PermissionDeniedError",
    "SERVICE_EXPIRED": "PermissionDeniedError",
    "QUOTA_EXCEEDED": "QuotaExceededError",
    "VALIDATION_ERROR": "InvalidRequestError",
    "INVALID_BANK_CODE": "InvalidRequestError",
    "INVALID_EXTRA_VERIFY": "InvalidRequestError",
    "INVALID_MATCH_MODE": "InvalidRequestError",
    "IMAGE_SIZE_TOO_LARGE": "InvalidImageError",
    "INVALID_IMAGE_FORMAT": "InvalidImageError",
    "INVALID_IMAGE_TYPE": "InvalidImageError",
    "INVALID_IMAGE": "InvalidImageError",
    "INVALID_WALLET_QR": "InvalidImageError",
    "URL_PROTOCOL_NOT_ALLOWED": "InvalidUrlError",
    "URL_INVALID_IP_RANGE": "InvalidUrlError",
    "IMAGE_URL_UNREACHABLE": "InvalidUrlError",
    "INVALID_CALLBACK_URL": "InvalidUrlError",
    "SLIP_NOT_FOUND": "SlipNotFoundError",
    "SLIP_PENDING": "SlipPendingError",
    "BANK_ACCOUNT_NOT_FOUND": "NotFoundError",
    "JOB_NOT_FOUND": "NotFoundError",
    "NOT_FOUND": "NotFoundError",
    "BANK_ACCOUNT_DUPLICATE": "ConflictError",
    "RATE_LIMIT_EXCEEDED": "RateLimitError",
    "API_SERVER_ERROR": "ServerError",
    "INTERNAL_SERVER_ERROR": "ServerError",
    "RENEWAL_TEMPORARILY_UNAVAILABLE": "ServiceUnavailableError",
    "CALLBACK_UNAVAILABLE": "ServiceUnavailableError",
    "unauthorized": "AuthenticationError",
    "access_denied": "PermissionDeniedError",
    "account_not_verified": "PermissionDeniedError",
    "application_expired": "PermissionDeniedError",
    "application_deactivated": "PermissionDeniedError",
    "quota_exceeded": "QuotaExceededError",
    "invalid_payload": "InvalidRequestError",
    "invalid_check_duplicate": "InvalidRequestError",
    "invalid_request": "InvalidRequestError",
    "invalid_type": "InvalidRequestError",
    "invalid_transaction_id": "InvalidRequestError",
    "invalid_sender_name": "InvalidRequestError",
    "invalid_receiver_name": "InvalidRequestError",
    "invalid_receiver_phone": "InvalidRequestError",
    "invalid_date": "InvalidRequestError",
    "invalid_amount": "InvalidRequestError",
    "invalid_image": "InvalidImageError",
    "invalid_wallet_qr": "InvalidImageError",
    "invalid_base64": "InvalidImageError",
    "image_size_too_large": "InvalidImageError",
    "invalid_url": "InvalidUrlError",
    "url_unreachable": "InvalidUrlError",
    "duplicate_slip": "DuplicateSlipError",
    "slip_not_found": "SlipNotFoundError",
    "qrcode_not_found": "SlipNotFoundError",
    "slip_pending": "SlipPendingError",
    "not_found": "NotFoundError",
    "rate_limit_exceeded": "RateLimitError",
    "server_error": "ServerError",
    "api_server_error": "ServerError",
    "renewal_temporarily_unavailable": "ServiceUnavailableError",
}
_FALLBACK = {
    400: "InvalidRequestError",
    401: "AuthenticationError",
    403: "PermissionDeniedError",
    404: "NotFoundError",
    409: "ConflictError",
    429: "RateLimitError",
    500: "ServerError",
    502: "ServerError",
    503: "ServiceUnavailableError",
    504: "ServerError",
}


_JSON_ESCAPE = re.compile(r'(?:\\u[0-9a-fA-F]{4})+|\\[/\\"]|\\[bfnrt]')


def _decoded(value: str) -> str:
    # Decode valid escapes independently: a header need not be a JSON document.
    def escape(match: re.Match[str]) -> str:
        return cast(str, json.loads('"' + match.group() + '"'))

    return _JSON_ESCAPE.sub(escape, unquote(value))


def redact(value: str, secret: str) -> str:
    """Remove credential echoes, including mixed URL and JSON escapes."""
    if len(secret) < 4:
        return value
    original = value
    while True:
        if secret in value:
            return "[REDACTED]".join(redact(part, secret) for part in value.split(secret))
        decoded = _decoded(value)
        if decoded == value:
            return original
        value = decoded


def redact_header(name: str, value: str, secret: str) -> str:
    """Remove an entire credential-bearing header value."""
    if name.lower() in {"authorization", "proxy-authorization"} or redact(value, secret) != value:
        return "[REDACTED]"
    return value


def _clean_json(value: Any, secret: str) -> Any:
    if isinstance(value, str):
        return redact(value, secret)
    if isinstance(value, list):
        return [_clean_json(item, secret) for item in value]
    if isinstance(value, dict):
        return {redact(k, secret): _clean_json(v, secret) for k, v in value.items()}
    return value


def api_error(response: httpx.Response, secret: str) -> ApiError:
    """Decode an HTTP error and redact literal or JSON-escaped credential echoes."""
    original = response.text
    raw = original
    try:
        body = json.loads(original)
        clean = _clean_json(body, secret)
        if clean != body:
            raw = json.dumps(clean, ensure_ascii=False)
        body = clean
    except ValueError:
        raw = redact(original, secret)
        if raw != original and _decoded(original) != original:
            raw = "[REDACTED]"
        body = {}
    if not isinstance(body, dict):
        body = {}
    value: dict[str, Any] = (
        cast(dict[str, Any], body["error"]) if isinstance(body.get("error"), dict) else body
    )
    code = value.get("code") or value.get("message")
    message = value.get("message") or f"HTTP {response.status_code}"
    headers = {k.lower(): redact_header(k, v, secret) for k, v in response.headers.items()}
    cls = globals()[
        _CODES.get(
            code or "",
            _FALLBACK.get(
                response.status_code, "ServerError" if response.status_code >= 500 else "ApiError"
            ),
        )
    ]
    result: ApiError = cls(
        response.status_code,
        code,
        message,
        headers.get("x-request-id") or headers.get("cf-ray"),
        raw,
        headers=headers,
        details=body.get("details"),
        retry_after=retry_after(headers.get("retry-after")),
        rate_limit=rate_limit(headers),
    )
    result._sensitive_body = lambda: original
    if isinstance(result, DuplicateSlipError) and isinstance(body.get("data"), dict):
        data = body["data"]
        result.slip = (
            decode(TrueWalletSlip, data) if "transactionId" in data else decode(BankSlip, data)
        )
    return result


class SanitizedTransportError(Exception):
    """An allowlisted transport diagnostic; never retains the source exception."""

    def __init__(self, error: BaseException, secret: str) -> None:
        self.type_name = type(error).__name__
        message = redact(str(error), secret)
        if message != str(error) and _decoded(str(error)) != str(error):
            message = "[REDACTED]"
        self.code: str | int | float | None = None
        code = getattr(error, "code", getattr(error, "errno", None))
        if isinstance(code, (str, int, float)):
            self.code = redact(str(code), secret) if isinstance(code, str) else code
        super().__init__(message)
