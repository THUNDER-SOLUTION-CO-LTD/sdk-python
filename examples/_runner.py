"""Run one SDK operation. Input JSON and the API key stay in local files."""

from __future__ import annotations
import argparse
import base64
import json
import os
from pathlib import Path
from thunder_slip import Client
from thunder_slip.models import *  # noqa: F403


def run(operation: str) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        help="JSON file with payload, image, image_url, account_id, job_id, callback_url",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Consent to requests, quota use and account writes for this operation",
    )
    args = parser.parse_args()
    if not args.run:
        parser.error("Read the operation first, then pass --run explicitly")
    key_file = os.environ.get("THUNDER_API_KEY_FILE")
    if not key_file:
        parser.error("Set THUNDER_API_KEY_FILE to a private key file")
    data = json.loads(args.input.read_text()) if args.input else {}
    payload = data.get("payload", "")
    image = data.get("image", "slip.png")
    encoded = base64.b64encode(Path(image).read_bytes()).decode() if "Base64" in operation else ""
    image_url = data.get("image_url", "")
    account_id = data.get("account_id", 0)
    job_id = data.get("job_id", "")
    callback_url = data.get("callback_url", "")
    with Client(
        Path(key_file).read_text().strip(),
        v1_base_url=os.environ.get("THUNDER_V1_BASE_URL"),
        v2_base_url=os.environ.get("THUNDER_V2_BASE_URL"),
    ) as client:
        if operation not in OPERATIONS:
            parser.error("Unknown operation")
        # Result models may contain slip PII. Output stays on your terminal.
        result = eval(OPERATIONS[operation], globals(), locals())
        print(result)


OPERATIONS = {
    "getInfo": "client.get_info()",
    "verify.bankByPayload": "client.verify.bank_by_payload(payload, VerifyOptions(check_duplicate=True))",
    "verify.bankByImage": "client.verify.bank_by_image(image)",
    "verify.bankByBase64": "client.verify.bank_by_base64(encoded)",
    "verify.bankByUrl": "client.verify.bank_by_url(image_url)",
    "verify.truewalletByImage": "client.verify.truewallet_by_image(image)",
    "verify.truewalletByBase64": "client.verify.truewallet_by_base64(encoded)",
    "verify.truewalletByUrl": "client.verify.truewallet_by_url(image_url)",
    "banks.list": "client.banks.list()",
    "bankAccounts.list": "client.bank_accounts.list(ListBankAccountsParams(limit=20))",
    "bankAccounts.listAll": "client.bank_accounts.list_all()",
    "bankAccounts.get": "client.bank_accounts.get(account_id)",
    "bankAccounts.create": 'client.bank_accounts.create(CreateBankAccountParams(bank_code="004",bank_number="1234567890",name_th="บัญชีทดสอบ",name_en="Test",type="NATURAL"))',
    "bankAccounts.update": "client.bank_accounts.update(account_id,UpdateBankAccountParams(extra_verify=None))",
    "bankAccounts.link": "client.bank_accounts.link(account_id)",
    "bankAccounts.unlink": "client.bank_accounts.unlink(account_id)",
    "bankAccounts.iterate": "list(client.bank_accounts.iterate())",
    "bankAccounts.iterateAll": "list(client.bank_accounts.iterate_all())",
    "jobs.submitBank": "client.jobs.submit_bank(payload,AsyncVerifyOptions(callback_url=callback_url))",
    "jobs.submitBankBatch": "client.jobs.submit_bank_batch([BatchSlip(payload=payload)],BatchOptions(callback_url=callback_url))",
    "jobs.submitBankMany": "client.jobs.submit_bank_many([BatchSlip(payload=payload)]*201,BatchOptions(callback_url=callback_url))",
    "jobs.get": "client.jobs.get(job_id)",
    "jobs.waitForJob": "client.jobs.wait_for_job(job_id,timeout=600)",
    "v1.getMe": "client.v1.get_me()",
    "v1.verifyBankByPayload": "client.v1.verify_bank_by_payload(payload,V1VerifyOptions(check_duplicate=True))",
    "v1.verifyBankByImage": "client.v1.verify_bank_by_image(image)",
    "v1.verifyBankByBase64": "client.v1.verify_bank_by_base64(encoded)",
    "v1.verifyBankByUrl": "client.v1.verify_bank_by_url(image_url)",
    "v1.verifyTruemoneyByImage": "client.v1.verify_truemoney_by_image(image)",
    "v1.generateQr": 'client.v1.generate_qr(QrRequest(type="PROMPTPAY",msisdn="0812345678",amount=100))',
}
