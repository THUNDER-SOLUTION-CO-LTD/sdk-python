"""Pagination, batching, polling and cryptographic contract tests."""

import asyncio
import json
import time
import httpx
import pytest
from thunder_slip import Client, AsyncClient
from thunder_slip import models as m
from thunder_slip.errors import BatchSubmitError, InputError, JobWaitTimeoutError
from thunder_slip.webhooks import verify_signature, parse_event, construct_event
from test_conformance import FIXTURES, invoke, response_for


@pytest.mark.parametrize(
    "path", list((FIXTURES / "behaviour/retry").glob("*.json")), ids=lambda x: x.stem
)
def test_retry_fixtures(path):
    case = json.loads(path.read_text())
    n = 0
    delays = []

    def handler(request):
        nonlocal n
        step = case["steps"][n]
        n += 1
        if "transportError" in step:
            kind = step["transportError"]
            cls = {
                "connect": httpx.ConnectError,
                "timeout": httpx.ReadTimeout,
                "reset": httpx.ReadError,
            }[kind]
            raise cls("simulated", request=request)
        return response_for({"response": step})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with Client(
            "fixture-secret", http=http, max_retries=case["call"]["clientOptions"]["maxRetries"]
        ) as c:
            c._v2._sleep = delays.append
            try:
                result = invoke(c, case["call"]["operation"], case["call"]["args"])
            except Exception as error:
                assert type(error).__name__ == case["expect"]["error"]
            else:
                assert type(result).__name__ == case["expect"]["result"]
            assert n == case["expect"]["requests"]
            if "minDelaySeconds" in case["expect"]:
                assert delays[0] >= case["expect"]["minDelaySeconds"]


def test_pagination_starts_requested_page_and_stops_empty():
    pages = []

    def handler(r):
        page = int(r.url.params["page"])
        pages.append(page)
        assert r.url.params["limit"] == "2"
        return httpx.Response(
            200, json={"data": {"items": [], "total": 100, "page": page, "limit": 2}}
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with Client("fixture-secret", http=http) as c:
            assert list(c.bank_accounts.iterate(m.ListBankAccountsParams(page=3, limit=2))) == []
    assert pages == [3]


def test_batch_partial_receipts_and_input_bounds():
    lengths = []

    def handler(r):
        lengths.append(len(json.loads(r.content)["slips"]))
        if len(lengths) == 2:
            return httpx.Response(
                400, json={"error": {"code": "VALIDATION_ERROR", "message": "no"}}
            )
        return httpx.Response(202, json={"data": {"batchId": "one", "jobs": []}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with Client("fixture-secret", http=http, max_retries=0) as c:
            with pytest.raises(BatchSubmitError) as raised:
                c.jobs.submit_bank_many([m.BatchSlip(payload="a") for _ in range(201)])
            assert lengths == [100, 100]
            assert raised.value.failed_chunk == 1
            assert raised.value.submitted[0].batch_id == "one"
            for slips, code in [
                ([], "EMPTY_BATCH"),
                ([m.BatchSlip(payload="a")] * 101, "BATCH_TOO_LARGE"),
            ]:
                with pytest.raises(InputError) as error:
                    c.jobs.submit_bank_batch(slips)
                assert error.value.code == code


def test_wait_timeout_bounds_entire_retry_budget():
    with httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(503, headers={"Retry-After": "20"}))
    ) as http:
        with Client("fixture-secret", http=http) as c:
            start = time.monotonic()
            with pytest.raises(JobWaitTimeoutError):
                c.jobs.wait_for_job("j", timeout=0.05)
            assert time.monotonic() - start < 0.3


@pytest.mark.asyncio
async def test_async_wait_timeout_and_cancellation():
    async def handler(r):
        await asyncio.sleep(10)
        return httpx.Response(200, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        async with AsyncClient("fixture-secret", http=http) as c:
            with pytest.raises(JobWaitTimeoutError):
                await c.jobs.wait_for_job("j", timeout=0.05)
            task = asyncio.create_task(c.jobs.get("j"))
            await asyncio.sleep(0.01)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task


def test_webhook_shared_signatures_and_roundtrip():
    sig = json.loads((FIXTURES / "webhook/signatures.json").read_text())
    for case in sig["cases"]:
        raw = (FIXTURES / case["body"]).read_bytes()
        assert verify_signature(raw, case.get("signature", ""), sig["secret"]) is case["valid"]
        if not case["valid"]:
            with pytest.raises(Exception):
                construct_event(raw, case.get("signature", ""), sig["secret"])
    for case in json.loads((FIXTURES / "webhook/events.json").read_text())["cases"]:
        event = parse_event((FIXTURES / case["body"]).read_bytes())
        assert event.to_dict() == case["expect"]["json"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path", list((FIXTURES / "behaviour/retry").glob("*.json")), ids=lambda x: x.stem
)
async def test_async_retry_fixtures(path):
    case = json.loads(path.read_text())
    n = 0
    delays = []

    def handler(request):
        nonlocal n
        step = case["steps"][n]
        n += 1
        if "transportError" in step:
            cls = {
                "connect": httpx.ConnectError,
                "timeout": httpx.ReadTimeout,
                "reset": httpx.ReadError,
            }[step["transportError"]]
            raise cls("simulated", request=request)
        return response_for({"response": step})

    async def sleep(delay):
        delays.append(delay)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        async with AsyncClient(
            "fixture-secret", http=http, max_retries=case["call"]["clientOptions"]["maxRetries"]
        ) as c:
            c._v2._sleep = sleep
            try:
                result = await invoke(c, case["call"]["operation"], case["call"]["args"])
            except Exception as error:
                assert type(error).__name__ == case["expect"]["error"]
            else:
                assert type(result).__name__ == case["expect"]["result"]
            assert n == case["expect"]["requests"]
            if "minDelaySeconds" in case["expect"]:
                assert delays[0] >= case["expect"]["minDelaySeconds"]
