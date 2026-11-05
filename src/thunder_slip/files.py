"""Bounded, content-sniffed image input."""

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from .errors import InputError


@dataclass(frozen=True)
class ImageInput:
    """An image ready for multipart upload."""

    data: bytes
    content_type: str
    filename: str


def image_input(value: str | Path | bytes | BinaryIO, *, max_bytes: int) -> ImageInput:
    """Read at most limit+1 bytes from paths or streams and validate image magic."""
    if max_bytes <= 0:
        raise InputError("INVALID_ARGUMENT", "Image size limit must be positive")
    if isinstance(value, (str, Path)):
        path = Path(value)
        try:
            with path.open("rb") as stream:
                data = stream.read(max_bytes + 1)
        except OSError:
            raise InputError("FILE_NOT_READABLE", "Cannot read image file") from None
    elif isinstance(value, bytes):
        data = value
    else:
        try:
            data = value.read(max_bytes + 1)
        except (OSError, ValueError, AttributeError):
            raise InputError("FILE_NOT_READABLE", "Cannot read image stream") from None
    if not isinstance(data, bytes):
        raise InputError("INVALID_ARGUMENT", "Expected a binary image stream")
    if not data:
        raise InputError("EMPTY_FILE", "Image is empty")
    if len(data) > max_bytes:
        raise InputError("FILE_TOO_LARGE", "Image exceeds upload size limit")
    if data.startswith(b"\x89PNG"):
        mime = "image/png"
    elif data.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    elif data.startswith(b"GIF8"):
        mime = "image/gif"
    elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        mime = "image/webp"
    else:
        raise InputError("UNSUPPORTED_FILE_TYPE", "Unsupported image content")
    extension = {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/gif": "gif",
        "image/webp": "webp",
    }[mime]
    filename = f"slip.{extension}"
    return ImageInput(data, mime, filename)
