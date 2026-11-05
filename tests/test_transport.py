import asyncio
import io

import httpx
import pytest

from thunder_slip._transport import AsyncTransport, Transport
from thunder_slip.errors import APIError, NetworkError, TimeoutError
from thunder_slip.files import image_input
from thunder_slip.webhook import parse_webhook, verify_signature

KEY = "test-only-secret-never-visible"


def test_safe_read_retries_and_honors_retry_after():
    calls = []
    sleeps = []

    def handle(request):
        calls.append(request)
        assert request.headers["authorization"] == f"Bearer {KEY}"
        assert request.headers["user-agent"].startswith("fixture/1 python/")
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "2"}, json={"code": "RATE_LIMIT"})
        return httpx.Response(200, headers={"x-request-id": "id1"}, json={"data": {"ok": True}})

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        with Transport(
            KEY, "https://fixture.invalid", http=http, user_agent="fixture/1", sleep=sleeps.append
        ) as transport:
            response = transport.request("GET", "/info", safe=True)
            assert response.json()["data"]["ok"]
            assert response.headers["x-request-id"] == "id1"
            assert KEY not in repr(transport)
        assert not http.is_closed
    assert sleeps == [2]
    assert len(calls) == 2


@pytest.mark.parametrize("failure", [503, "read", "connect"])
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_quota_calls_never_retry(failure, method):
    calls = []

    def handle(request):
        calls.append(request)
        if failure == "read":
            raise httpx.ReadTimeout(KEY)
        if failure == "connect":
            raise httpx.ConnectError(KEY)
        return httpx.Response(503, json={"code": "BUSY", "message": KEY})

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        transport = Transport(KEY, "https://fixture.invalid", http=http, sleep=lambda _: None)
        with pytest.raises((APIError, NetworkError, TimeoutError)) as result:
            transport.request(method, "/verify/bank", safe=False, json={"payload": "fixture"})
        assert KEY not in str(result.value)
        assert KEY not in repr(result.value)
    assert len(calls) == (3 if failure == "connect" else 1)


def test_safe_network_exhaustion_sanitized():
    def handle(request):
        raise httpx.ConnectError(KEY)

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        transport = Transport(
            KEY, "https://fixture.invalid", http=http, max_retries=1, sleep=lambda _: None
        )
        with pytest.raises(NetworkError) as result:
            transport.request("GET", "/info", safe=True)
        assert KEY not in str(result.value)
        assert result.value.__cause__ is None


async def test_async_transport_retry_and_cancel():
    calls = []

    async def handle(request):
        calls.append(request)
        return httpx.Response(502 if len(calls) == 1 else 200, json={"data": None})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        async with AsyncTransport(
            KEY,
            "https://fixture.invalid",
            http=http,
            max_retries=1,
            sleep=lambda _: asyncio.sleep(0),
        ) as transport:
            assert (await transport.request("GET", "/info", safe=True)).status_code == 200
        assert not http.is_closed
    assert len(calls) == 2


def test_image_sniff_limit_and_stream_position(tmp_path):
    png = b"\x89PNG\r\n\x1a\n" + b"fixture"
    path = tmp_path / "photo.bin"
    path.write_bytes(png)
    for value in [png, path, io.BytesIO(png)]:
        image = image_input(value, max_bytes=len(png))
        assert image.content_type == "image/png"
        assert image.data == png
    with pytest.raises(ValueError, match="limit"):
        image_input(io.BytesIO(png), max_bytes=4)
    with pytest.raises(ValueError, match="image"):
        image_input(b"not an image", max_bytes=1024)


def test_webhook_raw_utf8_prefix_and_invalid_signature():
    import hashlib
    import hmac

    raw = '{"message":"ทดสอบ"}'.encode()
    signature = "sha256=" + hmac.new(b"fixture", raw, hashlib.sha256).hexdigest()
    assert verify_signature(raw, signature, "fixture")
    assert not verify_signature(raw + b" ", signature, "fixture")
    assert not verify_signature(raw, signature[7:], "fixture")
    assert parse_webhook(raw)["message"] == "ทดสอบ"


async def test_async_cancellation_propagates_without_retry():
    started = asyncio.Event()
    calls = 0

    async def handle(request):
        nonlocal calls
        calls += 1
        started.set()
        await asyncio.Event().wait()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        transport = AsyncTransport(KEY, "https://fixture.invalid", http=http)
        task = asyncio.create_task(transport.request("GET", "/info", safe=True))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert calls == 1


@pytest.mark.parametrize("value", [float("inf"), float("nan"), 0, -1])
def test_invalid_timeout_rejected(value):
    with pytest.raises(ValueError):
        Transport(KEY, "https://fixture.invalid", timeout=value)


@pytest.mark.parametrize("value", [float("inf"), float("nan"), 1.5, True, 21])
def test_invalid_retry_budget_rejected(value):
    with pytest.raises(ValueError):
        Transport(KEY, "https://fixture.invalid", max_retries=value)


def test_json_escaped_echo_does_not_restore_key_in_error():
    escaped = "".join("\\u%04x" % ord(char) for char in KEY)

    def handle(request):
        return httpx.Response(
            400, content='{"code":"BAD","message":"' + escaped + '"}', headers={"x-request-id": KEY}
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        transport = Transport(KEY, "https://fixture.invalid", http=http, sleep=lambda _: None)
        with pytest.raises(APIError) as result:
            transport.request("POST", "/verify")
    assert KEY not in str(result.value)
    assert KEY not in str(result.value.__dict__)


def test_nested_v2_error_envelope():
    def handle(request):
        return httpx.Response(
            400,
            json={
                "success": False,
                "error": {"code": "VALIDATION_ERROR", "message": "Invalid input"},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        with pytest.raises(APIError) as result:
            Transport(KEY, "https://fixture.invalid", http=http).request("POST", "/verify")
    assert result.value.code == "VALIDATION_ERROR"
    assert result.value.message == "Invalid input"


def test_webhook_matches_openssl_utf8_signature():
    # openssl dgst -sha256 -hmac fixture over the exact UTF-8 body below.
    raw = '{"message":"ทดสอบ"}'.encode()
    signature = "sha256=e33a4d2685803c3df04f24d5db1648d210b67cf2c627aa4a26b1990988218249"
    assert verify_signature(raw, signature, "fixture")


def test_custom_headers_cannot_replace_credentials_or_user_agent():
    def handle(request):
        assert request.headers["authorization"] == f"Bearer {KEY}"
        assert (
            request.headers["user-agent"].startswith("sdk/")
            and " python/" in request.headers["user-agent"]
        )
        assert request.headers["x-trace"] == "fixture"
        return httpx.Response(200, json={})

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        Transport(KEY, "https://fixture.invalid", http=http).request(
            "GET",
            "/info",
            headers={"Authorization": "bad", "User-Agent": "bad", "X-Trace": "fixture"},
        )


@pytest.mark.parametrize(
    "status,safe,after,expected",
    [
        (429, False, "0", 3),
        (429, False, "61", 1),
        (501, True, None, 1),
        (503, True, "61", 1),
        (502, True, "0", 3),
    ],
)
def test_retry_classes_and_retry_after_cap(status, safe, after, expected):
    calls = []

    def handle(request):
        calls.append(request)
        headers = {"Retry-After": after} if after else {}
        return httpx.Response(
            status, headers=headers, json={"error": {"code": "REJECTED", "message": "No"}}
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        transport = Transport(KEY, "https://fixture.invalid", http=http, sleep=lambda _: None)
        with pytest.raises(APIError):
            transport.request("POST", "/fixture", safe=safe)
    assert len(calls) == expected


def test_signature_requires_lowercase_hex_and_accepts_raw_text():
    raw = '{"message":"ทดสอบ"}'
    signature = "sha256=e33a4d2685803c3df04f24d5db1648d210b67cf2c627aa4a26b1990988218249"
    assert verify_signature(raw, signature, "fixture")
    assert not verify_signature(raw.encode(), "sha256=" + signature[7:].upper(), "fixture")


def test_bytes_default_image_filename_matches_sniffed_type():
    assert image_input(b"\x89PNG\r\n\x1a\nfixture", max_bytes=1024).filename == "slip.png"
