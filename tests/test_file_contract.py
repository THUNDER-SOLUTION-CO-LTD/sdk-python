from thunder_slip.files import image_input


def test_path_filename_is_sniffed_and_normalized(tmp_path):
    path = tmp_path / "private-account-name.jpeg"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 8)
    image = image_input(path, max_bytes=4194304)
    assert image.filename == "slip.png"
    assert image.content_type == "image/png"


def test_unreadable_or_text_stream_has_typed_safe_error():
    import io
    import pytest
    from thunder_slip.errors import InputError

    class Broken:
        def read(self, _limit):
            raise OSError("private-key-in-caller-error")

    for stream in [Broken(), io.StringIO("text")]:
        with pytest.raises(InputError) as raised:
            image_input(stream, max_bytes=4194304)
        assert "private-key" not in str(raised.value)
