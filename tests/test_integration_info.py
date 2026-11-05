"""Read-only account connectivity check, enabled explicitly by the caller."""

import os
import pytest
from thunder_slip import Client, AsyncClient

pytestmark = pytest.mark.skipif(
    os.environ.get("THUNDER_INTEGRATION") != "1", reason="THUNDER_INTEGRATION is not enabled"
)


def test_account_info():
    with Client() as client:
        assert client.get_info().meta.status == 200


async def test_async_account_info():
    async with AsyncClient() as client:
        assert (await client.get_info()).meta.status == 200
