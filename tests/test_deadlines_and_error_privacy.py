"""Adversarial job deadlines and reflected credentials."""

import asyncio
import json
import time
import httpx
import pytest
from thunder_slip import Client, AsyncClient
from thunder_slip.errors import ApiError, JobWaitTimeoutError
from test_conformance import FIXTURES

DONE = json.loads((FIXTURES / "v2/jobs/get/done.json").read_text())["response"]["body"]


def test_sync_late_terminal_is_timeout():
    def handler(request):
        time.sleep(0.12)
        return httpx.Response(200, json=DONE)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with Client("synthetic-secret", http=http) as client:
            started = time.monotonic()
            with pytest.raises(JobWaitTimeoutError):
                client.jobs.wait_for_job("j", timeout=0.02)
            assert time.monotonic() - started < 0.09
            # Let the cooperative test transport finish before closing its client.
            time.sleep(0.14)


@pytest.mark.asyncio
async def test_async_late_terminal_after_cancel_is_timeout():
    async def handler(request):
        try:
            await asyncio.sleep(0.12)
        except asyncio.CancelledError:
            await asyncio.sleep(0.12)
        return httpx.Response(200, json=DONE)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        async with AsyncClient("synthetic-secret", http=http) as client:
            started = time.monotonic()
            with pytest.raises(JobWaitTimeoutError) as raised:
                await client.jobs.wait_for_job("j", timeout=0.02)
            assert raised.value.last_job is None
            assert time.monotonic() - started < 0.09
            await asyncio.sleep(0.14)


@pytest.mark.parametrize("escaped", [False, True])
def test_reflected_authorization_has_no_exception_or_log_leak(escaped, caplog):
    secret = "synthetic-credential-98"

    def handler(request):
        authorization = request.headers["Authorization"]
        text = json.dumps(
            {
                "error": {"code": authorization, "message": authorization},
                "details": {"authorization": authorization},
            }
        )
        if escaped:
            text = text.replace(secret, "".join(f"\\u{ord(c):04x}" for c in secret))
        return httpx.Response(
            401, text=text, headers={"X-Request-ID": authorization, "X-Echo": authorization}
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with Client(secret, http=http, max_retries=0) as client:
            with pytest.raises(ApiError) as raised:
                client.get_info()
    error = raised.value
    views = [str(error), repr(error), repr(error.args), repr(vars(error)), caplog.text]
    assert all(secret not in view for view in views)


@pytest.mark.parametrize("asynchronous", [False, True])
def test_stalled_socket_has_overall_deadline(asynchronous):
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    release = threading.Event()
    disconnected = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.connection.settimeout(0.4)
            if self.connection.recv(1) == b"":
                disconnected.set()
            release.wait(1)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"

    async def run():
        async with AsyncClient("synthetic-secret", v2_base_url=url) as client:
            with pytest.raises(JobWaitTimeoutError):
                await client.jobs.wait_for_job("j", timeout=0.04)

    try:
        started = time.monotonic()
        if asynchronous:
            asyncio.run(run())
        else:
            with Client("synthetic-secret", v2_base_url=url) as client:
                with pytest.raises(JobWaitTimeoutError):
                    client.jobs.wait_for_job("j", timeout=0.04)
        assert time.monotonic() - started < 0.3
        assert disconnected.wait(0.4), "request socket must close at deadline"
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("encoded", [False, True])
def test_sensitive_original_and_encoded_echoes(legacy, encoded):
    from urllib.parse import quote

    secret = "synthetic+credential/98"
    echo = quote(secret, safe="") if encoded else secret
    body = {"message": echo, "details": {echo: echo}}
    if not legacy:
        body = {"error": {"code": "INVALID_API_KEY", "message": echo}, "details": {echo: echo}}
    original = json.dumps(body)

    def handler(request):
        return httpx.Response(
            401,
            text=original,
            headers={
                "Authorization": "different",
                "Proxy-Authorization": "different",
                "X-Echo": echo,
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with Client(secret, http=http, max_retries=0) as client:
            with pytest.raises(ApiError) as raised:
                (client.v1.get_me if legacy else client.get_info)()
    error = raised.value
    assert error.sensitive_raw_body() == original
    assert error.headers["authorization"] == "[REDACTED]"
    assert error.headers["proxy-authorization"] == "[REDACTED]"
    for view in (str(error), repr(error), repr(error.args), repr(vars(error))):
        assert secret not in view and echo not in view


@pytest.mark.parametrize("asynchronous", [False, True])
def test_http_server_reflects_authorization(asynchronous, caplog):
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    secret = "synthetic-reflection-98"

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            echo = self.headers["Authorization"]
            raw = json.dumps({"error": {"code": "INVALID_API_KEY", "message": echo}}).encode()
            self.send_response(401)
            self.send_header("Authorization", echo)
            self.send_header("X-Echo", echo)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"

    async def run():
        async with AsyncClient(secret, v2_base_url=url, max_retries=0) as client:
            with pytest.raises(ApiError) as raised:
                await client.get_info()
            return raised.value

    try:
        if asynchronous:
            error = asyncio.run(run())
        else:
            with Client(secret, v2_base_url=url, max_retries=0) as client:
                with pytest.raises(ApiError) as raised:
                    client.get_info()
                error = raised.value
        assert secret in error.sensitive_raw_body()
        assert secret not in str(error) + repr(error) + repr(error.args) + caplog.text
        assert error.headers["authorization"] == "[REDACTED]"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_success_metadata_redacts_encoded_key_and_auth_headers():
    from urllib.parse import quote

    secret = "synthetic+credential/98"
    echo = quote(secret, safe="")
    case = json.loads((FIXTURES / "v2/info/success.json").read_text())
    body = case["response"]["body"]
    body["message"] = echo

    def handler(request):
        return httpx.Response(
            200, json=body, headers={"Authorization": "different", "X-Echo": echo}
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with Client(secret, http=http) as client:
            result = client.get_info()
    assert result.meta.headers["authorization"] == "[REDACTED]"
    assert echo not in repr(result.meta) and secret not in repr(result.meta)
