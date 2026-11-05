# Thunder Python SDK

[![CI](https://github.com/THUNDER-SOLUTION-CO-LTD/sdk-python/actions/workflows/ci.yml/badge.svg)](https://github.com/THUNDER-SOLUTION-CO-LTD/sdk-python/actions/workflows/ci.yml) [![MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Verify Thai bank transfer slips and TrueMoney Wallet receipts from Python. Check the receiving account, amount and duplicate status before crediting an order.

[ภาษาไทย](README.th.md)

## Features

- Verify a bank slip from an image, QR payload, URL or base64.
- Check whether a transfer pays a linked receiving account for the expected amount.
- Detect previously used slips before accepting payment.
- Verify TrueMoney Wallet receipts.
- Read remaining quota and manage receiving accounts.
- Submit batches, track background jobs and authenticate webhooks.
- Generate PromptPay and bill payment QR codes.

## Requirements

Python 3.11 through 3.15. Create a service in [the Thunder developer portal](https://developer.thunder.in.th), then copy its API key into your server environment as `THUNDER_API_KEY`. You can instead set `THUNDER_API_KEY_FILE` to a private file containing the key.

## Installation

```sh
python -m pip install thunder-solution-sdk
```

## Quick start

Save the program below as `verify_payment.py`. Put a transfer slip at `slip.png` and set the API key. In the portal, add your receiving account and link it to the service/branch associated with the key. Change `150.0` to the order amount from your own database, not a value sent by the customer. Each verification can consume quota.

```python
from pathlib import Path
from thunder_slip import Client
from thunder_slip.errors import SlipNotFoundError, SlipPendingError
from thunder_slip.models import MatchedAccount, VerifyOptions


def main() -> None:
    with Client() as client:  # Reads THUNDER_API_KEY from the environment.
        try:
            result = client.verify.bank_by_image(
                Path("slip.png"),
                VerifyOptions(match_account=True, match_amount=150.0, check_duplicate=True),
            )
        except SlipPendingError:
            print("The bank has not made this slip available yet. Check again later.")
            return
        except SlipNotFoundError:
            print("No transfer was found. Ask the customer to check the slip.")
            return
        if result.is_duplicate is not False:
            print("This slip was used before, or duplicate checking was unavailable.")
            return
        if result.is_amount_matched is not True:
            print("The transfer does not match the order amount.")
            return
        if not isinstance(result.matched_account, MatchedAccount):
            print("The transfer did not match a linked receiving account.")
            return
        slip = result.raw_slip
        print("Amount:", result.amount_in_slip)
        print("Date:", slip.date)
        print("Sender:", slip.sender.account.name.th)
        print("Receiver:", slip.receiver.account.name.th)
        print("Transaction:", slip.trans_ref)
        print("Payment checks passed. Record this transaction once for the order.")


if __name__ == "__main__":
    main()
```

Run `python verify_payment.py`. A successful check prints output like this (illustrative values):

    Amount: 150.0
    Date: 2026-10-29T14:32:00+07:00
    Sender: ผู้โอนตัวอย่าง
    Receiver: ร้านตัวอย่าง
    Transaction: EXAMPLE-TRANSFER-001
    Payment checks passed. Record this transaction once for the order.

Credit the order only after all checks pass. Store the transaction reference with a database uniqueness constraint and update the order in the same transaction, so concurrent requests cannot credit it twice. The SDK does not update your orders.

Next steps: [payment checks](#payment-checks), [receiving accounts](#receiving-accounts), [background jobs](#background-jobs), [error handling](#error-handling).

## Usage

### Verify a bank slip

| What you have | Method |
| --- | --- |
| Image file or uploaded bytes | `client.verify.bank_by_image` |
| QR payload text | `client.verify.bank_by_payload` |
| Public image URL | `client.verify.bank_by_url` |
| Base64 image | `client.verify.bank_by_base64` |

Payload means the text decoded from the slip QR, not the transaction reference. Image input accepts a path, `bytes` or a binary file object. A string is a local file path: never pass an untrusted user string, because the SDK will read that file on your server.

```python
from pathlib import Path
from thunder_slip import Client

with Client() as client:
    result = client.verify.bank_by_payload(Path("payload.txt").read_text().strip())
    print(result.amount_in_slip, result.raw_slip.trans_ref)
```

### Payment checks

API v2 returns check results in a successful response: `is_duplicate=True`, `is_amount_matched=False`, or `matched_account=None` means you must reject the payment. A mismatch does not raise an API error. The quick start also rejects missing check results. `matchAccount` checks accounts linked to this service/branch; `matchAmount` compares the transfer against your order total; `checkDuplicate` asks whether this slip was used before.

```python
from thunder_slip import Client
from thunder_slip.models import VerifyOptions

with Client() as client:
    result = client.verify.bank_by_image(
        "slip.png", VerifyOptions(match_account=True, match_amount=150.0, check_duplicate=True)
    )
    print(result.is_duplicate, result.is_amount_matched, result.matched_account)
```

### TrueMoney Wallet

Use a Wallet receipt image. Check the same payment flags before crediting the order; the receipt reference is `raw_slip.transaction_id`.

```python
from thunder_slip import Client
from thunder_slip.models import VerifyOptions

with Client() as client:
    result = client.verify.truewallet_by_image(
        "wallet-slip.png",
        VerifyOptions(match_account=True, match_amount=150.0, check_duplicate=True),
    )
    print(result.amount_in_slip, result.raw_slip.transaction_id)
```

### Account info and quota

Read quota before planning a batch. A null remaining quota means the API did not return a numeric limit; it is not zero.

```python
from thunder_slip import Client

with Client() as client:
    info = client.get_info()
    print("Remaining quota:", info.application.quota.remaining)
```

### Receiving accounts

This example lists linked accounts with automatic pagination, creates a receiving account, updates its name and links it to the key's branch. Set `RECEIVING_ACCOUNT_NUMBER` to your own account; run the create step once, then reuse the returned id. `list()` and `list_all()` return one page; `iterate_all()` walks all service accounts.

```python
import os
from thunder_slip import Client
from thunder_slip.models import (
    CreateBankAccountParams,
    ListBankAccountsParams,
    UpdateBankAccountParams,
)

with Client() as client:
    for account in client.bank_accounts.iterate(ListBankAccountsParams(limit=50)):
        print(account.id, account.name_th)
    account = client.bank_accounts.create(
        CreateBankAccountParams(
            bank_code="004",
            bank_number=os.environ["RECEIVING_ACCOUNT_NUMBER"],
            name_th="ร้านตัวอย่าง",
            name_en="Example Shop",
            type="JURISTIC",
        )
    )
    updated = client.bank_accounts.update(
        account.id, UpdateBankAccountParams(name_en="Example Shop")
    )
    print("Updated:", updated.id)
    print("Linked:", client.bank_accounts.link(account.id).linked)
```

### Background jobs

Submit QR payloads as a batch and keep each job id. Polling the same job does not submit another verification. `wait_for_job` waits up to ten minutes by default, including HTTP requests and retry delays; inspect the terminal status and payment checks before accepting a result.

```python
from pathlib import Path
from thunder_slip import Client
from thunder_slip.models import BatchSlip

with Client() as client:
    payload = Path("payload.txt").read_text().strip()
    batch = client.jobs.submit_bank_batch([BatchSlip(payload=payload, check_duplicate=True)])
    for submitted in batch.jobs:
        job = client.jobs.wait_for_job(submitted.job_id, timeout=600)
        print(job.job_id, job.status, job.result)
```

### Generate a payment QR

Set `PROMPTPAY_PHONE` to your PromptPay phone number. For bill payment, use `type="PROMPTPAY"` with `biller_id` and `ref1`; `ref2` is optional. The older `BILL_PAYMENT` type still works for existing integrations. Amounts must be from 0.01 to 9,999,999,999.99 with at most two decimal places; omit the amount for an open-amount QR. Save the image returned by the API:

```python
import os
from pathlib import Path
from thunder_slip import Client
from thunder_slip.models import QrRequest

with Client() as client:
    qr = client.v1.generate_qr(
        QrRequest(
            type="PROMPTPAY",
            msisdn=os.environ["PROMPTPAY_PHONE"],
            amount=150.0,
        )
    )
    Path("payment-qr.png").write_bytes(qr.image_bytes())
    print("Saved payment-qr.png")
```

```python
import os
from thunder_slip import Client
from thunder_slip.models import QrRequest

with Client() as client:
    qr = client.v1.generate_qr(
        QrRequest(
            type="PROMPTPAY",
            biller_id=os.environ["BILLER_ID"],
            ref1=os.environ["BILL_REFERENCE"],
            amount=150.0,
        )
    )
    print(qr.image)
```

### Legacy API v1

Use v2 for new integrations. Existing v1 code can use `client.v1`; it returns the slip directly, and duplicate detection raises `DuplicateSlipError`.

```python
from thunder_slip import Client
from thunder_slip.models import V1VerifyOptions

with Client() as client:
    slip = client.v1.verify_bank_by_image("slip.png", V1VerifyOptions(check_duplicate=True))
    print(slip.amount.amount, slip.trans_ref)
```

### Async requests

Use `AsyncClient` in an async application and await each operation. Reuse one client for multiple requests; limit concurrency to fit your quota and server resources.

```python
import asyncio
from thunder_slip import AsyncClient
from thunder_slip.models import VerifyOptions


async def main() -> None:
    async with AsyncClient() as client:
        result = await client.verify.bank_by_image(
            "slip.png", VerifyOptions(match_account=True, match_amount=150.0, check_duplicate=True)
        )
        print(result.amount_in_slip, result.is_duplicate, result.is_amount_matched)


asyncio.run(main())
```

## The result object

The bank and Wallet result share amount and payment-check fields. Bank details are under `raw_slip`; Wallet uses a different receipt model. Optional fields appear only when the API supplies them: `UNSET` means absent, while `None` means JSON null.

| Field | Type | Meaning | Example |
| --- | --- | --- | --- |
| `amount_in_slip` | float | Verified transfer amount in baht | 150.0 |
| `is_duplicate` | optional bool | Whether the slip was used before | false |
| `is_amount_matched` | optional bool | Whether the transfer matches the order amount | true |
| `amount_in_order` | optional float | Order amount sent for comparison | 150.0 |
| `matched_account` | optional account or null | Linked receiving account that matched | account object |
| `raw_slip.trans_ref` | string | Bank transaction reference | EXAMPLE-TRANSFER-001 |
| `raw_slip.date` | string | Transfer date and time, including offset when returned | 2026-10-29T14:32:00+07:00 |
| `raw_slip.sender.account.name.th` | optional string | Sender name in Thai | ผู้โอนตัวอย่าง |
| `raw_slip.receiver.account.name.th` | optional string | Receiver name in Thai | ร้านตัวอย่าง |
| `raw_slip.sender.account.bank.account` | optional string | Sender account number as returned, possibly masked | xxx-x-x1234-x |
| `raw_slip.receiver.account.bank.account` | optional string | Receiver account number as returned, possibly masked | xxx-x-x5678-x |
| `raw_slip.transaction_id` | string (Wallet) | Wallet transaction reference | EXAMPLE-WALLET-001 |
| `raw_slip.sender.name` | string (Wallet) | Wallet sender name | ผู้ส่งตัวอย่าง |
| `raw_slip.receiver.name` | string (Wallet) | Wallet receiver name | ผู้รับตัวอย่าง |
| `raw_slip.receiver.phone` | string (Wallet) | Wallet receiver phone as returned | 0xx-xxx-1234 |

See the [full Python model reference](https://document.thunder.in.th/en/sdk/python).

## Configuration

| Option | Environment variable | Default | What it does |
| --- | --- | --- | --- |
| `api_key` | THUNDER_API_KEY; THUNDER_API_KEY_FILE | environment/file | Explicit key overrides environment; file is the fallback. |
| `timeout` | none | 30 seconds | Timeout for each HTTP attempt. |
| `max_retries` | none | 2 | At most two additional attempts when retry rules allow. |
| `v2_base_url / v1_base_url` | THUNDER_V2_BASE_URL; THUNDER_V1_BASE_URL | https://api.thunder.in.th/v2; https://api.thunder.in.th/v1 | Override the API endpoints. |
| `http` | none | new HTTP client | Supply a custom client; close it yourself. |

The example closes the custom HTTP client as well as the SDK client. With the default client, `with Client()` closes its connections automatically.

```python
import httpx
from thunder_slip import Client

with httpx.Client(trust_env=False, follow_redirects=False) as http:
    with Client(timeout=15, max_retries=1, http=http) as client:
        print(client.get_info().application.name)
```

## Error handling

`ThunderError` is the root exception; `ApiError` covers HTTP failures and `RequestTimeoutError` is a `NetworkError`.

A recognized API error code selects the error class first; otherwise the SDK uses the HTTP status. Unmapped 4xx responses use `ApiError`.

| Error class | HTTP status or stage | When it happens | What to do |
| --- | --- | --- | --- |
| `ThunderError` | varies | Base for all SDK failures. | Catch a specific error first. |
| `ApiError` | HTTP | Base for rejected API requests. | Use status, code and request id for diagnosis. |
| `AuthenticationError` | 401 | API key is invalid. | Check the key for this service. |
| `PermissionDeniedError` | 403 | Service, branch or IP cannot call the API. | Check service access and IP restrictions. |
| `QuotaExceededError` | 403 | Verification quota is exhausted. | Add quota before accepting more slips. |
| `InvalidRequestError` | 400 | The API rejects an argument. | Correct the request before sending again. |
| `InvalidImageError` | 400 | Image is unreadable, oversized or unsupported. | Send a readable supported image. |
| `InvalidUrlError` | 400 | Image or callback URL is refused. | Use a reachable public HTTPS URL. |
| `DuplicateSlipError` | 400 (v1) | A previously verified slip is submitted with duplicate checking. | Do not credit the same transfer again; inspect slip. |
| `NotFoundError` | 404 | Resource is missing or outside this branch. | Check the account or job id and branch. |
| `SlipNotFoundError` | 404 | No transfer or slip QR was found. | Ask for a readable slip from a completed transfer. |
| `SlipPendingError` | 404 | A recent slip is not available from the bank yet. | Wait before checking again. |
| `ConflictError` | 409 | Receiving account already exists. | Reuse it instead of creating another. |
| `RateLimitError` | 429 | Request rate is too high. | Wait for retry_after when present. |
| `ServerError` | 500, 502, 504; other 5xx except 503 | The API or bank could not finish the request. | Reconcile billed calls before resending. |
| `ServiceUnavailableError` | 503 | A dependency is unavailable. | Wait and check service status. |
| `InputError` | before sending | Local validation rejects input. | Fix the argument identified by code. |
| `NetworkError` | network | Connection fails. | Check connectivity and reconcile the outcome. |
| `RequestTimeoutError` | network | HTTP request exceeds its timeout. | Check the payment outcome before resubmitting. |
| `JobWaitTimeoutError` | polling deadline | Job polling exceeds the overall deadline. | Keep last_job and poll the same job later. |
| `BatchSubmitError` | partial batch | A chunk fails after earlier chunks were accepted. | Resume only the unsent chunks. |
| `WebhookSignatureError` | before processing | Webhook signature is invalid or missing. | Return 400; do not process the event. |

```python
from thunder_slip import Client
from thunder_slip.errors import ApiError, NetworkError, QuotaExceededError, SlipNotFoundError

try:
    with Client() as client:
        result = client.verify.bank_by_image("slip.png")
        print(result.amount_in_slip)
except SlipNotFoundError:
    print("Ask the customer for a readable slip from a completed transfer.")
except QuotaExceededError:
    print("Add verification quota before processing more payments.")
except ApiError as error:
    print("Verification failed:", error.status, error.code, error.request_id)
except NetworkError:
    print("The outcome is unknown. Reconcile the payment before resubmitting it.")
```

| Situation | Automatic retry (default) |
| --- | --- |
| Connection fails before sending | Up to 2 extra attempts, including verification. |
| HTTP 429 | Up to 2 extra attempts when the delay is at most 60 seconds. |
| Safe reads and idempotent account linking | Up to 2 extra attempts for transport failures and HTTP 500, 502, 503, 504. |
| Verification or job submission after sending | Never retry read timeouts or 5xx: another send could consume quota twice. |
| Other 4xx | No automatic retry; correct the input or permissions. |

Retries use exponential backoff with jitter and respect `Retry-After` up to 60 seconds. A failed network call does not prove that a billed operation was never processed.

## Webhooks

Install Flask with `python -m pip install Flask`, save this as `webhook_app.py`, set `THUNDER_WEBHOOK_SECRET`, then run `python webhook_app.py`. The handler reads the original body and `X-Thunder-Signature`, returns 400 for an invalid signature or malformed event, and acknowledges a verified event with 204. Replace the logging step with durable storage or a queue before using it to confirm payments; process each job id once. Deploy behind HTTPS with a production WSGI server.

```python
import os
from flask import Flask, Response, request
from thunder_slip.errors import InputError, WebhookSignatureError
from thunder_slip.webhooks import construct_event

app = Flask(__name__)
webhook_secret = os.environ["THUNDER_WEBHOOK_SECRET"]


@app.post("/webhooks/thunder")
def receive_webhook() -> Response:
    raw_body = request.get_data(cache=False)
    try:
        event = construct_event(
            raw_body, request.headers.get("X-Thunder-Signature"), webhook_secret
        )
    except (WebhookSignatureError, InputError):
        return Response("Invalid webhook", status=400)
    # Save or enqueue the event durably, using job_id to prevent duplicate processing.
    app.logger.info("Verified job %s: %s", event.job_id, event.status)
    return Response(status=204)


if __name__ == "__main__":
    app.run(port=8000)
```

## Security and privacy

Keep the API key on your server, never in a browser or mobile application. Public errors and response headers redact the configured key, including percent-encoded and JSON-escaped forms, and always hide authorization headers. Transport causes contain sanitized diagnostics. `sensitive_raw_body()` returns the original error body and can expose secrets; keep it out of logs. Transfer results include personal data such as names and account numbers. Limit access, retention and what you print in application logs.

## Versioning and support policy

This SDK follows semantic versioning. Breaking public API changes require a major version. The runtime support policy follows versions still supported upstream; changes to the supported range are announced in the [changelog](CHANGELOG.md).

## Examples and documentation

[Runnable examples](examples/README.md) include one program per operation. Read the [Python SDK guide](https://document.thunder.in.th/en/sdk/python) and [API reference](https://document.thunder.in.th) for all options.

## Support

For account, quota or billing questions, use the [contact page](https://developer.thunder.in.th/contact) and include the request id if available. Report bugs and suggest features in [issues](https://github.com/THUNDER-SOLUTION-CO-LTD/sdk-python/issues). Never post API keys or real slip images.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, checks and pull requests. Maintainers follow [RELEASING.md](RELEASING.md).

## Security reports

Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md), or use the [contact page](https://developer.thunder.in.th/contact). Never report vulnerabilities in public issues.

## License

[MIT](LICENSE). Copyright (c) 2026 Thunder Solution Co., Ltd.
