"""QR request shapes of the API v1 rules of 2026-10-30 are sent exactly as given."""

import json
import httpx
from thunder_slip import Client
from thunder_slip.models import QrRequest

PNG = "iVBORw0KGgo="
REQUESTS = [
    (
        QrRequest(type="PROMPTPAY", biller_id="010555123456701", amount=125.5),
        {"type": "PROMPTPAY", "billerId": "010555123456701", "amount": 125.5},
    ),
    (
        QrRequest(type="BILL_PAYMENT", biller_id="010555123456701"),
        {"type": "BILL_PAYMENT", "billerId": "010555123456701"},
    ),
    (
        QrRequest(type="KSHOP", ref1="KB000001234567", amount=250),
        {"type": "KSHOP", "ref1": "KB000001234567", "amount": 250},
    ),
    (
        QrRequest(type="KSHOP", ref1="kps004kb000001234567"),
        {"type": "KSHOP", "ref1": "kps004kb000001234567"},
    ),
    (
        QrRequest(type="MAE_MANEE", ref1="014000123456789"),
        {"type": "MAE_MANEE", "ref1": "014000123456789"},
    ),
    (
        QrRequest(
            type="TUNGNGERN",
            ref1="ORDECredential privacy2345",
            merchant_name="MY STORE",
            amount=750,
        ),
        {
            "type": "TUNGNGERN",
            "ref1": "ORDECredential privacy2345",
            "merchantName": "MY STORE",
            "amount": 750,
        },
    ),
]


def test_new_qr_shapes_are_sent_unchanged():
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        assert request.url.path == "/v1/qr/generate"
        data = {"image": PNG, "mime": "image/png", "payload": "000201"}
        return httpx.Response(200, json={"status": 200, "data": data})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with Client("synthetic", http=http) as client:
            for request, _ in REQUESTS:
                assert client.v1.generate_qr(request).payload == "000201"
    assert bodies == [wire for _, wire in REQUESTS]
