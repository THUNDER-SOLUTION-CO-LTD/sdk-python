"""Opt-in two-call integration smoke for the deadline and error changes."""

import json
import os
from pathlib import Path
import pytest
from thunder_slip import Client
from thunder_slip.errors import ApiError
from test_conformance import FIXTURES


@pytest.mark.skipif(
    os.environ.get("THUNDER_JOB_INTEGRATION") != "1", reason="explicit integration smoke only"
)
def test_wait_and_error_live():

    url = os.environ["THUNDER_V2_BASE_URL"]
    assert url.startswith("https://")
    key = Path(os.environ["THUNDER_API_KEY_FILE"]).read_text().strip()
    job_id = json.loads((FIXTURES / "v2/jobs/get/done.json").read_text())["call"]["args"]["jobId"]
    with Client(
        key,
        v2_base_url=url,
        max_retries=0,
    ) as client:
        job = client.jobs.wait_for_job(job_id, timeout=20)
        assert job.status == "done"
        with pytest.raises(ApiError) as raised:
            client.jobs.get("00000000-0000-0000-0000-000000000000")
        assert raised.value.status == 404
        assert key not in str(raised.value) + repr(raised.value) + repr(raised.value.args)
        print("integration wait terminal=done; error status=404; credential views safe")
