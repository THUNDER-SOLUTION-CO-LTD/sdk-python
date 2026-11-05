"""Raw-body signature primitives; typed webhook models follow the shared spec."""

import hashlib
import hmac
import json
from typing import Any


def verify_signature(raw_body: bytes | str, signature: str | None, secret: str) -> bool:
    """Verify a sha256= hexadecimal HMAC over the exact raw UTF-8 body."""
    if not secret or not signature or not signature.startswith("sha256="):
        return False
    digest = signature[7:]
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        return False
    body = raw_body.encode("utf8") if isinstance(raw_body, str) else raw_body
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, digest)


def parse_webhook(raw_body: bytes) -> dict[str, Any]:
    """Decode an object; verify its raw signature before trusting it."""
    value: Any = json.loads(raw_body)
    if not isinstance(value, dict):
        raise ValueError("Webhook body must be an object")
    return value
