"""Image upload minimum signatures and upload-size boundaries."""

import asyncio
import httpx
import pytest
from thunder_slip import Client, AsyncClient
from thunder_slip.errors import ApiError, InputError
from thunder_slip.files import image_input

LIMIT = 4194304
CASES = [
    ("jpeg-min", b"\xff\xd8\xff", "image/jpeg", None),
    ("jpeg-short", b"\xff\xd8", None, "UNSUPPORTED_FILE_TYPE"),
    ("png-min", b"\x89PNG", "image/png", None),
    ("png-short", b"\x89PN", None, "UNSUPPORTED_FILE_TYPE"),
    ("gif-min", b"GIF8", "image/gif", None),
    ("gif-short", b"GIF", None, "UNSUPPORTED_FILE_TYPE"),
    ("webp-min", b"RIFFabcdWEBP", "image/webp", None),
    ("webp-short", b"RIFFabcdWEB", None, "UNSUPPORTED_FILE_TYPE"),
    ("png-eight", b"\x89PNG\r\n\x1a\n", "image/png", None),
    ("empty", b"", None, "EMPTY_FILE"),
    ("at-limit", b"\x89PNG" + bytes(LIMIT - 4), "image/png", None),
    ("over-limit", b"\x89PNG" + bytes(LIMIT - 3), None, "FILE_TOO_LARGE"),
]


@pytest.mark.parametrize("name,data,mime,code", CASES, ids=[r[0] for r in CASES])
def test_signature_boundary(name, data, mime, code):
    if code:
        with pytest.raises(InputError) as caught:
            image_input(data, max_bytes=LIMIT)
        assert caught.value.code == code
    else:
        image = image_input(data, max_bytes=LIMIT)
        assert image.content_type == mime
        assert image.data == data


@pytest.mark.parametrize("name,data,mime,code", CASES, ids=[r[0] for r in CASES])
@pytest.mark.parametrize("asynchronous", [False, True])
def test_sync_async_upload_boundary(name, data, mime, code, asynchronous):
    sends = 0

    def handler(request):
        nonlocal sends
        sends += 1
        assert f"Content-Type: {mime}".encode() in request.content
        return httpx.Response(
            400, json={"error": {"code": "VALIDATION_ERROR", "message": "fixture"}}
        )

    expected = InputError if code else ApiError

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            async with AsyncClient("synthetic", http=http, max_retries=0) as client:
                with pytest.raises(expected) as caught:
                    await client.verify.bank_by_image(data)
                assert caught.value.code == (code or "VALIDATION_ERROR")

    if asynchronous:
        asyncio.run(run())
    else:
        with httpx.Client(transport=httpx.MockTransport(handler)) as http:
            with Client("synthetic", http=http, max_retries=0) as client:
                with pytest.raises(expected) as caught:
                    client.verify.bank_by_image(data)
                assert caught.value.code == (code or "VALIDATION_ERROR")
    assert sends == (0 if code else 1)
