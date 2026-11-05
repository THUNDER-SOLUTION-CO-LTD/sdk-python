import json
from urllib.parse import quote, unquote

import httpx
import pytest

from thunder_slip.errors import api_error, redact_header

KEY = "test-SYNTHETIC/+=secret"
FORMS = [
    KEY,
    KEY.replace("/", r"\/"),
    "".join(f"%{ord(c):02X}" for c in KEY),
    quote(KEY, safe=""),
    "".join(f"%{ord(c):02x}" for c in KEY),
    "".join(f"\\u{ord(c):04x}" for c in KEY),
    "".join(f"\\u{ord(c):04X}" if i % 2 else c for i, c in enumerate(KEY)),
    "".join(f"%{ord(c):02X}" if i % 2 else c for i, c in enumerate(KEY)),
]


@pytest.mark.parametrize("form", FORMS)
def test_header_whole_value_redacted(form):
    assert redact_header("X-Echo", form, KEY) == "[REDACTED]"


@pytest.mark.parametrize("form", FORMS)
@pytest.mark.parametrize("version", ["v1", "v2"])
def test_body_decoded_strings_and_keys(form, version):
    value = {"message": form, "details": {form: form}}
    data = {"error": value, "details": value["details"]} if version == "v2" else value
    original = json.dumps(data)
    error = api_error(httpx.Response(400, text=original), KEY)
    assert error.sensitive_raw_body() == original
    public = json.dumps(json.loads(error.raw_body), ensure_ascii=False)
    assert KEY not in unquote(public)
    assert form not in public or form == "[REDACTED]"


@pytest.mark.parametrize("form", FORMS)
@pytest.mark.parametrize("asynchronous", [False, True])
def test_transport_and_success_headers(form, asynchronous, caplog):
    import asyncio
    from thunder_slip import AsyncClient, Client
    from thunder_slip.errors import NetworkError
    from test_conformance import FIXTURES

    info = json.loads((FIXTURES / "v2/info/success.json").read_text())["response"]["body"]

    def handler(request):
        if request.url.path.endswith("/info"):
            return httpx.Response(
                200, json=info, headers={"X-Echo": form, "Authorization": "anything"}
            )
        error = httpx.ReadError(form, request=request)
        error.code = form
        error.headers = {"authorization": KEY}
        raise error

    def check(error):
        assert error.__context__ is None
        assert error.__cause__ is None
        assert error.cause is not None
        assert not hasattr(error.cause, "request")
        assert not hasattr(error.cause, "headers")
        assert KEY not in unquote(repr(vars(error.cause)))
        assert KEY not in unquote(str(error.cause))
        assert KEY not in caplog.text

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            async with AsyncClient(KEY, http=http, max_retries=0) as client:
                result = await client.get_info()
                assert result.meta.headers["x-echo"] == "[REDACTED]"
                with pytest.raises(NetworkError) as raised:
                    await client.verify.bank_by_payload("synthetic")
                check(raised.value)

    if asynchronous:
        asyncio.run(run())
    else:
        with httpx.Client(transport=httpx.MockTransport(handler)) as http:
            with Client(KEY, http=http, max_retries=0) as client:
                result = client.get_info()
                assert result.meta.headers["x-echo"] == "[REDACTED]"
                with pytest.raises(NetworkError) as raised:
                    client.verify.bank_by_payload("synthetic")
                check(raised.value)


@pytest.mark.parametrize("form", FORMS)
def test_non_json_body(form):
    original = "upstream says " + form
    error = api_error(httpx.Response(500, text=original), KEY)
    assert KEY not in unquote(error.raw_body)
    assert form not in error.raw_body
    assert error.sensitive_raw_body() == original


def test_mixed_occurrences_and_untouched_body():
    from thunder_slip.errors import redact

    assert KEY not in unquote(redact(KEY + " " + FORMS[-1], KEY))
    text = ' { "message" : "ordinary", "details": null } '
    assert api_error(httpx.Response(400, text=text), KEY).raw_body == text


@pytest.mark.parametrize("form", FORMS)
@pytest.mark.parametrize("asynchronous", [False, True])
def test_error_response_every_surface(form, asynchronous):
    import asyncio
    from thunder_slip import AsyncClient, Client
    from thunder_slip.errors import ApiError

    def handler(request):
        return httpx.Response(
            400,
            json={"message": form, "details": {form: form}},
            headers={"X-Echo": form, "Proxy-Authorization": "anything"},
        )

    def check(error):
        assert error.headers["x-echo"] == "[REDACTED]"
        assert error.headers["proxy-authorization"] == "[REDACTED]"
        for text in (
            str(error),
            repr(error),
            repr(error.args),
            repr(vars(error)),
            json.dumps(json.loads(error.raw_body)),
            json.dumps(error.details),
        ):
            assert KEY not in unquote(text)
        assert error.sensitive_raw_body()

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            async with AsyncClient(KEY, http=http, max_retries=0) as client:
                with pytest.raises(ApiError) as raised:
                    await client.get_info()
                check(raised.value)

    if asynchronous:
        asyncio.run(run())
    else:
        with httpx.Client(transport=httpx.MockTransport(handler)) as http:
            with Client(KEY, http=http, max_retries=0) as client:
                with pytest.raises(ApiError) as raised:
                    client.get_info()
                check(raised.value)
