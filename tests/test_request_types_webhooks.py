"""Public input contracts for receiving accounts, QR requests and webhooks."""

import hashlib
import hmac
import subprocess
import sys

import pytest

from thunder_slip.errors import InputError
from thunder_slip.webhooks import construct_event, parse_event


@pytest.mark.parametrize("body", [b"not JSON", b"{}", b"[]", b'"text"'])
def test_malformed_signed_webhook_is_public_input_error(body):
    secret = "webhook-test-secret"
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    for parse in (lambda: parse_event(body), lambda: construct_event(body, signature, secret)):
        with pytest.raises(InputError) as caught:
            parse()
        assert caught.value.code == "INVALID_ARGUMENT"
        assert caught.value.__context__ is None


def test_request_literals_reject_invalid_values_but_response_types_stay_open(tmp_path):
    source = tmp_path / "consumer.py"
    source.write_text("""from thunder_slip import AccountType, QrType
from thunder_slip.models import CreateBankAccountParams, UpdateBankAccountParams, ListBankAccountsParams, QrRequest, MatchedAccount, MatchedBank
account: AccountType = "JURISTIC"
qr: QrType = "PROMPTPAY"
CreateBankAccountParams(bank_code="004", bank_number="123", name_th="Shop", name_en="Shop", type=account)
UpdateBankAccountParams(type=account)
ListBankAccountsParams(type=account)
QrRequest(type=qr)
MatchedAccount(type="FUTURE", bank=MatchedBank(), name_th="", name_en="", bank_number="")
""")
    good = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(source)], capture_output=True, text=True
    )
    assert good.returncode == 0, good.stdout + good.stderr
    source.write_text(
        source.read_text()
        + 'CreateBankAccountParams(bank_code="004", bank_number="123", name_th="Shop", name_en="Shop", type="BANK")\nListBankAccountsParams(type="BANK")\nUpdateBankAccountParams(type="BANK")\nQrRequest(type="INVALID")\n'
    )
    bad = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(source)], capture_output=True, text=True
    )
    assert bad.returncode != 0
    assert bad.stdout.count("error:") == 4, bad.stdout + bad.stderr
