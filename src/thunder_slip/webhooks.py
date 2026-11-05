"""Standalone webhook authentication and typed event parsing."""

import json
from .webhook import verify_signature as verify_signature
from ._codec import DecodeError, decode
from .models import WebhookEvent
from .errors import InputError, WebhookSignatureError

SIGNATURE_HEADER: str = "X-Thunder-Signature"


def parse_event(raw_body: bytes | str) -> WebhookEvent:
    """Parse the original UTF-8 body without verifying its signature."""
    try:
        return decode(WebhookEvent, json.loads(raw_body))
    except (json.JSONDecodeError, UnicodeDecodeError, DecodeError):
        pass
    raise InputError("INVALID_ARGUMENT", "Webhook body must be a valid event JSON object")


def construct_event(raw_body: bytes | str, signature: str | None, secret: str) -> WebhookEvent:
    """Verify HMAC before parsing, or raise WebhookSignatureError."""
    if not verify_signature(raw_body, signature, secret):
        raise WebhookSignatureError("Invalid webhook signature")
    return parse_event(raw_body)
