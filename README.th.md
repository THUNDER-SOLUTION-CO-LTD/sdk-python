# Thunder Python SDK

[![CI](https://github.com/THUNDER-SOLUTION-CO-LTD/sdk-python/actions/workflows/ci.yml/badge.svg)](https://github.com/THUNDER-SOLUTION-CO-LTD/sdk-python/actions/workflows/ci.yml) [![MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

ใช้ Python ตรวจสลิปโอนเงินธนาคารไทยและใบเสร็จ TrueMoney Wallet พร้อมตรวจบัญชีรับเงิน ยอดเงิน และสลิปซ้ำก่อนเติมเงินหรือยืนยันคำสั่งซื้อ

[English](README.md)

## ความสามารถ

- ตรวจสลิปธนาคารจากรูป ข้อความ QR, URL หรือ base64
- ตรวจว่ารายการโอนเข้าบัญชีที่ผูกไว้และตรงกับยอดที่ต้องชำระ
- ตรวจสลิปซ้ำก่อนรับชำระเงิน
- ตรวจใบเสร็จ TrueMoney Wallet
- ดูโควต้าคงเหลือและจัดการบัญชีรับเงิน
- ส่งสลิปเป็นชุด ติดตาม job เบื้องหลัง และตรวจลายเซ็น webhook
- สร้าง QR สำหรับพร้อมเพย์และบิลเพย์เมนต์

## สิ่งที่ต้องเตรียม

Python 3.11 ถึง 3.15 สร้างบริการใน [Thunder developer portal](https://developer.thunder.in.th) แล้วนำ API key ของบริการนั้นมาเก็บใน environment ของเซิร์ฟเวอร์ชื่อ `THUNDER_API_KEY` หรือใช้ `THUNDER_API_KEY_FILE` ชี้ไปยังไฟล์ส่วนตัวที่เก็บ key

## ติดตั้ง

```sh
python -m pip install thunder-solution-sdk
```

## เริ่มตรวจสลิป

บันทึกโปรแกรมด้านล่างเป็น `verify_payment.py` เตรียมสลิปชื่อ `slip.png` และตั้ง API key ให้เรียบร้อย เพิ่มบัญชีรับเงินใน portal แล้วผูกกับบริการ/สาขาที่ใช้ key นี้ เปลี่ยน `150.0` เป็นยอดคำสั่งซื้อจากฐานข้อมูลของคุณเอง อย่าใช้ยอดที่ลูกค้าส่งมา การตรวจแต่ละครั้งอาจใช้โควต้า

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

รัน `python verify_payment.py` เมื่อตรวจผ่าน ผลลัพธ์จะมีลักษณะดังนี้ (ข้อมูลตัวอย่าง):

    Amount: 150.0
    Date: 2026-10-29T14:32:00+07:00
    Sender: ผู้โอนตัวอย่าง
    Receiver: ร้านตัวอย่าง
    Transaction: EXAMPLE-TRANSFER-001
    Payment checks passed. Record this transaction once for the order.

เติมเงินหรือยืนยันคำสั่งซื้อเมื่อผ่านทุกเงื่อนไขแล้วเท่านั้น เก็บเลขอ้างอิงรายการโอนแบบไม่ให้ซ้ำในฐานข้อมูล และอัปเดตคำสั่งซื้อใน transaction เดียวกัน เพื่อกันคำขอที่เข้ามาพร้อมกันเติมเงินซ้ำ SDK ไม่ได้อัปเดตคำสั่งซื้อให้

อ่านต่อ: [เงื่อนไขรับชำระ](#เงื่อนไขรับชำระ), [บัญชีรับเงิน](#บัญชีรับเงิน), [งานเบื้องหลัง](#งานเบื้องหลัง), [จัดการข้อผิดพลาด](#จัดการข้อผิดพลาด)

## วิธีใช้งาน

### ตรวจสลิปธนาคาร

| สิ่งที่มี | เมธอด |
| --- | --- |
| ไฟล์รูปหรือ bytes จากการอัปโหลด | `client.verify.bank_by_image` |
| ข้อความ payload ของ QR | `client.verify.bank_by_payload` |
| URL รูปที่เข้าถึงได้จากภายนอก | `client.verify.bank_by_url` |
| รูปแบบ base64 | `client.verify.bank_by_base64` |

payload คือข้อความที่อ่านจาก QR บนสลิป ไม่ใช่เลขอ้างอิงรายการโอน รูปส่งเป็น path, `bytes` หรือ binary file object ได้ ถ้าส่ง string SDK จะอ่านไฟล์ตาม path นั้นบนเซิร์ฟเวอร์ จึงห้ามนำ string จากผู้ใช้มาส่งตรงๆ

```python
from pathlib import Path
from thunder_slip import Client

with Client() as client:
    result = client.verify.bank_by_payload(Path("payload.txt").read_text().strip())
    print(result.amount_in_slip, result.raw_slip.trans_ref)
```

### เงื่อนไขรับชำระ

API v2 ส่งผลการตรวจมากับ response ที่สำเร็จ: `is_duplicate=True`, `is_amount_matched=False` หรือ `matched_account=None` หมายถึงต้องไม่รับชำระรายการนี้ ค่าที่ไม่ตรงไม่ได้ทำให้เกิด API error ตัวอย่างเริ่มต้นจึงตรวจผลเหล่านี้และปฏิเสธเมื่อไม่มีผลตรวจด้วย `matchAccount` ตรวจบัญชีที่ผูกกับบริการ/สาขานี้ `matchAmount` เทียบยอดโอนกับยอดคำสั่งซื้อ และ `checkDuplicate` ตรวจว่าเคยใช้สลิปนี้แล้วหรือไม่

```python
from thunder_slip import Client
from thunder_slip.models import VerifyOptions

with Client() as client:
    result = client.verify.bank_by_image(
        "slip.png", VerifyOptions(match_account=True, match_amount=150.0, check_duplicate=True)
    )
    print(result.is_duplicate, result.is_amount_matched, result.matched_account)
```

### ใบเสร็จ TrueMoney Wallet

ใช้รูปใบเสร็จ Wallet และตรวจผลบัญชี ยอดเงิน และสลิปซ้ำก่อนยืนยันคำสั่งซื้อเช่นเดียวกับสลิปธนาคาร เลขอ้างอิงอยู่ที่ `raw_slip.transaction_id`

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

### ข้อมูลบริการและโควต้า

ดูโควต้าก่อนวางแผนส่งสลิปเป็นชุด ถ้าโควต้าคงเหลือเป็น null แปลว่า API ไม่ได้ส่งขีดจำกัดเป็นตัวเลข ไม่ใช่โควต้าเป็นศูนย์

```python
from thunder_slip import Client

with Client() as client:
    info = client.get_info()
    print("Remaining quota:", info.application.quota.remaining)
```

### บัญชีรับเงิน

ตัวอย่างนี้ไล่อ่านบัญชีที่ผูกไว้ทุกหน้า สร้างบัญชีรับเงิน แก้ชื่อ แล้วผูกกับสาขาที่ใช้ key ตั้ง `RECEIVING_ACCOUNT_NUMBER` เป็นเลขบัญชีของคุณ สร้างครั้งเดียวแล้วเก็บ id ไว้ใช้ต่อ `list()` และ `list_all()` คืนทีละหน้า ส่วน `iterate_all()` อ่านทุกบัญชีของบริการ

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

### งานเบื้องหลัง

ส่ง payload ของ QR เป็นชุดและเก็บ job id ของแต่ละรายการ การติดตาม job เดิมไม่ได้ส่งตรวจสลิปใหม่ `wait_for_job` รอได้สิบนาทีโดยค่าเริ่มต้น รวมเวลาส่ง HTTP และรอก่อนลองใหม่ ต้องตรวจสถานะสุดท้ายและผลเงื่อนไขรับชำระก่อนใช้ผล

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

### สร้าง QR รับชำระ

ตั้ง `PROMPTPAY_PHONE` เป็นเบอร์พร้อมเพย์ของคุณ สำหรับบิลเพย์เมนต์ใช้ `type="PROMPTPAY"` พร้อม `biller_id` และ `ref1` โดย `ref2` ไม่บังคับ ส่วน `BILL_PAYMENT` ยังใช้ได้สำหรับระบบที่เชื่อมต่อไว้แล้ว ยอดเงินต้องอยู่ในช่วง 0.01 ถึง 9,999,999,999.99 และมีทศนิยมไม่เกินสองตำแหน่ง ถ้าไม่กำหนดยอดให้เว้น amount ไว้ บันทึกรูปที่ API ส่งกลับได้ดังนี้:

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

### API v1 สำหรับระบบเดิม

ระบบใหม่ควรใช้ v2 ระบบเดิมที่ยังเรียก v1 ใช้ผ่าน `client.v1` ได้ โดยคืนข้อมูลสลิปโดยตรง และการตรวจพบสลิปซ้ำจะเป็น `DuplicateSlipError`

```python
from thunder_slip import Client
from thunder_slip.models import V1VerifyOptions

with Client() as client:
    slip = client.v1.verify_bank_by_image("slip.png", V1VerifyOptions(check_duplicate=True))
    print(slip.amount.amount, slip.trans_ref)
```

### คำขอแบบ async

ใช้ `AsyncClient` ในแอป async แล้ว `await` แต่ละเมธอด ใช้ client เดียวกับหลายคำขอได้ และควรจำกัดจำนวนคำขอพร้อมกันตามโควต้าและทรัพยากรเซิร์ฟเวอร์

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

## ข้อมูลผลตรวจ

ผลธนาคารและ Wallet มีฟิลด์ยอดเงินและผลเงื่อนไขรับชำระเหมือนกัน รายละเอียดธนาคารอยู่ใน `raw_slip` ส่วน Wallet ใช้โมเดลใบเสร็จของตัวเอง ฟิลด์ที่ไม่บังคับจะมีเมื่อ API ส่งมาเท่านั้น: `UNSET` คือไม่มีฟิลด์ ส่วน `None` คือ JSON null

| ฟิลด์ | ชนิด | ความหมาย | ตัวอย่าง |
| --- | --- | --- | --- |
| `amount_in_slip` | float | ยอดโอนที่ตรวจได้ หน่วยบาท | 150.0 |
| `is_duplicate` | optional bool | เคยใช้สลิปนี้แล้วหรือไม่ | false |
| `is_amount_matched` | optional bool | ยอดโอนตรงกับคำสั่งซื้อหรือไม่ | true |
| `amount_in_order` | optional float | ยอดคำสั่งซื้อที่ส่งไปเทียบ | 150.0 |
| `matched_account` | optional account or null | บัญชีรับเงินที่ผูกไว้และตรงกับรายการ | account object |
| `raw_slip.trans_ref` | string | เลขอ้างอิงรายการโอนธนาคาร | EXAMPLE-TRANSFER-001 |
| `raw_slip.date` | string | วันเวลาโอน รวม offset หาก API ส่งมา | 2026-10-29T14:32:00+07:00 |
| `raw_slip.sender.account.name.th` | optional string | ชื่อผู้โอนภาษาไทย | ผู้โอนตัวอย่าง |
| `raw_slip.receiver.account.name.th` | optional string | ชื่อผู้รับภาษาไทย | ร้านตัวอย่าง |
| `raw_slip.sender.account.bank.account` | optional string | เลขบัญชีผู้โอนตามที่ API ส่งมา อาจปิดบังบางส่วน | xxx-x-x1234-x |
| `raw_slip.receiver.account.bank.account` | optional string | เลขบัญชีผู้รับตามที่ API ส่งมา อาจปิดบังบางส่วน | xxx-x-x5678-x |
| `raw_slip.transaction_id` | string (Wallet) | เลขอ้างอิงรายการ Wallet | EXAMPLE-WALLET-001 |
| `raw_slip.sender.name` | string (Wallet) | ชื่อผู้ส่ง Wallet | ผู้ส่งตัวอย่าง |
| `raw_slip.receiver.name` | string (Wallet) | ชื่อผู้รับ Wallet | ผู้รับตัวอย่าง |
| `raw_slip.receiver.phone` | string (Wallet) | เบอร์ผู้รับ Wallet ตามที่ API ส่งมา | 0xx-xxx-1234 |

ดู [โมเดล Python ฉบับเต็ม](https://document.thunder.in.th/th/sdk/python)

## ตั้งค่า

| ตัวเลือก | Environment variable | ค่าเริ่มต้น | หน้าที่ |
| --- | --- | --- | --- |
| `api_key` | THUNDER_API_KEY; THUNDER_API_KEY_FILE | environment/file | key ที่ส่งตรงมีลำดับก่อน environment และใช้ไฟล์เป็นทางเลือกสุดท้าย |
| `timeout` | none | 30 seconds | เวลาสูงสุดของ HTTP แต่ละครั้ง |
| `max_retries` | none | 2 | ลองเพิ่มได้ไม่เกินสองครั้งเมื่อเข้าเงื่อนไข retry |
| `v2_base_url / v1_base_url` | THUNDER_V2_BASE_URL; THUNDER_V1_BASE_URL | https://api.thunder.in.th/v2; https://api.thunder.in.th/v1 | กำหนด URL ของ API |
| `http` | none | new HTTP client | ใช้ HTTP client ที่เตรียมเองและปิดเองเมื่อเสร็จ |

ตัวอย่างปิดทั้ง HTTP client ที่สร้างเองและ SDK client ถ้าใช้ค่าเริ่มต้น `with Client()` จะปิดการเชื่อมต่อให้อัตโนมัติ

```python
import httpx
from thunder_slip import Client

with httpx.Client(trust_env=False, follow_redirects=False) as http:
    with Client(timeout=15, max_retries=1, http=http) as client:
        print(client.get_info().application.name)
```

## จัดการข้อผิดพลาด

`ThunderError` เป็น exception หลัก โดย `ApiError` ครอบคลุมข้อผิดพลาด HTTP และ `RequestTimeoutError` เป็นชนิดย่อยของ `NetworkError`

SDK เลือกคลาสจากรหัสข้อผิดพลาดที่รู้จักก่อน ถ้าไม่รู้จักจึงเลือกตาม HTTP status ส่วน 4xx ที่ไม่ได้ระบุใช้ `ApiError`

| คลาส | HTTP status หรือจุดที่เกิด | สาเหตุ | วิธีจัดการ |
| --- | --- | --- | --- |
| `ThunderError` | ขึ้นกับข้อผิดพลาด | คลาสหลักของข้อผิดพลาด SDK | ดักคลาสที่เฉพาะเจาะจงก่อน |
| `ApiError` | HTTP | คลาสหลักของคำขอที่ API ปฏิเสธ | ดู status, code และ request id |
| `AuthenticationError` | 401 | API key ไม่ถูกต้อง | ตรวจ key ของบริการนี้ |
| `PermissionDeniedError` | 403 | บริการ สาขา หรือ IP ไม่มีสิทธิ์เรียก API | ตรวจสิทธิ์บริการและข้อจำกัด IP |
| `QuotaExceededError` | 403 | โควต้าตรวจสลิปหมด | เพิ่มโควต้าก่อนรับสลิปเพิ่ม |
| `InvalidRequestError` | 400 | API ไม่รับค่าที่ส่งไป | แก้ข้อมูลก่อนส่งอีกครั้ง |
| `InvalidImageError` | 400 | รูปอ่านไม่ได้ ใหญ่เกิน หรือไม่รองรับ | ส่งรูปสลิปที่ชัดและเป็นชนิดที่รองรับ |
| `InvalidUrlError` | 400 | API ไม่รับ URL รูปหรือ callback | ใช้ HTTPS URL ที่เข้าถึงได้จากภายนอก |
| `DuplicateSlipError` | 400 (v1) | ส่งสลิปที่เคยตรวจแล้วโดยเปิดตรวจสลิปซ้ำ | อย่าเติมเงินซ้ำ ตรวจผลเดิมจาก slip |
| `NotFoundError` | 404 | ไม่พบข้อมูลหรือข้อมูลอยู่นอกสาขานี้ | ตรวจ id บัญชีหรือ job และสาขา |
| `SlipNotFoundError` | 404 | ไม่พบรายการโอนหรือ QR สลิป | ขอสลิปที่ชัดจากรายการโอนสำเร็จ |
| `SlipPendingError` | 404 | ธนาคารยังไม่พร้อมให้ตรวจสลิปที่เพิ่งโอน | รอสักครู่แล้วตรวจใหม่ |
| `ConflictError` | 409 | มีบัญชีรับเงินนี้แล้ว | ใช้บัญชีเดิมแทนการสร้างซ้ำ |
| `RateLimitError` | 429 | ส่งคำขอถี่เกินไป | รอตาม retry_after หากมี |
| `ServerError` | 500, 502, 504; 5xx อื่นยกเว้น 503 | API หรือธนาคารประมวลผลไม่สำเร็จ | ตรวจผลรายการที่อาจใช้โควต้าแล้วก่อนส่งซ้ำ |
| `ServiceUnavailableError` | 503 | บริการที่เกี่ยวข้องไม่พร้อม | รอและตรวจสถานะบริการ |
| `InputError` | ก่อนส่ง | SDK ไม่รับข้อมูลก่อนส่ง | แก้ค่าที่ระบุใน code |
| `NetworkError` | เครือข่าย | เชื่อมต่อไม่สำเร็จ | ตรวจเครือข่ายและผลรายการก่อนส่งซ้ำ |
| `RequestTimeoutError` | เครือข่าย | คำขอ HTTP เกินเวลาที่ตั้งไว้ | ตรวจผลการจ่ายก่อนส่งซ้ำ |
| `JobWaitTimeoutError` | หมดเวลารอ job | รอผล job เกินเวลารวม | เก็บ last_job แล้วติดตาม job เดิมภายหลัง |
| `BatchSubmitError` | ส่ง batch บางส่วน | บางชุดส่งไม่สำเร็จหลัง API รับชุดก่อนหน้าแล้ว | ส่งต่อเฉพาะชุดที่ยังไม่ได้รับ |
| `WebhookSignatureError` | ก่อนประมวลผล | ลายเซ็น webhook ไม่ถูกต้องหรือไม่มี | ตอบ 400 และอย่าประมวลผล event |

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

| กรณี | การลองซ้ำอัตโนมัติ (ค่าเริ่มต้น) |
| --- | --- |
| เชื่อมต่อไม่ได้ก่อนส่ง | ลองเพิ่มไม่เกิน 2 ครั้ง รวมคำขอตรวจสลิป |
| HTTP 429 | ลองเพิ่มไม่เกิน 2 ครั้งเมื่อเวลารอไม่เกิน 60 วินาที |
| การอ่านและผูกบัญชีที่ทำซ้ำได้ | ลองเพิ่มไม่เกิน 2 ครั้งเมื่อเครือข่ายผิดพลาดหรือ HTTP 500, 502, 503, 504 |
| ตรวจสลิปหรือส่ง job หลังส่งคำขอแล้ว | ไม่ลองซ้ำเมื่อ read timeout หรือ 5xx เพราะส่งใหม่อาจใช้โควต้าซ้ำ |
| 4xx อื่นๆ | ไม่ลองซ้ำอัตโนมัติ แก้ข้อมูลหรือสิทธิ์ก่อน |

SDK เพิ่มเวลารอก่อนลองซ้ำแบบ exponential backoff พร้อม jitter และใช้ `Retry-After` ไม่เกิน 60 วินาที เครือข่ายที่ขัดข้องไม่ได้ยืนยันว่ารายการที่ใช้โควต้ายังไม่ถูกประมวลผล

## Webhook

ติดตั้ง Flask ด้วย `python -m pip install Flask` บันทึกเป็น `webhook_app.py` ตั้ง `THUNDER_WEBHOOK_SECRET` แล้วรัน `python webhook_app.py` handler อ่าน body เดิมและ `X-Thunder-Signature` ตอบ 400 เมื่อลายเซ็นหรือข้อมูล event ไม่ถูกต้อง และตอบ 204 เมื่อยืนยัน event ได้ ก่อนใช้ยืนยันการจ่ายจริง ให้เปลี่ยนขั้นตอน log เป็นการเก็บลงฐานข้อมูลหรือคิวอย่างถาวร และประมวลผลแต่ละ job id เพียงครั้งเดียว ใช้ HTTPS ผ่าน WSGI server สำหรับ production

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

## ความปลอดภัยและข้อมูลส่วนบุคคล

เก็บ API key ไว้ฝั่งเซิร์ฟเวอร์ ห้ามใส่ใน browser หรือแอปมือถือ ข้อผิดพลาดและ response header ที่ SDK เปิดให้อ่านจะปิดบัง key ที่ตั้งไว้ รวมรูปแบบ percent-encoded และ JSON-escaped และปิดบัง authorization header เสมอ สาเหตุจาก transport เก็บเฉพาะข้อมูลวินิจฉัยที่ล้างข้อมูลลับแล้ว `sensitive_raw_body()` คืน body ข้อผิดพลาดต้นฉบับซึ่งอาจมีข้อมูลลับ จึงไม่ควรนำไป log ผลตรวจมีข้อมูลส่วนบุคคล เช่น ชื่อและเลขบัญชี ควรจำกัดสิทธิ์ ระยะเวลาเก็บ และข้อมูลที่เขียนลง log ของแอป

## เวอร์ชันและระยะเวลารองรับ

SDK ใช้ semantic versioning การเปลี่ยน public API ที่ทำให้โค้ดเดิมใช้ไม่ได้จะเพิ่ม major version รองรับ runtime ที่ยังได้รับการดูแลจากผู้พัฒนา หากเปลี่ยนช่วงเวอร์ชันที่รองรับจะแจ้งใน [changelog](CHANGELOG.md)

## ตัวอย่างและเอกสาร

[ตัวอย่างที่รันได้](examples/README.md) แยกโปรแกรมตามแต่ละเมธอด ดูตัวเลือกทั้งหมดได้ที่ [คู่มือ Python SDK](https://document.thunder.in.th/th/sdk/python) และ [API reference](https://document.thunder.in.th)

## ช่วยเหลือ

เรื่องบัญชี โควต้า หรือการชำระเงิน ติดต่อผ่าน[หน้าติดต่อเรา](https://developer.thunder.in.th/contact) พร้อม request id ถ้ามี แจ้งบั๊กหรือขอฟีเจอร์ได้ใน [issues](https://github.com/THUNDER-SOLUTION-CO-LTD/sdk-python/issues) ห้ามแนบ API key หรือรูปสลิปจริง

## ร่วมพัฒนา

อ่านวิธีติดตั้งเครื่องมือ รันทดสอบ และส่ง pull request ใน [CONTRIBUTING.md](CONTRIBUTING.md) ผู้ดูแลการออกเวอร์ชันอ่าน [RELEASING.md](RELEASING.md)

## แจ้งปัญหาความปลอดภัย

แจ้งแบบส่วนตัวตาม [SECURITY.md](SECURITY.md) หรือติดต่อผ่าน[หน้าติดต่อ](https://developer.thunder.in.th/contact) ห้ามแจ้งช่องโหว่ใน issue สาธารณะ

## สัญญาอนุญาต

[MIT](LICENSE). Copyright (c) 2026 Thunder Solution Co., Ltd.
