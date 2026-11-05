"""The installed package exposes the documented defaults and error hierarchy."""

from pathlib import Path
import tomllib
from thunder_slip import Client, Thunder, ThunderError
from thunder_slip.errors import ApiError, InputError, NetworkError
from thunder_slip.webhooks import SIGNATURE_HEADER

ROOT = Path(__file__).parents[1]


def test_defaults_and_environment(monkeypatch, tmp_path):
    for name in ("THUNDER_API_KEY", "THUNDER_V1_BASE_URL", "THUNDER_V2_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    key = tmp_path / "key"
    key.write_text("fixture-key\n")
    monkeypatch.setenv("THUNDER_API_KEY_FILE", str(key))
    with Client() as client:
        assert client._v1._base == "https://api.thunder.in.th/v1"
        assert client._v2._base == "https://api.thunder.in.th/v2"
        assert (
            client._v2._agent.startswith("thunder-slip-python/") and " python/" in client._v2._agent
        )
        assert "fixture-key" not in repr(client)
    assert Thunder is Client
    assert SIGNATURE_HEADER == "X-Thunder-Signature"
    for error in (ApiError, InputError, NetworkError):
        assert issubclass(error, ThunderError)


def test_package_metadata_and_license():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert data["name"] == "thunder-solution-sdk"
    assert data["license"] == "MIT"
    assert data["authors"] == [{"name": "Thunder Solution Co., Ltd."}]
    assert "Copyright (c) 2026 Thunder Solution Co., Ltd." in (ROOT / "LICENSE").read_text()
    url = "https://github.com/THUNDER-SOLUTION-CO-LTD/sdk-python"
    assert data["urls"] == {"Repository": url, "Homepage": url, "Issues": url + "/issues"}
    for name in ("README.md", "README.th.md"):
        text = (ROOT / name).read_text()
        assert "pip install thunder-solution-sdk" in text
        assert "from thunder_slip import Client" in text
        assert url in text
    assert (ROOT / "src/thunder_slip/py.typed").exists()
