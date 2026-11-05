"""Shared response contract, exercised without live credentials."""

import json
import os
from pathlib import Path
import httpx
import pytest
from thunder_slip import models
from thunder_slip._codec import decode
from thunder_slip.errors import api_error
from thunder_slip import Client, AsyncClient
import re
import hashlib
from email import policy
from email.parser import BytesParser


FIXTURES = Path(os.environ.get("THUNDER_FIXTURES_DIR", Path(__file__).parents[1] / "fixtures"))
CASES = []
for path in FIXTURES.rglob("*.json"):
    value = json.loads(path.read_text())
    if isinstance(value, dict) and "response" in value and "expect" in value:
        CASES.append((path.relative_to(FIXTURES).as_posix(), value))


@pytest.mark.parametrize("name,case", CASES, ids=[x[0] for x in CASES])
def test_response_contract(name, case):
    r = case["response"]
    exp = case["expect"]
    body = r["body"]
    raw = (
        body.get("_nonJson")
        if isinstance(body, dict) and "_nonJson" in body
        else json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    )
    response = httpx.Response(r["status"], headers=r.get("headers", {}), content=raw)
    if "error" in exp:
        err = api_error(response, "fixture-secret")
        for field in ("status", "code", "message", "requestId", "retryAfter"):
            if field in exp["error"]:
                attr = {"requestId": "request_id", "retryAfter": "retry_after"}.get(field, field)
                assert getattr(err, attr) == exp["error"][field], name
        assert type(err).__name__ == exp["error"]["class"]
        assert err.raw_body == raw
    elif "model" in exp:
        model = getattr(models, exp["model"])
        data = body["data"]
        result = (
            model(items=[decode(models.Bank, x) for x in data])
            if model is models.BankList
            else decode(model, data)
        )
        assert result.to_dict() == data, name


def snake(value):
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()


def invoke(client, operation, args):
    args = dict(args)
    if "file" in args:
        args["file"] = (FIXTURES / args["file"]).read_bytes()
    # Fixtures flatten parameters; resources expose typed params/options.
    parts = operation.split(".")
    if operation == "getInfo":
        return client.get_info()
    resource = getattr(client, snake(parts[0]))
    method = getattr(resource, snake(parts[1]))
    if parts[0] == "bankAccounts":
        if parts[1] in ("list", "listAll"):
            return method(decode(models.ListBankAccountsParams, args))
        if parts[1] == "create":
            return method(decode(models.CreateBankAccountParams, args.get("params", args)))
        id = args.pop("id")
        if parts[1] == "update":
            return method(id, decode(models.UpdateBankAccountParams, args.get("params", args)))
        return method(id)
    if parts[0] == "banks":
        return method()
    if parts[0] == "jobs":
        if parts[1] == "get":
            return method(args["jobId"])
        if parts[1] == "submitBankBatch":
            return method(
                [decode(models.BatchSlip, x) for x in args["slips"]],
                decode(
                    models.BatchOptions,
                    args.get(
                        "options", {k: v for k, v in args.items() if k not in ("payload", "slips")}
                    ),
                ),
            )
        return method(
            args["payload"],
            decode(
                models.AsyncVerifyOptions,
                args.get(
                    "options", {k: v for k, v in args.items() if k not in ("payload", "slips")}
                ),
            ),
        )
    if parts[0] == "v1" and parts[1] == "getMe":
        return method()
    if parts[0] == "v1" and parts[1] == "generateQr":
        return method(decode(models.QrRequest, args.get("request", args)))
    field = next(k for k in ("payload", "file", "base64", "url") if k in args)
    option_model = models.V1VerifyOptions if parts[0] == "v1" else models.VerifyOptions
    options = args.get("options", {k: v for k, v in args.items() if k != field})
    return method(args[field], decode(option_model, options))


def assert_request(request, case):
    expected = case["request"]
    assert request.method == expected["method"]
    assert request.url.path == "/" + case["api"] + expected["path"]
    assert dict(request.url.params) == expected.get("query", {})
    assert request.headers["authorization"] == "Bearer fixture-secret"
    if "contentType" in expected:
        assert request.headers.get("content-type", "").split(";")[0] == expected["contentType"]
    if "body" in expected:
        assert json.loads(request.content) == expected["body"]
    if "multipart" in expected:
        message = BytesParser(policy=policy.default).parsebytes(
            b"Content-Type: "
            + request.headers["content-type"].encode()
            + b"\r\n\r\n"
            + request.content
        )
        fields = {}
        files = []
        for part in message.iter_parts():
            name = part.get_param("name", header="content-disposition")
            data = part.get_payload(decode=True)
            if part.get_filename():
                files.append(
                    dict(
                        field=name,
                        filename=part.get_filename(),
                        contentType=part.get_content_type(),
                        sha256=hashlib.sha256(data).hexdigest(),
                    )
                )
            else:
                fields[name] = data.decode()
        assert fields == expected["multipart"]["fields"]
        assert files == [
            {k: f[k] for k in ("field", "filename", "contentType", "sha256")}
            for f in expected["multipart"]["files"]
        ]


def response_for(case):
    r = case["response"]
    body = r["body"]
    return httpx.Response(
        r["status"],
        headers=r.get("headers", {}),
        content=body["_nonJson"]
        if isinstance(body, dict) and "_nonJson" in body
        else json.dumps(body, ensure_ascii=False),
    )


CALLS = [
    (n, c)
    for n, c in CASES
    if c.get("conformance") == "call" and c.get("request", {}).get("auth") != "none"
]


@pytest.mark.parametrize("name,case", CALLS, ids=[x[0] for x in CALLS])
def test_sync_request(name, case):
    def handler(request):
        assert_request(request, case)
        return response_for(case)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with Client(
            "fixture-secret",
            v2_base_url="https://api.test/v2",
            v1_base_url="https://api.test/v1",
            http=http,
            max_retries=0,
        ) as client:
            if "error" in case["expect"]:
                with pytest.raises(Exception) as error:
                    invoke(client, case["operation"], case["call"]["args"])
                assert type(error.value).__name__ == case["expect"]["error"]["class"]
            else:
                result = invoke(client, case["operation"], case["call"]["args"])
                assert result.to_dict() == case["response"]["body"]["data"]
                assert result.meta.status == case["response"]["status"]


@pytest.mark.asyncio
@pytest.mark.parametrize("name,case", CALLS, ids=[x[0] for x in CALLS])
async def test_async_request(name, case):
    def handler(request):
        assert_request(request, case)
        return response_for(case)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        async with AsyncClient(
            "fixture-secret",
            v2_base_url="https://api.test/v2",
            v1_base_url="https://api.test/v1",
            http=http,
            max_retries=0,
        ) as client:
            if "error" in case["expect"]:
                with pytest.raises(Exception) as error:
                    await invoke(client, case["operation"], case["call"]["args"])
                assert type(error.value).__name__ == case["expect"]["error"]["class"]
            else:
                result = await invoke(client, case["operation"], case["call"]["args"])
                assert result.to_dict() == case["response"]["body"]["data"]
