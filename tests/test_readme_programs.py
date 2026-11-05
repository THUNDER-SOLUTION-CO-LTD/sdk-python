"""Run the payment decisions and webhook handler exactly as printed in the guides."""

import hashlib
import hmac
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from thunder_slip.models import MatchedAccount, MatchedBank, UNSET

ROOT = Path(__file__).parents[1]


def programs(locale):
    return re.findall(r"^```python\n(.*?)^```", (ROOT / locale).read_text(), re.M | re.S)


@pytest.mark.parametrize("locale", ["README.md", "README.th.md"])
@pytest.mark.parametrize(
    "duplicate,amount,account,accepted",
    [
        (False, True, True, True),
        (True, True, True, False),
        (UNSET, True, True, False),
        (False, False, True, False),
        (False, UNSET, True, False),
        (False, True, None, False),
        (False, True, UNSET, False),
    ],
)
def test_quick_start_accepts_only_checked_payment(
    locale, duplicate, amount, account, accepted, capsys
):
    namespace = {"__name__": "readme_example"}
    exec(compile(programs(locale)[0], locale, "exec"), namespace)
    if account is True:
        account = MatchedAccount(
            bank=MatchedBank(), name_th="Shop", name_en="Shop", type="BANK", bank_number="1234"
        )
    name = SimpleNamespace(th="Example")
    party = SimpleNamespace(account=SimpleNamespace(name=name))
    result = SimpleNamespace(
        is_duplicate=duplicate,
        is_amount_matched=amount,
        matched_account=account,
        amount_in_slip=150.0,
        raw_slip=SimpleNamespace(
            date="2026-10-29", trans_ref="example-transfer", sender=party, receiver=party
        ),
    )
    client = MagicMock()
    client.__enter__.return_value.verify.bank_by_image.return_value = result
    namespace["Client"] = lambda: client
    namespace["main"]()
    assert ("Payment checks passed" in capsys.readouterr().out) is accepted
    options = client.__enter__.return_value.verify.bank_by_image.call_args.args[1]
    assert options.match_account is True
    assert options.match_amount == 150.0
    assert options.check_duplicate is True


@pytest.mark.parametrize("locale", ["README.md", "README.th.md"])
def test_webhook_handler_authenticates_original_body(locale, monkeypatch):
    secret = "example-webhook-secret"
    monkeypatch.setenv("THUNDER_WEBHOOK_SECRET", secret)
    namespace = {"__name__": "readme_webhook"}
    exec(compile(programs(locale)[-1], locale, "exec"), namespace)
    client = namespace["app"].test_client()
    body = b'{"jobId":"example-job","batchId":null,"status":"success","data":null,"timestamp":"2026-10-29T00:00:00Z"}'
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert client.post("/webhooks/thunder", data=body).status_code == 400
    assert (
        client.post(
            "/webhooks/thunder", data=body, headers={"X-Thunder-Signature": "bad"}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/webhooks/thunder", data=body, headers={"X-Thunder-Signature": signature}
        ).status_code
        == 204
    )
    assert (
        client.post(
            "/webhooks/thunder", data=body + b" ", headers={"X-Thunder-Signature": signature}
        ).status_code
        == 400
    )


def test_locale_programs_are_identical():
    assert programs("README.md") == programs("README.th.md")


@pytest.mark.parametrize("locale", ["README.md", "README.th.md"])
@pytest.mark.parametrize("body", [b"not JSON", b"{}"])
def test_webhook_handler_rejects_signed_invalid_event(locale, body, monkeypatch):
    secret = "example-webhook-secret"
    monkeypatch.setenv("THUNDER_WEBHOOK_SECRET", secret)
    namespace = {"__name__": "readme_webhook"}
    exec(compile(programs(locale)[-1], locale, "exec"), namespace)
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    response = (
        namespace["app"]
        .test_client()
        .post("/webhooks/thunder", data=body, headers={"X-Thunder-Signature": signature})
    )
    assert response.status_code == 400
