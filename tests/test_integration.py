import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ach_intelligence.api import create_app
from ach_intelligence.config import Settings
from ach_intelligence.fixtures import make_file, mutate

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv("TEST_MOOV_URL"), reason="Set TEST_MOOV_URL for the real Moov service"
    ),
]


def test_real_moov_and_persistence(tmp_path: Path):
    config = Settings(
        moov_url=os.environ["TEST_MOOV_URL"],
        database_url=os.getenv("TEST_DATABASE_URL", f"sqlite:///{tmp_path / 'live.db'}"),
    )
    with TestClient(create_app(config)) as client:
        assert client.get("/health").status_code == 200
        valid = client.post(
            "/api/v1/ach/files",
            headers={"X-Synthetic-Data": "true"},
            files={"file": ("valid.ach", make_file(), "text/plain")},
        )
        assert valid.status_code == 201, valid.text
        assert valid.json()["validation_status"] in {"valid", "needs_review"}, valid.text
        assert valid.json()["adapter"]["status"] == "valid"
        bad = client.post(
            "/api/v1/ach/files",
            headers={"X-Synthetic-Data": "true"},
            files={
                "file": ("bad.ach", mutate(make_file(), 4, 32, 44, "000000000001"), "text/plain")
            },
        )
        assert bad.status_code == 201, bad.text
        assert bad.json()["validation_status"] == "invalid"
        assert any(e["source"] == "moov" for e in bad.json()["exceptions"])
